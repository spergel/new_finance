#!/usr/bin/env python3
"""
Custom BCSF (Bain Capital Specialty Finance) Investment Extractor

BCSF uses XBRL for investment data with embedded information in company_name field.
"""

import re
import logging
import os
from typing import List, Dict, Optional
import csv
from collections import defaultdict
from dataclasses import dataclass
import requests

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class BCSFInvestment:
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


class BCSFCustomExtractor:
    """Custom extractor for BCSF that uses XBRL parsing."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "BCSF") -> Dict:
        """Extract investments from BCSF's latest 10-Q filing."""
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
        return self.extract_from_url(txt_url, "Bain Capital Specialty Finance Inc", cik)
    
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
        investments: List[BCSFInvestment] = []
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
        out_file = os.path.join(out_dir, 'BCSF_Bain_Capital_Specialty_Finance_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
            ])
            writer.writeheader()
            for inv in investments:
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
            'investments': [{'company_name':x.company_name,'industry':standardize_industry(x.industry),'business_description':x.business_description,'investment_type':standardize_investment_type(x.investment_type),'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardize_reference_rate(x.reference_rate),'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate} for x in investments],
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(ind_br),
            'investment_type_breakdown': dict(type_br)
        }
    
    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        res = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1)
            html = m.group(2)
            tm = tp.search(html)
            if not tm:
                continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', html)
            sd = re.search(r'<startDate>([^<]+)</startDate>', html)
            ed = re.search(r'<endDate>([^<]+)</endDate>', html)
            same = None
            em = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', html, re.DOTALL|re.IGNORECASE)
            if em:
                same = self._industry_member_to_name(em.group(1).strip())
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same if same else 'Unknown')
            res.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
                'interest_rate': parsed.get('interest_rate'),
                'maturity_date': parsed.get('maturity_date'),
                'pik_rate': parsed.get('pik_rate'),
            })
        return res
    
    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        """Parse BCSF investment identifier to extract company name, industry, and investment type."""
        res = {'company_name': 'Unknown', 'industry': 'Unknown', 'investment_type': 'Unknown',
               'reference_rate': None, 'spread': None, 'floor_rate': None, 'interest_rate': None,
               'maturity_date': None, 'pik_rate': None}
        
        if not identifier:
            return res
        
        # Decode HTML entities
        identifier = identifier.replace('&amp;', '&').replace('&#x2013;', '-')
        
        # Pattern 1: "Non-controlled/Non-Affiliated Investments [Industry] [Company Name]"
        # Pattern 2: "[Industry] [Company Name]" (without prefix)
        # Pattern 3: "Controlled Affiliate Investments [Industry] [Company Name]"
        
        # Remove common prefixes
        cleaned = identifier
        prefixes = [
            r'^Non-controlled/Non-Affiliated\s+Investments\s+',
            r'^Non-controlled/Non-Affiliate\s+Investments\s+',
            r'^Controlled\s+Affiliate\s+Investments\s+',
            r'^European\s+Currency\s+',
            r'^British\s+Pound\s+',
        ]
        for prefix in prefixes:
            cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
        
        # First, try to extract industry if it's at the beginning
        industry = 'Unknown'
        company_name = cleaned
        
        # Check for industry patterns at the start
        industry_patterns = [
            r'^(Services:\s+Business|Services:\s+Consumer|Services)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Healthcare\s+&\s+Pharmaceuticals|Healthcare)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Aerospace\s+&\s+Defense|Aerospace)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(High\s+Tech\s+Industries|High\s+Tech)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Consumer\s+Goods:\s+Non-Durable|Consumer\s+Goods)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Transportation:\s+Cargo|Transportation)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Beverage,\s+Food\s+&\s+Tobacco|Food\s+&\s+Beverage)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Chemicals,\s+Plastics\s+&\s+Rubber|Chemicals)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Capital\s+Equipment|Equipment)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(FIRE:\s+Finance|FIRE:\s+Insurance|Finance|Insurance)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
            r'^(Wholesale|Retail|Automotive|Metals\s+&\s+Mining|Construction\s+&\s+Building|Diversified\s+Financial\s+Services)\s+(.+?)(?:\s+First\s+Lien|\s+Second\s+Lien|\s+Preferred|\s+Common|\s+Equity|\s+Debt|$)',
        ]
        
        for pattern in industry_patterns:
            match = re.match(pattern, cleaned, re.IGNORECASE)
            if match:
                industry = match.group(1).strip()
                company_name = match.group(2).strip()
                break
        
        # Extract investment type patterns - search in the full cleaned identifier
        inv_type_patterns = [
            (r'\s+First\s+Lien\s+Senior\s+Secured\s+Loan', 'First Lien Debt'),
            (r'\s+First\s+Lien', 'First Lien Debt'),
            (r'\s+Second\s+Lien', 'Second Lien Debt'),
            (r'\s+Subordinated\s+Debt', 'Subordinated Debt'),
            (r'\s+Preferred\s+Equity', 'Preferred Equity'),
            (r'\s+Preferred\s+Stock', 'Preferred Equity'),
            (r'\s+Common\s+Equity', 'Common Equity'),
            (r'\s+Common\s+Stock', 'Common Equity'),
            (r'\s+Equity\s+Interest', 'Equity'),
            (r'\s+Warrant', 'Warrant'),
        ]
        
        inv_type = 'Unknown'
        inv_type_match = None
        
        # Find the first investment type pattern in the cleaned identifier
        for pattern, inv_type_name in inv_type_patterns:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                inv_type_match = match
                inv_type = inv_type_name
                break
        
        # Extract company name - everything before the investment type
        if inv_type_match:
            company_name = cleaned[:inv_type_match.start()].strip()
            # If we found an industry earlier, remove it from company_name
            if industry != 'Unknown' and company_name.startswith(industry):
                company_name = company_name[len(industry):].strip()
        else:
            # No investment type found - might be pure equity or the identifier is just the company name
            # Check if there are other indicators that suggest it's not just a company name
            if not any(x in cleaned.lower() for x in ['loan', 'debt', 'equity', 'stock', 'warrant', 'revolver', 'delayed draw', 'maturity date']):
                # Likely just a company name (pure equity investment)
                inv_type = 'Equity'
        
        # Clean company name - remove trailing separators and extra whitespace
        company_name = re.sub(r'[\u2013\u2014\-–—]\s*$', '', company_name).strip()
        company_name = re.sub(r'\s+', ' ', company_name)
        
        # Extract rates and dates
        # SOFR Spread X.XX% Interest Rate Y.YY%
        sofr_match = re.search(r'SOFR\s+Spread\s+([\d\.]+)\s*%\s*Interest\s+Rate\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if sofr_match:
            res['reference_rate'] = 'SOFR'
            res['spread'] = f"{sofr_match.group(1)}%"
            res['interest_rate'] = f"{sofr_match.group(2)}%"
        
        # SONIA Spread
        sonia_match = re.search(r'SONIA\s+Spread\s+([\d\.]+)\s*%\s*Interest\s+Rate\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if sonia_match:
            res['reference_rate'] = 'SONIA'
            res['spread'] = f"{sonia_match.group(1)}%"
            res['interest_rate'] = f"{sonia_match.group(2)}%"
        
        # EURIBOR Spread
        euribor_match = re.search(r'EURIBOR\s+Spread\s+([\d\.]+)\s*%\s*(?:PIK\s+)?Interest\s+Rate\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if euribor_match:
            res['reference_rate'] = 'EURIBOR'
            res['spread'] = f"{euribor_match.group(1)}%"
            res['interest_rate'] = f"{euribor_match.group(2)}%"
        
        # PIK rate
        pik_match = re.search(r'\(incl\.\s*([\d\.]+)\s*%\s*PIK\)', identifier, re.IGNORECASE)
        if pik_match:
            res['pik_rate'] = f"{pik_match.group(1)}%"
        
        # Maturity date
        maturity_match = re.search(r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})', identifier, re.IGNORECASE)
        if maturity_match:
            res['maturity_date'] = maturity_match.group(1)
        
        res['company_name'] = company_name if company_name else 'Unknown'
        res['industry'] = industry
        res['investment_type'] = inv_type
        
        return res
    
    def _industry_member_to_name(self, member: str) -> Optional[str]:
        """Convert XBRL industry member to readable name."""
        if not member:
            return None
        member = re.sub(r'^[^:]+:', '', member)
        return member.replace('_', ' ').title()
    
    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates = [c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None
    
    def _build_industry_index(self, content: str) -> Dict[str, str]:
        """Build index of industry by instant date."""
        res = {}
        return res
    
    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        """Extract XBRL facts grouped by context ID."""
        facts = defaultdict(list)
        
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept = match.group(1)
            cref = match.group(2)
            unit_ref = match.group(3)
            val = match.group(4)
            if val and cref:
                fact_entry = {'concept': concept, 'value': val.strip()}
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match:
                        fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
        
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:unitRef="([^"]*)")?[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1)
            cref = m.group(2)
            unit_ref = m.group(3)
            html = m.group(5)
            if not cref:
                continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                fact_entry = {'concept': name, 'value': txt}
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match:
                        fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
        
        return dict(facts)
    
    def _build_investment(self, ctx: Dict, facts: List[Dict]) -> Optional[BCSFInvestment]:
        """Build investment from context and facts."""
        if ctx.get('company_name') == 'Unknown':
            return None
        
        def _percent(v: str) -> str:
            try:
                val = float(str(v).replace(',', '').replace('%', ''))
                # If value is already a percentage (0-1 range), convert to percentage string
                if val < 1:
                    return f"{val * 100:.2f}%"
                else:
                    return f"{val:.2f}%"
            except:
                return str(v) if v else None
        
        inv = BCSFInvestment(
            company_name=ctx.get('company_name', 'Unknown'),
            investment_type=ctx.get('investment_type', 'Unknown'),
            industry=ctx.get('industry', 'Unknown'),
            context_ref=ctx.get('id'),
            reference_rate=ctx.get('reference_rate'),
            spread=ctx.get('spread'),
            floor_rate=ctx.get('floor_rate'),
            interest_rate=ctx.get('interest_rate'),
            maturity_date=ctx.get('maturity_date'),
            pik_rate=ctx.get('pik_rate')
        )
        
        # Process facts - extract ALL available fields
        for f in facts:
            c = f.get('concept', '')
            v = f.get('value', '')
            if not v:
                continue
            v_clean = v.replace(',', '').strip()
            cl = c.lower()
            
            # Principal amount
            if any(k in cl for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal', 'debtinstrumentprincipalamount']):
                try:
                    inv.principal_amount = float(v_clean)
                except:
                    pass
                continue
            
            # Cost
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl or 'costbasisofinvestments' in cl:
                try:
                    inv.cost = float(v_clean)
                except:
                    pass
                continue
            
            # Fair value
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl or 'fairvalueofinvestments' in cl:
                try:
                    inv.fair_value = float(v_clean)
                except:
                    pass
                continue
            
            # Maturity date
            if 'maturitydate' in cl or ('maturity' in cl and 'date' in cl):
                inv.maturity_date = v.strip()
                continue
            
            # Acquisition date
            if 'acquisitiondate' in cl or 'investmentdate' in cl:
                inv.acquisition_date = v.strip()
                continue
            
            # Interest rate
            if 'interestrate' in cl and 'floor' not in cl:
                inv.interest_rate = _percent(v_clean)
                continue
            
            # Reference rate (from variable interest rate type)
            if 'variableinterestratetype' in cl or ('reference' in cl and 'rate' in cl):
                if 'sofr' in cl or 'sofr' in v.lower():
                    inv.reference_rate = 'SOFR'
                elif 'libor' in cl or 'libor' in v.lower():
                    inv.reference_rate = 'LIBOR'
                elif 'prime' in cl or 'prime' in v.lower():
                    inv.reference_rate = 'PRIME'
                elif 'sonia' in cl or 'sonia' in v.lower():
                    inv.reference_rate = 'SONIA'
                elif 'euribor' in cl or 'euribor' in v.lower():
                    inv.reference_rate = 'EURIBOR'
                elif v and not v.startswith('http'):
                    inv.reference_rate = v.strip()
                continue
            
            # Spread
            if 'spread' in cl or ('basis' in cl and 'spread' in cl):
                inv.spread = _percent(v_clean)
                continue
            
            # Floor rate
            if 'floor' in cl and 'rate' in cl:
                inv.floor_rate = _percent(v_clean)
                continue
            
            # PIK rate
            if 'pik' in cl and 'rate' in cl:
                inv.pik_rate = _percent(v_clean)
                continue
        
        # Skip if no meaningful financial data
        if not inv.principal_amount and not inv.cost and not inv.fair_value:
            return None
        
        return inv


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = BCSFCustomExtractor()
    try:
        result = extractor.extract_from_ticker("BCSF")
        print(f"\n✓ Successfully extracted {result.get('total_investments', 0)} investments")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
