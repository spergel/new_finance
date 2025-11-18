#!/usr/bin/env python3
"""Custom parser for PSEC (Prospect Capital Corp) that extracts investment data from HTML tables in SEC filings."""

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


class PSECCustomExtractor:
    """
    Custom extractor for PSEC that parses HTML tables from SEC filings.
    Similar to GBDC/OFS parsers but adapted for PSEC's specific table structure.
    
    PSEC structure:
    - Col 0: Portfolio Company
    - Col 1: Industry
    - Col 2: Investments (Investment Type)
    - Col 3: Acquisition Date
    - Col 4: Coupon/Yield (interest rate with reference rate and spread)
    - Col 5: Floor
    - Col 6: Legal Maturity
    - Col 7: Principal Value (with $ in Col 7, value in Col 8)
    - Col 8: Amortized Cost (with $ in Col 10, value in Col 11)
    - Col 9: Fair Value (with $ in Col 13, value in Col 14)
    """
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "PSEC", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
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
            
            # Check if this table has investment data
            has_headers = False
            header_row_idx = None
            for row_idx, row in enumerate(rows[:15]):
                row_text = row.get_text(' ', strip=True).lower()
                header_keywords = ['portfolio company', 'industry', 'investment', 
                                  'acquisition date', 'coupon', 'yield', 'maturity',
                                  'principal', 'amortized cost', 'fair value']
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
                table_text = table.get_text().lower()
                has_investment_data = any(indicator in table_text for indicator in [
                    'first lien', 'second lien', 'senior secured', 'subordinated',
                    'preferred equity', 'common equity', 'term loan', 'revolving'
                ])
                
                if in_schedule_section or has_investment_data:
                    investment_tables.append(table)
                    logger.debug(f"Added table with {len(rows)} rows")
            else:
                if in_schedule_section:
                    table_text = table.get_text().lower()
                    if 'footnotes' in table_text[:500] or 'see notes' in table_text[:500]:
                        logger.debug("Reached end of investment schedule")
                        break
        
        logger.info(f"Filtered to {len(investment_tables)} investment schedule tables")
        return investment_tables
    
    def _parse_html_table(self, table, current_industry: str, current_company: Optional[str]) -> List[Dict]:
        """Parse a single HTML table.
        
        PSEC structure:
        - Col 0: Portfolio Company (company name, or empty for continuation rows)
        - Col 1: Industry (only in company name rows)
        - Col 2: Investments (Investment Type)
        - Col 3: Acquisition Date
        - Col 4: Coupon/Yield (e.g., "15.25 % (PRIME + 7.75 %)")
        - Col 5: Floor
        - Col 6: Legal Maturity
        - Col 7: Principal Value (with $ in Col 7, value in Col 8, scale=3)
        - Col 8: Amortized Cost (with $ in Col 10, value in Col 11, scale=3)
        - Col 9: Fair Value (with $ in Col 13, value in Col 14, scale=3)
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
        
        # Default column positions for PSEC
        if not column_map:
            column_map = {
                'company': 0,
                'industry': 1,
                'investment_type': 2,
                'acquisition_date': 3,
                'coupon_yield': 4,
                'floor': 5,
                'maturity_date': 6,
                'principal': 8,  # Value is in Col 8 (Col 7 has $)
                'cost': 11,  # Value is in Col 11 (Col 10 has $)
                'fair_value': 14  # Value is in Col 14 (Col 13 has $)
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
            
            # Check if this is a company name row (has company name in Col 0 and industry in Col 1)
            company_col = column_map.get('company', 0)
            industry_col = column_map.get('industry', 1)
            inv_type_col = column_map.get('investment_type', 2)
            
            # Check if Col 0 has a company name (and Col 1 has industry)
            has_company_name = (len(cell_texts) > company_col and 
                               cell_texts[company_col].strip() and
                               len(cell_texts) > industry_col and 
                               cell_texts[industry_col].strip())
            
            if has_company_name:
                company_text = cell_texts[company_col].strip()
                # Clean company name
                company_text = re.sub(r'\([^)]+\)', '', company_text).strip()  # Remove footnotes
                company_text = re.sub(r'[#~&*<>\+\^]+$', '', company_text).strip()
                
                # Check if it's actually a company name (not an investment type)
                investment_type_keywords = ['first lien', 'second lien', 'preferred', 'common', 
                                           'term loan', 'revolving', 'delayed draw', 'warrant',
                                           'membership interest', 'units', 'shares', 'stock']
                is_investment_type = any(keyword in company_text.lower() for keyword in investment_type_keywords)
                
                if company_text and len(company_text) > 1 and not is_investment_type:
                    local_company = company_text
                    
                    # Get industry
                    industry_text = cell_texts[industry_col].strip()
                    local_industry = self._clean_industry_name(industry_text)
                    logger.debug(f"Found company: {local_company}, industry: {local_industry}")
                    
                    # Check if this row also has investment type (it's both company header AND investment row)
                    if len(cell_texts) > inv_type_col and cell_texts[inv_type_col].strip():
                        # This row has both company name and investment type - parse it as investment
                        investment = self._parse_investment_row(cells, cell_texts, column_map, local_company, local_industry)
                        if investment:
                            investments.append(investment)
                    # Otherwise, it's just a company header row, continue to next row
                    continue
            
            # This should be an investment row
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
        header_keywords = ['portfolio company', 'industry', 'investment', 
                          'acquisition date', 'coupon', 'yield', 'maturity',
                          'principal', 'amortized cost', 'fair value']
        
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
            
            if 'portfolio company' in cell_lower:
                column_map['company'] = idx
            elif 'industry' in cell_lower:
                column_map['industry'] = idx
            elif 'investment' in cell_lower and 'type' not in column_map:
                column_map['investment_type'] = idx
            elif 'acquisition date' in cell_lower:
                column_map['acquisition_date'] = idx
            elif 'coupon' in cell_lower or 'yield' in cell_lower:
                column_map['coupon_yield'] = idx
            elif 'floor' in cell_lower:
                column_map['floor'] = idx
            elif 'maturity' in cell_lower or 'legal maturity' in cell_lower:
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
        
        # Get investment type from Col 2 (or Col 0 if it's a continuation row)
        # Check if Col 0 has an investment type (continuation row)
        company_col = column_map.get('company', 0)
        inv_type_col = column_map.get('investment_type', 2)
        
        # Check if Col 0 has an investment type (continuation row where company name is empty)
        if len(cell_texts) > company_col:
            col0_text = cell_texts[company_col].strip()
            # Check if Col 0 looks like an investment type (not a company name)
            investment_type_keywords = ['first lien', 'second lien', 'preferred', 'common', 
                                       'term loan', 'revolving', 'delayed draw', 'warrant',
                                       'membership interest', 'units', 'shares', 'stock',
                                       'class', 'series']
            if col0_text and any(keyword in col0_text.lower() for keyword in investment_type_keywords):
                # This is a continuation row - Col 0 has investment type
                inv_type = re.sub(r'\([^)]+\)', '', col0_text).strip()
                investment['investment_type'] = standardize_investment_type(inv_type)
        
        # Otherwise, get investment type from Col 2
        if investment['investment_type'] == 'Unknown' and len(cell_texts) > inv_type_col:
            inv_type = cell_texts[inv_type_col].strip()
            if inv_type and inv_type != 'N/A':
                # Clean investment type (remove footnotes)
                inv_type = re.sub(r'\([^)]+\)', '', inv_type).strip()
                investment['investment_type'] = standardize_investment_type(inv_type)
        
        # Get coupon/yield from Col 4 (or Col 2 if continuation row) - contains interest rate, reference rate, and spread
        # Format: "15.25 % (PRIME + 7.75 %)" or "11.28 % (3M SOFR + 7.00 %)" or "12.26 % PIK"
        # Skip for Common Equity - it doesn't have interest rates
        inv_type_lower = investment.get('investment_type', '').lower()
        is_common_equity = 'common equity' in inv_type_lower
        
        if not is_common_equity:
            coupon_col = column_map.get('coupon_yield', 4)
            # For continuation rows, coupon might be in Col 2
            for check_col in [2, coupon_col, 3, 4]:
                if len(cell_texts) > check_col:
                    coupon_text = cell_texts[check_col].strip()
                    if coupon_text and coupon_text.lower() not in ('n/m', 'n/a', ''):
                        # Extract interest rate (first percentage)
                        rate_match = re.search(r'(\d+\.?\d*)\s*%', coupon_text)
                        if rate_match:
                            investment['interest_rate'] = f"{rate_match.group(1)}%"
                        
                        # Check for PIK rate
                        pik_match = re.search(r'(\d+\.?\d*)\s*%\s*PIK', coupon_text, re.IGNORECASE)
                        if pik_match:
                            investment['pik_rate'] = f"{pik_match.group(1)}%"
                        
                        # Check for "X% plus Y% PIK" pattern
                        pik_plus_match = re.search(r'(\d+\.?\d*)\s*%\s*plus\s*(\d+\.?\d*)\s*%\s*PIK', coupon_text, re.IGNORECASE)
                        if pik_plus_match:
                            investment['interest_rate'] = f"{pik_plus_match.group(1)}%"
                            investment['pik_rate'] = f"{pik_plus_match.group(2)}%"
                        
                        # Extract reference rate and spread from parentheses
                        # Pattern: "(PRIME + 7.75 %)" or "(3M SOFR + 7.00 %)" or "(1M SOFR + 7.25 %)"
                        ref_spread_match = re.search(r'\(([^)]+)\s*\+\s*(\d+\.?\d*)\s*%\)', coupon_text)
                        if ref_spread_match:
                            ref_text = ref_spread_match.group(1).strip()
                            spread_val = ref_spread_match.group(2)
                            investment['spread'] = f"{spread_val}%"
                            
                            # Extract reference rate (SOFR, PRIME, LIBOR, etc.)
                            if 'sofr' in ref_text.lower():
                                investment['reference_rate'] = 'SOFR'
                            elif 'prime' in ref_text.lower():
                                investment['reference_rate'] = 'PRIME'
                            elif 'libor' in ref_text.lower():
                                investment['reference_rate'] = 'LIBOR'
                            else:
                                investment['reference_rate'] = standardize_reference_rate(ref_text)
                        
                        # If we found something, break
                        if investment.get('interest_rate') or investment.get('pik_rate'):
                            break
        
        # Get floor rate from Col 5
        floor_col = column_map.get('floor', 5)
        if len(cell_texts) > floor_col:
            floor_text = cell_texts[floor_col].strip()
            if floor_text and floor_text not in ('—', '-', '–', 'N/A', ''):
                floor_match = re.search(r'(\d+\.?\d*)', floor_text)
                if floor_match:
                    investment['floor_rate'] = f"{floor_match.group(1)}%"
        
        # Get acquisition date from Col 3 (or Col 1 if continuation row)
        acq_col = column_map.get('acquisition_date', 3)
        # For continuation rows, date might be in Col 1
        for check_col in [1, acq_col, 2, 3, 4]:
            if len(cells) > check_col:
                date_cell = cells[check_col]
                date_text = self._extract_cell_text(date_cell).strip()
                if date_text and re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_text):
                    investment['acquisition_date'] = date_text
                    break
        
        # Get maturity date from Col 6 (or Col 4 if continuation row)
        mat_col = column_map.get('maturity_date', 6)
        # For continuation rows, maturity might be in Col 4
        for check_col in [4, mat_col, 5, 6, 7]:
            if len(cells) > check_col:
                date_cell = cells[check_col]
                date_text = self._extract_cell_text(date_cell).strip()
                if date_text and re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_text):
                    investment['maturity_date'] = date_text
                    break
        
        # Get principal amount (Col 8, scale=3 means thousands)
        # Structure: Col 7 has '$', Col 8 has the value
        principal_col = column_map.get('principal', 8)
        # Check the exact column first (Col 8), then nearby columns, but skip Col 5 (floor rate)
        for check_col in [principal_col, 8, 7, 9]:
            if len(cells) > check_col:
                principal_cell = cells[check_col]
                cell_text = self._extract_cell_text(principal_cell).strip()
                # Skip if it's just a dollar sign or empty
                if cell_text in ('$', '—', '-', '–', ''):
                    continue
                principal_value = self._extract_numeric_value(principal_cell)
                if principal_value is not None and principal_value >= 1000:  # At least $1K (in actual dollars)
                    investment['principal_amount'] = principal_value
                    break
        
        # Get cost (Col 11, scale=3 means thousands)
        # Structure: Col 10 has '$', Col 11 has the value
        # For continuation rows: Col 7 might have cost, Col 9 has '—' (empty)
        cost_col = column_map.get('cost', 11)
        # Check if this is a continuation row (equity investment) - Col 7 might have the value
        is_equity = investment.get('investment_type', '').lower() in ['common equity', 'preferred equity', 'membership interest', 'warrant']
        if is_equity:
            # For equity, check Col 7 first (principal/cost), then Col 11
            for check_col in [7, cost_col, 10, 11, 12]:
                if len(cells) > check_col:
                    cost_cell = cells[check_col]
                    cell_text = self._extract_cell_text(cost_cell).strip()
                    if cell_text in ('$', '—', '-', '–', '', 'N/A', 'n/a'):
                        continue
                    # Skip if it looks like a footnote reference
                    if cell_text.startswith('(') and cell_text.endswith(')'):
                        continue
                    cost_value = self._extract_numeric_value(cost_cell)
                    if cost_value is not None and cost_value >= 1000:  # At least $1K
                        investment['cost'] = cost_value
                        break
        else:
            # For debt investments, use standard columns
            for check_col in [cost_col, 10, 11, 12]:
                if len(cells) > check_col:
                    cost_cell = cells[check_col]
                    cell_text = self._extract_cell_text(cost_cell).strip()
                    if cell_text in ('$', '—', '-', '–', '', 'N/A', 'n/a'):
                        continue
                    # Skip if it looks like a footnote reference
                    if cell_text.startswith('(') and cell_text.endswith(')'):
                        continue
                    cost_value = self._extract_numeric_value(cost_cell)
                    if cost_value is not None and cost_value >= 1000:  # At least $1K
                        investment['cost'] = cost_value
                        break
        
        # Get fair value (Col 14, scale=3 means thousands)
        # Structure: Col 13 has '$', Col 14 has the value
        # For continuation rows: Col 11 might have '—' (empty), Col 12 has footnote
        fv_col = column_map.get('fair_value', 14)
        for check_col in [fv_col, 13, 14, 15]:
            if len(cells) > check_col:
                fv_cell = cells[check_col]
                cell_text = self._extract_cell_text(fv_cell).strip()
                if cell_text in ('$', '—', '-', '–', '', 'N/A', 'n/a'):
                    continue
                # Skip if it looks like a footnote reference (e.g., "(14)", "-14")
                if (cell_text.startswith('(') and cell_text.endswith(')')) or \
                   (cell_text.startswith('-') and len(cell_text) <= 4 and cell_text.replace('-', '').isdigit()):
                    continue
                fv_value = self._extract_numeric_value(fv_cell)
                if fv_value is not None:
                    # For fair value, accept any value (could be negative or small)
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
        principal = investment.get('principal_amount') or 0
        cost = investment.get('cost') or 0
        fv = investment.get('fair_value') or 0
        if (investment.get('investment_type') == 'Unknown' and 
            has_financial_data and
            (abs(principal) > 10000000 or  # > $10M suggests aggregate
             abs(cost) > 10000000 or
             abs(fv) > 10000000)):
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
        output_file = os.path.join(output_dir, 'PSEC_Prospect_Capital_Corp_investments.csv')
        
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
        
        return output_file


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = PSECCustomExtractor()
    try:
        result = extractor.extract_from_ticker("PSEC")
        print(f"\nSuccessfully extracted {result.get('total_investments', 0)} investments")
        print(f"  Total Principal: ${result.get('total_principal', 0):,.0f}")
        print(f"  Total Cost: ${result.get('total_cost', 0):,.0f}")
        print(f"  Total Fair Value: ${result.get('total_fair_value', 0):,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == '__main__':
    main()
