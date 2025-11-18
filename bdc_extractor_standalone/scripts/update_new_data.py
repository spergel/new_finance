#!/usr/bin/env python3
"""
Update Data for New Filings

This script checks for new filings and extracts data for tickers that have updates.

Usage:
    python scripts/update_new_data.py
    python scripts/update_new_data.py --ticker ARCC
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.check_new_filings import check_new_filings
from scripts.generate_static_data import main as generate_static_data_main
from sec_api_client import SECAPIClient
from bdc_config import BDC_UNIVERSE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Check for and update data from new SEC filings"
    )
    parser.add_argument(
        '--ticker',
        action='append',
        help='Specific ticker(s) to update (can be used multiple times)'
    )
    parser.add_argument(
        '--days-back',
        type=int,
        default=30,
        help='Number of days to look back for filings (default: 30)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force update even if no new filings detected'
    )
    parser.add_argument(
        '--years-back',
        type=int,
        default=1,
        help='Years of historical data to extract (default: 1, for updates)'
    )
    
    args = parser.parse_args()
    
    logger.info("="*80)
    logger.info("UPDATE DATA FROM NEW FILINGS")
    logger.info("="*80)
    logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    
    # Determine which tickers to check
    if args.ticker:
        tickers = [t.upper() for t in args.ticker]
    else:
        tickers = [bdc['ticker'] for bdc in BDC_UNIVERSE]
    
    logger.info(f"Checking {len(tickers)} ticker(s) for new filings...")
    logger.info("")
    
    sec_client = SECAPIClient()
    tickers_to_update = []
    
    # Check each ticker
    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[{i}/{len(tickers)}] Checking {ticker}...")
        
        try:
            result = check_new_filings(ticker, args.days_back, sec_client)
            
            if result['has_new'] or args.force:
                tickers_to_update.append(ticker)
                if result['has_new']:
                    logger.info(f"  ✅ New filing found: {result['latest_filing_date']}")
                else:
                    logger.info(f"  🔄 Forcing update (--force flag)")
            else:
                logger.info(f"  ⏸️  {result['reason']}")
        except Exception as e:
            logger.error(f"  ❌ Error checking {ticker}: {e}")
            if args.force:
                # If force flag is set, try to update anyway
                tickers_to_update.append(ticker)
    
    if not tickers_to_update:
        logger.info("")
        logger.info("No tickers need updating. Exiting.")
        return 0
    
    logger.info("")
    logger.info("="*80)
    logger.info(f"UPDATING {len(tickers_to_update)} TICKER(S)")
    logger.info("="*80)
    logger.info(f"Tickers: {', '.join(tickers_to_update)}")
    logger.info("")
    
    # Update data for tickers with new filings
    try:
        generate_static_data_main(
            years_back=args.years_back,
            tickers=tickers_to_update
        )
        
        logger.info("")
        logger.info("="*80)
        logger.info("UPDATE COMPLETE")
        logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*80)
        return 0
    except Exception as e:
        logger.error(f"Update failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())







