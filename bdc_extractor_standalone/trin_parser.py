#!/usr/bin/env python3
"""
TRIN (Trinity Capital Inc) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filter; de-dup; industry enrichment.
RECREATED with identifier parsing improvements and debt detection.
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass
import os
import csv
import requests
from bs4 import BeautifulSoup

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class TRINInvestment:
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


class TRINExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "TRIN", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        # Prefer HTML parsing first
        documents = self.sec_client.get_documents_from_index(index_url)
        def is_primary_html(doc) -> bool:
            name = (doc.filename or '').lower()
            return (
                name.endswith('.htm') and
                (('10-q' in name) or ('10k' in name) or ('10-k' in name) or ('form10q' in name) or ('form10k' in name) or ('_10q' in name) or ('10q.htm' in name)) and
                not name.startswith('ex') and 'exhibit' not in name
            )
        main_html = next((d for d in documents if is_primary_html(d)), None)
        if not main_html:
            main_html = next((d for d in documents if (d.filename or '').lower().endswith('.htm') and not (d.filename or '').lower().startswith('ex')), None)
        if main_html:
            logger.info(f"Found main HTML: {main_html.url}")
            return self.extract_from_html_url(main_html.url, "Trinity Capital Inc", cik)
        # Fallback to XBRL txt
        acc = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not acc:
            raise ValueError("Could not parse accession number")
        accession = acc.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Trinity_Capital_Inc", cik)

    def extract_from_html_url(self, html_url: str, company_name: str, cik: str) -> Dict:
        """Extract from HTML URL. For TRIN, XBRL is faster and more reliable, so prefer it."""
        logger.info(f"TRIN: Preferring XBRL extraction over HTML (faster and more reliable)")
        return self._fallback_to_xbrl(html_url, company_name, cik)

    def _fallback_to_xbrl(self, html_url: str, company_name: str, cik: str) -> Dict:
        m = re.search(r'/(\d{10}-\d{2}-\d{6})\.htm', html_url)
        if not m:
            m2 = re.search(r'/(\d{10})(\d{2})(\d{6})', html_url)
            if m2:
                accession = f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
            else:
                raise ValueError(f"Could not parse accession number from {html_url}")
        else:
            accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        logger.info(f"Falling back to XBRL: {txt_url}")
        return self.extract_from_url(txt_url, company_name, cik)

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
        investments: List[TRINInvestment] = []
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
        out_file = os.path.join(out_dir, 'TRIN_Trinity_Capital_Inc_investments.csv')
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
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
                'interest_rate': parsed.get('interest_rate'),
                'maturity_date': parsed.get('maturity_date'),
                'pik_rate': parsed.get('pik_rate'),
            })
        return contexts

    def _normalize_text(self, s: str) -> str:
        return ' '.join((s or '').split())
    
    def _clean_company_name(self, name: str) -> str:
        """Clean company name by removing industry prefixes."""
        if not name:
            return ""
        
        name = re.sub(r'^Total\s+', '', name, flags=re.IGNORECASE).strip()
        
        industry_prefixes = [
            r'^(Healthcare\s+Services?)\s+',
            r'^(Construction\s+Technology)\s+',
            r'^(Automation)\s+',
            r'^(Connectivity)\s+',
            r'^(Healthcare)\s+',
            r'^(Construction)\s+',
            r'^(Technology)\s+',
            r'^(Services)\s+',
        ]
        
        for pattern in industry_prefixes:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        name = ' '.join(name.split())
        return name.strip()

    def _is_invalid_company_name(self, name: str) -> bool:
        """Check if a company name is invalid (too generic, etc.)."""
        if not name or len(name) < 3:
            return True
        
        name_lower = name.lower()
        invalid_names = ['total', 'unknown', 'n/a', 'none', 'portfolio company', 'company']
        if name_lower in invalid_names:
            return True
        
        return False

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'reference_rate':None,'spread':None,'floor_rate':None,'interest_rate':None,
               'maturity_date':None,'pik_rate':None}
        if ',' in identifier:
            last = identifier.rfind(',')
            company = identifier[:last].strip()
            tail = identifier[last+1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        company = re.sub(r'\s+',' ', company).rstrip(',')
        
        # Extract maturity date from year patterns like "2028 Interest Rate" or "2031 Series Preferred"
        year_match = re.search(r'\b(20\d{2})\s+(?:Interest\s+Rate|Series\s+Preferred)', identifier, re.IGNORECASE)
        if year_match:
            year = year_match.group(1)
            # Default to end of year (December 31)
            res['maturity_date'] = f"{year}-12-31"
        
        # Extract interest rate: "Fixed interest rate 11.9%" or "Variable interest rate Prime + 6.0%"
        fixed_rate_match = re.search(r'Fixed\s+interest\s+rate\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if fixed_rate_match:
            res['interest_rate'] = self._percent(fixed_rate_match.group(1))
        
        # Extract PIK rate: "PIK Fixed Interest Rate 1.0%"
        pik_match = re.search(r'PIK\s+(?:Fixed\s+)?Interest\s+Rate\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if pik_match:
            res['pik_rate'] = self._percent(pik_match.group(1))
        
        # Extract rate information from the full identifier string
        rate_match = re.search(r'[Vv]ariable interest rate\s+(SOFR|Prime|LIBOR|Base Rate)(?:\s+(\d+)\s+Month\s+Term)?\s*\+\s*([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if not rate_match:
            rate_match = re.search(r'ariable interest rate\s+(SOFR|Prime|LIBOR|Base Rate)(?:\s+(\d+)\s+Month\s+Term)?\s*\+\s*([\d\.]+)\s*%', identifier, re.IGNORECASE)
        if rate_match:
            ref_base = rate_match.group(1).upper()
            term_months = rate_match.group(2)
            spread_val = rate_match.group(3)
            
            if ref_base == 'SOFR' and term_months:
                res['reference_rate'] = f"SOFR ({term_months}M)"
            elif ref_base == 'SOFR':
                res['reference_rate'] = "SOFR (1M)"
            else:
                res['reference_rate'] = ref_base
            
            res['spread'] = f"{spread_val}%"
            
            # Extract floor rate
            floor_match = re.search(r'Floor rate\s+([\d\.]+)\s*%', identifier, re.IGNORECASE)
            if floor_match:
                floor_val = floor_match.group(1)
                res['floor_rate'] = f"{floor_val}%"
                # For variable rates with floor, use floor rate as the interest rate
                if not res['interest_rate']:
                    res['interest_rate'] = f"{floor_val}%"
        
        # Clean up concatenated company names
        if 'Portfolio Company' in company or 'Type of Investment' in company:
            normalized = re.sub(r"\s+", " ", company)
            cut = normalized.lower().find('type of investment')
            if cut > 0:
                normalized = normalized[:cut]
            suffix = r"(LLC|L\.L\.C\.|Inc\.?|Corporation|Corp\.?|Ltd\.?|L\.P\.|LP|LLP|PLC|AG|S\.A\.|SA|N\.V\.|NV|GmbH|Holdings?|Holdco\.?|Company|Co\.?|Limited)"
            matches = list(re.finditer(r"([A-Z][A-Za-z0-9 &,'\-\.]{1,120}?)\s+" + suffix + r"\b", normalized))
            if matches:
                m = matches[-1]
                name_part = m.group(1).strip()
                ent_suffix = m.group(2)
                common_prefixes = [
                    'Portfolio Company', 'Debt Securities- United States', 'Warrant Investments- United States',
                    'Equity Investments- United States', 'Debt Securities-', 'Warrant Investments-',
                    'Equity Investments-', 'United States', 'Europe',
                    'Transportation Technology', 'Space Technology', 'Marketing, Media, and Entertainment',
                    'Finance and Insurance', 'Biotechnology', 'Medical Devices', 'Connectivity',
                    'Human Resource Technology', 'Green Technology', 'Consumer Products & Services',
                    'Supply Chain Technology', 'Healthcare Technology', 'Food and Agriculture Technologies',
                    'Real Estate Technology', 'SaaS', 'Industrial', 'Other', 'Defense Technologies',
                    'Diversified Financial Services', 'Education Technology', 'Services'
                ]
                changed = True
                while changed:
                    changed = False
                    lowered = name_part.lower()
                    for pref in common_prefixes:
                        pl = pref.lower()
                        if lowered.startswith(pl):
                            name_part = name_part[len(pref):].strip(" -")
                            changed = True
                            break
                company = f"{name_part} {ent_suffix}"
        
        # Clean company name - remove industry prefixes
        company = self._clean_company_name(company)
        
        # Validate company name
        if self._is_invalid_company_name(company):
            res['company_name'] = 'Unknown'
        else:
            res['company_name'] = company
        
        # Clean tail to extract investment type - remove all rate metadata
        preferred_match = re.search(r'Series\s+Preferred\s+Series\s+[A-Z0-9-]+', identifier, re.IGNORECASE)
        if preferred_match:
            res['investment_type'] = 'Preferred Equity'
        elif re.search(r'Common\s+Equity', identifier, re.IGNORECASE):
            res['investment_type'] = 'Common Equity'
        elif re.search(r'Warrants?', identifier, re.IGNORECASE):
            res['investment_type'] = 'Warrants'
        else:
            # For debt investments, try to extract from tail after cleaning
            cleaned_tail = tail
            cleaned_tail = re.sub(r'^\d{4}\s+Interest\s+Rate\s+', '', cleaned_tail, flags=re.IGNORECASE)
            cleaned_tail = re.sub(r'Fixed\s+interest\s+rate\s+[\d\.]+%\s*;?\s*', '', cleaned_tail, flags=re.IGNORECASE)
            cleaned_tail = re.sub(r'Variable\s+interest\s+rate\s+[^;]+;?\s*', '', cleaned_tail, flags=re.IGNORECASE)
            cleaned_tail = re.sub(r'Floor\s+rate\s+[\d\.]+%\s*\+?', '', cleaned_tail, flags=re.IGNORECASE)
            cleaned_tail = re.sub(r'PIK\s+(?:Fixed\s+)?Interest\s+Rate\s+[\d\.]+%\s*;?\s*', '', cleaned_tail, flags=re.IGNORECASE)
            cleaned_tail = re.sub(r'EOT\s+[\d\.]+%\s*', '', cleaned_tail, flags=re.IGNORECASE)
            cleaned_tail = re.sub(r'or\s+', '', cleaned_tail, flags=re.IGNORECASE)
            cleaned_tail = cleaned_tail.strip(' ;')
            
            patterns = [
                r'First\s+lien', r'Second\s+lien', r'Unitranche', r'Senior\s+secured',
                r'Secured\s+Debt', r'Unsecured\s+Debt', r'Preferred\s+Equity', r'Preferred\s+Stock',
                r'Common\s+Stock', r'Member\s+Units', r'Warrants?'
            ]
            it = None
            for p in patterns:
                mm = re.search(p, cleaned_tail, re.IGNORECASE)
                if mm:
                    it = mm.group(0)
                    if 'First lien' in it or 'First Lien' in it:
                        it = 'First Lien Debt'
                    elif 'Second lien' in it or 'Second Lien' in it:
                        it = 'Second Lien Debt'
                    elif 'Secured Debt' in it:
                        it = 'Secured Debt'
                    elif 'Unsecured Debt' in it:
                        it = 'Unsecured Debt'
                    elif 'Preferred' in it:
                        it = 'Preferred Equity'
                    elif 'Common' in it:
                        it = 'Common Equity'
                    break
            
            if not it and cleaned_tail:
                if cleaned_tail.lower().strip() in ['llc', 'inc.', 'inc', 'ltd.', 'ltd', 'corp.', 'corp', 'lp', 'llp']:
                    if res['company_name'] != 'Unknown':
                        res['company_name'] = f"{res['company_name']} {cleaned_tail}".strip()
                    it = 'Unknown'
                else:
                    if res['interest_rate'] or res['reference_rate']:
                        it = 'Debt'
                    else:
                        it = cleaned_tail if cleaned_tail else 'Unknown'
            
            res['investment_type'] = it if it else 'Unknown'
        
        # Post-process: If investment_type is still Unknown, check if it's debt based on indicators
        if res['investment_type'] == 'Unknown':
            has_debt_indicators = (
                res.get('interest_rate') is not None or
                res.get('reference_rate') is not None or
                res.get('spread') is not None or
                res.get('maturity_date') is not None or
                res.get('floor_rate') is not None
            )
            identifier_lower = identifier.lower()
            has_debt_keywords = any(keyword in identifier_lower for keyword in [
                'interest rate', 'fixed interest', 'variable interest', 'sofr', 'prime', 'libor',
                'maturity', 'floor rate', 'spread', 'debt', 'loan', 'note', 'lien'
            ])
            
            if has_debt_indicators or has_debt_keywords:
                res['investment_type'] = 'Debt'
        
        # Post-process: clean and validate company name one more time
        if res['company_name'] != 'Unknown':
            cleaned = self._clean_company_name(res['company_name'])
            if not self._is_invalid_company_name(cleaned):
                res['company_name'] = cleaned
            else:
                res['company_name'] = 'Unknown'
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[TRINInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = TRINInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id'],
            reference_rate=context.get('reference_rate'),
            spread=context.get('spread'),
            floor_rate=context.get('floor_rate')
        )
        # Set values from identifier parsing if available
        if context.get('interest_rate'):
            inv.interest_rate = context['interest_rate']
        if context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
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
            # Maturity date
            if 'maturitydate' in cl or ('maturity' in cl and 'date' in cl) or cl=='derived:maturitydate':
                inv.maturity_date = v.strip()
                continue
            
            # Acquisition date
            if 'acquisitiondate' in cl or 'investmentdate' in cl or cl=='derived:acquisitiondate':
                inv.acquisition_date = v.strip()
                continue
            
            # Reference rate (check BEFORE interest rate to avoid confusion)
            if cl=='derived:referenceratetoken' or 'variableinterestratetype' in cl or ('reference' in cl and 'rate' in cl):
                if not inv.reference_rate:
                    if 'sofr' in cl or 'sofr' in v.lower():
                        inv.reference_rate = 'SOFR'
                    elif 'libor' in cl or 'libor' in v.lower():
                        inv.reference_rate = 'LIBOR'
                    elif 'prime' in cl or 'prime' in v.lower():
                        inv.reference_rate = 'PRIME'
                    elif v and not v.startswith('http'):
                        inv.reference_rate = v.upper().strip()
                continue
            
            # Interest rate (skip if it's a URL)
            if 'interestrate' in cl and 'floor' not in cl:
                if v and not v.startswith('http'):
                    inv.interest_rate = self._percent(v)
                continue
            
            # Spread
            if 'spread' in cl or ('basis' in cl and 'spread' in cl) or 'investmentbasisspreadvariablerate' in cl:
                inv.spread = self._percent(v)
                continue
            
            # Floor rate
            if 'floor' in cl and 'rate' in cl or cl=='derived:floorrate':
                inv.floor_rate = self._percent(v)
                continue
            
            # PIK rate
            if 'pik' in cl and 'rate' in cl or cl=='derived:pikrate':
                inv.pik_rate = self._percent(v)
                continue
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
        
        # Final check: If investment_type is still Unknown, detect if it's debt based on indicators
        if inv.investment_type == 'Unknown':
            has_debt_indicators = (
                inv.principal_amount is not None or
                inv.interest_rate is not None or
                inv.reference_rate is not None or
                inv.spread is not None or
                inv.maturity_date is not None or
                inv.floor_rate is not None
            )
            is_equity = inv.shares_units is not None and not has_debt_indicators
            
            if has_debt_indicators and not is_equity:
                inv.investment_type = 'Debt'
        
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
    ex=TRINExtractor()
    try:
        res=ex.extract_from_ticker('TRIN')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()
