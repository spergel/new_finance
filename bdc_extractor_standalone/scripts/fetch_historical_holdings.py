#!/usr/bin/env python3
"""
Fetch historical 10-Q and 10-K filings and extract holdings for quarterly vs annual comparisons.

This script:
1. Fetches the last 4 quarters (10-Q filings)
2. Fetches the last 2 annual filings (10-K filings)
3. Extracts holdings from each filing using the appropriate parser
4. Saves holdings as CSV and JSON files with period identifiers
"""

import os
import sys
import json
import csv
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import importlib
import traceback

ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(ROOT, 'output')
PUBLIC_DATA_DIR = os.path.join(ROOT, 'frontend', 'public', 'data')

sys.path.insert(0, ROOT)

from sec_api_client import SECAPIClient
from bdc_config import BDC_UNIVERSE

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def get_historical_filings(sec_client: SECAPIClient, ticker: str, form_type: str, years_back: int = 2) -> List[Dict[str, Any]]:
    """Get historical filings of a specific type (10-Q or 10-K)."""
    cik = sec_client.get_cik(ticker)
    if not cik:
        logger.warning(f"Could not find CIK for {ticker}")
        return []
    
    try:
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        response = requests.get(submissions_url, headers=sec_client.headers)
        response.raise_for_status()
        submissions = response.json()
        recent_filings = submissions['filings']['recent']
        
        # Set date range
        end_datetime = datetime.now()
        start_datetime = end_datetime - timedelta(days=years_back * 365)
        
        # Find all filings of the specified type
        filings = []
        for i, form in enumerate(recent_filings['form']):
            if form == form_type:
                filing_date_str = recent_filings['filingDate'][i]
                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d')
                
                # Check if within date range
                if filing_date < start_datetime or filing_date > end_datetime:
                    continue
                
                accession = recent_filings['accessionNumber'][i]
                accession_no_hyphens = accession.replace('-', '')
                
                filing_info = {
                    'form': form,
                    'date': filing_date_str,
                    'accession': accession,
                    'description': recent_filings['primaryDocument'][i],
                    'index_url': f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}-index.html",
                    'period_end_date': None  # Will be extracted from filing if available
                }
                filings.append(filing_info)
        
        # Sort by date (most recent first)
        filings.sort(key=lambda x: x['date'], reverse=True)
        
        logger.info(f"Found {len(filings)} {form_type} filings for {ticker} in the last {years_back} years")
        return filings
        
    except Exception as e:
        logger.error(f"Error fetching historical {form_type} filings for {ticker}: {e}")
        return []


def get_parser_for_ticker(ticker: str):
    """Get the parser module for a ticker."""
    ticker_lower = ticker.lower()
    parser_name = f"{ticker_lower}_parser"
    
    try:
        parser_module = importlib.import_module(parser_name)
        # Look for extractor class (usually named like HTGCExtractor, PSECExtractor, etc.)
        extractor_class = None
        for attr_name in dir(parser_module):
            if attr_name.endswith('Extractor') and not attr_name.startswith('_'):
                extractor_class = getattr(parser_module, attr_name)
                break
        
        if extractor_class:
            return extractor_class()
        else:
            logger.warning(f"No extractor class found in {parser_name}")
            return None
    except ImportError as e:
        logger.warning(f"Could not import {parser_name}: {e}")
        return None


