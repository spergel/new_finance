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
import json
from datetime import datetime, timedelta, date
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
                         last_update_date: Optional[date] = None) -> Optional[date]:
    """
    Check if there's a new filing more recent than the last update date.
    
    Args:
        ticker: Company ticker symbol
        sec_client: SEC API client instance
        last_update_date: Date of last update (if None, will return latest filing date)
        
    Returns:
        Date of the latest filing if it's newer than last_update_date, None otherwise
    """
    try:
        cik = sec_client.get_cik(ticker)
        if not cik:
            logger.warning(f"Could not find CIK for {ticker}")
            return None
        
        # Get the latest filing date for 10-Q and 10-K
        latest_filing_date = sec_client.get_latest_filing_date(ticker, ["10-Q", "10-K"], cik=cik)
        
        if not latest_filing_date:
            return None
        
        # If no last update date, return the latest filing date
        if last_update_date is None:
            return latest_filing_date
        
        # Return the filing date if it's newer than the last update
        if latest_filing_date > last_update_date:
            return latest_filing_date
        
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


def get_company_name_from_ticker(ticker: str) -> str:
    """Get company name from ticker by reading the CSV filename."""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    csv_files = glob.glob(os.path.join(output_dir, f'{ticker}_*_investments.csv'))
    if csv_files:
        # Extract company name from filename: TICKER_Company_Name_investments.csv
        basename = os.path.basename(csv_files[0])
        parts = basename.replace('_investments.csv', '').split('_', 1)
        if len(parts) > 1:
            return parts[1].replace('_', ' ')
    return ticker

