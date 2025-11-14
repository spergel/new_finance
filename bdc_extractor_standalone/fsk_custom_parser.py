#!/usr/bin/env python3
"""
Custom FSK (FS KKR Capital Corp) Investment Extractor

Extracts investment data directly from HTML tables with XBRL inline elements.
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

from xbrl_typed_extractor import BDCExtractionResult
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class FSKCustomExtractor:
    """Custom extractor for FSK that extracts data from HTML tables with XBRL inline elements."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
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
        
        # Get HTML URL - try to find the main filing document
        documents = self.sec_client.get_documents_from_index(index_url)
        
        # Try to find the main filing document (usually the largest .htm file or one with the ticker name)
        html_docs = [d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()]
        
        if not html_docs:
            raise RuntimeError("Could not find HTML document")
        
        # Try to find the main filing document (usually the largest or one with ticker name)
        # Schedule of investments might be in the main filing, not an exhibit
        main_html = None
        
        # First, try to find one with ticker name
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
        
        return self.extract_from_filing(htm_url, "FS KKR Capital Corp", cik, ticker)
    
    def extract_from_filing(self, html_url: str, company_name: str, cik: str, ticker: str = "FSK") -> BDCExtractionResult:
        """Extract complete FSK investment data from HTML tables."""
        
        logger.info(f"Starting FSK extraction from HTML...")
        
        investments = self._parse_html_table(html_url)
        logger.info(f"Extracted {len(investments)} investments from HTML")
        
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
        output_file = os.path.join(output_dir, f'{ticker}_FS_KKR_Capital_Corp_investments.csv')
        
        self._save_to_csv(investments, output_file)
        logger.info(f"Saved {len(investments)} investments to {output_file}")
        
        return BDCExtractionResult(
            company_name=company_name,
            cik=cik,
            filing_date=None,  # HTML-only extraction
            filing_url=html_url,
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
        """Parse FSK's HTML schedule of investments table with XBRL inline elements."""
        
        logger.info(f"Fetching HTML from {html_url}")
        resp = requests.get(html_url, headers=self.headers)
        resp.raise_for_status()
        
        # Parse with HTML parser (BeautifulSoup handles XBRL inline elements)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables")
        
        all_investments = []
        target_date = "September 30, 2025"
        target_date_variants = ["9/30/2025", "09/30/2025", "September 30, 2025", "Sep 30, 2025"]
        
        for table_idx, table in enumerate(tables):
            # Check if this table is for the target period
            if not self._is_table_for_period(table, target_date, target_date_variants):
                continue
            
            # Check if this is a schedule table
            if not self._is_schedule_table(table):
                continue
            
            logger.info(f"Processing schedule table {table_idx + 1}")
            
            rows = self._table_to_rows(table)
            if not rows:
                continue
            
            # Find header row
            header_row_idx = None
            for i, row in enumerate(rows):
                if self._is_header_row(row):
                    header_row_idx = i
                    break
            
            if header_row_idx is None:
                continue
            
            # Process data rows
            last_company = ""
            last_industry = ""
            current_investment_type = None  # Track current section's investment type
            
            for i in range(header_row_idx + 1, len(rows)):
                row = rows[i]
                cell_texts = [self._normalize_text(cell) for cell in row]
                
                # Skip empty rows
                if not any(cell_texts):
                    continue
                
                # Skip total rows
                if self._is_total_row(cell_texts):
                    continue
                
                # Check if this is a section header - extract investment type from it
                if self._is_section_header(cell_texts):
                    section_type = self._extract_investment_type_from_section_header(cell_texts)
                    if section_type:
                        current_investment_type = section_type
                        logger.debug(f"Found section header: {cell_texts[0][:50]} -> {current_investment_type}")
                    continue
                
                # Check if this is an investment row
                if self._is_investment_row(cell_texts, last_company):
                    inv = self._parse_investment_row(table, row, i, cell_texts, last_company, last_industry, current_investment_type)
                    if inv:
                        if inv.get('company_name'):
                            last_company = inv['company_name']
                        if inv.get('industry'):
                            last_industry = inv['industry']
                        all_investments.append(inv)
        
        return all_investments
    
    def _is_table_for_period(self, table: BeautifulSoup, target_date: str, target_date_variants: List[str]) -> bool:
        """Check if table is for the target reporting period."""
        
        # Get table text to check for dates
        table_text = table.get_text().lower()
        
        # Check for exclusion dates (e.g., December 31, 2024)
        exclusion_dates = ["december 31, 2024", "12/31/2024"]
        for excl_date in exclusion_dates:
            if excl_date in table_text:
                return False
        
        # If no explicit exclusion date found, assume it's for current period (Q3 2025)
        # since we're processing the latest 10-Q
        return True
    
    def _get_table_context(self, table: BeautifulSoup) -> str:
        """Get text context before a table."""
        context_parts = []
        
        # Look at previous siblings
        for prev in table.find_all_previous(string=True, limit=20):
            text = prev.strip()
            if text and len(text) > 3:
                context_parts.append(text)
                if len(context_parts) >= 5:
                    break
        
        return " ".join(context_parts)
    
    def _is_schedule_table(self, table: BeautifulSoup) -> bool:
        """Check if table is a schedule of investments table."""
        
        # Get raw HTML text to check for keywords (handles XBRL namespaces better)
        table_html = str(table).lower()
        
        # Look for schedule keywords in raw HTML
        header_keywords = ["portfolio company", "principal", "cost", "fair value", "maturity", "rate", "floor", "amortized", "amortized cost"]
        
        matches = sum(1 for keyword in header_keywords if keyword in table_html)
        
        # Also check table structure
        rows = self._table_to_rows(table)
        if len(rows) < 2:
            return False
        
        # Check first few rows for header keywords in text
        header_text = " ".join([cell.lower() for row in rows[:5] for cell in row])
        text_matches = sum(1 for keyword in header_keywords if keyword in header_text)
        
        # Need "portfolio company" in HTML or text, plus financial values
        has_portfolio_company = "portfolio company" in table_html or "portfolio company" in header_text
        has_financial_values = any(kw in table_html or kw in header_text for kw in ["principal", "cost", "fair value", "amortized"])
        
        if has_portfolio_company and has_financial_values:
            return True
        
        # Also check if table has many columns (schedule tables are usually wide)
        if len(rows) > 0:
            first_row_cells = len(rows[0])
            # FSK tables have many columns due to colspan, so check for wide tables
            if first_row_cells >= 8 and (matches >= 2 or text_matches >= 2):
                return True
        
        return matches >= 3 or text_matches >= 3  # Need at least 3 matching keywords
    
    def _is_header_row(self, row: List[str]) -> bool:
        """Check if row is a header row."""
        if not row:
            return False
        
        row_text = " ".join([cell.lower() for cell in row])
        header_keywords = ["portfolio company", "principal", "cost", "fair value", "maturity", "rate", "floor"]
        
        return any(keyword in row_text for keyword in header_keywords)
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if row is a total/summary row."""
        if not cell_texts:
            return False
        
        first_cell = cell_texts[0].strip().lower()
        
        # Check for total keywords
        total_keywords = ["total", "subtotal"]
        if any(keyword in first_cell for keyword in total_keywords):
            return True
        
        return False
    
    def _is_section_header(self, cell_texts: List[str]) -> bool:
        """Check if row is a section header (e.g., 'Senior Secured Loans—First Lien—126.4%')."""
        if not cell_texts:
            return False
        
        first_cell = cell_texts[0].strip().lower()
        
        # Section headers often have percentages and keywords
        section_keywords = ["senior secured loans", "first lien", "second lien", "subordinated",
                          "control investments", "non-control", "non-affiliate", "affiliate investments",
                          "senior secured", "unsecured", "mezzanine", "preferred", "common", "warrant"]
        
        has_percentage = any('%' in cell for cell in cell_texts[:3])
        has_section_keyword = any(keyword in first_cell for keyword in section_keywords)
        
        # Section headers typically have the keyword and either a percentage or are short enough to be a header
        return has_section_keyword and (has_percentage or len(first_cell) < 100)
    
    def _extract_investment_type_from_section_header(self, cell_texts: List[str]) -> Optional[str]:
        """Extract investment type from section header row.
        
        Examples:
        - "Senior Secured Loans—First Lien—126.4%" -> "First Lien Debt"
        - "Senior Secured Loans—Second Lien—5.2%" -> "Second Lien Debt"
        - "Subordinated Debt—10.5%" -> "Subordinated Debt"
        """
        if not cell_texts:
            return None
        
        first_cell = cell_texts[0].strip()
        if not first_cell:
            return None
        
        # Remove percentage and dashes/em dashes
        # Handle both regular dashes and em dashes (—)
        text = first_cell.replace('—', '-').replace('–', '-')
        # Remove percentage like "126.4%"
        text = re.sub(r'\s*-\s*\d+\.?\d*%', '', text).strip()
        text = re.sub(r'\d+\.?\d*%', '', text).strip()
        text = text.strip('-').strip()
        
        text_lower = text.lower()
        
        # Map section headers to investment types
        if 'first lien' in text_lower:
            return "First Lien Debt"
        elif 'second lien' in text_lower:
            return "Second Lien Debt"
        elif 'subordinated' in text_lower:
            return "Subordinated Debt"
        elif 'mezzanine' in text_lower:
            return "Mezzanine Debt"
        elif 'senior secured' in text_lower:
            # If it says "Senior Secured" but doesn't specify lien, default to First Lien
            return "First Lien Debt"
        elif 'unsecured' in text_lower:
            return "Unsecured Debt"
        elif 'preferred' in text_lower:
            return "Preferred Equity"
        elif 'common' in text_lower:
            return "Common Equity"
        elif 'warrant' in text_lower:
            return "Warrants"
        elif 'control investment' in text_lower or 'non-control' in text_lower:
            # Control/non-control is a classification, not an investment type
            # Keep the current type or default
            return None
        
        # If we have "Senior Secured Loans" without lien specification, default to First Lien
        if 'senior secured' in text_lower and 'loan' in text_lower:
            return "First Lien Debt"
        
        return None
    
    def _is_investment_row(self, cell_texts: List[str], last_company: str) -> bool:
        """Check if row is an investment data row."""
        if not cell_texts:
            return False
        
        # Must have company name (in first column or use last_company)
        company_name = cell_texts[0].strip() if len(cell_texts) > 0 else ""
        if not company_name and not last_company:
            return False
        
        # Skip if it looks like a section header or total
        if company_name:
            company_lower = company_name.lower()
            if any(keyword in company_lower for keyword in ["total", "senior secured", "first lien", "second lien", "subtotal"]):
                return False
        
        # Must have at least one financial value (principal, cost, or fair value)
        # These are typically in the last few columns
        has_financial_value = False
        for cell in cell_texts:
            if cell and self._looks_like_money(cell):
                has_financial_value = True
                break
        
        # Also check for XBRL values embedded in text (numbers that look like money)
        if not has_financial_value:
            for cell in cell_texts:
                if cell:
                    # Look for patterns like "1.2" or "122.5" (millions)
                    if re.search(r'\d+\.\d+', cell) and len(cell) < 20:
                        try:
                            val = float(cell.replace(',', '').strip())
                            if 0.1 <= val <= 10000:  # Reasonable range for millions
                                has_financial_value = True
                                break
                        except:
                            pass
        
        return has_financial_value
    
    def _looks_like_money(self, text: str) -> bool:
        """Check if text looks like a monetary value."""
        if not text:
            return False
        
        # Remove common non-numeric characters
        clean = text.replace(',', '').replace('$', '').replace('(', '').replace(')', '').strip()
        
        # Check if it's a number
        try:
            float(clean)
            return True
        except (ValueError, TypeError):
            return False
        
    def _parse_investment_row(self, table: BeautifulSoup, row: List[str], row_idx: int,
                              cell_texts: List[str], last_company: str, last_industry: str, 
                              current_investment_type: Optional[str] = None) -> Optional[Dict]:
        """Parse an investment row from FSK's HTML table.
        
        FSK table structure (after colspan expansion):
        - Col 0: Portfolio Company
        - Col 1: Footnotes
        - Col 2: Industry
        - Col 3-5: Rate (Reference Rate, "+", Spread, sometimes PIK)
        - Col 6: Floor
        - Col 7: Maturity
        - Col 8-9: Principal Amount (with $ in previous cell, values in millions)
        - Col 10-11: Amortized Cost (with $ in previous cell, values in millions)
        - Col 12-13: Fair Value (with $ in previous cell, values in millions)
        """
        
        try:
            # Get the actual row element
            rows = table.find_all('tr')
            if row_idx >= len(rows):
                return None
            
            actual_row = rows[row_idx]
            cells = actual_row.find_all(['td', 'th'])
            
            # Extract company name (col 0)
            company_name = cell_texts[0] if len(cell_texts) > 0 else ""
            if not company_name or company_name.strip() == "":
                company_name = last_company
            
            if not company_name:
                return None
            
            # Clean company name (remove footnotes)
            company_name = self._normalize_company_name(company_name)
            
            # Extract industry (col 2)
            industry = cell_texts[2] if len(cell_texts) > 2 else ""
            if not industry or industry.strip() == "":
                industry = last_industry if last_industry else "Unknown"
            
            # Extract reference rate and spread from Rate column
            # Format: "SF" (or "E"), "+", "6.0%", sometimes "(3.5% PIK / 3.5% PIK)"
            reference_rate = None
            spread = None
            pik_rate = None
            floor_rate = None
            
            # Find Rate column (usually around col 3-5)
            for i in range(3, min(6, len(cell_texts))):
                cell_text = cell_texts[i] if i < len(cell_texts) else ""
                if cell_text:
                    # Check for reference rate indicators
                    if cell_text.upper() in ['SF', 'SOFR']:
                        reference_rate = "SOFR"
                    elif cell_text.upper() in ['E', 'EURIBOR']:
                        reference_rate = "EURIBOR"
                    elif cell_text.upper() in ['L', 'LIBOR']:
                        reference_rate = "LIBOR"
                    elif cell_text.upper() in ['P', 'PRIME']:
                        reference_rate = "Prime"
                    
                    # Check for spread (percentage)
                    spread_match = re.search(r'([\d.]+)%', cell_text)
                    if spread_match:
                        spread = f"{spread_match.group(1)}%"
                    
                    # Check for PIK rate
                    pik_match = re.search(r'\(([\d.]+)%\s*PIK', cell_text, re.IGNORECASE)
                    if pik_match:
                        pik_rate = f"{pik_match.group(1)}%"
            
            # Extract floor rate (col 6)
            floor_str = cell_texts[6] if len(cell_texts) > 6 else ""
            if floor_str and floor_str.strip() and floor_str not in ['—', '', ' ', 'N/A']:
                floor_match = re.search(r'([\d.]+)%', floor_str)
                if floor_match:
                    floor_rate = f"{floor_match.group(1)}%"
            
            # Extract maturity date (col 7)
            maturity_date = cell_texts[7] if len(cell_texts) > 7 else ""
            if maturity_date and maturity_date not in ['—', '', ' ', 'N/A']:
                # Format: "11/2026" -> "11/01/2026"
                maturity_match = re.match(r'(\d{1,2})/(\d{4})', maturity_date)
                if maturity_match:
                    month = maturity_match.group(1).zfill(2)
                    year = maturity_match.group(2)
                    maturity_date = f"{month}/01/{year}"
                else:
                    maturity_date = self._normalize_date(maturity_date)
            else:
                maturity_date = None
            
            # Extract Principal Amount (col 8-9, values in millions)
            principal_amount = self._extract_money_value(cells, cell_texts, 8, 9)
            
            # Extract Amortized Cost (col 10-11, values in millions)
            cost_basis = self._extract_money_value(cells, cell_texts, 10, 11)
            
            # Extract Fair Value (col 12-13, values in millions)
            fair_value = self._extract_money_value(cells, cell_texts, 12, 13)
            
            # If we have no principal, cost, or fair value, skip this row
            if not principal_amount and not cost_basis and not fair_value:
                return None
            
            # Determine investment type from section header or default
            if current_investment_type:
                investment_type = current_investment_type
            else:
                # Default to First Lien Debt for FSK (most common)
                investment_type = "First Lien Debt"
            
            return {
                'company_name': company_name,
                'business_description': "",
                'investment_type': investment_type,
                'industry': industry,
                'acquisition_date': None,
                'maturity_date': maturity_date,
                'principal_amount': principal_amount,
                'cost_basis': cost_basis,
                'fair_value': fair_value,
                'interest_rate': None,  # Not directly available, would need to calculate from spread + floor
                'reference_rate': reference_rate,
                'spread': spread,
                'floor_rate': floor_rate,
                'pik_rate': pik_rate,
                'shares_units': None,
                'percent_net_assets': None
            }
        
        except Exception as e:
            logger.warning(f"Failed to parse row for {last_company}: {e}")
            return None
    
    def _extract_money_value(self, cells: List, cell_texts: List[str], col_start: int, col_end: int) -> Optional[float]:
        """Extract monetary value from HTML table cells.
        
        Args:
            cells: List of cell elements
            cell_texts: List of cell text values (already expanded for colspan)
            col_start: Starting column index to search
            col_end: Ending column index to search
        """
        # Search in a wider range to account for colspan variations
        search_start = max(0, col_start - 2)
        search_end = min(len(cell_texts), col_end + 3)
        
        for i in range(search_start, search_end):
            if i >= len(cell_texts):
                continue
            
            text = cell_texts[i]
            if not text or text.strip() in ['—', '', ' ', '$', 'N/A', '&nbsp;', '+', '%']:
                continue
            
            # Check if previous cell has "$" or if current cell has "$"
            has_dollar = False
            if i > 0 and i - 1 < len(cell_texts):
                prev_text = cell_texts[i - 1].strip()
                if prev_text == '$' or '$' in prev_text:
                    has_dollar = True
            
            if '$' in text:
                has_dollar = True
            
            # Try to extract number (could be in XBRL format like "1.2" or "122.5")
            if has_dollar or self._looks_like_money(text):
                try:
                    # Extract number from text - handle both formatted and plain numbers
                    # Remove everything except digits and decimal point
                    value_str = re.sub(r'[^\d.]', '', text.replace(',', '').strip())
                    if value_str:
                        value = float(value_str)
                        # Values in table are in millions, so multiply by 1,000,000
                        # But only if it's a reasonable value (not a percentage or small number)
                        if value >= 0.1:  # At least 0.1 million = $100K
                            value = value * 1000000
                            return value
                except (ValueError, TypeError):
                    continue
            
            # Also try to extract from XBRL inline elements in the cell
            if i < len(cells):
                cell = cells[i]
                # Look for any number in the cell that looks like money
                cell_text_full = cell.get_text(strip=True)
                # Look for patterns like "1.2" or "122.5" (millions) that aren't percentages
                number_match = re.search(r'(\d+\.?\d*)', cell_text_full)
                if number_match and '%' not in cell_text_full:
                    try:
                        value = float(number_match.group(1))
                        if 0.1 <= value <= 10000:  # Reasonable range for millions
                            value = value * 1000000
                            return value
                    except (ValueError, TypeError):
                        pass
        
        return None
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name by removing footnotes."""
        if not name:
            return ""
        
        # Remove footnote patterns like "(v)", "(i)(v)", etc.
        name = re.sub(r'\s*\([^)]*\)', '', name).strip()
        return name
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text by removing extra whitespace."""
        if not text:
            return ""
        return ' '.join(text.split())
    
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
    
    def _table_to_rows(self, table: BeautifulSoup) -> List[List[str]]:
        """Convert table to list of rows (list of cell strings), handling colspan."""
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            vals = []
            for c in cells:
                # Get text from cell, including XBRL inline elements
                cell_text = self._normalize_text(c.get_text(" ", strip=True))
                
                # If cell is empty, try to get text from XBRL elements
                if not cell_text or cell_text.strip() == "":
                    # Look for XBRL nonfraction elements
                    xbrl_elems = c.find_all(attrs={'name': True}) + c.find_all(attrs={'scale': True})
                    for elem in xbrl_elems:
                        elem_text = elem.get_text(strip=True)
                        if elem_text:
                            cell_text = elem_text
                            break
                
                # Handle colspan - add the cell value once, then empty strings for remaining columns
                colspan = int(c.get('colspan', 1))
                vals.append(cell_text)
                # Add empty strings for remaining colspan columns
                for _ in range(colspan - 1):
                    vals.append("")
            rows.append(vals)
        return rows
    
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
    
    extractor = FSKCustomExtractor()
    try:
        result = extractor.extract_from_ticker("FSK")
        print(f"\n[SUCCESS] Successfully extracted {result.total_investments} investments")
        print(f"  Total Principal: ${result.total_principal:,.0f}")
        print(f"  Total Cost: ${result.total_cost:,.0f}")
        print(f"  Total Fair Value: ${result.total_fair_value:,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()