def extract_holdings_from_filing(extractor, ticker: str, filing_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract holdings from a single filing."""
    try:
        # Try to extract using the extractor's standard method
        if hasattr(extractor, 'extract_from_url'):
            # Some extractors take URL directly
            result = extractor.extract_from_url(filing_info['index_url'], ticker, filing_info.get('accession'))
        elif hasattr(extractor, 'extract_from_html_url'):
            # Get the main HTML document URL - look for the main filing document
            sec_client = SECAPIClient()
            documents = sec_client.get_documents_from_index(filing_info['index_url'])
            
            # Find main HTML document (not exhibits/excluded files)
            # Priority: 1) main filing (ticker-YYYYMMDD.htm), 2) any .htm that's not an exhibit
            main_html = None
            ticker_lower = ticker.lower()
            
            # First, try to find main filing document (pattern: ticker-YYYYMMDD.htm)
            for doc in documents:
                if doc.filename and doc.filename.lower().endswith('.htm'):
                    fn_lower = doc.filename.lower()
                    # Skip exhibits and excluded documents
                    if 'ex-' in fn_lower or 'exx' in fn_lower or 'exhibit' in fn_lower:
                        continue
                    # Prefer documents that start with ticker
                    if fn_lower.startswith(ticker_lower):
                        main_html = doc
                        break
            
            # If not found, get first .htm that's not an exhibit
            if not main_html:
                for doc in documents:
                    if doc.filename and doc.filename.lower().endswith('.htm'):
                        fn_lower = doc.filename.lower()
                        if 'ex-' not in fn_lower and 'exx' not in fn_lower and 'exhibit' not in fn_lower:
                            main_html = doc
                            break
            
            if main_html:
                cik = sec_client.get_cik(ticker)
                logger.info(f"Using HTML document: {main_html.filename}")
                result = extractor.extract_from_html_url(main_html.url, ticker, cik)
            else:
                logger.warning(f"No main HTML document found for {filing_info['index_url']}")
                return None
        elif hasattr(extractor, 'extract_from_ticker'):
            # Some extractors fetch their own filing
            # We need to modify them to use our specific filing
            logger.warning(f"Extractor for {ticker} uses extract_from_ticker - may not work with specific filing")
            return None
        else:
            logger.warning(f"Extractor for {ticker} doesn't have a recognized extraction method")
            return None
        
        if result and isinstance(result, dict):
            # Add filing metadata
            result['filing_date'] = filing_info['date']
            result['accession_number'] = filing_info['accession']
            result['form_type'] = filing_info['form']
            return result
        else:
            logger.warning(f"Extraction returned unexpected result type: {type(result)}")
            return None
            
    except Exception as e:
        logger.error(f"Error extracting holdings from {filing_info['index_url']}: {e}")
        logger.debug(traceback.format_exc())
        return None


def save_holdings_to_csv(ticker: str, holdings_data: Dict[str, Any], period: str, form_type: str):
    """Save holdings to CSV file."""
    # Try different possible structures
    investments = holdings_data.get('investments', [])
    if not investments:
        # Some parsers might return a list directly
        if isinstance(holdings_data, list):
            investments = holdings_data
        elif 'total_investments' in holdings_data:
            # Some parsers return summary with investments elsewhere
            investments = holdings_data.get('investments', [])
    
    if not investments:
        logger.warning(f"No investments found in holdings data for {ticker} period {period}")
        return None
    
    # Convert investment objects to dictionaries if needed
    investments_dicts = []
    for inv in investments:
        if isinstance(inv, dict):
            investments_dicts.append(inv)
        elif hasattr(inv, '__dict__'):
            # Convert dataclass/object to dict
            investments_dicts.append(vars(inv))
        elif hasattr(inv, '_asdict'):
            # Namedtuple
            investments_dicts.append(inv._asdict())
        else:
            logger.warning(f"Unknown investment type: {type(inv)}")
            continue
    
    if not investments_dicts:
        logger.warning(f"No valid investments to save for {ticker} period {period}")
        return None
    
    # Determine CSV filename
    period_suffix = period.replace('-', '_')
    form_suffix = form_type.replace('-', '_')
    csv_filename = f"{ticker}_{period_suffix}_{form_suffix}_investments.csv"
    csv_path = os.path.join(OUTPUT_DIR, csv_filename)
    
    # Get fieldnames from first investment
    fieldnames = list(investments_dicts[0].keys())
    
    # Write CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for inv in investments_dicts:
            # Convert None to empty string for CSV
            row = {k: (v if v is not None else '') for k, v in inv.items()}
            writer.writerow(row)
    
    logger.info(f"Saved {len(investments)} investments to {csv_path}")
    return csv_path


def save_holdings_to_json(ticker: str, holdings_data: Dict[str, Any], period: str):
    """Save holdings to JSON file in public data directory."""
    ticker_dir = os.path.join(PUBLIC_DATA_DIR, ticker.upper())
    os.makedirs(ticker_dir, exist_ok=True)
    
    # Determine form type for filename
    form_type = holdings_data.get('form_type', '10-Q')
    form_suffix = form_type.replace('-', '_')
    
    json_filename = f"investments_{period}_{form_suffix}.json"
    json_path = os.path.join(ticker_dir, json_filename)
    
    # Convert investments to dicts for JSON serialization
    investments = holdings_data.get('investments', [])
    investments_dicts = []
    for inv in investments:
        if isinstance(inv, dict):
            investments_dicts.append(inv)
        elif hasattr(inv, '__dict__'):
            investments_dicts.append(vars(inv))
        elif hasattr(inv, '_asdict'):
            investments_dicts.append(inv._asdict())
        else:
            # Try to serialize as-is (might work for simple types)
            investments_dicts.append(inv)
    
    # Prepare JSON structure
    json_data = {
        'ticker': ticker.upper(),
        'name': holdings_data.get('company_name'),
        'period': period,
        'filing_date': holdings_data.get('filing_date'),
        'accession_number': holdings_data.get('accession_number'),
        'form_type': form_type,
        'investments': investments_dicts,
        'generated_at': datetime.now().isoformat() + 'Z'
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)
    
    logger.info(f"Saved holdings JSON to {json_path}")
    return json_path


def process_ticker(ticker: str, name: str):
    """Process a single ticker: fetch historical filings and extract holdings."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing {ticker} ({name})")
    logger.info(f"{'='*60}")
    
    sec_client = SECAPIClient()
    extractor = get_parser_for_ticker(ticker)
    
    if not extractor:
        logger.warning(f"Could not get extractor for {ticker}, skipping")
        return
    
    # Fetch last 4 quarters (10-Q)
    logger.info(f"\nFetching 10-Q filings for {ticker}...")
    quarterly_filings = get_historical_filings(sec_client, ticker, "10-Q", years_back=2)
    quarterly_filings = quarterly_filings[:4]  # Limit to last 4 quarters
    
    # Fetch last 2 annual filings (10-K)
    logger.info(f"\nFetching 10-K filings for {ticker}...")
    annual_filings = get_historical_filings(sec_client, ticker, "10-K", years_back=2)
    annual_filings = annual_filings[:2]  # Limit to last 2 annual
    
    all_filings = quarterly_filings + annual_filings
    
    if not all_filings:
        logger.warning(f"No historical filings found for {ticker}")
        return
    
    logger.info(f"Found {len(all_filings)} total filings ({len(quarterly_filings)} 10-Q, {len(annual_filings)} 10-K)")
    
    # Extract holdings from each filing
    extracted_count = 0
    for filing_info in all_filings:
        logger.info(f"\nExtracting from {filing_info['form']} filed {filing_info['date']}...")
        
        holdings_data = extract_holdings_from_filing(extractor, ticker, filing_info)
        
        if holdings_data:
            # Use filing date as period identifier (or try to extract period end date)
            period = filing_info['date']
            
            # Save to CSV
            csv_path = save_holdings_to_csv(ticker, holdings_data, period, filing_info['form'])
            
            # Save to JSON
            json_path = save_holdings_to_json(ticker, holdings_data, period)
            
            extracted_count += 1
        else:
            logger.warning(f"Failed to extract holdings from {filing_info['form']} {filing_info['date']}")
    
    logger.info(f"\n✅ Completed {ticker}: extracted {extracted_count}/{len(all_filings)} filings")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch historical 10-Q and 10-K filings and extract holdings')
    parser.add_argument('--ticker', type=str, help='Process specific ticker only')
    parser.add_argument('--years-back', type=int, default=2, help='Years to look back for filings (default: 2)')
    
    args = parser.parse_args()
    
    # Convert BDC_UNIVERSE list to dict for easier lookup
    bdc_dict = {bdc['ticker'].upper(): bdc['name'] for bdc in BDC_UNIVERSE if 'ticker' in bdc and 'name' in bdc}
    
    if args.ticker:
        # Process single ticker
        ticker_upper = args.ticker.upper()
        if ticker_upper in bdc_dict:
            name = bdc_dict[ticker_upper]
            process_ticker(ticker_upper, name)
        else:
            logger.error(f"Ticker {args.ticker} not found in BDC_UNIVERSE")
            return 1
    else:
        # Process all tickers
        logger.info(f"Processing all {len(bdc_dict)} BDCs...")
        for ticker, name in bdc_dict.items():
            try:
                process_ticker(ticker, name)
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                logger.debug(traceback.format_exc())
                continue
    
    logger.info("\n✅ All done!")
    return 0


if __name__ == "__main__":
    exit(main())

