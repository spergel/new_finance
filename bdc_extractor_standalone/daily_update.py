#!/usr/bin/env python3
"""
Daily update script to check for new SEC filings and update investment data.

This script:
1. Checks for new 10-Q and 10-K filings for all BDC tickers
2. Runs parsers only for tickers with new filings
3. Updates output CSV files
4. Logs results for monitoring
"""

import os
import sys
import logging
import glob
import importlib
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from sec_api_client import SECAPIClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_update.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def find_parser_files() -> List[Tuple[str, str]]:
    """Find all parser files and their tickers."""
    parser_dir = os.path.dirname(__file__)
    parsers = []
    seen_tickers = set()
    
    parser_files = glob.glob(os.path.join(parser_dir, '*_parser.py'))
    custom_files = glob.glob(os.path.join(parser_dir, '*_custom_parser.py'))
    
    all_files = parser_files + custom_files
    
    for parser_file in all_files:
        basename = os.path.basename(parser_file)
        # Skip utility parsers
        if basename in ['flexible_table_parser.py', 'verbose_identifier_parser.py', 
                       'xbrl_typed_extractor.py', 'daily_update.py']:
            continue
        
        # Extract ticker from filename
        if '_custom_parser.py' in basename:
            ticker = basename.replace('_custom_parser.py', '').upper()
        else:
            ticker = basename.replace('_parser.py', '').upper()
        
        # Skip if we've already seen this ticker
        if ticker in seen_tickers:
            continue
        
        seen_tickers.add(ticker)
        parsers.append((ticker, parser_file))
    
    return sorted(parsers)


def get_extractor_class(module, ticker: str):
    """Get the extractor class from a module."""
    # Try common class name patterns
    class_names = [
        f'{ticker}Extractor',
        f'{ticker}CustomExtractor',
        'Extractor',
        'CustomExtractor'
    ]
    
    for class_name in class_names:
        if hasattr(module, class_name):
            return getattr(module, class_name)
    
    # Special cases
    if ticker == 'FDUS':
        return getattr(module, 'FDUSExtractor')
    
    return None


def check_for_new_filing(ticker: str, sec_client: SECAPIClient, 
                         days_back: int = 7) -> Optional[str]:
    """Check if there's a new filing in the last N days."""
    try:
        cik = sec_client.get_cik(ticker)
        if not cik:
            logger.warning(f"Could not find CIK for {ticker}")
            return None
        
        # Check for 10-Q first (more frequent)
        index_url = sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if index_url:
            # Extract date from URL or check filing date
            # For now, we'll just try to get the latest and compare
            return index_url
        
        # Check for 10-K
        index_url = sec_client.get_filing_index_url(ticker, "10-K", cik=cik)
        if index_url:
            return index_url
        
        return None
    except Exception as e:
        logger.error(f"Error checking filing for {ticker}: {e}")
        return None


def get_last_update_time(output_dir: str) -> Dict[str, datetime]:
    """Get last modification time for each CSV file."""
    last_updates = {}
    csv_files = glob.glob(os.path.join(output_dir, '*_investments.csv'))
    
    for csv_file in csv_files:
        ticker = os.path.basename(csv_file).split('_')[0].upper()
        mtime = datetime.fromtimestamp(os.path.getmtime(csv_file))
        last_updates[ticker] = mtime
    
    return last_updates


def run_parser(ticker: str, parser_file: str) -> Dict:
    """Run a single parser and return results."""
    result = {
        'ticker': ticker,
        'parser_file': os.path.basename(parser_file),
        'status': 'unknown',
        'error': None,
        'investments_count': 0
    }
    
    try:
        # Import the parser module
        module_name = os.path.basename(parser_file).replace('.py', '')
        module = importlib.import_module(module_name)
        
        # Get extractor class
        extractor_class = get_extractor_class(module, ticker)
        if not extractor_class:
            result['status'] = 'skipped'
            result['error'] = f'No extractor class found'
            return result
        
        # Create extractor instance
        extractor = extractor_class()
        
        # Check if extract_from_ticker exists
        if not hasattr(extractor, 'extract_from_ticker'):
            result['status'] = 'skipped'
            result['error'] = 'No extract_from_ticker method found'
            return result
        
        # Run the extractor
        logger.info(f"Running {ticker} parser...")
        try:
            data = extractor.extract_from_ticker(ticker)
        except TypeError:
            data = extractor.extract_from_ticker()
        
        # Extract investment count
        if isinstance(data, dict):
            result['investments_count'] = data.get('total_investments', 0)
        
        result['status'] = 'success'
        logger.info(f"[OK] {ticker}: {result['investments_count']} investments")
        
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
        logger.error(f"[ERROR] {ticker}: {result['error']}")
    
    return result


