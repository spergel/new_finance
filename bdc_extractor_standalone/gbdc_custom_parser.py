#!/usr/bin/env python3
"""
GBDC (Golub Capital BDC Inc) Custom Investment Extractor
Fetches and parses investment data directly from SEC filings HTML tables.
"""

import os
import re
import logging
import csv
import requests
from typing import List, Dict, Optional
from collections import defaultdict
from bs4 import BeautifulSoup
from datetime import datetime

import sys
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate
from sec_api_client import SECAPIClient

logger = logging.getLogger(__name__)


class GBDCCustomExtractor:
    """Custom extractor for GBDC that fetches and parses HTML tables from SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "GBDC", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from GBDC's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker} from SEC filings")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        logger.info(f"Found CIK: {cik}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        logger.info(f"Filing index: {index_url}")
        
        # Get HTML URL
        documents = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
        if not main_html:
            raise ValueError("Could not find HTML document")
        
        htm_url = main_html.url
        logger.info(f"HTML URL: {htm_url}")
        
        # Parse HTML tables
        all_investments = self._parse_html_filing(htm_url)
        logger.info(f"Total investments extracted: {len(all_investments)}")
        
        # Calculate totals
        total_principal = sum(inv.get('principal_amount', 0) or 0 for inv in all_investments)
        total_cost = sum(inv.get('cost', 0) or 0 for inv in all_investments)
        total_fair_value = sum(inv.get('fair_value', 0) or 0 for inv in all_investments)
        
        # Industry and type breakdown
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        for inv in all_investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'GBDC_Golub_Capital_BDC_Inc_investments.csv')
        
        self._save_to_csv(all_investments, output_file)
        logger.info(f"Saved {len(all_investments)} investments to {output_file}")
        
        return {
            'company_name': 'Golub Capital BDC Inc',
            'cik': cik,
            'total_investments': len(all_investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _parse_html_filing(self, html_url: str) -> List[Dict]:
        """Parse investment data from HTML filing."""
        logger.info(f"Fetching HTML from {html_url}")
        
        response = requests.get(html_url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all investment schedule tables
        investment_tables = self._find_investment_tables(soup)
        
        if not investment_tables:
            logger.warning("No investment tables found")
            return []
        
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
        
        return all_investments
    
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
                                  'amortized cost', 'portfolio company', 'fair value']
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
                    'one stop', 'senior secured', 'second lien', 'subordinated',
                    'preferred equity', 'common equity', 'lp units', 'llc units'
                ])
                
                if in_schedule_section or has_investment_data:
                    investment_tables.append(table)
                    logger.debug(f"Added table with {len(rows)} rows (header at row {header_row_idx}, in_section={in_schedule_section}, has_data={has_investment_data})")
                else:
                    logger.debug(f"Skipped table with headers but no schedule section and no investment data")
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
        
        Returns list of investment dictionaries.
        Updates current_industry and current_company as it parses rows.
        """
        rows = table.find_all('tr')
        if not rows:
            return []
        
        investments = []
        # Use local variables that can be updated during parsing
        local_industry = current_industry
        local_company = current_company
        
        # Find header row to map columns
        header_row_idx = None
        column_map = {}
        
        for idx, row in enumerate(rows[:20]):
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
        
        # If no header found, use default column positions based on GBDC structure
        if not column_map:
            # Default: Col 0/1=Company, Col 2=Type, Col 4=Spread, Col 6=Rate, Col 8=Date, Col 10=Principal, Col 12=Cost
            column_map = {
                'company': 0,
                'investment_type': 2,
                'reference_rate': 4,
                'interest_rate': 6,
                'maturity_date': 8,
                'acquisition_date': 8,  # Some tables use Col 8 for acquisition
                'principal': 10,
                'cost': 12,
                'fair_value': 14
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
            
            # Check if this is an industry header row
            # In GBDC structure, industries appear in Col 1 (company column) as standalone rows
            company_col = column_map.get('company', 1)
            if len(cell_texts) > company_col:
                industry_text = cell_texts[company_col].strip()
                if self._is_industry_header(industry_text, cell_texts, column_map):
                    local_industry = self._clean_industry_name(industry_text)
                    logger.debug(f"Found industry: {local_industry}")
                    continue
            
            # Parse investment row
            investment = self._parse_investment_row(cells, cell_texts, column_map, local_company, local_industry)
            if investment:
                investments.append(investment)
                # Update current company and industry if we found them
                if investment.get('company_name') and investment['company_name'] != 'Unknown':
                    local_company = investment['company_name']
                if investment.get('industry') and investment['industry'] != 'Unknown':
                    local_industry = investment['industry']
        
        return investments
    
    def _extract_cell_text(self, cell) -> str:
        """Extract text from cell, handling XBRL tags."""
        # First try to get all text
        text = cell.get_text(' ', strip=True)
        
        # If empty, check for XBRL tags
        if not text or text.strip() == '':
            xbrl_tags = cell.find_all(['ix:nonfraction', 'ix:nonnumeric', 'nonfraction', 'nonnumeric'])
            if xbrl_tags:
                text = xbrl_tags[0].get_text(' ', strip=True)
        
        return text
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a header row."""
        header_keywords = ['investment type', 'spread above', 'interest rate', 
                          'maturity date', 'acquisition date', 'principal', 
                          'amortized cost', 'portfolio company', 'fair value']
        
        text_combined = ' '.join(cell_texts).lower()
        matches = sum(1 for keyword in header_keywords if keyword in text_combined)
        return matches >= 4
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a total row."""
        text_combined = ' '.join(cell_texts).lower()
        return ('total' in text_combined and 
                ('investments' in text_combined or 'assets' in text_combined or 'company' in text_combined))
    
    def _is_industry_header(self, text: str, cell_texts: List[str], column_map: Dict) -> bool:
        """Check if this is an industry header row."""
        if not text or len(text) < 3:
            return False
        
        # Skip if it's clearly not an industry
        if text.lower() in ['total', 'subtotal', 'investments', 'debt investments', 
                           'equity investments', 'non-controlled', 'affiliate']:
            return False
        
        # Industry headers are typically single lines in the company column (Col 1)
        # and don't have investment types or financial data in subsequent columns
        inv_type_col = column_map.get('investment_type', 2)
        has_investment_type = len(cell_texts) > inv_type_col and cell_texts[inv_type_col].strip()
        
        # Check for numeric data in financial columns (principal, cost, fair value)
        # But allow for percentage columns which might have numbers
        principal_col = column_map.get('principal', 15)
        cost_col = column_map.get('cost', 18)
        fv_col = column_map.get('fair_value', 23)
        has_financial_data = False
        for col_idx in [principal_col, cost_col, fv_col]:
            if col_idx and len(cell_texts) > col_idx:
                cell_val = cell_texts[col_idx].strip()
                # Check if it's a significant numeric value (not just a percentage or small number)
                if re.search(r'\d{4,}', cell_val):  # 4+ digits suggests financial amount
                    has_financial_data = True
                    break
        
        # Industry names are typically:
        # - Capitalized phrases (title case or all caps)
        # - 2-6 words
        # - No investment type in Col 2
        # - No significant financial data
        # - Common industry patterns like "Aerospace & Defense", "Auto Components", etc.
        is_industry = (
            len(text.split()) <= 6 and  # Reasonable length
            len(text.split()) >= 1 and  # At least one word
            not re.search(r'^\d', text) and  # Doesn't start with number
            not has_investment_type and  # No investment type in Col 2
            not has_financial_data and  # No significant financial data
            'Total' not in text and
            'Subtotal' not in text and
            (text[0].isupper() or text.isupper()) and  # Starts with capital or all caps
            'Inc.' not in text and  # Not a company name
            'LLC' not in text and  # Not a company name
            'Corp' not in text and  # Not a company name
            'Ltd' not in text  # Not a company name
        )
        
        return is_industry
    
    def _map_columns(self, header_cells: List[str]) -> Dict[str, int]:
        """Map column names to indices."""
        column_map = {}
        
        for idx, cell_text in enumerate(header_cells):
            cell_lower = cell_text.lower()
            
            if ('portfolio company' in cell_lower or 'company' in cell_lower) and 'company' not in column_map:
                column_map['company'] = idx
            elif 'investment type' in cell_lower:
                column_map['investment_type'] = idx
            elif 'spread above' in cell_lower or 'spread' in cell_lower:
                column_map['reference_rate'] = idx
            elif 'interest rate' in cell_lower:
                column_map['interest_rate'] = idx
            elif 'acquisition date' in cell_lower:
                column_map['acquisition_date'] = idx
            elif 'maturity date' in cell_lower:
                column_map['maturity_date'] = idx
            elif 'principal' in cell_lower or 'shares' in cell_lower:
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
        
        # Get company name - based on actual structure: Col 1 (not Col 0)
        company_col = column_map.get('company', 1)
        if len(cell_texts) > company_col:
            company_text = cell_texts[company_col].strip()
            # Clean company name (remove suffixes like +, <, #, etc. and footnotes)
            if company_text:
                # Remove common suffixes but keep the name
                # First remove footnote references like (7)(26) or (8)(9)(10)
                company_text = re.sub(r'\([^)]+\)', '', company_text).strip()
                # Remove trailing symbols like *+ but keep the main name
                company_text = re.sub(r'[#~&*<>\+\^]+$', '', company_text).strip()
                # Make sure it's not an investment type (like "One stop", "Senior secured", etc.)
                if company_text and company_text not in ['One stop', 'Senior secured', 'Second lien', 'Subordinated debt', 
                                                          'Preferred Equity', 'Common Equity', 'LP units', 'LLC units', 
                                                          'Warrants', 'Unknown'] and len(company_text) > 1:
                    investment['company_name'] = company_text
        
        # If no company name found in this row, use the current company (carry forward)
        if not investment.get('company_name') or investment['company_name'] == 'Unknown':
            if current_company:
                investment['company_name'] = current_company
            else:
                # Skip if no company name at all (might be a total row or section header)
                return None
        
        # Get investment type - based on actual structure: Col 2
        inv_type_col = column_map.get('investment_type', 2)
        if len(cell_texts) > inv_type_col:
            inv_type = cell_texts[inv_type_col].strip()
            if inv_type and inv_type != 'N/A':
                investment['investment_type'] = standardize_investment_type(inv_type)
        
        # Get reference rate and spread - based on actual structure: Col 4 (Spread Above Index label) and Col 5 (spread value)
        # Col 4 has "SF +", "E +", "SN +", "P +", "N/A", etc.
        # Col 5 has the spread percentage like "6.50%"
        ref_col = column_map.get('reference_rate', 4)
        spread_col = 5  # Always Col 5 based on actual structure
        
        if len(cell_texts) > ref_col:
            ref_text = cell_texts[ref_col].strip()
            if ref_text and ref_text != 'N/A':
                # Extract reference rate (SF = SOFR, E = EURIBOR, SN = SONIA, P = Prime, etc.)
                investment['reference_rate'] = standardize_reference_rate(ref_text)
        
        if len(cell_texts) > spread_col:
            spread_text = cell_texts[spread_col].strip()
            if spread_text and spread_text != 'N/A':
                spread_match = re.search(r'(\d+\.?\d*)\s*%', spread_text)
                if spread_match:
                    investment['spread'] = f"{spread_match.group(1)}%"
        
        # Get interest rate - based on actual structure: Col 8 (Interest Rate (2))
        rate_col = column_map.get('interest_rate', 8)
        if len(cell_texts) > rate_col:
            rate_text = cell_texts[rate_col].strip()
            if rate_text and rate_text != 'N/A':
                # Extract percentage
                rate_match = re.search(r'(\d+\.?\d*)\s*%', rate_text)
                if rate_match:
                    investment['interest_rate'] = f"{rate_match.group(1)}%"
        
        # Check for PIK - can be in Col 8 (after interest rate) or nearby columns
        # Look for "cash/X% PIK" pattern in nearby columns
        for check_col in [8, 9, 10]:
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
        
        # Get maturity date - based on actual structure: Col 13 (Maturity Date)
        for date_col in [13, 7, 8, 10]:
            if len(cell_texts) > date_col:
                date_text = cell_texts[date_col].strip()
                if date_text and date_text != 'N/A':
                    # Check if it's a date format (MM/YYYY or MM/DD/YYYY)
                    if re.match(r'\d{1,2}[/-]\d{2,4}', date_text):
                        investment['maturity_date'] = date_text
                        break
        
        # Get principal - based on actual structure: Col 15 or 16
        # Sometimes Col 15 has '$', value in Col 16; sometimes value directly in Col 15
        # Scale=3 means thousands
        for principal_col in [15, 16, 8, 10, 11]:
            if len(cells) > principal_col:
                principal_cell = cells[principal_col]
                cell_text = self._extract_cell_text(principal_cell).strip()
                # Skip if it's just a dollar sign or dash
                if cell_text in ('$', '—', '-', '–', ''):
                    continue
                principal_value = self._extract_numeric_value(principal_cell)
                if principal_value is not None and principal_value > 0:
                    investment['principal_amount'] = principal_value
                    break
        
        # Get cost (Amortized Cost) - based on actual structure: Col 18 or 20
        # Sometimes Col 19 has '$', value in Col 20; sometimes value directly in Col 18
        # Scale=3 means thousands
        for cost_col in [18, 20, 9, 12, 13]:
            if len(cells) > cost_col:
                cost_cell = cells[cost_col]
                cell_text = self._extract_cell_text(cost_cell).strip()
                # Skip if it's just a dollar sign
                if cell_text == '$':
                    continue
                cost_value = self._extract_numeric_value(cost_cell)
                if cost_value is not None and cost_value > 0:
                    investment['cost'] = cost_value
                    break
        
        # Get fair value - based on actual structure: Col 23 or 26
        # Sometimes Col 25 has '$', value in Col 26; sometimes value directly in Col 23
        # Scale=3 means thousands
        for fv_col in [23, 26, 11, 16, 14]:
            if len(cells) > fv_col:
                fv_cell = cells[fv_col]
                cell_text = self._extract_cell_text(fv_cell).strip()
                # Skip if it's just a dollar sign
                if cell_text == '$':
                    continue
                fv_value = self._extract_numeric_value(fv_cell)
                if fv_value is not None and fv_value > 0:
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
        
# Skip if no meaningful data at all
        # But don't skip if we have a valid company name and investment type (even if no financial data)
        has_financial_data = (investment.get('principal_amount') or 
                             investment.get('cost') or 
                             investment.get('fair_value'))
        has_valid_investment = (investment.get('investment_type') and 
                               investment.get('investment_type') != 'Unknown')
        
        # Filter out subtotal rows - these have "Unknown" investment type and large aggregated values
        # They're typically summary rows for a company
        principal = investment.get('principal_amount') or 0
        cost = investment.get('cost') or 0
        fv = investment.get('fair_value') or 0
        if (investment.get('investment_type') == 'Unknown' and 
            has_financial_data and
            (principal > 10000000 or  # > $10M suggests aggregate
             cost > 10000000 or
             fv > 10000000)):
            # This looks like a subtotal row, skip it
            return None
        
        # Only skip if we have neither financial data nor a valid investment type
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
                    # Scale 3 means thousands (e.g., 7,388 = 7,388,000)
                    # Scale 6 means millions
                    # Scale -2 means the value is already in base units
                    if scale == 6:  # Millions
                        return int(value * 1000000)
                    elif scale == 3:  # Thousands
                        return int(value * 1000)
                    elif scale == -2:  # Base units (percentages, etc.)
                        return int(value)
                    elif scale == 0:  # Base units
                        return int(value)
                    else:
                        # For other scales, calculate multiplier
                        return int(value * (10 ** scale))
                except (ValueError, TypeError):
                    pass
        
        # Fallback to text parsing
        text = cell.get_text(' ', strip=True)
        if not text or text in ('—', '-', '–', 'N/A', 'n/a', '', '—'):
            return None
        
        # Remove $ and commas
        text = text.replace('$', '').replace(',', '').strip()
        
        # Handle negative in parentheses
        is_negative = False
        if text.startswith('(') and text.endswith(')'):
            is_negative = True
            text = text[1:-1]
        
        # Handle suffixes (M=million, B=billion, K=thousand)
        multiplier = 1
        if text.upper().endswith('M'):
            multiplier = 1000000
            text = text[:-1]
        elif text.upper().endswith('B'):
            multiplier = 1000000000
            text = text[:-1]
        elif text.upper().endswith('K'):
            multiplier = 1000
            text = text[:-1]
        
        try:
            value = float(text)
            result = int(value * multiplier)
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
    
    def _save_to_csv(self, investments: List[Dict], output_file: str):
        """Save investments to CSV file."""
        fieldnames = [
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost',
            'fair_value', 'interest_rate', 'reference_rate', 'spread', 'floor_rate',
            'pik_rate', 'shares_units', 'percent_net_assets', 'currency',
            'commitment_limit', 'undrawn_commitment'
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


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = GBDCCustomExtractor()
    try:
        result = extractor.extract_from_ticker("GBDC")
        print(f"\nSuccessfully extracted {result.get('total_investments', 0)} investments")
        print(f"  Total Principal: ${result.get('total_principal', 0):,.0f}")
        print(f"  Total Cost: ${result.get('total_cost', 0):,.0f}")
        print(f"  Total Fair Value: ${result.get('total_fair_value', 0):,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
