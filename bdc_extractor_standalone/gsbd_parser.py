#!/usr/bin/env python3
"""
GSBD (Goldman Sachs BDC Inc) Investment Extractor
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
class GSBDInvestment:
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


class GSBDExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "GSBD"), year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
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
        return self.extract_from_url(txt_url, "Goldman_Sachs_BDC_Inc", cik)

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
        investments: List[GSBDInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # HTML fallback for missing optional fields (acquisition_date, maturity_date, interest_rate)
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
        out_file = os.path.join(out_dir, 'GSBD_Goldman_Sachs_BDC_Inc_investments.csv')
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
            'investments': investment_dicts,  # Add investments list for historical extractor
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
                'business_description': parsed.get('business_description'),
                'investment_type': parsed['investment_type'],
                'maturity_date': parsed.get('maturity_date'),
                'acquisition_date': parsed.get('acquisition_date'),
                'pik_rate': parsed.get('pik_rate'),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
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
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # GSBD format: "Investment Debt Investments - X% [Country] - Y% [Investment Type] - Z% [Company Name] (dba/fka) Industry [Industry] Interest Rate ..."
        # Or: "Investment Equity Securities - X% [Country] - Y% Common Stock - Z% [Company Name] Industry [Industry] Initial Acquisition Date ..."
        
        # Extract dates first
        maturity_match = re.search(r'Maturity\s+(\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            date_str = maturity_match.group(1)
            # Normalize 2-digit year to 4-digit
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        acq_match = re.search(r'Initial\s+Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if acq_match:
            date_str = acq_match.group(1)
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['acquisition_date'] = date_str
        
        # Extract investment type
        if '1st Lien/Senior Secured Debt' in ident_clean or '1st Lien' in ident_clean:
            if 'Unitranche' in ident_clean or 'Last-Out Unitranche' in ident_clean:
                res['investment_type'] = '1st Lien/Last-Out Unitranche'
            else:
                res['investment_type'] = '1st Lien/Senior Secured Debt'
        elif 'Common Stock' in ident_clean:
            res['investment_type'] = 'Common Stock'
        elif 'Preferred Stock' in ident_clean:
            res['investment_type'] = 'Preferred Stock'
        elif '2nd Lien' in ident_clean or 'Second Lien' in ident_clean:
            res['investment_type'] = 'Second Lien Secured Debt'
        
        # Extract industry - pattern: "Industry [Industry Name]"
        industry_match = re.search(r'Industry\s+([^I]+?)(?:\s+Interest\s+Rate|\s+Reference\s+Rate|\s+Initial\s+Acquisition|\s+Maturity|$)', ident_clean, re.IGNORECASE)
        if industry_match:
            industry_raw = industry_match.group(1).strip()
            # Clean up - remove trailing descriptors and rate info
            industry_raw = re.sub(r'\s+Interest\s+Rate.*$', '', industry_raw, flags=re.IGNORECASE)
            industry_raw = industry_raw.rstrip('.,').strip()
            if industry_raw and len(industry_raw) > 2:
                res['industry'] = industry_raw
        
        # Extract company name - find entity name (LLC, Inc., Corp, etc.)
        # Remove prefix: "Investment Debt Investments - X% [Country] - Y% [Investment Type] - Z%"
        ident_for_company = re.sub(r'^Investment\s+(?:Debt|Equity)\s+Investments?\s+-[^-]+-[^-]+-', '', ident_clean, flags=re.IGNORECASE)
        ident_for_company = re.sub(r'^\d+\.\d+%\s+', '', ident_for_company)  # Remove leading percentage if still there
        
        # Also remove country and percentage prefixes that might remain
        ident_for_company = re.sub(r'^(?:United\s+States|Canada)\s*-[^-]+-[^-]+-', '', ident_for_company, flags=re.IGNORECASE)
        ident_for_company = re.sub(r'^\d+\.\d+%\s+(?:1st\s+Lien|Senior\s+Secured|Debt|Common\s+Stock)\s*-[^-]+-', '', ident_for_company, flags=re.IGNORECASE)
        
        # Find entity pattern - company name comes before "Industry"
        # Pattern: [Company Name] (optional dba/fka) Industry
        industry_pos = ident_for_company.upper().find('INDUSTRY')
        if industry_pos > 0:
            company_text = ident_for_company[:industry_pos].strip()
            # Remove trailing investment type mentions
            company_text = re.sub(r'\s+(?:1st\s+Lien|Senior\s+Secured|Debt|Common\s+Stock)[^I]*$', '', company_text, flags=re.IGNORECASE)
            company_text = company_text.strip()
            
            # Find entity name with type
            entity_pattern = r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co)(?:\s|$|,|\)|Industry)'
            entity_match = re.search(entity_pattern, company_text, re.IGNORECASE)
            if entity_match:
                entity_name = entity_match.group(1).strip().rstrip(',')
                # Find entity type - it might be in the match or right after
                entity_full_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co)', company_text, re.IGNORECASE)
                if entity_full_match:
                    entity_name = entity_full_match.group(1).strip().rstrip(',')
                    entity_type = entity_full_match.group(2)
                else:
                    after_entity = company_text[entity_match.end():entity_match.end()+20]
                    entity_type_match = re.search(r'\b(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co)\b', after_entity, re.IGNORECASE)
                    entity_type = entity_type_match.group(0) if entity_type_match else ""
                
                # Check for dba/fka in the company_text (before or after entity)
                dba_match = re.search(r'\(dba\s+([^)]+)\)', company_text, re.IGNORECASE)
                fka_match = re.search(r'\(fka\s+([^)]+)\)', company_text, re.IGNORECASE)
                
                company_full = f"{entity_name} {entity_type}".strip()
                if dba_match:
                    company_full = f"{company_full} (dba {dba_match.group(1)})"
                elif fka_match:
                    company_full = f"{company_full} (fka {fka_match.group(1)})"
                
                res['company_name'] = self._strip_footnote_refs(company_full)
            else:
                # Fallback: try to extract company name without clear entity type
                # Look for capitalized words before "Industry"
                company_words = [w for w in company_text.split() if w and w[0].isupper() and not w.endswith('%')]
                if len(company_words) >= 2:
                    # Remove common prefixes and take meaningful name parts
                    filtered_words = []
                    skip_next = False
                    for i, word in enumerate(company_words):
                        if skip_next:
                            skip_next = False
                            continue
                        if word.lower() in ['buyer', 'acquiror', 'purchaser', 'parent', 'holdings', 'investor', 'states', 'united']:
                            if word.lower() == 'states' and i > 0 and company_words[i-1].lower() == 'united':
                                continue
                            if i + 1 < len(company_words):
                                skip_next = True
                            continue
                        if word.endswith('%') or word.replace('.', '').isdigit():
                            continue
                        filtered_words.append(word)
                    
                    if filtered_words:
                        potential_name = ' '.join(filtered_words[:5])  # Take up to 5 words
                        if potential_name and len(potential_name) > 3:
                            res['company_name'] = self._strip_footnote_refs(potential_name)
        
        # Extract rates and spreads
        # Pattern: "Reference Rate and Spread S + 5.25%" or "Reference Rate and Spread 3.00% PIK"
        ref_spread_match = re.search(r'Reference\s+Rate\s+and\s+Spread\s+([SPFC])\s*\+\s*([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            rate_letter = ref_spread_match.group(1).upper()
            spread_val = ref_spread_match.group(2)
            if rate_letter == 'S':
                res['reference_rate'] = 'SOFR'
            elif rate_letter == 'P':
                res['reference_rate'] = 'PRIME'
            elif rate_letter == 'F':
                res['reference_rate'] = 'FED FUNDS'
            elif rate_letter == 'C':
                res['reference_rate'] = 'CDOR'  # Canadian Dollar Offered Rate
            res['spread'] = self._percent(spread_val)
        
        # Extract PIK rate - can be in "Reference Rate and Spread X.XX% PIK" or "(Incl. X.XX% PIK)"
        pik_match = re.search(r'(?:Reference\s+Rate\s+and\s+Spread|Incl\.)\s+([\d\.]+)\s*%\s*PIK', ident_clean, re.IGNORECASE)
        if pik_match:
            pik_val = pik_match.group(1)
            try:
                if float(pik_val) > 0:
                    res['pik_rate'] = self._percent(pik_val)
            except:
                pass
        
        # Extract interest rate
        interest_rate_match = re.search(r'Interest\s+Rate\s+([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if interest_rate_match:
            res['interest_rate'] = self._percent(interest_rate_match.group(1))
        
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        # Extract standard XBRL facts and also capture unitRef for currency
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
            dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[GSBDInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = GSBDInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
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
                inv.spread = self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v); continue
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
        # Fill missing fields from parsed identifier tokens
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
        
        # Extract shares/units and currency from facts
        for f in facts:
            c = f['concept']; v = f['value']; cl = c.lower()
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val = v.replace(',', '').strip()
                    float(shares_val)  # Validate
                    inv.shares_units = shares_val
                except: pass
            if 'currency' in f:
                inv.currency = f.get('currency')
        
        # Extract commitment_limit and undrawn_commitment for revolvers
        if 'revolving' in inv.investment_type.lower() or 'revolver' in inv.investment_type.lower():
            if inv.fair_value and not inv.principal_amount:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value
            elif inv.principal_amount and inv.fair_value:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value - inv.principal_amount if inv.fair_value > inv.principal_amount else 0
        
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

    def _extract_html_fallback(self, filing_url: str, investments: List[GSBDInvestment]) -> Optional[Dict[str, Dict]]:
        """Extract optional fields from HTML as fallback when XBRL doesn't have them."""
        try:
            from flexible_table_parser import FlexibleTableParser
            
            # Get HTML URL from index - construct index URL from .txt URL
            match = re.search(r'/edgar/data/(\d+)/(\d+)/([^/]+)\.txt', filing_url)
            if not match:
                logger.debug("Could not parse filing URL for HTML fallback")
                return None
            
            cik = match.group(1)
            accession_no_hyphens = match.group(2)
            filename_base = match.group(3).replace('.txt', '')
            # Construct index URL: replace the .txt filename with -index.html
            index_url = filing_url.replace(f"{filename_base}.txt", f"{filename_base}-index.html")
            
            # Get HTML document from index
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
            
            # Create lookup by company_name (primary) and investment_type (secondary)
            html_lookup_by_name = {}
            html_lookup_by_name_type = {}
            for html_inv in html_investments:
                company_name = html_inv.get('company_name', '').strip().lower()
                investment_type = html_inv.get('investment_type', '').strip().lower()
                
                if company_name:
                    # Primary lookup: by company name only
                    if company_name not in html_lookup_by_name:
                        html_lookup_by_name[company_name] = html_inv
                    
                    # Secondary lookup: by company name + investment type
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
    
    def _merge_html_data(self, investments: List[GSBDInvestment], html_data: Dict[str, Dict]):
        """Merge HTML-extracted optional fields into XBRL investments."""
        html_by_name = html_data.get('by_name', {})
        html_by_name_type = html_data.get('by_name_type', {})
        
        # Create normalized lookup for fuzzy matching
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
            
            # Strategy 1: Try exact match first (company_name + investment_type)
            key = (company_name_lower, investment_type_lower)
            html_inv = html_by_name_type.get(key)
            
            # Strategy 2: Fallback to company name only
            if not html_inv:
                html_inv = html_by_name.get(company_name_lower)
            
            # Strategy 3: Try normalized matching
            if not html_inv:
                normalized = self._normalize_company_name(inv.company_name)
                html_inv = html_by_normalized.get(normalized)
            
            # Strategy 4: Fuzzy matching (last resort)
            if not html_inv:
                for html_name, html_inv_candidate in html_by_name.items():
                    if self._fuzzy_match_company_names(inv.company_name, html_name, threshold=0.8):
                        html_inv = html_inv_candidate
                        break
            
            if html_inv:
                merged = False
                # Only fill in missing fields
                if not inv.acquisition_date and html_inv.get('acquisition_date'):
                    inv.acquisition_date = html_inv['acquisition_date']
                    merged = True
                if not inv.maturity_date and html_inv.get('maturity_date'):
                    inv.maturity_date = html_inv['maturity_date']
                    merged = True
                if not inv.interest_rate and html_inv.get('interest_rate'):
                    inv.interest_rate = html_inv['interest_rate']
                    merged = True
                if merged:
                    merged_count += 1
        
        if merged_count > 0:
            logger.info(f"HTML fallback: Merged data into {merged_count} investments")


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=GSBDExtractor()
    try:
        res=ex.extract_from_ticker('GSBD')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()

