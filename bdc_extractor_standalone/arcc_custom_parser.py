#!/usr/bin/env python3
"""
ARCC (Ares Capital Corporation) Custom Investment Extractor
Parses investment data from HTML tables extracted from SEC filings.
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
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class ARCCCustomExtractor:
    """Custom extractor for ARCC that parses HTML tables from SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "ARCC"), year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from SEC filing HTML tables."""
        logger.info(f"Extracting investments for {ticker}")
        
        # Get CIK
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        logger.info(f"Found CIK: {cik}")
        
        # Get latest 10-Q filing URL
        filing_index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not filing_index_url:
            # Try 10-K as fallback
            filing_index_url = self.sec_client.get_filing_index_url(ticker, "10-K", cik=cik, year=year, min_date=min_date)
            if not filing_index_url:
                raise ValueError(f"Could not find 10-Q or 10-K filing for {ticker}")
        
        logger.info(f"Found filing index: {filing_index_url}")
        
        # Get documents from index
        documents = self.sec_client.get_documents_from_index(filing_index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith(".htm") and 'index' not in d.filename.lower()), None)
        if not main_html:
            raise ValueError(f"No main HTML document found for {ticker}")
        
        logger.info(f"Found main HTML: {main_html.url}")
        
        # Download and parse HTML
        response = requests.get(main_html.url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find investment schedule tables only
        tables = self._find_investment_tables(soup)
        logger.info(f"Found {len(tables)} investment schedule tables in HTML")
        
        # Parse investment tables
        all_investments = []
        for idx, table in enumerate(tables):
            logger.info(f"Parsing investment table {idx + 1}...")
            investments = self._parse_html_table(table)
            all_investments.extend(investments)
            logger.info(f"Extracted {len(investments)} investments from table {idx + 1}")
        
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
        output_file = os.path.join(output_dir, 'ARCC_Ares_Capital_Corporation_investments.csv')
        
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
            'company_name': 'Ares Capital Corporation',
            'cik': cik,
            'total_investments': len(all_investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _find_investment_tables(self, soup: BeautifulSoup) -> List:
        """Find investment schedule tables, filtering out financial statements."""
        schedule_keywords = [
            'schedule of investments',
            'consolidated schedule of investments',
            'portfolio of investments',
            'schedule of portfolio investments'
        ]
        
        financial_statement_keywords = [
            'consolidated statements of assets and liabilities',
            'consolidated statements of operations',
            'consolidated statements of cash flows',
            'consolidated statements of changes in net assets',
            'assets and liabilities',
            'statements of operations',
            'cash flows',
            'changes in net assets'
        ]
        
        investment_column_keywords = [
            'company', 'issuer', 'portfolio company',
            'investment', 'type of investment',
            'maturity', 'maturity date',
            'principal', 'par amount',
            'cost', 'amortized cost',
            'fair value',
            'interest rate', 'coupon', 'spread'
        ]
        
        investment_tables = []
        
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            
            # Skip tiny tables
            if len(rows) < 10:
                continue
            
            # Check context before table
            context_text = ""
            for prev in table.find_all_previous(['p', 'div', 'h1', 'h2', 'h3', 'td', 'span', 'th']):
                text = prev.get_text().lower()
                context_text += " " + text
                if len(context_text) > 2000:
                    break
            
            # Skip if it's a financial statement
            if any(kw in context_text for kw in financial_statement_keywords):
                continue
            
            # Check if context mentions schedule of investments
            has_schedule_context = any(kw in context_text for kw in schedule_keywords)
            
            # Check table headers for investment columns
            header_text = ""
            for row in rows[:3]:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    header_text += " " + cell.get_text(' ', strip=True).lower()
            
            has_investment_columns = sum(1 for kw in investment_column_keywords if kw in header_text) >= 3
            
            # Include if has schedule context OR has investment columns (and not a financial statement)
            if has_schedule_context or (has_investment_columns and len(rows) >= 10):
                investment_tables.append(table)
        
        return investment_tables
    
    def _parse_html_table(self, table) -> List[Dict]:
        """Parse a single HTML table element."""
        if not table:
            return []
        
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
        
        # If no header found, use default column positions based on ARCC structure
        if not column_map:
            column_map = {
                'company': 0,
                'business_description': 2,
                'investment_type': 4,
                'coupon': 6,
                'reference_rate': 8,
                'spread': 10,
                'acquisition_date': 12,
                'maturity_date': 14,
                'shares_units': 16,
                'principal': 18,
                'cost': 20,
                'fair_value': 22,
                'percent_net_assets': 24
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
            
            # Check if this is a total row (should be skipped)
            if self._is_total_row(cell_texts):
                continue
            
            # Check if this is an industry header row
            if self._is_industry_header(cell_texts, column_map):
                industry_col = column_map.get('company', 0)
                if len(cell_texts) > industry_col:
                    industry_text = cell_texts[industry_col].strip()
                    if industry_text and not industry_text.startswith('Total'):
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
                          'Reference', 'Spread', 'Acquisition Date', 'Maturity Date',
                          'Shares/Units', 'Principal', 'Amortized Cost', 'Fair Value']
        
        text_combined = ' '.join(cell_texts).lower()
        matches = sum(1 for keyword in header_keywords if keyword.lower() in text_combined)
        return matches >= 5  # Need at least 5 header keywords
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a total row."""
        text_combined = ' '.join(cell_texts).lower()
        return 'total' in text_combined and ('investments' in text_combined or 'assets' in text_combined)
    
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
            elif 'acquisition' in cell_lower and 'date' in cell_lower:
                column_map['acquisition_date'] = idx
            elif 'maturity' in cell_lower and 'date' in cell_lower:
                column_map['maturity_date'] = idx
            elif 'shares' in cell_lower or 'units' in cell_lower:
                column_map['shares_units'] = idx
            elif 'principal' in cell_lower:
                column_map['principal'] = idx
            elif 'amortized' in cell_lower and 'cost' in cell_lower:
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
            'percent_net_assets': None,
            'currency': 'USD',
            'commitment_limit': None,
            'undrawn_commitment': None,
        }
        
        # Get company name (may be in this row or carried from previous)
        company_col = column_map.get('company', 0)
        if len(cell_texts) > company_col:
            company_text = cell_texts[company_col].strip()
            if company_text and company_text != 'Unknown':
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
        
        # Get coupon/interest rate
        coupon_col = column_map.get('coupon', 6)
        if len(cells) > coupon_col:
            coupon_cell = cells[coupon_col]
            coupon_text = self._extract_cell_text(coupon_cell)
            # Extract percentage value
            coupon_match = re.search(r'(\d+\.?\d*)\s*%', coupon_text)
            if coupon_match:
                investment['interest_rate'] = f"{coupon_match.group(1)}%"
            
            # Check for PIK rate
            pik_match = re.search(r'(\d+\.?\d*)\s*%\s*PIK', coupon_text, re.IGNORECASE)
            if pik_match:
                investment['pik_rate'] = f"{pik_match.group(1)}%"
            
            # Check for combined rate with PIK
            combined_match = re.search(r'(\d+\.?\d*)\s*%\s*\([^)]*(\d+\.?\d*)\s*%\s*PIK[^)]*\)', coupon_text, re.IGNORECASE)
            if combined_match:
                investment['interest_rate'] = f"{combined_match.group(1)}%"
                investment['pik_rate'] = f"{combined_match.group(2)}%"
        
        # Get reference rate
        ref_col = column_map.get('reference_rate', 8)
        if len(cell_texts) > ref_col:
            ref_text = cell_texts[ref_col].strip()
            if ref_text:
                investment['reference_rate'] = standardize_reference_rate(ref_text)
        
        # Get spread
        spread_col = column_map.get('spread', 10)
        if len(cells) > spread_col:
            spread_cell = cells[spread_col]
            spread_text = self._extract_cell_text(spread_cell)
            spread_match = re.search(r'(\d+\.?\d*)\s*%', spread_text)
            if spread_match:
                investment['spread'] = f"{spread_match.group(1)}%"
        
        # Get acquisition date
        acq_col = column_map.get('acquisition_date', 12)
        if len(cell_texts) > acq_col:
            acq_text = cell_texts[acq_col].strip()
            if acq_text:
                investment['acquisition_date'] = acq_text
        
        # Get maturity date
        mat_col = column_map.get('maturity_date', 14)
        if len(cell_texts) > mat_col:
            mat_text = cell_texts[mat_col].strip()
            if mat_text:
                investment['maturity_date'] = mat_text
        
        # Get principal amount (from XBRL tag)
        principal_col = column_map.get('principal', 18)
        if len(cells) > principal_col:
            principal_cell = cells[principal_col]
            principal_value = self._extract_numeric_value(principal_cell, 'us-gaap:InvestmentOwnedBalancePrincipalAmount')
            if principal_value is not None:
                # Scale 6 means the value is already in millions, so multiply by 1M
                investment['principal_amount'] = int(principal_value * 1000000)
        
        # Get cost (from XBRL tag) - look in the cost column
        cost_col = column_map.get('cost', 20)
        if len(cells) > cost_col:
            cost_cell = cells[cost_col]
            # Try multiple XBRL concepts for cost
            cost_value = self._extract_numeric_value(cost_cell, 'us-gaap:InvestmentOwnedAtCost')
            if cost_value is not None:
                investment['cost'] = int(cost_value * 1000000)
            else:
                # Also check if there's a total row that might have cost
                # Look for any numeric value in the cost column
                cost_text = self._extract_cell_text(cost_cell)
                cost_match = re.search(r'(\d+\.?\d*)', cost_text.replace(',', ''))
                if cost_match:
                    try:
                        cost_val = float(cost_match.group(1))
                        investment['cost'] = int(cost_val * 1000000)
                    except ValueError:
                        pass
        
        # Get fair value (from XBRL tag)
        fv_col = column_map.get('fair_value', 22)
        if len(cells) > fv_col:
            fv_cell = cells[fv_col]
            fv_value = self._extract_numeric_value(fv_cell, 'us-gaap:InvestmentOwnedAtFairValue')
            if fv_value is not None:
                investment['fair_value'] = int(fv_value * 1000000)
            else:
                # Also check if there's a numeric value in the fair value column
                fv_text = self._extract_cell_text(fv_cell)
                fv_match = re.search(r'(\d+\.?\d*)', fv_text.replace(',', ''))
                if fv_match:
                    try:
                        fv_val = float(fv_match.group(1))
                        investment['fair_value'] = int(fv_val * 1000000)
                    except ValueError:
                        pass
        
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
        
        # Skip if no meaningful data (must have at least one financial value or valid investment type)
        has_financial_data = (investment.get('principal_amount') or 
                             investment.get('cost') or 
                             investment.get('fair_value'))
        has_valid_investment = (investment.get('investment_type') and 
                               investment.get('investment_type') != 'Unknown')
        
        # Skip rows that look like headers, totals, or non-investment items
        company_name = investment.get('company_name', '').lower()
        skip_patterns = [
            'total', 'subtotal', 'cash and cash equivalents', 'restricted cash',
            'interest receivable', 'receivable', 'payable', 'liabilities',
            'assets', 'other assets', 'due from', 'due to', 'collateral',
            'title of', 'trading symbol', 'exchange', 'registered'
        ]
        if any(pattern in company_name for pattern in skip_patterns):
            return None
        
        if not has_financial_data and not has_valid_investment:
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
                # Remove any non-numeric characters except decimal point and minus
                value_text = re.sub(r'[^\d\.\-]', '', value_text)
                
                # Handle special cases like "—" (em dash)
                if value_text == '' or value_text == '—' or value_text == '-':
                    return None
                
                try:
                    value = float(value_text)
                    # Check scale attribute
                    scale_attr = tag.get('scale', '0')
                    try:
                        scale = int(scale_attr)
                        # Scale is already applied in the value, but we need to handle it
                        # For scale=-5, the value is already in the correct units
                        # For scale=6, it's in millions, so we multiply by 1M
                        # But looking at the HTML, scale=-5 means the value is already correct
                        # Actually, scale=-5 with decimals=-5 means the value is in the base unit
                        # Let's just return the value as-is and handle scaling in the caller
                        return value
                    except (ValueError, TypeError):
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

