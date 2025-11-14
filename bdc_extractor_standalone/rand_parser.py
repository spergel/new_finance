#!/usr/bin/env python3
"""
RAND (Rand Capital Corp) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filtering; de-dup; industry enrichment.
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass
import os
import csv
import requests

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class RANDInvestment:
    company_name: str
    business_description: Optional[str] = None
    investment_type: str = "Unknown"
    industry: str = "Unknown"
    acquisition_date: Optional[str] = None
    maturity_date: Optional[str] = None
    principal_amount: Optional[float] = None
    cost: Optional[float] = None
    fair_value: Optional[float] = None
    interest_rate: Optional[str] = None
    reference_rate: Optional[str] = None
    spread: Optional[str] = None
    floor_rate: Optional[str] = None
    pik_rate: Optional[str] = None
    context_ref: Optional[str] = None
    shares_units: Optional[str] = None
    percent_net_assets: Optional[str] = None
    currency: Optional[str] = None
    commitment_limit: Optional[float] = None
    undrawn_commitment: Optional[float] = None


class RANDExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "RAND") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Rand_Capital_Corp", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        resp = requests.get(filing_url, headers=self.headers)
        resp.raise_for_status()
        content = resp.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
            logger.info(f"Filtered contexts to instant {sel}: {len(contexts)} remaining")

        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]

        facts_by_context = self._extract_facts(content)
        investments: List[RANDInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # de-dup
        ded = []
        seen = set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen:
                continue
            seen.add(combo)
            ded.append(inv)
        investments = ded

        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        ind_br = defaultdict(int)
        type_br = defaultdict(int)
        for inv in investments:
            ind_br[inv.industry] += 1
            type_br[inv.investment_type] += 1

        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'RAND_Rand_Capital_Corp_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
            ])
            writer.writeheader()
            for inv in investments:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(inv.investment_type)
                standardized_industry = standardize_industry(inv.industry)
                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)
                
                writer.writerow({
                    'company_name': inv.company_name,
                    'industry': standardized_industry,
                    'business_description': inv.business_description,
                    'investment_type': standardized_inv_type,
                    'acquisition_date': inv.acquisition_date,
                    'maturity_date': inv.maturity_date,
                    'principal_amount': inv.principal_amount,
                    'cost': inv.cost,
                    'fair_value': inv.fair_value,
                    'interest_rate': inv.interest_rate,
                    'reference_rate': standardized_ref_rate,
                    'spread': inv.spread,
                    'floor_rate': inv.floor_rate,
                    'pik_rate': inv.pik_rate,
                })

        logger.info(f"Saved to {out_file}")
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(ind_br),
            'investment_type_breakdown': dict(type_br)
        }

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        contexts: List[Dict] = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1)
            chtml = m.group(2)
            tm = tp.search(chtml)
            if not tm:
                continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', chtml)
            sd = re.search(r'<startDate>([^<]+)</startDate>', chtml)
            ed = re.search(r'<endDate>([^<]+)</endDate>', chtml)
            same_ind = None
            sm = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', chtml, re.DOTALL|re.IGNORECASE)
            if sm:
                same_ind = self._industry_member_to_name(sm.group(1).strip())
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': same_ind or parsed['industry'],
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        if ',' in identifier:
            last = identifier.rfind(',')
            company = identifier[:last].strip()
            tail = identifier[last+1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
        patterns = [
            r'First\s+lien\s+.*$', r'Second\s+lien\s+.*$', r'Unitranche\s*\d*$', r'Senior\s+secured\s*\d*$',
            r'Secured\s+Debt\s*\d*$', r'Unsecured\s+Debt\s*\d*$', r'Preferred\s+Equity$', r'Preferred\s+Stock$',
            r'Common\s+Stock\s*\d*$', r'Member\s+Units\s*\d*$', r'Warrants?$'
        ]
        it = None
        for p in patterns:
            mm = re.search(p, tail, re.IGNORECASE)
            if mm:
                it = mm.group(0)
                break
        if not it and tail:
            it = tail
        if it:
            res['investment_type'] = it
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
        for concept, cref, val in sp.findall(content):
            if val and cref:
                facts[cref].append({'concept': concept, 'value': val.strip()})
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1); cref = m.group(2); html = m.group(4)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                facts[cref].append({'concept': name, 'value': txt})
            start = max(0, m.start()-3000); end = min(len(content), m.end()+3000)
            window = content[start:end]
            ref = re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref:
                facts[cref].append({'concept':'derived:ReferenceRateToken','value': ref.group(1).replace('+','').upper()})
            floor = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor:
                facts[cref].append({'concept':'derived:FloorRate','value': floor.group(1)})
            pik = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik:
                facts[cref].append({'concept':'derived:PIKRate','value': pik.group(1)})
            # Try multiple date patterns
            dates = []
            dates.extend(re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', window))
            dates.extend(re.findall(r'\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{1,2}/\d{4}\b', window))
            if dates:
                # Remove duplicates
                seen = set(); unique_dates = []
                for d in dates:
                    if d not in seen: seen.add(d); unique_dates.append(d)
                if len(unique_dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[-1]})
                elif len(unique_dates)==1:
                    date_idx = window.find(unique_dates[0])
                    date_context = window[max(0,date_idx-50):min(len(window),date_idx+50)]
                    if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', date_context, re.IGNORECASE):
                        facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    else:
                        facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[RANDInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = RANDInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v_clean = v.replace(',','').strip(); cl=c.lower()
            if any(k in cl for k in ['principalamount','ownedbalanceprincipalamount','outstandingprincipal']):
                try: inv.principal_amount=float(v_clean)
                except: pass; continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: inv.cost=float(v_clean)
                except: pass; continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: inv.fair_value=float(v_clean)
                except: pass; continue
            # Maturity date
            if 'maturitydate' in cl or ('maturity' in cl and 'date' in cl) or cl=='derived:maturitydate':
                inv.maturity_date = v.strip()
                continue
            # Acquisition date
            if 'acquisitiondate' in cl or 'investmentdate' in cl or cl=='derived:acquisitiondate':
                inv.acquisition_date = v.strip()
                continue
            # Reference rate (check BEFORE interest rate)
            if cl=='derived:referenceratetoken' or 'variableinterestratetype' in cl or ('reference' in cl and 'rate' in cl):
                if 'sofr' in cl or 'sofr' in v.lower():
                    inv.reference_rate = 'SOFR'
                elif 'libor' in cl or 'libor' in v.lower():
                    inv.reference_rate = 'LIBOR'
                elif 'prime' in cl or 'prime' in v.lower():
                    inv.reference_rate = 'PRIME'
                elif v and not v.startswith('http'):
                    inv.reference_rate = v.upper().strip()
                continue
            # Interest rate (skip if URL)
            if 'interestrate' in cl and 'floor' not in cl:
                if v and not v.startswith('http'):
                    inv.interest_rate = self._percent(v_clean)
                continue
            # Spread
            if 'spread' in cl or ('basis' in cl and 'spread' in cl) or 'investmentbasisspreadvariablerate' in cl:
                inv.spread = self._percent(v_clean)
                continue
            # Floor rate
            if 'floor' in cl and 'rate' in cl or cl=='derived:floorrate':
                inv.floor_rate = self._percent(v_clean)
                continue
            # PIK rate
            if 'pik' in cl and 'rate' in cl or cl=='derived:pikrate':
                inv.pik_rate = self._percent(v_clean)
                continue
            # Extract shares/units for equity investments
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val = v.strip().replace(',', '')
                    float(shares_val)  # Validate
                    inv.shares_units = shares_val
                except: pass
                continue
            # Extract currency from fact metadata
            if 'currency' in f: inv.currency = f.get('currency')
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        # Heuristic for commitment_limit and undrawn_commitment
        if inv.fair_value and not inv.principal_amount: inv.commitment_limit = inv.fair_value
        elif inv.fair_value and inv.principal_amount:
            if inv.fair_value > inv.principal_amount:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value - inv.principal_amount
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _percent(self, s: str) -> str:
        try:
            v=float(s)
        except:
            return f"{s}%"
        if 0<abs(v)<=1.0:
            v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={} ; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        ep=re.compile(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', re.DOTALL|re.IGNORECASE)
        for mm in cp.finditer(content):
            html=mm.group(2)
            inst=re.search(r'<instant>([^<]+)</instant>', html)
            inst=inst.group(1) if inst else None
            if not inst: continue
            em=ep.search(html)
            if not em: continue
            m[inst]=self._industry_member_to_name(em.group(1).strip())
        return m

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local=qname.split(':',1)[-1] if ':' in qname else qname
        local=re.sub(r'Member$','',local)
        if local.endswith('Sector'): local=local[:-6]
        words=re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words=re.sub(r'\bAnd\b','and',words)
        words=re.sub(r'\s+',' ',words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates=[c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # HTML Schedule of Investments extractor (aligned to WHF/CSWC)
    import requests
    from bs4 import BeautifulSoup

    def normalize_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def normalize_key(text: str) -> str:
        return normalize_text(text).lower()

    def strip_footnote_refs(text: Optional[str]) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        return normalize_text(cleaned)

    def extract_tables_under_heading(soup: BeautifulSoup) -> List[BeautifulSoup]:
        matches: List[BeautifulSoup] = []
        heading_required = ["schedule of investments","schedule of portfolio investments","portfolio of investments"]
        def heading_matches(blob: str) -> bool:
            blob_l = blob
            return any(h in blob_l for h in heading_required)
        # Anchor search first
        anchors = []
        for node in soup.find_all(string=True):
            try:
                txt = normalize_key(node if isinstance(node, str) else node.get_text(" ", strip=True))
            except Exception:
                continue
            if txt and any(h in txt for h in heading_required):
                anchors.append(node)
        if anchors:
            start = anchors[0]
            for t in start.find_all_next("table"):
                matches.append(t)
                if len(matches) >= 25:
                    break
            if matches:
                return matches
        # Fallback proximity search
        for table in soup.find_all("table"):
            context_texts = []
            cur = table
            for _ in range(16):
                prev = cur.find_previous(string=True)
                if not prev:
                    break
                txt = normalize_key(prev if isinstance(prev, str) else prev.get_text(" ", strip=True))
                if txt:
                    context_texts.append(txt)
                cur = prev.parent if hasattr(prev, "parent") else None
                if not cur:
                    break
            if heading_matches(" "+" ".join(context_texts)+" "):
                matches.append(table)
        if matches:
            return matches
        # Final fallback: header-content heuristic (look for expected header labels)
        key_tokens = ["issuer","investment","interest","maturity","principal","amortized","fair value"]
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows: continue
            first_cells = [normalize_key(td.get_text(" ", strip=True)) for td in rows[0].find_all(["td","th"])]
            blob = " ".join(first_cells)
            if sum(1 for k in key_tokens if k in blob) >= 3:
                matches.append(table)
        return matches

    def table_to_rows(table: BeautifulSoup) -> List[List[str]]:
        rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td","th"])
            if not cells:
                continue
            vals: List[str] = []
            for c in cells:
                txt = c.get_text(" ", strip=True).replace("\u200b"," ").replace("\xa0"," ")
                vals.append(normalize_text(txt))
            rows.append(vals)
        return rows

    def parse_section_tables(tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
        records: List[Dict[str, Optional[str]]] = []

        def compact_row(cells: List[str]) -> List[str]:
            filtered = [x for x in cells if x not in ("", "-")]
            merged: List[str] = []
            i=0
            while i < len(filtered):
                cur = filtered[i]
                nxt = filtered[i+1] if i+1 < len(filtered) else None
                if cur == "$" and nxt and re.match(r"^\d[\d,\.]*$", nxt):
                    merged.append(f"${nxt}"); i+=2; continue
                if re.match(r"^\d[\d,\.]*$", cur) and nxt == "%":
                    merged.append(f"{cur}%"); i+=2; continue
                merged.append(cur); i+=1
            return merged

        def merge_symbols_preserve(cells: List[str]) -> List[str]:
            out = list(cells)
            i=0
            while i < len(out)-1:
                cur=out[i]; nxt=out[i+1]
                if cur == "$" and nxt and re.match(r"^\d[\d,\.]*$", nxt):
                    out[i]=f"${nxt}"; out[i+1]=""; i+=2; continue
                if cur and re.match(r"^\d[\d,\.]*$", cur) and nxt == "%":
                    out[i]=f"{cur}%"; out[i+1]=""; i+=2; continue
                i+=1
            return out

        def find_header_map(rows: List[List[str]]) -> Optional[Dict[str,int]]:
            for r in rows[:12]:
                aligned = merge_symbols_preserve(r)
                keys = [normalize_key(c) for c in aligned]
                def find_idx(pats: List[str]) -> Optional[int]:
                    for i,k in enumerate(keys):
                        if not k: continue
                        if any(p in k for p in pats): return i
                    return None
                idx_company = find_idx(["issuer","company","portfolio company"]) 
                idx_investment = find_idx(["investment"]) 
                idx_type = find_idx(["investment type","security type","class"])
                idx_floor = find_idx(["floor"]) 
                idx_ref = find_idx(["reference rate"]) 
                idx_spread = find_idx(["spread above index","spread"]) 
                idx_rate = find_idx(["interest rate"]) 
                idx_acq = find_idx(["acquisition date"]) 
                idx_mat = find_idx(["maturity date"]) 
                idx_prin = find_idx(["principal","share amount","principal/share amount"]) 
                idx_cost = find_idx(["amortized cost","cost"]) 
                idx_fv = find_idx(["fair value"]) 
                idx_pct = find_idx(["percentage of net assets","% of net assets","as a percentage of net assets"]) 
                if idx_company is not None and idx_type is not None and idx_prin is not None and idx_fv is not None:
                    return {"company":idx_company,"investment": -1 if idx_investment is None else idx_investment,
                            "type":idx_type,"floor":-1 if idx_floor is None else idx_floor,
                            "ref":-1 if idx_ref is None else idx_ref,"spread":-1 if idx_spread is None else idx_spread,
                            "rate":-1 if idx_rate is None else idx_rate,"acq":-1 if idx_acq is None else idx_acq,
                            "mat":-1 if idx_mat is None else idx_mat,"prin":idx_prin,"cost":-1 if idx_cost is None else idx_cost,
                            "fv":idx_fv,"pct":-1 if idx_pct is None else idx_pct}
            return None

        def has_percent(tokens: List[str]) -> bool:
            return any(re.search(r"\d(\.\d+)?%$", t) or " % " in f" {t} " or "cash /" in t.lower() or "pik" in t.lower() for t in tokens)
        def has_spread_token(tokens: List[str]) -> bool:
            return any(t.upper().startswith(("SOFR+","PRIME+","LIBOR+","BASE RATE+","SOFR","PRIME","LIBOR","BASE RATE")) for t in tokens)
        def has_date(tokens: List[str]) -> bool:
            return any(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", t) for t in tokens)
        def is_section_header(text: str) -> bool:
            t=text.lower(); return any(k in t for k in ["investments","non-control","non-affiliate"]) 

        for table in tables:
            rows = table_to_rows(table)
            if not rows: continue
            header_map = find_header_map(rows) or {}
            last_company: Optional[str] = None
            last_industry: Optional[str] = None
            for r in rows:
                row_aligned = merge_symbols_preserve(r)
                row = compact_row(row_aligned)
                if not row: continue
                row_l = " ".join(normalize_key(c) for c in row)
                # Skip header rows more aggressively
                if all(token in row_l for token in ["issuer","investment","fair","value"]) and ("acquisition" in row_l or "maturity" in row_l):
                    continue
                if normalize_key(row_l).startswith("company, geographic location"):
                    continue
                
                # Check if first cell is empty (continuation row)
                first_aligned = row_aligned[0].strip() if len(row_aligned) > 0 else ""
                first = row[0] if row else ""
                
                # Skip section headers
                if is_section_header(first): continue
                # Skip percentage-of-total summary rows
                if any('percentage of total investments' in normalize_key(c) for c in row[:4]):
                    continue
                # Skip sector percentage rows like "Professional and Business Services, 36.6%"
                if len(row) >= 2:
                    second_lower = normalize_key(row[1])
                    if re.match(r'^\d{1,3}(?:\.\d+)?%$', second_lower) and not any(re.search(r'(\$|\d{1,3},\d{3})', x) for x in row):
                        continue
                
                # Skip "Total ..." rows (case-insensitive)
                if normalize_key(first).startswith("total ") or any(normalize_key(c).startswith("total ") for c in row[:3]):
                    continue
                # Also skip rows where company name is just "Total"
                if normalize_key(first) == "total":
                    continue
                
                # Skip rows that are just "Company" or header-like
                if normalize_key(first) == "company" or first.lower().startswith("(a) type of investment"):
                    continue
                
                detail = has_percent(row) or has_spread_token(row) or has_date(row) or any(re.search(r"\$\s*[\d,]+", c) for c in row)
                
                # If first cell is empty, this is a continuation row - use last_company
                if not first_aligned or first_aligned.lower().startswith("www."):
                    # This is a continuation row or website-only row
                    if not detail:
                        continue  # Skip website-only or empty continuation rows
                    # Continue with last_company for this detail row
                elif first and not detail:
                    # Non-detail row with content in first cell - could be company name or industry
                    non_empty = [c for c in row[1:] if c and c not in ("$","%")]
                    if not non_empty:
                        last_industry = first.strip(); continue
                    # Check if this looks like a company name (not continuation text)
                    first_lower = normalize_key(first)
                    # Skip continuation text fragments
                    if any(w in first_lower for w in ["activity breaks", "training software", "standards for", "executive search", "controlled expansion", "safety, fluid", "installation company"]):
                        continue
                    # If it's not a website and not clearly continuation text, treat as company name
                    if not first_lower.startswith("www."):
                        # Extract company name (take first line or part before common separators)
                        company_name_raw = first.strip()
                        # Try to extract just the company name part (before location/description)
                        # Pattern: "Company Name (tags) Location. Description"
                        company_match = re.match(r'^([^(]+?)(?:\s*\([^)]+\))?(?:\s+[A-Z][^.]*\.)?', company_name_raw)
                        if company_match:
                            company_name_raw = company_match.group(1).strip()
                        last_company = company_name_raw
                        # Do not set industry from adjacent cells for RAND; leave as-is
                    continue

                # For continuation rows (empty first cell), investment type comes from the row content, not first cell
                inv_type = ""
                interest_rate = next((c for c in row if re.search(r"\d(\.\d+)?%", c)), None)
                spread_val=None; ref_token=None
                for i,c in enumerate(row):
                    cu=c.upper()
                    if any(cu.startswith(tok) for tok in ["SOFR+","PRIME+","LIBOR+","BASE RATE+"]):
                        if i+1 < len(row):
                            nxt=row[i+1]
                            spread_val = nxt if nxt.endswith('%') else (nxt+'%' if re.match(r"^\d+(\.\d+)?$", nxt) else nxt)
                            break
                    m = re.match(r"^(SOFR|SONIA|PRIME|LIBOR|BASE RATE|EURIBOR)(?:\s*\([^)]*\))?$", c, re.IGNORECASE)
                    if m: ref_token=c

                if header_map:
                    def get(idx:int)->Optional[str]: return row_aligned[idx] if 0<=idx<len(row_aligned) else None
                    company_cell=get(header_map.get("company",-1)); it_cell=get(header_map.get("type",-1))
                    inv_cell=get(header_map.get("investment",-1))
                    rate_cell=get(header_map.get("rate",-1)); spread_cell=get(header_map.get("spread",-1))
                    acq_cell=get(header_map.get("acq",-1)); mat_cell=get(header_map.get("mat",-1))
                    prin_cell=get(header_map.get("prin",-1)); cost_cell=get(header_map.get("cost",-1)); fv_cell=get(header_map.get("fv",-1))
                    pct_cell=get(header_map.get("pct",-1)); ref_cell=get(header_map.get("ref",-1))
                    # Update values from mapped columns - investment type comes from investment column, not type column for RAND
                    inv_type = inv_cell or it_cell or inv_type
                    interest_rate = rate_cell or interest_rate
                    spread_val = spread_cell or spread_val
                    ref_token = ref_cell or ref_token
                    acq = acq_cell; mat = mat_cell
                    
                    # Determine company name: if first cell is empty, use last_company (continuation row)
                    # Otherwise, use company_cell if available, or first_aligned, or last_company
                    if not first_aligned:
                        company_for_row = last_company or ""
                    elif company_cell and company_cell.strip():
                        company_raw = company_cell.strip()
                        # Extract industry from parentheses like "(Consumer Goods)" or "(Professional and Business Services)"
                        industry_match = re.search(r'\(([^)]+(?:Goods|Services|Products|Technology|Manufacturing|Distribution|Software|Industry))\)', company_raw, re.IGNORECASE)
                        if industry_match:
                            extracted_industry = industry_match.group(1).strip()
                            if extracted_industry and not any(tok in extracted_industry.lower() for tok in ["preferred", "common", "units", "warrant"]):
                                last_industry = extracted_industry
                        # Extract company name - take part before first "(" or first "." after location indicator
                        if '(' in company_raw:
                            company_for_row = company_raw.split('(')[0].strip()
                        elif '.' in company_raw and len(company_raw.split('.')) > 2:
                            # Likely has location/description, take first part
                            parts = company_raw.split('.')
                            company_for_row = parts[0].strip()
                        else:
                            company_for_row = company_raw
                        # Update last_company if this is a new company row
                        if company_for_row and not company_for_row.lower().startswith("www.") and company_for_row.lower() != "company" and len(company_for_row) > 2:
                            last_company = company_for_row
                    elif first_aligned and not first_aligned.lower().startswith("www."):
                        company_raw = first_aligned.strip()
                        # Extract industry from parentheses
                        industry_match = re.search(r'\(([^)]+(?:Goods|Services|Products|Technology|Manufacturing|Distribution|Software|Industry))\)', company_raw, re.IGNORECASE)
                        if industry_match:
                            extracted_industry = industry_match.group(1).strip()
                            if extracted_industry and not any(tok in extracted_industry.lower() for tok in ["preferred", "common", "units", "warrant"]):
                                last_industry = extracted_industry
                        # Extract company name part
                        if '(' in company_raw:
                            company_for_row = company_raw.split('(')[0].strip()
                        elif '.' in company_raw and len(company_raw.split('.')) > 2:
                            parts = company_raw.split('.')
                            company_for_row = parts[0].strip()
                        else:
                            company_for_row = company_raw
                        if company_for_row and len(company_for_row) > 2:
                            last_company = company_for_row
                    else:
                        company_for_row = last_company or ""
                    
                    # Skip non-detail rows specific to RAND schedule
                    inv_txt_norm = normalize_key(inv_cell or "")
                    if (not inv_cell) or inv_txt_norm.startswith("total ") or inv_txt_norm.startswith("www") or inv_txt_norm in ("—","-"):
                        continue
                    money=[prin_cell,cost_cell,fv_cell]
                    if (not money[0]) or (not mat):
                        inv_txt = inv_cell or ""
                        mpar = re.search(r'\(([A-Z$ ]+)?([\d,]+)\s*par', inv_txt)
                        if mpar and not money[0]:
                            money[0] = mpar.group(2)
                        mmat = re.search(r'\bdue\s+([0-9]{1,2}/[0-9]{4})', inv_txt)
                        if not mmat:
                            mmat = re.search(r'\bdue\s+([0-9]{4})', inv_txt)
                        if mmat and not mat:
                            mat = mmat.group(1)
                else:
                    # No header map - fallback extraction
                    if not first_aligned:
                        company_for_row = last_company or ""
                    elif first_aligned and not first_aligned.lower().startswith("www."):
                        company_raw = first_aligned.strip()
                        if '(' in company_raw:
                            company_for_row = company_raw.split('(')[0].strip()
                        else:
                            company_for_row = company_raw.split('.')[0].strip() if '.' in company_raw else company_raw
                        if company_for_row and len(company_for_row) > 2:
                            last_company = company_for_row
                    else:
                        company_for_row = last_company or ""
                    # Extract investment type from row content
                    if not inv_type:
                        inv_type = row[0] if row and not first_aligned else (row[1] if len(row) > 1 else "")
                    dates=[c for c in row if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", c)]
                    acq = dates[0] if dates else None
                    mat = dates[1] if len(dates)>1 else None
                    money=[c for c in row if c.startswith('$') or re.match(r"^\$?\d[\d,]*$", c)]
                    pct_cell=None

                principal = money[0] if len(money)>=1 else None
                cost = money[1] if len(money)>=2 else None
                fv = money[2] if len(money)>=3 else None
                pct_nav=None
                if pct_cell: pct_nav=pct_cell
                else:
                    perc=[c for c in row if c.endswith('%')]
                    if perc:
                        pct_nav=perc[-1]

                def parse_num(x: Optional[str]) -> Optional[float]:
                    if not x: return None
                    t=x.replace(',','').replace('$','').strip()
                    if t in ('—','—%','— $'): return None
                    if t.endswith('%'):
                        try: return float(t[:-1])
                        except: return None
                    try: return float(t)
                    except: return None

                company_clean = strip_footnote_refs(company_for_row or last_company or "")
                inv_type_clean = strip_footnote_refs(inv_type)
                industry_clean = strip_footnote_refs(last_industry or "")
                
                # Clean industry: extract from parentheses and remove continuation text prefixes
                if industry_clean:
                    # Remove continuation text prefixes like "and software. (Manufacturing)" -> "(Manufacturing)"
                    industry_clean = re.sub(r'^[^)]*\s*\(', '(', industry_clean)
                    # Extract just the industry from parentheses if it exists
                    ind_match = re.search(r'\(([^)]+(?:Goods|Services|Products|Technology|Manufacturing|Distribution|Software|Industry))\)', industry_clean, re.IGNORECASE)
                    if ind_match:
                        industry_clean = ind_match.group(1).strip()
                    # Remove any remaining parentheses
                    industry_clean = industry_clean.strip('()')
                
                # Clear industry if it looks like a security descriptor rather than an industry
                ind_low = (industry_clean or '').lower()
                if (any(tok in ind_low for tok in ["preferred", "common", "units", "warrant", "shares", "class", "%"])) or ('www.' in ind_low) or (len(industry_clean.split())>6):
                    industry_clean = ""
                
                # Skip rows that are clearly invalid
                low_first = (company_clean or '').lower()
                low_inv = (inv_type_clean or '').lower()
                
                # Skip continuation text fragments (more comprehensive list)
                continuation_keywords = [
                    "activity breaks", "training software", "standards for", "executive search", 
                    "controlled expansion", "safety, fluid", "installation company", "fishing and pleasure",
                    "products.", "applications.", "training.", "industry.", "markets.",
                    "tire pressure", "monitoring systems", "consisting", "commercial kitchen", "renovations"
                ]
                if any(frag in low_first for frag in continuation_keywords) or (low_first.endswith(".") and len(low_first.split()) <= 4 and not any(c.isupper() for c in low_first[:10])):
                    continue
                
                # Also check industry column for continuation text
                low_industry = (industry_clean or '').lower()
                if any(frag in low_industry for frag in continuation_keywords) or (low_industry.endswith(".") and len(low_industry.split()) <= 4 and "preferred" not in low_industry and "common" not in low_industry):
                    # Clear invalid industry rather than skipping the whole row
                    industry_clean = ""
                
                # Skip financial statement rows (not schedule of investments)
                financial_terms = [
                    "interest receivable", "due to investment", "common stock", "stockholders", 
                    "net,$", "net,", "basic and diluted", "cash flows", "end of period", "liabilities",
                    "receivable", "payable", "equity", "shares authorized", "shares issued", "shares outstanding",
                    "ending balance", "prepaid expenses", "repayments and sales"
                ]
                # Check if company name is just "Net" or starts with "Net" followed by comma/dollar
                if low_first == "net" or low_first.startswith("net,") or any(term in low_first for term in financial_terms):
                    continue
                
                # Skip numbered rows like "1 st", "2 nd", etc.
                if re.match(r'^\d+\s*(st|nd|rd|th)$', low_first):
                    continue
                
                # Skip continuation text fragments that leaked through
                if any(frag in low_first for frag in ["commercial kitchen", "renovations and new", "builds.", "installation company"]):
                    continue
                
                # Skip footer rows
                if "other assets" in low_first or "net assets" in low_first or "other assets" in low_inv or "net assets" in low_inv:
                    continue
                
                # Skip header-like and subtotal rows
                if not (parse_num(principal) or parse_num(cost) or parse_num(fv)):
                    if low_first.startswith('company') or low_first.startswith('total ') or low_first == '':
                        continue
                
                # Skip rows without a valid company name
                if not company_clean or company_clean.lower().startswith('www.') or len(company_clean) < 3:
                    continue
                records.append({
                    'company_name': company_clean,
                    'investment_type': inv_type_clean,
                    'industry': industry_clean,
                    'interest_rate': interest_rate,
                    'reference_rate': ref_token,
                    'spread': spread_val,
                    'acquisition_date': acq,
                    'maturity_date': mat,
                    'principal_amount': parse_num(principal),
                    'amortized_cost': parse_num(cost),
                    'fair_value': parse_num(fv),
                    'percent_of_net_assets': parse_num(pct_nav),
                })
        return records

    client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
    index_url = client.get_filing_index_url("RAND", "10-Q")
    if not index_url:
        print("Could not find latest 10-Q for RAND"); return
    docs = client.get_documents_from_index(index_url)
    main_html = next((d for d in docs if d.filename.lower().endswith('.htm')), None)
    if not main_html:
        print("No main HTML document found for RAND"); return
    resp = requests.get(main_html.url, headers=client.headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    tables = extract_tables_under_heading(soup)
    records = parse_section_tables(tables)
    
    # Normalize company names for better deduplication (extract base name)
    def normalize_company_name(name: str) -> str:
        if not name:
            return ""
        name_lower = name.lower().strip()
        # Handle d/b/a cases: "Filterworks Acquisition USA, LLC d/b/a Autotality" -> "autotality"
        dba_match = re.search(r'\bd/b/a\s+([^,]+)', name_lower)
        if dba_match:
            return dba_match.group(1).strip()
        # Extract last significant word/phrase before LLC/Inc/Corp
        match = re.search(r'([a-z\s]+?)\s*(?:llc|inc|corp|llp|ltd|holdco|holdings)', name_lower)
        if match:
            base = match.group(1).strip()
            # If base is too short or generic, use full name
            if len(base) > 3 and base not in ['the', 'and', 'for']:
                return base
        return name_lower
    
    # Deduplicate records with smarter matching
    # Group by normalized company + investment type, then keep best record per group
    groups = {}
    for rec in records:
        company_raw = (rec.get('company_name') or '').strip()
        company_norm = normalize_company_name(company_raw)
        inv_type = (rec.get('investment_type') or '').lower().strip()
        
        # Normalize investment type for matching (remove minor variations)
        # Extract principal amount from investment type for comparison
        inv_normalized = re.sub(r'\d{1,2}\s*%\s*(?:\+\s*\d+%\s*PIK)?', '', inv_type).strip()
        inv_normalized = re.sub(r'due\s+[^.]*\.', '', inv_normalized).strip()
        inv_normalized = re.sub(r'through\s+[^,]*,', '', inv_normalized).strip()
        
        group_key = (company_norm, inv_normalized)
        
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(rec)
    
    # For each group, keep the best record (prefer one with fair_value and higher value)
    deduplicated = []
    for group_key, group_recs in groups.items():
        if len(group_recs) == 1:
            deduplicated.append(group_recs[0])
        else:
            # Find the best record - prefer one with fair_value, and highest value
            best = None
            best_score = -1
            for rec in group_recs:
                fv = rec.get('fair_value') or 0
                cost = rec.get('amortized_cost') or 0
                # Score: fair_value presence (+1000), then value amount
                score = (1000 if fv else 0) + fv + (cost * 0.5)
                if score > best_score:
                    best_score = score
                    best = rec
            if best:
                deduplicated.append(best)
    
    records = deduplicated

    out_dir = os.path.join(os.path.dirname(__file__), 'output')
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, 'RAND_Schedule_Continued_latest.csv')
    fieldnames = ['company_name','investment_type','industry','interest_rate','reference_rate','spread','acquisition_date','maturity_date','principal_amount','amortized_cost','fair_value','percent_of_net_assets']
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            # Apply standardization
            if 'investment_type' in rec:
                rec['investment_type'] = standardize_investment_type(rec.get('investment_type'))
            if 'industry' in rec:
                rec['industry'] = standardize_industry(rec.get('industry'))
            if 'reference_rate' in rec:
                rec['reference_rate'] = standardize_reference_rate(rec.get('reference_rate')) or ''
            
            writer.writerow(rec)
    print(f"Saved {len(records)} rows to {out_csv} (deduplicated from {len(parse_section_tables(tables))})")

    # QA simplified tables
    tables_dir = os.path.join(out_dir, 'rand_tables')
    os.makedirs(tables_dir, exist_ok=True)
    for i,t in enumerate(tables,1):
        simple = BeautifulSoup(str(t), 'html.parser').find('table')
        if simple:
            for ix in simple.find_all(lambda el: isinstance(el.name,str) and el.name.lower().startswith('ix:')):
                ix.replace_with(ix.get_text(' ', strip=True))
            def strip_attrs(el):
                if hasattr(el,'attrs'): el.attrs={}
                for child in getattr(el,'children',[]): strip_attrs(child)
            strip_attrs(simple)
            with open(os.path.join(tables_dir, f'rand_table_{i}.html'), 'w', encoding='utf-8') as fh:
                fh.write(str(simple))
    print(f"Saved {len(tables)} simplified tables to {tables_dir}")

if __name__=='__main__':
    main()

#!/usr/bin/env python3
import re, os, csv, logging, requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class RANDInvestment:
    company_name: str
    business_description: Optional[str] = None
    investment_type: str = "Unknown"
    industry: str = "Unknown"
    acquisition_date: Optional[str] = None
    maturity_date: Optional[str] = None
    principal_amount: Optional[float] = None
    cost: Optional[float] = None
    fair_value: Optional[float] = None
    interest_rate: Optional[str] = None
    reference_rate: Optional[str] = None
    spread: Optional[str] = None
    floor_rate: Optional[str] = None
    pik_rate: Optional[str] = None
    context_ref: Optional[str] = None
    shares_units: Optional[str] = None
    percent_net_assets: Optional[str] = None
    currency: Optional[str] = None
    commitment_limit: Optional[float] = None
    undrawn_commitment: Optional[float] = None


class RANDExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "RAND") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        return self.extract_from_url(txt_url, "Rand_Capital_Corp", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        r = requests.get(filing_url, headers=self.headers)
        r.raise_for_status()
        content = r.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
            logger.info(f"Filtered contexts to instant {sel}: {len(contexts)} remaining")

        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]

        facts_by_context = self._extract_facts(content)
        invs: List[RANDInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                invs.append(inv)

        # de-dup
        ded, seen = [], set()
        for inv in invs:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen: continue
            seen.add(combo); ded.append(inv)
        invs = ded

        total_principal = sum(x.principal_amount or 0 for x in invs)
        total_cost = sum(x.cost or 0 for x in invs)
        total_fair_value = sum(x.fair_value or 0 for x in invs)
        ind = defaultdict(int); ty = defaultdict(int)
        for x in invs:
            ind[x.industry] += 1; ty[x.investment_type] += 1

        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'RAND_Rand_Capital_Corp_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['company_name','industry','business_description','investment_type','acquisition_date','maturity_date','principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'])
            w.writeheader()
            for x in invs:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(x.investment_type)
                standardized_industry = standardize_industry(x.industry)
                standardized_ref_rate = standardize_reference_rate(x.reference_rate)
                
                w.writerow({'company_name':x.company_name,'industry':standardized_industry,'business_description':x.business_description,'investment_type':standardized_inv_type,'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardized_ref_rate,'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate})
        logger.info(f"Saved to {out_file}")
        inv_dicts = [{'company_name':x.company_name,'industry':standardize_industry(x.industry),'business_description':x.business_description,'investment_type':standardize_investment_type(x.investment_type),'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardize_reference_rate(x.reference_rate),'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate} for x in invs]
        return {'company_name':company_name,'cik':cik,'total_investments':len(invs),'investments':inv_dicts,'total_principal':total_principal,'total_cost':total_cost,'total_fair_value':total_fair_value,'industry_breakdown':dict(ind),'investment_type_breakdown':dict(ty)}

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        res = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1); html = m.group(2)
            tm = tp.search(html)
            if not tm: continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', html)
            sd = re.search(r'<startDate>([^<]+)</startDate>', html)
            ed = re.search(r'<endDate>([^<]+)</endDate>', html)
            same = None
            em = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', html, re.DOTALL|re.IGNORECASE)
            if em: same = self._industry_member_to_name(em.group(1).strip())
            res.append({'id':cid,'investment_identifier':ident,'company_name':parsed['company_name'],'industry':same or parsed['industry'],'investment_type':parsed['investment_type'],'instant':inst.group(1) if inst else None,'start_date':sd.group(1) if sd else None,'end_date':ed.group(1) if ed else None})
        return res

    def _parse_identifier(self, identifier: str) -> Dict[str,str]:
        res={'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        if ',' in identifier:
            last = identifier.rfind(','); company = identifier[:last].strip(); tail = identifier[last+1:].strip()
        else:
            company = identifier.strip(); tail = ''
        res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
        pats=[r'First\s+lien\s+.*$',r'Second\s+lien\s+.*$',r'Unitranche\s*\d*$',r'Senior\s+secured\s*\d*$',r'Secured\s+Debt\s*\d*$',r'Unsecured\s+Debt\s*\d*$',r'Preferred\s+Equity$',r'Preferred\s+Stock$',r'Common\s+Stock\s*\d*$',r'Member\s+Units\s*\d*$',r'Warrants?$']
        it=None
        for p in pats:
            mm=re.search(p, tail, re.IGNORECASE)
            if mm: it=mm.group(0); break
        if not it and tail: it=tail
        if it: res['investment_type']=it
        return res

    def _extract_facts(self, content: str) -> Dict[str,List[Dict]]:
        facts=defaultdict(list)
        # Extract standard XBRL facts and capture unitRef for currency
        sp=re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept=match.group(1); cref=match.group(2); unit_ref=match.group(3); val=match.group(4)
            if val and cref:
                fact_entry={'concept':concept,'value':val.strip()}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match=re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match: fact_entry['currency']=currency_match.group(1)
                facts[cref].append(fact_entry)
        ixp=re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:unitRef="([^"]*)")?[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name=m.group(1); cref=m.group(2); unit_ref=m.group(3); html=m.group(5)
            if not cref: continue
            txt=re.sub(r'<[^>]+>','',html).strip()
            if txt:
                fact_entry={'concept':name,'value':txt}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match=re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match: fact_entry['currency']=currency_match.group(1)
                facts[cref].append(fact_entry)
            start=max(0,m.start()-3000); end=min(len(content), m.end()+3000); window=content[start:end]
            ref=re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref: facts[cref].append({'concept':'derived:ReferenceRateToken','value':ref.group(1).replace('+','').upper()})
            floor=re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor: facts[cref].append({'concept':'derived:FloorRate','value':floor.group(1)})
            pik=re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik: facts[cref].append({'concept':'derived:PIKRate','value':pik.group(1)})
            dates=re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value':dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value':dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value':dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[RANDInvestment]:
        if context['company_name']=='Unknown': return None
        inv=RANDInvestment(company_name=context['company_name'],investment_type=context['investment_type'],industry=context['industry'],context_ref=context['id'])
        for f in facts:
            c=f['concept']; v=f['value']; v=v.replace(',',''); cl=c.lower()
            if any(k in cl for k in ['principalamount','ownedbalanceprincipalamount','outstandingprincipal']):
                try: inv.principal_amount=float(v)
                except: pass; continue
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: inv.cost=float(v)
                except: pass; continue
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: inv.fair_value=float(v)
                except: pass; continue
                continue
            if 'investmentbasisspreadvariablerate' in cl:
                inv.spread=self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate=self._percent(v); continue
            if cl=='derived:referenceratetoken': inv.reference_rate=v.upper(); continue
            if cl=='derived:floorrate': inv.floor_rate=self._percent(v); continue
            if cl=='derived:pikrate': inv.pik_rate=self._percent(v); continue
            if cl=='derived:acquisitiondate': inv.acquisition_date=v; continue
            if cl=='derived:maturitydate': inv.maturity_date=v; continue
        if not inv.acquisition_date and context.get('start_date'): inv.acquisition_date=context['start_date'][:10]
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value): return inv
        return None

    def _percent(self, s: str) -> str:
        try: v=float(s)
        except: return f"{s}%"
        if 0<abs(v)<=1.0: v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={}; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        ep=re.compile(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', re.DOTALL|re.IGNORECASE)
        for mm in cp.finditer(content):
            html=mm.group(2)
            inst=re.search(r'<instant>([^<]+)</instant>', html)
            inst=inst.group(1) if inst else None
            if not inst: continue
            em=ep.search(html)
            if not em: continue
            m[inst]=self._industry_member_to_name(em.group(1).strip())
        return m

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local=qname.split(':',1)[-1] if ':' in qname else qname
        local=re.sub(r'Member$','',local)
        if local.endswith('Sector'): local=local[:-6]
        words=re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words=re.sub(r'\bAnd\b','and',words)
        words=re.sub(r'\s+',' ',words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates=[c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=RANDExtractor()
    try:
        res=ex.extract_from_ticker('RAND')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()
