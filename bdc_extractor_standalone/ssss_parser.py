#!/usr/bin/env python3
"""
SSSS (SuRo Capital Corp) Investment Extractor
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
# from flexible_table_parser import FlexibleTableParser  # Removed - module doesn't exist
from bs4 import BeautifulSoup
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate
logger = logging.getLogger(__name__)

@dataclass
class SSSSInvestment:
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


class SSSSExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.table_parser = FlexibleTableParser()

    def extract_from_ticker(self, ticker: str = "SSSS") -> Dict:
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
        return self.extract_from_url(txt_url, "SuRo_Capital_Corp", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        resp = requests.get(filing_url, headers=self.headers)
        resp.raise_for_status()
        content = resp.text
        contexts = self._extract_typed_contexts(content)
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]
        facts_by_context = self._extract_facts(content)
        investments: List[SSSSInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)
        # If XBRL yielded nothing, fallback to HTML table parsing
        if not investments:
            # Derive filing index URL from the XBRL txt URL
            m = re.search(r'/Archives/edgar/data/\d+/([0-9\-]+)/\1\.txt$', filing_url)
            index_url = None
            if m:
                acc = m.group(1)
                index_url = filing_url.replace(f"/{acc}.txt", f"/{acc}-index.html")
            else:
                # As a fallback, try to transform to index.html
                index_url = re.sub(r'\.txt$', '-index.html', filing_url)
            docs = self.sec_client.get_documents_from_index(index_url)
            main_doc = None
            for d in docs:
                fn = d.filename.lower()
                if fn.endswith('.htm') and 'index' not in fn:
                    main_doc = d; break
            if main_doc:
                parsed = self.table_parser.parse_html_filing(main_doc.url)
                for it in parsed:
                    investments.append(SSSSInvestment(
                        company_name=it.get('company_name') or it.get('company') or '',
                        business_description=it.get('business_description'),
                        investment_type=it.get('investment_type') or it.get('type') or 'Unknown',
                        industry=it.get('industry') or 'Unknown',
                        acquisition_date=it.get('acquisition_date'),
                        maturity_date=it.get('maturity_date'),
                        principal_amount=it.get('principal_amount') or it.get('principal'),
                        cost=it.get('cost') or it.get('amortized_cost'),
                        fair_value=it.get('fair_value'),
                        interest_rate=it.get('interest_rate'),
                        reference_rate=it.get('reference_rate'),
                        spread=it.get('spread'),
                        floor_rate=it.get('floor_rate'),
                        pik_rate=it.get('pik_rate')
                    ))
                # If still empty, do a targeted HTML schedule scrape using inline IX tags pattern
                if not investments:
                    try:
                        html = requests.get(main_doc.url, headers=self.headers).text
                        soup = BeautifulSoup(html, 'html.parser')
                        # Limit to the Schedule of Investments table(s)
                        tables = [t for t in soup.find_all('table') if 'summary' in t.attrs and 'Schedule of Investments' in t.get('summary','')]
                        if not tables:
                            tables = soup.find_all('table')
                        def parse_money(s: str) -> Optional[float]:
                            if not s: return None
                            s = s.replace('\u00a0',' ').replace(',', '').replace('$','').strip()
                            try:
                                # handle dashes or empty
                                if s in ('—','-','–',''):
                                    return None
                                return float(s)
                            except:
                                return None
                        def looks_money(s: str) -> bool:
                            return bool(re.search(r'\$?\s*-?[\d,]+(\.\d+)?', s)) and parse_money(s) is not None
                        def parse_percent(s: str) -> Optional[str]:
                            s = (s or '').strip()
                            if not s or s in ('—','-','–'): return None
                            if not s.endswith('%'):
                                # try numeric
                                try:
                                    v = float(s)
                                    if 0 < abs(v) <= 1.0:
                                        v *= 100.0
                                    s = f"{v:.2f}%"
                                except:
                                    return None
                            return s
                        def parse_date_cell(s: str) -> Optional[str]:
                            s = (s or '').strip()
                            m = re.search(r'\b\d{1,2}/\d{1,2}/\d{4}\b', s)
                            return m.group(0) if m else None
                        # Target rows with colored background that carry the ix facts; capture company from previous bold row
                        for tbl in tables:
                            def find_ix(row, concept_regex: str, prefer_fraction: Optional[bool]=None):
                                pat = re.compile(concept_regex, re.I)
                                found_elem = None
                                for elem in row.descendants:
                                    if not hasattr(elem, 'name') or not elem.name:
                                        continue
                                    name_l = elem.name.lower()
                                    # Match both 'ix:nonFraction' and 'nonFraction' variants
                                    is_nonfraction = name_l.endswith('nonfraction')
                                    is_nonnumeric = name_l.endswith('nonnumeric')
                                    if not (is_nonfraction or is_nonnumeric):
                                        continue
                                    # attribute 'name' holds concept qname
                                    qn = elem.get('name') or ''
                                    if not isinstance(qn, str):
                                        continue
                                    if not pat.search(qn):
                                        continue
                                    if prefer_fraction is None:
                                        return elem
                                    if prefer_fraction and is_nonfraction:
                                        return elem
                                    if (prefer_fraction is False) and is_nonnumeric:
                                        return elem
                                    # fallback: keep first matched
                                    if not found_elem:
                                        found_elem = elem
                                return found_elem

                            current_company = None
                            for tr in tbl.find_all('tr'):
                                tds = tr.find_all('td')
                                if not tds:
                                    continue
                                # Company header row: bold/underlined text
                                hdr_txt = tds[0].get_text(strip=True) if tds else ''
                                if hdr_txt and ('underline' in (tds[0].get('style','')) or tds[0].find(['b','strong'])):
                                    current_company = re.sub(r'\s+',' ', hdr_txt)
                                    continue
                                # Data row: often has background-color rgb(204,238,255)
                                style = tr.get('style','')
                                if 'background-color' in style and ('204,238,255' in style or 'rgb(204, 238, 255)' in style):
                                    inv_type = tds[0].get_text(strip=True) if tds else ''
                                    # inline ix tags (namespace-agnostic)
                                    industry_ix = find_ix(tr, r'InvestmentIndustryDescription', prefer_fraction=False)
                                    date_ix = find_ix(tr, r'InitialInvestmentDate', prefer_fraction=False)
                                    principal_ix = find_ix(tr, r'InvestmentOwnedBalancePrincipalAmount|InvestmentOwnedBalanceShares', prefer_fraction=True)
                                    cost_ix = find_ix(tr, r'InvestmentOwnedAtCost', prefer_fraction=True)
                                    fv_ix = find_ix(tr, r'InvestmentOwnedAtFairValue', prefer_fraction=True)
                                    pct_ix = find_ix(tr, r'InvestmentOwnedPercentOfNetAssets', prefer_fraction=True)
                                    def clean_num(elem):
                                        if not elem: return None
                                        return parse_money(elem.get_text())
                                    industry = industry_ix.get_text(strip=True) if industry_ix else None
                                    date_val = date_ix.get_text(strip=True) if date_ix else None
                                    principal = clean_num(principal_ix)
                                    cost = clean_num(cost_ix)
                                    fv = clean_num(fv_ix)
                                    # build investment if we have company and any of cost/fv
                                    if current_company and (cost is not None or fv is not None):
                                        investments.append(SSSSInvestment(
                                            company_name=current_company,
                                            investment_type=inv_type or 'Unknown',
                                            industry=industry or 'Unknown',
                                            acquisition_date=date_val,
                                            principal_amount=principal,
                                            cost=cost,
                                            fair_value=fv
                                        ))
                        # de-dup minimal results
                        ded, seen = [], set()
                        for inv in investments:
                            key = (inv.company_name, inv.fair_value or 0.0)
                            if key in seen: continue
                            seen.add(key); ded.append(inv)
                        investments = ded
                    except Exception:
                        pass
        # de-dup
        ded, seen = [], set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen: continue
            seen.add(combo); ded.append(inv)
        investments = ded
        # write
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output'); os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'SSSS_SuRo_Capital_Corp_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate',
                'shares_units','percent_net_assets','currency','commitment_limit','undrawn_commitment'
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
                    'business_description': inv.business_description or '',
                    'investment_type': standardized_inv_type,
                    'acquisition_date': inv.acquisition_date or '',
                    'maturity_date': inv.maturity_date or '',
                    'principal_amount': inv.principal_amount or '',
                    'cost': inv.cost or '',
                    'fair_value': inv.fair_value or '',
                    'interest_rate': inv.interest_rate or '',
                    'reference_rate': standardized_ref_rate or '',
                    'spread': inv.spread or '',
                    'floor_rate': inv.floor_rate or '',
                    'pik_rate': inv.pik_rate or '',
                    'shares_units': inv.shares_units or '',
                    'percent_net_assets': inv.percent_net_assets or '',
                    'currency': inv.currency or 'USD',
                    'commitment_limit': inv.commitment_limit or '',
                    'undrawn_commitment': inv.undrawn_commitment or '',
                })
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments)
        }

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        contexts: List[Dict] = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1); chtml = m.group(2)
            tm = tp.search(chtml)
            if not tm: continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', chtml)
            sd = re.search(r'<startDate>([^<]+)</startDate>', chtml)
            ed = re.search(r'<endDate>([^<]+)</endDate>', chtml)
            same_ind = None
            sm = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', chtml, re.DOTALL|re.IGNORECASE)
            if sm: same_ind = self._industry_member_to_name(sm.group(1).strip())
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
            company = identifier[:last].strip(); tail = identifier[last+1:].strip()
        else:
            company = identifier.strip(); tail = ''
        res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
        patterns = [
            r'First\s+lien\s+.*$', r'Second\s+lien\s+.*$', r'Unitranche\s*\d*$', r'Senior\s+secured\s*\d*$',
            r'Secured\s+Debt\s*\d*$', r'Unsecured\s+Debt\s*\d*$', r'Preferred\s+Equity$', r'Preferred\s+Stock$',
            r'Common\s+Stock\s*\d*$', r'Member\s+Units\s*\d*$', r'Warrants?$'
        ]
        it = None
        for p in patterns:
            mm = re.search(p, tail, re.IGNORECASE)
            if mm: it = mm.group(0); break
        if not it and tail: it = tail
        if it: res['investment_type'] = it
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        # Extract standard XBRL facts and capture unitRef for currency
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept = match.group(1); cref = match.group(2); unit_ref = match.group(3); val = match.group(4)
            if val and cref:
                fact_entry = {'concept': concept, 'value': val.strip()}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match: fact_entry['currency'] = currency_match.group(1)
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
                    if currency_match: fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
            window = content[max(0, m.start()-3000):min(len(content), m.end()+3000)]
            ref = re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref: facts[cref].append({'concept':'derived:ReferenceRateToken','value': ref.group(1).replace('+','').upper()})
            floor = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor: facts[cref].append({'concept':'derived:FloorRate','value': floor.group(1)})
            pik = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik: facts[cref].append({'concept':'derived:PIKRate','value': pik.group(1)})
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[SSSSInvestment]:
        if context['company_name']=='Unknown': return None
        inv = SSSSInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        for f in facts:
            c=f['concept']; v=f['value'].replace(',',''); cl=c.lower()
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
                inv.spread = self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v); continue
            if cl=='derived:referenceratetoken': inv.reference_rate=v.upper(); continue
            if cl=='derived:floorrate': inv.floor_rate=self._percent(v); continue
            if cl=='derived:pikrate': inv.pik_rate=self._percent(v); continue
            if cl=='derived:acquisitiondate': inv.acquisition_date=v; continue
            if cl=='derived:maturitydate': inv.maturity_date=v; continue
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
            inv.acquisition_date=context['start_date'][:10]
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
    # HTML Schedule of Investments (tables) first – mirror WHF flow to save CSV + simplified tables
    client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
    index_url = client.get_filing_index_url("SSSS", "10-Q")
    if not index_url:
        print("Could not find latest 10-Q for SSSS")
        return
    docs = client.get_documents_from_index(index_url)
    main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
    if not main_html:
        print("No main HTML document found for SSSS")
        return
    resp = requests.get(main_html.url, headers=client.headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def normalize_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def normalize_key(text: str) -> str:
        return normalize_text(text).lower()

    def strip_footnote_refs(text: Optional[str]) -> str:
        if not text:
            return ""
        cleaned = text.replace("â€“", "–").replace("â€”", "—")
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", cleaned)
        return normalize_text(cleaned)

    def extract_tables_under_heading(ssoup: BeautifulSoup) -> List[BeautifulSoup]:
        matches: List[BeautifulSoup] = []
        def contains_date_like(blob: str) -> bool:
            return re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", blob, re.IGNORECASE) is not None
        required_any = ["schedule of investments", "consolidated", "unaudited", "dollar amounts in"]
        def heading_matches(blob: str) -> bool:
            blob_l = blob
            if "schedule of investments" not in blob_l:
                return False
            if not contains_date_like(blob_l):
                count = sum(1 for t in required_any if t in blob_l)
                if count < 2:
                    return False
            return True
        for table in ssoup.find_all("table"):
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
                txt = c.get_text(" ", strip=True)
                txt = txt.replace("\u200b", "").replace("\xa0", " ")
                vals.append(normalize_text(txt))
            rows.append(vals)
        return rows

    def compact_row(cells: List[str]) -> List[str]:
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
            # Choose the latest Fair Value column by year (or the last occurrence)
            fv_latest_idx = None
            best_year = -1
            for i,k in enumerate(keys):
                if k.startswith('fair value at'):
                    m = re.search(r'(19|20)\d{2}', k)
                    yr = int(m.group(0)) if m else -1
                    if yr > best_year or (yr == -1 and fv_latest_idx is None):
                        best_year = yr
                        fv_latest_idx = i
            return {
                "company": find_idx(["issuer","company","portfolio company"]) or -1,
                "type": find_idx(["investment type","security type","class"]) or -1,
                "floor": find_idx(["floor"]) or -1,
                "ref": find_idx(["reference rate"]) or -1,
                "spread": find_idx(["spread above index","spread"]) or -1,
                "rate": find_idx(["interest rate"]) or -1,
                "acq": find_idx(["acquisition date","investment date","initial investment date"]) or -1,
                "mat": find_idx(["maturity date","expiration date"]) or -1,
                "prin": find_idx(["principal","share amount","principal/ quantity","principal/quantity","shares/principal/ quantity"]) or -1,
                "cost": find_idx(["amortized cost","cost"]) or -1,
                "fv": (fv_latest_idx if fv_latest_idx is not None else (find_idx(["fair value"]) or -1)),
                "pct": find_idx(["percentage of net assets","% of net assets"]) or -1,
            }
        return None

    def parse_section_tables(tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
        recs: List[Dict[str, Optional[str]]] = []
        def parse_money_cell(x: Optional[str]) -> Optional[float]:
            if not x:
                return None
            t = str(x).strip()
            # remove stray trailing commas/parentheses artifacts like ",)"
            t = t.replace(',)', ')')
            t = t.replace(' )', ')')
            t = t.replace('$', '').replace(',', '')
            if t in ('—','-','–',''):
                return None
            neg = False
            if t.startswith('(') and t.endswith(')'):
                neg = True
                t = t[1:-1]
            try:
                v = float(t)
                return -v if neg else v
            except:
                return None
        for table in tables:
            rows = table_to_rows(table)
            if not rows:
                continue
            hdr = find_header_map(rows) or {}
            last_company: Optional[str] = None
            last_industry: Optional[str] = None
            type_keyword = re.compile(
                r'^(?:Common|Preferred|Class|Series|Membership|Senior|Subordinated|Warrant|Convertible|Note|Unit|Limited|Promissory|Simple\s+Agreement)',
                re.IGNORECASE
            )

            def split_company_and_type(raw: str) -> (str, Optional[str]):
                if not raw:
                    return "", None
                normalized = raw.replace("â€“", "–").replace("â€”", "—")
                parts = re.split(r'\s*[–—-]\s*', normalized, maxsplit=1)
                if len(parts) == 2 and type_keyword.match(parts[1].strip()):
                    return parts[0].strip(), parts[1].strip()
                return normalized.strip(), None

            def is_type_string(text: Optional[str]) -> bool:
                return bool(text and type_keyword.match(text.strip()))

            for r in rows:
                row = compact_row(r)
                if not row:
                    continue
                first = row[0]
                # Skip obvious section headers
                if normalize_key(first) in ("investments","debt investments","equity investments"):
                    continue
                # header row skip
                row_l = " ".join(normalize_key(c) for c in row)
                if "issuer" in row_l and "investment" in row_l and "fair value" in row_l:
                    continue
                # Identify company/industry lines (no dates/rates)
                if not any(re.search(r"\d{1,2}/\d{1,2}/\d{4}", c) for c in row) and not any('%' in c for c in row):
                    # often industry-only rows
                    if len(row) == 1:
                        candidate = split_company_and_type(first)[0]
                        if not is_type_string(candidate):
                            last_industry = candidate
                    else:
                        candidate, _ = split_company_and_type(row[0])
                        if not is_type_string(candidate):
                            last_company = candidate
                    continue
                # Skip totals/subtotals and portfolio header rows
                first_l = normalize_key(first)
                if (
                    first_l.startswith('total ')
                    or first_l == 'total'
                    or first_l == 'totals'
                    or first_l.startswith('portfolio investments')
                    or first_l.startswith('non-controlled')
                    or first_l in ('preferred stock', 'options', 'common stock')
                ):
                    continue
                def get(idx: int) -> Optional[str]:
                    return row[idx] if 0 <= idx < len(row) else None
                raw_company = get(hdr.get("company", -1)) or first
                company_candidate, inferred_type = split_company_and_type(raw_company)
                inv_type = get(hdr.get("type", -1)) or inferred_type or ""
                if is_type_string(company_candidate):
                    # this cell is likely the investment type, use last known company
                    if not inv_type:
                        inv_type = company_candidate
                    company = last_company or company_candidate
                else:
                    company = company_candidate
                    last_company = company or last_company
                floor = get(hdr.get("floor", -1))
                ref = get(hdr.get("ref", -1))
                spread = get(hdr.get("spread", -1))
                rate = get(hdr.get("rate", -1))
                acq = get(hdr.get("acq", -1))
                mat = get(hdr.get("mat", -1))
                prin = get(hdr.get("prin", -1))
                cost = get(hdr.get("cost", -1))
                fv = get(hdr.get("fv", -1))
                pct = get(hdr.get("pct", -1))
                # Parse numeric cells into floats where possible
                prin_v = parse_money_cell(prin)
                cost_v = parse_money_cell(cost)
                fv_v = parse_money_cell(fv)
                pct_v = None
                if pct:
                    pp = str(pct).strip().rstrip('%')
                    try:
                        pct_v = float(pp)
                    except:
                        pct_v = parse_money_cell(pct)
                # Heuristic date extraction if acq/mat not in headers
                row_blob = " ".join(row)
                if not inv_type:
                    inferred_match = re.search(
                        r'(?:Common|Preferred)\s+Shares?(?:,\s*Series\s+[A-Za-z0-9-]+)?'
                        r'|Class\s+[A-Za-z0-9-]+\s+Units?'
                        r'|Membership\s+Interest(?:s)?(?:,\s*Class\s+[A-Za-z0-9-]+)?'
                        r'|Series\s+[A-Za-z0-9-]+\s+Shares?'
                        r'|Junior\s+Preferred\s+Shares?(?:,\s*Series\s+[A-Za-z0-9-]+)?'
                        r'|Senior\s+Secured\s+[^,;]+'
                        r'|Subordinated\s+(?:Debt|Note)'
                        r'|Promissory\s+Note'
                        r'|Convertible\s+(?:Debt|Notes?)'
                        r'|Simple\s+Agreement\s+for\s+Future\s+Equity'
                        r'|Warrants?',
                        row_blob,
                        re.IGNORECASE
                    )
                    if inferred_match:
                        inv_type = inferred_match.group(0).strip()

                if (not acq or acq == '') or (not mat or mat == ''):
                    date_matches = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", row_blob)
                    if date_matches:
                        if len(date_matches) >= 2:
                            acq = acq or date_matches[0]
                            mat = mat or date_matches[-1]
                        else:
                            if re.search(r"expiration|maturity", row_blob, re.IGNORECASE):
                                mat = mat or date_matches[0]
                            else:
                                acq = acq or date_matches[0]

                # Extract reference_rate and spread from inline text if not in columns
                if not ref or not spread:
                    # Pattern: "SOFR + 6.00%", "Prime + 2.85%", "LIBOR + 3.50%", "E + 7.00%" (EURIBOR)
                    ref_map = {'E': 'EURIBOR', 'BASE RATE': 'BASE RATE', 'BASE': 'BASE RATE'}
                    ref_match = re.search(r'(\b[0-9]+[-\s]?month\s+)?(SOFR|LIBOR|PRIME|Prime|Base Rate|EURIBOR|E)\s*\+\s*([\d\.]+)\s*%?', row_blob, re.IGNORECASE)
                    if ref_match:
                        sofr_type = ref_match.group(1).strip() if ref_match.group(1) else None
                        base = ref_match.group(2).upper()
                        base = ref_map.get(base, base)
                        if sofr_type and base == 'SOFR':
                            ref = ref or f"SOFR ({sofr_type})"
                        else:
                            ref = ref or base
                        spread = spread or f"{float(ref_match.group(3)):.2f}%"

                # Extract floor rate from inline text if not in column
                if not floor:
                    floor_match = re.search(r"floor\s*(?:rate)?\s*([\d\.]+)\s*%", row_blob, re.IGNORECASE)
                    if floor_match:
                        floor = f"{float(floor_match.group(1)):.2f}%"

                # Extract PIK rate from inline text
                pik_rate = None
                pik_match = re.search(r"PIK\s*(?:interest)?\s*([\d\.]+)\s*%", row_blob, re.IGNORECASE)
                if pik_match:
                    pik_rate = f"{float(pik_match.group(1)):.2f}%"

                recs.append({
                    "company_name": strip_footnote_refs(company),
                    "investment_type": strip_footnote_refs(inv_type),
                    "industry": strip_footnote_refs(last_industry or ""),
                    "interest_rate": rate,
                    "reference_rate": ref,
                    "spread": spread,
                    "floor_rate": floor,
                    "pik_rate": pik_rate,
                    "acquisition_date": acq,
                    "maturity_date": mat,
                    "principal_amount": prin_v,
                    "amortized_cost": cost_v,
                    "fair_value": fv_v,
                    "percent_of_net_assets": pct_v,
                })
        return recs

    tables = extract_tables_under_heading(soup)
    if not tables:
        # Fallback: choose the largest tables by rows/cols to inspect manually
        all_tables = soup.find_all("table")
        scored = []
        for t in all_tables:
            rows = t.find_all("tr")
            rcount = len(rows)
            ccount = max((len(r.find_all(["td","th"])) for r in rows), default=0)
            scored.append((rcount*ccount, t))
        scored.sort(reverse=True, key=lambda x: x[0])
        tables = [t for _, t in scored[:10]]
    records = parse_section_tables(tables)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, "SSSS_Schedule_Continued_latest.csv")
    fieldnames = [
        "company_name","investment_type","industry","interest_rate","reference_rate","spread","floor_rate","pik_rate","acquisition_date","maturity_date","principal_amount","amortized_cost","fair_value","percent_of_net_assets",
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

    # Also build normalized investments CSV from the HTML schedule
    def parse_float_maybe(s: Optional[str]) -> Optional[float]:
        if s is None:
            return None
        t = str(s).replace(",", "").replace("$", "").strip()
        if t in ("—","-","–",""):
            return None
        # handle parentheses negatives like (1,234)
        neg = False
        if t.startswith("(") and t.endswith(")"):
            neg = True
            t = t[1:-1]
        try:
            v = float(t)
            return -v if neg else v
        except:
            return None

    inv_rows: List[Dict[str, Optional[str]]] = []
    for rec in records:
        name = (rec.get("company_name") or "").strip()
        if not name or name.lower().startswith("total "):
            continue
        pa = parse_float_maybe(rec.get("principal_amount"))
        cost = parse_float_maybe(rec.get("amortized_cost"))
        fv = parse_float_maybe(rec.get("fair_value"))
        if pa is None and cost is None and fv is None:
            continue
        inv_rows.append({
            'company_name': name,
            'industry': rec.get('industry') or '',
            'business_description': '',
            'investment_type': rec.get('investment_type') or '',
            'acquisition_date': rec.get('acquisition_date') or '',
            'maturity_date': rec.get('maturity_date') or '',
            'principal_amount': pa if pa is not None else '',
            'cost': cost if cost is not None else '',
            'fair_value': fv if fv is not None else '',
            'interest_rate': rec.get('interest_rate') or '',
            'reference_rate': rec.get('reference_rate') or '',
            'spread': rec.get('spread') or '',
            'floor_rate': rec.get('floor_rate') or '',
            'pik_rate': rec.get('pik_rate') or '',
        })

    inv_out = os.path.join(out_dir, 'SSSS_SuRo_Capital_Corp_investments.csv')
    with open(inv_out, 'w', newline='', encoding='utf-8') as f:
        inv_fields = ['company_name','industry','business_description','investment_type','acquisition_date','maturity_date','principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate']
        w = csv.DictWriter(f, fieldnames=inv_fields)
        w.writeheader()
        for r in inv_rows:
            # Apply standardization
            if 'investment_type' in r:
                r['investment_type'] = standardize_investment_type(r.get('investment_type'))
            if 'industry' in r:
                r['industry'] = standardize_industry(r.get('industry'))
            if 'reference_rate' in r:
                r['reference_rate'] = standardize_reference_rate(r.get('reference_rate')) or ''
            
            w.writerow(r)
    print(f"Saved {len(inv_rows)} rows to {inv_out}")

    tables_dir = os.path.join(out_dir, "ssss_tables")
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
            with open(os.path.join(tables_dir, f"ssss_table_{i}.html"), "w", encoding="utf-8") as fh:
                fh.write(str(simple))
    print(f"Saved {len(tables)} simplified tables to {tables_dir}")

if __name__=='__main__':
    main()

    import sys
    sys.exit(0)
