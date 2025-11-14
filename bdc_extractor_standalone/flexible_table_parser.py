#!/usr/bin/env python3
"""
Flexible HTML Table Parser for BDC Investment Schedules

Automatically detects column headers and extracts data based on keywords,
adapting to different BDC table formats.
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
import requests
from rate_normalization import (
    clean_percentage,
    normalize_interest_fields,
    normalize_reference,
)

logger = logging.getLogger(__name__)

class ColumnMapper:
    """Maps table columns to data fields based on header text."""
    
    # Column identification keywords (order matters - more specific first)
    COLUMN_KEYWORDS = {
        'company_name': [
            'portfolio company', 'portfolio companies', 'portfolio investments', 'company', 'borrower', 'issuer', 'investment'
        ],
        'business_description': [
            'business description', 'description', 'industry sector', 'business'
        ],
        'investment_type': [
            'type of investment', 'investment type', 'investment', 'type', 'security type', 'class', 'instrument type',
            'senior secured', 'first lien', 'second lien', 'subordinated', 'convertible', 'preferred', 'common', 'warrant'
        ],
        'acquisition_date': [
            'acquisition date', 'acquisition', 'date acquired', 'orig date', 'origination', 'investment date', 'purchase date', 'origination date'
        ],
        'maturity_date': [
            'maturity date', 'maturity', 'due date', 'due', 'maturity date (mm/dd/yyyy)',
            'maturity date*', 'maturity*', 'expiration date', 'exp date', 'mat date',
            'expiration', 'maturity date', 'mat', 'exp'
        ],
        'principal_amount': [
            'outstanding principal', 'principal amount', 'par amount', 'principal', 'par value', 'par'
        ],
        'cost': [
            'amortized cost', 'cost basis', 'cost', 'book value'
        ],
        'fair_value': [
            'fair value', 'market value', 'value', 'fv'
        ],
        'interest_rate': [
            'interest rate', 'coupon', 'rate', 'current rate', 'total rate', 'cash rate', 'yield', 'coupon rate',
            'interest', 'fixed rate', 'variable rate'
        ],
        'reference_rate': [
            'reference rate', 'reference', 'index', 'base rate', 'benchmark'
        ],
        'spread': [
            'spread', 'margin'
        ],
        'floor_rate': [
            'floor', 'floor rate', 'minimum rate', 'min rate'
        ],
        'pik_rate': [
            'pik', 'pik rate', 'payment in kind', 'payment-in-kind'
        ],
        'shares_units': [
            'shares/units', 'shares', 'units', 'quantity'
        ],
        'percent_net_assets': [
            '% of net assets', 'percent of net assets', '%', 'net assets'
        ],
        'currency': [
            'currency', 'curr', 'ccy'
        ],
        'commitment_limit': [
            'commitment', 'commitment limit', 'total commitment', 'facility limit'
        ],
        'undrawn_commitment': [
            'undrawn', 'undrawn commitment', 'available', 'unfunded'
        ],
        'geographic_location': [
            'geographic location', 'location', 'geography', 'region', 'country', 'state', 'jurisdiction'
        ],
        'credit_rating': [
            'credit rating', 'rating', 's&p rating', 'moody\'s rating', 'fitch rating', 's&p', 'moody', 'fitch'
        ],
        'payment_status': [
            'payment status', 'status', 'performing', 'non-accrual', 'non accrual', 'nonperforming', 'non performing', 'accrual status'
        ],
        'footnotes': [
            'footnotes', 'footnote', 'notes', 'fn'
        ]
    }
    
    def __init__(self):
        """Initialize the column mapper."""
        self.column_map = {}
        self.total_columns = 0
    
    def map_headers(self, header_cells: List) -> Dict[str, int]:
        """
        Map header cells to field names.
        
        Args:
            header_cells: List of header cell elements
            
        Returns:
            Dict mapping field names to column indices
        """
        self.total_columns = len(header_cells)
        self.column_map = {}
        principal_col = None
        
        for idx, cell in enumerate(header_cells):
            header_text = self._clean_header_text(cell.get_text())
            field_name = self._identify_field(header_text)
            
            if field_name:
                self.column_map[field_name] = idx
                logger.debug(f"Column {idx}: '{header_text}' → {field_name}")
                
                # Track principal column for offset calculation
                if field_name == 'principal_amount':
                    principal_col = idx
        
        # Special handling for ARCC/BXSL format: Cost and Fair Value may have offsets from Principal column
        # Try to find cost/fair_value by position if not found by header
        if principal_col is not None:
            # If cost not found, try common offsets
            if 'cost' not in self.column_map and principal_col + 3 < self.total_columns:
                # Check if column at offset looks like cost (has numbers, $, etc.)
                if principal_col + 3 < len(header_cells):
                    offset_cell_text = self._clean_header_text(header_cells[principal_col + 3].get_text())
                    if any(kw in offset_cell_text for kw in ['cost', 'amortized', 'book']):
                        self.column_map['cost'] = principal_col + 3
                        logger.debug(f"Inferred cost column at offset {principal_col + 3}")
            
            # If fair_value not found, try common offsets
            if 'fair_value' not in self.column_map and principal_col + 6 < self.total_columns:
                if principal_col + 6 < len(header_cells):
                    offset_cell_text = self._clean_header_text(header_cells[principal_col + 6].get_text())
                    if any(kw in offset_cell_text for kw in ['fair', 'value', 'market']):
                        self.column_map['fair_value'] = principal_col + 6
                        logger.debug(f"Inferred fair_value column at offset {principal_col + 6}")
            
            # If still not found, try scanning nearby columns for financial keywords
            if 'cost' not in self.column_map:
                for offset in [2, 3, 4]:
                    col_idx = principal_col + offset
                    if col_idx < len(header_cells):
                        cell_text = self._clean_header_text(header_cells[col_idx].get_text())
                        if any(kw in cell_text for kw in ['cost', 'amortized', 'book']):
                            self.column_map['cost'] = col_idx
                            logger.debug(f"Found cost column at {col_idx} by scanning")
                            break
            
            if 'fair_value' not in self.column_map:
                for offset in [5, 6, 7, 8]:
                    col_idx = principal_col + offset
                    if col_idx < len(header_cells):
                        cell_text = self._clean_header_text(header_cells[col_idx].get_text())
                        if any(kw in cell_text for kw in ['fair', 'value', 'market']):
                            self.column_map['fair_value'] = col_idx
                            logger.debug(f"Found fair_value column at {col_idx} by scanning")
                            break
            
            # Try to find investment_type and interest_rate by scanning if not found
            if 'investment_type' not in self.column_map:
                for idx, cell in enumerate(header_cells):
                    cell_text = self._clean_header_text(cell.get_text())
                    if any(kw in cell_text for kw in ['type', 'investment', 'security', 'class', 'instrument']):
                        if 'investment_type' not in self.column_map or idx < principal_col:
                            self.column_map['investment_type'] = idx
                            logger.debug(f"Found investment_type column at {idx} by scanning")
            
            if 'interest_rate' not in self.column_map:
                for idx, cell in enumerate(header_cells):
                    cell_text = self._clean_header_text(cell.get_text())
                    if any(kw in cell_text for kw in ['rate', 'coupon', 'interest', 'yield']):
                        if 'interest_rate' not in self.column_map:
                            self.column_map['interest_rate'] = idx
                            logger.debug(f"Found interest_rate column at {idx} by scanning")
        
        logger.info(f"Mapped {len(self.column_map)} columns: {list(self.column_map.keys())}")
        return self.column_map
    
    def _clean_header_text(self, text: str) -> str:
        """Clean header text for matching."""
        # Remove footnotes like (1), (12), etc.
        text = re.sub(r'\s*\(\d+\)\s*', ' ', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Lowercase for matching
        return text.lower().strip()
    
    def _identify_field(self, header_text: str) -> Optional[str]:
        """
        Identify which field a header corresponds to.
        
        Args:
            header_text: Cleaned header text
            
        Returns:
            Field name or None if no match
        """
        # Try each field's keywords
        for field_name, keywords in self.COLUMN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in header_text:
                    return field_name
        
        return None
    
    def get_column_index(self, field_name: str) -> Optional[int]:
        """Get the column index for a field name."""
        return self.column_map.get(field_name)
    
    def get_cell_value(self, cells: List, field_name: str) -> Optional[str]:
        """
        Get cell value for a field.
        
        Args:
            cells: List of cell elements for a row
            field_name: Field to extract
            
        Returns:
            Cell text or None
        """
        if field_name not in self.column_map:
            return None
        
        col_idx = self.column_map[field_name]
        
        if col_idx >= len(cells):
            return None
        
        cell_text = cells[col_idx].get_text(strip=True)
        
        # Special handling for financial columns: if cell only contains "$", 
        # check next cell for the actual value
        if cell_text == '$' and col_idx + 1 < len(cells):
            next_cell_text = cells[col_idx + 1].get_text(strip=True)
            # If next cell has a number, return it with $ prefix
            if next_cell_text and next_cell_text[0].isdigit():
                return f"${next_cell_text}"
        
        # If cell is empty or just whitespace, try adjacent cells for financial data
        if not cell_text or cell_text.strip() in ['', '—', '-', 'N/A']:
            if field_name in ['cost', 'fair_value', 'principal_amount']:
                # Try next cell
                if col_idx + 1 < len(cells):
                    next_text = cells[col_idx + 1].get_text(strip=True)
                    if next_text and (next_text[0].isdigit() or next_text.startswith('$')):
                        return next_text
                # Try previous cell
                if col_idx > 0:
                    prev_text = cells[col_idx - 1].get_text(strip=True)
                    if prev_text and (prev_text[0].isdigit() or prev_text.startswith('$')):
                        return prev_text
        
        return cell_text


class FlexibleTableParser:
    """Flexible parser that adapts to different BDC table formats."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        """Initialize the parser."""
        self.headers = {'User-Agent': user_agent}
        self.mapper = ColumnMapper()
        self.current_industry = "Unknown"
        self.current_company = None
        self.current_business_desc = None
    
    def parse_html_filing(self, url: str) -> List[Dict]:
        """
        Parse investment data from HTML filing.
        
        Args:
            url: URL to the HTML filing
            
        Returns:
            List of investment dictionaries
        """
        logger.info(f"Parsing HTML from: {url}")
        
        # Download HTML
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find ALL investment schedule tables (often split across multiple tables)
        investment_tables = self._find_investment_tables(soup)
        
        if not investment_tables:
            logger.warning("No investment tables found")
            return []
        
        logger.info(f"Found {len(investment_tables)} investment tables")
        
        # Parse all tables and combine
        # Reset state before parsing
        self.current_industry = "Unknown"
        self.current_company = None
        self.current_business_desc = None
        
        all_investments = []
        for table_idx, table in enumerate(investment_tables):
            investments = self._parse_table(table, is_first=(table_idx == 0))
            all_investments.extend(investments)
            logger.debug(f"Table {table_idx}: {len(investments)} investments")
        
        logger.info(f"Extracted {len(all_investments)} total investments from HTML")
        return all_investments
    
    def _find_investment_tables(self, soup: BeautifulSoup) -> List:
        """Find ALL investment schedule tables (may be split across multiple tables)."""
        
        # Investment schedule indicators
        schedule_keywords = [
            'schedule of investments',
            'consolidated schedule',
            'portfolio of investments'
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
                prev_text = ""
                for prev in table.find_all_previous(['p', 'div', 'h1', 'h2', 'h3', 'td', 'span']):
                    prev_text = prev.get_text().lower()
                    if any(kw in prev_text for kw in schedule_keywords):
                        in_schedule_section = True
                        logger.debug("Found investment schedule section")
                        break
                    if len(prev_text) > 1000:
                        break
            
            # If in schedule section, check if this table has investment data
            if in_schedule_section:
                # Check for investment table headers
                has_headers = False
                for row in rows[:5]:  # Check first 5 rows
                    row_text = row.get_text().lower()
                    header_count = sum(1 for kw in ['company', 'business description', 'investment', 
                                                     'maturity', 'acquisition', 'principal', 'cost', 'fair value']
                                      if kw in row_text)
                    if header_count >= 4:
                        has_headers = True
                        break
                
                if has_headers:
                    investment_tables.append(table)
                    logger.debug(f"Added table with {len(rows)} rows")
                
                # Stop if we've moved past the schedule (e.g., hit footnotes table)
                table_text = table.get_text().lower()
                if 'footnotes' in table_text[:200] or 'see notes' in table_text[:200]:
                    logger.debug("Reached end of investment schedule")
                    break
        
        logger.info(f"Found {len(investment_tables)} investment schedule tables")
        return investment_tables
    
    def _find_investment_table_old(self, soup: BeautifulSoup) -> Optional:
        """Find the investment schedule table."""
        
        # Table title keywords
        table_titles = [
            'schedule of investments',
            'consolidated schedule',
            'portfolio of investments',
            'investment portfolio'
        ]
        
        # Look for tables and score them
        best_table = None
        best_score = 0
        
        for table in soup.find_all('table'):
            score = 0
            rows = table.find_all('tr')
            
            # Skip small tables (investment schedules are large)
            if len(rows) < 50:
                continue
            
            score += min(len(rows) / 10, 50)  # More rows = better, up to 50 points
            
            # Check preceding text for title
            prev_text = ""
            for prev in table.find_all_previous(['p', 'div', 'h1', 'h2', 'h3', 'td']):
                prev_text = prev.get_text().lower()
                if any(title in prev_text for title in table_titles):
                    logger.debug(f"Found table with title match: {prev_text[:100]}")
                    score += 100  # Strong match
                    break
                # Don't look too far back
                if len(prev_text) > 500:
                    break
            
            # Check if it has appropriate column headers
            for row_idx, row in enumerate(rows[:10]):  # Check first 10 rows
                row_text = row.get_text().lower()
                header_keywords = ['company', 'investment', 'maturity', 'acquisition', 'principal', 'cost', 'fair value']
                keyword_matches = sum(1 for kw in header_keywords if kw in row_text)
                
                if keyword_matches >= 4:  # Found a row with many header keywords
                    score += 50
                    logger.debug(f"Found header-like row at idx {row_idx} with {keyword_matches} keywords")
                    break
            
            logger.debug(f"Table with {len(rows)} rows scored {score}")
            
            if score > best_score:
                best_score = score
                best_table = table
        
        if best_table:
            rows = best_table.find_all('tr')
            logger.info(f"Selected table with {len(rows)} rows (score: {best_score})")
        
        return best_table
    
    def _parse_table(self, table, is_first: bool = True) -> List[Dict]:
        """Parse investments from a table.
        
        Args:
            table: BeautifulSoup table element
            is_first: If True, will look for and map headers. If False, reuses existing mapping.
        """
        
        rows = table.find_all('tr')
        investments = []
        header_found = not is_first  # If not first table, skip header search
        
        # Use instance-level carry-forward state (persists across tables)
        logger.debug(f"Parsing table with {len(rows)} rows (is_first={is_first})")
        
        for row_idx, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            
            if not cells:
                continue
            
            # Debug first few rows of first table
            if is_first and row_idx < 5:
                row_text = ' | '.join([cell.get_text(strip=True)[:30] for cell in cells[:5]])
                logger.debug(f"Row {row_idx}: {len(cells)} cells - {row_text}")
            
            # Look for header row (only in first table)
            if is_first and not header_found:
                is_header = self._is_header_row(cells)
                if is_header:
                    self.mapper.map_headers(cells)
                    header_found = True
                    logger.info("Found and mapped header row")
                    continue
                elif row_idx < 10:  # Debug first 10 rows if no header found
                    row_text = ' | '.join([cell.get_text(strip=True).lower()[:20] for cell in cells[:5]])
                    logger.debug(f"Row {row_idx} not header: {row_text}")
            
            # After header is found, parse data rows
            if header_found:
                # Check if this is an industry header
                if self._is_industry_header_row(cells):
                    self.current_industry = self._extract_industry_name(cells)
                    logger.debug(f"Industry: {self.current_industry}")
                    self.current_company = None  # Reset company on industry change
                    self.current_business_desc = None
                    continue
                
                # Check if this might be a company name row (has company name but no investment type)
                company_name_raw = self.mapper.get_cell_value(cells, 'company_name')
                investment_type_raw = self.mapper.get_cell_value(cells, 'investment_type')
                business_desc_raw = self.mapper.get_cell_value(cells, 'business_description')
                
                # If we have a company name but no investment type, and it's not an investment description,
                # this is a company header row
                if company_name_raw and not investment_type_raw and not self._is_investment_description(company_name_raw):
                    # This is a company name row - update current_company
                    self.current_company = re.sub(r'\s*\(\d+\)\s*', '', company_name_raw).strip()
                    if business_desc_raw:
                        self.current_business_desc = business_desc_raw.strip()
                    continue
                
                # Check if this is a data row OR try parsing anyway if we have enough cells
                # Some tables might not pass _is_data_row but still have valid data
                is_data = self._is_data_row(cells)
                if is_data or len(cells) >= 5:  # Try parsing if we have enough cells
                    investment = self._parse_data_row(cells, self.current_company, self.current_business_desc)
                    if investment:
                        # Update carry-forward state if this row had company info (and it's not an investment description)
                        investment_company = investment.get('company_name')
                        if investment_company:
                            if not self._is_investment_description(investment_company):
                                # Valid company name - update current_company
                                self.current_company = investment_company
                            elif self._is_investment_description(investment_company) and self.current_company:
                                # Company name is actually an investment description - use current_company
                                investment['company_name'] = self.current_company
                        if investment.get('business_description'):
                            self.current_business_desc = investment['business_description']
                        
                        investment['industry'] = self.current_industry
                        investments.append(investment)
        
        return investments
    
    def _is_header_row(self, cells: List) -> bool:
        """Check if this row contains column headers."""
        
        if len(cells) < 5:  # Investment tables typically have many columns
            return False
        
        # Headers typically contain certain keywords
        row_text = ' '.join([cell.get_text().lower() for cell in cells])
        
        header_indicators = [
            'company', 'investment', 'maturity', 'principal', 'cost', 'fair value',
            'acquisition', 'type', 'portfolio'
        ]
        
        matches = sum(1 for indicator in header_indicators if indicator in row_text)
        
        logger.debug(f"Header check: {len(cells)} cells, {matches} keyword matches, text: {row_text[:100]}")
        
        # If at least 3 header keywords found, it's likely a header row
        return matches >= 3
    
    def _is_industry_header_row(self, cells: List) -> bool:
        """Check if this row is an industry/section header."""
        
        # Check first cell for industry header
        # Industry headers can be in rows with many cells (they just span multiple columns)
        if not cells:
            return False
        
        first_cell = cells[0]
        first_cell_text = first_cell.get_text(strip=True)
        
        # Empty or very short
        if not first_cell_text or len(first_cell_text) < 3:
            return False
        
        # Check if the cell or its children have bold styling
        is_bold = False
        # Check for bold tags
        if first_cell.find(['b', 'strong']):
            is_bold = True
        # Check for span with bold style
        elif first_cell.find('span'):
            span = first_cell.find('span')
            style = span.get('style', '')
            if 'bold' in style.lower() or 'font-weight' in style.lower():
                is_bold = True
        
        # Check for industry keywords
        industry_keywords = [
            'software', 'healthcare', 'technology', 'financial services',
            'commercial', 'professional services', 'insurance', 'consumer',
            'industrial', 'energy', 'materials', 'transportation', 'aerospace',
            'telecommunications', 'media', 'entertainment', 'utilities',
            'pharmaceuticals', 'biotechnology', 'food and beverage', 'retail'
        ]
        
        text_lower = first_cell_text.lower()
        
        # Must contain industry keyword and not contain company indicators
        has_industry = any(kw in text_lower for kw in industry_keywords)
        not_company = not any(indicator in text_lower for indicator in ['llc', 'inc.', 'corp', 'ltd', 'limited'])
        not_total = not text_lower.startswith('total')
        not_header = not any(kw in text_lower for kw in ['company', 'description', 'investment', 'coupon', 'maturity'])
        
        # Industry headers should be bold or very short (like "Software and Services")
        looks_like_industry = (is_bold or len(first_cell_text) < 50) and has_industry
        
        return looks_like_industry and not_company and not_total and not_header
    
    def _extract_industry_name(self, cells: List) -> str:
        """Extract industry name from header row."""
        text = cells[0].get_text(strip=True)
        # Remove trailing numbers and symbols
        text = re.sub(r'\s+[\d\$\(\)]+.*$', '', text)
        return text.strip()
    
    def _is_investment_description(self, text: str) -> bool:
        """Check if text is an investment description rather than a company name."""
        if not text:
            return False
        text_lower = text.lower()
        # Investment descriptions typically contain:
        # - Investment type keywords
        # - Par amount patterns like "$X par due"
        # - Maturity date patterns
        investment_indicators = [
            'first lien', 'second lien', 'senior secured', 'subordinated',
            'preferred', 'common', 'warrant', 'revolver', 'term loan',
            'par due', 'par value', 'due ', 'loan ($', 'note ($',
            'shares)', 'units)', 'stock (', 'equity (', 'member units',
            'limited partnership', 'class a', 'class b', 'series '
        ]
        return any(indicator in text_lower for indicator in investment_indicators)
    
    def _is_data_row(self, cells: List) -> bool:
        """Check if this row contains investment data."""
        
        # Must have enough cells
        if len(cells) < 5:
            return False
        
        first_cell_text = cells[0].get_text(strip=True)
        
        # Skip empty or totals
        if not first_cell_text:
            return False
        if first_cell_text.lower().startswith('total'):
            return False
        
        # Skip if first cell looks like a header keyword
        header_keywords = ['company', 'portfolio', 'investment', 'type', 'description', 'principal', 'cost', 'fair value']
        if any(kw in first_cell_text.lower() for kw in header_keywords) and len(first_cell_text) < 30:
            return False
        
        # Data rows typically have company name indicators or financial values
        company_indicators = ['llc', 'inc.', 'corp', 'ltd', 'holdings', 'lp', 'limited', 'company', 'corporation']
        has_company_indicator = any(ind in first_cell_text.lower() for ind in company_indicators)
        
        # Or has financial data in other cells (look for $ or large numbers)
        has_financial_data = any('$' in cell.get_text() or re.search(r'\d{1,3}(,\d{3})+', cell.get_text()) 
                                  for cell in cells[1:])
        
        # Also check if first cell has substantial text (likely a company name)
        has_substantial_text = len(first_cell_text) > 3 and not first_cell_text.isdigit()
        
        # More lenient: return True if we have substantial text OR financial data
        # (company indicators are nice but not required)
        return has_company_indicator or has_financial_data or (has_substantial_text and len(cells) >= 7)
    
    def _parse_data_row(self, cells: List, carried_company: Optional[str] = None, 
                       carried_business_desc: Optional[str] = None) -> Optional[Dict]:
        """Parse a data row into an investment dictionary.
        
        Args:
            cells: List of cell elements
            carried_company: Company name from previous row (for multi-row companies)
            carried_business_desc: Business description from previous row
            
        Returns:
            Investment dictionary or None
        """
        
        try:
            # Extract fields using column mapper
            company_name_raw = self.mapper.get_cell_value(cells, 'company_name')
            business_desc_raw = self.mapper.get_cell_value(cells, 'business_description')
            
            # Check if company_name_raw is actually an investment description
            if company_name_raw and self._is_investment_description(company_name_raw):
                # The company_name field contains an investment description, use carried_company
                company_name = carried_company
            elif company_name_raw and company_name_raw.strip():
                # Clean company name (remove footnotes)
                company_name = re.sub(r'\s*\(\d+\)\s*', '', company_name_raw).strip()
                # Double-check it's not an investment description
                if self._is_investment_description(company_name):
                    company_name = carried_company
            else:
                company_name = carried_company
            
            if business_desc_raw and business_desc_raw.strip():
                business_description = business_desc_raw.strip()
            else:
                business_description = carried_business_desc
                if not business_description and len(cells) > 1:
                    potential_desc = cells[1].get_text(strip=True)
                    if potential_desc and not self._looks_like_numeric(potential_desc) and not self._looks_like_header(potential_desc):
                        business_description = potential_desc
            
            # Must have at least a company name
            # Fallback: if mapper didn't find company_name, try first cell
            if not company_name and cells:
                first_cell_text = cells[0].get_text(strip=True)
                # Use first cell as company name if it looks like a name (not a number, not empty, not a header)
                if first_cell_text and len(first_cell_text) > 2:
                    # Check if it's not a header keyword or number
                    header_keywords = ['company', 'portfolio', 'investment', 'type', 'description', 'principal', 'cost', 'fair value', 'maturity', 'acquisition']
                    is_number = first_cell_text.replace(',', '').replace('.', '').replace('$', '').replace('(', '').replace(')', '').strip().isdigit()
                    if not any(kw in first_cell_text.lower() for kw in header_keywords) and not is_number:
                        company_name = first_cell_text.strip()
            
            if not company_name:
                return None
            
            # Extract investment type (should always be in current row)
            investment_type = self.mapper.get_cell_value(cells, 'investment_type')
            if not investment_type or not investment_type.strip():
                # Try to infer from other cells if column mapper didn't find it
                # Look for common investment type keywords in all cells
                investment_type_keywords = {
                    'senior secured': 'Senior Secured',
                    'first lien': 'First Lien',
                    'second lien': 'Second Lien',
                    'subordinated': 'Subordinated',
                    'convertible': 'Convertible',
                    'preferred': 'Preferred',
                    'common stock': 'Common Stock',
                    'warrant': 'Warrant',
                    'revolver': 'Revolver',
                    'term loan': 'Term Loan',
                    'bond': 'Bond',
                    'note': 'Note'
                }
                for cell in cells:
                    cell_text = cell.get_text(strip=True).lower()
                    for keyword, inv_type in investment_type_keywords.items():
                        if keyword in cell_text:
                            investment_type = inv_type
                            logger.debug(f"Inferred investment_type '{inv_type}' from cell: {cell_text[:50]}")
                            break
                    if investment_type and investment_type != "Unknown":
                        break
                
                if not investment_type or not investment_type.strip():
                    investment_type = "Unknown"
            
            # Extract dates - ALWAYS try mapped column first (most reliable)
            acquisition_date = self._clean_date(self.mapper.get_cell_value(cells, 'acquisition_date'))
            maturity_date = self._clean_date(self.mapper.get_cell_value(cells, 'maturity_date'))
            
            # Only scan other cells if mapped columns didn't work AND we're missing dates
            # This prevents incorrectly combining dates from wrong columns
            if not acquisition_date or not maturity_date:
                # Get column indices for date columns (if mapped)
                acq_col_idx = self.mapper.column_map.get('acquisition_date')
                mat_col_idx = self.mapper.column_map.get('maturity_date')
                
                # First, try to get dates from the mapped column indices directly (even if mapper didn't find them)
                if not acquisition_date and acq_col_idx is not None and acq_col_idx < len(cells):
                    acq_cell_text = cells[acq_col_idx].get_text(strip=True)
                    if acq_cell_text and len(acq_cell_text) <= 50:  # Reasonable length for a date
                        acquisition_date = self._clean_date(acq_cell_text)
                
                if not maturity_date and mat_col_idx is not None and mat_col_idx < len(cells):
                    mat_cell_text = cells[mat_col_idx].get_text(strip=True)
                    if mat_cell_text and len(mat_cell_text) <= 50:  # Reasonable length for a date
                        maturity_date = self._clean_date(mat_cell_text)
                
                # If still missing dates, scan nearby cells (but be conservative)
                # Only scan cells that are likely to contain dates (not too far from mapped columns)
                if not acquisition_date or not maturity_date:
                    dates_found = []
                    date_positions = []  # Track which column each date came from
                    
                    # Determine scan range: check mapped columns ± 2 cells, or first 15 cells if no mapping
                    scan_start = 0
                    scan_end = 15
                    if acq_col_idx is not None or mat_col_idx is not None:
                        # Scan around mapped date columns
                        min_col = min([c for c in [acq_col_idx, mat_col_idx] if c is not None] or [0])
                        max_col = max([c for c in [acq_col_idx, mat_col_idx] if c is not None] or [14])
                        scan_start = max(0, min_col - 2)
                        scan_end = min(len(cells), max_col + 3)
                    
                    cells_to_scan = cells[scan_start:scan_end]
                    
                    for cell_idx, cell in enumerate(cells_to_scan):
                        actual_col_idx = scan_start + cell_idx
                        cell_text = cell.get_text(strip=True)
                        # Skip if cell is too long (likely not a date)
                        if len(cell_text) > 50:
                            continue
                        # Skip if this is the mapped column we already checked
                        if actual_col_idx == acq_col_idx or actual_col_idx == mat_col_idx:
                            continue
                        
                        # Look for date patterns: MM/DD/YYYY, YYYY-MM-DD, Month DD, YYYY
                        date_patterns = [
                            r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
                            r'\d{4}-\d{1,2}-\d{1,2}',  # YYYY-MM-DD
                            r'[A-Za-z]+\s+\d{1,2},\s*\d{4}',  # Month DD, YYYY
                            r'[A-Za-z]+\s+\d{4}',  # Month YYYY
                            r'\d{1,2}/\d{4}',  # MM/YYYY
                        ]
                        for pattern in date_patterns:
                            date_match = re.search(pattern, cell_text)
                            if date_match:
                                cleaned = self._clean_date(date_match.group(0))
                                if cleaned:
                                    dates_found.append(cleaned)
                                    date_positions.append(actual_col_idx)
                                    break  # Only take first match per cell
                    
                    if dates_found:
                        # Remove duplicates while preserving order
                        seen_dates = set()
                        unique_dates = []
                        unique_positions = []
                        for i, d in enumerate(dates_found):
                            if d and d not in seen_dates:
                                seen_dates.add(d)
                                unique_dates.append(d)
                                unique_positions.append(date_positions[i])
                        
                        if unique_dates:
                            # Try to intelligently assign dates based on context and position
                            for i, (date_val, pos) in enumerate(zip(unique_dates, unique_positions)):
                                # Find the cell that contains this date
                                if pos < len(cells):
                                    cell_text = cells[pos].get_text(strip=True)
                                    cell_lower = cell_text.lower()
                                    
                                    # Check context keywords first (most reliable)
                                    if not acquisition_date and any(kw in cell_lower for kw in ['acquisition', 'origination', 'investment', 'purchase', 'initial', 'date acquired']):
                                        acquisition_date = date_val
                                        continue
                                    elif not maturity_date and any(kw in cell_lower for kw in ['maturity', 'expiration', 'due date', 'mat date', 'exp date', 'due']):
                                        maturity_date = date_val
                                        continue
                                    
                                    # If we have mapped column indices, prefer dates near those columns
                                    if not maturity_date and mat_col_idx is not None:
                                        # If this date is in or near the maturity column, use it
                                        if abs(pos - mat_col_idx) <= 1:
                                            maturity_date = date_val
                                            continue
                                    
                                    if not acquisition_date and acq_col_idx is not None:
                                        # If this date is in or near the acquisition column, use it
                                        if abs(pos - acq_col_idx) <= 1:
                                            acquisition_date = date_val
                                            continue
                            
                            # Conservative fallback: only assign if we're confident
                            # Don't assign by position alone unless we have strong indicators
                            if not acquisition_date and unique_dates and acq_col_idx is not None:
                                # If we have a mapped acquisition column but didn't find a date there,
                                # try the date closest to that column
                                closest_idx = min(range(len(unique_positions)), 
                                                 key=lambda i: abs(unique_positions[i] - acq_col_idx))
                                if abs(unique_positions[closest_idx] - acq_col_idx) <= 2:
                                    acquisition_date = unique_dates[closest_idx]
                            
                            if not maturity_date and unique_dates and mat_col_idx is not None:
                                # If we have a mapped maturity column but didn't find a date there,
                                # try the date closest to that column
                                closest_idx = min(range(len(unique_positions)), 
                                                 key=lambda i: abs(unique_positions[i] - mat_col_idx))
                                if abs(unique_positions[closest_idx] - mat_col_idx) <= 2:
                                    maturity_date = unique_dates[closest_idx]
                            
                            # Last resort: if we have exactly one date and one missing field, and the date
                            # is in a reasonable position (not in first few columns which are usually company/investment type)
                            if len(unique_dates) == 1 and unique_positions[0] >= 3:
                                if not acquisition_date and not maturity_date:
                                    # Can't tell which it is, skip it to avoid wrong assignment
                                    pass
                                elif not maturity_date:
                                    # Only maturity missing, and we have one date in a reasonable column
                                    maturity_date = unique_dates[0]
                                elif not acquisition_date:
                                    # Only acquisition missing, and we have one date in a reasonable column
                                    acquisition_date = unique_dates[0]
            
            # Extract percentage-based fields from dedicated columns
            reference_rate_raw = self.mapper.get_cell_value(cells, 'reference_rate')
            reference_rate = normalize_reference(reference_rate_raw) if reference_rate_raw else None
            spread = clean_percentage(self.mapper.get_cell_value(cells, 'spread'))
            floor_rate = clean_percentage(self.mapper.get_cell_value(cells, 'floor_rate'))
            pik_rate = clean_percentage(self.mapper.get_cell_value(cells, 'pik_rate'))
            
            # Special handling for BXSL-style tables where spread is in the cell after "SOFR +"
            # BXSL structure: Col with "SOFR +" followed by Col with spread (e.g., "5.25%")
            # First, try to find spread by scanning all cells for percentage values
            if not spread:
                # Scan all cells for percentage values that look like spreads
                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True)
                    if cell_text:
                        # Skip if it's clearly not a spread (too large, contains text, etc.)
                        if len(cell_text) > 20 or any(x in cell_text.lower() for x in ['sofr', 'prime', 'libor', 'company', 'date', '$']):
                            continue
                        # Check if it's a percentage value
                        if '%' in cell_text or re.match(r'^[+\-]?\d+\.?\d*$', cell_text):
                            spread_candidate = clean_percentage(cell_text)
                            if spread_candidate:
                                try:
                                    spread_num = float(spread_candidate.replace('%', '').strip())
                                    # Spreads are typically 0.5% to 30%
                                    if 0.5 <= spread_num <= 30:
                                        spread = spread_candidate
                                        logger.info(f"Found spread by scanning all cells: {spread} (from cell {i}: '{cell_text}')")
                                        break
                                except (ValueError, AttributeError):
                                    pass
            
            # Then try the column-based approach
            if not spread:
                # Check interest_rate column (often contains "SOFR +" in BXSL)
                interest_col_idx = self.mapper.get_column_index('interest_rate')
                if interest_col_idx is not None and interest_col_idx < len(cells):
                    interest_cell_text = cells[interest_col_idx].get_text(strip=True)
                    # If interest_rate contains "SOFR +" or similar, check next cell for spread
                    if interest_cell_text and ('SOFR' in interest_cell_text.upper() or 'PRIME' in interest_cell_text.upper() or 'LIBOR' in interest_cell_text.upper()):
                        # Check the next cell for spread
                        if interest_col_idx + 1 < len(cells):
                            next_cell_text = cells[interest_col_idx + 1].get_text(strip=True)
                            if next_cell_text:
                                # Try to parse as spread (should be a percentage like "5.25%")
                                spread_candidate = clean_percentage(next_cell_text)
                                if spread_candidate:
                                    try:
                                        spread_num = float(spread_candidate.replace('%', '').strip())
                                        # Spreads are typically 0.5% to 30%
                                        if 0.5 <= spread_num <= 30:
                                            spread = spread_candidate
                                            logger.info(f"Found spread in adjacent cell after interest_rate: {spread} (from '{next_cell_text}')")
                                    except (ValueError, AttributeError) as e:
                                        pass
                        # Also scan all cells for percentage values that could be spreads
                        # This is a fallback in case the adjacent cell approach doesn't work
                        if not spread:
                            for i, cell in enumerate(cells):
                                if i != interest_col_idx:  # Skip the interest_rate cell itself
                                    cell_text = cell.get_text(strip=True)
                                    if cell_text:
                                        # Try clean_percentage first
                                        spread_candidate = clean_percentage(cell_text)
                                        if spread_candidate:
                                            try:
                                                spread_num = float(spread_candidate.replace('%', '').strip())
                                                # Spreads are typically 0.5% to 30%
                                                if 0.5 <= spread_num <= 30:
                                                    spread = spread_candidate
                                                    logger.info(f"Found spread by scanning cells: {spread} (from cell {i}: '{cell_text}')")
                                                    break
                                            except (ValueError, AttributeError):
                                                pass
                                        # Also try direct regex match for percentage patterns
                                        elif re.match(r'^[+\-]?\d+\.?\d*\s*%$', cell_text):
                                            try:
                                                spread_num = float(cell_text.replace('%', '').replace('+', '').strip())
                                                if 0.5 <= spread_num <= 30:
                                                    spread = clean_percentage(spread_num)
                                                    logger.info(f"Found spread by regex match: {spread} (from cell {i}: '{cell_text}')")
                                                    break
                                            except (ValueError, AttributeError):
                                                pass
                
                # Also check reference_rate column if it exists
                if not spread and reference_rate_raw:
                    ref_col_idx = self.mapper.get_column_index('reference_rate')
                    if ref_col_idx is not None and ref_col_idx + 1 < len(cells):
                        next_cell_text = cells[ref_col_idx + 1].get_text(strip=True)
                        if next_cell_text:
                            spread_candidate = clean_percentage(next_cell_text)
                            if spread_candidate:
                                try:
                                    spread_num = float(spread_candidate.replace('%', '').strip())
                                    if 0.5 <= spread_num <= 30:
                                        spread = spread_candidate
                                        logger.debug(f"Found spread after reference_rate: {spread}")
                                except (ValueError, AttributeError):
                                    pass
            
            # Extract interest_rate - try mapped column first, then scan all cells
            interest_texts: List[str] = []
            mapped_interest_text = self.mapper.get_cell_value(cells, 'interest_rate')
            if mapped_interest_text:
                interest_texts.append(mapped_interest_text)
            interest_rate = self._clean_interest_rate(mapped_interest_text)
            
            # If interest_rate not found, scan all cells for rate patterns (but limit to avoid performance issues)
            if not interest_rate:
                # Limit scanning to first 15 cells to avoid performance issues
                cells_to_scan = cells[:15] if len(cells) > 15 else cells
                # Try multiple strategies to find interest rate
                for cell in cells_to_scan:
                    cell_text = cell.get_text(strip=True)
                    # Skip if cell is too long (likely not a rate)
                    if len(cell_text) > 100:
                        continue
                    # Strategy 1: Look for percentage patterns or rate keywords
                    if '%' in cell_text or any(kw in cell_text.lower() for kw in ['sofr', 'prime', 'libor', 'fixed', 'variable', 'pik', 'rate', 'coupon']):
                        cleaned_rate = self._clean_interest_rate(cell_text)
                        if cleaned_rate:
                            interest_rate = cleaned_rate
                            if cell_text not in interest_texts:
                                interest_texts.append(cell_text)
                            logger.debug(f"Found interest_rate by scanning: {cell_text[:50]}")
                            break
                
                # Strategy 2: If still not found, look for numeric patterns that might be rates
                if not interest_rate:
                    for cell in cells_to_scan:
                        cell_text = cell.get_text(strip=True)
                        # Skip if cell is too long
                        if len(cell_text) > 20:
                            continue
                        # Look for patterns like "10.5" or "10.5%" that might be rates
                        # But exclude if it looks like a date or amount
                        if re.search(r'^\d+\.?\d*\s*%?$', cell_text):
                            # Check if it's not a date (no slashes) and not too large (likely not an amount)
                            if '/' not in cell_text and not cell_text.startswith('$'):
                                try:
                                    num_val = float(cell_text.replace('%', '').strip())
                                    # If it's between 0 and 100, likely a percentage rate
                                    if 0 <= num_val <= 100:
                                        interest_rate = cell_text if '%' in cell_text else f"{cell_text}%"
                                        if cell_text not in interest_texts:
                                            interest_texts.append(cell_text)
                                        logger.debug(f"Found interest_rate as numeric: {cell_text}")
                                        break
                                except ValueError:
                                    pass
            
            if interest_texts:
                # Remove duplicates while preserving order
                seen_interest = set()
                deduped_interest = []
                for text in interest_texts:
                    if text not in seen_interest:
                        deduped_interest.append(text)
                        seen_interest.add(text)
                interest_texts = deduped_interest
            
            components = normalize_interest_fields(
                raw_texts=interest_texts,
                reference_rate=reference_rate,
                spread=spread,
                floor_rate=floor_rate,
                pik_rate=pik_rate,
                interest_rate=interest_rate,
            )
            reference_rate = components.reference_rate
            spread = components.spread
            floor_rate = components.floor_rate
            pik_rate = components.pik_rate
            interest_rate = components.summary
            
            # Extract shares_units and percent_net_assets
            shares_units = self.mapper.get_cell_value(cells, 'shares_units')
            percent_net_assets = self.mapper.get_cell_value(cells, 'percent_net_assets')
            currency = self.mapper.get_cell_value(cells, 'currency')
            commitment_limit = self.mapper.get_cell_value(cells, 'commitment_limit')
            undrawn_commitment = self.mapper.get_cell_value(cells, 'undrawn_commitment')
            
            # Clean shares_units (remove commas, keep as string since it might have units)
            if shares_units:
                shares_units = re.sub(r'[,\s]', '', shares_units).strip()
            
            # Clean percent_net_assets (extract percentage value)
            if percent_net_assets:
                # Remove % sign and clean
                percent_net_assets = re.sub(r'[%\s]', '', percent_net_assets).strip()
                # Try to convert to float for validation
                try:
                    float(percent_net_assets)
                except:
                    percent_net_assets = None
            
            # Clean currency (extract 3-letter code)
            if currency:
                currency_match = re.search(r'\b([A-Z]{3})\b', currency.upper())
                if currency_match:
                    currency = currency_match.group(1)
                else:
                    currency = None
            
            # Clean commitment fields
            if commitment_limit:
                commitment_limit = self._clean_amount(commitment_limit)
            if undrawn_commitment:
                undrawn_commitment = self._clean_amount(undrawn_commitment)
            
            # Extract new fields: geographic_location, credit_rating, payment_status
            geographic_location = self.mapper.get_cell_value(cells, 'geographic_location')
            credit_rating = self.mapper.get_cell_value(cells, 'credit_rating')
            payment_status = self.mapper.get_cell_value(cells, 'payment_status')
            
            # Fallback: Try to extract geographic_location from business_description
            if not geographic_location and business_description:
                # Look for common location patterns in business_description
                location_patterns = [
                    r'\b(United States|USA|U\.S\.|US)\b',
                    r'\b(Europe|European Union|EU)\b',
                    r'\b(Asia|Asia-Pacific|APAC)\b',
                    r'\b(Canada|Canadian)\b',
                    r'\b(Mexico|Mexican)\b',
                    r'\b(United Kingdom|UK|U\.K\.|Britain|British)\b',
                    r'\b(China|Chinese)\b',
                    r'\b(Japan|Japanese)\b',
                    r'\b(Germany|German)\b',
                    r'\b(France|French)\b',
                    r'\b(California|Texas|New York|Florida|Illinois)\b',  # Common US states
                ]
                for pattern in location_patterns:
                    match = re.search(pattern, business_description, re.IGNORECASE)
                    if match:
                        geographic_location = match.group(1)
                        break
            
            # Clean geographic_location
            if geographic_location:
                geographic_location = geographic_location.strip()
                # Remove common prefixes/suffixes
                geographic_location = re.sub(r'^(location|geography|region|country|state)[:\s]+', '', geographic_location, flags=re.IGNORECASE).strip()
                # Standardize common variations
                location_upper = geographic_location.upper()
                if location_upper in ['USA', 'U.S.', 'U.S.A.', 'UNITED STATES']:
                    geographic_location = 'United States'
                elif location_upper in ['UK', 'U.K.', 'UNITED KINGDOM', 'BRITAIN']:
                    geographic_location = 'United Kingdom'
                elif location_upper in ['EU', 'EUROPEAN UNION']:
                    geographic_location = 'Europe'
            
            # Clean credit_rating (standardize format)
            if credit_rating:
                credit_rating = credit_rating.strip().upper()
                # Remove rating agency prefixes if present
                credit_rating = re.sub(r'^(S&P|MOODY\'?S?|FITCH)[\s:]+', '', credit_rating, flags=re.IGNORECASE).strip()
                # Standardize "NR" or "Not Rated"
                if credit_rating in ['NR', 'NOT RATED', 'N/A', 'NONE']:
                    credit_rating = 'NR'
            
            # Clean payment_status (standardize values)
            if payment_status:
                payment_status = payment_status.strip()
                payment_lower = payment_status.lower()
                # Standardize common variations
                if any(kw in payment_lower for kw in ['non-accrual', 'non accrual', 'nonperforming', 'non performing']):
                    payment_status = 'Non-Accrual'
                elif any(kw in payment_lower for kw in ['performing', 'current', 'accruing']):
                    payment_status = 'Performing'
                elif 'default' in payment_lower:
                    payment_status = 'Default'
                elif 'restructured' in payment_lower:
                    payment_status = 'Restructured'
            
            # Extract other fields
            investment = {
                'company_name': company_name,
                'business_description': business_description,
                'investment_type': investment_type.strip(),
                'acquisition_date': acquisition_date,
                'maturity_date': maturity_date,
                'principal_amount': self._clean_amount(self.mapper.get_cell_value(cells, 'principal_amount')),
                'cost': self._clean_amount(self.mapper.get_cell_value(cells, 'cost')),
                'fair_value': self._clean_amount(self.mapper.get_cell_value(cells, 'fair_value')),
                'interest_rate': interest_rate,
                'reference_rate': reference_rate,
                'spread': spread,
                'floor_rate': floor_rate if floor_rate else None,
                'pik_rate': pik_rate if pik_rate else None,
                'shares_units': shares_units if shares_units else None,
                'percent_net_assets': percent_net_assets if percent_net_assets else None,
                'currency': currency,
                'commitment_limit': commitment_limit,
                'undrawn_commitment': undrawn_commitment,
                'geographic_location': geographic_location if geographic_location else None,
                'credit_rating': credit_rating if credit_rating else None,
                'payment_status': payment_status if payment_status else None,
            }
            
            # Only return if we have essential data
            # Be more lenient: if we have company_name and enough cells, return it
            # (financial data is nice but not always present in every row)
            has_financial_data = investment.get('cost') or investment.get('fair_value') or investment.get('principal_amount')
            
            # Return if we have company_name and either:
            # 1. Financial data, OR
            # 2. Investment type (even if Unknown), OR  
            # 3. Just company_name if we have enough cells (might be continuation row)
            if company_name:
                if has_financial_data:
                    return investment
                elif investment_type and investment_type != "Unknown":
                    return investment
                elif len(cells) >= 7:  # Enough cells suggests it's a data row
                    return investment
            
            # Log why we're skipping this row for debugging
            logger.debug(f"Skipping row: company={company_name}, has_financial={has_financial_data}, inv_type={investment_type}, cells={len(cells)}")
            return None
            
        except Exception as e:
            logger.warning(f"Failed to parse row: {e}")
            return None
    
    def _looks_like_numeric(self, text: str) -> bool:
        """Determine if text is primarily numeric (e.g., amounts or percentages)."""
        if not text:
            return False
        cleaned = text.replace(',', '').replace('$', '').replace('—', '').strip()
        if cleaned in ['', '-', 'N/A', '—']:
            return False
        return bool(re.match(r'^-?\d+(\.\d+)?%?$', cleaned))
    
    def _looks_like_header(self, text: str) -> bool:
        """Determine if text looks like a header keyword."""
        if not text:
            return False
        lowered = text.lower()
        header_keywords = [
            'company', 'portfolio', 'investment', 'type', 'description',
            'principal', 'cost', 'fair value', 'maturity', 'acquisition',
            'schedule', 'subtotal', 'total'
        ]
        return any(keyword in lowered for keyword in header_keywords)
    
    def _clean_date(self, date_str: Optional[str]) -> Optional[str]:
        """Clean and validate date string."""
        if not date_str:
            return None
        
        date_text = date_str.strip()
        
        if date_text in ['—', '-', '', 'N/A', 'N/A—', '—N/A']:
            return None
        
        # Normalize unicode dashes and ordinal indicators
        date_text = date_text.replace('–', '-').replace('—', '-')
        date_text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_text, flags=re.IGNORECASE)
        date_text = re.sub(r'\s+', ' ', date_text).strip()
        
        # Attempt to parse using common formats
        formats = [
            ('%m/%d/%Y', False),
            ('%m/%d/%y', False),
            ('%Y-%m-%d', False),
            ('%Y/%m/%d', False),
            ('%b %d, %Y', False),
            ('%B %d, %Y', False),
            ('%b %Y', True),
            ('%B %Y', True),
            ('%m/%Y', True),
        ]
        
        for fmt, assume_first_day in formats:
            try:
                parsed = datetime.strptime(date_text, fmt)
                if assume_first_day:
                    parsed = parsed.replace(day=1)
                return parsed.strftime('%m/%d/%Y')
            except ValueError:
                continue
        
        # Detect ISO-like dates without delimiters (e.g., 20240131)
        if re.match(r'^\d{8}$', date_text):
            try:
                parsed = datetime.strptime(date_text, '%Y%m%d')
                return parsed.strftime('%m/%d/%Y')
            except ValueError:
                pass
        
        # Detect partial formats like "March 15 2025"
        try:
            parsed = datetime.strptime(date_text, '%B %d %Y')
            return parsed.strftime('%m/%d/%Y')
        except ValueError:
            pass
        
        return date_text
    
    def _clean_interest_rate(self, rate_str: Optional[str]) -> Optional[str]:
        """Clean and validate interest rate string."""
        if not rate_str:
            return None
        
        rate_str = rate_str.strip()
        
        if rate_str in ['—', '-', '', 'N/A', 'N/A—', '—N/A']:
            return None
        
        # Remove extra whitespace and normalize
        rate_str = ' '.join(rate_str.split())
        
        # If it contains a percentage or rate keywords, return it
        if '%' in rate_str or any(kw in rate_str.lower() for kw in ['sofr', 'prime', 'libor', 'fixed', 'variable', 'pik', 'rate', 'coupon']):
            # Clean up common patterns
            # Remove extra spaces around operators
            rate_str = re.sub(r'\s*\+\s*', ' + ', rate_str)
            rate_str = re.sub(r'\s*/\s*', ' / ', rate_str)
            return rate_str
        
        # If it's just a number, assume it's a percentage
        if re.match(r'^\d+\.?\d*\s*%?$', rate_str):
            return rate_str if '%' in rate_str else f"{rate_str}%"
        
        # Check if it looks like a rate (has digits and might be a percentage)
        if re.search(r'\d+\.?\d*', rate_str):
            # If it has rate-like structure, return it
            return rate_str
        
        return rate_str
    
    def _clean_amount(self, amount_str: Optional[str]) -> Optional[float]:
        """Clean and parse monetary amount."""
        if not amount_str:
            return None
        
        # Remove $ and commas
        amount_str = amount_str.replace('$', '').replace(',', '').strip()
        
        if amount_str in ['—', '-', '', 'N/A']:
            return None
        
        try:
            return float(amount_str)
        except (ValueError, TypeError):
            return None


def main():
    """Test the flexible parser."""
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    parser = FlexibleTableParser()
    
    # Test with ARES Capital Corp
    url = "https://www.sec.gov/Archives/edgar/data/1287750/000128775025000046/arcc-20250930.htm"
    company_name = "Ares Capital Corporation"
    
    try:
        investments = parser.parse_html_filing(url)
        
        print(f"\n[SUCCESS] Parsed {len(investments)} investments from HTML table")
        
        # Show sample
        print(f"\n[SAMPLE] Sample Investments:")
        for i, inv in enumerate(investments[:5]):
            print(f"\n{i+1}. {inv['company_name']}")
            print(f"   Industry: {inv.get('industry', 'Unknown')}")
            print(f"   Type: {inv.get('investment_type', 'N/A')}")
            print(f"   Acquisition: {inv.get('acquisition_date', 'N/A')}")
            print(f"   Maturity: {inv.get('maturity_date', 'N/A')}")
            if inv.get('fair_value'):
                print(f"   Fair Value: ${inv['fair_value']:,.0f}")
        
        # Data quality
        total = len(investments)
        if total > 0:
            with_industry = sum(1 for inv in investments if inv.get('industry') != 'Unknown')
            with_type = sum(1 for inv in investments if inv.get('investment_type'))
            with_dates = sum(1 for inv in investments if inv.get('acquisition_date'))
            with_business_desc = sum(1 for inv in investments if inv.get('business_description'))
            
            print(f"\n[QUALITY] Data Quality:")
            print(f"   Industries: {with_industry}/{total} ({100*with_industry/total:.1f}%)")
            print(f"   Investment Types: {with_type}/{total} ({100*with_type/total:.1f}%)")
            print(f"   Dates: {with_dates}/{total} ({100*with_dates/total:.1f}%)")
            print(f"   Business Descriptions: {with_business_desc}/{total} ({100*with_business_desc/total:.1f}%)")
            
            # Save to CSV
            import csv
            import os
            
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{company_name.replace(' ', '_')}_html_investments.csv")
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'company_name', 'industry', 'business_description', 'investment_type',
                    'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                    'interest_rate', 'reference_rate', 'spread'
                ])
                writer.writeheader()
                writer.writerows(investments)
            
            print(f"\n[SAVED] Results saved to: {output_file}")
        else:
            print(f"\n[WARNING] No investments extracted")
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


