#!/usr/bin/env python3
"""
Batch extractor for insider trading and ownership data for all BDCs.

This script extracts insider/ownership data for all BDCs and saves to JSON files.
Can be run standalone or integrated into daily_update.py
"""

import os
import sys
import logging
import glob
from typing import List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from insider_ownership_extractor import InsiderOwnershipExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_bdc_tickers() -> List[str]:
    """Find all BDC tickers from parser files."""
    parser_dir = os.path.dirname(__file__)
    tickers = set()
    
    parser_files = glob.glob(os.path.join(parser_dir, '*_parser.py'))
    custom_files = glob.glob(os.path.join(parser_dir, '*_custom_parser.py'))
    
    all_files = parser_files + custom_files
    
    for parser_file in all_files:
        basename = os.path.basename(parser_file)
        # Skip utility files
        if basename in ['insider_ownership_extractor.py', 'extract_insider_ownership.py',
                       'daily_update.py', 'run_all_parsers.py', 'sec_api_client.py',
                       'standardization.py']:
            continue
        
        # Extract ticker from filename
        # Format: ticker_parser.py or ticker_custom_parser.py
        parts = basename.replace('_custom_parser.py', '').replace('_parser.py', '').split('_')
        if parts:
            ticker = parts[0].upper()
            if len(ticker) >= 2 and ticker.isalpha():
                tickers.add(ticker)
    
    return sorted(list(tickers))


def main():
    """Extract insider/ownership data for all BDCs."""
    logger.info("=" * 80)
    logger.info("INSIDER/OWNERSHIP DATA EXTRACTION")
    logger.info("=" * 80)
    
    # Get output directory
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    # Find all BDC tickers
    tickers = find_bdc_tickers()
    logger.info(f"Found {len(tickers)} BDC tickers")
    
    # Initialize extractor
    extractor = InsiderOwnershipExtractor()
    
    # Extract data for each ticker
    successful = []
    failed = []
    
    for ticker in tickers:
        try:
            logger.info(f"\nProcessing {ticker}...")
            data = extractor.extract_for_ticker(ticker, days_back=365)
            extractor.save_to_json(data, output_dir)
            
            successful.append({
                'ticker': ticker,
                'transactions': len(data['insider_transactions']),
                'ownership': len(data['ownership'])
            })
            
            logger.info(f"[OK] {ticker}: {len(data['insider_transactions'])} transactions, "
                       f"{len(data['ownership'])} ownership entries")
        
        except Exception as e:
            logger.error(f"[ERROR] {ticker}: {e}")
            failed.append({'ticker': ticker, 'error': str(e)})
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("EXTRACTION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Successful: {len(successful)}")
    logger.info(f"Failed: {len(failed)}")
    
    if successful:
        total_transactions = sum(s['transactions'] for s in successful)
        total_ownership = sum(s['ownership'] for s in successful)
        logger.info(f"\nTotal insider transactions: {total_transactions}")
        logger.info(f"Total ownership entries: {total_ownership}")
    
    if failed:
        logger.info("\nFailed extractions:")
        for f in failed:
            logger.info(f"  {f['ticker']}: {f['error']}")


if __name__ == '__main__':
    main()

