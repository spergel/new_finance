#!/usr/bin/env python3
"""
Custom MSDL (Morgan Stanley Direct Lending Fund) Investment Extractor

MSDL appears to use XBRL primarily for investment data. This custom parser
enhances XBRL extraction with any available HTML table data.
"""

import logging
import os
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import csv
from collections import defaultdict

from xbrl_typed_extractor import TypedMemberExtractor, BDCExtractionResult
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class MSDLCustomExtractor:
    """Custom extractor for MSDL that uses XBRL with HTML enhancement."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.xbrl_extractor = TypedMemberExtractor(user_agent)
    
    def extract_from_ticker(self, ticker: str = "MSDL") -> BDCExtractionResult:
        """Extract investments from MSDL's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise RuntimeError("Could not resolve CIK for MSDL")
        
        logger.info(f"Found CIK: {cik}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise RuntimeError("Could not locate latest 10-Q index for MSDL")
        
        logger.info(f"Filing index: {index_url}")
        
        # Get URLs
        match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
        if not match:
            raise RuntimeError("Could not parse accession/URLs for MSDL")
        
        accession = match.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        
        # Get HTML URL
        documents = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
        if not main_html:
            raise RuntimeError("Could not find HTML document")
        
        htm_url = main_html.url
        logger.info(f"XBRL URL: {txt_url}")
        logger.info(f"HTML URL: {htm_url}")
        
        return self.extract_from_filing(txt_url, htm_url, "Morgan Stanley Direct Lending Fund", cik, ticker)
    
    def extract_from_filing(self, txt_url: str, htm_url: str, company_name: str, cik: str, ticker: str = "MSDL") -> BDCExtractionResult:
        """Extract complete MSDL investment data from XBRL (primary) and HTML (enhancement)."""
        
        logger.info(f"Starting MSDL extraction from XBRL...")
        
        # Extract from XBRL (primary source for MSDL)
        xbrl_result = self.xbrl_extractor.extract_from_url(txt_url, company_name, cik)
        logger.info(f"XBRL extraction: {xbrl_result.total_investments} investments")
        
        # Convert XBRL investments to dict format
        investments = []
        for inv in xbrl_result.investments:
            raw_company_name = inv.get('company_name', '')
            
            # Parse the company_name field to extract all available information
            parsed_data = self._parse_company_name_field(raw_company_name)
            
            # Use parsed data to fill in missing fields (only if field is missing or empty)
            company_name = parsed_data.get('company_name') or raw_company_name
            industry = inv.get('industry') or parsed_data.get('industry') or ''
            investment_type = inv.get('investment_type') or parsed_data.get('investment_type') or ''
            maturity_date = inv.get('maturity_date') or parsed_data.get('maturity_date')
            acquisition_date = inv.get('acquisition_date') or parsed_data.get('acquisition_date')
            interest_rate = inv.get('interest_rate') or parsed_data.get('interest_rate')
            reference_rate = inv.get('reference_rate') or parsed_data.get('reference_rate')
            spread = inv.get('spread') or parsed_data.get('spread')
            pik_rate = inv.get('pik_rate') or parsed_data.get('pik_rate')
            
            # Normalize dates
            if maturity_date:
                maturity_date = self._normalize_date(maturity_date)
            if acquisition_date:
                acquisition_date = self._normalize_date(acquisition_date)
            
            investments.append({
                'company_name': company_name,
                'business_description': inv.get('business_description', ''),
                'investment_type': investment_type,
                'industry': industry,
                'acquisition_date': acquisition_date,
                'maturity_date': maturity_date,
                'principal_amount': inv.get('principal_amount'),
                'cost_basis': inv.get('cost_basis'),
                'fair_value': inv.get('fair_value'),
                'interest_rate': interest_rate,
                'reference_rate': reference_rate,
                'spread': spread,
                'floor_rate': inv.get('floor_rate'),
                'pik_rate': pik_rate,
                'shares_units': inv.get('shares_units'),
                'percent_net_assets': inv.get('percent_net_assets')
            })
        
        # Try to enhance with HTML data if available
        try:
            html_investments = self._parse_html_table(htm_url)
            if html_investments:
                logger.info(f"Found {len(html_investments)} investments in HTML, attempting to merge...")
                investments = self._merge_data(investments, html_investments)
        except Exception as e:
            logger.warning(f"HTML parsing failed, using XBRL only: {e}")
        
        # Recalculate totals
        total_principal = sum(inv.get('principal_amount') or 0 for inv in investments)
        total_cost = sum(inv.get('cost_basis') or 0 for inv in investments)
        total_fair_value = sum(inv.get('fair_value') or 0 for inv in investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f'{ticker}_Morgan_Stanley_Direct_Lending_Fund_investments.csv')
        
        self._save_to_csv(investments, output_file)
        logger.info(f"Saved {len(investments)} investments to {output_file}")
        
        from datetime import datetime
        return BDCExtractionResult(
            company_name=company_name,
            cik=cik,
            filing_date=xbrl_result.filing_date,
            filing_url=htm_url,
            extraction_date=datetime.now().isoformat(),
            total_investments=len(investments),
            total_principal=total_principal,
            total_cost=total_cost,
            total_fair_value=total_fair_value,
            investments=investments,
            industry_breakdown=dict(industry_breakdown),
            investment_type_breakdown=dict(investment_type_breakdown)
        )
    
    def _parse_company_name_field(self, company_name: str) -> Dict:
        """
        Parse the company_name field to extract structured information.
        
        Handles patterns like:
        - "Investments-non-controlled/non-affiliated Debt Investments [Industry] [Company] Investment [Type] Reference Rate and Spread [Rate] Interest Rate [Rate] Maturity Date [Date]"
        - "First Lien Debt [Company] Commitment Type [Type]"
        - "Investments-non-controlled/non-affiliated Equity Investments [Industry] [Company] Investment [Type] Acquisition Date [Date]"
        """
        result = {
            'company_name': None,
            'industry': None,
            'investment_type': None,
            'maturity_date': None,
            'acquisition_date': None,
            'interest_rate': None,
            'reference_rate': None,
            'spread': None,
            'pik_rate': None
        }
        
        if not company_name:
            return result
        
        # Decode HTML entities
        company_name = company_name.replace('&amp;', '&')
        
        # Pattern 1: Full investment description with all details
        # "Investments-non-controlled/non-affiliated [Debt/Equity] Investments [Industry] [Company Name] Investment(s) [Type] ..."
        full_pattern = re.compile(
            r'Investments-non-controlled/non-affiliated\s+'
            r'(Debt|Equity)\s+Investments\s+'
            r'(.+?)\s+'  # Industry (greedy match until company name)
            r'([A-Z][A-Za-z0-9\s,&\.\(\)]+?)\s+'  # Company name (starts with capital, ends before "Investment")
            r'Investment(s)?\s+'
            r'(.+?)(?:\s+Reference\s+Rate|$|\s+Acquisition)',  # Investment type
            re.IGNORECASE | re.DOTALL
        )
        
        match = full_pattern.search(company_name)
        if match:
            investment_category = match.group(1)  # Debt or Equity
            industry = match.group(2).strip() if match.group(2) else ''
            company = match.group(3).strip() if match.group(3) else ''
            inv_type = match.group(5).strip() if match.group(5) else ''  # group(4) is "Investment(s)?", group(5) is the type
            
            # Clean up industry (remove trailing "Investment" if present)
            industry = re.sub(r'\s+Investment\s*$', '', industry, flags=re.IGNORECASE).strip()
            
            # Clean up company name (remove trailing "Investment" or "Investments")
            company = re.sub(r'\s+Investment(s)?\s*$', '', company, flags=re.IGNORECASE).strip()
            
            result['industry'] = industry
            result['company_name'] = company
            result['investment_type'] = inv_type
            
            # Extract reference rate and spread
            ref_spread_match = re.search(
                r'Reference\s+Rate\s+and\s+Spread\s+([A-Z]+)\s*\+\s*([\d\.]+)\s*%',
                company_name,
                re.IGNORECASE
            )
            if ref_spread_match:
                ref_rate = ref_spread_match.group(1).upper()
                spread_val = ref_spread_match.group(2)
                result['reference_rate'] = ref_rate
                result['spread'] = f"{spread_val}%"
            
            # Extract PIK rate if mentioned in spread
            pik_match = re.search(
                r'\(incl\.\s*([\d\.]+)\s*%\s*PIK\)',
                company_name,
                re.IGNORECASE
            )
            if pik_match:
                result['pik_rate'] = f"{pik_match.group(1)}%"
            
            # Extract interest rate
            int_rate_match = re.search(
                r'Interest\s+Rate\s+([\d\.]+)\s*%',
                company_name,
                re.IGNORECASE
            )
            if int_rate_match:
                result['interest_rate'] = f"{int_rate_match.group(1)}%"
            
            # Extract maturity date
            maturity_match = re.search(
                r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
                company_name,
                re.IGNORECASE
            )
            if maturity_match:
                result['maturity_date'] = maturity_match.group(1)
            
            # Extract acquisition date (for equity)
            acquisition_match = re.search(
                r'Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
                company_name,
                re.IGNORECASE
            )
            if acquisition_match:
                result['acquisition_date'] = acquisition_match.group(1)
        
        else:
            # Pattern 2: Simple debt commitment
            # "First Lien Debt [Company] Commitment Type [Type]"
            simple_debt_pattern = re.compile(
                r'(.+?)\s+Debt\s+'
                r'([A-Z][A-Za-z0-9\s,&\.\(\)]+?)\s+'
                r'Commitment\s+Type',
                re.IGNORECASE
            )
            
            match = simple_debt_pattern.search(company_name)
            if match:
                inv_type = match.group(1).strip()
                company = match.group(2).strip()
                result['investment_type'] = inv_type
                result['company_name'] = company
                
                # Try to extract maturity date from elsewhere in the string
                maturity_match = re.search(
                    r'(\d{1,2}/\d{1,2}/\d{4})',
                    company_name
                )
                if maturity_match:
                    result['maturity_date'] = maturity_match.group(1)
            else:
                # Pattern 3: Try to extract just company name and investment type
                # Look for common investment types
                inv_types = [
                    r'First\s+Lien\s+Debt',
                    r'Second\s+Lien\s+Debt',
                    r'Unitranche',
                    r'Senior\s+Secured',
                    r'Common\s+Equity',
                    r'Preferred\s+Equity',
                    r'Preferred\s+Stock',
                    r'Common\s+Stock',
                    r'Member\s+Units',
                    r'Warrants?'
                ]
                
                for inv_type_pattern in inv_types:
                    match = re.search(
                        rf'({inv_type_pattern}.*?)\s+([A-Z][A-Za-z0-9\s,&\.\(\)]+?)(?:\s+Investment|\s+Commitment|$)',
                        company_name,
                        re.IGNORECASE
                    )
                    if match:
                        result['investment_type'] = match.group(1).strip()
                        result['company_name'] = match.group(2).strip()
                        break
                
                # If still no company name, try to extract from start after common prefixes
                if not result['company_name']:
                    # Remove common prefixes
                    cleaned = re.sub(
                        r'^Investments-non-controlled/non-affiliated\s+[^/]+\s+Investments\s+',
                        '',
                        company_name,
                        flags=re.IGNORECASE
                    )
                    cleaned = re.sub(r'\s+Investment.*$', '', cleaned, flags=re.IGNORECASE)
                    # Try to find company name (usually capitalized words)
                    company_match = re.search(r'([A-Z][A-Za-z0-9\s,&\.\(\)]+?)(?:\s+Investment|\s+First|\s+Second|\s+Reference|$)', cleaned)
                    if company_match:
                        result['company_name'] = company_match.group(1).strip()
        
        return result
    
    def _extract_date_from_company_name(self, company_name: str) -> Optional[str]:
        """Extract date from company name if it contains 'Commitment Expiration Date'."""
        if not company_name:
            return None
        
        # Pattern: "Commitment Expiration Date MM/DD/YYYY"
        match = re.search(r'commitment\s+expiration\s+date\s+(\d{1,2}/\d{1,2}/\d{4})', company_name, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Also try: "Expiration Date MM/DD/YYYY"
        match = re.search(r'expiration\s+date\s+(\d{1,2}/\d{1,2}/\d{4})', company_name, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Also try: "Maturity MM/DD/YYYY" (in case it's in the name)
        match = re.search(r'maturity\s+(\d{1,2}/\d{1,2}/\d{4})', company_name, re.IGNORECASE)
        if match:
            return match.group(1)
        
        return None
    
    def _clean_company_name(self, company_name: str) -> str:
        """Remove commitment expiration date and other prefixes from company name."""
        if not company_name:
            return company_name
        
        # Remove "Commitment Expiration Date MM/DD/YYYY"
        cleaned = re.sub(r'commitment\s+expiration\s+date\s+\d{1,2}/\d{1,2}/\d{4}', '', company_name, flags=re.IGNORECASE)
        
        # Remove "Expiration Date MM/DD/YYYY"
        cleaned = re.sub(r'expiration\s+date\s+\d{1,2}/\d{1,2}/\d{4}', '', cleaned, flags=re.IGNORECASE)
        
        # Remove common prefixes
        prefixes_to_remove = [
            'investments - non-controlled/non-affiliated',
            'investments - non-controlled, non-affiliated',
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                cleaned = cleaned.lstrip(' :').strip()
        
        # Remove "Commitment Type" and related text
        # Pattern: "Commitment Type XXXX" -> remove
        cleaned = re.sub(r'commitment\s+type\s+[^:]+:', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra spaces and punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = cleaned.rstrip(' :').strip()
        
        return cleaned if cleaned else company_name
    
    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize date from various formats to YYYY-MM-DD."""
        if not date_str:
            return None
        
        # Remove dashes and clean up
        date_str = date_str.replace('—', '').strip()
        if not date_str or date_str == 'N/A':
            return None
        
        # Try MM/DD/YYYY format (common in XBRL)
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if match:
            month = match.group(1).zfill(2)
            day = match.group(2).zfill(2)
            year = match.group(3)
            return f"{year}-{month}-{day}"
        
        # Try MM/DD/YY format (2-digit year)
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2})$', date_str)
        if match:
            month = match.group(1).zfill(2)
            day = match.group(2).zfill(2)
            year = match.group(3)
            # Assume 20xx for years 00-50, 19xx for years 51-99
            year_int = int(year)
            full_year = f"20{year}" if year_int <= 50 else f"19{year}"
            return f"{full_year}-{month}-{day}"
        
        # Try YYYY-MM-DD format (already normalized)
        match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if match:
            return date_str
        
        # Try MM/YYYY format
        match = re.match(r'(\d{1,2})/(\d{4})', date_str)
        if match:
            month = match.group(1).zfill(2)
            year = match.group(2)
            return f"{year}-{month}-01"
        
        return date_str
    
    def _parse_html_table(self, html_url: str) -> List[Dict]:
        """Parse MSDL's HTML schedule of investments table (if available)."""
        
        logger.info(f"Fetching HTML from {html_url}")
        resp = requests.get(html_url, headers=self.headers)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables")
        
        # Look for schedule of investments table
        # MSDL may not have a detailed schedule table, so return empty list
        # The XBRL extraction should be sufficient
        
        return []
    
    def _merge_data(self, xbrl_investments: List[Dict], html_investments: List[Dict]) -> List[Dict]:
        """Merge XBRL and HTML data, preferring HTML for descriptive fields."""
        
        # For now, just return XBRL investments since HTML table may not be available
        # In the future, we could implement matching logic similar to other parsers
        return xbrl_investments
    
    def _save_to_csv(self, investments: List[Dict], output_file: str):
        """Save investments to CSV file."""
        fieldnames = [
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost_basis',
            'fair_value', 'interest_rate', 'reference_rate', 'spread', 'floor_rate',
            'pik_rate', 'shares_units', 'percent_net_assets'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for inv in investments:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(inv.get('investment_type', ''))
                standardized_industry = standardize_industry(inv.get('industry', ''))
                standardized_ref_rate = standardize_reference_rate(inv.get('reference_rate'))
                
                writer.writerow({
                    'company_name': inv.get('company_name', ''),
                    'industry': standardized_industry,
                    'business_description': inv.get('business_description', ''),
                    'investment_type': standardized_inv_type,
                    'acquisition_date': inv.get('acquisition_date'),
                    'maturity_date': inv.get('maturity_date'),
                    'principal_amount': inv.get('principal_amount'),
                    'cost_basis': inv.get('cost_basis'),
                    'fair_value': inv.get('fair_value'),
                    'interest_rate': inv.get('interest_rate'),
                    'reference_rate': standardized_ref_rate,
                    'spread': inv.get('spread'),
                    'floor_rate': inv.get('floor_rate'),
                    'pik_rate': inv.get('pik_rate'),
                    'shares_units': inv.get('shares_units'),
                    'percent_net_assets': inv.get('percent_net_assets')
                })


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = MSDLCustomExtractor()
    try:
        result = extractor.extract_from_ticker("MSDL")
        print(f"\n✓ Successfully extracted {result.total_investments} investments")
        print(f"  Total Principal: ${result.total_principal:,.0f}")
        print(f"  Total Cost: ${result.total_cost:,.0f}")
        print(f"  Total Fair Value: ${result.total_fair_value:,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()

