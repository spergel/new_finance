#!/usr/bin/env python3
"""
SSSS (SuRo Capital Corp) Custom Investment Extractor
Parses investment data from SEC filings using sec_api_client.
"""

import os
import re
import logging
import csv
from typing import List, Dict, Optional
from collections import defaultdict
from bs4 import BeautifulSoup

import sys
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class SSSSCustomExtractor:
    """Custom extractor for SSSS that fetches and parses SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "SSSS", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from SEC filing."""
        logger.info(f"Extracting investments for {ticker} from SEC filings")
        
        # Get CIK
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        # Get the latest 10-Q filing
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        # Extract accession number and build .txt URL
        acc_match = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not acc_match:
            raise ValueError("Could not parse accession number from index URL")
        
        accession = acc_match.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        
        logger.info(f"Fetching filing from: {txt_url}")
        
        # Fetch the filing using requests directly
        import requests
        response = requests.get(txt_url, headers=self.headers)
        response.raise_for_status()
        content = response.text
        
        # Parse the filing
        investments = self._parse_filing_content(content, txt_url)
        
        logger.info(f"Extracted {len(investments)} investments")
        
        # Calculate totals
        total_principal = sum(inv.get('principal_amount', 0) or 0 for inv in investments)
        total_cost = sum(inv.get('cost', 0) or 0 for inv in investments)
        total_fair_value = sum(inv.get('fair_value', 0) or 0 for inv in investments)
        
        # Industry and type breakdown
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        for inv in investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'SSSS_SuRo_Capital_Corp_investments.csv')
        
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
            'company_name': 'SuRo Capital Corp',
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _parse_filing_content(self, content: str, filing_url: str) -> List[Dict]:
        """Parse investment data from filing content."""
        investments = []
        
        # The .txt filing contains HTML documents separated by <DOCUMENT> tags
        # Find the main HTML document (usually the 10-Q itself)
        doc_pattern = re.compile(r'<DOCUMENT>\s*<TYPE>([^<]+)</TYPE>.*?<TEXT>(.*?)</TEXT>\s*</DOCUMENT>', re.DOTALL)
        documents = doc_pattern.findall(content)
        
        logger.info(f"Found {len(documents)} documents in filing")
        
        # Look for the main 10-Q HTML document
        main_html = None
        for doc_type, doc_text in documents:
            doc_type_clean = doc_type.strip().upper()
            # Check if this looks like the main document (contains investment schedule)
            if 'schedule of investments' in doc_text.lower() or 'portfolio' in doc_text.lower():
                main_html = doc_text
                logger.info(f"Found main document with schedule: {doc_type}")
                break
        
        # If no main document found, try to find HTML documents
        if not main_html:
            for doc_type, doc_text in documents:
                doc_type_clean = doc_type.strip().upper()
                # Look for HTML/HTM documents, or documents that might contain tables
                if ('HTML' in doc_type_clean or 'HTM' in doc_type_clean or 
                    doc_type_clean == '' or '10-Q' in doc_type_clean or '10Q' in doc_type_clean):
                    # Check if it has HTML structure
                    if '<table' in doc_text.lower() or '<tr' in doc_text.lower():
                        main_html = doc_text
                        logger.info(f"Found HTML document: {doc_type}")
                        break
        
        # If still no HTML found, try parsing the entire content as HTML
        if not main_html:
            logger.warning("No HTML document found in filing, trying to parse entire content")
            if '<table' in content.lower() or '<tr' in content.lower():
                main_html = content
        
        if not main_html:
            logger.warning("No HTML content found in filing")
            return []
        
        # Parse HTML
        soup = BeautifulSoup(main_html, 'html.parser')
        
        # Find investment schedule tables using the approach from the existing SSSS parser
        investments = self._parse_inline_xbrl_tables(soup)
        
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
    
    def _parse_inline_xbrl_tables(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse investment data using inline XBRL tags (similar to existing SSSS parser)."""
        investments = []
        
        # Find all tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables in HTML")
        
        def find_ix(row, concept_regex: str, prefer_fraction: Optional[bool] = None):
            """Find XBRL inline element matching concept regex."""
            pat = re.compile(concept_regex, re.I)
            found_elem = None
            for elem in row.descendants:
                if not hasattr(elem, 'name') or not elem.name:
                    continue
                name_l = elem.name.lower()
                is_nonfraction = name_l.endswith('nonfraction')
                is_nonnumeric = name_l.endswith('nonnumeric')
                if not (is_nonfraction or is_nonnumeric):
                    continue
                qn = elem.get('name') or ''
                if not isinstance(qn, str):
                    continue
                if not pat.search(qn):
                    continue
                if prefer_fraction is None:
                    return elem
                if prefer_fraction and is_nonfraction:
                    return elem
                if (prefer_fraction is False) and is_nonnumeric:
                    return elem
                if not found_elem:
                    found_elem = elem
            return found_elem
        
        def parse_money(s: str) -> Optional[float]:
            """Parse monetary value from string."""
            if not s:
                return None
            s = s.replace('\u00a0', ' ').replace(',', '').replace('$', '').strip()
            try:
                if s in ('—', '-', '–', ''):
                    return None
                return float(s)
            except:
                return None
        
        current_company = None
        current_industry = "Unknown"
        current_business_desc = None
        rows_since_company = 0  # Track how many rows since last company
        
        # Filter tables to only those that look like investment schedules
        # First, look for tables with "Schedule of Investments" in summary attribute (like existing parser)
        investment_tables = []
        for tbl_idx, tbl in enumerate(tables):
            # Check summary attribute first (like existing SSSS parser)
            summary_attr = tbl.get('summary', '')
            if 'schedule of investments' in summary_attr.lower():
                investment_tables.insert(0, tbl)  # Highest priority
                logger.info(f"Found Schedule of Investments table {tbl_idx+1} (summary attribute)")
                continue
            
            # Check if table contains investment-related keywords
            table_text = tbl.get_text().lower()
            
            # Must have investment-related content
            has_investment_content = any(keyword in table_text for keyword in [
                'schedule of investments', 'portfolio company', 'investment', 'fair value', 'cost'
            ])
            
            # But exclude balance sheet/income statement tables and XBRL metadata tables
            has_financial_statement_content = any(keyword in table_text for keyword in [
                'total assets', 'total liabilities', 'net assets', 'operating expenses', 
                'income statement', 'balance sheet', 'data type', 'dtr-types', 'xbrli:'
            ])
            
            # Also check if table has actual company names (not just metadata)
            has_company_names = bool(re.search(r'\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation)\b', table_text, re.I))
            
            logger.debug(f"Table {tbl_idx+1}: has_investment={has_investment_content}, has_financial_stmt={has_financial_statement_content}, has_companies={has_company_names}")
            
            if has_investment_content and not has_financial_statement_content:
                # Prefer tables with company names
                if has_company_names:
                    investment_tables.append(tbl)  # Add to end (lower priority than summary tables)
                    logger.debug(f"Added table {tbl_idx+1} (has companies)")
                else:
                    investment_tables.append(tbl)
                    logger.debug(f"Added table {tbl_idx+1}")
        
        if not investment_tables:
            logger.warning("No investment schedule tables found, using all tables")
            investment_tables = tables
        else:
            logger.info(f"Filtered to {len(investment_tables)} investment tables from {len(tables)} total tables")
        
        logger.info(f"Processing {len(investment_tables)} investment tables")
        
        companies_found = 0
        investment_rows_found = 0
        
        for tbl_idx, tbl in enumerate(investment_tables):
            rows = tbl.find_all('tr')
            if not rows:
                continue
            
            logger.debug(f"Processing table {tbl_idx+1}/{len(investment_tables)} with {len(rows)} rows")
            
            for tr in rows:
                tds = tr.find_all('td')
                if not tds:
                    continue
                
                # Check if this is a company header row
                first_cell = tds[0]
                first_cell_text = first_cell.get_text(strip=True)
                
                # Skip summary/aggregate rows and XBRL metadata
                summary_keywords = [
                    'industry theme', 'asset', 'total', 'beginning', 'ending', 'purchases',
                    'realized', 'unrealized', 'appreciation', 'depreciation', 'exercises',
                    'conversions', 'fair value as of', 'net change', 'private portfolio',
                    'publicly traded', 'portfolio companies', 'schedule of investments [line items]',
                    'general description', 'period type', 'commitments and contingencies',
                    'abstract', 'duration', 'instant', 'aggregate principal amount',
                    'deferred', 'financing costs', 'nav per share', 'number of shares',
                    'gross proceeds', 'net proceeds', 'weighted average', 'balance type',
                    'debt capital activities', 'stock-based compensation', 'subsequent events',
                    'outstanding as of', 'data type', 'dtr-types', 'xbrli:', 'na,'
                ]
                if any(keyword in first_cell_text.lower() for keyword in summary_keywords):
                    continue
                
                # Skip rows that are clearly XBRL metadata (contain brackets)
                if '[' in first_cell_text and ']' in first_cell_text:
                    continue
                
                # Company header rows typically have:
                # - Bold or underlined text in first cell
                # - No financial data in the row
                # - Company name format (not investment type keywords)
                is_company_row = False
                if first_cell_text:
                    # Check for bold/strong/underline styling (like existing SSSS parser)
                    has_bold = first_cell.find(['b', 'strong']) is not None
                    style = first_cell.get('style', '')
                    has_underline = 'underline' in style.lower() or 'text-decoration:underline' in style.lower()
                    
                    # Check if it looks like a company name (not an investment type)
                    investment_type_keywords = [
                        'preferred shares', 'common shares', 'warrant', 'loan', 'debt',
                        'equity', 'notes', 'bonds', 'series', 'agreement for future',
                        'options', 'simple agreement'
                    ]
                    looks_like_investment_type = any(keyword in first_cell_text.lower() for keyword in investment_type_keywords)
                    
                    # Check if row has financial data (cost/fair value) in first few cells
                    has_financial_data = False
                    for i, td in enumerate(tds[:5]):  # Only check first 5 cells
                        td_text = td.get_text(strip=True)
                        if re.search(r'\$?\s*\d+[,\.]\d+', td_text):
                            has_financial_data = True
                            break
                    
                    # Company row if: (bold/underline) AND (not investment type) AND (no financial data in first few cells)
                    # Company name patterns: contains Inc., LLC, Ltd., Corp, etc.
                    has_company_suffix = bool(re.search(r'\b(Inc\.?|LLC|L\.L\.C\.|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|LLP|PLC)\b', first_cell_text, re.I))
                    
                    # Also check if it's a location (City, State format)
                    is_location = bool(re.match(r'^[A-Z][a-z]+,?\s+[A-Z]{2}$', first_cell_text))
                    
                    # Company row: must have bold/underline AND look like company name AND no financial data
                    # OR has company suffix and no financial data
                    # OR looks like a company name (has suffix) even without bold/underline
                    if ((has_bold or has_underline) and not looks_like_investment_type and not has_financial_data and not is_location) or (has_company_suffix and not has_financial_data and not is_location):
                        # Additional validation: should have company suffix or be a reasonable company name
                        if has_company_suffix or (len(first_cell_text.split()) >= 2 and len(first_cell_text) > 5):
                            is_company_row = True
                    
                    # Also check if first cell looks like a company name even without styling
                    if not is_company_row and has_company_suffix and not has_financial_data and not is_location and not looks_like_investment_type:
                        is_company_row = True
                
                if is_company_row:
                    current_company = re.sub(r'\s+', ' ', first_cell_text)
                    # Clean up company name
                    current_company = self._clean_text(current_company)
                    companies_found += 1
                    rows_since_company = 0  # Reset counter
                    logger.debug(f"Found company: {current_company}")
                    # Try to get business description from second cell
                    if len(tds) > 1:
                        biz_desc = self._extract_cell_text(tds[1])
                        if biz_desc and not re.match(r'^[A-Z][a-z]+,?\s+[A-Z]{2}$', biz_desc):
                            current_business_desc = biz_desc
                    # Try to get industry from XBRL
                    industry_ix = find_ix(tr, r'InvestmentIndustryDescription', prefer_fraction=False)
                    if industry_ix:
                        industry_text = industry_ix.get_text(strip=True)
                        if industry_text:
                            current_industry = self._clean_industry_name(industry_text)
                    continue
                
                # Increment counter for non-company rows
                if current_company:
                    rows_since_company += 1
                
                # Check if this is an investment data row (has financial data)
                # Look for rows with specific background color (rgb(204,238,255)) - these are investment rows
                style = tr.get('style', '')
                has_investment_background = (
                    'background-color' in style.lower() and 
                    ('204,238,255' in style or 'rgb(204, 238, 255)' in style or '#cceeff' in style.lower())
                )
                
                # Look for financial data in the row using XBRL tags
                cost_ix = find_ix(tr, r'InvestmentOwnedAtCost', prefer_fraction=True)
                fv_ix = find_ix(tr, r'InvestmentOwnedAtFairValue', prefer_fraction=True)
                principal_ix = find_ix(tr, r'InvestmentOwnedBalancePrincipalAmount|InvestmentOwnedBalanceShares', prefer_fraction=True)
                
                # Also check for numeric values in cells
                has_numeric_data = False
                for td in tds:
                    td_text = td.get_text(strip=True)
                    if re.search(r'\$?\s*\d+[,\.]\d+', td_text):
                        has_numeric_data = True
                        break
                
                # This is an investment row if:
                # 1. Has the investment background color AND has a company (highest confidence)
                # 2. Has XBRL financial data AND has a company (high confidence)
                # 3. Has numeric data AND has a company AND doesn't look like a company row (medium confidence)
                is_investment_row = False
                if current_company and not is_company_row:
                    # Highest confidence: background color or XBRL tags
                    if has_investment_background or cost_ix or fv_ix or principal_ix:
                        is_investment_row = True
                        logger.debug(f"High confidence investment row: {first_cell_text[:50]}")
                    elif has_numeric_data:
                        # Additional check: first cell should not be a company name or summary
                        # Also check if it looks like an investment type
                        looks_like_inv_type = any(keyword in first_cell_text.lower() for keyword in [
                            'preferred', 'common', 'warrant', 'loan', 'debt', 'equity', 'notes', 
                            'bonds', 'series', 'agreement', 'options', 'simple', 'shares', 'units'
                        ])
                        # More lenient: if it's not a company name, not a summary, and has numeric data, it's likely an investment
                        # Also check if the row has multiple cells with data (investment rows usually have several columns)
                        # And if it's within 5 rows of a company name, it's more likely to be an investment
                        has_multiple_cells = len([td for td in tds if td.get_text(strip=True)]) >= 3
                        is_near_company = rows_since_company <= 5  # Within 5 rows of company
                        if (first_cell_text != current_company and 
                            not any(keyword in first_cell_text.lower() for keyword in summary_keywords) and
                            (looks_like_inv_type or (len(first_cell_text) < 100 and (has_multiple_cells or is_near_company)))):
                            is_investment_row = True
                            logger.debug(f"Medium confidence investment row ({rows_since_company} rows after company): {first_cell_text[:50]}")
                
                if is_investment_row:
                    # Get investment type from first cell (if not company name)
                    inv_type = self._extract_cell_text(first_cell).strip()
                    
                    # Skip if this looks like a summary row or invalid investment type
                    # But be more selective - only skip obvious non-investments
                    invalid_inv_types = [
                        'schedule of investments', 'granted', 'outstanding as of', 'gcl', 
                        'long term debt, principal', 'balance type', 'data type', 'period type',
                        'investment at fair value', 'investment owned at fair value', 'investment cost',
                        'debt instrument face amount', 'debt instrument, fair value', 'debt investments',
                        'proceeds from debt', 'repurchase amount', 'escrow proceeds receivable',
                        'share-based payment arrangement', 'number of restricted shares', 'restricted shares grant',
                        'fair value', 'investment owned at cost', 'investment cost', 'debt investments'
                    ]
                    if any(keyword in inv_type.lower() for keyword in invalid_inv_types):
                        continue
                    
                    # Skip if it's just a year (4 digits)
                    if re.match(r'^\d{4}$', inv_type.strip()):
                        continue
                    
                    # Skip if it's a very short non-investment type
                    if len(inv_type.strip()) <= 3 and inv_type.strip().upper() not in ['SAFE', 'PIK']:
                        continue
                    
                    # Skip if investment type looks like a financial statement line item
                    if any(keyword in inv_type.lower() for keyword in ['proceeds', 'repurchase', 'escrow', 'restricted', 'share-based', 'noncash expense']):
                        continue
                    
                    # If first cell is the company name, try to get investment type from second cell
                    if inv_type == current_company or not inv_type:
                        # Try second cell
                        if len(tds) > 1:
                            inv_type = self._extract_cell_text(tds[1]).strip()
                        # If still company name, try third cell
                        if inv_type == current_company and len(tds) > 2:
                            inv_type = self._extract_cell_text(tds[2]).strip()
                    
                    # Get dates
                    date_ix = find_ix(tr, r'InitialInvestmentDate|InvestmentDate', prefer_fraction=False)
                    acq_date = date_ix.get_text(strip=True) if date_ix else None
                    
                    # Get financial values from XBRL tags
                    principal = parse_money(principal_ix.get_text()) if principal_ix else None
                    cost = parse_money(cost_ix.get_text()) if cost_ix else None
                    fv = parse_money(fv_ix.get_text()) if fv_ix else None
                    
                    # Extract percentage values from XBRL tags
                    interest_rate_ix = find_ix(tr, r'InvestmentInterestRate', prefer_fraction=True)
                    spread_ix = find_ix(tr, r'InvestmentBasisSpreadVariableRate|InvestmentBasisSpread', prefer_fraction=True)
                    floor_rate_ix = find_ix(tr, r'InvestmentInterestRateFloor|FloorRate', prefer_fraction=True)
                    pik_rate_ix = find_ix(tr, r'PIKRate|PIKInterestRate', prefer_fraction=True)
                    reference_rate_ix = find_ix(tr, r'ReferenceRateToken|VariableInterestRateType', prefer_fraction=False)
                    
                    # Extract percentage values
                    interest_rate = None
                    if interest_rate_ix:
                        rate_text = interest_rate_ix.get_text(strip=True)
                        interest_rate = self._format_percent(rate_text)
                    
                    spread = None
                    if spread_ix:
                        spread_text = spread_ix.get_text(strip=True)
                        spread = self._format_percent(spread_text)
                    
                    floor_rate = None
                    if floor_rate_ix:
                        floor_text = floor_rate_ix.get_text(strip=True)
                        floor_rate = self._format_percent(floor_text)
                    
                    pik_rate = None
                    if pik_rate_ix:
                        pik_text = pik_rate_ix.get_text(strip=True)
                        pik_rate = self._format_percent(pik_text)
                    
                    reference_rate = None
                    if reference_rate_ix:
                        ref_text = reference_rate_ix.get_text(strip=True)
                        if ref_text:
                            reference_rate = standardize_reference_rate(ref_text.upper())
                    
                    # Also try to extract from cell text (for cases where XBRL tags aren't present)
                    # Get cell texts for this row
                    row_cell_texts = [self._extract_cell_text(td) for td in tds]
                    row_text = ' '.join(row_cell_texts).upper()
                    
                    # Extract reference rate and spread from patterns like "SOFR + 6.00%", "Prime + 2.85%"
                    if not reference_rate or not spread:
                        ref_spread_match = re.search(
                            r'(\b(?:[0-9]+[-\s]?MONTH\s+)?(?:SOFR|LIBOR|PRIME|PRIME RATE|BASE RATE|EURIBOR|E)\b)\s*\+\s*([\d\.]+)\s*%?',
                            row_text, re.IGNORECASE
                        )
                        if ref_spread_match:
                            ref_base = ref_spread_match.group(1).strip().upper()
                            # Normalize reference rate names
                            ref_map = {'E': 'EURIBOR', 'BASE RATE': 'BASE RATE', 'BASE': 'BASE RATE'}
                            ref_base = ref_map.get(ref_base, ref_base)
                            if not reference_rate:
                                reference_rate = standardize_reference_rate(ref_base)
                            if not spread:
                                spread = f"{float(ref_spread_match.group(2)):.2f}%"
                    
                    # Extract floor rate from text pattern "floor 2.00%" or "floor rate 2.00%"
                    if not floor_rate:
                        floor_match = re.search(r'FLOOR\s*(?:RATE)?\s*([\d\.]+)\s*%', row_text, re.IGNORECASE)
                        if floor_match:
                            floor_rate = f"{float(floor_match.group(1)):.2f}%"
                    
                    # Extract PIK rate from text pattern "PIK 5.00%" or "PIK interest 5.00%"
                    if not pik_rate:
                        pik_match = re.search(r'PIK\s*(?:INTEREST)?\s*([\d\.]+)\s*%', row_text, re.IGNORECASE)
                        if pik_match:
                            pik_rate = f"{float(pik_match.group(1)):.2f}%"
                    
                    # Extract interest rate from cell text if not found in XBRL
                    if not interest_rate:
                        # Look for percentage patterns in cells
                        for cell_text in row_cell_texts:
                            rate_match = re.search(r'([\d\.]+)\s*%', cell_text)
                            if rate_match:
                                rate_val = float(rate_match.group(1))
                                # If it's a reasonable interest rate (between 0.1% and 50%)
                                if 0.1 <= rate_val <= 50:
                                    interest_rate = f"{rate_val:.2f}%"
                                    break
                    
                    # If no XBRL values, try to extract from cell text
                    if cost is None and fv is None:
                        # Look for cost/fair value in cells (usually in later columns)
                        # Try to find columns that might contain cost and fair value
                        money_values = []
                        for i, td in enumerate(tds):
                            td_text = td.get_text(strip=True)
                            money_val = parse_money(td_text)
                            if money_val and money_val > 100:  # Filter out small values that might be years or percentages
                                money_values.append((i, money_val))
                        
                        # If we found money values, use the larger ones (likely cost/fair value)
                        if money_values:
                            # Sort by value (descending) and take the largest ones
                            money_values.sort(key=lambda x: x[1], reverse=True)
                            if len(money_values) >= 2:
                                cost = money_values[1][1]  # Second largest
                                fv = money_values[0][1]    # Largest
                            elif len(money_values) == 1:
                                fv = money_values[0][1]    # Use as fair value
                    
                    # Only create investment if we have meaningful data
                    if cost is not None or fv is not None:
                        logger.debug(f"Creating investment for {current_company}: type={inv_type}, cost={cost}, fv={fv}")
                        # Clean up investment type
                        clean_inv_type = self._clean_text(inv_type) if inv_type else 'Unknown'
                        
                        # Skip if investment type is just a company name (wrong column)
                        if clean_inv_type and clean_inv_type != 'Unknown':
                            # Check if investment type looks like a company name (has Inc, LLC, etc.)
                            has_company_suffix = bool(re.search(r'\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation)\b', clean_inv_type, re.I))
                            if has_company_suffix and len(clean_inv_type) > 20:  # Likely a company name, not investment type
                                logger.debug(f"Skipping row - investment type looks like company name: {clean_inv_type}")
                                continue
                        
                        investment = {
                            'company_name': self._clean_text(current_company),
                            'industry': current_industry,
                            'business_description': self._clean_text(current_business_desc) if current_business_desc else '',
                            'investment_type': standardize_investment_type(clean_inv_type) if clean_inv_type else 'Unknown',
                            'acquisition_date': acq_date,
                            'maturity_date': None,
                            'principal_amount': int(principal) if principal else None,
                            'cost': int(cost) if cost else None,
                            'fair_value': int(fv) if fv else None,
                            'interest_rate': interest_rate,
                            'reference_rate': reference_rate,
                            'spread': spread,
                            'floor_rate': floor_rate,
                            'pik_rate': pik_rate,
                        }
                        
                        # Skip if company name looks invalid
                        company_name = investment['company_name']
                        invalid_patterns = [
                            'schedule of investments', 'general description', 'period type',
                            'commitments', 'abstract', 'duration', 'instant', 'aggregate',
                            'deferred', 'financing', 'nav', 'proceeds', 'weighted', 'average',
                            'part ii', 'part i', 'total', 'assets', 'liabilities', 'income',
                            'expense', 'item', 'jurisdiction', 'address', 'industry theme',
                            'balance type', 'debt capital', 'stock-based', 'subsequent events',
                            'outstanding as of', 'data type', 'dtr-types', 'xbrli:', 'na,',
                            'investment at fair value', 'investment owned at fair value', 'investment cost',
                            'debt instrument', 'escrow proceeds', 'share-based payment', 'restricted shares',
                            'repurchase amount', 'proceeds from'
                        ]
                        is_valid = (
                            company_name and 
                            len(company_name) >= 3 and
                            not company_name.startswith('(') and
                            not any(pattern in company_name.lower() for pattern in invalid_patterns) and
                            '[' not in company_name and  # No XBRL metadata
                            ']' not in company_name
                        )
                        
                        # Additional validation: skip summary rows
                        # Summary rows often have:
                        # - No acquisition date AND very large round numbers (likely totals)
                        # - Investment type is just generic (Preferred Equity, Common Equity) without details
                        # - Cost equals fair value exactly (often indicates summary/total row)
                        is_summary_row = False
                        if not acq_date:
                            # Check if values are very large and round (likely summary)
                            if cost or fv:
                                cost_val = cost or 0
                                fv_val = fv or 0
                                max_val = max(cost_val, fv_val)
                                
                                # Very large round numbers without acquisition date are suspicious
                                if max_val > 10000000:  # Over 10M
                                    # Check if investment type is very generic
                                    generic_types = ['preferred equity', 'common equity', 'options', 'debt investments', 'membership interest']
                                    if clean_inv_type.lower() in generic_types:
                                        # Strong indicator: cost equals fair value exactly (within $1)
                                        if cost and fv and abs(cost - fv) <= 1:
                                            is_summary_row = True
                                        # Also check: if cost and fv are both very large round numbers (multiples of 1M)
                                        elif cost and fv:
                                            # Check if both are round numbers (end in many zeros)
                                            cost_round = (cost % 1000000 == 0)
                                            fv_round = (fv % 1000000 == 0)
                                            if cost_round and fv_round and max_val > 50000000:
                                                # And no other distinguishing info
                                                if not principal and not interest_rate:
                                                    is_summary_row = True
                                        # Or if only one value exists and it's very large
                                        elif (cost and not fv) or (fv and not cost):
                                            if max_val > 50000000:  # Over 50M
                                                is_summary_row = True
                        
                        if is_valid and not is_summary_row:
                            investment_rows_found += 1
                            investments.append(investment)
                            logger.debug(f"Added investment: {company_name} - {investment.get('investment_type')} - Cost: {investment.get('cost')}, FV: {investment.get('fair_value')}")
        
        # De-duplicate investments
        deduplicated = []
        seen = set()
        for inv in investments:
            key = (
                inv['company_name'],
                inv.get('investment_type', 'Unknown'),
                inv.get('cost', 0),
                inv.get('fair_value', 0)
            )
            if key not in seen:
                seen.add(key)
                deduplicated.append(inv)
        
        logger.info(f"Found {companies_found} companies, {investment_rows_found} investment rows, {len(investments)} before de-dup, {len(deduplicated)} after de-dup")
        return deduplicated
    
    def _extract_cell_text(self, cell) -> str:
        """Extract text from cell, handling XBRL tags and cleaning up whitespace."""
        # First try to get all text
        text = cell.get_text(' ', strip=True)
        
        # If empty or just whitespace, check for XBRL tags
        if not text or text.strip() == '':
            # Look for ix:nonfraction or ix:nonnumeric tags
            xbrl_tags = cell.find_all(['ix:nonfraction', 'ix:nonnumeric', 'nonfraction', 'nonnumeric'])
            if xbrl_tags:
                # Get text from first XBRL tag
                text = xbrl_tags[0].get_text(' ', strip=True)
        
        # Clean up the text: normalize whitespace, remove excessive newlines
        if text:
            # Replace multiple whitespace/newlines with single space
            text = re.sub(r'\s+', ' ', text)
            # Remove leading/trailing whitespace
            text = text.strip()
            # Remove any remaining newline characters
            text = text.replace('\n', ' ').replace('\r', ' ')
            # Normalize again after removing newlines
            text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _format_percent(self, value_str: str) -> Optional[str]:
        """Format a percentage value string to standard format (e.g., "6.00%")."""
        if not value_str:
            return None
        
        try:
            # Remove any non-numeric characters except decimal point and minus
            clean_value = re.sub(r'[^\d\.\-]', '', value_str.strip())
            if not clean_value or clean_value in ('—', '-', '–', ''):
                return None
            
            value = float(clean_value)
            
            # If value is between 0 and 1, it's likely a decimal (e.g., 0.06 = 6%)
            # If value is between 1 and 100, it's likely already a percentage
            if 0 < abs(value) <= 1.0:
                value *= 100.0
            
            # Format to 2 decimal places, remove trailing zeros
            formatted = f"{value:.4f}".rstrip('0').rstrip('.')
            return f"{formatted}%"
        except (ValueError, TypeError):
            # If it's already a percentage string, return as-is
            if '%' in value_str:
                return value_str.strip()
            return None
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text by removing excessive whitespace and newlines."""
        if not text:
            return ""
        
        # Replace multiple whitespace/newlines with single space
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        # Remove any remaining newline/carriage return characters
        text = text.replace('\n', ' ').replace('\r', ' ')
        # Normalize again after removing newlines
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _clean_industry_name(self, industry: str) -> str:
        """Clean and standardize industry name."""
        if not industry:
            return "Unknown"
        
        industry = self._clean_text(industry)
        if not industry:
            return "Unknown"
        
        # Standardize
        industry = standardize_industry(industry)
        
        return industry
