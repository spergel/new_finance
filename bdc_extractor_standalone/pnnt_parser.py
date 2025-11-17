#!/usr/bin/env python3
"""
PNNT (PennantPark Investment Corporation) Investment Extractor

Parses verbose InvestmentIdentifierAxis identifiers like:
"Investments in Non-Controlled, Non-Affiliated Portfolio Companies First Lien Secured Debt Issuer Name Spendmend Holdings LLC Maturity 03/01/2028 Industry Business Services Current Coupon 10.25% Basis Point Spread Above Index 3M SOFR+565"

- XBRL-first via InvestmentIdentifierAxis
- Latest-instant filtering and de-duplication
- Industry enrichment via EquitySecuritiesByIndustryAxis if present
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass
import requests
import os
import csv

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class PNNTInvestment:
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


class PNNTExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "PNNT", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """
        Extract investments from 10-Q filing.
        
        Args:
            ticker: Company ticker symbol
            year: Year to filter filings (default: 2025). Set to None to get latest regardless of year.
            min_date: Minimum date in YYYY-MM-DD format (overrides year if provided)
        """
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError("Could not find 10-Q filing")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "PennantPark_Investment_Corp", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        r = requests.get(filing_url, headers=self.headers)
        r.raise_for_status()
        content = r.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        # Latest instant only
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
            logger.info(f"Filtered contexts to instant {sel}: {len(contexts)} remaining")

        # Industry enrichment
        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]

        facts_by_context = self._extract_facts(content)
        investments: List[PNNTInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # De-dup
        ded: List[PNNTInvestment] = []
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
        out_file = os.path.join(out_dir, 'PNNT_PennantPark_Investment_Corp_investments.csv')
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
                'maturity_date': parsed.get('maturity_date'),
                'interest_rate': parsed.get('interest_rate'),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'pik_rate': parsed.get('pik_rate'),
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _parse_identifier(self, text: str) -> Dict[str, str]:
        res = {'company_name': 'Unknown', 'industry': 'Unknown', 'investment_type': 'Unknown'}

        # Extract company (after 'Issuer Name ')
        comp = re.search(r'Issuer Name\s+(.+?)(?:\s+Maturity\b|\s+Industry\b|\s+Current Coupon\b|\s+Basis Point|$)', text)
        if comp:
            res['company_name'] = comp.group(1).strip().rstrip('.')

        # Investment type: take the phrase before 'Issuer Name', without the long prefix
        before = text.split('Issuer Name')[0]
        # Common patterns
        pat_types = [
            r'First\s+Lien\s+Secured\s+Debt',
            r'Second\s+Lien\s+Secured\s+Debt',
            r'Subordinated\s+Debt/Corporate\s+Notes',
            r'Preferred\s+Equity/Partnership\s+Interests',
            r'Common\s+Equity/Partnership\s+Interests/Warrants',
            r'Common\s+Equity/Partnership\s+Interests',
            r'Preferred\s+Equity',
            r'Common\s+Equity',
            r'First\s+Lien\s+Secured\s+Debt',
        ]
        it = None
        for p in pat_types:
            m = re.search(p, before, re.IGNORECASE)
            if m:
                it = m.group(0)
        if it:
            res['investment_type'] = it

        # Maturity
        mat = re.search(r'Maturity\s+([\d/]{4,10})', text)
        if mat:
            res['maturity_date'] = mat.group(1)

        # Industry
        ind = re.search(r'Industry\s+([A-Za-z,&\s/]+?)(?:\s+Current Coupon\b|\s+Basis Point|$)', text)
        if ind:
            industry_text = ind.group(1).strip()
            # Clean up industry name - remove trailing periods, extra spaces
            industry_text = re.sub(r'\.+$', '', industry_text)
            industry_text = re.sub(r'\s+', ' ', industry_text).strip()
            res['industry'] = industry_text

        # Current Coupon (may contain PIK)
        coup = re.search(r'Current\s+Coupon\s+([\d\.]+)%', text)
        if coup:
            res['interest_rate'] = self._percent(coup.group(1))
        # PIK in coupon line like '(PIK 15.00%)' or 'PIK 9.80%'
        pik = re.search(r'PIK\s+([\d\.]+)%', text)
        if pik:
            res['pik_rate'] = self._percent(pik.group(1))

        # Basis Point Spread Above Index ... e.g., '3M SOFR+565' or 'SOFR+540'
        bps = re.search(r'(?:\b\d+M\s+)?(SOFR|LIBOR|PRIME|Base Rate|EURIBOR)\s*\+\s*(\d{2,4})', text, re.IGNORECASE)
        if bps:
            rate = bps.group(1).upper()
            res['reference_rate'] = rate
            spread_bps = int(bps.group(2))
            res['spread'] = self._percent(str(spread_bps / 100.0))

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
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[PNNTInvestment]:
        if context['company_name'] == 'Unknown':
            return None
        inv = PNNTInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            maturity_date=context.get('maturity_date'),
            interest_rate=context.get('interest_rate'),
            reference_rate=context.get('reference_rate'),
            spread=context.get('spread'),
            pik_rate=context.get('pik_rate'),
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v = v.replace(',', '')
            cl = c.lower()
            if any(k in cl for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal']):
                try: 
                    val = float(v)
                    if val > 0:  # Only accept positive principal amounts
                        inv.principal_amount = val
                except: pass; continue
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: 
                    val = float(v)
                    if val > 0:  # Only accept positive cost values
                        inv.cost = val
                except: pass; continue
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: 
                    val = float(v)
                    # For unfunded commitments, fair value might be negative (liability)
                    # Set to None if negative, as it's not a meaningful fair value
                    if val >= 0:
                        inv.fair_value = val
                    # If negative and we have principal, this might be an unfunded commitment
                    elif val < 0 and inv.principal_amount:
                        # Negative fair value for unfunded commitments - set to None
                        inv.fair_value = None
                except: pass; continue
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
        
        # Handle unfunded commitments - if we have principal but negative or zero fair value,
        # this is likely an unfunded commitment
        is_unfunded = 'unfunded' in inv.company_name.lower() or 'unfunded' in (inv.investment_type or '').lower()
        if is_unfunded and inv.principal_amount and (not inv.fair_value or inv.fair_value <= 0):
            # For unfunded commitments, fair value should be None or 0, not negative
            inv.fair_value = None
        
        # Heuristic for commitment_limit and undrawn_commitment
        if inv.fair_value and not inv.principal_amount: 
            inv.commitment_limit = inv.fair_value
        elif inv.fair_value and inv.principal_amount:
            if inv.fair_value > inv.principal_amount:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value - inv.principal_amount
        
        # Skip investments with no meaningful financial data
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _build_industry_index(self, content: str) -> Dict[str, str]:
        m = {} ; cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        ep = re.compile(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', re.DOTALL|re.IGNORECASE)
        for mm in cp.finditer(content):
            html = mm.group(2)
            inst = re.search(r'<instant>([^<]+)</instant>', html)
            inst = inst.group(1) if inst else None
            if not inst: continue
            em = ep.search(html)
            if not em: continue
            m[inst] = self._industry_member_to_name(em.group(1).strip())
        return m

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local = qname.split(':',1)[-1] if ':' in qname else qname
        local = re.sub(r'Member$','', local)
        if local.endswith('Sector'): local = local[:-6]
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+',' ', words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates = [c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None

    def _percent(self, s: str) -> str:
        try:
            v = float(s)
        except:
            return f"{s}%"
        if 0 < abs(v) <= 1.0:
            v *= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex = PNNTExtractor()
    try:
        res = ex.extract_from_ticker('PNNT')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == '__main__':
    main()



