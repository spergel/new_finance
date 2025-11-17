#!/usr/bin/env python3
"""
FSK (FS KKR Capital Corp) Custom Investment Extractor
Extracts investment data directly from SEC filings HTML tables.
"""

import logging
import os
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import csv
from collections import defaultdict
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(__file__))
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class FSKCustomExtractor:
    """Custom extractor for FSK that extracts data from SEC filings HTML tables."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "FSK"), year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from FSK's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise RuntimeError("Could not resolve CIK for FSK")
        
        logger.info(f"Found CIK: {cik}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise RuntimeError("Could not locate latest 10-Q index for FSK")
        
        logger.info(f"Filing index: {index_url}")
        
        # Get HTML URL - try to find the main filing document
        documents = self.sec_client.get_documents_from_index(index_url)
        
        # Try to find the main filing document (usually the largest .htm file or one with the ticker name)
        html_docs = [d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()]
        
        if not html_docs:
            raise RuntimeError("Could not find HTML document")
        
        # First, try to find one with ticker name
        main_html = None
        for doc in html_docs:
            if ticker.lower() in doc.filename.lower():
                main_html = doc
                break
        
        # If not found, try main filing (usually doesn't have "exhibit" in name)
        if not main_html:
            for doc in html_docs:
                if 'exhibit' not in doc.filename.lower() and 'index' not in doc.filename.lower():
                    main_html = doc
                    break
        
        # If still not found, try exhibit documents
        if not main_html:
            for doc in html_docs:
                if 'exhibit' in doc.filename.lower():
                    main_html = doc
                    break
        
        # Fallback to first HTML doc
        if not main_html:
            main_html = html_docs[0]
        
        htm_url = main_html.url
        logger.info(f"HTML URL: {htm_url} (file: {main_html.filename})")
        
        # Extract investments from HTML
        investments = self._parse_html_table(htm_url)
        logger.info(f"Extracted {len(investments)} investments from HTML")
        
        # Recalculate totals
        total_principal = sum(inv.get('principal_amount') or 0 for inv in investments)
        total_cost = sum(inv.get('cost') or 0 for inv in investments)
        total_fair_value = sum(inv.get('fair_value') or 0 for inv in investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'FSK_FS_KKR_Capital_Corp_investments.csv')
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate',
                'shares_units', 'percent_net_assets', 'currency', 'commitment_limit', 'undrawn_commitment'
            ])
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
        
        logger.info(f"Saved {len(investments)} investments to {output_file}")
        
        return {
            'company_name': 'FS KKR Capital Corp',
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _parse_html_table(self, html_url: str) -> List[Dict]:
        """Parse FSK's HTML schedule of investments table."""
        
        logger.info(f"Fetching HTML from {html_url}")
        resp = requests.get(html_url, headers=self.headers)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables")
        
        # Filter tables to only current period (skip December 2024)
        target_date_variants = ["september 30, 2025", "sep 30, 2025", "9/30/2025", "09/30/2025", "2025-09-30"]
        
        all_investments = []
        last_company = None
        last_industry = None
        current_investment_type = None
        
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
                    logger.debug(f"Table {table_idx} not a schedule table. Header: {header_text[:200]}")
                continue
            
            logger.info(f"Found schedule table {table_idx} with {len(rows)} rows")
            
            # Check if this table is for the target period
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
                logger.debug(f"Skipping table: not for current period")
                continue
            
            logger.info(f"Processing schedule table with {len(rows)} rows")
            
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
                logger.debug(f"Could not find header row, skipping table")
                continue
            
            # Parse investments from this table
            for i, row in enumerate(rows[header_row_idx + 1:], start=header_row_idx + 1):
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                
                # Expand cells to handle colspan - create a list that accounts for colspan
                cell_texts = []
                for cell in cells:
                    text = cell.get_text(strip=True)
                    colspan = int(cell.get('colspan', 1))
                    cell_texts.append(text)
                    # Add empty strings for additional colspan columns
                    for _ in range(colspan - 1):
                        cell_texts.append('')
                
                # Check if this is a section header (investment type)
                if self._is_section_header(cell_texts):
                    section_type = self._extract_investment_type_from_section_header(cell_texts)
                    if section_type:
                        current_investment_type = section_type
                        logger.debug(f"Found section header: {current_investment_type}")
                    continue
                
                # Skip header, total rows
                if self._is_header_row(cell_texts) or self._is_total_row(cell_texts):
                    continue
                
                # Parse investment row
                investment = self._parse_investment_row(cells, cell_texts, last_company, last_industry, current_investment_type)
                if investment:
                    if investment.get('company_name'):
                        last_company = investment['company_name']
                    if investment.get('industry'):
                        last_industry = investment['industry']
                    all_investments.append(investment)
        
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
            'amortized cost', 'par amount', 'loan', 'debt', 'equity', 'footnotes',
            'industry', 'rate', 'floor'
        ]
        
        matches = sum(1 for keyword in schedule_keywords if keyword in header_text)
        
        # Also check if table has many columns (schedule tables are usually wide)
        if len(rows) > 0:
            first_row_cells = len(rows[0].find_all(['td', 'th']))
            # FSK tables have many columns, so be more lenient
            if first_row_cells >= 8 and matches >= 2:
                return True
        
        # Need at least 3 matching keywords OR portfolio company + financial data
        has_portfolio_company = 'portfolio company' in header_text
        has_financial_data = any(kw in header_text for kw in ['principal', 'cost', 'fair value', 'amortized'])
        
        if has_portfolio_company and has_financial_data:
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
    
    def _extract_investment_type_from_section_header(self, cell_texts: List[str]) -> Optional[str]:
        """Extract investment type from section header row."""
        if not cell_texts:
            return None
        
        header_text = ' '.join(cell_texts).lower()
        
        # Map section headers to investment types
        if 'first lien' in header_text:
            return 'First Lien Debt'
        elif 'second lien' in header_text:
            return 'Second Lien Debt'
        elif 'subordinated' in header_text:
            return 'Subordinated Debt'
        elif 'senior secured' in header_text and 'first lien' not in header_text:
            return 'Senior Secured Debt'
        elif 'unsecured' in header_text:
            return 'Unsecured Debt'
        elif 'mezzanine' in header_text:
            return 'Mezzanine Debt'
        elif 'preferred' in header_text:
            return 'Preferred Equity'
        elif 'common' in header_text:
            return 'Common Equity'
        elif 'warrant' in header_text:
            return 'Warrant'
        
        return None
    
    def _parse_investment_row(self, cells: List, cell_texts: List[str], 
                             last_company: str, last_industry: str, current_investment_type: Optional[str]) -> Optional[Dict]:
        """Parse an investment row from FSK's HTML table.
        
        FSK table structure (from actual table):
        - Column 0: Portfolio Company (company name)
        - Column 1: Footnotes (like (v), (i)(v), (x))
        - Column 2: Industry (like "Software & Services")
        - Column 3: Reference Rate (SF, E, SA, SR, etc.)
        - Column 4: "+" (separator)
        - Column 5: Spread (e.g., "6.0%")
        - Column 6-7: PIK rate info (e.g., "(3.5% PIK / 3.5% PIK)")
        - Column 8: Floor (e.g., "0.8%")
        - Column 9: Maturity (MM/YYYY format, e.g., "11/2026")
        - Column 10: "$" or currency symbol (€, £, SEK, etc.)
        - Column 11: Principal Amount (in millions, e.g., "1.2", "122.5")
        - Column 12: "$" or empty
        - Column 13: Amortized Cost (in millions)
        - Column 14: "$" or empty
        - Column 15: Fair Value (in millions)
        """
        
        try:
            # Debug: print first few rows to understand structure
            if len(cell_texts) > 0 and len(cell_texts) < 20:
                logger.debug(f"Row cells ({len(cell_texts)}): {cell_texts[:10]}")
            
            # Get company name (column 0)
            company_name = cell_texts[0] if len(cell_texts) > 0 else ""
            if not company_name or company_name.strip() == "":
                company_name = last_company
            
            if not company_name:
                return None
            
            # Clean company name (remove footnotes in parentheses that might be in the name itself)
            company_name = re.sub(r'\s*\([^)]*\)', '', company_name).strip()
            
            # Based on actual HTML structure after colspan expansion:
            # Col 0: Company, Col 6: Footnotes, Col 12: Industry, Col 18: Ref Rate, 
            # Col 21: '+', Col 24: Spread, Col 36: Floor, Col 42: Maturity,
            # Col 49: Principal, Col 55: Cost, Col 61: Fair Value
            
            # Get industry (column 12 after colspan expansion)
            industry = None
            if len(cell_texts) > 12:
                industry = cell_texts[12].strip()
                # Skip if it looks like footnotes
                if industry and re.match(r'^\([a-z]+\)+$', industry):
                    industry = None
            
            # If not found at expected position, search around it
            if not industry or industry == "":
                for idx in range(10, min(15, len(cell_texts))):
                    potential = cell_texts[idx].strip()
                    if potential and len(potential) > 3 and not re.match(r'^\([a-z]+\)+$', potential) and not re.match(r'^[A-Z]{1,2}$', potential) and potential not in ['+', '%', '$', '€', '£', 'SEK', '—']:
                        industry = potential
                        break
            
            if not industry or industry.strip() == "":
                industry = last_industry or "Unknown"
            else:
                industry = industry.strip()
                # Update last_industry if we found a new one
                if industry != "Unknown":
                    last_industry = industry
            
            # Extract reference rate (column 18 after colspan expansion)
            reference_rate = None
            ref_rate_idx = None
            if len(cell_texts) > 18:
                ref_text = cell_texts[18].strip()
                if ref_text in ['SF', 'E', 'SA', 'SR', 'B', 'L', 'SOFR', 'EURIBOR', 'SONIA', 'STIBOR', 'BBSW', 'LIBOR']:
                    ref_rate_idx = 18
                    ref_map = {
                        'SF': 'SOFR', 'E': 'EURIBOR', 'SA': 'SONIA', 
                        'SR': 'STIBOR', 'B': 'BBSW', 'L': 'LIBOR'
                    }
                    reference_rate = ref_map.get(ref_text, ref_text)
            
            # If not found, search around expected position
            if not reference_rate:
                for idx in range(15, min(25, len(cell_texts))):
                    ref_text = cell_texts[idx].strip()
                    if ref_text in ['SF', 'E', 'SA', 'SR', 'B', 'L']:
                        ref_rate_idx = idx
                        ref_map = {
                            'SF': 'SOFR', 'E': 'EURIBOR', 'SA': 'SONIA', 
                            'SR': 'STIBOR', 'B': 'BBSW', 'L': 'LIBOR'
                        }
                        reference_rate = ref_map.get(ref_text, ref_text)
                        break
            
            # Extract spread (column 24 after colspan expansion, after "+" at 21)
            spread = None
            interest_rate = None
            if len(cell_texts) > 24:
                spread_text = cell_texts[24].strip()
                if spread_text and '%' in spread_text:
                    spread = spread_text
                    interest_rate = spread_text
                elif spread_text and spread_text.replace('.', '').replace('%', '').isdigit():
                    spread = spread_text if '%' in spread_text else spread_text + '%'
                    interest_rate = spread
            
            # Extract PIK rate (after spread, around columns 25-30)
            pik_rate = None
            if len(cell_texts) > 25:
                pik_text = ""
                for idx in range(25, min(35, len(cell_texts))):
                    pik_text += " " + cell_texts[idx].strip()
                pik_text = pik_text.strip()
                if 'PIK' in pik_text:
                    # Look for pattern like "(X.X% PIK / Y.Y% PIK)" - take the second one
                    pik_matches = re.findall(r'(\d+\.\d+)%\s*PIK', pik_text)
                    if pik_matches:
                        pik_rate = pik_matches[-1] + '%'  # Take the last PIK rate
            
            # Extract floor (column 36 after colspan expansion)
            floor_rate = None
            if len(cell_texts) > 36:
                floor_text = cell_texts[36].strip()
                if floor_text and '%' in floor_text:
                    floor_rate = floor_text
                elif floor_text and floor_text.replace('.', '').isdigit():
                    floor_rate = floor_text + '%'
            
            # If not found, search around expected position
            if not floor_rate:
                for idx in range(30, min(45, len(cell_texts))):
                    floor_text = cell_texts[idx].strip()
                    if floor_text and '%' in floor_text and 'PIK' not in floor_text:
                        floor_rate = floor_text
                        break
            
            # Extract maturity date (column 42 after colspan expansion, MM/YYYY format)
            maturity_date = None
            if len(cell_texts) > 42:
                maturity_text = cell_texts[42].strip()
                if maturity_text and re.match(r'\d{1,2}/\d{4}', maturity_text):
                    match = re.match(r'(\d{1,2})/(\d{4})', maturity_text)
                    if match:
                        month = match.group(1).zfill(2)
                        year = match.group(2)
                        maturity_date = f"{month}/01/{year}"
            
            # If not found, search around expected position
            if not maturity_date:
                for idx in range(40, min(50, len(cell_texts))):
                    maturity_text = cell_texts[idx].strip()
                    if maturity_text and re.match(r'\d{1,2}/\d{4}', maturity_text):
                        match = re.match(r'(\d{1,2})/(\d{4})', maturity_text)
                        if match:
                            month = match.group(1).zfill(2)
                            year = match.group(2)
                            maturity_date = f"{month}/01/{year}"
                            break
            
            # Extract Principal Amount, Cost, and Fair Value
            # After colspan expansion: Col 49: Principal, Col 55: Cost, Col 61: Fair Value (in millions)
            principal = None
            cost = None
            fair_value = None
            
            # Principal (column 49)
            if len(cell_texts) > 49:
                principal_text = cell_texts[49].strip()
                if principal_text and principal_text not in ['—', '', ' ', '$', '€', '£', 'SEK']:
                    try:
                        principal_val = float(principal_text.replace(',', ''))
                        if 0.1 <= principal_val <= 10000:
                            principal = int(principal_val * 1000000)
                    except (ValueError, TypeError):
                        pass
            
            # Cost (column 55)
            if len(cell_texts) > 55:
                cost_text = cell_texts[55].strip()
                if cost_text and cost_text not in ['—', '', ' ', '$', '€', '£', 'SEK']:
                    try:
                        cost_val = float(cost_text.replace(',', ''))
                        if 0.1 <= cost_val <= 10000:
                            cost = int(cost_val * 1000000)
                    except (ValueError, TypeError):
                        pass
            
            # Fair Value (column 61)
            if len(cell_texts) > 61:
                fv_text = cell_texts[61].strip()
                if fv_text and fv_text not in ['—', '', ' ', '$', '€', '£', 'SEK']:
                    try:
                        fv_val = float(fv_text.replace(',', ''))
                        if 0.1 <= fv_val <= 10000:
                            fair_value = int(fv_val * 1000000)
                    except (ValueError, TypeError):
                        pass
            
            # Fallback: search for financial values if not found at expected positions
            if not principal or not cost or not fair_value:
                financial_values = []
                for idx, cell_text in enumerate(cell_texts):
                    text = cell_text.strip()
                    # Skip currency symbols, separators, and non-numeric
                    if text in ['$', '€', '£', 'SEK', '+', '—', '', ' ']:
                        continue
                    # Check if it's a number (could be in millions like "1.2" or "122.5")
                    try:
                        val = float(text.replace(',', ''))
                        # If it's a reasonable value for millions (0.1 to 10000), store it
                        if 0.1 <= val <= 10000:
                            financial_values.append((idx, val))
                    except (ValueError, TypeError):
                        continue
                
                # The last 3 financial values should be Principal, Cost, Fair Value
                if len(financial_values) >= 3 and (not principal or not cost or not fair_value):
                    # Take the last 3 values
                    if not principal:
                        principal = int(financial_values[-3][1] * 1000000)
                    if not cost:
                        cost = int(financial_values[-2][1] * 1000000)
                    if not fair_value:
                        fair_value = int(financial_values[-1][1] * 1000000)
                elif len(financial_values) == 2:
                    if not cost:
                        cost = int(financial_values[-2][1] * 1000000)
                    if not fair_value:
                        fair_value = int(financial_values[-1][1] * 1000000)
                elif len(financial_values) == 1:
                    if not fair_value:
                        fair_value = int(financial_values[-1][1] * 1000000)
            
            # Determine investment type
            investment_type = current_investment_type or "First Lien Debt"  # Default
            
            # Standardize investment type
            investment_type = standardize_investment_type(investment_type)
            industry = standardize_industry(industry)
            reference_rate = standardize_reference_rate(reference_rate) if reference_rate else None
            
            # Must have at least principal or fair value to be a valid investment
            if not principal and not fair_value:
                return None
            
            return {
                'company_name': company_name,
                'business_description': "",
                'investment_type': investment_type,
                'industry': industry,
                'acquisition_date': None,
                'maturity_date': maturity_date,
                'interest_rate': interest_rate,
                'reference_rate': reference_rate,
                'spread': spread,
                'floor_rate': floor_rate,
                'pik_rate': pik_rate,
                'principal_amount': principal,
                'cost': cost,
                'fair_value': fair_value,
                'shares_units': None,
                'percent_net_assets': None
            }
        
        except Exception as e:
            logger.warning(f"Failed to parse row: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
