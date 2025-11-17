#!/usr/bin/env python3
"""
Custom KBDC (Kayne Anderson BDC) Investment Extractor

Parses KBDC's HTML table structure with embedded XBRL tags where:
- Column 0: Portfolio Company (company name)
- Column 2: Footnotes
- Column 4: Investment (investment type)
- Column 7-8: Interest Rate (value and %)
- Column 10-11: Spread (value and %)
- Column 13-14: PIK Rate (value and %)
- Column 16: Reference (SOFR(M), SOFR(Q), etc.)
- Column 18: Maturity Date
- Column 21: Principal/Par
- Column 24: Amortized Cost
- Column 27: Fair Value
- Column 30-31: Percentage of Net Assets
"""

import logging
import os
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import csv
from collections import defaultdict

from xbrl_typed_extractor import BDCExtractionResult
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate
from datetime import datetime

logger = logging.getLogger(__name__)


class KBDCCustomExtractor:
    """Custom extractor for KBDC that extracts everything from HTML tables only."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "KBDC") -> BDCExtractionResult:
        """Extract investments from KBDC's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise RuntimeError("Could not resolve CIK for KBDC")
        
        logger.info(f"Found CIK: {cik}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise RuntimeError("Could not locate latest 10-Q index for KBDC")
        
        logger.info(f"Filing index: {index_url}")
        
        # Get HTML URL and filing date
        documents = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
        if not main_html:
            raise RuntimeError("Could not find HTML document")
        
        htm_url = main_html.url
        
        # Get filing date from index page
        filing_date = self._get_filing_date_from_index(index_url)
        
        logger.info(f"HTML URL: {htm_url}")
        logger.info(f"Filing date: {filing_date}")
        
        return self.extract_from_filing(htm_url, "Kayne Anderson BDC, Inc.", cik, filing_date)
    
    def extract_from_filing(self, htm_url: str, company_name: str, cik: str, filing_date: str) -> BDCExtractionResult:
        """Extract complete KBDC investment data from HTML only."""
        
        logger.info(f"Starting KBDC extraction from HTML...")
        
        # Extract everything from HTML tables
        investments = self._parse_html_table(htm_url)
        logger.info(f"HTML extraction: {len(investments)} investments")
        
        # Calculate totals
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
        output_file = os.path.join(output_dir, f'KBDC_Kayne_Anderson_BDC_investments.csv')
        
        self._save_to_csv(investments, output_file)
        logger.info(f"Saved {len(investments)} investments to {output_file}")
        
        return BDCExtractionResult(
            company_name=company_name,
            cik=cik,
            filing_date=filing_date,
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
    
    def _get_filing_date_from_index(self, index_url: str) -> str:
        """Extract filing date from the index page."""
        try:
            resp = requests.get(index_url, headers=self.headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Look for filing date in the page
            # Usually in a table row with "Filing Date" or "Document Period End Date"
            for row in soup.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    if 'filing date' in label or 'filed as of' in label:
                        date_str = cells[1].get_text(strip=True)
                        # Try to parse and format
                        try:
                            # Common formats: MM/DD/YYYY, YYYY-MM-DD
                            if '/' in date_str:
                                parts = date_str.split('/')
                                if len(parts) == 3:
                                    return f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                            elif '-' in date_str and len(date_str) == 10:
                                return date_str
                        except:
                            pass
            
            # Fallback: try to get from URL or use today's date
            logger.warning("Could not find filing date in index, using today")
            return datetime.now().strftime('%Y-%m-%d')
        except Exception as e:
            logger.warning(f"Error getting filing date: {e}, using today")
            return datetime.now().strftime('%Y-%m-%d')
    
    def _parse_html_table(self, html_url: str) -> List[Dict]:
        """Parse KBDC's HTML schedule of investments table."""
        
        logger.info(f"Fetching HTML from {html_url}")
        resp = requests.get(html_url, headers=self.headers)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables")
        
        # Look for ALL schedule of investments tables (may be split across multiple tables)
        schedule_tables = []
        for table in tables:
            text = table.get_text(' ', strip=True).lower()
            if 'portfolio company' in text and 'investment' in text and ('amortized' in text or 'fair value' in text):
                schedule_tables.append(table)
                logger.info(f"Found schedule table with {len(table.find_all('tr'))} rows")
        
        if not schedule_tables:
            logger.warning("Schedule table not found")
            return []
        
        logger.info(f"Found {len(schedule_tables)} schedule table(s)")
        
        # Parse all schedule tables
        html_entries = []
        current_industry = None
        last_company = None
        column_map = None
        
        for table_idx, schedule_table in enumerate(schedule_tables):
            # Parse the table - first find header row to map columns
            rows = schedule_table.find_all('tr')
            
            # Find column map (reuse if already found, or find new one)
            if column_map is None or table_idx == 0:
                column_map = self._find_column_indices(rows)
                if not column_map:
                    logger.warning(f"Could not find column headers in table {table_idx}")
                    continue
                logger.info(f"Column map: {column_map}")
            
            # Parse the table
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                
                # Get cell texts (handling XBRL tags)
                cell_texts = []
                for cell in cells:
                    # Extract text, but also check for XBRL tags
                    text = self._extract_cell_text(cell)
                    cell_texts.append(text)
                
                # Check if this is a header row
                if self._is_header_row(cell_texts):
                    continue
                
                # Check if this is an industry header row
                if self._is_industry_header(cell_texts, column_map):
                    company_col = column_map.get('company', 0)
                    industry_text = cell_texts[company_col] if len(cell_texts) > company_col else ""
                    if industry_text and not industry_text.startswith('Total'):
                        current_industry = self._clean_industry_name(industry_text)
                    continue
                
                # Check if this is an investment row
                company_col = column_map.get('company', 0)
                investment_col = column_map.get('investment_type', 4)
                company_name_raw = cell_texts[company_col] if len(cell_texts) > company_col else ""
                investment_type = cell_texts[investment_col] if len(cell_texts) > investment_col else ""
                
                if self._is_investment_row(cell_texts, company_name_raw, investment_type):
                    entry = self._parse_investment_row(cells, cell_texts, column_map, current_industry, last_company)
                    if entry:
                        if entry.get('company_name'):
                            last_company = entry['company_name']
                        html_entries.append(entry)
        
        return html_entries
    
    def _find_column_indices(self, rows: List) -> Dict[str, int]:
        """Find column indices by examining header rows and XBRL name attributes."""
        column_map = {}
        
        # First, try to find columns by examining a data row's XBRL name attributes
        # This is more reliable than header text
        for row_idx, row in enumerate(rows[2:10], 2):  # Check rows 2-9 for a data row
            cells = row.find_all(['td', 'th'])
            if len(cells) < 20:
                continue
            
            # Check if this looks like a data row (has company name and investment type)
            company = self._extract_cell_text(cells[0]).strip()
            if not company or 'portfolio company' in company.lower():
                continue
            
            # This is a data row - scan cells for XBRL tags with known names
            for col_idx, cell in enumerate(cells):
                cell_html = str(cell)
                cell_text = self._extract_cell_text(cell).strip()
                
                # Check for XBRL tags (both nonfraction and nonnumeric)
                if '<ix:nonfraction' in cell_html.lower():
                    # Extract name attribute
                    name_match = re.search(r'name=["\']([^"\']+)["\']', cell_html, re.IGNORECASE)
                    if name_match:
                        name = name_match.group(1).lower()
                        name_part = name.split(':')[-1] if ':' in name else name
                        
                        # Map by XBRL concept name
                        if 'investmentownedbalanceprincipalamount' in name_part or 'principal' in name_part:
                            column_map['principal'] = col_idx
                        elif 'investmentownedatcost' in name_part or ('cost' in name_part and 'amortized' in name_part):
                            column_map['cost'] = col_idx
                        elif 'investmentownedatfairvalue' in name_part or 'fairvalue' in name_part:
                            column_map['fair_value'] = col_idx
                        elif 'investmentinterestrate' in name_part and 'paidincash' not in name_part:
                            column_map['interest_rate'] = col_idx
                        elif 'investmentinterestratepaidincash' in name_part:
                            column_map['spread'] = col_idx  # This is actually the cash rate (spread)
                        elif 'investmentinterestratepaidinkind' in name_part:
                            column_map['pik_rate'] = col_idx
                        elif 'investmentreference' in name_part or 'kbdc:investmentreference' in name:
                            column_map['reference_rate'] = col_idx
                        elif 'investmentownedpercentofnetassets' in name_part:
                            column_map['percent_net_assets'] = col_idx
                
                # Check for maturity date (ix:nonnumeric tags)
                if '<ix:nonnumeric' in cell_html.lower():
                    name_match = re.search(r'name=["\']([^"\']+)["\']', cell_html, re.IGNORECASE)
                    if name_match:
                        name = name_match.group(1).lower()
                        name_part = name.split(':')[-1] if ':' in name else name
                        if 'investmentmaturitydate' in name_part or 'maturitydate' in name_part:
                            column_map['maturity_date'] = col_idx
                    # Also check if the text looks like a date
                    elif re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', cell_text):
                        if 'maturity_date' not in column_map:
                            column_map['maturity_date'] = col_idx
            
            # If we found financial columns, break
            if 'principal' in column_map or 'cost' in column_map:
                break
        
        # Also find header-based columns for text fields
        for row_idx, row in enumerate(rows[:5]):
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            cell_texts = [self._extract_cell_text(cell).lower() for cell in cells]
            header_text = ' '.join(cell_texts)
            
            if 'portfolio company' in header_text and 'investment' in header_text:
                for col_idx, text in enumerate(cell_texts):
                    text_lower = text.lower()
                    if 'portfolio company' in text_lower or ('company' in text_lower and 'portfolio' in header_text):
                        column_map['company'] = col_idx
                    elif 'footnotes' in text_lower or 'footnote' in text_lower:
                        column_map['footnotes'] = col_idx
                    elif 'investment' in text_lower and ('type' not in text_lower or 'investment type' in text_lower):
                        if 'investment_type' not in column_map:
                            column_map['investment_type'] = col_idx
                    elif 'reference' in text_lower and 'rate' not in text_lower and 'reference_rate' not in column_map:
                        column_map['reference_rate'] = col_idx
                    elif 'maturity date' in text_lower or ('maturity' in text_lower and 'date' in text_lower):
                        if 'maturity_date' not in column_map:
                            column_map['maturity_date'] = col_idx
                    elif 'percentage of net assets' in text_lower or '% of net assets' in text_lower:
                        if 'percent_net_assets' not in column_map:
                            column_map['percent_net_assets'] = col_idx
                
                break
        
        # Fallback defaults if not found
        defaults = {
            'company': 0,
            'footnotes': 2,
            'investment_type': 4,
            'interest_rate': 7,
            'spread': 10,
            'pik_rate': 12,
            'reference_rate': 15,
            'maturity_date': 20,  # Updated based on debug output
            'principal': 23,  # Updated based on debug output
            'cost': 27,  # Updated based on debug output
            'fair_value': 31,  # Updated based on column map output
            'percent_net_assets': 35
        }
        
        # Use defaults for missing columns
        for key, default_val in defaults.items():
            if key not in column_map:
                column_map[key] = default_val
        
        return column_map
    
    def _extract_cell_text(self, cell) -> str:
        """Extract text from cell, handling XBRL tags."""
        # First try to get text directly
        text = cell.get_text(' ', strip=True)
        
        # If empty, check for XBRL tags
        if not text or text.strip() == '':
            # Look for ix:nonfraction or ix:nonnumeric tags
            xbrl_tags = cell.find_all(['ix:nonfraction', 'ix:nonnumeric', 'nonfraction', 'nonnumeric'])
            if xbrl_tags:
                # Get text from first XBRL tag
                text = xbrl_tags[0].get_text(' ', strip=True)
        
        return text
    
    def _is_industry_header(self, cell_texts: List[str], column_map: Dict[str, int] = None) -> bool:
        """Check if this is an industry header row."""
        if not cell_texts:
            return False
        
        # Use column map if available, otherwise default to first column
        company_col = column_map.get('company', 0) if column_map else 0
        investment_col = column_map.get('investment_type', 4) if column_map else 4
        
        first_cell = cell_texts[company_col] if len(cell_texts) > company_col else ""
        first_cell = first_cell.strip()
        
        # Industry headers are typically bold and don't have investment types
        # They're usually single words or short phrases
        if first_cell and len(first_cell) > 0:
            # Check if it looks like an industry (not a company name, not empty)
            # Industry headers often have & in them (e.g., "Aerospace & defense")
            if '&' in first_cell or first_cell in ['Debt and Equity Investments']:
                # Make sure it's not an investment row
                investment_type = cell_texts[investment_col] if len(cell_texts) > investment_col else ""
                if not investment_type or 'loan' not in investment_type.lower():
                    return True
        
        return False
    
    def _clean_industry_name(self, text: str) -> str:
        """Clean up industry name."""
        text = text.strip()
        # Remove common prefixes
        text = re.sub(r'^Debt and Equity Investments\s*', '', text, flags=re.IGNORECASE)
        return text.strip()
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a table header row."""
        if not cell_texts:
            return False
        
        header_keywords = ['Portfolio Company', 'Footnotes', 'Investment', 'Interest Rate',
                          'Spread', 'PIK Rate', 'Reference', 'Maturity Date', 'Principal',
                          'Amortized Cost', 'Fair Value', 'Percentage of Net Assets']
        
        first_few = ' '.join(cell_texts[:5]).lower()
        return any(keyword.lower() in first_few for keyword in header_keywords)
    
    def _is_investment_row(self, cell_texts: List[str], company_name: str, investment_type: str) -> bool:
        """Check if this row contains investment data."""
        # Skip total rows
        if company_name and company_name.startswith('Total'):
            return False
        
        # Must have investment type
        if not investment_type:
            return False
        
        # Investment types in KBDC
        investment_keywords = [
            'First lien', 'Second lien', 'Senior secured', 'Subordinated',
            'Revolving', 'Delayed draw', 'Preferred', 'Common', 'Warrants', 'Equity'
        ]
        
        return any(keyword.lower() in investment_type.lower() for keyword in investment_keywords)
    
    def _parse_investment_row(self, cells: List, cell_texts: List[str], column_map: Dict[str, int],
                             industry: str, last_company: str) -> Optional[Dict]:
        """Parse an investment row from KBDC's HTML table."""
        
        try:
            # Get column indices from map
            company_col = column_map.get('company', 0)
            investment_col = column_map.get('investment_type', 4)
            interest_col = column_map.get('interest_rate', 7)
            spread_col = column_map.get('spread', 10)
            pik_col = column_map.get('pik_rate', 13)
            reference_col = column_map.get('reference_rate', 16)
            maturity_col = column_map.get('maturity_date', 18)
            principal_col = column_map.get('principal', 21)
            cost_col = column_map.get('cost', 24)
            fair_value_col = column_map.get('fair_value', 27)
            pct_col = column_map.get('percent_net_assets', 30)
            
            company_name_raw = cell_texts[company_col] if len(cell_texts) > company_col else ""
            investment_type = cell_texts[investment_col] if len(cell_texts) > investment_col else ""
            
            # Use last company if current row doesn't have one
            company_name = company_name_raw if company_name_raw else last_company
            
            if not company_name or not investment_type:
                return None
            
            # Clean company name (remove footnotes in parentheses)
            company_name = re.sub(r'\s*\([^)]*\)', '', company_name).strip()
            
            # Extract dates - check both text and XBRL tags
            maturity_date = None
            if len(cells) > maturity_col:
                maturity_cell = cells[maturity_col]
                cell_html = str(maturity_cell)
                
                # Try XBRL tag first (ix:nonnumeric for dates)
                # Look for InvestmentMaturityDate specifically
                date_match = re.search(r'<ix:nonnumeric[^>]*name=["\'][^"\']*maturitydate[^"\']*["\'][^>]*>([^<]+)</ix:nonnumeric>', cell_html, re.IGNORECASE)
                if date_match:
                    maturity_date = date_match.group(1).strip()
                else:
                    # Try any ix:nonnumeric tag
                    date_match = re.search(r'<ix:nonnumeric[^>]*>([^<]+)</ix:nonnumeric>', cell_html, re.IGNORECASE)
                    if date_match:
                        maturity_date = date_match.group(1).strip()
                    else:
                        # Fallback to text
                        maturity_date = cell_texts[maturity_col] if len(cell_texts) > maturity_col else ""
            
            # Clean dates
            if maturity_date and maturity_date not in ['—', '', ' ', '-', 'N/A']:
                maturity_date = self._normalize_date(maturity_date)
            else:
                maturity_date = None
            
            # Extract rates (check next cell for % sign)
            interest_rate_raw = cell_texts[interest_col] if len(cell_texts) > interest_col else ""
            interest_rate_pct = cell_texts[interest_col + 1] if len(cell_texts) > interest_col + 1 else ""
            
            spread_raw = cell_texts[spread_col] if len(cell_texts) > spread_col else ""
            spread_pct = cell_texts[spread_col + 1] if len(cell_texts) > spread_col + 1 else ""
            
            pik_rate_raw = cell_texts[pik_col] if len(cell_texts) > pik_col else ""
            pik_rate_pct = cell_texts[pik_col + 1] if len(cell_texts) > pik_col + 1 else ""
            
            # Parse interest rate
            interest_rate = None
            if interest_rate_raw and interest_rate_raw not in ['—', '', ' ', '-']:
                if interest_rate_pct == '%':
                    interest_rate = interest_rate_raw + '%'
                else:
                    interest_rate = interest_rate_raw.strip()
            
            # Parse spread
            spread = None
            if spread_raw and spread_raw not in ['—', '', ' ', '-']:
                if spread_pct == '%':
                    spread = spread_raw + '%'
                else:
                    spread = spread_raw.strip()
            
            # Parse PIK rate
            pik_rate = None
            if pik_rate_raw and pik_rate_raw not in ['—', '', ' ', '-']:
                if pik_rate_pct == '%':
                    pik_rate = pik_rate_raw + '%'
                else:
                    pik_rate = pik_rate_raw.strip()
            
            # Extract reference rate
            reference_rate = cell_texts[reference_col] if len(cell_texts) > reference_col else ""
            if reference_rate and reference_rate not in ['—', '', ' ', '-']:
                reference_rate = reference_rate.strip()
            else:
                reference_rate = None
            
            # Extract monetary values (need to handle XBRL tags)
            principal = self._parse_money_value_from_cell(cells, principal_col, cell_texts)
            cost = self._parse_money_value_from_cell(cells, cost_col, cell_texts)
            fair_value = self._parse_money_value_from_cell(cells, fair_value_col, cell_texts)
            
            # Extract % of Net Assets
            percent_net_assets = None
            if len(cell_texts) > pct_col:
                pct_value = cell_texts[pct_col]
                pct_sign = cell_texts[pct_col + 1] if len(cell_texts) > pct_col + 1 else ""
                if pct_value and pct_value not in ['—', '', ' ', '-']:
                    if pct_sign == '%':
                        percent_net_assets = pct_value + '%'
                    else:
                        percent_net_assets = pct_value
            
            return {
                'company_name': company_name,
                'business_description': "",
                'investment_type': investment_type,
                'industry': industry or "Unknown",
                'acquisition_date': None,  # KBDC doesn't show acquisition dates in this table
                'maturity_date': maturity_date,
                'interest_rate': interest_rate,
                'reference_rate': reference_rate,
                'spread': spread,
                'pik_rate': pik_rate,
                'principal_amount': principal,
                'cost_basis': cost,
                'fair_value': fair_value,
                'percent_net_assets': percent_net_assets
            }
        
        except Exception as e:
            logger.warning(f"Failed to parse row: {e}")
            return None
    
    def _parse_money_value_from_cell(self, cells: List, col_idx: int, cell_texts: List[str]) -> Optional[float]:
        """Parse monetary value from cell, handling XBRL tags."""
        if col_idx >= len(cells):
            return None
        
        cell = cells[col_idx]
        
        # Get raw HTML string for this cell to extract XBRL tags with regex
        cell_html = str(cell)
        
        # Extract using simpler regex approach - find name, scale, and value separately
        if '<ix:nonfraction' in cell_html.lower():
            # Extract name, scale, and value
            name_match = re.search(r'name=["\']([^"\']+)["\']', cell_html, re.IGNORECASE)
            scale_match = re.search(r'scale=["\']([^"\']+)["\']', cell_html, re.IGNORECASE)
            value_match = re.search(r'<ix:nonfraction[^>]*>([^<]+)</ix:nonfraction>', cell_html, re.IGNORECASE)
            
            if value_match:
                value_str = value_match.group(1).strip()
                scale_str = scale_match.group(1) if scale_match else '0'
                name = name_match.group(1).lower() if name_match else ""
                
                # Only extract if it's a financial value (has USD unit or investment-related name)
                unit_match = re.search(r'unitref=["\']([^"\']+)["\']', cell_html, re.IGNORECASE)
                unit_ref = unit_match.group(1).lower() if unit_match else ""
                
                is_financial = ('usd' in unit_ref or 
                              'investment' in name or
                              'principal' in name or
                              'cost' in name or
                              'fair' in name or
                              'value' in name)
                
                if is_financial and value_str and value_str not in ['—', '', ' ', '-', 'N/A', '   -']:
                    try:
                        # Remove commas and formatting
                        value_str = value_str.replace(',', '').replace('$', '').strip()
                        value = float(value_str)
                        
                        # Apply scale (scale="3" means multiply by 1000, scale="-2" means divide by 100)
                        try:
                            scale_int = int(scale_str)
                            if scale_int > 0:
                                value = value * (10 ** scale_int)
                            elif scale_int < 0:
                                value = value / (10 ** abs(scale_int))
                        except (ValueError, TypeError):
                            pass
                        
                        return value
                    except (ValueError, TypeError):
                        pass
        
        # Try BeautifulSoup as fallback
        xbrl_tags = []
        for tag_name in ['ix:nonfraction', 'ix:nonnumeric', 'nonfraction', 'nonnumeric']:
            tags = cell.find_all(tag_name)
            if tags:
                xbrl_tags.extend(tags)
        
        for tag in cell.find_all(True):
            tag_name = tag.name.lower() if tag.name else ''
            if 'nonfraction' in tag_name or 'nonnumeric' in tag_name:
                if tag not in xbrl_tags:
                    xbrl_tags.append(tag)
        
        if xbrl_tags:
            for tag in xbrl_tags:
                unit_ref = tag.get('unitref', '')
                name_attr = tag.get('name', '')
                
                is_financial = ('usd' in unit_ref.lower() or 
                               'investment' in name_attr.lower() or
                               'principal' in name_attr.lower() or
                               'cost' in name_attr.lower() or
                               'fair' in name_attr.lower() or
                               'value' in name_attr.lower())
                
                if is_financial or not unit_ref:
                    value_str = tag.get_text(strip=True)
                    if value_str and value_str not in ['—', '', ' ', '-', 'N/A', '   -']:
                        try:
                            value_str = value_str.replace(',', '').replace('$', '').strip()
                            scale = tag.get('scale', '0')
                            try:
                                scale_int = int(scale)
                                value = float(value_str)
                                if scale_int != 0:
                                    value = value * (10 ** scale_int)
                                return value
                            except (ValueError, TypeError):
                                return float(value_str)
                        except (ValueError, TypeError):
                            continue
        
        # Final fallback: text extraction
        value_str = cell_texts[col_idx] if col_idx < len(cell_texts) else ""
        if not value_str or value_str in ['—', '', ' ', '-', '(1)', '(7)', '(12)', 'N/A', '   -']:
            cell_text = cell.get_text(strip=True)
            cell_text = re.sub(r'<[^>]+>', '', cell_text)
            value_str = cell_text
        
        if not value_str or value_str in ['—', '', ' ', '-', '(1)', '(7)', '(12)', 'N/A', '   -']:
            return None
        
        value_str = value_str.replace(',', '').replace('$', '').strip()
        try:
            return float(value_str)
        except (ValueError, TypeError):
            return None
    
    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize date from various formats to MM/DD/YYYY."""
        if not date_str:
            return None
        
        # Remove dashes
        date_str = date_str.replace('—', '').strip()
        if not date_str:
            return None
        
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
    
    
    def _save_to_csv(self, investments: List[Dict], output_file: str):
        """Save investments to CSV file."""
        fieldnames = [
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost_basis',
            'fair_value', 'interest_rate', 'reference_rate', 'spread', 'floor_rate',
            'pik_rate', 'shares_units', 'percent_net_assets', 'currency', 'commitment_limit', 'undrawn_commitment'
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
                    'percent_net_assets': inv.get('percent_net_assets'),
                    'currency': inv.get('currency', 'USD'),
                    'commitment_limit': inv.get('commitment_limit'),
                    'undrawn_commitment': inv.get('undrawn_commitment')
                })


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = KBDCCustomExtractor()
    try:
        result = extractor.extract_from_ticker("KBDC")
        print(f"\n✓ Successfully extracted {result.total_investments} investments")
        print(f"  Total Principal: ${result.total_principal:,.0f}")
        print(f"  Total Cost: ${result.total_cost:,.0f}")
        print(f"  Total Fair Value: ${result.total_fair_value:,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()

