#!/usr/bin/env python3
"""Custom parser for OFS Capital Corp that extracts investment data from HTML tables in SEC filings."""

import os
import re
import sys
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class OFSCustomExtractor:
    """
    Custom extractor for OFS that parses HTML tables from SEC filings.
    Similar to GBDC parser but adapted for OFS's specific table structure.
    """
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "OFS", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """
        Extract investments from 10-Q filing.
        
        Args:
            ticker: Company ticker symbol
            year: Year to filter filings (default: 2025). Set to None to get latest regardless of year.
            min_date: Minimum date in YYYY-MM-DD format (overrides year if provided)
        """
        logger.info(f"Extracting investments for {ticker} from SEC filings")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        logger.info(f"Found CIK: {cik}")
        
        # Get 10-Q filing (defaults to 2025, but can be overridden for historical data)
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        logger.info(f"Found 10-Q index for {ticker}: {index_url}")
        
        # Get main HTML document
        docs = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in docs if d.filename.lower().endswith('.htm') 
                         and 'index' not in d.filename.lower()), None)
        
        if not main_html:
            raise ValueError("Could not find main HTML document")
        
        logger.info(f"HTML URL: {main_html.url}")
        
        return self._parse_html_filing(main_html.url)
    
    def _parse_html_filing(self, htm_url: str) -> Dict:
        """Parse HTML filing and extract all investments."""
        logger.info(f"Fetching HTML from {htm_url}")
        resp = requests.get(htm_url, headers=self.headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Find investment schedule tables
        investment_tables = self._find_investment_tables(soup)
        logger.info(f"Found {len(investment_tables)} investment tables")
        
        # Parse all tables and combine
        all_investments = []
        current_industry = "Unknown"
        current_company = None
        
        for table_idx, table in enumerate(investment_tables):
            logger.info(f"Parsing table {table_idx + 1}/{len(investment_tables)}...")
            investments = self._parse_html_table(table, current_industry, current_company)
            all_investments.extend(investments)
            
            # Update state for next table (carry forward company/industry)
            if investments:
                last_inv = investments[-1]
                if last_inv.get('company_name') and last_inv['company_name'] != 'Unknown':
                    current_company = last_inv['company_name']
                if last_inv.get('industry') and last_inv['industry'] != 'Unknown':
                    current_industry = last_inv['industry']
            
            logger.info(f"Extracted {len(investments)} investments from table {table_idx + 1}")
        
        logger.info(f"Total investments extracted: {len(all_investments)}")
        
        # Calculate totals
        total_principal = sum(inv.get('principal_amount') or 0 for inv in all_investments)
        total_cost = sum(inv.get('cost') or 0 for inv in all_investments)
        total_fair_value = sum(inv.get('fair_value') or 0 for inv in all_investments)
        
        # Save to CSV
        output_file = self._save_to_csv(all_investments)
        logger.info(f"Saved {len(all_investments)} investments to {output_file}")
        
        return {
            'total_investments': len(all_investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value
        }
    
    def _find_investment_tables(self, soup: BeautifulSoup) -> List:
        """Find all investment schedule tables."""
        schedule_keywords = [
            'schedule of investments',
            'consolidated schedule',
            'portfolio of investments',
            'schedule of portfolio investments'
        ]
        
        investment_tables = []
        in_schedule_section = False
        
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            
            # Skip tiny tables
            if len(rows) < 10:
                continue
            
            # Check if we've reached the schedule section
            # Look in text before table AND in the table itself
            if not in_schedule_section:
                # Check text before table
                prev_text = ""
                for prev in table.find_all_previous(['p', 'div', 'h1', 'h2', 'h3', 'td', 'span', 'th']):
                    prev_text = prev.get_text().lower()
                    if any(kw in prev_text for kw in schedule_keywords):
                        in_schedule_section = True
                        logger.debug("Found investment schedule section")
                        break
                    if len(prev_text) > 1000:
                        break
                
                # Also check if table itself contains schedule keywords
                table_text = table.get_text().lower()
                if any(kw in table_text for kw in schedule_keywords):
                    in_schedule_section = True
                    logger.debug("Found investment schedule section in table")
            
            # Check if this table has investment data (either in schedule section OR has clear investment headers)
            has_headers = False
            header_row_idx = None
            for row_idx, row in enumerate(rows[:15]):
                # Use get_text(' ', strip=True) to preserve spaces for multi-word keywords
                row_text = row.get_text(' ', strip=True).lower()
                # Need multiple investment-related headers
                header_keywords = ['investment type', 'spread above', 'interest rate', 
                                  'maturity date', 'acquisition date', 'principal', 
                                  'amortized cost', 'portfolio company', 'fair value',
                                  'company name', 'portfolio']
                header_count = sum(1 for kw in header_keywords if kw in row_text)
                
                # Also check for actual column structure
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 8:
                    cell_texts = [c.get_text(' ', strip=True).lower() for c in cells]
                    cell_header_count = sum(1 for kw in header_keywords 
                                           for ct in cell_texts if kw in ct)
                    if cell_header_count >= 4:
                        has_headers = True
                        header_row_idx = row_idx
                        break
            
            # Include table if it has headers AND (we're in schedule section OR table has investment data)
            if has_headers:
                # Also check if table has actual investment data (company names, financial values)
                table_text = table.get_text().lower()
                has_investment_data = any(indicator in table_text for indicator in [
                    'first lien', 'second lien', 'senior secured', 'subordinated',
                    'preferred equity', 'common equity', 'common stock', 'preferred stock',
                    'warrants', 'units', 'revolver'
                ])
                
                if in_schedule_section or has_investment_data:
                    investment_tables.append(table)
                    logger.debug(f"Added table with {len(rows)} rows (header at row {header_row_idx}, in_section={in_schedule_section}, has_data={has_investment_data})")
            else:
                # If we're in schedule section but this table doesn't match, might be end
                if in_schedule_section:
                    table_text = table.get_text().lower()
                    if 'footnotes' in table_text[:500] or 'see notes' in table_text[:500]:
                        logger.debug("Reached end of investment schedule")
                        break
        
        logger.info(f"Filtered to {len(investment_tables)} investment schedule tables")
        return investment_tables
    
    def _parse_html_table(self, table, current_industry: str, current_company: Optional[str]) -> List[Dict]:
        """Parse a single HTML table.
        
        OFS structure:
        - Col 0: Company name (first row) OR Investment Type (subsequent rows)
        - Col 2: Industry (only in company name row)
        - Col 4: Interest Rate
        - Col 6: Reference Rate (SOFR+, PRIME+, etc.)
        - Col 7: Spread
        - Col 9: Acquisition Date
        - Col 11: Maturity Date
        - Col 14: Principal Amount (scale=3, thousands)
        - Col 18: Amortized Cost (scale=3, thousands)
        - Col 19: Fair Value (scale=3, thousands)
        """
        rows = table.find_all('tr')
        if not rows:
            return []
        
        investments = []
        local_industry = current_industry
        local_company = current_company
        
        # Find header row to map columns
        header_row_idx = None
        column_map = {}
        
        for idx, row in enumerate(rows[:10]):
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            cell_texts = [self._extract_cell_text(cell).lower() for cell in cells]
            
            # Check if this is the header row
            if self._is_header_row(cell_texts):
                header_row_idx = idx
                column_map = self._map_columns(cell_texts)
                logger.debug(f"Found header row at index {idx}, column map: {column_map}")
                break
        
        # Default column positions for OFS
        if not column_map:
            column_map = {
                'company': 0,
                'industry': 2,
                'investment_type': 0,  # Same as company column
                'interest_rate': 4,
                'reference_rate': 6,
                'spread': 7,
                'acquisition_date': 9,
                'maturity_date': 11,
                'principal': 14,
                'cost': 18,
                'fair_value': 19
            }
        
        # Parse data rows
        for row_idx, row in enumerate(rows):
            if header_row_idx is not None and row_idx <= header_row_idx:
                continue
            
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            cell_texts = [self._extract_cell_text(cell) for cell in cells]
            
            # Skip empty rows
            if not any(cell_texts):
                continue
            
            # Check if this is a total row
            if self._is_total_row(cell_texts):
                continue
            
            # Check if this is a section header (skip)
            if self._is_section_header(cell_texts):
                continue
            
            # Check if this is a company name row (has industry in Col 2)
            industry_col = column_map.get('industry', 2)
            if len(cell_texts) > industry_col and cell_texts[industry_col].strip():
                industry_text = cell_texts[industry_col].strip()
                company_text = cell_texts[0].strip() if len(cell_texts) > 0 else ""
                
                # Clean company name
                if company_text:
                    company_text = re.sub(r'\([^)]+\)', '', company_text).strip()  # Remove footnotes
                    company_text = re.sub(r'[#~&*<>\+\^]+$', '', company_text).strip()
                    
                    if company_text and len(company_text) > 1:
                        local_company = company_text
                        local_industry = self._clean_industry_name(industry_text)
                        logger.debug(f"Found company: {local_company}, industry: {local_industry}")
                continue
            
            # This should be an investment row (Col 0 has investment type, Col 2 is empty)
            investment = self._parse_investment_row(cells, cell_texts, column_map, local_company, local_industry)
            if investment:
                investments.append(investment)
        
        return investments
    
    def _extract_cell_text(self, cell) -> str:
        """Extract text from cell, handling XBRL tags."""
        text = cell.get_text(' ', strip=True)
        
        # If empty, check for XBRL tags
        if not text or text.strip() == '':
            xbrl_tags = cell.find_all(['ix:nonfraction', 'ix:nonnumeric', 'nonfraction', 'nonnumeric'])
            if xbrl_tags:
                text = xbrl_tags[0].get_text(' ', strip=True)
        
        return text
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a header row."""
        header_keywords = ['portfolio company', 'investment type', 'interest rate', 
                          'spread above', 'acquisition date', 'maturity', 
                          'principal amount', 'amortized cost', 'fair value', 'industry']
        
        text_combined = ' '.join(cell_texts).lower()
        matches = sum(1 for keyword in header_keywords if keyword in text_combined)
        return matches >= 4
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a total row."""
        text_combined = ' '.join(cell_texts).lower()
        return ('total' in text_combined and 
                ('investments' in text_combined or 'assets' in text_combined))
    
    def _is_section_header(self, cell_texts: List[str]) -> bool:
        """Check if this is a section header row."""
        if not cell_texts:
            return False
        first_cell = cell_texts[0].lower().strip()
        section_keywords = ['non-control', 'non-affiliate', 'debt and equity', 
                           'affiliate', 'control', 'investments']
        return any(kw in first_cell for kw in section_keywords)
    
    def _map_columns(self, header_cells: List[str]) -> Dict[str, int]:
        """Map column names to indices."""
        column_map = {}
        
        for idx, cell_text in enumerate(header_cells):
            cell_lower = cell_text.lower()
            
            if 'portfolio company' in cell_lower or ('company' in cell_lower and 'investment type' in cell_lower):
                column_map['company'] = idx
                column_map['investment_type'] = idx  # Same column in OFS
            elif 'industry' in cell_lower:
                column_map['industry'] = idx
            elif 'interest rate' in cell_lower:
                column_map['interest_rate'] = idx
            elif 'spread above' in cell_lower or 'spread' in cell_lower:
                column_map['spread'] = idx
            elif 'acquisition date' in cell_lower:
                column_map['acquisition_date'] = idx
            elif 'maturity' in cell_lower:
                column_map['maturity_date'] = idx
            elif 'principal' in cell_lower:
                column_map['principal'] = idx
            elif 'amortized cost' in cell_lower or 'cost' in cell_lower:
                column_map['cost'] = idx
            elif 'fair value' in cell_lower:
                column_map['fair_value'] = idx
        
        return column_map
    
    def _parse_investment_row(self, cells: List, cell_texts: List[str], column_map: Dict,
                              current_company: Optional[str], current_industry: str) -> Optional[Dict]:
        """Parse a single investment row."""
        investment = {
            'company_name': current_company or 'Unknown',
            'industry': current_industry,
            'business_description': '',
            'investment_type': 'Unknown',
            'acquisition_date': None,
            'maturity_date': None,
            'principal_amount': None,
            'cost': None,
            'fair_value': None,
            'interest_rate': None,
            'reference_rate': None,
            'spread': None,
            'floor_rate': None,
            'pik_rate': None,
            'shares_units': None,
            'percent_net_assets': None,
            'currency': 'USD',
            'commitment_limit': None,
            'undrawn_commitment': None,
        }
        
        # Skip if no company name
        if not current_company or current_company == 'Unknown':
            return None
        
        # Get investment type from Col 0
        inv_type_col = column_map.get('investment_type', 0)
        if len(cell_texts) > inv_type_col:
            inv_type = cell_texts[inv_type_col].strip()
            if inv_type and inv_type != 'N/A':
                # Clean investment type (remove footnotes)
                inv_type = re.sub(r'\([^)]+\)', '', inv_type).strip()
                investment['investment_type'] = standardize_investment_type(inv_type)
        
        # Get interest rate (Col 4)
        rate_col = column_map.get('interest_rate', 4)
        if len(cell_texts) > rate_col:
            rate_text = cell_texts[rate_col].strip()
            if rate_text and rate_text.lower() not in ('n/m', 'n/a', ''):
                rate_match = re.search(r'(\d+\.?\d*)\s*%', rate_text)
                if rate_match:
                    investment['interest_rate'] = f"{rate_match.group(1)}%"
        
        # Also check for PIK rate - can be in interest rate column or nearby
        for check_col in [rate_col, rate_col + 1, rate_col + 2]:
            if len(cell_texts) > check_col:
                check_text = ' '.join(cell_texts[max(0, check_col-1):min(len(cell_texts), check_col+3)])
                # Check for "cash/X% PIK" pattern
                pik_match = re.search(r'cash/\s*(\d+\.?\d*)\s*%\s*PIK', check_text, re.IGNORECASE)
                if pik_match:
                    investment['pik_rate'] = f"{pik_match.group(1)}%"
                    break
                # Also check for just "X% PIK"
                pik_match2 = re.search(r'(\d+\.?\d*)\s*%\s*PIK', check_text, re.IGNORECASE)
                if pik_match2:
                    investment['pik_rate'] = f"{pik_match2.group(1)}%"
                    break
        
        # Get reference rate (Col 6) - e.g., "SOFR+", "PRIME+"
        ref_col = column_map.get('reference_rate', 6)
        if len(cell_texts) > ref_col:
            ref_text = cell_texts[ref_col].strip()
            if ref_text and ref_text != 'N/A':
                investment['reference_rate'] = standardize_reference_rate(ref_text)
        
        # Get spread (Col 7)
        spread_col = column_map.get('spread', 7)
        if len(cell_texts) > spread_col:
            spread_text = cell_texts[spread_col].strip()
            if spread_text and spread_text != 'N/A':
                spread_match = re.search(r'(\d+\.?\d*)\s*%', spread_text)
                if spread_match:
                    investment['spread'] = f"{spread_match.group(1)}%"
        
        # Get acquisition date (Col 9) - check both text and XBRL
        acq_col = column_map.get('acquisition_date', 9)
        for check_col in [acq_col, 8, 9, 10]:
            if len(cells) > check_col:
                date_cell = cells[check_col]
                date_text = self._extract_cell_text(date_cell).strip()
                if date_text and re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_text):
                    investment['acquisition_date'] = date_text
                    break
        
        # Get maturity date (Col 11) - check both text and XBRL
        mat_col = column_map.get('maturity_date', 11)
        for check_col in [mat_col, 10, 11, 12]:
            if len(cells) > check_col:
                date_cell = cells[check_col]
                date_text = self._extract_cell_text(date_cell).strip()
                if date_text and re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_text):
                    investment['maturity_date'] = date_text
                    break
        
        # Get principal amount (Col 14, scale=3 means thousands)
        principal_col = column_map.get('principal', 14)
        for check_col in [principal_col, 13, 14, 15]:
            if len(cells) > check_col:
                principal_cell = cells[check_col]
                cell_text = self._extract_cell_text(principal_cell).strip()
                if cell_text in ('$', '—', '-', '–', ''):
                    continue
                principal_value = self._extract_numeric_value(principal_cell)
                if principal_value is not None and principal_value != 0:
                    investment['principal_amount'] = principal_value
                    break
        
        # Get cost (Col 18, scale=3 means thousands)
        cost_col = column_map.get('cost', 18)
        for check_col in [cost_col, 16, 17, 18, 19]:
            if len(cells) > check_col:
                cost_cell = cells[check_col]
                cell_text = self._extract_cell_text(cost_cell).strip()
                if cell_text in ('$', '—', '-', '–', ''):
                    continue
                cost_value = self._extract_numeric_value(cost_cell)
                if cost_value is not None:
                    investment['cost'] = cost_value
                    break
        
        # Get fair value (Col 19, scale=3 means thousands)
        fv_col = column_map.get('fair_value', 19)
        for check_col in [fv_col, 19, 20, 21]:
            if len(cells) > check_col:
                fv_cell = cells[check_col]
                cell_text = self._extract_cell_text(fv_cell).strip()
                if cell_text in ('$', '—', '-', '–', ''):
                    continue
                fv_value = self._extract_numeric_value(fv_cell)
                if fv_value is not None:
                    investment['fair_value'] = fv_value
                    break
        
        
        # Extract commitment_limit and undrawn_commitment for revolvers
        # Heuristic: If fair_value > principal_amount, it might be a revolver
        if investment.get('fair_value') and investment.get('principal_amount'):
            try:
                fv = int(investment['fair_value'])
                principal = int(investment['principal_amount'])
                if fv > principal:
                    investment['commitment_limit'] = fv
                    investment['undrawn_commitment'] = fv - principal
            except (ValueError, TypeError):
                pass
        elif investment.get('fair_value') and not investment.get('principal_amount'):
            # If we have fair value but no principal, might be a revolver commitment
            try:
                investment['commitment_limit'] = int(investment['fair_value'])
            except (ValueError, TypeError):
                pass
        
