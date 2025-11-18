#!/usr/bin/env python3
"""
OCSL (Oaktree Specialty Lending Corp) Custom Investment Extractor
Parses investment data directly from SEC filings HTML.
"""

import os
import re
import logging
import csv
import requests
from typing import List, Dict, Optional
from collections import defaultdict
from bs4 import BeautifulSoup

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate
from sec_api_client import SECAPIClient

logger = logging.getLogger(__name__)


class OCSLCustomExtractor:
    """Custom extractor for OCSL that fetches and parses HTML tables from SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "OCSL", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from SEC filings."""
        logger.info(f"Extracting investments for {ticker} from SEC filings")
        
        # Get CIK
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        logger.info(f"Found CIK: {cik}")
        
        # Get latest 10-Q filing
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        logger.info(f"Filing index: {index_url}")
        
        # Get HTML document URL
        documents = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
        if not main_html:
            raise ValueError("Could not find HTML document")
        
        html_url = main_html.url
        logger.info(f"HTML URL: {html_url}")
        
        # Fetch and parse HTML
        all_investments = self._parse_html_filing(html_url)
        
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
        output_file = os.path.join(output_dir, 'OCSL_Oaktree_Specialty_Lending_Corp_investments.csv')
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate',
                'shares_units', 'percent_net_assets', 'currency', 'commitment_limit', 'undrawn_commitment'
            ])
            writer.writeheader()
            for inv in all_investments:
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
        
        logger.info(f"Saved {len(all_investments)} investments to {output_file}")
        
        return {
            'company_name': 'Oaktree Specialty Lending Corp',
            'cik': cik,
            'total_investments': len(all_investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _parse_html_filing(self, html_url: str) -> List[Dict]:
        """Parse investment tables from SEC filing HTML."""
        logger.info(f"Fetching HTML from: {html_url}")
        
        # Fetch HTML
        response = requests.get(html_url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get the filing date from the document to filter for current quarter
        filing_date = self._extract_filing_date(soup)
        logger.info(f"Filing date: {filing_date}")
        
        # Find all investment schedule tables
        investment_tables = self._find_investment_tables(soup)
        logger.info(f"Found {len(investment_tables)} investment tables")
        
        if not investment_tables:
            logger.warning("No investment tables found")
            return []
        
        # Parse all tables and combine
        all_investments = []
        for table_idx, table in enumerate(investment_tables):
            logger.info(f"Parsing table {table_idx + 1}...")
            # Check if table is for current period
            if not self._is_current_period_table(table, filing_date):
                logger.debug(f"Skipping table {table_idx + 1}: not current period")
                continue
            investments = self._parse_html_table(table)
            all_investments.extend(investments)
            logger.info(f"Extracted {len(investments)} investments from table {table_idx + 1}")
        
        return all_investments
    
    def _extract_filing_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract filing date from document."""
        # Look for date patterns in the document
        text = soup.get_text()
        # Look for "as of" or date patterns
        date_match = re.search(r'as of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', text, re.IGNORECASE)
        if date_match:
            return date_match.group(1)
        # Look for "September 30, 2025" pattern
        date_match = re.search(r'([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', text)
        if date_match:
            return date_match.group(1)
        return None
    
    def _is_current_period_table(self, table, filing_date: Optional[str]) -> bool:
        """Check if table is for current period (not prior period)."""
        table_text = table.get_text(' ', strip=True).lower()
        
        # Check for explicit prior period indicators in table headers/rows
        # Look for patterns like "Fair Value at October 1, 2024" or "September 30, 2024"
        prior_period_patterns = [
            r'fair value at\s+(october|september|march|december|june)\s+\d{1,2},\s+202[0-4]',
            r'(october|september|march|december|june)\s+\d{1,2},\s+202[0-4]',
            r'as of\s+(october|september|march|december|june)\s+\d{1,2},\s+202[0-4]',
        ]
        
        for pattern in prior_period_patterns:
            if re.search(pattern, table_text, re.IGNORECASE):
                # Check if current period is also mentioned (comparison table)
                if filing_date:
                    year_match = re.search(r'(\d{4})', filing_date)
                    if year_match:
                        current_year = year_match.group(1)
                        # If current year is also in the table, it's a comparison (include it)
                        if current_year in table_text:
                            continue
                        # Otherwise it's only prior period (skip it)
                        return False
        
        # If we have a filing date, check for prior period dates
        if filing_date:
            # Extract year from filing date
            year_match = re.search(r'(\d{4})', filing_date)
            if year_match:
                current_year = year_match.group(1)
                # Check for prior year dates
                prior_years = [str(int(current_year) - 1), str(int(current_year) - 2)]
                for prior_year in prior_years:
                    if prior_year in table_text and ('march 31' in table_text or 'december 31' in table_text or 'september 30' in table_text or 'june 30' in table_text):
                        # Check if it's explicitly a comparison column
                        if current_year in table_text:
                            # This is a comparison table, include it
                            continue
                        # Otherwise skip if it's only prior period
                        if prior_year in table_text and current_year not in table_text:
                            return False
        
        # Look for "March 31" or "December 31" without current year - likely prior period
        if 'march 31' in table_text or 'december 31' in table_text or 'september 30' in table_text:
            # If we see current year too, it's a comparison table (include it)
            if filing_date:
                year_match = re.search(r'(\d{4})', filing_date)
                if year_match:
                    current_year = year_match.group(1)
                    if current_year in table_text:
                        return True
                    # If only old dates, skip
                    prior_years = [str(int(current_year) - 1), str(int(current_year) - 2)]
                    if any(prior_year in table_text for prior_year in prior_years):
                        if current_year not in table_text:
                            return False
        
        return True
    
    def _find_investment_tables(self, soup: BeautifulSoup) -> List:
        """Find all investment schedule tables."""
        tables = []
        
        # Look for tables with "Portfolio Company" header - this is the key indicator for OCSL
        all_tables = soup.find_all('table')
        for table in all_tables:
            rows = table.find_all('tr')
            if len(rows) < 10:  # Skip very small tables
                continue
            
            # Check if table has "Portfolio Company" header
            table_text = table.get_text(' ', strip=True)
            has_portfolio_company = 'Portfolio Company' in table_text
            
            # Also check for other investment schedule indicators
            has_investment_keywords = any(keyword in table_text.lower() for keyword in [
                'type of investment',
                'industry',
                'principal',
                'cost',
                'fair value'
            ])
            
            # Skip tables that are clearly not investment schedules
            skip_keywords = [
                'table of contents',
                'consolidated balance sheets',
                'consolidated statements of operations',
                'consolidated statements of changes',
                'consolidated statements of cash flows',
                'fair value measurements',
                'level 3 hierarchy',
                'exhibit number',
                'outstanding balance',
                'debt issuance costs',
                'grant-date fair value',
                'net realized gain',
                'gross additions',
                'gross reductions',
                '% of total investments',
                '% of net assets',
                'amount of interest, fees or dividends credited',
                'fair value at october 1, 2024',
                'fair value at september 30, 2024',
                'fair value at march 31, 2024',
                'fair value at december 31, 2024'
            ]
            has_skip_keywords = any(keyword in table_text.lower() for keyword in skip_keywords)
            
            # Special case: if it has "Portfolio Company" as a header, it's an investment schedule
            if has_portfolio_company and 'portfolio company' in table_text.lower():
                # This is definitely an investment schedule, ignore skip keywords
                has_skip_keywords = False
            
            # Include if it has portfolio company header and investment keywords, and doesn't have skip keywords
            if has_portfolio_company and has_investment_keywords and not has_skip_keywords:
                tables.append(table)
        
        logger.info(f"Found {len(tables)} investment schedule tables with 'Portfolio Company' header")
        return tables
    
    def _parse_html_table(self, table) -> List[Dict]:
        """Parse a single HTML table."""
        rows = table.find_all('tr')
        if not rows:
            return []
        
        investments = []
        current_industry = "Unknown"
        current_company = None
        current_business_desc = None
        
        # Find header row to map columns
        header_row_idx = None
        column_map = {}
        
        for idx, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            cell_texts = [self._extract_cell_text(cell) for cell in cells]
            
            # Check if this is the header row
            if self._is_header_row(cell_texts):
                header_row_idx = idx
                column_map = self._map_columns(cell_texts)
                logger.debug(f"Found header row at index {idx}, column map: {column_map}")
                break
        
        # If no header found, use default column positions based on OCSL structure
        if not column_map:
            column_map = {
                'company': 0,
                'industry': 1,
                'investment_type': 2,
                'reference_rate': 3,
                'spread': 4,
                'interest_rate': 5,
                'pik': 6,
                'maturity_date': 7,
                'shares_units': 8,
                'principal': 9,
                'cost': 10,
                'fair_value': 11
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
            
            # Skip rows that are clearly not investments
            if self._should_skip_row(cell_texts):
                continue
            
            # Check if this is a total row (should be skipped)
            if self._is_total_row(cell_texts):
                continue
            
            # Check if this is an industry header row
            if self._is_industry_header(cell_texts, column_map):
                industry_col = column_map.get('industry', 1)
                if len(cell_texts) > industry_col:
                    industry_text = cell_texts[industry_col].strip()
                    if industry_text and not industry_text.startswith('Total') and not industry_text.startswith('Subtotal'):
                        current_industry = self._clean_industry_name(industry_text)
                        logger.debug(f"Found industry: {current_industry}")
                continue
            
            # Check if this is a company name row (has company name but no investment type)
            company_col = column_map.get('company', 0)
            investment_col = column_map.get('investment_type', 2)
            
            if len(cell_texts) > company_col:
                company_text = cell_texts[company_col].strip()
                investment_text = cell_texts[investment_col].strip() if len(cell_texts) > investment_col else ""
                
                # If we have a company name and no investment type, it's a new company
                if company_text and not investment_text and company_text != current_company:
                    current_company = company_text
                    # Update industry if present
                    industry_col = column_map.get('industry', 1)
                    if len(cell_texts) > industry_col:
                        industry_text = cell_texts[industry_col].strip()
                        if industry_text:
                            current_industry = self._clean_industry_name(industry_text)
                    continue
            
            # Parse investment row
            investment = self._parse_investment_row(cells, cell_texts, column_map, current_company, current_industry, current_business_desc)
            if investment:
                investments.append(investment)
                # Update current company if we found one in this row
                if investment.get('company_name') and investment['company_name'] != 'Unknown':
                    current_company = investment['company_name']
                if investment.get('industry') and investment['industry'] != 'Unknown':
                    current_industry = investment['industry']
                if investment.get('business_description'):
                    current_business_desc = investment['business_description']
        
        return investments
    
    def _extract_cell_text(self, cell) -> str:
        """Extract text from cell, handling XBRL tags."""
        # First try to get all text
        text = cell.get_text(' ', strip=True)
        
        # If empty or just whitespace, check for XBRL tags
        if not text or text.strip() == '':
            # Look for ix:nonfraction or ix:nonnumeric tags
            xbrl_tags = cell.find_all(['ix:nonfraction', 'ix:nonnumeric', 'nonfraction', 'nonnumeric'])
            if xbrl_tags:
                # Get text from first XBRL tag
                text = xbrl_tags[0].get_text(' ', strip=True)
        
        return text
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a header row."""
        header_keywords = ['Company', 'Industry', 'Investment', 'Type', 'Index', 'Spread', 
                          'Cash Interest', 'PIK', 'Maturity', 'Shares', 'Principal', 'Cost', 'Fair Value']
        
        text_combined = ' '.join(cell_texts).lower()
        matches = sum(1 for keyword in header_keywords if keyword.lower() in text_combined)
        return matches >= 5  # Need at least 5 header keywords
    
    def _should_skip_row(self, cell_texts: List[str]) -> bool:
        """Check if this row should be skipped (not an investment row)."""
        text_combined = ' '.join(cell_texts).lower()
        first_cell = cell_texts[0].strip().lower() if cell_texts else ""
        skip_patterns = [
            'item 1.', 'item 2.', 'item 3.', 'item 4.', 'item 5.', 'item 6.',
            'part i', 'part ii', 'consolidated statements', 'consolidated schedule',
            'notes to consolidated', 'management\'s discussion', 'legal proceedings',
            'risk factors', 'exhibits', 'signatures', 'page',
            'control investments', 'affiliate investments',
            'cash and cash equivalents', 'restricted cash', 'dividends and interest',
            'receivables:', 'liabilities', 'net assets', 'common stock',
            'additional paid-in capital', 'total distributable',
            'percentage of', 'weighted average', 'new investments', 'proceeds from sales',
            'principal repayments', 'realized gain', 'unrealized',
            'september 30,', 'march 31,', 'portfolio company', 'units', 'type',
            'escrow', 'income tax receivable', 'income tax payable', 'debt issuance costs',
            'other assets', 'other liabilities', 'notes (net of...', 'credit facilities',
            'investments at fair value:', 'other,', '^other$', '% of portfolio',
            'conversion/exchange', 'conversion of security', 'pik interest earned',
            'accretion of loan', 'distributions-in-kind',
            'net realized gain', 'gross additions', 'gross reductions',
            'fair value at', 'amount of interest', 'net asset value',
        ]
        for pattern in skip_patterns:
            if pattern.startswith('^') and pattern.endswith('$'):
                if re.match(pattern, first_cell):
                    return True
            elif pattern in text_combined or first_cell.startswith(pattern) or first_cell == pattern:
                return True
        if first_cell and len(first_cell) < 3:
            if first_cell.isdigit() or first_cell in ['3', '4', '5', '6', '7']:
                return True
        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', first_cell):
            return True
        if first_cell == 'unknown' and not any(re.search(r'\d+', cell) for cell in cell_texts[1:] if cell):
            return True
        return False
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a total/subtotal row."""
        text_combined = ' '.join(cell_texts).lower()
        total_patterns = [
            '^total', '^subtotal', 'total investments', 'total portfolio',
            'total debt', 'total equity', 'grand total',
            'total non-control', 'total control'
        ]
        first_cell = cell_texts[0].strip().lower() if cell_texts else ""
        for pattern in total_patterns:
            if pattern.startswith('^'):
                if re.match(pattern, first_cell):
                    return True
            elif pattern in text_combined:
                return True
        return False
    
    def _is_industry_header(self, cell_texts: List[str], column_map: Dict) -> bool:
        """Check if this is an industry header row."""
        company_col = column_map.get('company', 0)
        if len(cell_texts) <= company_col:
            return False
        
        company_text = cell_texts[company_col].strip()
        if not company_text:
            return False
        
        # Industry headers typically:
        # - Are all caps or title case
        # - Don't have investment type in the next column
        # - Don't have numeric values
        investment_col = column_map.get('investment_type', 2)
        has_investment_type = len(cell_texts) > investment_col and cell_texts[investment_col].strip()
        
        # Check if it looks like an industry name (not a company name)
        is_industry_format = (
            not has_investment_type and
            len(company_text) > 3 and
            (company_text.isupper() or company_text.istitle()) and
            not any(re.search(r'\d+', cell) for cell in cell_texts[1:] if cell) and
            company_text.lower() not in ['total', 'subtotal', 'other', 'control investments']
        )
        
        return is_industry_format
    
    def _clean_industry_name(self, industry_text: str) -> str:
        """Clean and standardize industry name."""
        industry_text = industry_text.strip()
        # Remove common prefixes
        industry_text = re.sub(r'^subtotal:\s*', '', industry_text, flags=re.IGNORECASE)
        industry_text = re.sub(r'^total:\s*', '', industry_text, flags=re.IGNORECASE)
        return standardize_industry(industry_text)
    
    def _map_columns(self, header_cells: List[str]) -> Dict[str, int]:
        """Map column names to indices."""
        column_map = {}
        
        for idx, cell_text in enumerate(header_cells):
            cell_lower = cell_text.lower()
            
            if 'company' in cell_lower and 'company' not in column_map:
                column_map['company'] = idx
            elif 'industry' in cell_lower and 'industry' not in column_map:
                column_map['industry'] = idx
            elif 'business' in cell_lower and 'description' in cell_lower:
                column_map['business_description'] = idx
            elif 'investment' in cell_lower and 'type' in cell_lower and 'investment_type' not in column_map:
                # Must have both "investment" and "type" in the header
                column_map['investment_type'] = idx
            elif 'index' in cell_lower and 'reference_rate' not in column_map:
                column_map['reference_rate'] = idx
            elif 'spread' in cell_lower:
                column_map['spread'] = idx
            elif 'cash' in cell_lower and ('interest' in cell_lower or 'rate' in cell_lower):
                column_map['interest_rate'] = idx
            elif 'pik' in cell_lower:
                column_map['pik'] = idx
            elif 'maturity' in cell_lower and 'date' in cell_lower:
                column_map['maturity_date'] = idx
            elif 'shares' in cell_lower or 'units' in cell_lower:
                column_map['shares_units'] = idx
            elif 'principal' in cell_lower:
                column_map['principal'] = idx
            elif 'cost' in cell_lower and 'fair' not in cell_lower:
                column_map['cost'] = idx
            elif 'fair' in cell_lower and 'value' in cell_lower:
                column_map['fair_value'] = idx
        
        return column_map
    
    def _parse_investment_row(self, cells: List, cell_texts: List[str], column_map: Dict,
                              current_company: Optional[str], current_industry: str,
                              current_business_desc: Optional[str]) -> Optional[Dict]:
        """Parse a single investment row."""
        investment = {
            'company_name': current_company or 'Unknown',
            'industry': current_industry,
            'business_description': current_business_desc or '',
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
        
        # Get company name (may be in this row or carried from previous)
        company_col = column_map.get('company', 0)
        if len(cell_texts) > company_col:
            company_text = cell_texts[company_col].strip()
            if company_text and company_text != 'Unknown' and not company_text.startswith('Subtotal'):
                investment['company_name'] = company_text
            elif current_company:
                investment['company_name'] = current_company
        
        # Skip if company name is invalid
        if investment['company_name'] in ['Unknown', 'Other', ''] or investment['company_name'].startswith('Subtotal'):
            return None
        
        # Skip if company name looks like a balance sheet item
        company_lower = investment['company_name'].lower()
        if any(pattern in company_lower for pattern in [
            'item ', 'net asset', 'assets', 'liabilities', 'equity', 'per share',
            'shares outstanding', 'number of shares', 'total assets', 'total liabilities',
            'consolidated', 'balance sheet', 'statement', 'schedule', 'exhibit',
            'control investments', 'total non-control', 'total portfolio'
        ]):
            return None
        
        # Check raw cells for financial data BEFORE extracting (to catch empty rows early)
        has_financial_data = False
        for cell in cells:
            cell_text = self._extract_cell_text(cell).strip()
            # Skip empty cells, dates, percentages, and text-only cells
            if not cell_text or cell_text in ['—', '-', '']:
                continue
            # Check for dollar amounts or numeric values (but not dates or percentages)
            if re.search(r'\$[\d,]+|^[\d,]+\.?\d*$', cell_text):
                # Make sure it's not a date or percentage
                if not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', cell_text) and '%' not in cell_text:
                    # Check if it's a meaningful number (not just a small number like "6" which might be shares)
                    # For shares, we'll allow small numbers, but for principal/cost/fair value, we need larger numbers
                    try:
                        num_val = float(cell_text.replace('$', '').replace(',', ''))
                        # If it's a large number (>= 1000) or shares column, it's financial data
                        if num_val >= 1000:
                            has_financial_data = True
                            break
                    except:
                        pass
        
        # Also check for shares/units in the shares column specifically
        shares_col = column_map.get('shares_units', 8)
        if shares_col is not None and len(cell_texts) > shares_col:
            shares_text = cell_texts[shares_col].strip()
            if shares_text and shares_text not in ['—', '-', '']:
                # Even small share counts count as financial data
                has_financial_data = True
        
        # If no financial data at all, skip this row
        if not has_financial_data:
            return None
        
        # Get industry
        industry_col = column_map.get('industry', 1)
        if len(cell_texts) > industry_col:
            industry_text = cell_texts[industry_col].strip()
            if industry_text and industry_text.lower() not in ['unknown', 'other', '']:
                investment['industry'] = self._clean_industry_name(industry_text)
        
        # Get business description
        biz_desc_col = column_map.get('business_description')
        if biz_desc_col is not None and len(cell_texts) > biz_desc_col:
            biz_desc = cell_texts[biz_desc_col].strip()
            if biz_desc:
                investment['business_description'] = biz_desc
        
        # Get investment type
        inv_type_col = column_map.get('investment_type', 2)
        if len(cell_texts) > inv_type_col:
            inv_type = cell_texts[inv_type_col].strip()
            # Skip if it looks like a date (MM/DD/YYYY format)
            if inv_type and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', inv_type):
                investment['investment_type'] = standardize_investment_type(inv_type)
        
        # Get reference rate (Index column)
        ref_col = column_map.get('reference_rate', 3)
        if len(cell_texts) > ref_col:
            ref_text = cell_texts[ref_col].strip()
            if ref_text:
                investment['reference_rate'] = standardize_reference_rate(ref_text)
        
        # Get spread
        spread_col = column_map.get('spread', 4)
        if len(cell_texts) > spread_col:
            spread_text = cell_texts[spread_col].strip()
            # Extract percentage
            spread_match = re.search(r'(\d+\.?\d*)\s*%', spread_text)
            if spread_match:
                investment['spread'] = f"{spread_match.group(1)}%"
        
        # Get interest rate (Cash Interest Rate column)
        interest_col = column_map.get('interest_rate', 5)
        if len(cell_texts) > interest_col:
            interest_text = cell_texts[interest_col].strip()
            # Extract percentage
            interest_match = re.search(r'(\d+\.?\d*)\s*%', interest_text)
            if interest_match:
                investment['interest_rate'] = f"{interest_match.group(1)}%"
        
        # Get PIK rate
        pik_col = column_map.get('pik', 6)
        if len(cell_texts) > pik_col:
            pik_text = cell_texts[pik_col].strip()
            # Extract percentage
            pik_match = re.search(r'(\d+\.?\d*)\s*%', pik_text)
            if pik_match:
                investment['pik_rate'] = f"{pik_match.group(1)}%"
        
        # Get maturity date
        mat_col = column_map.get('maturity_date', 7)
        if mat_col is not None and len(cell_texts) > mat_col:
            mat_text = cell_texts[mat_col].strip()
            # Check if it's a date
            if mat_text and re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', mat_text):
                investment['maturity_date'] = mat_text
        
        # Get shares/units
        shares_col = column_map.get('shares_units', 8)
        if shares_col is not None and len(cell_texts) > shares_col:
            shares_text = cell_texts[shares_col].strip()
            if shares_text:
                # Try to extract numeric value
                shares_match = re.search(r'(\d+(?:,\d{3})*)', shares_text.replace(',', ''))
                if shares_match:
                    investment['shares_units'] = shares_match.group(1).replace(',', '')
        
        # Get principal amount - search all cells for XBRL tags
        principal_value = None
        for cell in cells:
            principal_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentOwnedBalancePrincipalAmount')
            if principal_value is not None:
                # Check scale attribute
                scale_attr = cell.find(['ix:nonfraction', 'nonfraction'], {'name': re.compile('us-gaap:InvestmentOwnedBalancePrincipalAmount', re.I)})
                if scale_attr:
                    scale = scale_attr.get('scale', '0')
                    try:
                        scale_int = int(scale)
                        if scale_int == 3:  # thousands
                            investment['principal_amount'] = int(principal_value * 1000)
                        elif scale_int == 6:  # millions
                            investment['principal_amount'] = int(principal_value * 1000000)
                        else:
                            investment['principal_amount'] = int(principal_value)
                    except:
                        investment['principal_amount'] = int(principal_value)
                else:
                    investment['principal_amount'] = int(principal_value)
                break
        
        # If not found in XBRL, try from mapped column
        if not investment.get('principal_amount'):
            principal_col = column_map.get('principal', 9)
            if principal_col is not None and len(cell_texts) > principal_col:
                principal_text = cell_texts[principal_col].strip()
                if principal_text:
                    # Extract numeric value (remove $, commas, etc.)
                    principal_clean = principal_text.replace('$', '').replace(',', '').replace('(', '').replace(')', '').strip()
                    if principal_clean and principal_clean != '—' and principal_clean != '-':
                        try:
                            # OCSL uses thousands, so multiply by 1000
                            principal_val = float(principal_clean) * 1000
                            investment['principal_amount'] = int(principal_val)
                        except ValueError:
                            pass
        
        # Get cost - search all cells for XBRL tags
        cost_value = None
        for cell in cells:
            cost_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentOwnedAtCost')
            if cost_value is not None:
                # Check scale attribute
                scale_attr = cell.find(['ix:nonfraction', 'nonfraction'], {'name': re.compile('us-gaap:InvestmentOwnedAtCost', re.I)})
                if scale_attr:
                    scale = scale_attr.get('scale', '0')
                    try:
                        scale_int = int(scale)
                        if scale_int == 3:  # thousands
                            investment['cost'] = int(cost_value * 1000)
                        elif scale_int == 6:  # millions
                            investment['cost'] = int(cost_value * 1000000)
                        else:
                            investment['cost'] = int(cost_value)
                    except:
                        investment['cost'] = int(cost_value)
                else:
                    investment['cost'] = int(cost_value)
                break
        
        # If not found in XBRL, try from mapped column
        if not investment.get('cost'):
            cost_col = column_map.get('cost', 10)
            if cost_col is not None and len(cell_texts) > cost_col:
                cost_text = cell_texts[cost_col].strip()
                if cost_text:
                    # Extract numeric value
                    cost_clean = cost_text.replace('$', '').replace(',', '').replace('(', '').replace(')', '').strip()
                    if cost_clean and cost_clean != '—' and cost_clean != '-':
                        try:
                            # OCSL uses thousands, so multiply by 1000
                            cost_val = float(cost_clean) * 1000
                            investment['cost'] = int(cost_val)
                        except ValueError:
                            pass
        
        # Get fair value - search all cells for XBRL tags
        fair_value = None
        for cell in cells:
            fair_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentOwnedAtFairValue')
            if fair_value is not None:
                # Check scale attribute
                scale_attr = cell.find(['ix:nonfraction', 'nonfraction'], {'name': re.compile('us-gaap:InvestmentOwnedAtFairValue', re.I)})
                if scale_attr:
                    scale = scale_attr.get('scale', '0')
                    try:
                        scale_int = int(scale)
                        if scale_int == 3:  # thousands
                            investment['fair_value'] = int(fair_value * 1000)
                        elif scale_int == 6:  # millions
                            investment['fair_value'] = int(fair_value * 1000000)
                        else:
                            investment['fair_value'] = int(fair_value)
                    except:
                        investment['fair_value'] = int(fair_value)
                else:
                    investment['fair_value'] = int(fair_value)
                break
        
        # If not found in XBRL, try from mapped column
        if not investment.get('fair_value'):
            fair_col = column_map.get('fair_value', 11)
            if fair_col is not None and len(cell_texts) > fair_col:
                fair_text = cell_texts[fair_col].strip()
                if fair_text:
                    # Extract numeric value
                    fair_clean = fair_text.replace('$', '').replace(',', '').replace('(', '').replace(')', '').strip()
                    if fair_clean and fair_clean != '—' and fair_clean != '-':
                        try:
                            # OCSL uses thousands, so multiply by 1000
                            fair_val = float(fair_clean) * 1000
                            investment['fair_value'] = int(fair_val)
                        except ValueError:
                            pass
        
        # If investment type is still Unknown, try to infer it from the data
        if investment['investment_type'] == 'Unknown':
            # Check if this row has shares/units - likely equity
            if investment.get('shares_units'):
                investment['investment_type'] = 'Common Equity'
            # Check if there's cost/fair value but no principal - likely equity
            elif (investment.get('cost') or investment.get('fair_value')) and not investment.get('principal_amount'):
                # If there's no interest rate either, it's almost certainly equity
                if not investment.get('interest_rate'):
                    investment['investment_type'] = 'Common Equity'
                else:
                    # Has interest rate but no principal - might be preferred equity or other
                    investment['investment_type'] = 'Preferred Equity'
        
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
        
        return investment
    
    def _extract_numeric_value(self, cell, concept_name: str) -> Optional[float]:
        """Extract numeric value from XBRL tag in cell."""
        xbrl_tags = cell.find_all(['ix:nonfraction', 'nonfraction'])
        for tag in xbrl_tags:
            name_attr = tag.get('name', '')
            if concept_name.lower() in name_attr.lower():
                value_text = tag.get_text(strip=True)
                if value_text == '' or value_text == '—' or value_text == '-' or value_text == '—':
                    return None
                value_text = value_text.replace(',', '').replace('$', '').replace('(', '').replace(')', '')
                value_text = re.sub(r'[^\d\.\-]', '', value_text)
                if value_text == '' or value_text == '-':
                    return None
                try:
                    value = float(value_text)
                    sign_attr = tag.get('sign', '')
                    if sign_attr == '-':
                        value = -value
                    return value
                except ValueError:
                    return None
        return None


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = OCSLCustomExtractor()
    try:
        result = extractor.extract_from_ticker("OCSL")
        print(f"\nSuccessfully extracted {result.get('total_investments', 0)} investments")
        print(f"  Total Principal: ${result.get('total_principal', 0):,.0f}")
        print(f"  Total Cost: ${result.get('total_cost', 0):,.0f}")
        print(f"  Total Fair Value: ${result.get('total_fair_value', 0):,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
