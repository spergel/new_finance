#!/usr/bin/env python3
"""
RAND (Rand Capital Corp) Custom Investment Extractor
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


class RANDCustomExtractor:
    """Custom extractor for RAND that parses HTML tables from SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "RAND", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
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
        
        # Deduplicate
        unique_investments = self._deduplicate_investments(all_investments)
        logger.info(f"Total investments after deduplication: {len(unique_investments)}")
        
        # Calculate totals
        total_principal = sum(inv.get('principal_amount', 0) or 0 for inv in unique_investments)
        total_cost = sum(inv.get('cost', 0) or 0 for inv in unique_investments)
        total_fair_value = sum(inv.get('fair_value', 0) or 0 for inv in unique_investments)
        
        # Industry and type breakdown
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        for inv in unique_investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'RAND_Rand_Capital_Corp_investments.csv')
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate',
                'shares_units', 'percent_net_assets', 'currency', 'commitment_limit', 'undrawn_commitment'
            ])
            writer.writeheader()
            for inv in unique_investments:
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
        
        logger.info(f"Saved {len(unique_investments)} investments to {output_file}")
        
        return {
            'company_name': 'Rand Capital Corp',
            'cik': cik,
            'total_investments': len(unique_investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _find_investment_tables(self, soup: BeautifulSoup) -> List:
        """Find investment schedule tables, filtering out financial statements."""
        schedule_keywords = [
            'schedule of investments', 'consolidated schedule of investments',
            'portfolio of investments', 'schedule of portfolio investments'
        ]
        financial_statement_keywords = [
            'consolidated statements of assets and liabilities', 'consolidated statements of operations',
            'consolidated statements of cash flows', 'consolidated statements of changes in net assets',
            'assets and liabilities', 'statements of operations', 'cash flows', 'changes in net assets'
        ]
        investment_column_keywords = [
            'company', 'issuer', 'portfolio company', 'investment', 'type of investment',
            'maturity', 'maturity date', 'principal', 'par amount', 'cost', 'amortized cost',
            'fair value', 'interest rate', 'coupon', 'spread'
        ]
        investment_tables = []
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            if len(rows) < 10:
                continue
            context_text = ""
            for prev in table.find_all_previous(['p', 'div', 'h1', 'h2', 'h3', 'td', 'span', 'th']):
                text = prev.get_text().lower()
                context_text += " " + text
                if len(context_text) > 2000:
                    break
            if any(kw in context_text for kw in financial_statement_keywords):
                continue
            has_schedule_context = any(kw in context_text for kw in schedule_keywords)
            header_text = ""
            for row in rows[:3]:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    header_text += " " + cell.get_text(' ', strip=True).lower()
            has_investment_columns = sum(1 for kw in investment_column_keywords if kw in header_text) >= 3
            if has_schedule_context or (has_investment_columns and len(rows) >= 10):
                investment_tables.append(table)
        return investment_tables
    
    def _parse_html_table(self, table) -> List[Dict]:
        """Parse a single HTML table and extract investments."""
        investments = []
        rows = table.find_all('tr')
        if len(rows) < 2:
            return investments
        
        # Map columns from header row
        header_row = rows[0]
        header_cells = header_row.find_all(['th', 'td'])
        column_map = self._map_columns([self._extract_cell_text(cell) for cell in header_cells])
        
        # Track current company/industry across rows
        current_company = None
        current_industry = 'Unknown'
        current_business_desc = None
        
        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                continue
            
            cell_texts = [self._extract_cell_text(cell) for cell in cells]
            
            # Skip empty rows
            if not any(cell_texts):
                continue
            
            # Skip header/total rows
            if self._is_header_row(cell_texts) or self._is_total_row(cell_texts):
                continue
            
            # Check for industry header
            if self._is_industry_header(cell_texts, column_map):
                industry_col = column_map.get('industry', 1)
                if len(cell_texts) > industry_col:
                    industry_text = cell_texts[industry_col].strip()
                    if industry_text:
                        current_industry = standardize_industry(industry_text)
                continue
            
            # Check if this is a continuation row (URL, location only, incomplete sentence)
            company_col = column_map.get('company', 0)
            first_cell = cell_texts[company_col].strip() if len(cell_texts) > company_col else ""
            
            # Check if first cell is a continuation (URL, location, or incomplete text)
            # A continuation row typically:
            # - Starts with www. or http
            # - Is just a location (City, State)
            # - Is all lowercase descriptive text (no company entity suffix)
            # - Starts with parentheses
            # - Is a short phrase without company entity indicators
            has_company_entity = bool(re.search(r'\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.)\b', first_cell, re.I))
            is_continuation = (
                first_cell.lower().startswith('www.') or
                first_cell.lower().startswith('http') or
                (first_cell and first_cell.startswith('(') and first_cell.endswith(')')) or
                # Location pattern: "City, State" or "City, ST"
                (first_cell and ',' in first_cell and len(first_cell.split(',')) == 2 and 
                 (any(word in first_cell.lower() for word in ['ma', 'ny', 'ca', 'tx', 'fl', 'ga', 'az', 'ut', 'pa', 'nj', 'me', 'mi', 'md', 'tn', 'nc', 'sc', 'va', 'wa', 'or', 'co', 'il', 'oh', 'in', 'ky']) or
                  re.match(r'^[A-Z][a-z]+,\s*[A-Z]{2}$', first_cell))) or
                # All lowercase descriptive text (no company entity)
                (first_cell and not has_company_entity and 
                 (not first_cell[0].isupper() or 
                  (len(first_cell.split()) > 2 and all(word.islower() or word[0].islower() for word in first_cell.split()[:3])))) or
                # Short phrase without entity (3 words or less, no entity suffix)
                (first_cell and len(first_cell.split()) <= 3 and not has_company_entity and not first_cell[0].isupper())
            )
            
            # If continuation row, use current company
            if is_continuation and current_company:
                # This is a continuation - parse with current company
                investment = self._parse_investment_row(cells, cell_texts, column_map, current_company, current_industry, current_business_desc)
                if investment:
                    investments.append(investment)
                continue
            
            # Extract company name and business description from first cell
            if first_cell and not is_continuation:
                extracted = self._extract_company_name_and_business_desc(first_cell)
                if extracted.get('company_name'):
                    current_company = extracted['company_name']
                if extracted.get('business_description'):
                    current_business_desc = extracted['business_description']
                # Extract industry from company text if present
                industry_match = re.search(r'\(([^)]+(?:Goods|Services|Products|Technology|Manufacturing|Distribution|Software|Industry|Automotive|Consumer))\)', first_cell, re.IGNORECASE)
                if industry_match:
                    current_industry = standardize_industry(industry_match.group(1).strip())
            
            # Parse investment row
            investment = self._parse_investment_row(cells, cell_texts, column_map, current_company, current_industry, current_business_desc)
            if investment:
                investments.append(investment)
                # Update current company if we found one
                if investment.get('company_name') and investment['company_name'] != 'Unknown':
                    current_company = investment['company_name']
                if investment.get('business_description'):
                    current_business_desc = investment['business_description']
        
        return investments
    
    def _map_columns(self, header_cells: List[str]) -> Dict[str, int]:
        """Map column headers to field names."""
        column_map = {}
        for idx, cell_text in enumerate(header_cells):
            cell_lower = cell_text.lower()
            if 'company' in cell_lower or 'issuer' in cell_lower or 'portfolio company' in cell_lower:
                column_map['company'] = idx
            elif 'industry' in cell_lower:
                column_map['industry'] = idx
            elif 'business' in cell_lower or 'description' in cell_lower:
                column_map['business_description'] = idx
            elif 'investment' in cell_lower and 'type' in cell_lower:
                column_map['investment_type'] = idx
            elif 'acquisition' in cell_lower and 'date' in cell_lower:
                column_map['acquisition_date'] = idx
            elif 'maturity' in cell_lower and 'date' in cell_lower:
                column_map['maturity_date'] = idx
            elif 'principal' in cell_lower or 'par amount' in cell_lower:
                column_map['principal'] = idx
            elif 'cost' in cell_lower or 'amortized cost' in cell_lower:
                column_map['cost'] = idx
            elif 'fair value' in cell_lower:
                column_map['fair_value'] = idx
            elif 'interest' in cell_lower and 'rate' in cell_lower or 'coupon' in cell_lower:
                column_map['interest_rate'] = idx
            elif 'reference' in cell_lower or 'index' in cell_lower:
                column_map['reference_rate'] = idx
            elif 'spread' in cell_lower:
                column_map['spread'] = idx
            elif 'floor' in cell_lower:
                column_map['floor_rate'] = idx
            elif 'pik' in cell_lower:
                column_map['pik_rate'] = idx
            elif 'shares' in cell_lower or 'units' in cell_lower:
                column_map['shares_units'] = idx
            elif '%' in cell_lower and 'net' in cell_lower:
                column_map['percent_net_assets'] = idx
        
        return column_map
    
    def _extract_company_name_and_business_desc(self, text: str) -> Dict[str, Optional[str]]:
        """Extract clean company name and business description from text that may include location and description."""
        result = {'company_name': None, 'business_description': None}
        
        if not text:
            return result
        
        # Remove HTML entities
        text = text.replace('&amp;', '&').replace('&#x2019;', "'")
        
        # Skip URLs and invalid patterns
        text_lower = text.lower()
        if text_lower.startswith('www.') or text_lower.startswith('http'):
            return result
        
        # Skip if it's just "LLC", "Inc.", etc.
        if text.strip() in ['LLC', 'Inc.', 'Corp.', 'Ltd.', 'LP', 'L.P.']:
            return result
        
        # Pattern: "Company Name (tags) Location. Business Description. (Industry)"
        # Extract company name (before first "(" or before location pattern)
        
        # First, try to find company name with entity suffix (Inc., LLC, etc.)
        company_match = re.search(r'^([A-Z][A-Za-z0-9\s&,\-\.]+?(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.))', text)
        if company_match:
            company_name = company_match.group(1).strip()
            # Remove any trailing tags in parentheses if they're just letters/numbers (like "(l)(p)")
            company_name = re.sub(r'\s*\([a-z0-9\(\)]+\)\s*$', '', company_name, flags=re.I)
            
            # Find location pattern (City, State.)
            # Pattern: "Company Name (tags) City, State. Business Description. (Industry)"
            # Location can be after tags in parentheses, so we need a more flexible pattern
            location_match = re.search(r'([A-Z][a-z]+),\s*([A-Z]{2})\.', text)
            if location_match:
                # Extract business description (text between location and industry in parentheses)
                location_end = location_match.end()
                # Find industry in parentheses at the end
                industry_match = re.search(r'\(([^)]+(?:Goods|Services|Products|Technology|Manufacturing|Distribution|Software|Industry|Automotive|Consumer))\)\s*$', text, re.IGNORECASE)
                if industry_match:
                    biz_desc_end = industry_match.start()
                    biz_desc = text[location_end:biz_desc_end].strip()
                    # Clean up business description - remove leading/trailing periods and whitespace
                    biz_desc = re.sub(r'^\s*\.\s*', '', biz_desc)  # Remove leading period
                    biz_desc = re.sub(r'\s*\.\s*$', '', biz_desc)  # Remove trailing period
                    biz_desc = biz_desc.strip()
                    # Only use if it's meaningful (not just a period or short fragment)
                    if biz_desc and len(biz_desc) > 5 and not biz_desc.lower().startswith('www.'):
                        result['business_description'] = biz_desc
                else:
                    # No industry marker, take text after location until end
                    # Split by periods and take the first meaningful part
                    remaining = text[location_end:].strip()
                    if remaining:
                        # Remove leading period
                        remaining = re.sub(r'^\s*\.\s*', '', remaining)
                        # Take text up to next period (if it's meaningful)
                        parts = remaining.split('.')
                        if parts and len(parts[0].strip()) > 5:
                            biz_desc = parts[0].strip()
                            if not biz_desc.lower().startswith('www.'):
                                result['business_description'] = biz_desc
            
            # Remove location pattern if present (City, State.)
            company_name = re.sub(r',\s*[A-Z][a-z]+,\s*[A-Z]{2}\.', '', company_name)
            company_name = company_name.strip()
            if company_name and len(company_name) >= 3:
                result['company_name'] = company_name
                return result
        
        # If no entity suffix, try to extract before location pattern (City, State.)
        location_match = re.search(r'^([^,]+?),\s*[A-Z]{2}\.', text)
        if location_match:
            company_part = location_match.group(1).strip()
            # Remove tags in parentheses
            company_part = re.sub(r'\s*\([^)]+\)\s*$', '', company_part)
            # Check if it has a company suffix
            if re.search(r'\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.)\b', company_part, re.I):
                if company_part and len(company_part) >= 3:
                    result['company_name'] = company_part
                    return result
        
        # Fallback: take first part before first period if it looks like a name
        parts = text.split('.')
        if len(parts) > 0:
            first_part = parts[0].strip()
            # Remove tags in parentheses
            first_part = re.sub(r'\s*\([^)]+\)\s*$', '', first_part)
            # Check if it has a company suffix or is reasonably long
            has_suffix = bool(re.search(r'\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.)\b', first_part, re.I))
            if first_part and len(first_part) >= 3 and (has_suffix or len(first_part) > 10) and not first_part.lower().startswith('www.'):
                result['company_name'] = first_part
                return result
        
        return result
    
    def _parse_investment_row(self, cells: List, cell_texts: List[str], column_map: Dict,
                              current_company: Optional[str], current_industry: str,
                              current_business_desc: Optional[str]) -> Optional[Dict]:
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
        
        # Get investment description (this contains the investment details like "$ 1,750,000 Term Note...")
        # This is NOT the business description - it's the investment description
        inv_desc_col = column_map.get('business_description', 2)  # Column is labeled "business_description" but contains investment details
        if len(cell_texts) > inv_desc_col:
            inv_desc = cell_texts[inv_desc_col].strip()
            if inv_desc:
                # Parse investment description to extract investment details
                self._parse_business_description(inv_desc, investment)
        
        # Business description should come from the company name field or be carried forward
        if current_business_desc:
            investment['business_description'] = current_business_desc
        
        # Get company name and business description (may be in company column or carried forward)
        company_col = column_map.get('company', 0)
        if len(cell_texts) > company_col:
            company_text = cell_texts[company_col].strip()
            if company_text:
                extracted = self._extract_company_name_and_business_desc(company_text)
                if extracted.get('company_name'):
                    investment['company_name'] = extracted['company_name']
                elif current_company:
                    investment['company_name'] = current_company
                # Update business description if found in company field
                if extracted.get('business_description'):
                    investment['business_description'] = extracted['business_description']
                    current_business_desc = extracted['business_description']
            elif current_company:
                investment['company_name'] = current_company
        
        # Get dates from date columns (if not already extracted from business description)
        acq_col = column_map.get('acquisition_date', 5)
        if len(cell_texts) > acq_col and not investment.get('acquisition_date'):
            acq_text = cell_texts[acq_col].strip()
            # Check if it's a date (not a percentage)
            if acq_text and re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', acq_text):
                investment['acquisition_date'] = acq_text
        
        mat_col = column_map.get('maturity_date', 6)
        if len(cell_texts) > mat_col and not investment.get('maturity_date'):
            mat_text = cell_texts[mat_col].strip()
            # Check if it's a date (not a percentage)
            if mat_text and re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', mat_text):
                investment['maturity_date'] = mat_text
        
        # Get financial values - try XBRL first, then text, then business description
        principal_col = column_map.get('principal', 7)
        if len(cells) > principal_col and not investment.get('principal_amount'):
            principal_cell = cells[principal_col]
            principal_value = self._extract_numeric_value(principal_cell, 'us-gaap:InvestmentOwnedBalancePrincipalAmount')
            if principal_value is not None:
                investment['principal_amount'] = int(principal_value * 1000000) if principal_value < 1000 else int(principal_value)
            else:
                principal_text = self._extract_cell_text(principal_cell)
                principal_match = re.search(r'[\d,]+', principal_text.replace(',', ''))
                if principal_match:
                    try:
                        val = float(principal_match.group().replace(',', ''))
                        investment['principal_amount'] = int(val * 1000000) if val < 1000 else int(val)
                    except ValueError:
                        pass
        
        cost_col = column_map.get('cost', 8)
        if len(cells) > cost_col:
            cost_cell = cells[cost_col]
            cost_value = self._extract_numeric_value(cost_cell, 'us-gaap:InvestmentOwnedAtCost')
            if cost_value is not None:
                investment['cost'] = int(cost_value * 1000000) if cost_value < 1000 else int(cost_value)
            else:
                cost_text = self._extract_cell_text(cost_cell)
                cost_match = re.search(r'[\d,]+', cost_text.replace(',', ''))
                if cost_match:
                    try:
                        val = float(cost_match.group().replace(',', ''))
                        investment['cost'] = int(val * 1000000) if val < 1000 else int(val)
                    except ValueError:
                        pass
        
        fv_col = column_map.get('fair_value', 9)
        if len(cells) > fv_col:
            fv_cell = cells[fv_col]
            fv_value = self._extract_numeric_value(fv_cell, 'us-gaap:InvestmentOwnedAtFairValue')
            if fv_value is not None:
                investment['fair_value'] = int(fv_value * 1000000) if fv_value < 1000 else int(fv_value)
            else:
                fv_text = self._extract_cell_text(fv_cell)
                fv_match = re.search(r'[\d,]+', fv_text.replace(',', ''))
                if fv_match:
                    try:
                        val = float(fv_match.group().replace(',', ''))
                        investment['fair_value'] = int(val * 1000000) if val < 1000 else int(val)
                    except ValueError:
                        pass
        
        # Get rates from columns (if not already extracted from business description)
        if not investment.get('interest_rate'):
            interest_col = column_map.get('interest_rate', 10)
            if len(cell_texts) > interest_col:
                interest_text = cell_texts[interest_col].strip()
                # Skip if it's a date or percentage without number
                if interest_text and not re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', interest_text):
                    interest_match = re.search(r'(\d+\.?\d*)\s*%', interest_text)
                    if interest_match:
                        investment['interest_rate'] = f"{interest_match.group(1)}%"
        
        if not investment.get('reference_rate'):
            ref_col = column_map.get('reference_rate', 11)
            if len(cell_texts) > ref_col:
                ref_text = cell_texts[ref_col].strip()
                if ref_text and not re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', ref_text):
                    investment['reference_rate'] = standardize_reference_rate(ref_text)
        
        if not investment.get('spread'):
            spread_col = column_map.get('spread', 12)
            if len(cell_texts) > spread_col:
                spread_text = cell_texts[spread_col].strip()
                spread_match = re.search(r'(\d+\.?\d*)\s*%', spread_text)
                if spread_match:
                    investment['spread'] = f"{spread_match.group(1)}%"
        
        if not investment.get('floor_rate'):
            floor_col = column_map.get('floor_rate', 13)
            if len(cell_texts) > floor_col:
                floor_text = cell_texts[floor_col].strip()
                floor_match = re.search(r'(\d+\.?\d*)\s*%', floor_text)
                if floor_match:
                    investment['floor_rate'] = f"{floor_match.group(1)}%"
        
        if not investment.get('pik_rate'):
            pik_col = column_map.get('pik_rate', 14)
            if len(cell_texts) > pik_col:
                pik_text = cell_texts[pik_col].strip()
                pik_match = re.search(r'(\d+\.?\d*)\s*%', pik_text)
                if pik_match:
                    investment['pik_rate'] = f"{pik_match.group(1)}%"
        
        # Get shares/units
        shares_col = column_map.get('shares_units', 15)
        if len(cell_texts) > shares_col:
            shares_text = cell_texts[shares_col].strip()
            if shares_text:
                investment['shares_units'] = shares_text
        
        # Extract commitment_limit and undrawn_commitment for revolvers
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
        xbrl_tags = cell.find_all(['ix:nonfraction', 'nonfraction'])
        for tag in xbrl_tags:
            name_attr = tag.get('name', '')
            if concept_name.lower() in name_attr.lower():
                value_text = tag.get_text(strip=True)
                if not value_text or value_text in ['—', '-', '']:
                    return None
                value_text = value_text.replace(',', '').replace('$', '')
                try:
                    return float(value_text)
                except ValueError:
                    return None
        return None
    
    def _extract_cell_text(self, cell) -> str:
        """Extract text from cell, handling XBRL tags."""
        text = cell.get_text(' ', strip=True)
        if not text or text.strip() == '':
            xbrl_tags = cell.find_all(['ix:nonfraction', 'ix:nonnumeric', 'nonfraction', 'nonnumeric'])
            if xbrl_tags:
                text = xbrl_tags[0].get_text(' ', strip=True)
        return text
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if row is a header row."""
        header_keywords = ['company', 'issuer', 'portfolio company', 'investment', 'type', 'maturity', 'principal', 'cost', 'fair value']
        text_lower = ' '.join(cell_texts).lower()
        return sum(1 for kw in header_keywords if kw in text_lower) >= 3
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if row is a total/subtotal row."""
        text_lower = ' '.join(cell_texts).lower()
        return 'total' in text_lower or 'subtotal' in text_lower
    
    def _is_industry_header(self, cell_texts: List[str], column_map: Dict) -> bool:
        """Check if row is an industry header."""
        industry_col = column_map.get('industry', 1)
        if len(cell_texts) > industry_col:
            industry_text = cell_texts[industry_col].strip()
            # Industry headers typically have industry name but no company name
            company_col = column_map.get('company', 0)
            company_text = cell_texts[company_col].strip() if len(cell_texts) > company_col else ''
            return bool(industry_text and not company_text and len(industry_text) > 2)
        return False
    
    def _deduplicate_investments(self, investments: List[Dict]) -> List[Dict]:
        """Remove duplicate investments."""
        seen = set()
        unique = []
        for inv in investments:
            # Skip invalid company names
            company_name = inv.get('company_name', '').strip()
            if not company_name or company_name == 'Unknown' or company_name.lower() in ['llc', 'inc.', 'corp.']:
                continue
            
            # Create key for deduplication
            key = (
                company_name.lower(),
                inv.get('investment_type', '').lower(),
                str(inv.get('principal_amount', '')),
                str(inv.get('cost', '')),
                str(inv.get('fair_value', ''))
            )
            if key not in seen:
                seen.add(key)
                unique.append(inv)
        return unique
    
    def _parse_business_description(self, biz_desc: str, investment: Dict):
        """Parse business description to extract investment type, principal, dates, rates."""
        if not biz_desc:
            return
    
        # Extract principal amount (e.g., "$ 1,750,000" or "$1,750,000")
        principal_match = re.search(r'\$\s*([\d,]+)', biz_desc)
        if principal_match and not investment.get('principal_amount'):
            try:
                principal_val = float(principal_match.group(1).replace(',', ''))
                investment['principal_amount'] = int(principal_val)
            except ValueError:
                pass
        
        # Extract investment type
        biz_lower = biz_desc.lower()
        if 'term note' in biz_lower or 'promissory note' in biz_lower or 'secured note' in biz_lower:
            investment['investment_type'] = standardize_investment_type('Term Note')
        elif 'convertible note' in biz_lower:
            investment['investment_type'] = standardize_investment_type('Convertible Note')
        elif 'preferred' in biz_lower and ('equity' in biz_lower or 'interest' in biz_lower or 'units' in biz_lower or 'shares' in biz_lower):
            investment['investment_type'] = standardize_investment_type('Preferred Equity')
        elif 'common' in biz_lower and ('equity' in biz_lower or 'units' in biz_lower or 'shares' in biz_lower):
            investment['investment_type'] = standardize_investment_type('Common Equity')
        elif 'warrant' in biz_lower:
            investment['investment_type'] = standardize_investment_type('Warrants')
        elif 'subordinated' in biz_lower:
            investment['investment_type'] = standardize_investment_type('Subordinated Debt')
        
        # Extract maturity date (e.g., "due July 2, 2027" or "due December 31, 2025")
        maturity_match = re.search(r'due\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', biz_desc, re.IGNORECASE)
        if maturity_match and not investment.get('maturity_date'):
            investment['maturity_date'] = maturity_match.group(1)
        
        # Extract interest rate (e.g., "at 12 %" or "at 14 %")
        interest_match = re.search(r'at\s+(\d+\.?\d*)\s*%', biz_desc, re.IGNORECASE)
        if interest_match and not investment.get('interest_rate'):
            investment['interest_rate'] = f"{interest_match.group(1)}%"
        
        # Extract PIK rate (e.g., "+ 2 % PIK" or "( 1 % PIK)")
        pik_match = re.search(r'[\(+]?\s*(\d+\.?\d*)\s*%\s*PIK', biz_desc, re.IGNORECASE)
        if pik_match and not investment.get('pik_rate'):
            investment['pik_rate'] = f"{pik_match.group(1)}%"
        
        # Extract shares/units (e.g., "1,124 Class A Preferred Units" or "626.2 shares")
        shares_match = re.search(r'([\d,]+\.?\d*)\s*(?:shares|units|Class|Preferred|Common)', biz_desc, re.IGNORECASE)
        if shares_match and not investment.get('shares_units'):
            investment['shares_units'] = shares_match.group(1).replace(',', '')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = RANDCustomExtractor()
    try:
        result = extractor.extract_from_ticker("RAND")
        print(f"\nSuccessfully extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
