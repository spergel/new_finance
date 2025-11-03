#!/usr/bin/env python3
"""
Custom OCSL (Oaktree Specialty Lending Corp) Investment Extractor

OCSL uses InvestmentIdentifierAxis format:
"[Company Name], [Industry], [Investment Type]"

Example: "C5 Technology Holdings, LLC, Data Processing & Outsourced Services, Common Stock"
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate
from dataclasses import dataclass
import requests
import csv
import os

logger = logging.getLogger(__name__)

@dataclass
class OCSLInvestment:
    """OCSL investment data structure."""
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

class OCSLExtractor:
    """Custom extractor for Oaktree Specialty Lending Corp (OCSL) investments."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        """Initialize the OCSL extractor."""
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    @staticmethod
    def _format_percent(value_str: str) -> str:
        """Normalize numeric strings to percentage with two decimals.
        Accepts numbers like '10.05' or '0.1005' and returns '10.05%'.
        """
        if value_str is None:
            return ''
        cleaned = value_str.strip().replace('%', '')
        try:
            num = float(cleaned)
        except (ValueError, TypeError):
            return value_str
        if abs(num) <= 1.0:
            num *= 100.0
        return f"{num:.2f}%"
    
    def extract_from_ticker(self, ticker: str = "OCSL") -> Dict:
        """Extract investments from OCSL's latest 10-Q filing."""
        
        logger.info(f"Extracting investments for {ticker}")
        
        # Get CIK
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        logger.info(f"Found CIK: {cik}")
        
        # Get latest 10-Q filing URL
        filing_index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not filing_index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        logger.info(f"Found filing index: {filing_index_url}")
        
        # Extract accession number and build .txt URL
        accession_match = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', filing_index_url)
        if not accession_match:
            raise ValueError(f"Could not parse accession number from {filing_index_url}")
        
        accession = accession_match.group(1)
        accession_no_hyphens = accession.replace('-', '')
        
        # Build URLs
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        logger.info(f"XBRL URL: {txt_url}")
        
        # Extract investments
        return self.extract_from_url(txt_url, "Oaktree Specialty Lending Corp", cik)
    
    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        """Extract investments from OCSL filing URL."""
        
        logger.info(f"Downloading XBRL from: {filing_url}")
        
        # Download the XBRL content
        response = requests.get(filing_url, headers=self.headers)
        response.raise_for_status()
        content = response.text
        
        logger.info(f"Downloaded {len(content)} characters")
        
        # Extract contexts with typedMember InvestmentIdentifierAxis
        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")

        # Keep only latest reporting instant to avoid prior-period duplicates
        selected_instant = self._select_reporting_instant(contexts)
        if selected_instant:
            contexts = [c for c in contexts if c.get('instant') == selected_instant]
            logger.info(f"Filtered contexts to instant {selected_instant}: {len(contexts)} remaining")
        
        # Extract facts
        facts_by_context = self._extract_facts(content)
        logger.info(f"Found facts for {len(facts_by_context)} contexts")
        
        # Build investments
        investments = []
        for ctx in contexts:
            investment = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if investment:
                investments.append(investment)

        # De-duplicate: keep first seen per (company, type, maturity) when values identical
        deduped = []
        seen = set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val_key = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val_key)
            if combo in seen:
                continue
            seen.add(combo)
            deduped.append(inv)
        investments = deduped
        
        logger.info(f"Built {len(investments)} investments")
        
        # Calculate totals
        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in investments:
            industry_breakdown[inv.industry] += 1
            investment_type_breakdown[inv.investment_type] += 1
        
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'investments': investments,
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        """Extract contexts with typedMember InvestmentIdentifierAxis."""
        
        contexts = []
        
        # Pattern to find contexts
        context_pattern = re.compile(
            r'<context id="([^"]+)">(.*?)</context>',
            re.DOTALL
        )
        
        # Pattern for typedMember with InvestmentIdentifierAxis
        typed_member_pattern = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>',
            re.DOTALL
        )
        
        for match in context_pattern.finditer(content):
            ctx_id = match.group(1)
            ctx_content = match.group(2)
            
            typed_match = typed_member_pattern.search(ctx_content)
            if typed_match:
                investment_identifier = typed_match.group(1).strip()
                
                # Parse OCSL format: "Company Name, Industry, Investment Type"
                parsed = self._parse_ocsl_identifier(investment_identifier)
                
                # Extract dates
                instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
                start_match = re.search(r'<startDate>([^<]+)</startDate>', ctx_content)
                end_match = re.search(r'<endDate>([^<]+)</endDate>', ctx_content)
                
                context = {
                    'id': ctx_id,
                    'investment_identifier': investment_identifier,
                    'company_name': parsed['company_name'],
                    'industry': parsed['industry'],
                    'investment_type': parsed['investment_type'],
                    'instant': instant_match.group(1) if instant_match else None,
                    'start_date': start_match.group(1) if start_match else None,
                    'end_date': end_match.group(1) if end_match else None
                }
                
                contexts.append(context)
        
        return contexts

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        """Choose the latest instant (YYYY-MM-DD) among contexts, if available."""
        dates = []
        for c in contexts:
            inst = c.get('instant')
            if inst and re.match(r'^\d{4}-\d{2}-\d{2}$', inst):
                dates.append(inst)
        if not dates:
            return None
        return max(dates)
    
    def _parse_ocsl_identifier(self, identifier: str) -> Dict[str, str]:
        """
        Parse OCSL's InvestmentIdentifierAxis format.
        
        Format: "[Company Name], [Industry], [Investment Type]"
        
        Examples:
        - "C5 Technology Holdings, LLC, Data Processing & Outsourced Services, Common Stock"
        - "Dominion Diagnostics, LLC, Health Care Services, First Lien Term Loan 1"
        - "SIO2 Medical Products, Inc., Metal, Glass & Plastic Containers, First Lien Term Loan 1"
        - "The Avery, Real Estate Operating Companies, First Lien Term Loan 1"
        """
        
        result = {
            'company_name': 'Unknown',
            'industry': 'Unknown',
            'investment_type': 'Unknown'
        }
        
        # Investment type patterns that indicate where investment type starts
        # These typically appear at the end
        investment_type_patterns = [
            r'\bFirst Lien.*$',
            r'\bSecond Lien.*$',
            r'\bSubordinated Debt$',
            r'\bCommon Stock\b.*$',
            r'\bPreferred Equity\b.*$',
            r'\bPreferred Stock\b.*$',
            r'\bWarrants?\b.*$',
            r'\bMembership Interest\b.*$',
            r'\bCLO Notes\b.*$',
            r'\bFixed Rate Bond\b.*$',
            r'\bRevolver\b.*$',
            r'\bTerm Loan\b.*$',
        ]
        
        # Find investment type by looking for patterns
        investment_type = None
        investment_type_pos = -1
        
        for pattern in investment_type_patterns:
            match = re.search(pattern, identifier, re.IGNORECASE)
            if match:
                investment_type = match.group(0).strip()
                investment_type_pos = match.start()
                break
        
        if not investment_type:
            # No investment type found - might be a subtotal or other entry
            # Try simple split as fallback
            parts = [p.strip() for p in identifier.split(',')]
            if len(parts) < 2:
                return result
            # Assume last part might be investment type anyway
            investment_type = parts[-1]
            investment_type_pos = len(identifier) - len(investment_type)
        else:
            # Clean up investment type (remove trailing spaces)
            investment_type = investment_type.strip()
        
        result['investment_type'] = investment_type
        
        # Everything before investment type is: Company, Industry
        # But industry can have commas (e.g., "Metal, Glass & Plastic Containers")
        # Strategy: Work backwards from investment type position
        # The industry starts at the last comma that doesn't match company name patterns
        
        company_and_industry = identifier[:investment_type_pos].strip().rstrip(',')
        
        if not company_and_industry:
            return result
        
        # Find all commas in company_and_industry
        commas = [i for i, char in enumerate(company_and_industry) if char == ',']
        
        if not commas:
            # No commas - probably just company name (subtotal or aggregate)
            result['company_name'] = company_and_industry
            result['industry'] = 'Unknown'
        elif len(commas) == 1:
            # Simple case: one comma, separates company and industry
            company_name = company_and_industry[:commas[0]].strip()
            industry = company_and_industry[commas[0] + 1:].strip()
            industry = industry.replace('&amp;', '&')
            result['company_name'] = company_name
            result['industry'] = industry
        else:
            # Multiple commas - need to determine where company ends and industry begins
            # Industries often contain words like: "Services", "Software", "Products", etc.
            # Company names typically end with: Inc., LLC, Corp., Ltd., etc.
            
            # Look for company name suffixes from the left
            company_suffixes = [r'Inc\.', r'LLC', r'Corp\.', r'Corporation', r'Ltd\.', r'LP', r'S\.A\.R\.L\.', r'plc']
            
            # Find the rightmost comma that's likely after a company name
            # Check from right to left
            best_split = None
            for i in range(len(commas) - 1, -1, -1):
                comma_pos = commas[i]
                text_before_comma = company_and_industry[:comma_pos]
                
                # Check if text before comma ends with a company suffix
                for suffix_pattern in company_suffixes:
                    if re.search(suffix_pattern + r'\s*$', text_before_comma, re.IGNORECASE):
                        best_split = comma_pos
                        break
                
                if best_split:
                    break
            
            if best_split:
                # Found a good split point
                company_name = company_and_industry[:best_split].strip()
                industry = company_and_industry[best_split + 1:].strip()
                industry = industry.replace('&amp;', '&')
                result['company_name'] = company_name
                result['industry'] = industry
            else:
                # Fallback: use the last comma
                last_comma = commas[-1]
                company_name = company_and_industry[:last_comma].strip()
                industry = company_and_industry[last_comma + 1:].strip()
                industry = industry.replace('&amp;', '&')
                result['company_name'] = company_name
                result['industry'] = industry
        
        return result
    
    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        """Extract facts grouped by context, supporting both standard XBRL and inline XBRL (ix:nonFraction)."""

        facts_by_context: Dict[str, List[Dict]] = defaultdict(list)

        # 1) Standard XBRL facts like <us-gaap:Concept contextRef="c-123">123</us-gaap:Concept>
        standard_fact_pattern = re.compile(
            r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>',
            re.DOTALL
        )
        for concept, context_ref, value in standard_fact_pattern.findall(content):
            if value and context_ref:
                facts_by_context[context_ref].append({
                    'concept': concept,
                    'value': value.strip()
                })

        # 2) Inline XBRL facts like <ix:nonFraction name="us-gaap:Concept" contextRef="c-123">123</ix:nonFraction>
        ix_fact_pattern = re.compile(
            r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>',
            re.DOTALL | re.IGNORECASE
        )

        # Additionally track the position of each ix fact to scrape nearby reference-rate text and dates
        for match in ix_fact_pattern.finditer(content):
            name = match.group(1)
            context_ref = match.group(2)
            value_html = match.group(4)
            if not context_ref:
                continue

            # Extract plain text value (strip tags)
            value_text = re.sub(r'<[^>]+>', '', value_html).strip()

            if value_text:
                facts_by_context[context_ref].append({
                    'concept': name,
                    'value': value_text
                })

            # Heuristic window around this ix fact: prefer enclosing table row to avoid cross-row noise
            tr_start = content.rfind('<tr', 0, match.start())
            tr_end = content.find('</tr>', match.end())
            if tr_start != -1 and tr_end != -1:
                window = content[tr_start:tr_end]
            else:
                start_idx = max(0, match.start() - 1500)
                end_idx = min(len(content), match.end() + 1500)
                window = content[start_idx:end_idx]

            # Reference rate token (allow optional tenor and whitespace before '+'); fallback to bare token
            ref_clean = None
            ref_match = re.search(r'\b((?:\d+\s*[DMWY]\s*)?SOFR|PRIME|LIBOR|EURIBOR|BASE\s*RATE)\s*\+', window, re.IGNORECASE)
            if ref_match:
                token = re.sub(r'\s+', ' ', ref_match.group(1)).strip().upper()
                if 'SOFR' in token:
                    ref_clean = 'SOFR'
                elif 'PRIME' in token:
                    ref_clean = 'PRIME'
                elif 'LIBOR' in token:
                    ref_clean = 'LIBOR'
                elif 'EURIBOR' in token:
                    ref_clean = 'EURIBOR'
                else:
                    ref_clean = 'BASE RATE'
            else:
                bare_ref = re.search(r'\b(SOFR|PRIME|LIBOR|EURIBOR|BASE\s*RATE)\b', window, re.IGNORECASE)
                if bare_ref:
                    token = re.sub(r'\s+', ' ', bare_ref.group(1)).strip().upper()
                    if 'SOFR' in token:
                        ref_clean = 'SOFR'
                    elif 'PRIME' in token:
                        ref_clean = 'PRIME'
                    elif 'LIBOR' in token:
                        ref_clean = 'LIBOR'
                    elif 'EURIBOR' in token:
                        ref_clean = 'EURIBOR'
                    else:
                        ref_clean = 'BASE RATE'
            if ref_clean:
                facts_by_context[context_ref].append({'concept': 'derived:ReferenceRateToken', 'value': ref_clean})

            # Floor rate token (e.g., "floor" nearby with a number or %)
            floor_match = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor_match:
                facts_by_context[context_ref].append({
                    'concept': 'derived:FloorRate',
                    'value': floor_match.group(1)
                })

            # PIK rate token
            pik_match = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik_match:
                facts_by_context[context_ref].append({
                    'concept': 'derived:PIKRate',
                    'value': pik_match.group(1)
                })

            # Date patterns within the same row (acquisition/maturity)
            acq_lbl = re.search(r'Acquisition\s*Date[^\d]{0,30}(\d{1,2}/\d{1,2}/\d{4})', window, re.IGNORECASE)
            mat_lbl = re.search(r'Maturity\s*Date[^\d]{0,30}(\d{1,2}/\d{1,2}/\d{4})', window, re.IGNORECASE)
            if acq_lbl:
                facts_by_context[context_ref].append({'concept': 'derived:AcquisitionDate', 'value': acq_lbl.group(1)})
            if mat_lbl:
                facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': mat_lbl.group(1)})
            if not acq_lbl or not mat_lbl:
                date_matches = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b', window)
                if date_matches:
                    if not acq_lbl and len(date_matches) >= 2:
                        facts_by_context[context_ref].append({'concept': 'derived:AcquisitionDate', 'value': date_matches[0]})
                    if not mat_lbl:
                        facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': date_matches[-1]})

        return facts_by_context
    
    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[OCSLInvestment]:
        """Build investment from context and facts."""
        
        # Skip invalid entries
        if context['company_name'] == 'Unknown':
            return None
        
        investment = OCSLInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        
        # Extract financial facts and derived attributes
        for fact in facts:
            concept = fact['concept']
            value_str = fact['value']
            
            # Remove commas from numbers
            value_str = value_str.replace(',', '')
            
            # Map concepts to investment fields
            concept_lower = concept.lower()
            
            # Numeric fields
            if any(k in concept_lower for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal']):
                try:
                    investment.principal_amount = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if ('cost' in concept_lower and ('amortized' in concept_lower or 'basis' in concept_lower)) or 'ownedatcost' in concept_lower:
                try:
                    investment.cost = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if 'fairvalue' in concept_lower or ('fair' in concept_lower and 'value' in concept_lower) or 'ownedatfairvalue' in concept_lower:
                try:
                    investment.fair_value = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue

            # Rates (as strings)
            if 'investmentbasisspreadvariablerate' in concept_lower:
                investment.spread = self._format_percent(value_str)
                continue
            if 'investmentinterestrate' in concept_lower:
                investment.interest_rate = self._format_percent(value_str)
                continue
            if concept_lower == 'derived:referenceratetoken':
                investment.reference_rate = value_str.upper()
                continue
            if concept_lower == 'derived:floorrate':
                investment.floor_rate = self._format_percent(value_str)
                continue
            if concept_lower == 'derived:pikrate':
                investment.pik_rate = self._format_percent(value_str)
                continue
            if concept_lower == 'derived:acquisitiondate':
                investment.acquisition_date = value_str
                continue
            if concept_lower == 'derived:maturitydate':
                investment.maturity_date = value_str
                continue
            
            # Context period might indicate acquisition date
            if context.get('start_date'):
                investment.acquisition_date = context['start_date'][:10]  # YYYY-MM-DD
        
        # Only return if we have essential data
        if investment.company_name and (investment.principal_amount or investment.cost or investment.fair_value):
            return investment
        
        return None


def main():
    """Test the OCSL extractor."""
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = OCSLExtractor()
    
    try:
        result = extractor.extract_from_ticker("OCSL")
        
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")
        
        # Show sample
        print(f"\n[SAMPLE] Sample Investments:")
        for i, inv in enumerate(result['investments'][:5]):
            print(f"\n{i+1}. {inv.company_name}")
            print(f"   Industry: {inv.industry}")
            print(f"   Type: {inv.investment_type}")
            if inv.fair_value:
                print(f"   Fair Value: ${inv.fair_value:,.0f}")
        
        # Save to CSV
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "OCSL_Oaktree_Specialty_Lending_investments.csv")
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate'
            ])
            writer.writeheader()
            
            for inv in result['investments']:
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
                    'pik_rate': inv.pik_rate
                })
        
        print(f"\n[SAVED] Results saved to: {output_file}")
        
        # Data quality
        total = result['total_investments']
        with_industry = sum(1 for inv in result['investments'] if inv.industry != 'Unknown')
        with_type = sum(1 for inv in result['investments'] if inv.investment_type != 'Unknown')
        with_fv = sum(1 for inv in result['investments'] if inv.fair_value)
        
        print(f"\n[QUALITY] Data Quality:")
        print(f"   Industries: {with_industry}/{total} ({100*with_industry/total:.1f}%)")
        print(f"   Investment Types: {with_type}/{total} ({100*with_type/total:.1f}%)")
        print(f"   Fair Values: {with_fv}/{total} ({100*with_fv/total:.1f}%)")
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()




if __name__ == "__main__":
    main()


