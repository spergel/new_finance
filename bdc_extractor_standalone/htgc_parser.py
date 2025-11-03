#!/usr/bin/env python3
"""
Custom HTGC (Hercules Capital) Investment Extractor

HTGC uses a different InvestmentIdentifierAxis format:
"Debt Investments [Industry] and [Company Name], [Investment Details]"

Example: "Debt Investments Biotechnology Tools and PathAI, Inc., Senior Secured, Maturity Date January 2027..."
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate
from dataclasses import dataclass
from datetime import datetime

@dataclass
class HTGCInvestment:
    """HTGC investment data structure."""
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
from bs4 import BeautifulSoup
import requests
import csv
import os

logger = logging.getLogger(__name__)

class HTGCExtractor:
    """Custom extractor for Hercules Capital (HTGC) investments."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        """Initialize the HTGC extractor."""
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "HTGC") -> Dict:
        """Extract investments from HTGC's latest 10-Q filing."""
        
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
        return self.extract_from_url(txt_url, "Hercules Capital Inc", cik)
    
    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        """Extract investments from HTGC filing URL."""
        
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
                
                # Parse HTGC-specific format
                parsed = self._parse_htgc_identifier(investment_identifier)
                
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
                    'maturity_date_raw': parsed.get('maturity_date'),
                    'interest_rate_raw': parsed.get('interest_rate'),
                    'reference_rate_raw': parsed.get('reference_rate'),
                    'spread_raw': parsed.get('spread'),
                    'floor_rate_raw': parsed.get('floor_rate'),
                    'pik_rate_raw': parsed.get('pik_rate'),
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
    
    def _parse_htgc_identifier(self, identifier: str) -> Dict[str, str]:
        """
        Parse HTGC's InvestmentIdentifierAxis format.
        
        Format: "Debt Investments [Industry] and [Company Name], [Investment Details...]"
        
        Examples:
        - "Debt Investments Biotechnology Tools and PathAI, Inc., Senior Secured, Maturity Date January 2027, Prime + 2.15%, Floor rate 9.15%..."
        - "Debt Investments Consumer & Business Services and SeatGeek, Inc., Senior Secured, Maturity Date May 2026, Prime + 7.00%, Floor rate 10.50%..."
        - "Debt Investments Consumer & Business Services (16.82%)"  <- Subtotal, skip
        - "Debt Investments Consumer & Business Services and Total SeatGeek, Inc."  <- Subtotal, skip
        """
        
        result = {
            'company_name': 'Unknown',
            'industry': 'Unknown',
            'investment_type': 'Unknown'
        }
        
        # Skip subtotals (they have percentages like "(16.82%)" or "Total [Company]")
        if re.search(r'\([\d.]+%\)', identifier) or re.search(r'\bTotal\s+[A-Z]', identifier):
            return result
        
        # Pattern: "Debt Investments [Industry] and [Company Name], [Investment Details...]"
        # OR: "Debt Investments [Industry] and [Company Name] [Investment Type], Maturity Date..."
        # Use a more flexible regex that handles "&" and various company name formats
        debt_investments_match = re.match(
            r'Debt Investments\s+(.+?)\s+and\s+([^,]+?)\s*,\s*(.+)$',
            identifier,
            re.IGNORECASE | re.DOTALL
        )
        
        if debt_investments_match:
            industry = debt_investments_match.group(1).strip()
            company_and_type = debt_investments_match.group(2).strip()
            details = debt_investments_match.group(3)
            
            # Extract investment type first (before extracting company name)
            investment_type_from_name = self._extract_investment_type_from_string(company_and_type)
            if investment_type_from_name:
                result['investment_type'] = investment_type_from_name
            
            # Then extract company name (this will remove the investment type)
            company_name = self._extract_company_name(company_and_type)
            
            # Clean company name (remove trailing periods, etc.)
            company_name = company_name.rstrip('.')
            
            result['industry'] = industry
            result['company_name'] = company_name
            
            # Parse details for investment type, maturity, rates, etc.
            # This will override investment_type if found
            details_parsed = self._parse_investment_details(details)
            result.update(details_parsed)
        else:
            # Fallback for non-standard formats
            # Check if it starts with "Debt Investments" but doesn't match pattern
            if identifier.startswith('Debt Investments'):
                # Might be a subtotal or aggregate line
                return result
            
            # Try to extract company name if pattern is "Industry and Company, Details"
            if ' and ' in identifier and ',' in identifier:
                # Find " and " and first comma after it
                and_pos = identifier.find(' and ')
                if and_pos > 0:
                    potential_industry = identifier[:and_pos].strip()
                    rest_after_and = identifier[and_pos + 5:].strip()  # +5 for " and "
                    
                    if ',' in rest_after_and:
                        company_name = rest_after_and.split(',')[0].strip().rstrip('.')
                        details = ','.join(rest_after_and.split(',')[1:]).strip()
                        
                        result['industry'] = potential_industry
                        result['company_name'] = company_name
                        details_parsed = self._parse_investment_details(details)
                        result.update(details_parsed)
        
        return result
    
    def _extract_company_name(self, text: str) -> str:
        """
        Extract company name from text that may contain investment type.
        
        Examples:
        - "PathAI, Inc." -> "PathAI, Inc."
        - "Weee! Inc.. Senior Secured" -> "Weee! Inc."
        - "Carwow LTD Senior Secured" -> "Carwow LTD"
        """
        
        # First, identify where investment type starts
        # Investment type keywords that indicate the end of company name
        type_keywords = [
            'Senior Secured', 'Convertible Debt', 'Unsecured', 
            'Senior Subordinated', 'Subordinated', 'Preferred Stock', 
            'Common Stock', 'Warrant', 'Limited Partnership'
        ]
        
        company_name = text
        
        # Find the earliest occurrence of an investment type keyword
        earliest_pos = len(text)
        found_type = None
        
        for keyword in type_keywords:
            # Case-insensitive search
            pos = text.lower().find(keyword.lower())
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
                found_type = keyword
        
        # If found, extract everything before the investment type
        if found_type:
            company_name = text[:earliest_pos].strip()
            
            # Clean up trailing punctuation
            company_name = company_name.rstrip('.,; ')
        
        # Additional cleanup: remove trailing periods/double periods
        company_name = re.sub(r'\.+$', '', company_name)
        
        return company_name.strip()
    
    def _extract_investment_type_from_string(self, text: str) -> Optional[str]:
        """Extract investment type from string if present."""
        
        type_patterns = [
            ('Senior Secured', 'Senior Secured'),
            ('Convertible Debt', 'Convertible Debt'),
            ('Unsecured', 'Unsecured'),
            ('Senior Subordinated', 'Senior Subordinated'),
            ('Subordinated', 'Subordinated'),
            ('Preferred Stock', 'Preferred Stock'),
            ('Common Stock', 'Common Stock'),
            ('Warrant', 'Warrant'),
        ]
        
        for pattern, label in type_patterns:
            if re.search(rf'\b{re.escape(pattern)}\b', text, re.IGNORECASE):
                return label
        
        return None
    
    def _parse_investment_details(self, details: str) -> Dict[str, str]:
        """Parse investment details string for type, maturity, rates, etc."""
        
        result = {}
        
        # Investment type patterns - check details string for investment type
        # Only set if found (don't overwrite with 'Unknown')
        type_patterns = [
            ('Senior Secured', 'Senior Secured'),
            ('Senior Subordinated', 'Senior Subordinated'),
            ('Unsecured', 'Unsecured'),
            ('Convertible Debt', 'Convertible Debt'),
            ('Common Stock', 'Common Stock'),
            ('Preferred Stock', 'Preferred Stock'),
            ('Warrant', 'Warrant'),
            ('Limited Partnership', 'Limited Partnership'),
        ]
        
        for pattern, label in type_patterns:
            if re.search(rf'\b{re.escape(pattern)}\b', details, re.IGNORECASE):
                result['investment_type'] = label
                break
        
        # Maturity date: "Maturity Date January 2027" or "Maturity Date 12/31/26"
        maturity_match = re.search(
            r'Maturity Date\s+([A-Za-z]+ \d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
            details,
            re.IGNORECASE
        )
        if maturity_match:
            result['maturity_date'] = maturity_match.group(1).strip()
        
        # Interest rate patterns
        # "Prime + 2.15%", "Fixed 8.25%", "3-month SOFR + 8.28%"
        rate_patterns = [
            (r'Fixed\s+(\d+\.?\d*)%', 'fixed'),
            (r'Prime\s*\+?\s*([+-]?\d+\.?\d*)%', 'prime'),
            (r'(\d+[-\s]?month)\s+SOFR\s*\+?\s*([+-]?\d+\.?\d*)%', 'sofr'),
            (r'1[-\s]?month\s+SOFR\s*\+?\s*([+-]?\d+\.?\d*)%', 'sofr_1m'),
            (r'3[-\s]?month\s+SOFR\s*\+?\s*([+-]?\d+\.?\d*)%', 'sofr_3m'),
        ]
        
        for pattern, rate_type in rate_patterns:
            match = re.search(pattern, details, re.IGNORECASE)
            if match:
                if rate_type == 'fixed':
                    result['interest_rate'] = f"{match.group(1)}%"
                    result['reference_rate'] = 'Fixed'
                elif rate_type == 'prime':
                    result['reference_rate'] = 'Prime'
                    result['spread'] = f"{match.group(1)}%"
                elif 'sofr' in rate_type:
                    result['reference_rate'] = f"SOFR ({match.groups()[0]})"
                    result['spread'] = f"{match.groups()[-1]}%"
                break
        
        # Floor rate: "Floor rate 9.15%"
        floor_match = re.search(r'Floor rate\s+(\d+\.?\d*)%', details, re.IGNORECASE)
        if floor_match:
            result['floor_rate'] = f"{floor_match.group(1)}%"
        
        # PIK Interest: "PIK Interest 12.00%" or "PIK Interest 1.50%"
        pik_match = re.search(r'PIK Interest\s+(\d+\.?\d*)%', details, re.IGNORECASE)
        if pik_match:
            result['pik_rate'] = f"{pik_match.group(1)}%"
        
        # Cap rate: "Cap rate 9.60%"
        cap_match = re.search(r'Cap rate\s+(\d+\.?\d*)%', details, re.IGNORECASE)
        if cap_match:
            result['cap_rate'] = f"{cap_match.group(1)}%"
        
        # Exit Fee: "7.85% Exit Fee"
        exit_fee_match = re.search(r'(\d+\.?\d*)%\s+Exit Fee', details, re.IGNORECASE)
        if exit_fee_match:
            result['exit_fee'] = f"{exit_fee_match.group(1)}%"
        
        return result
    
    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        """Extract facts grouped by context."""
        
        facts_by_context = defaultdict(list)
        
        # Find all facts (elements with contextRef attribute)
        fact_pattern = re.compile(
            r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>',
            re.DOTALL
        )
        matches = fact_pattern.findall(content)
        
        for concept, context_ref, value in matches:
            if value:  # Only include facts with values
                facts_by_context[context_ref].append({
                    'concept': concept,
                    'value': value.strip()
                })
        
        return facts_by_context
    
    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[HTGCInvestment]:
        """Build investment from context and facts."""
        
        # Skip subtotal rows
        if context['company_name'] == 'Unknown' or 'Total' in context['company_name']:
            return None
        
        investment = HTGCInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            maturity_date=self._normalize_date(context.get('maturity_date_raw')),
            interest_rate=context.get('interest_rate_raw'),
            reference_rate=context.get('reference_rate_raw'),
            spread=context.get('spread_raw'),
            floor_rate=context.get('floor_rate_raw'),
            pik_rate=context.get('pik_rate_raw'),
            context_ref=context['id']
        )
        
        # Extract financial facts
        for fact in facts:
            concept = fact['concept']
            value_str = fact['value']
            
            # Remove commas from numbers
            value_str = value_str.replace(',', '')
            
            try:
                value = float(value_str)
            except (ValueError, TypeError):
                continue
            
            # Map concepts to investment fields
            concept_lower = concept.lower()
            
            if 'principal' in concept_lower or 'outstandingprincipal' in concept_lower:
                investment.principal_amount = value
            elif 'cost' in concept_lower and ('amortized' in concept_lower or 'basis' in concept_lower):
                investment.cost = value
            elif 'fairvalue' in concept_lower or ('fair' in concept_lower and 'value' in concept_lower):
                investment.fair_value = value
            
            # Context period might indicate acquisition date
            if context.get('start_date'):
                investment.acquisition_date = context['start_date'][:10]  # YYYY-MM-DD
        
        # Only return if we have essential data
        if investment.company_name and (investment.principal_amount or investment.cost or investment.fair_value):
            return investment
        
        return None
    
    def _normalize_date(self, date_str: Optional[str]) -> Optional[str]:
        """Normalize date from various formats to YYYY-MM-DD or keep as-is."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Already in good format (YYYY-MM-DD)
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            return date_str
        
        # Month name format: "January 2027"
        month_match = re.match(r'([A-Za-z]+)\s+(\d{4})', date_str)
        if month_match:
            month_name = month_match.group(1)
            year = month_match.group(2)
            
            month_map = {
                'january': '01', 'february': '02', 'march': '03', 'april': '04',
                'may': '05', 'june': '06', 'july': '07', 'august': '08',
                'september': '09', 'october': '10', 'november': '11', 'december': '12'
            }
            
            month_num = month_map.get(month_name.lower())
            if month_num:
                # Use first day of month (we don't have day info)
                return f"{year}-{month_num}-01"
        
        # Return as-is if can't parse
        return date_str


def main():
    """Test the HTGC extractor."""
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = HTGCExtractor()
    
    try:
        result = extractor.extract_from_ticker("HTGC")
        
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
            print(f"   Maturity: {inv.maturity_date or 'N/A'}")
            if inv.fair_value:
                print(f"   Fair Value: ${inv.fair_value:,.0f}")
        
        # Save to CSV
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "HTGC_Hercules_Capital_investments.csv")
        
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