def save_filing_dates(filing_dates: Dict[str, Dict], output_dir: str):
    """Save latest filing dates to JSON file for frontend."""
    filing_info_file = os.path.join(output_dir, 'bdc_filing_dates.json')
    
    # Read existing data if it exists
    existing_data = {}
    if os.path.exists(filing_info_file):
        try:
            with open(filing_info_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read existing filing dates: {e}")
    
    # Update with new data
    existing_data.update(filing_dates)
    
    # Write back to file
    with open(filing_info_file, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved filing dates to {filing_info_file}")

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
    
    # Track latest filing dates for all BDCs
    filing_dates = {}
    
    # Determine which parsers to run
    parsers_to_run = []
    
    if force_all:
        logger.info("Force mode: Running all parsers")
        parsers_to_run = parsers
    else:
        logger.info("Checking for new 10-Q filings...")
        
        for ticker, parser_file in parsers:
            should_run = False
            
            # Always check for new 10-Q filings, regardless of CSV age
            if ticker in last_updates:
                last_update = last_updates[ticker]
                last_update_date = last_update.date()
                
                logger.info(f"{ticker}: Last updated {last_update.strftime('%Y-%m-%d')}, checking for new 10-Q filing...")
                new_filing_date = check_for_new_filing(ticker, sec_client, last_update_date)
                
                # Track latest filing date for this BDC
                if new_filing_date:
                    # Determine actual filing type (10-Q or 10-K)
                    filing_type = '10-Q'
                    q_date = sec_client.get_latest_filing_date(ticker, ["10-Q"])
                    k_date = sec_client.get_latest_filing_date(ticker, ["10-K"])
                    if k_date and (not q_date or k_date > q_date):
                        filing_type = '10-K'
                    elif q_date:
                        filing_type = '10-Q'
                    
                    filing_dates[ticker] = {
                        'ticker': ticker,
                        'company_name': get_company_name_from_ticker(ticker),
                        'latest_filing_date': new_filing_date.isoformat(),
                        'filing_type': filing_type,
                        'last_updated': last_update.isoformat()
                    }
                    logger.info(f"{ticker}: New {filing_type} filing found (date: {new_filing_date}), updating.")
                    should_run = True
                else:
                    # Still track the latest filing date even if no update needed
                    q_date = sec_client.get_latest_filing_date(ticker, ["10-Q"])
                    k_date = sec_client.get_latest_filing_date(ticker, ["10-K"])
                    latest_filing_date = None
                    filing_type = '10-Q'
                    if k_date and (not q_date or k_date > q_date):
                        latest_filing_date = k_date
                        filing_type = '10-K'
                    elif q_date:
                        latest_filing_date = q_date
                        filing_type = '10-Q'
                    
                    if latest_filing_date:
                        filing_dates[ticker] = {
                            'ticker': ticker,
                            'company_name': get_company_name_from_ticker(ticker),
                            'latest_filing_date': latest_filing_date.isoformat(),
                            'filing_type': filing_type,
                            'last_updated': last_update.isoformat()
                        }
                    logger.info(f"{ticker}: No new 10-Q filings (latest filing date is not newer than {last_update_date})")
            else:
                # No previous update, check if there's any filing available
                logger.info(f"{ticker}: No previous update found, checking for 10-Q filings...")
                latest_filing_date = check_for_new_filing(ticker, sec_client, None)
                if latest_filing_date:
                    # Determine actual filing type
                    q_date = sec_client.get_latest_filing_date(ticker, ["10-Q"])
                    k_date = sec_client.get_latest_filing_date(ticker, ["10-K"])
                    filing_type = '10-Q'
                    if k_date and (not q_date or k_date > q_date):
                        filing_type = '10-K'
                        latest_filing_date = k_date
                    elif q_date:
                        filing_type = '10-Q'
                        latest_filing_date = q_date
                    
                    filing_dates[ticker] = {
                        'ticker': ticker,
                        'company_name': get_company_name_from_ticker(ticker),
                        'latest_filing_date': latest_filing_date.isoformat(),
                        'filing_type': filing_type,
                        'last_updated': None
                    }
                    logger.info(f"{ticker}: Found {filing_type} filing (date: {latest_filing_date}), running parser...")
                    should_run = True
                else:
                    # Still track if there's any filing available
                    q_date = sec_client.get_latest_filing_date(ticker, ["10-Q"])
                    k_date = sec_client.get_latest_filing_date(ticker, ["10-K"])
                    latest_filing_date = None
                    filing_type = '10-Q'
                    if k_date and (not q_date or k_date > q_date):
                        latest_filing_date = k_date
                        filing_type = '10-K'
                    elif q_date:
                        latest_filing_date = q_date
                        filing_type = '10-Q'
                    
                    if latest_filing_date:
                        filing_dates[ticker] = {
                            'ticker': ticker,
                            'company_name': get_company_name_from_ticker(ticker),
                            'latest_filing_date': latest_filing_date.isoformat(),
                            'filing_type': filing_type,
                            'last_updated': None
                        }
                    logger.info(f"{ticker}: No 10-Q filings found, skipping")
            
            if should_run:
                parsers_to_run.append((ticker, parser_file))
        
        logger.info(f"Found {len(parsers_to_run)} parsers to run")
        logger.info("")
    
    # Run parsers if any need updating
    results = []
    if parsers_to_run:
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
    else:
        logger.info("No parsers to run. All up to date!")
    
    # Also collect filing dates for BDCs that were updated during this run
    for result in results:
        if result['status'] == 'success' and result['ticker'] not in filing_dates:
            ticker = result['ticker']
            q_date = sec_client.get_latest_filing_date(ticker, ["10-Q"])
            k_date = sec_client.get_latest_filing_date(ticker, ["10-K"])
            latest_filing_date = None
            filing_type = '10-Q'
            if k_date and (not q_date or k_date > q_date):
                latest_filing_date = k_date
                filing_type = '10-K'
            elif q_date:
                latest_filing_date = q_date
                filing_type = '10-Q'
            
            if latest_filing_date:
                filing_dates[ticker] = {
                    'ticker': ticker,
                    'company_name': get_company_name_from_ticker(ticker),
                    'latest_filing_date': latest_filing_date.isoformat(),
                    'filing_type': filing_type,
                    'last_updated': datetime.now().isoformat()
                }
    
    # Save filing dates for frontend (always save to track all BDCs)
    save_filing_dates(filing_dates, output_dir)
    logger.info(f"Updated filing dates for {len(filing_dates)} BDCs")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Daily update script for BDC investment data')
    parser.add_argument('--force-all', action='store_true', 
                       help='Force update all parsers regardless of last update time')
    parser.add_argument('--days-back', type=int, default=7,
                       help='Number of days to look back for new filings (default: 7)')
    
    args = parser.parse_args()
    
    main(force_all=args.force_all, days_back=args.days_back)

