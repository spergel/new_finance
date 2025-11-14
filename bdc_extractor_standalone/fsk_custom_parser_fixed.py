#!/usr/bin/env python3
"""
Custom FSK (FS KKR Capital Corp) Investment Extractor

Extracts investment data directly from HTML tables.
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
from datetime import datetime

logger = logging.getLogger(__name__)


class FSKCustomExtractor:
    """Custom extractor for FSK that properly handles their HTML table format."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.xbrl_extractor = TypedMemberExtractor(user_agent)
    
    def extract_from_ticker(self, ticker: str = "FSK") -> BDCExtractionResult:
        """Extract investments from FSK's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise RuntimeError("Could not resolve CIK for FSK")
        
        logger.info(f"Found CIK: {cik}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise RuntimeError("Could not locate latest 10-Q index for FSK")
        
        logger.info(f"Filing index: {index_url}")
        
        # Get URLs
        match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
        if not match:
            raise RuntimeError("Could not parse accession/URLs for FSK")
        
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
        
        return self.extract_from_filing(txt_url, htm_url, "FS KKR Capital Corp", cik, ticker)
    
    def extract_from_filing(self, txt_url: str, htm_url: str, company_name: str, cik: str, ticker: str = "FSK") -> BDCExtractionResult:
        """Extract complete FSK investment data from HTML tables."""
        
        logger.info(f"Starting FSK extraction from HTML...")
        
        # Extract from HTML tables (all data is in HTML)
        investments = self._parse_html_table(htm_url)
        logger.info(f"HTML extraction: {len(investments)} investments")
        
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
        
        return BDCExtractionResult(
            company_name=company_name,
            cik=cik,
            filing_date=None,
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
    
    def _parse_html_table(self, html_url: str) -> List[Dict]:
        """Parse FSK's HTML schedule of investments table."""
        
        logger.info(f"Fetching HTML from {html_url}")
        resp = requests.get(html_url, headers=self.headers)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables")
        
        # Filter tables to only Q3 2025 (September 30, 2025)
        target_date = "September 30, 2025"
        target_date_variants = ["september 30, 2025", "sep 30, 2025", "9/30/2025", "09/30/2025", "2025-09-30"]
        
        all_investments = []
        last_company = None
        last_industry = None
        
        for table_idx, table in enumerate(tables):
            rows = table.find_all('tr')
            if not rows:
                continue
            
            # Check if this is a schedule table
            is_schedule = self._is_schedule_table(rows)
            if not is_schedule:
                if table_idx < 5:  # Debug first few tables
                    header_text = " ".join([cell.get_text(" ", strip=True) for row in rows[:3] 
                                           for cell in row.find_all(['td', 'th'])]).lower()
                    logger.debug(f"Table {table_idx} not a schedule table. Header: {header_text[:100]}")
                continue
            
            logger.info(f"Found schedule table {table_idx} with {len(rows)} rows")
            
            # Check if this table is for the target period (Q3 2025)
            table_text = " ".join([cell.get_text(" ", strip=True) for row in rows[:20] 
                                  for cell in row.find_all(['td', 'th'])]).lower()
            
            # Skip if we see December 2024 explicitly
            if "december 31, 2024" in table_text or "12/31/2024" in table_text or "2024-12-31" in table_text:
                logger.debug(f"Skipping table with December 2024 date")
                continue
            
            # Check if table contains target date
            is_target_period = any(variant in table_text for variant in target_date_variants)
            
            # If no date found, assume it's current period (we're using latest filing)
            # But skip if we see other year-end dates
            if not is_target_period:
                if any(year in table_text for year in ["2024", "2023", "2022"]):
                    # Check if it's explicitly a year-end date
                    if "december" in table_text or "year end" in table_text or "ye " in table_text:
                        logger.debug(f"Skipping table with older year-end date")
                        continue
                # Otherwise assume it's current period
                is_target_period = True
            
            if not is_target_period:
                logger.debug(f"Skipping table: not for Q3 2025")
                continue
            
            logger.info(f"Processing schedule table with {len(rows)} rows (Q3 2025)")
            
            # Find header row
            header_row_idx = None
            for i, row in enumerate(rows[:10]):
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                if self._is_header_row(cell_texts):
                    header_row_idx = i
                    logger.debug(f"Found header at row {i}: {cell_texts[:5]}")
                    break
            
            if header_row_idx is None:
                logger.debug(f"Could not find header row, skipping table. First row: {[cell.get_text(strip=True) for cell in rows[0].find_all(['td', 'th'])[:5]]}")
                continue
            
            # Parse investments from this table
            for i, row in enumerate(rows[header_row_idx + 1:], start=header_row_idx + 1):
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                # Skip header, total, and section header rows
                if self._is_header_row(cell_texts) or self._is_total_row(cell_texts) or self._is_section_header(cell_texts):
                    continue
                
                # Parse investment row
                investment = self._parse_investment_row(cells, cell_texts, last_company, last_industry)
                if investment:
                    if investment.get('company_name'):
                        last_company = investment['company_name']
                    if investment.get('industry'):
                        last_industry = investment['industry']
                    all_investments.append(investment)
                elif len(all_investments) < 5:  # Debug first few failures
                    logger.debug(f"Failed to parse row {i}: {cell_texts[:5]}")
        
        return all_investments
    
    def _is_schedule_table(self, rows: List) -> bool:
        """Check if this is a schedule of investments table."""
        if not rows or len(rows) < 3:
            return False
        
        # Check first few rows for schedule indicators
        header_text = " ".join([cell.get_text(" ", strip=True) for row in rows[:10] 
                               for cell in row.find_all(['td', 'th'])]).lower()
        
        schedule_keywords = [
            'portfolio company', 'investment', 'principal', 'cost', 'fair value',
            'maturity', 'interest rate', 'reference rate', 'spread', 'company name',
            'amortized cost', 'par amount', 'loan', 'debt', 'equity'
        ]
        
        matches = sum(1 for keyword in schedule_keywords if keyword in header_text)
        # Also check if table has many columns (schedule tables are usually wide)
        if len(rows) > 0:
            first_row_cells = len(rows[0].find_all(['td', 'th']))
            if first_row_cells >= 10 and matches >= 2:
                return True
        
        return matches >= 3
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a table header row."""
        if not cell_texts:
            return False
        
        header_keywords = ['Portfolio Company', 'Footnotes', 'Industry', 'Rate', 'Floor', 
                          'Maturity', 'Principal', 'Amortized Cost', 'Fair Value']
        
        first_few = ' '.join(cell_texts[:8]).lower()
        return any(keyword.lower() in first_few for keyword in header_keywords)
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a total/summary row."""
        if not cell_texts:
            return False
        
        first_col = cell_texts[0].lower() if len(cell_texts) > 0 else ""
        return "total" in first_col
    
    def _is_section_header(self, cell_texts: List[str]) -> bool:
        """Check if this is a section header row."""
        if not cell_texts:
            return False
        
        first_col = cell_texts[0].lower() if len(cell_texts) > 0 else ""
        section_keywords = [
            'senior secured loans', 'first lien', 'second lien', 'subordinated',
            'control investments', 'non-control', 'non-affiliate', 'affiliate investments'
        ]
        
        # Also check if it's a percentage (section headers often have percentages like "126.4%")
        has_percentage = any('%' in cell for cell in cell_texts[:3])
        
        return any(keyword in first_col for keyword in section_keywords) or (has_percentage and len(first_col) < 50)
    
    def _parse_investment_row(self, cells: List, cell_texts: List[str], 
                             last_company: str, last_industry: str) -> Optional[Dict]:
        """Parse an investment row from FSK's HTML table.
        
        FSK table structure:
        - Column 0: Portfolio Company (company name)
        - Column 1: Footnotes
        - Column 2: Industry
        - Column 3: Reference Rate (SF, E, SA, SR, etc.)
        - Column 4: "+" (separator)
        - Column 5: Spread (e.g., "6.0%")
        - Column 6: Sometimes PIK rate info like "(0.0% PIK"
        - Column 7: Sometimes PIK rate continuation like "/ 3.3% PIK)"
        - Column 8: Floor (e.g., "0.8%")
        - Column 9: Maturity (MM/YYYY format, e.g., "11/2026")
        - Column 10: "$" or currency symbol
        - Column 11: Principal Amount (in millions)
        - Column 12: "$"
        - Column 13: Amortized Cost (in millions)
        - Column 14: "$"
        - Column 15: Fair Value (in millions)
        """
        
        try:
            # Get company name (column 0)
            company_name = cell_texts[0] if len(cell_texts) > 0 else ""
            if not company_name or company_name.strip() == "":
                company_name = last_company
            
            if not company_name:
                return None
            
            # Clean company name (remove footnotes in parentheses)
            company_name = re.sub(r'\s*\([^)]*\)', '', company_name).strip()
            
            # Get industry (column 2)
            industry = cell_texts[2] if len(cell_texts) > 2 else ""
            if not industry or industry.strip() == "":
                industry = last_industry or "Unknown"
            else:
                industry = industry.strip()
            
            # Extract reference rate and spread (columns 3-5)
            reference_rate = None
            spread = None
            floor_rate = None
            
            # Reference rate is in column 3 (SF, E, SA, SR, B, etc.)
            if len(cell_texts) > 3:
                ref_rate_text = cell_texts[3].strip()
                if ref_rate_text:
                    # Map common reference rates
                    ref_map = {
                        'SF': 'SOFR', 'E': 'EURIBOR', 'SA': 'SONIA', 
                        'SR': 'STIBOR', 'B': 'BBSW', 'L': 'LIBOR'
                    }
                    reference_rate = ref_map.get(ref_rate_text, ref_rate_text)
            
            # Spread is in column 5 (after "+" in column 4)
            interest_rate = None
            if len(cell_texts) > 5:
                spread_text = cell_texts[5].strip()
                if spread_text and '%' in spread_text:
                    spread = spread_text
                    # Also extract as interest rate
                    interest_rate = spread_text
                elif spread_text:
                    spread = spread_text + '%'
                    interest_rate = spread
            
            # Floor is in column 8
            if len(cell_texts) > 8:
                floor_text = cell_texts[8].strip()
                if floor_text and '%' in floor_text:
                    floor_rate = floor_text
                elif floor_text and floor_text.replace('.', '').isdigit():
                    floor_rate = floor_text + '%'
            
            # Extract PIK rate from columns 6-7 if present (e.g., "(0.0% PIK / 3.3% PIK)")
            pik_rate = None
            if len(cell_texts) > 6:
                # Combine columns 6-7 for PIK rate parsing
                pik_text = (cell_texts[6] + " " + cell_texts[7] if len(cell_texts) > 7 else cell_texts[6]).strip()
                if pik_text and 'PIK' in pik_text:
                    # Look for pattern like "(X.X% PIK / Y.Y% PIK)" - take the second one
                    pik_matches = re.findall(r'(\d+\.\d+)%\s*PIK', pik_text)
                    if pik_matches:
                        pik_rate = pik_matches[-1] + '%'  # Take the last PIK rate
            
            # Maturity date is in column 9 (MM/YYYY format)
            maturity_date = None
            if len(cell_texts) > 9:
                maturity_text = cell_texts[9].strip()
                if maturity_text and re.match(r'\d{1,2}/\d{4}', maturity_text):
                    # Convert MM/YYYY to MM/01/YYYY
                    match = re.match(r'(\d{1,2})/(\d{4})', maturity_text)
                    if match:
                        month = match.group(1).zfill(2)
                        year = match.group(2)
                        maturity_date = f"{month}/01/{year}"
            
            # Principal Amount: "$" in column 10, value in column 11 (in millions)
            principal = None
            if len(cell_texts) > 11:
                principal_text = cell_texts[11].strip()
                if principal_text and principal_text not in ['—', '', ' ']:
                    try:
                        principal = float(principal_text.replace(',', '')) * 1000000  # Convert millions to dollars
                    except (ValueError, TypeError):
                        pass
            
            # Amortized Cost: value in column 13 (in millions)
            cost = None
            if len(cell_texts) > 13:
                cost_text = cell_texts[13].strip()
                if cost_text and cost_text not in ['—', '', ' ']:
                    try:
                        cost = float(cost_text.replace(',', '')) * 1000000  # Convert millions to dollars
                    except (ValueError, TypeError):
                        pass
            
            # Fair Value: value in column 15 (in millions)
            fair_value = None
            if len(cell_texts) > 15:
                fv_text = cell_texts[15].strip()
                if fv_text and fv_text not in ['—', '', ' ']:
                    try:
                        fair_value = float(fv_text.replace(',', '')) * 1000000  # Convert millions to dollars
                    except (ValueError, TypeError):
                        pass
            
            # Determine investment type from section headers or default
            # FSK doesn't explicitly list investment type in each row, so we'll infer from context
            # or use a default based on the data structure
            investment_type = "Senior Secured Loan"  # Default, as most appear to be first lien loans
            
            # Must have at least principal or fair value to be a valid investment
            if not principal and not fair_value:
                return None
            
            return {
                'company_name': company_name,
                'business_description': "",
                'investment_type': investment_type,
                'industry': industry,
                'acquisition_date': None,  # FSK doesn't show acquisition dates in this table
                'maturity_date': maturity_date,
                'interest_rate': interest_rate,
                'reference_rate': reference_rate,
                'spread': spread,
                'floor_rate': floor_rate,
                'pik_rate': pik_rate,
                'principal_amount': principal,
                'cost_basis': cost,
                'fair_value': fair_value,
                'shares_units': None,
                'percent_net_assets': None
            }
        
        except Exception as e:
            logger.warning(f"Failed to parse row: {e}")
            return None
    
    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize date from various formats to MM/DD/YYYY."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Try MM/DD/YYYY format
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if match:
            month = match.group(1).zfill(2)
            day = match.group(2).zfill(2)
            year = match.group(3)
            return f"{month}/{day}/{year}"
        
        # Try MM/YYYY format
        match = re.match(r'(\d{1,2})/(\d{4})', date_str)
        if match:
            month = match.group(1).zfill(2)
            year = match.group(2)
            return f"{month}/01/{year}"
        
        return date_str
    
    def save_results(self, result: BDCExtractionResult, output_dir: str = 'output'):
        """Save extraction results."""
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_dir)
        os.makedirs(output_dir, exist_ok=True)
        
        # Save CSV
        csv_file = os.path.join(output_dir, 'FS_KKR_Capital_Corp_investments.csv')
        fieldnames = [
            'company_name', 'business_description', 'investment_type', 'industry',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost_basis',
            'fair_value', 'interest_rate', 'reference_rate', 'spread', 'floor_rate',
            'eot_rate', 'pik_rate', 'percent_net_assets'
        ]
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for inv in result.investments:
                writer.writerow({
                    'company_name': inv.get('company_name', ''),
                    'business_description': inv.get('business_description', ''),
                    'investment_type': standardize_investment_type(inv.get('investment_type', 'Unknown')),
                    'industry': standardize_industry(inv.get('industry', 'Unknown')),
                    'acquisition_date': inv.get('acquisition_date', ''),
                    'maturity_date': inv.get('maturity_date', ''),
                    'principal_amount': inv.get('principal_amount', ''),
                    'cost_basis': inv.get('cost_basis', ''),
                    'fair_value': inv.get('fair_value', ''),
                    'interest_rate': inv.get('interest_rate', ''),
                    'reference_rate': standardize_reference_rate(inv.get('reference_rate', '')),
                    'spread': inv.get('spread', ''),
                    'floor_rate': inv.get('floor_rate', ''),
                    'eot_rate': inv.get('eot_rate', ''),
                    'pik_rate': inv.get('pik_rate', ''),
                    'percent_net_assets': inv.get('percent_net_assets', '')
                })
        
        logger.info(f"Saved CSV to {csv_file}")


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = FSKCustomExtractor()
    result = extractor.extract_from_ticker("FSK")
    
    extractor.save_results(result)
    
    print(f"\n[SUCCESS] Extracted {result.total_investments} investments for FS KKR Capital Corp")
    print(f"  Total Cost: ${result.total_cost:,.0f}")
    print(f"  Total Fair Value: ${result.total_fair_value:,.0f}")


if __name__ == "__main__":
    main()

