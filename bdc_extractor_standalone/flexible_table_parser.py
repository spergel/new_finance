#!/usr/bin/env python3
"""
Flexible HTML Table Parser for BDC Investment Schedules

Automatically detects column headers and extracts data based on keywords,
adapting to different BDC table formats.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
import requests

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
            'type of investment', 'investment type', 'investment', 'type'
        ],
        'acquisition_date': [
            'acquisition date', 'acquisition', 'date acquired', 'orig date', 'origination'
        ],
        'maturity_date': [
            'maturity date', 'maturity', 'mat date', 'expiration'
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
            'interest rate', 'coupon', 'rate', 'current rate'
        ],
        'reference_rate': [
            'reference rate', 'reference', 'index', 'base rate', 'benchmark'
        ],
        'spread': [
            'spread', 'margin'
        ],
        'shares_units': [
            'shares/units', 'shares', 'units', 'quantity'
        ],
        'percent_net_assets': [
            '% of net assets', 'percent of net assets', '%', 'net assets'
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
        
        # Special handling for ARCC format: Cost and Fair Value have offsets from Principal column
        if principal_col is not None and 'cost' in self.column_map and 'fair_value' in self.column_map:
            # Cost is typically at Principal + 3
            self.column_map['cost'] = principal_col + 3
            # Fair Value is typically at Principal + 6
            self.column_map['fair_value'] = principal_col + 6
            logger.debug(f"Applied financial column offsets: cost={principal_col + 3}, fair_value={principal_col + 6}")
        
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
        
        return cell_text


class FlexibleTableParser:
    """Flexible parser that adapts to different BDC table formats."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        """Initialize the parser."""
        self.headers = {'User-Agent': user_agent}
        self.mapper = ColumnMapper()
        self.current_industry = "Unknown"
    
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
                
                # Check if this is a data row
                if self._is_data_row(cells):
                    investment = self._parse_data_row(cells, self.current_company, self.current_business_desc)
                    if investment:
                        # Update carry-forward state if this row had company info
                        if investment.get('company_name'):
                            self.current_company = investment['company_name']
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
        
        # Data rows typically have company name indicators or financial values
        company_indicators = ['llc', 'inc.', 'corp', 'ltd', 'holdings', 'lp', 'limited']
        has_company_indicator = any(ind in first_cell_text.lower() for ind in company_indicators)
        
        # Or has financial data in other cells
        has_financial_data = any('$' in cell.get_text() or re.search(r'\d{1,3}(,\d{3})+', cell.get_text()) 
                                  for cell in cells[1:])
        
        return has_company_indicator or has_financial_data
    
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
            
            # Use carried-forward values if current cells are empty
            if company_name_raw and company_name_raw.strip():
                # Clean company name (remove footnotes)
                company_name = re.sub(r'\s*\(\d+\)\s*', '', company_name_raw).strip()
            else:
                company_name = carried_company
            
            if business_desc_raw and business_desc_raw.strip():
                business_description = business_desc_raw.strip()
            else:
                business_description = carried_business_desc
            
            # Must have at least a company name
            if not company_name:
                return None
            
            # Extract investment type (should always be in current row)
            investment_type = self.mapper.get_cell_value(cells, 'investment_type')
            if not investment_type or not investment_type.strip():
                # Skip rows with no investment type (likely subtotal rows)
                return None
            
            # Extract other fields
            investment = {
                'company_name': company_name,
                'business_description': business_description,
                'investment_type': investment_type.strip(),
                'acquisition_date': self._clean_date(self.mapper.get_cell_value(cells, 'acquisition_date')),
                'maturity_date': self._clean_date(self.mapper.get_cell_value(cells, 'maturity_date')),
                'principal_amount': self._clean_amount(self.mapper.get_cell_value(cells, 'principal_amount')),
                'cost': self._clean_amount(self.mapper.get_cell_value(cells, 'cost')),
                'fair_value': self._clean_amount(self.mapper.get_cell_value(cells, 'fair_value')),
                'interest_rate': self.mapper.get_cell_value(cells, 'interest_rate'),
                'reference_rate': self.mapper.get_cell_value(cells, 'reference_rate'),
                'spread': self.mapper.get_cell_value(cells, 'spread'),
            }
            
            # Only return if we have essential data (company + at least one financial value)
            if company_name and (investment.get('cost') or investment.get('fair_value') or investment.get('principal_amount')):
                return investment
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to parse row: {e}")
            return None
    
    def _clean_date(self, date_str: Optional[str]) -> Optional[str]:
        """Clean and validate date string."""
        if not date_str:
            return None
        
        # Remove dashes and whitespace
        date_str = date_str.strip()
        
        if date_str in ['—', '-', '', 'N/A']:
            return None
        
        return date_str
    
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
            
            output_dir = "output"
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