# Skip if no meaningful data
        has_financial_data = (investment.get('principal_amount') or 
                             investment.get('cost') or 
                             investment.get('fair_value'))
        has_valid_investment = (investment.get('investment_type') and 
                               investment.get('investment_type') != 'Unknown')
        
        # Filter out subtotal rows - these have "Unknown" investment type and aggregated values
        # In OFS, subtotal rows typically have "Unknown" type and sum up multiple investments
        principal = investment.get('principal_amount') or 0
        cost = investment.get('cost') or 0
        fv = investment.get('fair_value') or 0
        if (investment.get('investment_type') == 'Unknown' and 
            has_financial_data and
            (abs(principal) > 1000000 or  # > $1M suggests aggregate (lower threshold for OFS)
             abs(cost) > 1000000 or
             abs(fv) > 1000000)):
            # This looks like a subtotal row, skip it
            return None
        
        if not has_financial_data and not has_valid_investment:
            return None
        
        return investment
    
    def _extract_numeric_value(self, cell) -> Optional[int]:
        """Extract numeric value from cell (handles XBRL tags and text)."""
        # First try XBRL tags
        xbrl_tags = cell.find_all(['ix:nonfraction', 'nonfraction'])
        for tag in xbrl_tags:
            value_text = tag.get_text(strip=True)
            value_text = re.sub(r'[^\d\.\-]', '', value_text)
            if value_text and value_text not in ('—', '-', '–'):
                try:
                    value = float(value_text)
                    scale = int(tag.get('scale', '0'))
                    # Scale 3 means thousands
                    if scale == 6:  # Millions
                        return int(value * 1000000)
                    elif scale == 3:  # Thousands
                        return int(value * 1000)
                    elif scale == -2:  # Base units (percentages, etc.)
                        return int(value)
                    elif scale == 0:  # Base units
                        return int(value)
                    else:
                        return int(value * (10 ** scale))
                except (ValueError, TypeError):
                    pass
        
        # Fallback to text parsing
        text = cell.get_text(' ', strip=True)
        if not text or text in ('—', '-', '–', 'N/A', 'n/a', '', '—'):
            return None
        
        # Handle negative in parentheses
        is_negative = False
        if text.startswith('(') and text.endswith(')'):
            is_negative = True
            text = text[1:-1]
        
        # Remove $ and commas
        text = text.replace('$', '').replace(',', '').strip()
        
        try:
            value = float(text)
            result = int(value)
            return -result if is_negative else result
        except ValueError:
            return None
    
    def _clean_industry_name(self, industry: str) -> str:
        """Clean and standardize industry name."""
        if not industry:
            return "Unknown"
        
        industry = industry.strip()
        if not industry:
            return "Unknown"
        
        return standardize_industry(industry)
    
    def _save_to_csv(self, investments: List[Dict]) -> str:
        """Save investments to CSV file."""
        import csv
        
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'OFS_OFS_Capital_Corp_investments.csv')
        
        fieldnames = [
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost',
            'fair_value', 'interest_rate', 'reference_rate', 'spread', 'floor_rate',
            'pik_rate'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for inv in investments:
                writer.writerow({
                    'company_name': inv.get('company_name', ''),
                    'industry': inv.get('industry', 'Unknown'),
                    'business_description': inv.get('business_description', ''),
                    'investment_type': inv.get('investment_type', 'Unknown'),
                    'acquisition_date': inv.get('acquisition_date', ''),
                    'maturity_date': inv.get('maturity_date', ''),
                    'principal_amount': inv.get('principal_amount', ''),
                    'cost': inv.get('cost', ''),
                    'fair_value': inv.get('fair_value', ''),
                    'interest_rate': inv.get('interest_rate', ''),
                    'reference_rate': inv.get('reference_rate', ''),
                    'spread': inv.get('spread', ''),
                    'floor_rate': inv.get('floor_rate', ''),
                    'pik_rate': inv.get('pik_rate', ''),
                    'shares_units': inv.get('shares_units', ''),
                    'percent_net_assets': inv.get('percent_net_assets', ''),
                    'currency': inv.get('currency', 'USD'),
                    'commitment_limit': inv.get('commitment_limit', ''),
                    'undrawn_commitment': inv.get('undrawn_commitment', ''),
                })
        
        return output_file


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = OFSCustomExtractor()
    try:
        result = extractor.extract_from_ticker("OFS")
        print(f"\nSuccessfully extracted {result.get('total_investments', 0)} investments")
        print(f"  Total Principal: ${result.get('total_principal', 0):,.0f}")
        print(f"  Total Cost: ${result.get('total_cost', 0):,.0f}")
        print(f"  Total Fair Value: ${result.get('total_fair_value', 0):,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == '__main__':
    main()

