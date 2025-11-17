#!/usr/bin/env python3
"""
CSWC (Capital Southwest Corporation) Custom Investment Extractor
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


class CSWCCustomExtractor:
    """Custom extractor for CSWC that fetches and parses HTML tables from SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "CSWC"), year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
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
        output_file = os.path.join(output_dir, 'CSWC_Capital_Southwest_Corp_investments.csv')
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate',
                'shares_units', 'percent_net_assets', 'currency', 'commitment_limit', 'undrawn_commitment', 'shares_units'
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
                })
        
        logger.info(f"Saved {len(all_investments)} investments to {output_file}")
        
        return {
            'company_name': 'Capital Southwest Corp',
            'cik': '17313',
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
        
        # If we have a filing date, check for prior period dates
        if filing_date:
            # Extract year from filing date
            year_match = re.search(r'(\d{4})', filing_date)
            if year_match:
                current_year = year_match.group(1)
                # Check for prior year dates
                prior_years = [str(int(current_year) - 1), str(int(current_year) - 2)]
                for prior_year in prior_years:
                    if prior_year in table_text and ('march 31' in table_text or 'december 31' in table_text):
                        # Check if it's explicitly a comparison column
                        if 'march 31' in table_text and current_year in table_text:
                            # This is a comparison table, include it
                            continue
                        # Otherwise skip if it's only prior period
                        if prior_year in table_text and current_year not in table_text:
                            return False
        
        # Look for "March 31" or "December 31" without current year - likely prior period
        if 'march 31' in table_text or 'december 31' in table_text:
            # If we see current year too, it's a comparison table (include it)
            if filing_date and any(year in table_text for year in ['2025', '2024']):
                return True
            # If only old dates, skip
            if '2023' in table_text or '2022' in table_text:
                if '2024' not in table_text and '2025' not in table_text:
                    return False
        
        return True
    
    def _find_investment_tables(self, soup: BeautifulSoup) -> List:
        """Find all investment schedule tables."""
        tables = []
        
        # Look for tables with investment schedule keywords
        all_tables = soup.find_all('table')
        for table in all_tables:
            table_text = table.get_text(' ', strip=True).lower()
            # Check for investment schedule indicators
            if any(keyword in table_text for keyword in [
                'schedule of investments',
                'portfolio company',
                'type of investment',
                'fair value',
                'amortized cost',
                'principal amount'
            ]):
                # Make sure it's substantial (not just a header)
                rows = table.find_all('tr')
                if len(rows) > 5:  # At least 5 rows
                    tables.append(table)
        
        # If no tables found with keywords, try to find the largest tables
        if not tables:
            logger.warning("No investment tables found with keywords, trying largest tables")
            all_tables = soup.find_all('table')
            scored = []
            for table in all_tables:
                rows = table.find_all('tr')
                cells = sum(len(row.find_all(['td', 'th'])) for row in rows)
                scored.append((len(rows) * cells, table))
            scored.sort(reverse=True, key=lambda x: x[0])
            # Take top 5 largest tables
            tables = [t for _, t in scored[:5]]
        
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
        
        # If no header found, use default column positions based on CSWC structure
        if not column_map:
            column_map = {
                'company': 0,
                'business_description': 2,
                'investment_type': 4,
                'coupon': 6,
                'reference_rate': 8,
                'spread': 10,
                'floor': 12,
                'pik': 14,
                'acquisition_date': 16,
                'maturity_date': 18,
                'shares_units': 20,
                'principal': 22,
                'cost': 24,
                'fair_value': 26,
                'percent_net_assets': 28
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
                industry_col = column_map.get('company', 0)
                if len(cell_texts) > industry_col:
                    industry_text = cell_texts[industry_col].strip()
                    if industry_text and not industry_text.startswith('Total') and not industry_text.startswith('Subtotal'):
                        current_industry = self._clean_industry_name(industry_text)
                        logger.debug(f"Found industry: {current_industry}")
                continue
            
            # Check if this is a company name row (has company name but no investment type)
            company_col = column_map.get('company', 0)
            investment_col = column_map.get('investment_type', 4)
            
            if len(cell_texts) > company_col:
                company_text = cell_texts[company_col].strip()
                investment_text = cell_texts[investment_col].strip() if len(cell_texts) > investment_col else ""
                
                # If we have a company name and no investment type, it's a new company
                if company_text and not investment_text and company_text != current_company:
                    current_company = company_text
                    # Try to get business description
                    biz_desc_col = column_map.get('business_description', 2)
                    if len(cell_texts) > biz_desc_col:
                        desc_text = cell_texts[biz_desc_col].strip()
                        if desc_text:
                            current_business_desc = desc_text
                    continue
            
            # Parse investment row
            investment = self._parse_investment_row(cells, cell_texts, column_map, current_company, current_industry, current_business_desc)
            if investment:
                investments.append(investment)
                # Update current company if we found one in this row
                if investment.get('company_name') and investment['company_name'] != 'Unknown':
                    current_company = investment['company_name']
                if investment.get('business_description'):
                    current_business_desc = investment['business_description']
        
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
        header_keywords = ['Company', 'Business Description', 'Investment', 'Coupon', 
                          'Reference', 'Spread', 'Floor', 'PIK', 'Acquisition Date', 'Maturity',
                          'Principal', 'Cost', 'Fair Value', 'Units', 'Type']
        
        text_combined = ' '.join(cell_texts).lower()
        matches = sum(1 for keyword in header_keywords if keyword.lower() in text_combined)
        return matches >= 5  # Need at least 5 header keywords
    
    def _should_skip_row(self, cell_texts: List[str]) -> bool:
        """Check if this row should be skipped (not an investment row)."""
        text_combined = ' '.join(cell_texts).lower()
        first_cell = cell_texts[0].strip().lower() if cell_texts else ""
        
        # Skip document structure rows
        skip_patterns = [
            'item 1.', 'item 2.', 'item 3.', 'item 4.', 'item 5.', 'item 6.',
            'part i', 'part ii',
            'consolidated statements',
            'consolidated schedule',
            'notes to consolidated',
            'management\'s discussion',
            'legal proceedings',
            'risk factors',
            'exhibits', 'signatures',
            'page',
            'affiliate investments (cost:',
            'control investments (cost:',
            'cash and cash equivalents',
            'restricted cash',
            'dividends and interest',
            'receivables:',
            'liabilities',
            'net assets',
            'common stock',
            'additional paid-in capital',
            'total distributable',
            'second lien loans',
            'subordinated debt',
            'preferred equity',
            'common equity',
            'earnout',
            'percentage of',
            'weighted average',
            'new investments',
            'proceeds from sales',
            'principal repayments',
            'realized gain',
            'unrealized',
            'september 30,',
            'march 31,',
            'portfolio company',
            'units', 'type',  # Header rows
            'escrow',
            'income tax receivable',
            'income tax payable',
            'debt issuance costs',
            'other assets',
            'other liabilities',
            'accrued restoration',
            'deferred tax',
            'october 2026 notes',
            'august 2028 notes',
            '2029 convertible notes',
            'september 2030 notes',
            'credit facilities',
            'investments at fair value:',  # Balance sheet category, not industry
            'other,',  # Balance sheet item
            'other assets',
            'other liabilities',
            '^other$',  # Just "Other" as company name
            '% of portfolio',  # Summary statistics
            'conversion/exchange',
            'conversion of security',
            'pik interest earned',
            'accretion of loan',
            'distributions-in-kind',
            'realized gain',
            'unrealized',
            'new investments',
            'proceeds from sales',
            'principal repayments',
        ]
        
        for pattern in skip_patterns:
            # Handle regex patterns
            if pattern.startswith('^') and pattern.endswith('$'):
                if re.match(pattern, first_cell):
                    return True
            elif pattern in text_combined or first_cell.startswith(pattern) or first_cell == pattern:
                return True
        
        # Skip rows where first cell is just a number or date without company name
        if first_cell and len(first_cell) < 3:
            if first_cell.isdigit() or first_cell in ['3', '4', '5', '6', '7']:
                return True
        
        # Skip rows that are just dates
        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', first_cell):
            return True
        
        # Skip rows with "Unknown" company and no meaningful data
        if first_cell == 'unknown' and not any(
            re.search(r'\d+', cell) for cell in cell_texts[1:] if cell
        ):
            return True
        
        return False
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a total row."""
        text_combined = ' '.join(cell_texts).lower()
        first_cell = cell_texts[0].strip().lower() if cell_texts else ""
        
        return (
            ('total' in text_combined and ('investments' in text_combined or 'assets' in text_combined)) or
            ('subtotal' in text_combined) or
            first_cell.startswith('total') or
            first_cell.startswith('subtotal')
        )
    
    def _is_industry_header(self, cell_texts: List[str], column_map: Dict) -> bool:
        """Check if this is an industry header row."""
        company_col = column_map.get('company', 0)
        if len(cell_texts) <= company_col:
            return False
        
        industry_text = cell_texts[company_col].strip()
        if not industry_text:
            return False
        
        # Industry headers typically don't have investment types or financial data
        investment_col = column_map.get('investment_type', 4)
        has_investment_type = len(cell_texts) > investment_col and cell_texts[investment_col].strip()
        
        # Check if there's any numeric data (principal, cost, fair value)
        has_numeric_data = False
        for cell_text in cell_texts:
            if re.search(r'\d+\.?\d*\s*[MmBbKk]?', cell_text):
                has_numeric_data = True
                break
        
        # Common industry patterns - industries are typically single words or short phrases
        # and don't have numbers, investment types, or dates
        is_industry_format = (
            len(industry_text.split()) <= 4 and  # Short phrase
            not re.search(r'\d', industry_text) and  # No numbers
            not has_investment_type and  # No investment type
            not has_numeric_data and  # No financial data
            'Total' not in industry_text and
            'Subtotal' not in industry_text and
            industry_text[0].isupper()  # Starts with capital
        )
        
        return is_industry_format
    
    def _map_columns(self, header_cells: List[str]) -> Dict[str, int]:
        """Map column names to indices."""
        column_map = {}
        
        for idx, cell_text in enumerate(header_cells):
            cell_lower = cell_text.lower()
            
            if 'company' in cell_lower and 'company' not in column_map:
                column_map['company'] = idx
            elif 'business' in cell_lower and 'description' in cell_lower:
                column_map['business_description'] = idx
            elif 'investment' in cell_lower and 'type' not in column_map:
                column_map['investment_type'] = idx
            elif 'coupon' in cell_lower:
                column_map['coupon'] = idx
            elif 'reference' in cell_lower:
                column_map['reference_rate'] = idx
            elif 'spread' in cell_lower:
                column_map['spread'] = idx
            elif 'floor' in cell_lower:
                column_map['floor'] = idx
            elif 'pik' in cell_lower:
                column_map['pik'] = idx
            elif 'acquisition' in cell_lower and 'date' in cell_lower:
                column_map['acquisition_date'] = idx
            elif 'maturity' in cell_lower:
                column_map['maturity_date'] = idx
            elif 'shares' in cell_lower or 'units' in cell_lower:
                column_map['shares_units'] = idx
            elif 'principal' in cell_lower:
                column_map['principal'] = idx
            elif 'cost' in cell_lower and 'fair' not in cell_lower:
                column_map['cost'] = idx
            elif 'fair' in cell_lower and 'value' in cell_lower:
                column_map['fair_value'] = idx
            elif '%' in cell_lower and 'net' in cell_lower:
                column_map['percent_net_assets'] = idx
        
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
        }
        
        # Get company name (may be in this row or carried from previous)
        company_col = column_map.get('company', 0)
        if len(cell_texts) > company_col:
            company_text = cell_texts[company_col].strip()
            if company_text and company_text != 'Unknown' and not company_text.startswith('Subtotal'):
                investment['company_name'] = company_text
            elif current_company:
                investment['company_name'] = current_company
        
        # Get business description
        biz_desc_col = column_map.get('business_description', 2)
        if len(cell_texts) > biz_desc_col:
            biz_desc = cell_texts[biz_desc_col].strip()
            if biz_desc:
                investment['business_description'] = biz_desc
        
        # Get investment type
        inv_type_col = column_map.get('investment_type', 4)
        if len(cell_texts) > inv_type_col:
            inv_type = cell_texts[inv_type_col].strip()
            if inv_type:
                investment['investment_type'] = standardize_investment_type(inv_type)
        
        # Get coupon/interest rate (from XBRL tag) - search all cells
        interest_value = None
        for cell in cells:
            interest_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentInterestRate')
            if interest_value is not None:
                investment['interest_rate'] = f"{interest_value}%"
                break
        
        # Get reference rate - search all cells for SOFR, LIBOR, Prime, etc.
        reference_rate_patterns = ['SOFR', 'LIBOR', 'Prime', 'EURIBOR', 'CDOR', 'BBSW']
        for cell in cells:
            cell_text = self._extract_cell_text(cell).strip()
            for pattern in reference_rate_patterns:
                if pattern in cell_text.upper():
                    investment['reference_rate'] = standardize_reference_rate(cell_text)
                    break
            if investment.get('reference_rate'):
                break
        
        # Get spread (from XBRL tag) - search all cells
        spread_value = None
        for cell in cells:
            spread_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentBasisSpreadVariableRate')
            if spread_value is not None:
                investment['spread'] = f"{spread_value}%"
                break
        
        # Get floor rate (from XBRL tag) - search all cells
        floor_value = None
        for cell in cells:
            floor_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentInterestRateFloor')
            if floor_value is not None:
                investment['floor_rate'] = f"{floor_value}%"
                break
        
        # Get PIK rate (from XBRL tag) - search all cells
        pik_value = None
        for cell in cells:
            pik_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentInterestRatePaidInKind')
            if pik_value is not None:
                investment['pik_rate'] = f"{pik_value}%"
                break
        
        # Get acquisition date - search all cells for date patterns
        # Dates typically appear after the interest rate columns and before maturity
        acquisition_date = None
        maturity_date = None
        dates_found = []
        
        for cell in cells:
            cell_text = self._extract_cell_text(cell).strip()
            # Look for date patterns: MM/DD/YYYY or M/D/YYYY
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', cell_text)
            if date_match:
                date_str = date_match.group(1)
                dates_found.append((date_str, cell))
        
        # If we found dates, assign them based on position
        # Typically acquisition date comes before maturity date
        if len(dates_found) >= 2:
            # Sort by position in the row (earlier cells = earlier dates)
            dates_found.sort(key=lambda x: cells.index(x[1]))
            acquisition_date = dates_found[0][0]
            maturity_date = dates_found[1][0]
        elif len(dates_found) == 1:
            # Only one date found - try to determine if it's acquisition or maturity
            # by checking column position relative to known columns
            date_str, date_cell = dates_found[0]
            date_idx = cells.index(date_cell)
            # If it's before principal column, likely acquisition date
            principal_col = column_map.get('principal', 22)
            if date_idx < principal_col:
                acquisition_date = date_str
            else:
                maturity_date = date_str
        
        if acquisition_date:
            investment['acquisition_date'] = acquisition_date
        if maturity_date:
            investment['maturity_date'] = maturity_date
        
        # Get shares/units (for equity investments)
        shares_col = column_map.get('shares_units', 20)
        if len(cells) > shares_col:
            shares_cell = cells[shares_col]
            shares_value = self._extract_numeric_value(shares_cell, 'us-gaap:InvestmentOwnedBalanceShares')
            if shares_value is not None:
                investment['shares_units'] = str(int(shares_value))
            else:
                # Fallback to text extraction
                shares_text = self._extract_cell_text(shares_cell)
                if shares_text:
                    investment['shares_units'] = shares_text
        
        # Get principal amount (from XBRL tag) - search all cells since colspan makes positions unreliable
        principal_value = None
        for cell in cells:
            principal_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentOwnedBalancePrincipalAmount')
            if principal_value is not None:
                # CSWC uses scale="3" (thousands), so multiply by 1000
                investment['principal_amount'] = int(principal_value * 1000)
                break
        
        # Get cost (from XBRL tag) - search all cells
        cost_value = None
        for cell in cells:
            cost_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentOwnedAtCost')
            if cost_value is not None:
                # CSWC uses scale="3" (thousands), so multiply by 1000
                investment['cost'] = int(cost_value * 1000)
                break
        
        # Get fair value (from XBRL tag) - search all cells
        fv_value = None
        for cell in cells:
            fv_value = self._extract_numeric_value(cell, 'us-gaap:InvestmentOwnedAtFairValue')
            if fv_value is not None:
                # CSWC uses scale="3" (thousands), so multiply by 1000
                investment['fair_value'] = int(fv_value * 1000)
                break
        
        # Skip if no meaningful data
        if (not investment.get('principal_amount') and 
            not investment.get('cost') and 
            not investment.get('fair_value') and
            not investment.get('shares_units') and
            investment.get('investment_type') == 'Unknown'):
            return None
        
        # Skip if company name is invalid
        company_name = investment.get('company_name', '').strip()
        if not company_name or company_name == 'Unknown' or len(company_name) < 2:
            return None
        
        # Skip if it looks like a summary row or balance sheet item
        skip_keywords = [
            'total', 'subtotal', 'affiliate', 'control', 'cash', 'receivables',
            'liabilities', 'net assets', 'common stock', 'percentage',
            'escrow', 'income tax', 'debt issuance', 'other assets',
            'other liabilities', 'accrued', 'deferred tax', 'notes (net',
            'credit facilities', 'investments at fair value',
            '% of portfolio', 'conversion', 'pik interest', 'accretion',
            'distributions-in-kind', 'realized', 'unrealized', 'new investments',
            'proceeds from', 'principal repayments'
        ]
        company_lower = company_name.lower()
        if any(keyword in company_lower for keyword in skip_keywords):
            return None
        
        # Skip if company name is just "Other" (balance sheet item)
        if company_lower.strip() == 'other':
            return None
        
        # Skip if industry is a balance sheet category or summary statistic
        industry = investment.get('industry', '').strip()
        if industry:
            industry_lower = industry.lower()
            if ('investments at fair value' in industry_lower or 
                industry_lower == 'assets' or
                (industry_lower == 'unknown' and '%' in company_name)):
                return None
        
        # Skip rows with Unknown industry and no investment type (likely summary/continuation rows)
        if (industry and industry.lower() == 'unknown' and 
            investment.get('investment_type') == 'Unknown' and
            not investment.get('principal_amount') and
            not investment.get('shares_units')):
            return None
        
        # Skip subtotal rows (have cost/fair value but "Unknown" investment type - these are company subtotals)
        # These rows summarize all investments for a company but aren't individual investments
        if (investment.get('investment_type') == 'Unknown' and 
            (investment.get('cost') or investment.get('fair_value')) and
            not investment.get('principal_amount')):
            # Check if shares_units looks like a percentage or is just a number (not actual shares)
            shares_units = investment.get('shares_units', '')
            if not shares_units or (shares_units and not any(char.isalpha() for char in str(shares_units))):
                # This is likely a subtotal row, skip it
                return None
        
        return investment
    
    def _extract_numeric_value(self, cell, concept_name: str) -> Optional[float]:
        """Extract numeric value from XBRL tag in cell."""
        # Look for ix:nonfraction tags with the specific concept
        xbrl_tags = cell.find_all(['ix:nonfraction', 'nonfraction'])
        
        for tag in xbrl_tags:
            name_attr = tag.get('name', '')
            if concept_name.lower() in name_attr.lower():
                # Get the text value
                value_text = tag.get_text(strip=True)
                
                # Handle special cases like "—" (em dash) or empty
                if value_text == '' or value_text == '—' or value_text == '-' or value_text == '—':
                    return None
                
                # Remove commas and other formatting, but keep decimal point and minus
                value_text = value_text.replace(',', '').replace('$', '').replace('(', '').replace(')', '')
                value_text = re.sub(r'[^\d\.\-]', '', value_text)
                
                if value_text == '' or value_text == '-':
                    return None
                
                try:
                    value = float(value_text)
                    # Check for sign attribute (negative values)
                    sign_attr = tag.get('sign', '')
                    if sign_attr == '-':
                        value = -value
                    return value
                except ValueError:
                    return None
        
        return None
    
    def _clean_industry_name(self, industry: str) -> str:
        """Clean and standardize industry name."""
        if not industry:
            return "Unknown"
        
        industry = industry.strip()
        if not industry:
            return "Unknown"
        
        # Standardize
        industry = standardize_industry(industry)
        
        return industry
