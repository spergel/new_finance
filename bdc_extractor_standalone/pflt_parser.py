#!/usr/bin/env python3
"""
PFLT (PennantPark Floating Rate Capital Ltd) Investment Extractor
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
class PFLTInvestment:
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


class PFLTExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "PFLT") -> Dict:
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
        return self.extract_from_url(txt_url, "PennantPark_Floating_Rate_Capital_Ltd", cik)

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
        investments: List[PFLTInvestment] = []
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

        out_dir = 'output'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'PFLT_PennantPark_Floating_Rate_Capital_Ltd_investments.csv')
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
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        return re.sub(r'\s+',' ', cleaned).strip()
    
    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        ident_clean = re.sub(r'\s+',' ', identifier).strip()
        
        # PFLT format examples:
        # "First Lien Secured Debt Issuer Name ARGANO LLC Maturity 9/13/2029 Industry Business Services Current Coupon 10.07% Basis Point Spread Above Index SOFR+575"
        # "Investments in Non-Controlled, Non-Affiliated Portfolio Companies First Lien Secured Debt Urology Management Holdings Inc. - Unfunded Term Loan Maturity 9/3/2026 Industry Healthcare Providers and Services"
        # "Investments in Non-Controlled, Non-Affiliated Portfolio Companies Common Equity/Warrants Gauge Loving Tan LP Industry Personal Products"
        
        # Extract investment type - look for keywords first, then extract base type
        it = None
        if re.search(r'First\s+Lien', ident_clean, re.IGNORECASE):
            it = 'First Lien Secured Debt'
        elif re.search(r'Second\s+Lien', ident_clean, re.IGNORECASE):
            it = 'Second Lien Secured Debt'
        elif re.search(r'Common\s+Equity', ident_clean, re.IGNORECASE) or re.search(r'Warrants', ident_clean, re.IGNORECASE):
            it = 'Common Equity/Warrants'
        elif re.search(r'Subordinate\s+Debt', ident_clean, re.IGNORECASE):
            it = 'Subordinate Debt'
        elif re.search(r'Preferred\s+Equity', ident_clean, re.IGNORECASE):
            it = 'Preferred Equity'
        elif re.search(r'Preferred\s+Stock', ident_clean, re.IGNORECASE):
            it = 'Preferred Stock'
        
        if it:
            res['investment_type'] = self._strip_footnote_refs(it)
        
        # Extract industry: look for "Industry [Industry Name]" pattern
        ind_match = re.search(r'Industry\s+([^C]+?)(?:\s+Current\s+Coupon|\s+Maturity|$)', ident_clean, re.IGNORECASE)
        if ind_match:
            industry_raw = ind_match.group(1).strip()
            industry_raw = industry_raw.rstrip('.,').strip()
            # Clean up industry - remove common trailing descriptors
            industry_raw = re.sub(r'\s+(Inc|LLC|Corp|Ltd|Company|Holdings)$', '', industry_raw, flags=re.IGNORECASE)
            if industry_raw and len(industry_raw) > 2:
                res['industry'] = self._strip_footnote_refs(industry_raw)
        
        # Extract company name
        company_name = None
        
        # Pattern 1: "Issuer Name [Company] Maturity" (e.g., "Issuer Name ARGANO LLC Maturity")
        issuer_match = re.search(r'Issuer\s+Name\s+([^M]+?)\s+Maturity', ident_clean, re.IGNORECASE)
        if issuer_match:
            company_name = issuer_match.group(1).strip()
        
        # Pattern 2: "Investments in Non-Controlled... [Investment Type] [Company] Maturity/Industry/-"
        if not company_name:
            # Try to match the pattern directly: after "Portfolio Companies [Investment Type] [Company Name]"
            # Look for: "Investments in Non-Controlled, Non-Affiliated Portfolio Companies [Investment Type] [Company]"
            pattern2_match = re.search(
                r'Investments\s+in\s+Non[^-]+Portfolio\s+Companies\s+(?:First\s+Lien\s+Secured\s+Debt|Second\s+Lien\s+Secured\s+Debt|Subordinate\s+Debt|Common\s+Equity/Warrants|Preferred\s+Equity|Preferred\s+Stock)\s+(.+?)(?:\s+Maturity|\s+Industry|\s+-|\s*$)',
                ident_clean,
                re.IGNORECASE
            )
            if pattern2_match:
                company_name = pattern2_match.group(1).strip()
            else:
                # Fallback: remove prefix manually
                candidate = ident_clean
                # Match "Investments in Non-Controlled" (with comma) followed by anything up to "Portfolio Companies"
                candidate = re.sub(r'^Investments\s+in\s+Non[^P]*Portfolio\s+Companies\s+', '', candidate, flags=re.IGNORECASE)
                
                # Remove investment type keywords
                candidate = re.sub(r'^First\s+Lien\s+Secured\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Second\s+Lien\s+Secured\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Subordinate\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Common\s+Equity/Warrants\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Preferred\s+Equity\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Preferred\s+Stock\s+', '', candidate, flags=re.IGNORECASE)
                
                # Find stop points: Maturity, Industry, or dash
                maturity_pos = candidate.upper().find('MATURITY')
                industry_pos = candidate.upper().find('INDUSTRY')
                dash_pos = candidate.find(' - ')
                
                stop_positions = [pos for pos in [maturity_pos, industry_pos, dash_pos] if pos > 0]
                end_pos = min(stop_positions) if stop_positions else len(candidate)
                
                if end_pos > 0:
                    company_raw = candidate[:end_pos].strip()
                    # Remove suffixes
                    company_raw = re.sub(r'\s+-\s+(Unfunded|Term\s+Loan|Revolver|Convertible\s+Notes).*$', '', company_raw, flags=re.IGNORECASE)
                    company_raw = company_raw.rstrip(' -').strip()
                    if company_raw and len(company_raw) > 2:
                        company_name = company_raw
        
        # Pattern 3: Handle "Issuer Name [Company] (f/k/a...) Maturity" - extract just the main company name
        if company_name:
            # Handle f/k/a cases - prefer the main name before f/k/a
            fka_match = re.search(r'([^(]+?)\s*\(f/k/a\s+([^)]+)\)', company_name, re.IGNORECASE)
            if fka_match:
                # Use the name before f/k/a
                company_name = fka_match.group(1).strip()
        
        if company_name:
            # Final cleanup
            company_name = re.sub(r'\s+\(f/k/a[^)]+\)', '', company_name, flags=re.IGNORECASE)
            company_name = self._strip_footnote_refs(company_name)
            company_name = re.sub(r'^Issuer\s+Name\s+', '', company_name, flags=re.IGNORECASE)
            res['company_name'] = company_name
        
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
            dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[PFLTInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = PFLTInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v = v.replace(',',''); cl=c.lower()
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
                inv.spread = self._percent(v)
                continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v)
                continue
            if cl=='derived:referenceratetoken':
                inv.reference_rate = v.upper(); continue
            if cl=='derived:floorrate':
                inv.floor_rate = self._percent(v); continue
            if cl=='derived:pikrate':
                inv.pik_rate = self._percent(v); continue
            if cl=='derived:acquisitiondate':
                inv.acquisition_date = v; continue
            if cl=='derived:maturitydate':
                inv.maturity_date = v; continue
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
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
    ex=PFLTExtractor()
    try:
        res=ex.extract_from_ticker('PFLT')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()






PFLT (PennantPark Floating Rate Capital Ltd) Investment Extractor
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
class PFLTInvestment:
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


class PFLTExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "PFLT") -> Dict:
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
        return self.extract_from_url(txt_url, "PennantPark_Floating_Rate_Capital_Ltd", cik)

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
        investments: List[PFLTInvestment] = []
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

        out_dir = 'output'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'PFLT_PennantPark_Floating_Rate_Capital_Ltd_investments.csv')
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
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        return re.sub(r'\s+',' ', cleaned).strip()
    
    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        ident_clean = re.sub(r'\s+',' ', identifier).strip()
        
        # PFLT format examples:
        # "First Lien Secured Debt Issuer Name ARGANO LLC Maturity 9/13/2029 Industry Business Services Current Coupon 10.07% Basis Point Spread Above Index SOFR+575"
        # "Investments in Non-Controlled, Non-Affiliated Portfolio Companies First Lien Secured Debt Urology Management Holdings Inc. - Unfunded Term Loan Maturity 9/3/2026 Industry Healthcare Providers and Services"
        # "Investments in Non-Controlled, Non-Affiliated Portfolio Companies Common Equity/Warrants Gauge Loving Tan LP Industry Personal Products"
        
        # Extract investment type - look for keywords first, then extract base type
        it = None
        if re.search(r'First\s+Lien', ident_clean, re.IGNORECASE):
            it = 'First Lien Secured Debt'
        elif re.search(r'Second\s+Lien', ident_clean, re.IGNORECASE):
            it = 'Second Lien Secured Debt'
        elif re.search(r'Common\s+Equity', ident_clean, re.IGNORECASE) or re.search(r'Warrants', ident_clean, re.IGNORECASE):
            it = 'Common Equity/Warrants'
        elif re.search(r'Subordinate\s+Debt', ident_clean, re.IGNORECASE):
            it = 'Subordinate Debt'
        elif re.search(r'Preferred\s+Equity', ident_clean, re.IGNORECASE):
            it = 'Preferred Equity'
        elif re.search(r'Preferred\s+Stock', ident_clean, re.IGNORECASE):
            it = 'Preferred Stock'
        
        if it:
            res['investment_type'] = self._strip_footnote_refs(it)
        
        # Extract industry: look for "Industry [Industry Name]" pattern
        ind_match = re.search(r'Industry\s+([^C]+?)(?:\s+Current\s+Coupon|\s+Maturity|$)', ident_clean, re.IGNORECASE)
        if ind_match:
            industry_raw = ind_match.group(1).strip()
            industry_raw = industry_raw.rstrip('.,').strip()
            # Clean up industry - remove common trailing descriptors
            industry_raw = re.sub(r'\s+(Inc|LLC|Corp|Ltd|Company|Holdings)$', '', industry_raw, flags=re.IGNORECASE)
            if industry_raw and len(industry_raw) > 2:
                res['industry'] = self._strip_footnote_refs(industry_raw)
        
        # Extract company name
        company_name = None
        
        # Pattern 1: "Issuer Name [Company] Maturity" (e.g., "Issuer Name ARGANO LLC Maturity")
        issuer_match = re.search(r'Issuer\s+Name\s+([^M]+?)\s+Maturity', ident_clean, re.IGNORECASE)
        if issuer_match:
            company_name = issuer_match.group(1).strip()
        
        # Pattern 2: "Investments in Non-Controlled... [Investment Type] [Company] Maturity/Industry/-"
        if not company_name:
            # Try to match the pattern directly: after "Portfolio Companies [Investment Type] [Company Name]"
            # Look for: "Investments in Non-Controlled, Non-Affiliated Portfolio Companies [Investment Type] [Company]"
            pattern2_match = re.search(
                r'Investments\s+in\s+Non[^-]+Portfolio\s+Companies\s+(?:First\s+Lien\s+Secured\s+Debt|Second\s+Lien\s+Secured\s+Debt|Subordinate\s+Debt|Common\s+Equity/Warrants|Preferred\s+Equity|Preferred\s+Stock)\s+(.+?)(?:\s+Maturity|\s+Industry|\s+-|\s*$)',
                ident_clean,
                re.IGNORECASE
            )
            if pattern2_match:
                company_name = pattern2_match.group(1).strip()
            else:
                # Fallback: remove prefix manually
                candidate = ident_clean
                # Match "Investments in Non-Controlled" (with comma) followed by anything up to "Portfolio Companies"
                candidate = re.sub(r'^Investments\s+in\s+Non[^P]*Portfolio\s+Companies\s+', '', candidate, flags=re.IGNORECASE)
                
                # Remove investment type keywords
                candidate = re.sub(r'^First\s+Lien\s+Secured\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Second\s+Lien\s+Secured\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Subordinate\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Common\s+Equity/Warrants\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Preferred\s+Equity\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Preferred\s+Stock\s+', '', candidate, flags=re.IGNORECASE)
                
                # Find stop points: Maturity, Industry, or dash
                maturity_pos = candidate.upper().find('MATURITY')
                industry_pos = candidate.upper().find('INDUSTRY')
                dash_pos = candidate.find(' - ')
                
                stop_positions = [pos for pos in [maturity_pos, industry_pos, dash_pos] if pos > 0]
                end_pos = min(stop_positions) if stop_positions else len(candidate)
                
                if end_pos > 0:
                    company_raw = candidate[:end_pos].strip()
                    # Remove suffixes
                    company_raw = re.sub(r'\s+-\s+(Unfunded|Term\s+Loan|Revolver|Convertible\s+Notes).*$', '', company_raw, flags=re.IGNORECASE)
                    company_raw = company_raw.rstrip(' -').strip()
                    if company_raw and len(company_raw) > 2:
                        company_name = company_raw
        
        # Pattern 3: Handle "Issuer Name [Company] (f/k/a...) Maturity" - extract just the main company name
        if company_name:
            # Handle f/k/a cases - prefer the main name before f/k/a
            fka_match = re.search(r'([^(]+?)\s*\(f/k/a\s+([^)]+)\)', company_name, re.IGNORECASE)
            if fka_match:
                # Use the name before f/k/a
                company_name = fka_match.group(1).strip()
        
        if company_name:
            # Final cleanup
            company_name = re.sub(r'\s+\(f/k/a[^)]+\)', '', company_name, flags=re.IGNORECASE)
            company_name = self._strip_footnote_refs(company_name)
            company_name = re.sub(r'^Issuer\s+Name\s+', '', company_name, flags=re.IGNORECASE)
            res['company_name'] = company_name
        
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
            dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[PFLTInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = PFLTInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v = v.replace(',',''); cl=c.lower()
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
                inv.spread = self._percent(v)
                continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v)
                continue
            if cl=='derived:referenceratetoken':
                inv.reference_rate = v.upper(); continue
            if cl=='derived:floorrate':
                inv.floor_rate = self._percent(v); continue
            if cl=='derived:pikrate':
                inv.pik_rate = self._percent(v); continue
            if cl=='derived:acquisitiondate':
                inv.acquisition_date = v; continue
            if cl=='derived:maturitydate':
                inv.maturity_date = v; continue
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
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
    ex=PFLTExtractor()
    try:
        res=ex.extract_from_ticker('PFLT')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





