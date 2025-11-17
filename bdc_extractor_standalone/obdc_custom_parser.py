#!/usr/bin/env python3
"""
Custom OBDC (Blue Owl Capital Corp) Investment Extractor

OBDC uses HTML table parsing similar to GBDC/OFS/PSEC.
"""

import logging
import os
import re
import sys
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import csv
from collections import defaultdict

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class OBDCCustomExtractor:
    """Custom extractor for OBDC that parses HTML tables from SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "OBDC", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
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
        
        # Get XBRL URL for industry data
        match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
        if match:
            accession = match.group(1)
            accession_no_hyphens = accession.replace('-', '')
            txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
            logger.info(f"XBRL URL: {txt_url}")
        else:
            txt_url = None
        
        return self._parse_html_filing(main_html.url, cik, ticker, txt_url)
    
    def _parse_html_filing(self, htm_url: str, cik: str, ticker: str, xbrl_url: Optional[str] = None) -> Dict:
        """Parse investment data from HTML filing."""
        logger.info(f"Fetching HTML from {htm_url}")
        
        response = requests.get(htm_url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all investment schedule tables
        investment_tables = self._find_investment_tables(soup)
        
        if not investment_tables:
            logger.warning("No investment tables found")
            return {'company_name': 'Blue Owl Capital Corp', 'cik': cik, 'total_investments': 0, 'investments': []}
        
        logger.info(f"Found {len(investment_tables)} investment tables")
        
        # Parse all tables and combine
        all_investments = []
        current_industry = "Unknown"
        current_company = None
        current_business_desc = None
        
        for table_idx, table in enumerate(investment_tables):
            logger.info(f"Parsing table {table_idx + 1}/{len(investment_tables)}...")
            investments = self._parse_html_table(table, current_industry, current_company, current_business_desc)
            all_investments.extend(investments)
            
            # Update state for next table (carry forward company/industry/business desc)
            if investments:
                last_inv = investments[-1]
                if last_inv.get('company_name') and last_inv['company_name'] != 'Unknown':
                    current_company = last_inv['company_name']
                if last_inv.get('industry') and last_inv['industry'] != 'Unknown':
                    current_industry = last_inv['industry']
                if last_inv.get('business_description'):
                    current_business_desc = last_inv['business_description']
            
            logger.info(f"Extracted {len(investments)} investments from table {table_idx + 1}")
        
        # Enhance with XBRL data (industry and interest rates) if available
        if xbrl_url:
            try:
                # Extract industry data
                industry_map = self._extract_industries_from_xbrl(xbrl_url, all_investments)
                if industry_map:
                    logger.info(f"Found industry data for {len(industry_map)} investments from XBRL")
                    # Merge industry data
                    matched_count = 0
                    for inv in all_investments:
                        company_key = self._normalize_company_name(inv.get('company_name', ''))
                        if company_key in industry_map:
                            inv['industry'] = industry_map[company_key]
                            matched_count += 1
                        else:
                            # Try fuzzy matching
                            for xbrl_key, xbrl_industry in industry_map.items():
                                if self._companies_match(company_key, xbrl_key):
                                    inv['industry'] = xbrl_industry
                                    matched_count += 1
                                    break
                    logger.info(f"Matched industry data for {matched_count} investments")
                
                # Extract interest rate data
                rate_data_map = self._extract_interest_rates_from_xbrl(xbrl_url, all_investments)
                if rate_data_map:
                    logger.info(f"Found interest rate data for {len(rate_data_map)} investments from XBRL")
                    # Merge interest rate data
                    matched_count = 0
                    for inv in all_investments:
                        company_key = self._normalize_company_name(inv.get('company_name', ''))
                        if company_key in rate_data_map:
                            rate_data = rate_data_map[company_key]
                            if rate_data.get('interest_rate'):
                                inv['interest_rate'] = rate_data['interest_rate']
                            if rate_data.get('reference_rate'):
                                inv['reference_rate'] = rate_data['reference_rate']
                            if rate_data.get('spread'):
                                inv['spread'] = rate_data['spread']
                            if rate_data.get('floor_rate'):
                                inv['floor_rate'] = rate_data['floor_rate']
                            if rate_data.get('pik_rate'):
                                inv['pik_rate'] = rate_data['pik_rate']
                            matched_count += 1
                        else:
                            # Try fuzzy matching
                            for xbrl_key, rate_data in rate_data_map.items():
                                if self._companies_match(company_key, xbrl_key):
                                    if rate_data.get('interest_rate'):
                                        inv['interest_rate'] = rate_data['interest_rate']
                                    if rate_data.get('reference_rate'):
                                        inv['reference_rate'] = rate_data['reference_rate']
                                    if rate_data.get('spread'):
                                        inv['spread'] = rate_data['spread']
                                    if rate_data.get('floor_rate'):
                                        inv['floor_rate'] = rate_data['floor_rate']
                                    if rate_data.get('pik_rate'):
                                        inv['pik_rate'] = rate_data['pik_rate']
                                    matched_count += 1
                                    break
                    logger.info(f"Matched interest rate data for {matched_count} investments")
            except Exception as e:
                logger.warning(f"Failed to extract data from XBRL: {e}")
        
        # Calculate totals
        total_principal = sum(inv.get('principal_amount') or 0 for inv in all_investments)
        total_cost = sum(inv.get('cost') or 0 for inv in all_investments)
        total_fair_value = sum(inv.get('fair_value') or 0 for inv in all_investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in all_investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f'{ticker}_Blue_Owl_Capital_Corp_investments.csv')
        
        self._save_to_csv(all_investments, output_file)
        logger.info(f"Saved {len(all_investments)} investments to {output_file}")
        
        return {
            'company_name': 'Blue Owl Capital Corp',
            'cik': cik,
            'total_investments': len(all_investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
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
            
            if not in_schedule_section:
                continue
            
            # Check if table has investment-related headers
            header_text = ""
            for row in rows[:5]:
                cells = row.find_all(['td', 'th'])
                if cells:
                    header_text += " " + " ".join([self._extract_cell_text(cell).lower() for cell in cells])
            
            # Look for investment-related keywords in headers
            investment_keywords = [
                'portfolio company', 'company', 'investment', 'principal', 'cost', 'fair value',
                'amortized cost', 'interest rate', 'maturity', 'industry', 'business description'
            ]
            
            # Skip balance sheet/statement of assets/income statement tables
            skip_keywords = [
                'assets', 'liabilities', 'net asset value', 'statement of assets', 'balance sheet',
                'income', 'revenue', 'expense', 'earnings', 'dividend income', 'interest income',
                'realized gain', 'unrealized gain', 'net investment income', 'operations',
                'performance based', 'management fees', 'general and administrative'
            ]
            if any(skip_kw in header_text for skip_kw in skip_keywords):
                continue
            
            if any(kw in header_text for kw in investment_keywords):
                # Check if table has investment-specific data (company names, investment types)
                has_investment_data = False
                investment_type_keywords = ['first lien', 'second lien', 'senior secured', 'subordinated',
                                          'preferred', 'common', 'warrant', 'revolver', 'term loan']
                
                for row in rows[:30]:
                    cells = row.find_all(['td', 'th'])
                    row_text = " ".join([self._extract_cell_text(cell).lower() for cell in cells])
                    
                    # Check for investment type keywords
                    if any(it_kw in row_text for it_kw in investment_type_keywords):
                        has_investment_data = True
                        break
                    
                    # Check for company name patterns (not just numbers)
                    if len(cells) > 0:
                        first_cell = self._extract_cell_text(cells[0])
                        # Company names typically have letters and aren't just numbers/currency
                        if first_cell and any(c.isalpha() for c in first_cell) and not re.match(r'^[\d,\$\.\s]+$', first_cell):
                            # Check if it's not a balance sheet item
                            if not any(bs_item in first_cell.lower() for bs_item in ['assets', 'liabilities', 'net asset', 'total']):
                                has_investment_data = True
                                break
                
                if has_investment_data:
                    investment_tables.append(table)
                    logger.debug(f"Found investment table with {len(rows)} rows")
            
            # Stop if we've passed the schedule section
            if in_schedule_section:
                # Check if we've reached the end (look for "Total" or section end markers)
                table_text_lower = table.get_text().lower()
                if any(marker in table_text_lower for marker in ['total investments', 'end of schedule', 'reached end']):
                    logger.debug("Reached end of investment schedule")
                    break
        
        logger.info(f"Filtered to {len(investment_tables)} investment schedule tables")
        return investment_tables
    
    def _parse_html_table(self, table, current_industry: str, current_company: Optional[str], current_business_desc: Optional[str]) -> List[Dict]:
        """Parse a single HTML table."""
        rows = table.find_all('tr')
        if not rows:
            return []
        
        investments = []
        local_industry = current_industry
        local_company = current_company
        local_business_desc = current_business_desc
        
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
            
            # Check if this is an industry header row
            if self._is_industry_header(cell_texts):
                industry_col = column_map.get('company', 0)
                if len(cell_texts) > industry_col:
                    industry_text = cell_texts[industry_col].strip()
                    if industry_text and not industry_text.startswith('Total') and not industry_text.startswith('Subtotal'):
                        local_industry = self._clean_industry_name(industry_text)
                        logger.debug(f"Found industry: {local_industry}")
                continue
            
            # Check if this is a total/subtotal row
            if self._is_total_row(cell_texts):
                continue
            
            # Parse investment row
            investment = self._parse_investment_row(cells, cell_texts, column_map, local_company, local_industry, local_business_desc)
            if investment:
                investments.append(investment)
                # Update local state
                if investment.get('company_name') and investment['company_name'] != 'Unknown':
                    local_company = investment['company_name']
                if investment.get('industry') and investment['industry'] != 'Unknown':
                    local_industry = investment['industry']
                if investment.get('business_description'):
                    local_business_desc = investment['business_description']
        
        return investments
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if a row is a header row."""
        header_keywords = [
            'portfolio company', 'company', 'investment', 'principal', 'cost', 'fair value',
            'amortized cost', 'interest rate', 'maturity', 'industry', 'business description',
            'acquisition date', 'reference rate', 'spread', 'floor'
        ]
        
        combined_text = " ".join(cell_texts)
        matches = sum(1 for kw in header_keywords if kw in combined_text)
        return matches >= 3
    
    def _map_columns(self, header_texts: List[str]) -> Dict[str, int]:
        """Map column headers to field names."""
        column_map = {}
        combined_text = " ".join(header_texts)
        
        for idx, text in enumerate(header_texts):
            text_lower = text.lower()
            
            if 'company' in text_lower and 'portfolio' in text_lower:
                column_map['company'] = idx
            elif 'industry' in text_lower:
                column_map['industry'] = idx
            elif 'business' in text_lower and 'description' in text_lower:
                column_map['business_description'] = idx
            elif 'investment' in text_lower and 'type' in text_lower:
                column_map['investment_type'] = idx
            elif 'principal' in text_lower:
                column_map['principal'] = idx
            elif 'cost' in text_lower and 'amortized' in text_lower:
                column_map['cost'] = idx
            elif 'fair' in text_lower and 'value' in text_lower:
                column_map['fair_value'] = idx
            elif 'interest' in text_lower and 'rate' in text_lower:
                column_map['interest_rate'] = idx
            elif 'rate' in text_lower and ('coupon' in text_lower or 'current' in text_lower):
                column_map['interest_rate'] = idx
            elif 'spread' in text_lower:
                column_map['spread'] = idx
            elif 'floor' in text_lower:
                column_map['floor'] = idx
            elif 'pik' in text_lower:
                column_map['pik'] = idx
            elif 'reference' in text_lower and 'rate' in text_lower:
                column_map['reference_rate'] = idx
            elif 'spread' in text_lower:
                column_map['spread'] = idx
            elif 'maturity' in text_lower:
                column_map['maturity'] = idx
            elif 'acquisition' in text_lower:
                column_map['acquisition'] = idx
        
        # Default positions if not found - try to infer from data patterns
        # Based on OBDC output, it seems like:
        # Col 0: Company Name (correct)
        # Col 1: Might be business description or parent company (currently being read as industry)
        # Col 2: Investment Type (currently being read as business_description)
        # So we need to be smarter about detection
        
        if 'company' not in column_map:
            column_map['company'] = 0
        if 'industry' not in column_map:
            # Don't default industry - let it be detected from content
            pass
        if 'business_description' not in column_map:
            # Try col 1, but might need content-based detection
            column_map['business_description'] = 1
        if 'investment_type' not in column_map:
            column_map['investment_type'] = 2
        
        return column_map
    
    def _is_industry_header(self, cell_texts: List[str]) -> bool:
        """Check if a row is an industry header."""
        if not cell_texts:
            return False
        
        first_cell = cell_texts[0].strip() if cell_texts else ""
        
        # Industry headers are typically:
        # - All caps or title case
        # - No financial data
        # - Not company names (no LLC, Inc, etc.)
        # - Longer than 3 characters
        if len(first_cell) < 3:
            return False
        
        # Check if it's all caps or title case (but not a number or date)
        is_title_case = first_cell[0].isupper() if first_cell else False
        has_lowercase = any(c.islower() for c in first_cell)
        
        # Skip if it looks like a company name
        company_indicators = ['llc', 'inc', 'corp', 'ltd', 'lp', 'holdings', 'holdco', 'group']
        if any(ind in first_cell.lower() for ind in company_indicators):
            return False
        
        # Skip if it has financial data
        if re.search(r'\$|[\d,]+[MBK]', first_cell):
            return False
        
        # Skip common non-industry terms
        skip_terms = ['total', 'subtotal', 'portfolio company', 'company', 'investment', 'principal', 'cost', 'fair value']
        if any(term in first_cell.lower() for term in skip_terms):
            return False
        
        # If it's title case or all caps and no other cells have data, it's likely an industry header
        if is_title_case and len(cell_texts) > 1:
            # Check if other cells are mostly empty
            other_cells_have_data = any(
                re.search(r'\$|[\d,]+[MBK]|%', cell) 
                for cell in cell_texts[1:5] if cell.strip()
            )
            if not other_cells_have_data:
                return True
        
        return False
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if a row is a total/subtotal row."""
        if not cell_texts:
            return False
        
        first_cell = cell_texts[0].strip().lower()
        
        # Check for total/subtotal keywords
        total_keywords = ['total', 'subtotal', 'grand total']
        if any(keyword in first_cell for keyword in total_keywords):
            return True
        
        return False
    
    def _parse_investment_row(self, cells: List, cell_texts: List[str], column_map: Dict[str, int], 
                             current_company: Optional[str], current_industry: str, current_business_desc: Optional[str]) -> Optional[Dict]:
        """Parse an investment row."""
        try:
            # Get company name
            company_col = column_map.get('company', 0)
            company_text = cell_texts[company_col].strip() if len(cell_texts) > company_col else ""
            
            # Skip rows that look like income statement items
            if company_text and any(term in company_text.lower() for term in [
                'income', 'expense', 'revenue', 'earnings', 'dividend', 'interest income',
                'realized', 'unrealized', 'net investment', 'operations', 'fees', 'tax'
            ]):
                return None
            
            # Clean company name
            if company_text:
                company_text = re.sub(r'\s*\([^)]*\)\s*$', '', company_text)  # Remove trailing footnotes
                company_text = re.sub(r'[,\s]+$', '', company_text)  # Remove trailing commas/spaces
            else:
                company_text = current_company or "Unknown"
            
            # Skip if company name is still invalid
            if not company_text or company_text == "Unknown" or len(company_text) < 2:
                return None
            
            # Smart column detection based on content
            # OBDC structure seems to be: Company | Business Desc/Parent | Investment Type | ...
            # But the current mapping might be wrong, so let's detect based on content
            
            # Get industry - OBDC's HTML structure doesn't have a reliable industry column
            # Column 1 contains parent company names or investment categories, not industries
            # Since XBRL doesn't have industry either, we'll set to Unknown unless we find a clear industry
            industry = "Unknown"  # Default to Unknown since OBDC doesn't provide reliable industry data
            
            # Try to find industry in any column, but be very strict about what qualifies
            for col_idx in range(min(6, len(cell_texts))):
                text = cell_texts[col_idx].strip() if col_idx < len(cell_texts) else ""
                if not text:
                    continue
                
                # Skip if it looks like an investment category
                if any(cat_term in text.lower() for cat_term in [
                    'non-controlled', 'non-affiliated', 'affiliated', 'controlled',
                    'debt commitments', 'equity commitments', 'specialty finance',
                    'equity investment', 'debt investment'
                ]):
                    continue
                
                # Skip if it looks like a company name (has entity indicators)
                if any(company_indicator in text for company_indicator in [
                    'LLC', 'Inc.', 'Corp', 'Ltd', 'LP', 'Holdings', 'Holdco', 
                    'Bidco', 'Buyer', 'Limited', 'dba', 'Holdco'
                ]):
                    continue
                
                # Only accept if it has clear industry-like terms
                industry_keywords = [
                    'software', 'healthcare', 'technology', 'services', 'manufacturing',
                    'retail', 'finance', 'real estate', 'energy', 'media', 'consumer',
                    'industrial', 'business', 'professional', 'education', 'construction',
                    'aerospace', 'defense', 'automotive', 'chemicals', 'pharmaceuticals',
                    'telecommunications', 'utilities', 'transportation', 'hospitality'
                ]
                
                if any(term in text.lower() for term in industry_keywords):
                    # Make sure it's not too long (industries are usually short phrases)
                    if len(text.split()) <= 5:
                        industry = self._clean_industry_name(text)
                        break
            
            # Get business description - Column 1 in OBDC contains parent company names
            # which can serve as business description (e.g., "Aerosmith Bidco 1 Limited (dba Audiotonix)")
            # Try column 1 first, but also check other columns
            biz_desc_col = column_map.get('business_description', 1)
            business_desc = ""
            
            # Try to get from mapped column
            if biz_desc_col is not None and len(cell_texts) > biz_desc_col:
                potential_desc = cell_texts[biz_desc_col].strip()
                # Use if it looks like a parent company or business description
                # (has company indicators but different from the main company name)
                if potential_desc and potential_desc != company_text:
                    # Skip if it's an investment category
                    if not any(cat_term in potential_desc.lower() for cat_term in [
                        'non-controlled', 'non-affiliated', 'affiliated', 'controlled',
                        'debt commitments', 'equity commitments', 'specialty finance',
                        'equity investment', 'debt investment'
                    ]):
                        business_desc = potential_desc
            
            # Get investment type - try col 2, but check if it's actually in col 1 or 2
            inv_type_col = column_map.get('investment_type', 2)
            investment_type = cell_texts[inv_type_col].strip() if len(cell_texts) > inv_type_col else ""
            
            # If still empty, try other columns for business description (after we know inv_type_col)
            if not business_desc:
                for col_idx in range(min(6, len(cell_texts))):
                    if col_idx == company_col or (inv_type_col is not None and col_idx == inv_type_col):
                        continue
                    text = cell_texts[col_idx].strip() if col_idx < len(cell_texts) else ""
                    if text and text != company_text and len(text) > 3:
                        # Check if it looks like a company name or description (not investment type)
                        if any(indicator in text for indicator in ['LLC', 'Inc.', 'Corp', 'Ltd', 'LP', 'Limited', 'dba']):
                            if not any(cat_term in text.lower() for cat_term in [
                                'non-controlled', 'non-affiliated', 'affiliated', 'controlled',
                                'debt commitments', 'equity commitments', 'specialty finance'
                            ]):
                                business_desc = text
                                break
            
            # If investment type is empty, check other columns
            if not investment_type or investment_type == "Unknown":
                # Check if business_desc is actually investment type
                if business_desc and any(it_term in business_desc.lower() for it_term in [
                    'first lien', 'second lien', 'senior secured', 'revolving', 'term loan',
                    'preferred', 'common', 'warrant', 'equity', 'debt'
                ]):
                    investment_type = business_desc
                    business_desc = ""  # Clear it since it's actually investment type
                else:
                    # Check other columns
                    for col_idx in range(min(5, len(cell_texts))):
                        text = cell_texts[col_idx].strip() if col_idx < len(cell_texts) else ""
                        if any(it_term in text.lower() for it_term in [
                            'first lien', 'second lien', 'senior secured', 'revolving', 'term loan',
                            'preferred', 'common', 'warrant', 'equity', 'debt'
                        ]):
                            investment_type = text
                            break
            
            if not investment_type:
                investment_type = "Unknown"
            
            if not business_desc:
                business_desc = current_business_desc
            
            # Get financial values
            principal = self._extract_numeric_value(cells, column_map.get('principal', 7))
            cost = self._extract_numeric_value(cells, column_map.get('cost', 8))
            fair_value = self._extract_numeric_value(cells, column_map.get('fair_value', 9))
            
            # Skip rows with no financial data
            if not principal and not cost and not fair_value:
                return None
            
            # Get dates
            maturity_date = None
            acquisition_date = None
            maturity_col = column_map.get('maturity', None)
            if maturity_col is not None and len(cell_texts) > maturity_col:
                maturity_date = self._extract_date(cell_texts[maturity_col])
            acquisition_col = column_map.get('acquisition', None)
            if acquisition_col is not None and len(cell_texts) > acquisition_col:
                acquisition_date = self._extract_date(cell_texts[acquisition_col])
            
            # Get interest rate info - search all cells for percentage patterns
            interest_rate = None
            reference_rate = None
            spread = None
            floor_rate = None
            pik_rate = None
            
            # First, try the mapped interest rate column
            interest_col = column_map.get('interest_rate', None)
            if interest_col is not None and len(cell_texts) > interest_col:
                interest_text = cell_texts[interest_col]
                interest_rate, reference_rate, spread, floor_rate, pik_rate = self._parse_interest_rate(interest_text)
            
            # If not found, search all cells for rate information
            if not interest_rate and not reference_rate:
                combined_text = " ".join(cell_texts)
                interest_rate, reference_rate, spread, floor_rate, pik_rate = self._parse_interest_rate(combined_text)
            
            # Also search individual cells for percentage patterns (including XBRL)
            if not interest_rate:
                for cell_idx, cell in enumerate(cells):
                    # Try XBRL extraction first
                    xbrl_percent = self._extract_percentage_from_cell(cell)
                    if xbrl_percent:
                        # Check if this cell is likely an interest rate (not spread/floor/PIK)
                        cell_text = cell_texts[cell_idx].lower()
                        name_attr = ""
                        xbrl_tag = cell.find(['ix:nonfraction', 'nonfraction'])
                        if xbrl_tag:
                            name_attr = xbrl_tag.get('name', '').lower()
                        
                        # Skip if it's clearly spread, floor, or PIK
                        if not any(kw in cell_text or kw in name_attr for kw in ['spread', 'floor', 'pik', 'basis point', 'bps']):
                            rate_val = float(xbrl_percent.replace('%', ''))
                            if 0.1 <= rate_val <= 30:
                                interest_rate = xbrl_percent
                                break
                    
                    # Fall back to text pattern matching
                    cell_text = cell_texts[cell_idx]
                    rate_match = re.search(r'([\d\.]+)\s*%', cell_text)
                    if rate_match:
                        rate_val = float(rate_match.group(1))
                        # Reasonable interest rate range (0.1% to 30%)
                        if 0.1 <= rate_val <= 30:
                            # Skip if it's clearly a spread or floor (has keywords nearby)
                            cell_lower = cell_text.lower()
                            if not any(kw in cell_lower for kw in ['spread', 'floor', 'pik', 'basis point', 'bps']):
                                interest_rate = f"{rate_val:.2f}%"
                                break
            
            return {
                'company_name': company_text,
                'industry': industry,
                'business_description': business_desc,
                'investment_type': investment_type,
                'acquisition_date': acquisition_date,
                'maturity_date': maturity_date,
                'principal_amount': principal,
                'cost': cost,
                'fair_value': fair_value,
                'interest_rate': interest_rate,
                'reference_rate': reference_rate,
                'spread': spread,
                'floor_rate': floor_rate,
                'pik_rate': pik_rate
            }
        except Exception as e:
            logger.debug(f"Error parsing investment row: {e}")
            return None
    
    def _extract_numeric_value(self, cells: List, col_idx: int) -> Optional[float]:
        """Extract numeric value from a cell, handling XBRL tags."""
        if col_idx >= len(cells):
            return None
        
        cell = cells[col_idx]
        
        # Check for XBRL tags first
        xbrl_tag = cell.find(['ix:nonfraction', 'nonfraction'])
        if xbrl_tag:
            try:
                value_str = xbrl_tag.get_text(strip=True)
                if not value_str:
                    return None
                
                # Get scale attribute
                scale = int(xbrl_tag.get('scale', '0'))
                value = float(value_str.replace(',', ''))
                
                # Apply scale (scale=3 means thousands)
                if scale == 3:
                    value *= 1000
                elif scale == 6:
                    value *= 1000000
                
                return value
            except (ValueError, AttributeError):
                pass
        
        # Fallback to text parsing
        cell_text = self._extract_cell_text(cell)
        if not cell_text:
            return None
        
        # Remove $ and parse
        cell_text = cell_text.replace('$', '').replace(',', '').strip()
        
        # Handle suffixes (M, B, K)
        multiplier = 1
        if cell_text.endswith('M'):
            multiplier = 1000000
            cell_text = cell_text[:-1]
        elif cell_text.endswith('B'):
            multiplier = 1000000000
            cell_text = cell_text[:-1]
        elif cell_text.endswith('K'):
            multiplier = 1000
            cell_text = cell_text[:-1]
        
        try:
            value = float(cell_text) * multiplier
            return value if value != 0 else None
        except ValueError:
            return None
    
    def _extract_cell_text(self, cell) -> str:
        """Extract text from a cell, handling XBRL tags."""
        # Check for XBRL tags
        xbrl_tag = cell.find(['ix:nonfraction', 'nonfraction', 'ix:nonnumeric', 'nonnumeric'])
        if xbrl_tag:
            return xbrl_tag.get_text(strip=True)
        
        return cell.get_text(strip=True)
    
    def _extract_percentage_from_cell(self, cell) -> Optional[str]:
        """Extract percentage value from a cell, checking XBRL tags first."""
        # Check for XBRL nonfraction tags
        xbrl_tag = cell.find(['ix:nonfraction', 'nonfraction'])
        if xbrl_tag:
            value_text = xbrl_tag.get_text(strip=True)
            # Check if this is a percentage concept
            name = xbrl_tag.get('name', '').lower()
            if any(kw in name for kw in ['interestrate', 'spread', 'floor', 'pik']):
                try:
                    value = float(value_text.replace(',', ''))
                    # If value is > 1, it might be in basis points or already a percentage
                    if value > 1 and value < 100:
                        return f"{value:.2f}%"
                    elif value >= 100:
                        # Likely basis points, convert to percentage
                        return f"{value / 100:.2f}%"
                    else:
                        # Already a decimal percentage
                        return f"{value * 100:.2f}%"
                except (ValueError, TypeError):
                    pass
        
        # Fall back to text extraction
        cell_text = self._extract_cell_text(cell)
        rate_match = re.search(r'([\d\.]+)\s*%', cell_text)
        if rate_match:
            return f"{float(rate_match.group(1)):.2f}%"
        
        return None
    
    def _extract_date(self, date_text: str) -> Optional[str]:
        """Extract and normalize date."""
        if not date_text:
            return None
        
        # Try to parse common date formats
        date_patterns = [
            r'(\d{1,2})/(\d{1,2})/(\d{4})',  # MM/DD/YYYY
            r'(\d{4})-(\d{2})-(\d{2})',  # YYYY-MM-DD
            r'(\d{1,2})/(\d{1,2})/(\d{2})',  # MM/DD/YY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, date_text)
            if match:
                if len(match.groups()) == 3:
                    m, d, y = match.groups()
                    if len(y) == 2:
                        y = '20' + y
                    return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        
        return None
    
    def _parse_interest_rate(self, rate_text: str) -> tuple:
        """Parse interest rate string to extract rate, reference rate, spread, floor, PIK."""
        if not rate_text:
            return None, None, None, None, None
        
        interest_rate = None
        reference_rate = None
        spread = None
        floor_rate = None
        pik_rate = None
        
        # Try to extract percentage
        percent_match = re.search(r'(\d+\.?\d*)\s*%', rate_text)
        if percent_match:
            interest_rate = f"{percent_match.group(1)}%"
        
        # Try to extract reference rate (SOFR, PRIME, LIBOR, etc.)
        ref_rate_patterns = [
            r'(SOFR|PRIME|LIBOR|EURIBOR|CDOR|BBSW)\s*[+\-]?',
            r'([A-Z]{2,})\s*\+',
        ]
        for pattern in ref_rate_patterns:
            match = re.search(pattern, rate_text, re.IGNORECASE)
            if match:
                reference_rate = match.group(1).upper()
                break
        
        # Try to extract spread
        spread_match = re.search(r'[+\-]\s*(\d+\.?\d*)\s*%', rate_text)
        if spread_match:
            spread = f"{spread_match.group(1)}%"
        
        # Try to extract floor
        floor_match = re.search(r'floor[:\s]+(\d+\.?\d*)\s*%', rate_text, re.IGNORECASE)
        if floor_match:
            floor_rate = f"{floor_match.group(1)}%"
        
        # Try to extract PIK
        pik_match = re.search(r'PIK[:\s]+(\d+\.?\d*)\s*%', rate_text, re.IGNORECASE)
        if pik_match:
            pik_rate = f"{pik_match.group(1)}%"
        
        return interest_rate, reference_rate, spread, floor_rate, pik_rate
    
    def _extract_industries_from_xbrl(self, xbrl_url: str, investments: List[Dict]) -> Dict[str, str]:
        """Extract industry data from XBRL using EquitySecuritiesByIndustryAxis."""
        industry_map = {}
        
        try:
            response = requests.get(xbrl_url, headers=self.headers)
            response.raise_for_status()
            content = response.text
            
            # Extract contexts with InvestmentIdentifierAxis and EquitySecuritiesByIndustryAxis
            cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
            
            # Build a map of all company names from HTML investments for better matching
            html_companies = {}
            for inv in investments:
                company = inv.get('company_name', '').strip()
                if company and company != 'Unknown':
                    normalized = self._normalize_company_name(company)
                    html_companies[normalized] = company
            
            # Find investment identifiers and their industries
            for m in cp.finditer(content):
                cid = m.group(1)
                chtml = m.group(2)
                
                # Check for InvestmentIdentifierAxis
                inv_axis = re.search(
                    r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
                    r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
                    r'\s*</xbrldi:typedMember>', chtml, re.DOTALL)
                
                if not inv_axis:
                    continue
                
                identifier = inv_axis.group(1).strip()
                
                # Check for EquitySecuritiesByIndustryAxis or InvestmentIndustryAxis
                ind_axis = re.search(
                    r'<xbrldi:explicitMember[^>]*dimension="(?:us-gaap:)?(?:EquitySecuritiesByIndustryAxis|InvestmentIndustryAxis)"[^>]*>([^<]+)</xbrldi:explicitMember>',
                    chtml, re.DOTALL | re.IGNORECASE)
                
                if not ind_axis:
                    # Also try to find industry in the identifier itself
                    # Some companies embed industry in the identifier string
                    industry_in_ident = re.search(r'Industry[:\s]+([A-Za-z,&\s/]+?)(?:\s+Investment|\s+Type|$)', identifier_clean, re.IGNORECASE)
                    if industry_in_ident:
                        industry = self._clean_industry_name(industry_in_ident.group(1).strip())
                        if industry and industry != 'Unknown':
                            # Store by identifier for matching
                            normalized = self._normalize_company_name(identifier_clean.split(',')[0].split('-')[0].strip())
                            industry_map[normalized] = industry
                    continue
                
                industry = self._industry_member_to_name(ind_axis.group(1).strip())
                if not industry or industry == 'Unknown':
                    continue
                
                # Try to match identifier to HTML company names
                # Extract potential company name from identifier
                identifier_clean = identifier.strip()
                
                # Try different extraction methods
                potential_names = []
                
                # Method 1: First part before comma or dash
                name1 = identifier_clean.split(',')[0].split('-')[0].strip()
                name1 = re.sub(r'\s*\([^)]*\)\s*$', '', name1)  # Remove trailing parentheses
                if name1:
                    potential_names.append(name1)
                
                # Method 2: Look for common company patterns
                company_pattern = re.search(r'([A-Z][A-Za-z0-9\s,&\.\(\)\-]+?)(?:\s+(?:LLC|Inc\.?|Corp\.?|Ltd\.?|LP|Limited|Holdings|Holdco))', identifier_clean)
                if company_pattern:
                    potential_names.append(company_pattern.group(1).strip())
                
                # Method 3: Everything before " - " or " | "
                for sep in [' - ', ' | ', ' / ']:
                    if sep in identifier_clean:
                        potential_names.append(identifier_clean.split(sep)[0].strip())
                
                # Try to match with HTML companies
                matched = False
                for potential_name in potential_names:
                    normalized = self._normalize_company_name(potential_name)
                    
                    # Exact match
                    if normalized in html_companies:
                        industry_map[normalized] = industry
                        matched = True
                        break
                    
                    # Fuzzy match - check if any HTML company contains this name or vice versa
                    for html_norm, html_orig in html_companies.items():
                        if self._companies_match(normalized, html_norm):
                            industry_map[html_norm] = industry
                            matched = True
                            break
                    if matched:
                        break
                
                # If no match found, store by identifier for potential later matching
                if not matched and potential_names:
                    normalized = self._normalize_company_name(potential_names[0])
                    industry_map[normalized] = industry
            
            logger.info(f"Extracted {len(industry_map)} industry mappings from XBRL")
            return industry_map
        except Exception as e:
            logger.warning(f"Error extracting industries from XBRL: {e}")
            return {}
    
    def _industry_member_to_name(self, member: str) -> str:
        """Convert XBRL industry member to readable name."""
        # Remove namespace prefixes
        member = re.sub(r'^[^:]+:', '', member)
        # Convert camelCase to Title Case
        member = re.sub(r'([a-z])([A-Z])', r'\1 \2', member)
        return member.strip()
    
    def _extract_interest_rates_from_xbrl(self, xbrl_url: str, investments: List[Dict]) -> Dict[str, Dict]:
        """Extract interest rate data from XBRL facts."""
        rate_data_map = {}
        
        try:
            response = requests.get(xbrl_url, headers=self.headers)
            response.raise_for_status()
            content = response.text
            
            # Extract investment contexts
            contexts = {}
            cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
            tp = re.compile(
                r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
                r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
                r'\s*</xbrldi:typedMember>', re.DOTALL)
            
            for m in cp.finditer(content):
                cid = m.group(1)
                chtml = m.group(2)
                tm = tp.search(chtml)
                if tm:
                    identifier = tm.group(1).strip()
                    # Extract company name from identifier
                    company_name = identifier.split(',')[0].split('-')[0].strip()
                    company_name = re.sub(r'\s*\([^)]*\)\s*$', '', company_name)
                    normalized = self._normalize_company_name(company_name)
                    contexts[cid] = normalized
            
            # Extract facts
            facts = defaultdict(list)
            # Standard XBRL facts
            sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
            for match in sp.finditer(content):
                concept = match.group(1)
                cref = match.group(2)
                val = match.group(4)
                if val and cref:
                    facts[cref].append({'concept': concept, 'value': val.strip()})
            
            # Inline XBRL facts
            ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:unitRef="([^"]*)")?[^>]*?>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
            for m in ixp.finditer(content):
                name = m.group(1)
                cref = m.group(2)
                html = m.group(4)
                txt = re.sub(r'<[^>]+>', '', html).strip()
                if txt and cref:
                    facts[cref].append({'concept': name, 'value': txt})
            
            # Process facts for each context
            for ctx_id, company_key in contexts.items():
                if ctx_id not in facts:
                    continue
                
                rate_data = {}
                interest_rate_candidates = []
                
                for fact in facts[ctx_id]:
                    concept = fact['concept'].lower()
                    value = fact['value'].replace(',', '').strip()
                    
                    # Interest rate - check multiple concepts
                    # Some companies use different XBRL concepts for interest rates
                    is_interest_rate_concept = (
                        'interestrate' in concept and 
                        'paidincash' not in concept and 
                        'paidinkind' not in concept
                    ) or (
                        'coupon' in concept and 'rate' in concept
                    ) or (
                        'yield' in concept and 'rate' in concept
                    )
                    
                    if is_interest_rate_concept:
                        try:
                            rate_val = float(value)
                            original_val = rate_val
                            
                            # Try different conversion strategies
                            conversions = []
                            
                            # Strategy 1: Already percentage (5 = 5%)
                            conversions.append(('as_is', rate_val))
                            
                            # Strategy 2: Multiply by 100 (0.05 -> 5% or 5 -> 500%)
                            conversions.append(('x100', rate_val * 100))
                            
                            # Strategy 3: Multiply by 1000 (0.005 -> 5% or 0.0005 -> 0.5%)
                            if rate_val < 1:
                                conversions.append(('x1000', rate_val * 1000))
                            
                            # Strategy 4: Divide by 100 (500 -> 5%)
                            if rate_val >= 100:
                                conversions.append(('div100', rate_val / 100))
                            
                            # Strategy 5: Multiply by 10 (0.5 -> 5%)
                            if rate_val < 10:
                                conversions.append(('x10', rate_val * 10))
                            
                            # Find the best conversion (value in reasonable range 0.1% to 30%)
                            # But strongly prefer values in the 1-15% range
                            best_rate = None
                            best_method = None
                            for method, converted_val in conversions:
                                if 0.1 <= converted_val <= 30:
                                    # Strongly prefer values in the 1-15% range (most common for loans)
                                    if best_rate is None:
                                        best_rate = converted_val
                                        best_method = method
                                    elif 1 <= converted_val <= 15:
                                        # This is in the preferred range - always prefer this
                                        best_rate = converted_val
                                        best_method = method
                                    elif not (1 <= best_rate <= 15):
                                        # Neither is in preferred range, prefer higher
                                        if converted_val > best_rate:
                                            best_rate = converted_val
                                            best_method = method
                            
                            if best_rate:
                                interest_rate_candidates.append((best_rate, concept))
                        except (ValueError, TypeError):
                            pass
                
                # Use the best interest rate candidate
                if interest_rate_candidates:
                    # Prefer rates in the 1-15% range (most common for loans)
                    # If multiple candidates, prefer the one in the 1-15% range
                    best_candidate = None
                    for rate, concept_name in interest_rate_candidates:
                        if 1 <= rate <= 15:
                            if best_candidate is None or not (1 <= best_candidate <= 15):
                                best_candidate = rate
                            elif rate > best_candidate:
                                # If both in range, prefer higher (more likely correct)
                                best_candidate = rate
                    
                    # If no candidate in preferred range, take the highest reasonable one
                    if best_candidate is None:
                        # Sort by rate (descending) and take the highest
                        sorted_candidates = sorted(interest_rate_candidates, key=lambda x: x[0], reverse=True)
                        best_candidate = sorted_candidates[0][0]
                    
                    # Final check: if rate is < 1%, it's likely off by order of magnitude
                    # User feedback: 0.05% should be 5%, so multiply by 100
                    # Try progressively larger multipliers until we get a reasonable rate
                    if best_candidate < 1.0 and best_candidate > 0:
                        # Try x100, x1000, x10000 to find the best conversion
                        multipliers = [100, 1000, 10000]
                        best_corrected = best_candidate
                        for mult in multipliers:
                            corrected = best_candidate * mult
                            if 1 <= corrected <= 15:
                                # Perfect range for loans, use this
                                best_corrected = corrected
                                break
                            elif 0.5 <= corrected <= 30 and not (1 <= best_corrected <= 15):
                                # Reasonable range, use if we don't have a better one
                                best_corrected = corrected
                        
                        # Only use corrected rate if it's better than original
                        if 1 <= best_corrected <= 15 or (best_corrected >= 0.5 and best_candidate < 0.5):
                            best_candidate = best_corrected
                    
                    rate_data['interest_rate'] = f"{best_candidate:.2f}%"
                
                # Extract spread, floor, PIK, reference rate
                for fact in facts[ctx_id]:
                    concept = fact['concept'].lower()
                    value = fact['value'].replace(',', '').strip()
                    
                    # Spread
                    if 'spread' in concept or ('basis' in concept and 'point' in concept):
                        try:
                            spread_val = float(value)
                            # Convert basis points to percentage if > 10
                            if spread_val >= 10:
                                spread_val = spread_val / 100
                            rate_data['spread'] = f"{spread_val:.2f}%"
                        except (ValueError, TypeError):
                            pass
                    
                    # Floor rate
                    if 'floor' in concept:
                        try:
                            floor_val = float(value)
                            if floor_val >= 100:
                                floor_val = floor_val / 100
                            elif floor_val < 1:
                                floor_val = floor_val * 100
                            if 0 <= floor_val <= 10:
                                rate_data['floor_rate'] = f"{floor_val:.2f}%"
                        except (ValueError, TypeError):
                            pass
                    
                    # PIK rate
                    if 'pik' in concept or 'paidinkind' in concept:
                        try:
                            pik_val = float(value)
                            if pik_val >= 100:
                                pik_val = pik_val / 100
                            elif pik_val < 1:
                                pik_val = pik_val * 100
                            if 0 <= pik_val <= 30:
                                rate_data['pik_rate'] = f"{pik_val:.2f}%"
                        except (ValueError, TypeError):
                            pass
                    
                    # Reference rate (from identifier or fact)
                    if 'reference' in concept or 'index' in concept:
                        value_upper = value.upper()
                        if 'SOFR' in value_upper:
                            rate_data['reference_rate'] = 'SOFR'
                        elif 'LIBOR' in value_upper:
                            rate_data['reference_rate'] = 'LIBOR'
                        elif 'PRIME' in value_upper:
                            rate_data['reference_rate'] = 'PRIME'
                        elif 'EURIBOR' in value_upper:
                            rate_data['reference_rate'] = 'EURIBOR'
                
                # Also check identifier for reference rate and spread
                if ctx_id in contexts:
                    # Find the identifier for this context
                    for m in cp.finditer(content):
                        if m.group(1) == ctx_id:
                            identifier = ""
                            tm = tp.search(m.group(2))
                            if tm:
                                identifier = tm.group(1).strip()
                            
                            # Extract reference rate and spread from identifier
                            if identifier and not rate_data.get('reference_rate'):
                                ref_match = re.search(r'(SOFR|LIBOR|PRIME|Base Rate|EURIBOR)', identifier, re.IGNORECASE)
                                if ref_match:
                                    rate_data['reference_rate'] = ref_match.group(1).upper()
                            
                            if identifier and not rate_data.get('spread'):
                                spread_match = re.search(r'[+\-]\s*(\d+\.?\d*)\s*%', identifier)
                                if spread_match:
                                    spread_val = float(spread_match.group(1))
                                    rate_data['spread'] = f"{spread_val:.2f}%"
                            break
                
                if rate_data:
                    rate_data_map[company_key] = rate_data
            
            logger.info(f"Extracted interest rate data for {len(rate_data_map)} investments from XBRL")
            return rate_data_map
        except Exception as e:
            logger.warning(f"Error extracting interest rates from XBRL: {e}")
            return {}
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for matching."""
        if not name:
            return ''
        # Remove common suffixes and normalize
        name = re.sub(r'\s+(LLC|Inc\.?|Corp\.?|L\.P\.?|LP|Ltd\.?|Limited|Holdings|Holdco|Bidco|Buyer|Holdco)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[,\s]+', ' ', name).strip().lower()
        # Remove common prefixes
        name = re.sub(r'^(the\s+)', '', name, flags=re.IGNORECASE)
        return name
    
    def _companies_match(self, name1: str, name2: str) -> bool:
        """Check if two company names match (fuzzy)."""
        if not name1 or not name2:
            return False
        # Exact match
        if name1 == name2:
            return True
        # One contains the other (for cases like "Company" vs "Company, LLC")
        if name1 in name2 or name2 in name1:
            return True
        # Check if they share significant words
        words1 = set(name1.split())
        words2 = set(name2.split())
        if len(words1) > 0 and len(words2) > 0:
            common = words1.intersection(words2)
            # Need at least 2 common words, or if one name is short, 1 word is enough
            min_common = min(2, len(words1), len(words2))
            if len(common) >= min_common:
                return True
        return False
    
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
            'pik_rate'
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
                    'cost': inv.get('cost'),
                    'fair_value': inv.get('fair_value'),
                    'interest_rate': inv.get('interest_rate'),
                    'reference_rate': standardized_ref_rate,
                    'spread': inv.get('spread'),
                    'floor_rate': inv.get('floor_rate'),
                    'pik_rate': inv.get('pik_rate'),
                })


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = OBDCCustomExtractor()
    try:
        result = extractor.extract_from_ticker("OBDC")
        print(f"\n✓ Successfully extracted {result.get('total_investments', 0)} investments")
        print(f"  Total Principal: ${result.get('total_principal', 0):,.0f}")
        print(f"  Total Cost: ${result.get('total_cost', 0):,.0f}")
        print(f"  Total Fair Value: ${result.get('total_fair_value', 0):,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
