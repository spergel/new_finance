#!/usr/bin/env python3
"""
Historical Investment Extractor

Extracts investment data from historical 10-Q filings for BDCs, tracking
reporting periods to build time-series investment data.
"""

import os
import logging
import csv
import re
import requests
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime
from collections import defaultdict
import importlib

from sec_api_client import SECAPIClient

logger = logging.getLogger(__name__)


def _to_plain(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return {k: v for k, v in vars(row).items()}
    except Exception:
        return {}

class HistoricalInvestmentExtractor:
    """
    Extracts historical investment data from multiple 10-Q filings.
    Works with existing BDC parsers by calling their extraction methods.
    """
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.headers = {'User-Agent': user_agent}
    
    def extract_historical_investments(
        self,
        ticker: str,
        parser_module_name: str = None,
        years_back: int = 5,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract historical investments from multiple 10-Q filings.
        
        Args:
            ticker: BDC ticker symbol
            parser_module_name: Name of the parser module (e.g., 'glad_parser')
                               If None, tries to infer from ticker
            years_back: Number of years to look back
            start_date: Start date in YYYY-MM-DD format (optional)
            end_date: End date in YYYY-MM-DD format (optional)
            
        Returns:
            List of investment dictionaries, each with a 'reporting_period' field
        """
        logger.info(f"Extracting historical investments for {ticker}")
        
        filings = self.sec_client.get_historical_10q_filings(
            ticker, years_back=years_back, start_date=start_date, end_date=end_date
        )
        
        if not filings:
            logger.warning(f"No historical 10-Q filings found for {ticker}")
            return []
        
        logger.info(f"Found {len(filings)} 10-Q filings for {ticker}")
        
        parser = self._get_parser_for_ticker(ticker, parser_module_name)
        if not parser:
            logger.error(f"Could not find parser for {ticker}")
            return []
        
        all_investments: List[Dict[str, Any]] = []
        # Track investments by period to prevent duplicates
        seen_by_period: Dict[str, set] = defaultdict(set)
        
        for filing_info in filings:
            try:
                logger.info(f"Processing filing {filing_info['date']} (accession: {filing_info['accession']})")
                
                txt_url = self._get_filing_txt_url(filing_info)
                if not txt_url:
                    logger.warning(f"Could not get text URL for filing {filing_info['accession']}")
                    continue
                
                try:
                    filing_response = requests.get(txt_url, headers=self.headers)
                    filing_response.raise_for_status()
                    filing_content = filing_response.text
                except Exception as e:
                    logger.warning(f"Could not download filing content: {e}")
                    filing_content = None
                
                period_end = self._extract_period_end_date(filing_info, filing_content)
                reporting_period = period_end or filing_info['date']
                
                # For ARCC, prefer HTML URL
                if ticker.upper() == 'ARCC':
                    html_url = self._get_filing_html_url(filing_info)
                    if html_url:
                        txt_url = html_url  # Use HTML URL instead
                
                # Handle different extractor interfaces
                # Check for extract_from_filing first (custom parsers like CSWC, CGBD, MAIN)
                if hasattr(parser, 'extract_from_filing'):
                    html_url = self._get_filing_html_url(filing_info)
                    if html_url and txt_url:
                        logger.info(f"Using extract_from_filing for {ticker}")
                        try:
                            extraction_result = parser.extract_from_filing(
                                txt_url,
                                html_url,
                                self._get_company_name(ticker),
                                self.sec_client.get_cik(ticker),
                                ticker
                            )
                            # Handle BDCExtractionResult object
                            if hasattr(extraction_result, 'investments'):
                                result = {
                                    'investments': extraction_result.investments,
                                    'company_name': extraction_result.company_name,
                                    'cik': extraction_result.cik
                                }
                            elif isinstance(extraction_result, dict):
                                result = extraction_result
                            else:
                                result = None
                        except Exception as e:
                            logger.warning(f"extract_from_filing failed for {ticker}: {e}")
                            result = None
                    else:
                        logger.warning(f"extract_from_filing requires both TXT and HTML URLs, but HTML URL not found")
                        result = None
                # Check for HTML URL method (many parsers prefer HTML)
                elif hasattr(parser, 'extract_from_html_url'):
                    # Try to get HTML URL from filing
                    html_url = self._get_filing_html_url(filing_info)
                    if html_url:
                        logger.info(f"Using HTML URL for {ticker}: {html_url}")
                        result = parser.extract_from_html_url(
                            html_url,
                            self._get_company_name(ticker),
                            self.sec_client.get_cik(ticker)
                        )
                    else:
                        logger.warning(f"Parser {ticker} requires HTML URL but couldn't find one, trying TXT URL")
                        # Fallback to TXT if HTML not available
                        if hasattr(parser, 'extract_from_url'):
                            result = parser.extract_from_url(
                                txt_url,
                                self._get_company_name(ticker),
                                self.sec_client.get_cik(ticker)
                            )
                        else:
                            result = None
                elif hasattr(parser, 'extract_from_url'):
                    result = parser.extract_from_url(
                        txt_url,
                        self._get_company_name(ticker),
                        self.sec_client.get_cik(ticker)
                    )
                else:
                    logger.warning(f"Parser for {ticker} doesn't have extract_from_filing, extract_from_url or extract_from_html_url method")
                    result = None
                
                if result and 'investments' in result:
                    duplicates_count = 0
                    for inv in result['investments']:
                        plain = _to_plain(inv)
                        plain['reporting_period'] = reporting_period
                        plain['filing_date'] = filing_info['date']
                        plain['accession_number'] = filing_info['accession']
                        
                        # Deduplicate within the same period: (company_name, investment_type)
                        dedup_key = (
                            str(plain.get('company_name', '')).lower().strip(),
                            str(plain.get('investment_type', '')).lower().strip()
                        )
                        
                        if dedup_key in seen_by_period[reporting_period]:
                            duplicates_count += 1
                            continue
                        
                        seen_by_period[reporting_period].add(dedup_key)
                        all_investments.append(plain)
                    
                    if duplicates_count > 0:
                        logger.info(f"Extracted {len(result['investments'])} investments from {filing_info['date']} ({duplicates_count} duplicates filtered)")
                    else:
                        logger.info(f"Extracted {len(result['investments'])} investments from {filing_info['date']}")
                else:
                    logger.warning(f"No investments extracted from filing {filing_info['date']}")
                    
            except Exception as e:
                logger.error(f"Error processing filing {filing_info.get('date', 'unknown')}: {e}")
                continue
        
        logger.info(f"Total historical investments extracted for {ticker}: {len(all_investments)}")
        return all_investments
    
    def _get_parser_for_ticker(self, ticker: str, parser_module_name: Optional[str] = None):
        """Get the appropriate parser for a ticker."""
                # Special handling for ARCC - uses flexible_table_parser
        if ticker.upper() == 'ARCC':
            try:
                from flexible_table_parser import FlexibleTableParser
                parser = FlexibleTableParser(user_agent=self.headers['User-Agent'])
                # Wrap it in a simple adapter
                class ARCCAdapter:
                    def __init__(self, parser):
                        self.parser = parser
                        self.headers = {'User-Agent': 'BDC-Extractor/1.0'}
                    
                    def extract_from_url(self, url, company_name, cik):
                        # This should not be called for ARCC since we use HTML URL
                        return self.extract_from_html_url(url, company_name, cik)
                    
                    def extract_from_html_url(self, html_url, company_name, cik):
                        """Extract from HTML URL using FlexibleTableParser."""
                        try:
                            investments = self.parser.parse_html_filing(html_url)
                            if not investments or len(investments) == 0:
                                logger.warning(f"FlexibleTableParser extracted 0 investments from {html_url}")
                                # This is a known issue - FlexibleTableParser finds tables but extracts 0 rows
                                # The issue is likely in _parse_data_row requiring both company_name and investment_type
                                return {'investments': []}
                            
                            return {
                                'investments': investments,
                                'company_name': company_name,
                                'cik': cik
                            }
                        except Exception as e:
                            logger.error(f"Failed to parse {html_url}: {e}")
                            return {'investments': []}
                
                return ARCCAdapter(parser)
            except Exception as e:
                logger.warning(f"Could not create ARCC parser: {e}")
        
        # Check for parser (custom parsers have been renamed to regular parsers)
        if parser_module_name:
            try:
                module = importlib.import_module(parser_module_name)
                for class_name in ['Extractor', f'{ticker}Extractor', f'{ticker.upper()}Extractor']:
                    if hasattr(module, class_name):
                        extractor_class = getattr(module, class_name)
                        logger.info(f"Using parser: {parser_module_name}.{class_name}")
                        return extractor_class(user_agent=self.headers['User-Agent'])
            except ImportError as e:
                logger.warning(f"Could not import parser module {parser_module_name}: {e}")
        
        # Fallback: try default parser name
        parser_module_name = f"{ticker.lower()}_parser"
        try:
            module = importlib.import_module(parser_module_name)
            for class_name in ['Extractor', f'{ticker}Extractor', f'{ticker.upper()}Extractor']:
                if hasattr(module, class_name):
                    extractor_class = getattr(module, class_name)
                    logger.info(f"Using parser: {parser_module_name}.{class_name}")
                    return extractor_class(user_agent=self.headers['User-Agent'])
        except ImportError:
            pass
        
        return None
    
    def _get_filing_txt_url(self, filing_info: Dict[str, Any]) -> Optional[str]:
        index_url = filing_info.get('index_url')
        if not index_url:
            return None
        match = re.search(r'/edgar/data/(\d+)/(\d+)/([\d-]+)-index\.html', index_url)
        if not match:
            return None
        cik = match.group(1)
        accession_no_hyphens = match.group(2)
        accession = match.group(3)
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
    
    def _get_filing_html_url(self, filing_info: Dict[str, Any]) -> Optional[str]:
        """Get HTML URL for a filing (preferred for many parsers)."""
        index_url = filing_info.get('index_url')
        if not index_url:
            return None
        
        # Try to get HTML document from index
        try:
            response = requests.get(index_url, headers=self.headers)
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for main HTML document - try multiple patterns
                base_url = '/'.join(index_url.split('/')[:-1])
                
                # Pattern 1: Look for links with 'main' in the name (but not index)
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    link_text = link.get_text().lower()
                    if (href.endswith('.htm') or href.endswith('.html')) and not href.endswith('index.htm') and not href.endswith('index.html'):
                        if 'main' in href.lower() or 'main' in link_text:
                            if href.startswith('http'):
                                return href
                            else:
                                # Relative URL - construct properly
                                if href.startswith('/'):
                                    return f"https://www.sec.gov{href}"
                                else:
                                    return f"https://www.sec.gov{base_url}/{href}"
                
                # Pattern 2: Look for any .htm file (often the main document, but skip index)
                # Prefer files that look like main documents (have numbers or ticker-like names)
                candidates = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if href.endswith('.htm') and not href.endswith('-index.htm') and not href.endswith('index.htm'):
                        # Handle /ix?doc= URLs (SEC viewer) - extract the actual path
                        if '/ix?doc=' in href:
                            # Extract the path after doc=
                            doc_match = re.search(r'/ix\?doc=(.+)', href)
                            if doc_match:
                                doc_path = doc_match.group(1)
                                # URL decode if needed
                                from urllib.parse import unquote
                                doc_path = unquote(doc_path)
                                if doc_path.startswith('/'):
                                    href = f"https://www.sec.gov{doc_path}"
                                else:
                                    href = f"https://www.sec.gov/{doc_path}"
                        
                        if href.startswith('http'):
                            candidates.append(href)
                        else:
                            if href.startswith('/'):
                                candidates.append(f"https://www.sec.gov{href}")
                            else:
                                candidates.append(f"https://www.sec.gov{base_url}/{href}")
                
                # Return the first candidate (usually the main document is listed first)
                if candidates:
                    return candidates[0]
                
                # Pattern 3: Try to construct from accession number
                accession = filing_info.get('accession', '')
                if accession:
                    # Extract ticker from company name or use a pattern
                    # Many filings have format: ticker-YYYYMMDD.htm
                    # But we don't have ticker here, so try common patterns
                    cik = filing_info.get('cik', '').lstrip('0')
                    accession_no_hyphens = accession.replace('-', '')
                    # Try: accession.htm, main.htm, etc.
                    for pattern in [f"{accession}.htm", "main.htm", "main.html"]:
                        test_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{pattern}"
                        # Don't actually test, just return the most likely one
                        return test_url
                        
        except Exception as e:
            logger.debug(f"Could not get HTML URL from index: {e}")
        
        return None
    
    def _extract_period_end_date(self, filing_info: Dict[str, Any], filing_content: str = None) -> Optional[str]:
        if filing_content:
            instant_pattern = re.compile(r'<instant>(\d{4}-\d{2}-\d{2})</instant>')
            instants = instant_pattern.findall(filing_content)
            if instants:
                return max(instants)
        description = filing_info.get('description', '')
        if description:
            date_match = re.search(r'(\d{8})', description)
            if date_match:
                date_str = date_match.group(1)
                try:
                    date_obj = datetime.strptime(date_str, '%Y%m%d')
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    pass
        return None
    
    def _get_company_name(self, ticker: str) -> str:
        try:
            from bdc_config import get_bdc_by_ticker
            bdc = get_bdc_by_ticker(ticker)
            if bdc:
                return bdc.get('name', ticker)
        except:
            pass
        return ticker
    
    def save_historical_csv(
        self,
        investments: List[Dict[str, Any]],
        ticker: str,
        output_dir: str = "output"
    ) -> str:
        if not investments:
            logger.warning("No investments to save")
            return None
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_dir)
        os.makedirs(output_dir, exist_ok=True)
        company_name = self._get_company_name(ticker)
        safe_name = company_name.replace(' ', '_').replace(',', '')
        output_file = os.path.join(output_dir, f"{ticker}_{safe_name}_historical_investments.csv")
        fieldnames = [
            'reporting_period', 'filing_date', 'accession_number',
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
            'interest_rate', 'reference_rate', 'spread',
            'commitment_limit', 'undrawn_commitment', 'floor_rate', 'pik_rate',
            'shares_units', 'percent_net_assets', 'currency',
            'geographic_location', 'credit_rating', 'payment_status'
        ]
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for inv in investments:
                row = {k: inv.get(k, '') for k in fieldnames}
                writer.writerow(row)
        logger.info(f"Saved {len(investments)} historical investments to {output_file}")
        return output_file


def extract_historical_for_ticker(
    ticker: str,
    parser_module_name: str = None,
    years_back: int = 5,
    output_dir: str = "output"
) -> Optional[str]:
    """
    Convenience function to extract historical investments for a single ticker.
    
    Args:
        ticker: BDC ticker symbol
        parser_module_name: Optional parser module name
        years_back: Number of years to look back
        output_dir: Output directory for CSV
        
    Returns:
        Path to saved CSV file, or None if failed
    """
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_dir)

    extractor = HistoricalInvestmentExtractor()
    
    try:
        investments = extractor.extract_historical_investments(
            ticker=ticker,
            parser_module_name=parser_module_name,
            years_back=years_back
        )
        
        if investments:
            return extractor.save_historical_csv(investments, ticker, output_dir)
        else:
            logger.warning(f"No investments extracted for {ticker}")
            return None
            
    except Exception as e:
        logger.error(f"Error extracting historical investments for {ticker}: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Example usage
    ticker = "GLAD"
    parser_module = "glad_parser"
    
    csv_path = extract_historical_for_ticker(
        ticker=ticker,
        parser_module_name=parser_module,
        years_back=3
    )
    
    if csv_path:
        print(f"✅ Successfully extracted historical investments for {ticker}")
        print(f"   Saved to: {csv_path}")
    else:
        print(f"❌ Failed to extract historical investments for {ticker}")

