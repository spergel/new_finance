#!/usr/bin/env python3
"""
BCSF (Bain Capital Specialty Finance Inc) Investment Extractor
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


class BCSFExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def _strip_footnote_refs(self, text: Optional[str]) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)."""
        if not text:
            return ""
        cleaned = re.sub(r'(?:\s*\(\s*\d+\s*\))+', '', text)
        return re.sub(r'\s+', ' ', cleaned).strip()

    def extract_from_ticker(self, ticker: str = "BCSF") -> Dict:
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
        return self.extract_from_url(txt_url, "Bain_Capital_Specialty_Finance_Inc", cik)

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
            clean_ind = self._strip_footnote_refs(inv.industry)
            clean_type = self._strip_footnote_refs(inv.investment_type)
            ind_br[clean_ind] += 1
            type_br[clean_type] += 1

        out_dir = 'output'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'BCSF_Bain_Capital_Specialty_Finance_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
            ])
            writer.writeheader()
            for inv in investments:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(self._strip_footnote_refs(inv.investment_type))
                standardized_industry = standardize_industry(self._strip_footnote_refs(inv.industry))
                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)
                
                writer.writerow({
                    'company_name': self._strip_footnote_refs(inv.company_name),
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

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # BCSF format appears to be:
        # "[Spread]% Interest Rate [Rate]% Maturity Date [Date], [Industry] [Company Name] [Investment Type]..."
        # Or: "[Industry] [Company Name] [Investment Type]..."
        
        # Extract dates first
        maturity_match = re.search(r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            res['maturity_date'] = maturity_match.group(1)
        
        # Extract interest rate - pattern: "Interest Rate 8.23%" or "Interest Rate 11.16%"
        interest_rate_match = re.search(r'Interest\s+Rate\s+([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if interest_rate_match:
            res['interest_rate'] = self._percent(interest_rate_match.group(1))
        
        # Extract spread and reference rate - pattern: "SOFR Spread 5.50%" or "EURIBOR Spread"
        # Also check for "[X]% Interest Rate" at the start - this might be the spread
        ref_spread_match = re.search(r'\b(SOFR|EURIBOR|LIBOR|PRIME|BASE\s+RATE)\s+Spread\s+([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            res['reference_rate'] = ref_spread_match.group(1).upper()
            res['spread'] = self._percent(ref_spread_match.group(2))
        else:
            # Try pattern at start: "[X]% Interest Rate" where X is the spread
            start_spread_match = re.match(r'^([\d\.]+)\s*%\s+Interest\s+Rate', ident_clean, re.IGNORECASE)
            if start_spread_match:
                # Need to find reference rate - look for SOFR, EURIBOR, etc. in the string
                ref_match = re.search(r'\b(SOFR|EURIBOR|LIBOR|PRIME)\b', ident_clean, re.IGNORECASE)
                if ref_match:
                    res['reference_rate'] = ref_match.group(1).upper()
                res['spread'] = self._percent(start_spread_match.group(1))
        
        # Extract PIK rate - pattern: "X% PIK" or "(X% PIK)"
        pik_match = re.search(r'\(?([\d\.]+)\s*%\s*PIK\)?', ident_clean, re.IGNORECASE)
        if pik_match:
            res['pik_rate'] = self._percent(pik_match.group(1))
        else:
            # Try "X% PIK Interest Rate"
            pik_match2 = re.search(r'([\d\.]+)\s*%\s+PIK\s+Interest\s+Rate', ident_clean, re.IGNORECASE)
            if pik_match2:
                res['pik_rate'] = self._percent(pik_match2.group(1))
        
        # Remove rate/date prefixes from the start
        # Pattern: "[X]% [PIK] Interest Rate [Y]% Maturity Date [Date],"
        ident_clean = re.sub(r'^[\d\.]+\s*%\s*(?:PIK\s+)?Interest\s+Rate\s+[\d\.]+\s*%\s+Maturity\s+Date\s+\d{1,2}/\d{1,2}/\d{4}\s*,?\s*', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^-?\s*Delayed\s+Draw\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^-?\s*Revolver\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^[\d\.]+%\s*,?\s*', '', ident_clean)
        ident_clean = re.sub(r'^Interest\s*,?\s*', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^\d{1,2}/\d{1,2}/\d{4}\s*,?\s*', '', ident_clean)
        
        # Remove common prefixes (more aggressive - handle variations)
        ident_clean = re.sub(r'^(?:Non-controlled|Non-Controlled)/(?:Non-Affiliated|Affiliate)\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^Controlled\s+Affiliate\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^(?:British Pound|U\.S\. Dollar|U\.S\.)\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^(?:Euro|EUR)\s+', '', ident_clean, flags=re.IGNORECASE)
        
        # Split by comma - format: "[Industry] [Company Name] [Investment Type]..."
        if ',' in ident_clean:
            parts = ident_clean.split(',', 1)
            before_comma = parts[0].strip()
            after_comma = parts[1].strip() if len(parts) > 1 else ''
        else:
            before_comma = ident_clean
            after_comma = ''
        
        # Common industries in BCSF
        common_industries = [
            'Environmental Industries', 'Energy', 'Consumer Goods: Durable', 'Consumer Goods: Non-Durable',
            'Telecommunications', 'Services: Business', 'Services: Consumer', 'FIRE: Finance', 'FIRE: Insurance',
            'Healthcare & Pharmaceuticals', 'Wholesale', 'Beverage, Food & Tobacco', 'Hotel, Gaming & Leisure',
            'Aerospace & Defense', 'Capital Equipment', 'Automotive', 'Utilities: Water',
            'Transportation: Cargo', 'Investment Vehicles'
        ]
        
        # Find industry - it's typically the first part or after comma
        # Need to check both before_comma and after_comma, and handle multi-word industries
        industry_found = None
        industry_end_pos = 0
        search_text = before_comma + (', ' + after_comma if after_comma else '')
        
        # Try matching industries (longest first for better matches)
        sorted_industries = sorted(common_industries, key=len, reverse=True)
        
        for ind in sorted_industries:
            # Escape special regex chars but handle commas and colons
            escaped_ind = re.escape(ind)
            # Try matching from start of before_comma
            pattern = r'^' + escaped_ind + r'\s+'
            match = re.match(pattern, before_comma, re.IGNORECASE)
            if match:
                industry_found = ind
                industry_end_pos = match.end()
                break
            
            # Try matching from start of after_comma
            if after_comma:
                match = re.match(pattern, after_comma, re.IGNORECASE)
                if match:
                    industry_found = ind
                    industry_end_pos = match.end()
                    before_comma = after_comma
                    after_comma = ''
                    break
            
            # Also try searching anywhere in the text (for cases where format is different)
            pattern_anywhere = r'\b' + escaped_ind + r'\s+'
            match = re.search(pattern_anywhere, search_text, re.IGNORECASE)
            if match:
                # Make sure it's not inside a company name (check if followed by entity pattern)
                after_match = search_text[match.end():match.end()+50]
                # If followed by an entity pattern, this is likely the industry
                entity_check = re.search(r'\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|First|Second|Subordinated|Equity)', after_match, re.IGNORECASE)
                if entity_check:
                    industry_found = ind
                    industry_end_pos = match.end()
                    # Reconstruct before_comma/after_comma based on match position
                    if match.start() < len(before_comma):
                        before_comma = search_text[match.end():]
                    else:
                        before_comma = after_comma[match.end()-len(before_comma)-2:] if after_comma else ''
                    after_comma = ''
                    break
        
        if industry_found:
            res['industry'] = industry_found
            # Company name and investment type are in the remaining text
            remaining = before_comma[industry_end_pos:] if industry_end_pos > 0 else before_comma
        else:
            # No industry found, use all of before_comma
            remaining = before_comma
        
        # Extract investment type from remaining text (also check original identifier)
        inv_type_patterns = [
            r'First\s+Lien\s+Senior\s+Secured\s+Loan(?:\s*-\s*(?:Delayed\s+Draw|Revolver))?',
            r'Second\s+Lien\s+Senior\s+Secured\s+Loan',
            r'Subordinated\s+Debt',
            r'Subordinated\s+Note',
            r'Equity',
            r'Common\s+Stock',
            r'Preferred\s+Equity'
        ]
        
        inv_type_match = None
        # Search in remaining text first
        for pattern in inv_type_patterns:
            match = re.search(pattern, remaining, re.IGNORECASE)
            if match:
                inv_type_match = match
                break
        
        # If not found, try in original identifier
        if not inv_type_match:
            for pattern in inv_type_patterns:
                match = re.search(pattern, identifier, re.IGNORECASE)
                if match:
                    inv_type_match = match
                    remaining = identifier  # Use full identifier for company name extraction
                    break
        
        if inv_type_match:
            inv_type_text = inv_type_match.group(0)
            # Normalize
            if 'First Lien Senior Secured Loan' in inv_type_text:
                if '- Revolver' in inv_type_text:
                    res['investment_type'] = 'First Lien Senior Secured Loan - Revolver'
                elif '- Delayed Draw' in inv_type_text:
                    res['investment_type'] = 'First Lien Senior Secured Loan - Delayed Draw'
                else:
                    res['investment_type'] = 'First Lien Senior Secured Loan'
            elif 'Second Lien' in inv_type_text:
                res['investment_type'] = 'Second Lien Senior Secured Loan'
            elif 'Subordinated Debt' in inv_type_text or 'Subordinated Note' in inv_type_text:
                res['investment_type'] = 'Subordinated Debt'
            elif 'Equity' in inv_type_text and 'Common' not in inv_type_text and 'Preferred' not in inv_type_text:
                res['investment_type'] = 'Equity'
            else:
                res['investment_type'] = inv_type_text
        
        # Extract company name - it's before investment type (if found) or the main part
        if inv_type_match:
            company_text = remaining[:inv_type_match.start()].strip()
        else:
            # Look for stop words
            stop_pattern = r'\s+(SOFR|EURIBOR|LIBOR|PRIME)\s+Spread'
            stop_match = re.search(stop_pattern, remaining, re.IGNORECASE)
            if stop_match:
                company_text = remaining[:stop_match.start()].strip()
            else:
                # Remove trailing investment type mentions
                company_text = re.sub(r'\s+Maturity\s+Date.*$', '', remaining, flags=re.IGNORECASE)
                company_text = company_text.strip()
        
        # Clean up company name - remove prefixes FIRST (before other cleanup)
        # Remove "Non-controlled/Non-Affiliated Investments" even if embedded
        company_text = re.sub(r'Non-controlled/Non-Affiliated\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'Non-Controlled/Non-Affiliated\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'Non-controlled/Affiliate\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'Controlled\s+Affiliate\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        
        # Clean up company name
        company_text = re.sub(r'\s+One\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Two\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Three\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = company_text.replace('&amp;', '&')
        company_text = company_text.rstrip(',.').strip()
        
        # Remove any remaining industry prefixes if they leaked in (including partial matches)
        for ind in sorted_industries:  # Use sorted list (longest first)
            # Try exact match first
            if company_text.startswith(ind + ' '):
                company_text = company_text[len(ind):].strip()
                continue
            # Try with colon variations (e.g., "Services: Business" -> "Business")
            elif ':' in ind:
                parts = ind.split(':')
                if len(parts) == 2 and company_text.startswith(parts[0] + ': '):
                    company_text = company_text[len(parts[0]) + 2:].strip()
                    continue
            # Also try comma-separated industries like "Beverage, Food & Tobacco"
            elif ',' in ind:
                ind_parts = ind.split(',')
                if len(ind_parts) == 2:
                    first_part = ind_parts[0].strip()
                    if company_text.startswith(first_part + ', '):
                        # Check if rest matches
                        rest = company_text[len(first_part) + 2:].strip()
                        if rest.startswith(ind_parts[1].strip()):
                            company_text = rest[len(ind_parts[1].strip()):].strip()
                            continue
                    # Also try just the first part (e.g., "Non-Durable" from "Consumer Goods: Non-Durable")
                    if company_text.startswith(first_part + ' '):
                        company_text = company_text[len(first_part):].strip()
                        continue
            # Also check for partial matches at the start (e.g., "Non-Durable" from "Consumer Goods: Non-Durable")
            ind_words = ind.split()
            if len(ind_words) > 1:
                # Check if company name starts with last word(s) of industry
                for i in range(1, len(ind_words) + 1):
                    last_words = ' '.join(ind_words[-i:])
                    if company_text.startswith(last_words + ' '):
                        company_text = company_text[len(last_words):].strip()
                        break
        
        # Remove trailing investment type mentions if they're still there
        company_text = re.sub(r'\s+(?:First|Second)\s+Lien.*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Subordinated.*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Equity\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Maturity\s+Date.*$', '', company_text, flags=re.IGNORECASE)
        
        # Clean up incomplete company names (single words that look like industries)
        if company_text and len(company_text.split()) == 1:
            single_word = company_text.strip()
            # If it's just an industry word, try to get more context from original identifier
            if single_word.lower() in ['beverage', 'hotel', 'services', 'consumer', 'fire', 'insurance']:
                # Look for entity pattern in original identifier after this word
                # Pattern: "[Word], [Industry] [Company Name]..." or "[Word] [Industry] [Company Name]"
                entity_match = re.search(r'\b' + re.escape(single_word) + r'(?:\s*,\s*[^,]+)?\s+([A-Z][A-Za-z0-9\s&,\-\.\(\)/]{2,}?)\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|GmbH|AB|plc)', identifier, re.IGNORECASE)
                if entity_match:
                    entity_name = entity_match.group(1).strip()
                    entity_type_match = re.search(r'\b(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|GmbH|AB|plc)\b', identifier[entity_match.end():entity_match.end()+20], re.IGNORECASE)
                    if entity_type_match:
                        company_text = f"{entity_name} {entity_type_match.group(0)}"
        
        # Remove "FIRE: Insurance" or "Services: Consumer" type prefixes that might have leaked
        company_text = re.sub(r'^(?:FIRE|Services|Consumer|Fire|Services)\s*:\s*', '', company_text, flags=re.IGNORECASE)
        
        if company_text and len(company_text) > 2:
            res['company_name'] = self._strip_footnote_refs(company_text)
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[BCSFInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = BCSFInvestment(
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
        # Fill missing fields from parsed identifier
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if not inv.interest_rate and context.get('interest_rate'):
            inv.interest_rate = context['interest_rate']
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
    ex=BCSFExtractor()
    try:
        res=ex.extract_from_ticker('BCSF')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")


if __name__=='__main__':
	main()





        inv_type_patterns = [
            r'First\s+Lien\s+Senior\s+Secured\s+Loan(?:\s*-\s*(?:Delayed\s+Draw|Revolver))?',
            r'Second\s+Lien\s+Senior\s+Secured\s+Loan',
            r'Subordinated\s+Debt',
            r'Subordinated\s+Note',
            r'Equity',
            r'Common\s+Stock',
            r'Preferred\s+Equity'
        ]
        
        inv_type_match = None
        # Search in remaining text first
        for pattern in inv_type_patterns:
            match = re.search(pattern, remaining, re.IGNORECASE)
            if match:
                inv_type_match = match
                break
        
        # If not found, try in original identifier
        if not inv_type_match:
            for pattern in inv_type_patterns:
                match = re.search(pattern, identifier, re.IGNORECASE)
                if match:
                    inv_type_match = match
                    remaining = identifier  # Use full identifier for company name extraction
                    break
        
        if inv_type_match:
            inv_type_text = inv_type_match.group(0)
            # Normalize
            if 'First Lien Senior Secured Loan' in inv_type_text:
                if '- Revolver' in inv_type_text:
                    res['investment_type'] = 'First Lien Senior Secured Loan - Revolver'
                elif '- Delayed Draw' in inv_type_text:
                    res['investment_type'] = 'First Lien Senior Secured Loan - Delayed Draw'
                else:
                    res['investment_type'] = 'First Lien Senior Secured Loan'
            elif 'Second Lien' in inv_type_text:
                res['investment_type'] = 'Second Lien Senior Secured Loan'
            elif 'Subordinated Debt' in inv_type_text or 'Subordinated Note' in inv_type_text:
                res['investment_type'] = 'Subordinated Debt'
            elif 'Equity' in inv_type_text and 'Common' not in inv_type_text and 'Preferred' not in inv_type_text:
                res['investment_type'] = 'Equity'
            else:
                res['investment_type'] = inv_type_text
        
        # Extract company name - it's before investment type (if found) or the main part
        if inv_type_match:
            company_text = remaining[:inv_type_match.start()].strip()
        else:
            # Look for stop words
            stop_pattern = r'\s+(SOFR|EURIBOR|LIBOR|PRIME)\s+Spread'
            stop_match = re.search(stop_pattern, remaining, re.IGNORECASE)
            if stop_match:
                company_text = remaining[:stop_match.start()].strip()
            else:
                # Remove trailing investment type mentions
                company_text = re.sub(r'\s+Maturity\s+Date.*$', '', remaining, flags=re.IGNORECASE)
                company_text = company_text.strip()
        
        # Clean up company name - remove prefixes FIRST (before other cleanup)
        # Remove "Non-controlled/Non-Affiliated Investments" even if embedded
        company_text = re.sub(r'Non-controlled/Non-Affiliated\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'Non-Controlled/Non-Affiliated\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'Non-controlled/Affiliate\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'Controlled\s+Affiliate\s+Investments\s+', '', company_text, flags=re.IGNORECASE)
        
        # Clean up company name
        company_text = re.sub(r'\s+One\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Two\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Three\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = company_text.replace('&amp;', '&')
        company_text = company_text.rstrip(',.').strip()
        
        # Remove any remaining industry prefixes if they leaked in (including partial matches)
        for ind in sorted_industries:  # Use sorted list (longest first)
            # Try exact match first
            if company_text.startswith(ind + ' '):
                company_text = company_text[len(ind):].strip()
                continue
            # Try with colon variations (e.g., "Services: Business" -> "Business")
            elif ':' in ind:
                parts = ind.split(':')
                if len(parts) == 2 and company_text.startswith(parts[0] + ': '):
                    company_text = company_text[len(parts[0]) + 2:].strip()
                    continue
            # Also try comma-separated industries like "Beverage, Food & Tobacco"
            elif ',' in ind:
                ind_parts = ind.split(',')
                if len(ind_parts) == 2:
                    first_part = ind_parts[0].strip()
                    if company_text.startswith(first_part + ', '):
                        # Check if rest matches
                        rest = company_text[len(first_part) + 2:].strip()
                        if rest.startswith(ind_parts[1].strip()):
                            company_text = rest[len(ind_parts[1].strip()):].strip()
                            continue
                    # Also try just the first part (e.g., "Non-Durable" from "Consumer Goods: Non-Durable")
                    if company_text.startswith(first_part + ' '):
                        company_text = company_text[len(first_part):].strip()
                        continue
            # Also check for partial matches at the start (e.g., "Non-Durable" from "Consumer Goods: Non-Durable")
            ind_words = ind.split()
            if len(ind_words) > 1:
                # Check if company name starts with last word(s) of industry
                for i in range(1, len(ind_words) + 1):
                    last_words = ' '.join(ind_words[-i:])
                    if company_text.startswith(last_words + ' '):
                        company_text = company_text[len(last_words):].strip()
                        break
        
        # Remove trailing investment type mentions if they're still there
        company_text = re.sub(r'\s+(?:First|Second)\s+Lien.*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Subordinated.*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Equity\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Maturity\s+Date.*$', '', company_text, flags=re.IGNORECASE)
        
        # Clean up incomplete company names (single words that look like industries)
        if company_text and len(company_text.split()) == 1:
            single_word = company_text.strip()
            # If it's just an industry word, try to get more context from original identifier
            if single_word.lower() in ['beverage', 'hotel', 'services', 'consumer', 'fire', 'insurance']:
                # Look for entity pattern in original identifier after this word
                # Pattern: "[Word], [Industry] [Company Name]..." or "[Word] [Industry] [Company Name]"
                entity_match = re.search(r'\b' + re.escape(single_word) + r'(?:\s*,\s*[^,]+)?\s+([A-Z][A-Za-z0-9\s&,\-\.\(\)/]{2,}?)\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|GmbH|AB|plc)', identifier, re.IGNORECASE)
                if entity_match:
                    entity_name = entity_match.group(1).strip()
                    entity_type_match = re.search(r'\b(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|GmbH|AB|plc)\b', identifier[entity_match.end():entity_match.end()+20], re.IGNORECASE)
                    if entity_type_match:
                        company_text = f"{entity_name} {entity_type_match.group(0)}"
        
        # Remove "FIRE: Insurance" or "Services: Consumer" type prefixes that might have leaked
        company_text = re.sub(r'^(?:FIRE|Services|Consumer|Fire|Services)\s*:\s*', '', company_text, flags=re.IGNORECASE)
        
        if company_text and len(company_text) > 2:
            res['company_name'] = self._strip_footnote_refs(company_text)
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[BCSFInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = BCSFInvestment(
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
        # Fill missing fields from parsed identifier
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if not inv.interest_rate and context.get('interest_rate'):
            inv.interest_rate = context['interest_rate']
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
    ex=BCSFExtractor()
    try:
        res=ex.extract_from_ticker('BCSF')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")


if __name__=='__main__':
	main()




