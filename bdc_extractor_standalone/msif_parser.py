#!/usr/bin/env python3
"""
MSIF (MSC Income Fund Inc) Investment Extractor
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
class MSIFInvestment:
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


class MSIFExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "MSIF") -> Dict:
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
        return self.extract_from_url(txt_url, "MSC_Income_Fund_Inc", cik)

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
        investments: List[MSIFInvestment] = []
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
        out_file = os.path.join(out_dir, 'MSIF_MSC_Income_Fund_Inc_investments.csv')
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
        inv_dicts = [{'company_name':inv.company_name,'industry':standardize_industry(inv.industry),'business_description':inv.business_description,'investment_type':standardize_investment_type(inv.investment_type),'acquisition_date':inv.acquisition_date,'maturity_date':inv.maturity_date,'principal_amount':inv.principal_amount,'cost':inv.cost,'fair_value':inv.fair_value,'interest_rate':inv.interest_rate,'reference_rate':standardize_reference_rate(inv.reference_rate),'spread':inv.spread,'floor_rate':inv.floor_rate,'pik_rate':inv.pik_rate} for inv in investments]
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'investments': inv_dicts,
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
        
        # MSIF format: "Company Name, Investment Type"
        # Example: "BDB Holdings, LLC, Secured Debt"
        # Or: "GRT Rubber Technologies LLC,  Secured Debt 1" (note extra spaces)
        
        if ',' in identifier:
            last = identifier.rfind(',')
            company = identifier[:last].strip()
            tail = identifier[last+1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        
        # Clean company name - remove extra spaces, trailing commas
        company = re.sub(r'\s+', ' ', company).rstrip(',').strip()
        
        # Clean investment type - remove leading/trailing spaces, normalize
        tail = re.sub(r'\s+', ' ', tail).strip()
        
        # Extract investment type using patterns
        patterns = [
            r'First\s+lien\s+.*$', r'Second\s+lien\s+.*$', r'Unitranche\s*\d*$', r'Senior\s+secured\s*\d*$',
            r'Secured\s+Debt\s*\d*$', r'Unsecured\s+Debt\s*\d*$', r'Preferred\s+Equity$', r'Preferred\s+Stock$',
            r'Common\s+Stock\s*\d*$', r'Member\s+Units\s*\d*$', r'Preferred\s+Member\s+Units\s*\d*$', r'Warrants?$',
            r'LP\s*Interests?.*$', r'L\.P\.\s*Interests?.*$'
        ]
        it = None
        for p in patterns:
            mm = re.search(p, tail, re.IGNORECASE)
            if mm:
                it = mm.group(0)
                break
        if not it and tail:
            it = tail
        
        # Normalize investment type
        if it:
            it = re.sub(r'\s+\d+$', '', it)  # Remove trailing numbers like "1", "2"
            it = it.strip()
            # Normalize common patterns
            it_lower = it.lower()
            if 'secured debt' in it_lower:
                it = 'Secured Debt'
            elif 'preferred equity' in it_lower:
                it = 'Preferred Equity'
            elif 'common stock' in it_lower:
                it = 'Common Stock'
            elif 'member units' in it_lower:
                if 'preferred' in it_lower:
                    it = 'Preferred Member Units'
                else:
                    it = 'Member Units'
            elif 'lp interests' in it_lower or 'l.p. interests' in it_lower:
                it = 'LP Interests'
            res['investment_type'] = it
        
        res['company_name'] = company if company else 'Unknown'
        
        # Note: Industries are not available in MSIF XBRL identifier strings
        # They would need to come from HTML tables or external lookup
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[MSIFInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = MSIFInvestment(
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
    ex=MSIFExtractor()
    try:
        res=ex.extract_from_ticker('MSIF')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()
