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
import importlib

from sec_api_client import SECAPIClient

logger = logging.getLogger(__name__)


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
        
        # Get historical 10-Q filings
        filings = self.sec_client.get_historical_10q_filings(
            ticker, years_back=years_back, start_date=start_date, end_date=end_date
        )
        
        if not filings:
            logger.warning(f"No historical 10-Q filings found for {ticker}")
            return []
        
        logger.info(f"Found {len(filings)} 10-Q filings for {ticker}")
        
        # Try to get parser for this ticker
        parser = self._get_parser_for_ticker(ticker, parser_module_name)
        if not parser:
            logger.error(f"Could not find parser for {ticker}")
            return []
        
        all_investments = []
        
        # Process each filing
        for filing_info in filings:
            try:
                logger.info(f"Processing filing {filing_info['date']} (accession: {filing_info['accession']})")
                
                # Get the XBRL/text URL from the index
                txt_url = self._get_filing_txt_url(filing_info)
                if not txt_url:
                    logger.warning(f"Could not get text URL for filing {filing_info['accession']}")
                    continue
                
                # Download filing content to extract period end date
                try:
                    filing_response = requests.get(txt_url, headers=self.headers)
                    filing_response.raise_for_status()
                    filing_content = filing_response.text
                except Exception as e:
                    logger.warning(f"Could not download filing content: {e}")
                    filing_content = None
                
                # Extract period end date from filing if possible
                period_end = self._extract_period_end_date(filing_info, filing_content)
                reporting_period = period_end or filing_info['date']
                
                # Extract investments using the parser
                result = parser.extract_from_url(
                    txt_url,
                    self._get_company_name(ticker),
                    self.sec_client.get_cik(ticker)
                )
                
                if result and 'investments' in result:
                    # Add reporting period to each investment
                    for inv in result['investments']:
                        inv['reporting_period'] = reporting_period
                        inv['filing_date'] = filing_info['date']
                        inv['accession_number'] = filing_info['accession']
                    
                    all_investments.extend(result['investments'])
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
        if parser_module_name:
            try:
                module = importlib.import_module(parser_module_name)
                # Try common extractor class names
                for class_name in ['Extractor', f'{ticker}Extractor', f'{ticker.upper()}Extractor']:
                    if hasattr(module, class_name):
                        extractor_class = getattr(module, class_name)
                        return extractor_class(user_agent=self.headers['User-Agent'])
            except ImportError as e:
                logger.warning(f"Could not import parser module {parser_module_name}: {e}")
        
        # Try to infer parser module name from ticker
        parser_module_name = f"{ticker.lower()}_parser"
        try:
            module = importlib.import_module(parser_module_name)
            # Try common extractor class names
            for class_name in ['Extractor', f'{ticker}Extractor', f'{ticker.upper()}Extractor']:
                if hasattr(module, class_name):
                    extractor_class = getattr(module, class_name)
                    return extractor_class(user_agent=self.headers['User-Agent'])
        except ImportError:
            pass
        
        return None
    
    def _get_filing_txt_url(self, filing_info: Dict[str, Any]) -> Optional[str]:
        """Get the .txt URL for a filing from its index URL."""
        index_url = filing_info.get('index_url')
        if not index_url:
            return None
        
        # Extract CIK and accession from index URL
        match = re.search(r'/edgar/data/(\d+)/(\d+)/([\d-]+)-index\.html', index_url)
        if not match:
            return None
        
        cik = match.group(1)
        accession_no_hyphens = match.group(2)
        accession = match.group(3)
        
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
    
    def _extract_period_end_date(self, filing_info: Dict[str, Any], filing_content: str = None) -> Optional[str]:
        """
        Try to extract the period end date from filing metadata or XBRL content.
        
        Args:
            filing_info: Filing metadata dictionary
            filing_content: Optional filing content to parse for period end date
            
        Returns:
            Period end date in YYYY-MM-DD format, or None if not found
        """
        # Try to extract from filing content if available
        if filing_content:
            # Look for period end date in XBRL context instants
            # Pattern: <instant>YYYY-MM-DD</instant>
            instant_pattern = re.compile(r'<instant>(\d{4}-\d{2}-\d{2})</instant>')
            instants = instant_pattern.findall(filing_content)
            
            if instants:
                # Return the latest instant (most recent period end date)
                return max(instants)
        
        # Try to extract from description/filename
        description = filing_info.get('description', '')
        if description:
            # Some filenames contain period end dates like "arcc-20250930.htm"
            date_match = re.search(r'(\d{8})', description)
            if date_match:
                date_str = date_match.group(1)
                try:
                    # Convert YYYYMMDD to YYYY-MM-DD
                    date_obj = datetime.strptime(date_str, '%Y%m%d')
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    pass
        
        # Fallback: return None (will use filing date instead)
        return None
    
    def _get_company_name(self, ticker: str) -> str:
        """Get company name from ticker."""
        # Try to get from bdc_config
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
        """
        Save historical investments to CSV with reporting_period field.
        
        Args:
            investments: List of investment dictionaries
            ticker: BDC ticker symbol
            output_dir: Output directory for CSV file
            
        Returns:
            Path to saved CSV file
        """
        if not investments:
            logger.warning("No investments to save")
            return None
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Determine company name
        company_name = self._get_company_name(ticker)
        safe_name = company_name.replace(' ', '_').replace(',', '')
        output_file = os.path.join(output_dir, f"{ticker}_{safe_name}_historical_investments.csv")
        
        # Standard fieldnames (match existing parser format)
        fieldnames = [
            'reporting_period', 'filing_date', 'accession_number',
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
            'interest_rate', 'reference_rate', 'spread',
            'commitment_limit', 'undrawn_commitment', 'floor_rate', 'pik_rate'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for inv in investments:
                # Ensure all fields are present
                row = {}
                for field in fieldnames:
                    row[field] = inv.get(field, '')
                
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

