#!/usr/bin/env python3
"""
Check for New SEC Filings

This script checks SEC EDGAR for new 10-Q filings for all BDCs and
identifies which companies have new data available.

Usage:
    python scripts/check_new_filings.py
    python scripts/check_new_filings.py --ticker ARCC
    python scripts/check_new_filings.py --days-back 7
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sec_api_client import SECAPIClient
from bdc_config import BDC_UNIVERSE, get_bdc_by_ticker

# Try to use edgartools if available (better for checking filings)
try:
    from edgar import Company, set_identity
    EDGARTOOLS_AVAILABLE = True
    set_identity("bdc-extractor@example.com")  # SEC requires email
except ImportError:
    EDGARTOOLS_AVAILABLE = False
    Company = None

# Define PUBLIC_DATA_DIR here to avoid circular import
ROOT = os.path.dirname(os.path.dirname(__file__))
PUBLIC_DATA_DIR = os.path.join(ROOT, 'frontend', 'public', 'data')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_latest_period(ticker: str) -> Optional[str]:
    """Get the latest period for a ticker from existing data."""
    ticker_dir = os.path.join(PUBLIC_DATA_DIR, ticker.upper())
    latest_file = os.path.join(ticker_dir, 'latest.json')
    
    if not os.path.exists(latest_file):
        return None
    
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('latest_period')
    except Exception:
        return None


def get_latest_filing_date(ticker: str) -> Optional[str]:
    """Get the latest filing date from existing data."""
    latest_period = get_latest_period(ticker)
    if not latest_period:
        return None
    
    ticker_dir = os.path.join(PUBLIC_DATA_DIR, ticker.upper())
    investments_file = os.path.join(ticker_dir, f'investments_{latest_period}.json')
    
    if not os.path.exists(investments_file):
        return None
    
    try:
        with open(investments_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('filing_date')
    except Exception:
        return None


def check_new_filings(
    ticker: str,
    days_back: int = 30,
    sec_client: SECAPIClient = None
) -> Dict:
    """
    Check for new 10-Q filings for a ticker.
    
    Returns:
        Dict with 'has_new', 'latest_filing', 'existing_filing_date', etc.
    """
    existing_filing_date = get_latest_filing_date(ticker)
    
    # Try edgartools first (more reliable)
    if EDGARTOOLS_AVAILABLE:
        try:
            company = Company(ticker)
            filings = company.get_filings(form="10-Q")
            
            if not filings:
                return {
                    'ticker': ticker,
                    'has_new': False,
                    'reason': 'no_filings_found',
                    'existing_filing_date': existing_filing_date
                }
            
            # Filter by date
            cutoff_date = datetime.now() - timedelta(days=days_back)
            recent_filings = []
            for f in filings:
                # Handle both string and date objects
                if isinstance(f.filing_date, str):
                    filing_dt = datetime.strptime(f.filing_date, '%Y-%m-%d')
                else:
                    # It's a date object
                    filing_dt = datetime.combine(f.filing_date, datetime.min.time())
                
                if filing_dt >= cutoff_date:
                    recent_filings.append(f)
            
            if not recent_filings:
                return {
                    'ticker': ticker,
                    'has_new': False,
                    'reason': 'no_recent_filings',
                    'existing_filing_date': existing_filing_date
                }
            
            # Get the most recent filing
            latest_filing_obj = max(recent_filings, key=lambda f: f.filing_date if isinstance(f.filing_date, str) else f.filing_date)
            
            # Normalize filing date to string
            if isinstance(latest_filing_obj.filing_date, str):
                latest_filing_date = latest_filing_obj.filing_date
            else:
                latest_filing_date = latest_filing_obj.filing_date.strftime('%Y-%m-%d')
            
            # Check if this is newer than what we have
            has_new = False
            if existing_filing_date is None:
                has_new = True
                reason = 'no_existing_data'
            else:
                existing_dt = datetime.strptime(existing_filing_date, '%Y-%m-%d')
                latest_dt = datetime.strptime(latest_filing_date, '%Y-%m-%d')
                if latest_dt > existing_dt:
                    has_new = True
                    reason = 'newer_filing_available'
                else:
                    reason = 'up_to_date'
            
            return {
                'ticker': ticker,
                'has_new': has_new,
                'reason': reason,
                'existing_filing_date': existing_filing_date,
                'latest_filing_date': latest_filing_date,
                'latest_filing': {
                    'date': latest_filing_date,
                    'accession': latest_filing_obj.accession_number,
                    'form': latest_filing_obj.form,
                    'url': latest_filing_obj.url if hasattr(latest_filing_obj, 'url') else None
                },
                'days_since_existing': (
                    (datetime.strptime(latest_filing_date, '%Y-%m-%d') - 
                     datetime.strptime(existing_filing_date, '%Y-%m-%d')).days
                    if existing_filing_date else None
                )
            }
        except Exception as e:
            logger.warning(f"edgartools failed for {ticker}, falling back to SEC API: {e}")
    
    # Fallback to SEC API client
    if sec_client is None:
        sec_client = SECAPIClient()
    
    # Get recent 10-Q filings
    filings = sec_client.get_historical_10q_filings(
        ticker,
        years_back=1,  # Only check last year
        start_date=(datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    )
    
    if not filings:
        return {
            'ticker': ticker,
            'has_new': False,
            'reason': 'no_filings_found',
            'existing_filing_date': existing_filing_date
        }
    
    # Get the most recent filing
    latest_filing = max(filings, key=lambda f: f['date'])
    latest_filing_date = latest_filing['date']
    
    # Check if this is newer than what we have
    has_new = False
    if existing_filing_date is None:
        has_new = True
        reason = 'no_existing_data'
    else:
        existing_dt = datetime.strptime(existing_filing_date, '%Y-%m-%d')
        latest_dt = datetime.strptime(latest_filing_date, '%Y-%m-%d')
        if latest_dt > existing_dt:
            has_new = True
            reason = 'newer_filing_available'
        else:
            reason = 'up_to_date'
    
    return {
        'ticker': ticker,
        'has_new': has_new,
        'reason': reason,
        'existing_filing_date': existing_filing_date,
        'latest_filing_date': latest_filing_date,
        'latest_filing': latest_filing,
        'days_since_existing': (
            (datetime.strptime(latest_filing_date, '%Y-%m-%d') - 
             datetime.strptime(existing_filing_date, '%Y-%m-%d')).days
            if existing_filing_date else None
        )
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check for new SEC 10-Q filings"
    )
    parser.add_argument(
        '--ticker',
        action='append',
        help='Specific ticker(s) to check (can be used multiple times)'
    )
    parser.add_argument(
        '--days-back',
        type=int,
        default=30,
        help='Number of days to look back for filings (default: 30)'
    )
    parser.add_argument(
        '--output',
        help='Output JSON file path (optional)'
    )
    parser.add_argument(
        '--only-new',
        action='store_true',
        help='Only show tickers with new filings'
    )
    
    args = parser.parse_args()
    
    logger.info("="*80)
    logger.info("CHECKING FOR NEW SEC FILINGS")
    logger.info("="*80)
    logger.info(f"Days back: {args.days_back}")
    logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    
    # Determine which tickers to check
    if args.ticker:
        tickers = [t.upper() for t in args.ticker]
    else:
        tickers = [bdc['ticker'] for bdc in BDC_UNIVERSE]
    
    logger.info(f"Checking {len(tickers)} ticker(s)")
    logger.info("")
    
    sec_client = SECAPIClient()
    results = []
    new_filings = []
    
    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[{i}/{len(tickers)}] Checking {ticker}...")
        
        try:
            result = check_new_filings(ticker, args.days_back, sec_client)
            results.append(result)
            
            if result['has_new']:
                new_filings.append(ticker)
                logger.info(f"  ✅ NEW FILING: {result['latest_filing_date']} "
                          f"(existing: {result['existing_filing_date'] or 'none'})")
            else:
                if not args.only_new:
                    logger.info(f"  ⏸️  {result['reason']} "
                              f"(latest: {result.get('latest_filing_date', 'N/A')})")
        except Exception as e:
            logger.error(f"  ❌ Error checking {ticker}: {e}")
            results.append({
                'ticker': ticker,
                'has_new': False,
                'error': str(e)
            })
    
    logger.info("")
    logger.info("="*80)
    logger.info("SUMMARY")
    logger.info("="*80)
    logger.info(f"Total checked: {len(tickers)}")
    logger.info(f"New filings found: {len(new_filings)}")
    
    if new_filings:
        logger.info("")
        logger.info("Tickers with new filings:")
        for ticker in new_filings:
            result = next(r for r in results if r['ticker'] == ticker)
            logger.info(f"  - {ticker}: {result['latest_filing_date']}")
    
    logger.info("="*80)
    
    # Write output JSON if requested
    if args.output:
        output_data = {
            'checked_at': datetime.now().isoformat(),
            'days_back': args.days_back,
            'total_checked': len(tickers),
            'new_filings_count': len(new_filings),
            'results': results
        }
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results written to: {args.output}")
    
    # Return exit code based on whether new filings were found
    return 0 if new_filings else 1


if __name__ == '__main__':
    exit(main())

