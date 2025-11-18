#!/usr/bin/env python3
"""
FDUS (Fidus Investment Corp) Investment Extractor
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
class FDUSInvestment:
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


class FDUSExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "FDUS", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Fidus_Investment_Corp", cik)

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
        investments: List[FDUSInvestment] = []
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
        out_file = os.path.join(out_dir, 'FDUS_Fidus_Investment_Corp_investments.csv')
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
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same if same else 'Unknown')
            res.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': parsed.get('acquisition_date') or (sd.group(1) if sd else None),
                'end_date': parsed.get('maturity_date') or (ed.group(1) if ed else None),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
                'interest_rate': parsed.get('interest_rate'),
                'maturity_date': parsed.get('maturity_date'),
                'pik_rate': parsed.get('pik_rate'),
                'acquisition_date': parsed.get('acquisition_date'),
            })
        return res
    
    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        """Parse investment identifier to extract company name, industry, and investment type."""
        res = {'company_name': 'Unknown', 'industry': 'Unknown', 'investment_type': 'Unknown',
               'reference_rate': None, 'spread': None, 'floor_rate': None, 'interest_rate': None,
               'maturity_date': None, 'pik_rate': None, 'acquisition_date': None}
        
        if not identifier:
            return res
        
        # Decode HTML entities
        identifier = identifier.replace('&amp;', '&')
        
        # Remove common prefixes
        cleaned = identifier
        prefixes = [
            r'^Non-control/Non-affiliate\s+Investments\s+',
            r'^Non-control/Non-affiliate\s+Investmnts\s+',
            r'^Affiliate\s+Investments\s+',
        ]
        for prefix in prefixes:
            cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
        
        # Pattern: "[Company Name] [Industry] [Investment Type] ..."
        # Or: "[Company Name] (dba [Name]) [Industry] [Investment Type] ..."
        
        # Extract company name - usually first part before industry
        # Look for patterns like "Company Name, LLC" or "Company Name (dba Name)"
        company_match = re.match(r'^([A-Z][A-Za-z0-9\s,&\.\(\)\-]+?)(?:\s+(?:Healthcare\s+Services?|Business\s+Services?|Building\s+Products|Information\s+Technology|Transportation|Environmental|Promotional|Specialty|Aerospace|Defense|Manufacturing|Component|Industrial|Utilities|Retail|Capital|Equipment|Software|Services|Technology|Finance|Insurance|Real\s+Estate|Consumer|Products|Food|Agriculture|Energy|Media|Entertainment|Education|Construction|Wholesale|Automotive|Metals|Mining|Chemicals|Plastics|Rubber|Textiles|Apparel|Leisure|Hotels|Restaurants|Beverage|Tobacco|Pharmaceuticals|Biotechnology|Medical|Devices|Healthcare|Technology|Green|Space|Transportation|Connectivity|Marketing|Media|Entertainment|Finance|Insurance|Human|Resource|Consumer|Products|Services|Supply|Chain|Real|Estate|SaaS|Industrial|Other|Defense|Diversified|Financial|Education|Services))', cleaned, re.IGNORECASE)
        
        if company_match:
            company_name = company_match.group(1).strip()
            # Remove trailing entity suffixes that might be part of the match
            company_name = re.sub(r'\s+(LLC|L\.L\.C\.|Inc\.?|Corporation|Corp\.?|Ltd\.?|L\.P\.|LP|LLP|PLC|AG|S\.A\.|SA|N\.V\.|NV|GmbH|Holdings?|Holdco\.?|Company|Co\.?|Limited)\s*$', '', company_name, flags=re.IGNORECASE)
            res['company_name'] = company_name
        
        # Extract industry
        industry_patterns = [
            r'\b(Healthcare\s+Services?|Business\s+Services?|Building\s+Products\s+Manufacturing|Information\s+Technology\s+Services?|Transportation\s+services?|Environmental\s+Industries|Promotional\s+products|Specialty\s+Distribution|Aerospace\s+&\s+Defense\s+Manufacturing|Component\s+Manufacturing|Industrial\s+Cleaning\s+&\s+Coatings|Utilities:\s+Services?|Retail|Capital\s+Equipment|Software|Services|Technology|Finance|Insurance|Real\s+Estate|Consumer|Products|Food|Agriculture|Energy|Media|Entertainment|Education|Construction|Wholesale|Automotive|Metals|Mining|Chemicals|Plastics|Rubber|Textiles|Apparel|Leisure|Hotels|Restaurants|Beverage|Tobacco|Pharmaceuticals|Biotechnology|Medical|Devices|Healthcare|Technology|Green|Space|Transportation|Connectivity|Marketing|Media|Entertainment|Finance|Insurance|Human|Resource|Consumer|Products|Services|Supply|Chain|Real|Estate|SaaS|Industrial|Other|Defense|Diversified|Financial|Education|Services)\b',
        ]
        
        for pattern in industry_patterns:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                res['industry'] = match.group(1).strip()
                break
        
        # Extract investment type
        if 'First Lien Debt' in identifier or 'First Lien' in identifier:
            res['investment_type'] = 'First Lien Debt'
        elif 'Second Lien Debt' in identifier or 'Second Lien' in identifier:
            res['investment_type'] = 'Second Lien Debt'
        elif 'Subordinated Debt' in identifier:
            res['investment_type'] = 'Subordinated Debt'
        elif 'Preferred Equity' in identifier or 'Preferred Stock' in identifier:
            res['investment_type'] = 'Preferred Equity'
        elif 'Common Equity' in identifier or 'Common Stock' in identifier:
            res['investment_type'] = 'Common Equity'
        elif 'Warrant' in identifier:
            res['investment_type'] = 'Warrant'
        
        # Extract rates
        # Variable Index Spread (S + X.XX%) Variable Index Floor (Y.YY%) Rate Cash Z.ZZ% Rate PIK A.AA%
        var_match = re.search(r'Variable\s+Index\s+Spread\s+\(S\s*\+\s*([\d\.]+)\s*%\)\s+Variable\s+Index\s+Floor\s+\(([\d\.]+)\s*%\)\s+Rate\s+Cash\s+([\d\.]+)\s*%\s+Rate\s+PIK\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if var_match:
            res['reference_rate'] = 'SOFR'  # S typically means SOFR
            res['spread'] = f"{var_match.group(1)}%"
            res['floor_rate'] = f"{var_match.group(2)}%"
            res['interest_rate'] = f"{var_match.group(3)}%"
            res['pik_rate'] = f"{var_match.group(4)}%"
        else:
            # Try simpler patterns
            cash_match = re.search(r'Rate\s+Cash\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
            if cash_match:
                res['interest_rate'] = f"{cash_match.group(1)}%"
            
            pik_match = re.search(r'Rate\s+PIK\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
            if pik_match:
                res['pik_rate'] = f"{pik_match.group(1)}%"
        
        # Extract dates
        # Investment date MM/DD/YYYY
        acq_match = re.search(r'Investment\s+date\s+(\d{1,2}/\d{1,2}/\d{4})', identifier, re.IGNORECASE)
        if acq_match:
            res['acquisition_date'] = acq_match.group(1)
        
        # Maturity MM/DD/YYYY or Maturity Date MM/DD/YYYY
        mat_match = re.search(r'Maturity(?:\s+Date)?\s+(\d{1,2}/\d{1,2}/\d{4})', identifier, re.IGNORECASE)
        if mat_match:
            res['maturity_date'] = mat_match.group(1)
        
        return res
    
    def _industry_member_to_name(self, member: str) -> Optional[str]:
        """Convert XBRL industry member to readable name."""
        if not member:
            return None
        # Remove namespace prefixes
        member = re.sub(r'^[^:]+:', '', member)
        # Convert to title case
        return member.replace('_', ' ').title()
    
    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates = [c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None
    
    def _build_industry_index(self, content: str) -> Dict[str, str]:
        """Build index of industry by instant date."""
        res = {}
        # Look for industry facts by instant
        # This is a simplified version - can be enhanced
        return res
    
    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        """Extract XBRL facts grouped by context ID."""
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
        
        # Also extract ix:nonFraction elements (common in XBRL)
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
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match:
                        fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
        
        # Map concepts to our fact names
        concept_mapping = {
            'principal_amount': [
                'us-gaap:DebtInstrumentPrincipalAmount',
                'us-gaap:DebtInstrumentCarryingAmount',
                'us-gaap:FinancialInstrumentFaceAmount',
            ],
            'cost': [
                'us-gaap:CostBasisOfInvestments',
                'us-gaap:CostOfInvestment',
                'us-gaap:InvestmentCost',
            ],
            'fair_value': [
                'us-gaap:FairValueOfInvestments',
                'us-gaap:FairValue',
                'us-gaap:InvestmentsFairValueDisclosure',
            ],
            'maturity_date': [
                'us-gaap:DebtInstrumentMaturityDate',
                'us-gaap:MaturityDate',
            ],
            'interest_rate': [
                'us-gaap:DebtInstrumentInterestRateStatedPercentage',
                'us-gaap:InterestRateStatedPercentage',
            ],
        }
        
        # Return facts with concept names (don't map to fact names, let _build_investment handle it)
        # This is more flexible and matches how GECC works
        return dict(facts)
    
    def _build_investment(self, ctx: Dict, facts: List[Dict]) -> Optional[FDUSInvestment]:
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
        
        inv = FDUSInvestment(
            company_name=ctx.get('company_name', 'Unknown'),
            investment_type=ctx.get('investment_type', 'Unknown'),
            industry=ctx.get('industry', 'Unknown'),
            context_ref=ctx.get('id'),
            acquisition_date=ctx.get('acquisition_date'),
            maturity_date=ctx.get('maturity_date'),
            reference_rate=ctx.get('reference_rate'),
            spread=ctx.get('spread'),
            floor_rate=ctx.get('floor_rate'),
            interest_rate=ctx.get('interest_rate'),
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

