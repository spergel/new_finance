#!/usr/bin/env python3
"""
PFLT (PennantPark Floating Rate Capital Ltd) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filter; de-dup; industry enrichment.
RECREATED with identifier parsing improvements.
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
    shares_units: Optional[str] = None
    percent_net_assets: Optional[str] = None
    currency: Optional[str] = None
    commitment_limit: Optional[float] = None
    undrawn_commitment: Optional[float] = None


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

        # HTML fallback for optional fields (dates, rates)
        html_data = self._extract_html_fallback(filing_url, investments)
        if html_data:
            self._merge_html_data(investments, html_data)

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
        # Convert investments to dict format
        investment_dicts = []
        for inv in investments:
            standardized_inv_type = standardize_investment_type(inv.investment_type)
            standardized_industry = standardize_industry(inv.industry)
            standardized_ref_rate = standardize_reference_rate(inv.reference_rate)
            investment_dicts.append({
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
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'investment_type': parsed['investment_type'],
                'interest_rate': parsed.get('interest_rate'),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'maturity_date': parsed.get('maturity_date'),
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
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'interest_rate':None,'reference_rate':None,'spread':None,'maturity_date':None}
        ident_clean = re.sub(r'\s+',' ', identifier).strip()
        
        # PFLT format examples:
        # "First Lien Secured Debt Issuer Name ARGANO LLC Maturity 9/13/2029 Industry Business Services Current Coupon 10.07% Basis Point Spread Above Index SOFR+575"
        # "Investments in Non-Controlled, Non-Affiliated Portfolio Companies First Lien Secured Debt Urology Management Holdings Inc. - Unfunded Term Loan Maturity 9/3/2026 Industry Healthcare Providers and Services"
        
        # Extract investment type
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
        
        # Extract interest rate: "Current Coupon X.XX%"
        coupon_match = re.search(r'Current\s+Coupon\s+([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if coupon_match:
            res['interest_rate'] = self._percent(coupon_match.group(1))
        
        # Extract reference rate and spread: "SOFR+575", "3M SOFR+ 636", etc.
        ref_spread_match = re.search(r'(SOFR|PRIME|LIBOR|EURIBOR|Base\s+Rate)(?:\s*\+\s*|\+)(\d+)', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            ref_rate = ref_spread_match.group(1).upper()
            spread_bps = ref_spread_match.group(2)
            res['reference_rate'] = ref_rate
            try:
                spread_val = float(spread_bps) / 100.0
                res['spread'] = f"{spread_val:.2f}%"
            except:
                res['spread'] = f"{spread_bps} bps"
        
        # Pattern 2: "3M SOFR+ 636" (with tenor prefix)
        tenor_ref_match = re.search(r'(\d+[MW])\s+(SOFR|PRIME|LIBOR|EURIBOR)(?:\s*\+\s*|\+)(\d+)', ident_clean, re.IGNORECASE)
        if tenor_ref_match and not res['reference_rate']:
            tenor = tenor_ref_match.group(1).upper()
            ref_rate = tenor_ref_match.group(2).upper()
            spread_bps = tenor_ref_match.group(3)
            res['reference_rate'] = f"{tenor} {ref_rate}"
            try:
                spread_val = float(spread_bps) / 100.0
                res['spread'] = f"{spread_val:.2f}%"
            except:
                res['spread'] = f"{spread_bps} bps"
        
        # Extract maturity date: "Maturity MM/DD/YYYY" or "Maturity MM/DD/YY"
        maturity_match = re.search(r'Maturity\s+(\d{1,2})/(\d{1,2})/(\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            month = maturity_match.group(1).zfill(2)
            day = maturity_match.group(2).zfill(2)
            year = maturity_match.group(3)
            if len(year) == 2:
                year_int = int(year)
                year = f"20{year}" if year_int <= 50 else f"19{year}"
            res['maturity_date'] = f"{year}-{month}-{day}"
        
        # Extract industry: look for "Industry [Industry Name]" pattern
        ind_match = re.search(r'Industry\s+(.+?)(?:\s+Current\s+Coupon|\s+Maturity|$)', ident_clean, re.IGNORECASE)
        if ind_match:
            industry_raw = ind_match.group(1).strip()
            industry_raw = industry_raw.rstrip('.,').strip()
            industry_raw = re.sub(r'\s+(Inc|LLC|Corp|Ltd|Company|Holdings)$', '', industry_raw, flags=re.IGNORECASE)
            industry_raw = industry_raw.replace('&amp;', '&')
            if industry_raw and len(industry_raw) > 2:
                res['industry'] = self._strip_footnote_refs(industry_raw)
        
        # Extract company name
        company_name = None
        
        # Pattern 1: "Issuer Name [Company] Maturity"
        issuer_match = re.search(r'Issuer\s+Name\s+([^M]+?)\s+Maturity', ident_clean, re.IGNORECASE)
        if issuer_match:
            company_name = issuer_match.group(1).strip()
        
        # Pattern 2a: Direct pattern starting with investment type
        if not company_name:
            direct_type_match = re.search(
                r'^(?:First\s+Lien\s+Secured\s+Debt|Second\s+Lien\s+Secured\s+Debt|Subordinate\s+Debt)\s+(.+?)(?:\s+-\s+Unfunded|\s+Maturity|\s+Industry|$)',
                ident_clean,
                re.IGNORECASE
            )
            if direct_type_match:
                company_name = direct_type_match.group(1).strip()
        
        # Pattern 2b: "Investments in Non-Controlled... [Investment Type] [Company]"
        if not company_name:
            pattern2_match = re.search(
                r'Investments\s+in\s+Non[^-]+Portfolio\s+Companies\s+(?:First\s+Lien\s+Secured\s+Debt|Second\s+Lien\s+Secured\s+Debt|Subordinate\s+Debt|Common\s+Equity/Warrants|Preferred\s+Equity|Preferred\s+Stock)\s+(.+?)(?:\s+Maturity|\s+Industry|\s+-|\s*$)',
                ident_clean,
                re.IGNORECASE
            )
            if pattern2_match:
                company_name = pattern2_match.group(1).strip()
            else:
                candidate = ident_clean
                candidate = re.sub(r'^Investments\s+in\s+Non[^P]*Portfolio\s+Companies\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^First\s+Lien\s+Secured\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Second\s+Lien\s+Secured\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Subordinate\s+Debt\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Common\s+Equity/Warrants\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Preferred\s+Equity\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^Preferred\s+Stock\s+', '', candidate, flags=re.IGNORECASE)
                
                maturity_pos = candidate.upper().find('MATURITY')
                industry_pos = candidate.upper().find('INDUSTRY')
                dash_pos = candidate.find(' - ')
                
                stop_positions = [pos for pos in [maturity_pos, industry_pos, dash_pos] if pos > 0]
                end_pos = min(stop_positions) if stop_positions else len(candidate)
                
                if end_pos > 0:
                    company_raw = candidate[:end_pos].strip()
                    company_raw = re.sub(r'\s+-\s+(Unfunded|Term\s+Loan|Revolver|Convertible\s+Notes).*$', '', company_raw, flags=re.IGNORECASE)
                    company_raw = company_raw.rstrip(' -').strip()
                    if company_raw and len(company_raw) > 2:
                        company_name = company_raw
        
        # Handle f/k/a cases
        if company_name:
            fka_match = re.search(r'([^(]+?)\s*\(f/k/a\s+([^)]+)\)', company_name, re.IGNORECASE)
            if fka_match:
                company_name = fka_match.group(1).strip()
        
        if company_name:
            # Final cleanup - remove all metadata
            company_name = re.sub(r'\s+\(f/k/a[^)]+\)', '', company_name, flags=re.IGNORECASE)
            company_name = self._strip_footnote_refs(company_name)
            company_name = re.sub(r'^Issuer\s+Name\s+', '', company_name, flags=re.IGNORECASE)
            company_name = re.sub(r'\s+-\s+(Unfunded|Term\s+Loan|Revolver|Convertible\s+Notes?|First-Out\s+Term\s+Loan).*$', '', company_name, flags=re.IGNORECASE)
            company_name = re.sub(r'\s+Maturity\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', company_name, flags=re.IGNORECASE)
            company_name = re.sub(r'\s+Industry\s+[^C]+?(?=\s+Current\s+Coupon|$)', '', company_name, flags=re.IGNORECASE)
            company_name = re.sub(r'\s+Current\s+Coupon\s+[\d\.]+%', '', company_name, flags=re.IGNORECASE)
            company_name = re.sub(r'\s+Basis\s+Point\s+Spread\s+Above\s+Index\s+[^$]+', '', company_name, flags=re.IGNORECASE)
            company_name = company_name.rstrip(' -.,').strip()
            company_name = company_name.replace('&amp;', '&')
            
            res['company_name'] = company_name
        
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
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
            name = m.group(1); cref = m.group(2); unit_ref = m.group(3); html = m.group(5)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                fact_entry = {'concept': name, 'value': txt}
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
            dates = []
            dates.extend(re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', window))
            dates.extend(re.findall(r'\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{1,2}/\d{4}\b', window))
            if dates:
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[PFLTInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = PFLTInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        # Set values from identifier parsing if available
        if context.get('interest_rate'):
            inv.interest_rate = context['interest_rate']
        if context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if context.get('spread'):
            inv.spread = context['spread']
        if context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
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
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val = v.strip().replace(',', '')
                    float(shares_val)
                    inv.shares_units = shares_val
                except: pass
                continue
            if 'currency' in f:
                inv.currency = f.get('currency')
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
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
    
    def _extract_html_fallback(self, filing_url: str, investments: List[PFLTInvestment]) -> Optional[Dict[str, Dict]]:
        """Extract HTML table data as fallback for missing optional fields."""
        try:
            from flexible_table_parser import FlexibleTableParser
            
            match = re.search(r'/edgar/data/(\d+)/(\d+)/([^/]+)\.txt', filing_url)
            if not match:
                logger.debug("Could not parse filing URL for HTML fallback")
                return None
            
            cik = match.group(1)
            accession_no_hyphens = match.group(2)
            filename_base = match.group(3).replace('.txt', '')
            index_url = filing_url.replace(f"{filename_base}.txt", f"{filename_base}-index.html")
            
            docs = self.sec_client.get_documents_from_index(index_url)
            main_doc = None
            for d in docs:
                fn = d.filename.lower() if d.filename else ''
                if fn.endswith('.htm') and 'index' not in fn:
                    main_doc = d
                    break
            
            if not main_doc:
                logger.debug(f"HTML fallback: No HTML document found in index")
                return None
            
            html_url = main_doc.url
            logger.info(f"HTML fallback: Using HTML URL: {html_url}")
            
            parser = FlexibleTableParser(user_agent=self.headers['User-Agent'])
            html_investments = parser.parse_html_filing(html_url)
            
            if not html_investments:
                logger.debug(f"HTML fallback: No investments extracted from {html_url}")
                return None
            
            logger.info(f"HTML fallback: Extracted {len(html_investments)} investments from HTML")
            
            html_lookup_by_name = {}
            html_lookup_by_name_type = {}
            for html_inv in html_investments:
                company_name = html_inv.get('company_name', '').strip().lower()
                investment_type = html_inv.get('investment_type', '').strip().lower()
                
                if company_name:
                    if company_name not in html_lookup_by_name:
                        html_lookup_by_name[company_name] = html_inv
                    key = (company_name, investment_type)
                    html_lookup_by_name_type[key] = html_inv
            
            return {
                'by_name': html_lookup_by_name,
                'by_name_type': html_lookup_by_name_type
            }
        except Exception as e:
            logger.debug(f"HTML fallback extraction failed: {e}")
            return None
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for better matching."""
        if not name:
            return ""
        name = name.lower().strip()
        name = re.sub(r'\s*(inc\.?|incorporated|corp\.?|corporation|ltd\.?|limited|llc\.?|lp\.?|l\.p\.?|l\.l\.c\.?)\s*$', '', name)
        name = re.sub(r'\s*\([^)]*\)\s*', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        name = re.sub(r'^(the\s+)', '', name)
        return name
    
    def _fuzzy_match_company_names(self, name1: str, name2: str, threshold: float = 0.8) -> bool:
        """Check if two company names are similar enough to match."""
        from difflib import SequenceMatcher
        norm1 = self._normalize_company_name(name1)
        norm2 = self._normalize_company_name(name2)
        if not norm1 or not norm2:
            return False
        if norm1 == norm2:
            return True
        if norm1 in norm2 or norm2 in norm1:
            return True
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        return similarity >= threshold
    
    def _merge_html_data(self, investments: List[PFLTInvestment], html_data: Dict[str, Dict]):
        """Merge HTML-extracted optional fields into XBRL investments."""
        html_by_name = html_data.get('by_name', {})
        html_by_name_type = html_data.get('by_name_type', {})
        
        html_by_normalized = {}
        for html_inv in html_by_name.values():
            company_name = html_inv.get('company_name', '').strip()
            if company_name:
                normalized = self._normalize_company_name(company_name)
                if normalized and normalized not in html_by_normalized:
                    html_by_normalized[normalized] = html_inv
        
        merged_count = 0
        for inv in investments:
            company_name_lower = inv.company_name.strip().lower()
            investment_type_lower = inv.investment_type.strip().lower()
            
            html_inv = None
            
            key = (company_name_lower, investment_type_lower)
            html_inv = html_by_name_type.get(key)
            
            if not html_inv:
                html_inv = html_by_name.get(company_name_lower)
            
            if not html_inv:
                normalized = self._normalize_company_name(inv.company_name)
                html_inv = html_by_normalized.get(normalized)
            
            if not html_inv:
                for html_name, html_inv_candidate in html_by_name.items():
                    if self._fuzzy_match_company_names(inv.company_name, html_name, threshold=0.8):
                        html_inv = html_inv_candidate
                        break
            
            if html_inv:
                merged = False
                is_debt = any(kw in inv.investment_type.lower() for kw in ['debt', 'loan', 'note', 'lien', 'secured', 'bond'])
                
                if not inv.acquisition_date and html_inv.get('acquisition_date'):
                    inv.acquisition_date = html_inv['acquisition_date']
                    merged = True
                
                if not inv.maturity_date and html_inv.get('maturity_date'):
                    inv.maturity_date = html_inv['maturity_date']
                    merged = True
                elif is_debt and not inv.maturity_date:
                    due_match = re.search(r'[Dd]ue\s+(\d{1,2})/(\d{2,4})', inv.investment_type)
                    if due_match:
                        month = due_match.group(1).zfill(2)
                        year_part = due_match.group(2)
                        if len(year_part) == 2:
                            year = f"20{year_part}"
                        else:
                            year = year_part
                        inv.maturity_date = f"{year}-{month}-01"
                        merged = True
                
                if not inv.interest_rate and html_inv.get('interest_rate'):
                    inv.interest_rate = html_inv['interest_rate']
                    merged = True
                if not inv.reference_rate and html_inv.get('reference_rate'):
                    inv.reference_rate = html_inv['reference_rate']
                    merged = True
                if not inv.spread and html_inv.get('spread'):
                    inv.spread = html_inv['spread']
                    merged = True
                if merged:
                    merged_count += 1
        
        if merged_count > 0:
            logger.info(f"HTML fallback: Merged data into {merged_count} investments")


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
