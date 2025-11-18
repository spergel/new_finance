#!/usr/bin/env python3
"""
Backfill Historical Data for All BDCs

This script extracts historical investment and financial data for all BDCs
and generates static JSON files for the frontend.

Usage:
    python scripts/backfill_all_data.py --years-back 5
    python scripts/backfill_all_data.py --ticker ARCC --ticker OBDC
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.generate_static_data import main as generate_static_data_main
from bdc_config import BDC_UNIVERSE, get_bdc_by_ticker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill historical data for all BDCs"
    )
    parser.add_argument(
        '--years-back',
        type=int,
        default=5,
        help='Number of years to look back (default: 5)'
    )
    parser.add_argument(
        '--ticker',
        action='append',
        help='Specific ticker(s) to process (can be used multiple times)'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip tickers that already have data files'
    )
    parser.add_argument(
        '--max-tickers',
        type=int,
        help='Maximum number of tickers to process (useful for testing)'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=5,
        help='Number of parallel workers (default: 5, increase for faster processing but watch SEC rate limits)'
    )
    
    args = parser.parse_args()
    
    logger.info("="*80)
    logger.info("BDC HISTORICAL DATA BACKFILL")
    logger.info("="*80)
    logger.info(f"Years back: {args.years_back}")
    logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    
    # Determine which tickers to process
    if args.ticker:
        tickers = [t.upper() for t in args.ticker]
        logger.info(f"Processing {len(tickers)} specified ticker(s): {', '.join(tickers)}")
    else:
        tickers = [bdc['ticker'] for bdc in BDC_UNIVERSE]
        logger.info(f"Processing all {len(tickers)} BDCs")
    
    # Limit if requested
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]
        logger.info(f"Limited to first {len(tickers)} tickers")
    
    # Check for existing data if skip flag is set
    if args.skip_existing:
        from scripts.generate_static_data import PUBLIC_DATA_DIR
        skipped = []
        remaining = []
        
        for ticker in tickers:
            ticker_dir = os.path.join(PUBLIC_DATA_DIR, ticker.upper())
            periods_file = os.path.join(ticker_dir, 'periods.json')
            
            if os.path.exists(periods_file):
                skipped.append(ticker)
            else:
                remaining.append(ticker)
        
        if skipped:
            logger.info(f"Skipping {len(skipped)} tickers with existing data: {', '.join(skipped)}")
        tickers = remaining
    
    if not tickers:
        logger.info("No tickers to process. Exiting.")
        return 0
    
    logger.info(f"Processing {len(tickers)} ticker(s)")
    logger.info("")
    
    # Call the generate_static_data script
    try:
        generate_static_data_main(
            years_back=args.years_back,
            tickers=tickers,
            max_workers=args.max_workers
        )
        logger.info("")
        logger.info("="*80)
        logger.info("BACKFILL COMPLETE")
        logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        return 0
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())


