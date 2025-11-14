#!/usr/bin/env python3
"""
Extract XBRL investment data for specified BDC tickers.

This script extracts raw XBRL investment data to understand what's available
before redoing the parsers.
"""

import os
import re
import logging
import csv
from typing import List, Dict, Optional
from collections import defaultdict
import requests
from bs4 import BeautifulSoup

from sec_api_client import SECAPIClient
from xbrl_typed_extractor import TypedMemberExtractor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Tickers to extract
TICKERS = [
    'ARCC', 'BCSF', 'CGBD', 'CSWC', 'FDUS', 'FSK', 'GBDC', 'GLAD', 'MAIN',
    'MRCC', 'MSDL', 'MSIF', 'NCDL', 'NMFC', 'OBDC', 'OFS', 'OXSQ', 'PFX',
    'PSEC', 'RAND', 'SCM', 'SSSS', 'TPVG', 'TRIN', 'WHF'
]

def extract_xbrl_investments(ticker: str) -> Dict:
    """Extract XBRL investment data for a ticker."""
    logger.info(f"Extracting XBRL investments for {ticker}")
    
    sec_client = SECAPIClient()
    extractor = TypedMemberExtractor()
    
    # Get CIK
    cik = sec_client.get_cik(ticker)
    if not cik:
        logger.error(f"Could not find CIK for {ticker}")
        return {'ticker': ticker, 'error': 'CIK not found', 'investments': []}
    
    # Get latest 10-Q
    index_url = sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
    if not index_url:
        logger.error(f"Could not find 10-Q filing for {ticker}")
        return {'ticker': ticker, 'error': '10-Q not found', 'investments': []}
    
    # Get XBRL URL
    match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
    if not match:
        logger.error(f"Could not parse accession for {ticker}")
        return {'ticker': ticker, 'error': 'Could not parse accession', 'investments': []}
    
    accession = match.group(1)
    accession_no_hyphens = accession.replace('-', '')
    txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
    
    logger.info(f"Downloading XBRL from: {txt_url}")
    
    try:
        # Extract using TypedMemberExtractor
        result = extractor.extract_from_url(txt_url, f"{ticker} Company", cik)
        
        logger.info(f"Found {result.total_investments} investments for {ticker}")
        
        return {
            'ticker': ticker,
            'cik': cik,
            'accession': accession,
            'total_investments': result.total_investments,
            'investments': result.investments,
            'filing_date': result.filing_date,
            'error': None
        }
    except Exception as e:
        logger.error(f"Error extracting {ticker}: {e}", exc_info=True)
        return {'ticker': ticker, 'error': str(e), 'investments': []}

def save_xbrl_data(results: List[Dict], output_dir: str):
    """Save XBRL extraction results to CSV files."""
    os.makedirs(output_dir, exist_ok=True)
    
    for result in results:
        if result.get('error'):
            logger.warning(f"Skipping {result['ticker']} due to error: {result['error']}")
            continue
        
        ticker = result['ticker']
        investments = result.get('investments', [])
        
        if not investments:
            logger.warning(f"No investments found for {ticker}")
            continue
        
        output_file = os.path.join(output_dir, f'{ticker}_xbrl_raw.csv')
        
        # Get all unique field names from investments
        fieldnames = set()
        for inv in investments:
            fieldnames.update(inv.keys())
        
        fieldnames = sorted(list(fieldnames))
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for inv in investments:
                # Convert all values to strings, handle None
                row = {k: (str(v) if v is not None else '') for k, v in inv.items()}
                writer.writerow(row)
        
        logger.info(f"Saved {len(investments)} investments to {output_file}")

def main():
    """Extract XBRL data for all tickers."""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'xbrl_raw')
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    for ticker in TICKERS:
        result = extract_xbrl_investments(ticker)
        results.append(result)
    
    # Save results
    save_xbrl_data(results, output_dir)
    
    # Print summary
    print("\n" + "=" * 80)
    print("XBRL EXTRACTION SUMMARY")
    print("=" * 80)
    
    successful = [r for r in results if not r.get('error') and r.get('total_investments', 0) > 0]
    failed = [r for r in results if r.get('error')]
    empty = [r for r in results if not r.get('error') and r.get('total_investments', 0) == 0]
    
    print(f"\nSuccessful: {len(successful)}")
    for r in successful:
        print(f"  {r['ticker']}: {r['total_investments']} investments")
    
    if failed:
        print(f"\nFailed: {len(failed)}")
        for r in failed:
            print(f"  {r['ticker']}: {r.get('error', 'Unknown error')}")
    
    if empty:
        print(f"\nEmpty (no investments found): {len(empty)}")
        for r in empty:
            print(f"  {r['ticker']}")
    
    total_investments = sum(r.get('total_investments', 0) for r in successful)
    print(f"\nTotal investments extracted: {total_investments}")
    print("=" * 80)

if __name__ == '__main__':
    main()