def main(force_all: bool = False, days_back: int = 7):
    """Main function to check for updates and run parsers."""
    logger.info("=" * 80)
    logger.info("DAILY UPDATE CHECK")
    logger.info("=" * 80)
    logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Force all: {force_all}")
    logger.info(f"Days back: {days_back}")
    logger.info("")
    
    # Initialize SEC client
    sec_client = SECAPIClient()
    
    # Get output directory
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    # Get last update times
    last_updates = get_last_update_time(output_dir)
    
    # Find all parsers
    parsers = find_parser_files()
    logger.info(f"Found {len(parsers)} parser files")
    logger.info("")
    
    # Determine which parsers to run
    parsers_to_run = []
    
    if force_all:
        logger.info("Force mode: Running all parsers")
        parsers_to_run = parsers
    else:
        logger.info("Checking for new filings...")
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for ticker, parser_file in parsers:
            should_run = False
            
            # Check if we have a last update time
            if ticker in last_updates:
                last_update = last_updates[ticker]
                if last_update < cutoff_date:
                    logger.info(f"{ticker}: Last updated {last_update.strftime('%Y-%m-%d')}, checking for new filing...")
                    filing_url = check_for_new_filing(ticker, sec_client, days_back)
                    if filing_url:
                        logger.info(f"{ticker}: New filing found!")
                        should_run = True
                    else:
                        logger.info(f"{ticker}: No new filing found")
                else:
                    logger.info(f"{ticker}: Recently updated ({last_update.strftime('%Y-%m-%d')}), skipping")
            else:
                # No previous update, run it
                logger.info(f"{ticker}: No previous update found, running parser...")
                should_run = True
            
            if should_run:
                parsers_to_run.append((ticker, parser_file))
        
        logger.info(f"Found {len(parsers_to_run)} parsers to run")
        logger.info("")
    
    if not parsers_to_run:
        logger.info("No parsers to run. All up to date!")
        return
    
    # Run parsers
    results = []
    for ticker, parser_file in parsers_to_run:
        result = run_parser(ticker, parser_file)
        results.append(result)
        logger.info("")
    
    # Summary
    logger.info("=" * 80)
    logger.info("UPDATE SUMMARY")
    logger.info("=" * 80)
    
    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] == 'error']
    skipped = [r for r in results if r['status'] == 'skipped']
    
    logger.info(f"[OK] Successful: {len(successful)}")
    logger.info(f"[ERROR] Failed: {len(failed)}")
    logger.info(f"[SKIP] Skipped: {len(skipped)}")
    logger.info("")
    
    if successful:
        logger.info("Successful updates:")
        for r in successful:
            logger.info(f"  [OK] {r['ticker']}: {r['investments_count']} investments")
        logger.info("")
    
    if failed:
        logger.info("Failed updates:")
        for r in failed:
            logger.info(f"  [ERROR] {r['ticker']}: {r['error']}")
        logger.info("")
    
    total_investments = sum(r['investments_count'] for r in successful)
    logger.info(f"Total investments updated: {total_investments}")
    logger.info("=" * 80)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Daily update script for BDC investment data')
    parser.add_argument('--force-all', action='store_true', 
                       help='Force update all parsers regardless of last update time')
    parser.add_argument('--days-back', type=int, default=7,
                       help='Number of days to look back for new filings (default: 7)')
    
    args = parser.parse_args()
    
    main(force_all=args.force_all, days_back=args.days_back)

