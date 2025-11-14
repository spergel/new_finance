#!/usr/bin/env python3
"""
WHF (WhiteHorse Finance Inc) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filter; de-dup; industry enrichment.
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
class WHFInvestment:
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


class WHFExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "WHF") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        acc = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not acc:
            raise ValueError("Could not parse accession number")
        accession = acc.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "WhiteHorse_Finance_Inc", cik)

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
        investments: List[WHFInvestment] = []
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
        out_file = os.path.join(out_dir, 'WHF_WhiteHorse_Finance_Inc_investments.csv')
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
        # Convert to dict format
        investment_dicts = []
        for inv in investments:
            investment_dicts.append({
                'company_name': inv.company_name,
                'industry': inv.industry,
                'business_description': inv.business_description,
                'investment_type': inv.investment_type,
                'acquisition_date': inv.acquisition_date,
                'maturity_date': inv.maturity_date,
                'principal_amount': inv.principal_amount,
                'cost': inv.cost,
                'fair_value': inv.fair_value,
                'interest_rate': inv.interest_rate,
                'reference_rate': inv.reference_rate,
                'spread': inv.spread,
                'floor_rate': inv.floor_rate,
                'pik_rate': inv.pik_rate,
                'shares_units': inv.shares_units,
                'percent_net_assets': inv.percent_net_assets,
                'currency': inv.currency,
                'commitment_limit': inv.commitment_limit,
                'undrawn_commitment': inv.undrawn_commitment,
            })
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'investments': investment_dicts,
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
        
        # Investment type patterns - more comprehensive and ordered from specific to general
        type_patterns = [
            r'First\s+Lien\s+Secured\s+Delayed\s+Draw\s+Loan',
            r'First\s+Lien\s+Secured\s+Revolving\s+Loan',
            r'First\s+Lien\s+Secured\s+Term\s+Loan',
            r'First\s+Lien\s+Secured\s+.*',
            r'First\s+lien\s+.*',
            r'Second\s+Lien\s+Secured\s+Term\s+Loan',
            r'Second\s+Lien\s+Secured\s+.*',
            r'Second\s+lien\s+.*',
            r'Unitranche\s*\d*',
            r'Senior\s+secured\s+\d*',
            r'Secured\s+Debt\s*\d*',
            r'Unsecured\s+Debt\s*\d*',
            r'Preferred\s+Equity',
            r'Preferred\s+Stock',
            r'Common\s+Stock\s*\d*',
            r'Member\s+Units\s*\d*',
            r'Equity',
            r'Interests',
            r'Warrants?',
        ]
        
        # First, try to find investment type in the full identifier
        it = None
        it_match = None
        for p in type_patterns:
            mm = re.search(p, identifier, re.IGNORECASE)
            if mm:
                it = mm.group(0).strip()
                it_match = mm
                break
        
        # If found, extract company name by removing the investment type
        if it and it_match:
            # Remove investment type from identifier to get company name
            company = identifier[:it_match.start()].strip()
            # Also check if there's a comma - if so, use part before comma
            if ',' in company:
                last_comma = company.rfind(',')
                company = company[:last_comma].strip()
            res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',').strip()
            res['investment_type'] = it
        else:
            # Fallback: try comma-separated format
            if ',' in identifier:
                last = identifier.rfind(',')
                company = identifier[:last].strip()
                tail = identifier[last+1:].strip()
            else:
                company = identifier.strip()
                tail = ''
            
            # Try patterns on tail
            if tail:
                for p in type_patterns:
                    mm = re.search(p, tail, re.IGNORECASE)
                    if mm:
                        it = mm.group(0)
                        break
                if not it:
                    it = tail
            
            res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',').strip()
            if it:
                res['investment_type'] = it
        
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        # Extract standard XBRL facts and capture unitRef for currency
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept = match.group(1)
            cref = match.group(2)
            unit_ref = match.group(3)
            val = match.group(4)
            if val and cref:
                fact_entry = {'concept': concept, 'value': val.strip()}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match:
                        fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:unitRef="([^"]*)")?[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1); cref = m.group(2); unit_ref = m.group(3); html = m.group(5)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                fact_entry = {'concept': name, 'value': txt}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match:
                        fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
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
                seen = set()
                unique_dates = []
                for d in dates:
                    if d not in seen:
                        seen.add(d)
                        unique_dates.append(d)
                if len(unique_dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[-1]})
                elif len(unique_dates)==1:
                    date_idx = window.find(unique_dates[0])
                    date_context = window[max(0, date_idx-50):min(len(window), date_idx+50)]
                    if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', date_context, re.IGNORECASE):
                        facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    else:
                        facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[WHFInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = WHFInvestment(
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
            if 'currency' in f:
                inv.currency = f.get('currency')
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        # Heuristic for commitment_limit and undrawn_commitment
        if inv.fair_value and not inv.principal_amount:
            inv.commitment_limit = inv.fair_value
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
    # Integrated HTML Schedule of Investments extractor (based on workflow)
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

        def contains_date_like(blob: str) -> bool:
            return re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", blob, re.IGNORECASE) is not None

        required_any = [
            "consolidated schedule of investments",
            "continued",
            "unaudited",
            "dollar amounts in thousands",
        ]

        def heading_matches(blob: str) -> bool:
            blob_l = blob
            if "consolidated schedule of investments" not in blob_l:
                return False
            if not contains_date_like(blob_l):
                count = sum(1 for t in required_any if t in blob_l)
                if count < 3:
                    return False
            return True

        for table in soup.find_all("table"):
            context_texts = []
            cur = table
            for _ in range(12):
                prev = cur.find_previous(string=True)
                if not prev:
                    break
                txt = normalize_key(prev if isinstance(prev, str) else prev.get_text(" ", strip=True))
                if txt:
                    context_texts.append(txt)
                cur = prev.parent if hasattr(prev, "parent") else None
                if not cur:
                    break
            context_blob = " ".join(context_texts)
            if heading_matches(context_blob):
                matches.append(table)
        return matches

    def table_to_rows(table: BeautifulSoup) -> List[List[str]]:
        rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            vals: List[str] = []
            for c in cells:
                # Retain basic symbols like $ and % but normalize whitespace
                txt = c.get_text(" ", strip=True)
                # Remove zero-width and NBSP
                txt = txt.replace("\u200b", "").replace("\xa0", " ")
                vals.append(normalize_text(txt))
            rows.append(vals)
        return rows

    def parse_section_tables(tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
        records: List[Dict[str, Optional[str]]] = []

        def compact_row(cells: List[str]) -> List[str]:
            # Remove spacer/blank cells and merge tokens like "$" + number, number + "%"
            filtered = [x for x in cells if x not in ("", "-")]
            merged: List[str] = []
            i = 0
            while i < len(filtered):
                cur = filtered[i]
                nxt = filtered[i+1] if i+1 < len(filtered) else None
                if cur == "$" and nxt and re.match(r"^\d[\d,\.]*$", nxt):
                    merged.append(f"${nxt}")
                    i += 2
                    continue
                if re.match(r"^\d[\d,\.]*$", cur) and nxt == "%":
                    merged.append(f"{cur}%")
                    i += 2
                    continue
                merged.append(cur)
                i += 1
            return merged

        def find_header_map(rows: List[List[str]]) -> Optional[Dict[str,int]]:
            for r in rows[:12]:
                header_cells = compact_row(r)
                keys = [normalize_key(c) for c in header_cells]
                def find_idx(patterns: List[str]) -> Optional[int]:
                    for i,k in enumerate(keys):
                        if any(p in k for p in patterns):
                            return i
                    return None
                idx_company = find_idx(["issuer","company","portfolio company"]) 
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
                    return {
                        "company": idx_company,
                        "type": idx_type,
                        "floor": -1 if idx_floor is None else idx_floor,
                        "ref": -1 if idx_ref is None else idx_ref,
                        "spread": -1 if idx_spread is None else idx_spread,
                        "rate": -1 if idx_rate is None else idx_rate,
                        "acq": -1 if idx_acq is None else idx_acq,
                        "mat": -1 if idx_mat is None else idx_mat,
                        "prin": idx_prin,
                        "cost": -1 if idx_cost is None else idx_cost,
                        "fv": idx_fv,
                        "pct": -1 if idx_pct is None else idx_pct,
                    }
            return None

        def has_percent(tokens: List[str]) -> bool:
            return any(re.search(r"\d(\.\d+)?%$", t) or " % " in f" {t} " or "cash /" in t.lower() or "pik" in t.lower() for t in tokens)

        def has_spread_token(tokens: List[str]) -> bool:
            return any(t.upper().startswith(("SOFR+", "PRIME+", "LIBOR+", "BASE RATE+", "SOFR", "PRIME", "LIBOR", "BASE RATE")) for t in tokens)

        def has_date(tokens: List[str]) -> bool:
            return any(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", t) for t in tokens)

        def is_section_header(text: str) -> bool:
            t = text.lower()
            return any(k in t for k in ["investments", "debt and equity", "non-control", "non-affiliate"])

        for table in tables:
            rows = table_to_rows(table)
            if not rows:
                continue
            header_map = find_header_map(rows) or {}
            last_company: Optional[str] = None
            last_industry: Optional[str] = None
            for r in rows:
                # Compact the row the same way we compact the header
                row = compact_row(r)
                if not row:
                    continue
                first = row[0]
                if is_section_header(first):
                    continue

                detail_signals = has_percent(row) or has_spread_token(row) or has_date(row)
                if first and not detail_signals:
                    # If the row looks like an industry header (only first cell meaningful), set industry
                    non_empty_others = [c for c in row[1:] if c and c not in ("$", "%")]
                    if not non_empty_others:
                        last_industry = first.strip()
                    else:
                        last_company = first.strip()
                        cand_ind = None
                        for cell in row[1:]:
                            if cell and not has_percent([cell]) and not has_date([cell]) and not has_spread_token([cell]):
                                cand_ind = cell.strip()
                                break
                        if cand_ind:
                            last_industry = cand_ind
                    continue
                # Map columns if header detected; otherwise fallback heuristics
                inv_type = first.strip()
                interest_rate = next((c for c in row if re.search(r"\d(\.\d+)?%", c)), None)
                spread_val = None
                for i, c in enumerate(row):
                    cu = c.upper()
                    if any(cu.startswith(tok) for tok in ["SOFR+", "PRIME+", "LIBOR+", "BASE RATE+"]):
                        if i + 1 < len(row):
                            nxt = row[i + 1]
                            spread_val = nxt if nxt.endswith("%") else (nxt + "%" if re.match(r"^\d+(\.\d+)?$", nxt) else nxt)
                            break
                # Reference rate token present as e.g., "SOFR (3M)"
                ref_token = None
                if header_map:
                    def get(idx: int) -> Optional[str]:
                        return row[idx] if 0 <= idx < len(row) else None
                    company_cell = get(header_map.get("company", -1))
                    it_cell = get(header_map.get("type", -1))
                    ref_cell = get(header_map.get("ref", -1))
                    rate_cell = get(header_map.get("rate", -1))
                    spread_cell = get(header_map.get("spread", -1))
                    acq_cell = get(header_map.get("acq", -1))
                    mat_cell = get(header_map.get("mat", -1))
                    prin_cell = get(header_map.get("prin", -1))
                    cost_cell = get(header_map.get("cost", -1))
                    fv_cell = get(header_map.get("fv", -1))
                    pct_cell = get(header_map.get("pct", -1))
                    # prefer mapped values
                    inv_type = it_cell or inv_type
                    interest_rate = rate_cell or interest_rate
                    spread_val = spread_cell or spread_val
                    ref_token = ref_cell
                    acq = acq_cell
                    mat = mat_cell
                    company_for_row = company_cell or last_company or ""
                    money = [prin_cell, cost_cell, fv_cell]
                else:
                    company_for_row = last_company or ""
                    dates = [c for c in row if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", c)]
                    acq = dates[0] if dates else None
                    mat = dates[1] if len(dates) > 1 else None
                    money = [c for c in row if c.startswith("$") or re.match(r"^\$?\d[\d,]*$", c)]
                    pct_cell = None
                    # scan for reference rate token
                    for tok in row:
                        m = re.match(r"^(SOFR|SONIA|PRIME|LIBOR|BASE RATE|EURIBOR)(?:\s*\([^)]*\))?$", tok, re.IGNORECASE)
                        if m:
                            ref_token = tok
                            break

                principal = money[0] if len(money) >= 1 else None
                cost = money[1] if len(money) >= 2 else None
                fair_value = money[2] if len(money) >= 3 else None
                pct_nav = None
                if pct_cell:
                    pct_nav = pct_cell
                else:
                    percent_tokens = [c for c in row if c.endswith("%")]
                    if percent_tokens:
                        pct_nav = percent_tokens[-1]

                def parse_number_local(text: Optional[str]) -> Optional[float]:
                    if not text:
                        return None
                    t = text.replace("\xa0", " ").replace(",", "").strip()
                    t = t.replace("$", "")
                    if t in ("—", "—%", "— $"):
                        return None
                    if t.endswith("%"):
                        try:
                            return float(t[:-1])
                        except:
                            return None
                    try:
                        return float(t)
                    except:
                        return None

                company_clean = strip_footnote_refs(company_for_row or last_company or "")
                inv_type_clean = strip_footnote_refs(inv_type)
                # Apply standardization to investment type
                if inv_type_clean:
                    inv_type_clean = standardize_investment_type(inv_type_clean)
                industry_clean = strip_footnote_refs(last_industry or "")
                records.append({
                    "company_name": company_clean,
                    "investment_type": inv_type_clean,
                    "industry": industry_clean,
                    "interest_rate": interest_rate,
                    "reference_rate": ref_token,
                    "spread": spread_val,
                    "acquisition_date": acq,
                    "maturity_date": mat,
                    "principal_amount": parse_number_local(principal),
                    "amortized_cost": parse_number_local(cost),
                    "fair_value": parse_number_local(fair_value),
                    "percent_of_net_assets": parse_number_local(pct_nav),
                })
        return records

    client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
    index_url = client.get_filing_index_url("WHF", "10-Q")
    if not index_url:
        print("Could not find latest 10-Q for WHF")
        return
    docs = client.get_documents_from_index(index_url)
    main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
    if not main_html:
        print("No main HTML document found for WHF")
        return
    resp = requests.get(main_html.url, headers=client.headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tables = extract_tables_under_heading(soup)
    records = parse_section_tables(tables)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, "WHF_Schedule_Continued_latest.csv")
    fieldnames = [
        "company_name",
        "investment_type",
        "industry",
        "interest_rate",
        "reference_rate",
        "spread",
        "acquisition_date",
        "maturity_date",
        "principal_amount",
        "amortized_cost",
        "fair_value",
        "percent_of_net_assets",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
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
    print(f"Saved {len(records)} rows to {out_csv}")

    # Save simplified tables for QA
    tables_dir = os.path.join(out_dir, "whf_tables")
    os.makedirs(tables_dir, exist_ok=True)
    for i, t in enumerate(tables, 1):
        simple = BeautifulSoup(str(t), "html.parser").find("table")
        if simple:
            for ix in simple.find_all(lambda el: isinstance(el.name, str) and el.name.lower().startswith("ix:")):
                ix.replace_with(ix.get_text(" ", strip=True))
            def strip_attrs(el):
                if hasattr(el, "attrs"):
                    el.attrs = {}
                for child in getattr(el, "children", []):
                    strip_attrs(child)
            strip_attrs(simple)
            with open(os.path.join(tables_dir, f"whf_table_{i}.html"), "w", encoding="utf-8") as fh:
                fh.write(str(simple))
    print(f"Saved {len(tables)} simplified tables to {tables_dir}")

if __name__=='__main__':
    main()
