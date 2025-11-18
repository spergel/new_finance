#!/usr/bin/env python3
"""
Rerun extraction for tickers with most missing dates to get improved date extraction.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from historical_investment_extractor import HistoricalInvestmentExtractor
from sec_api_client import SECAPIClient
import traceback

def rerun_ticker(ticker: str, years_back: int = 1):
    """Rerun extraction for a single ticker."""
    print(f"\n=== Rerunning {ticker} ===")
    try:
        extractor = HistoricalInvestmentExtractor()
        investments = extractor.extract_historical_investments(ticker=ticker, years_back=years_back)
        
        if not investments:
            print(f"[{ticker}] No investments extracted")
            return None
        
        print(f"[{ticker}] Extracted {len(investments)} investments")
        
        # Count missing dates
        missing_acq = sum(1 for inv in investments if not inv.get('acquisition_date'))
        missing_mat = sum(1 for inv in investments if not inv.get('maturity_date'))
        print(f"[{ticker}] Missing acquisition dates: {missing_acq}/{len(investments)}")
        print(f"[{ticker}] Missing maturity dates: {missing_mat}/{len(investments)}")
        
        return {
            'ticker': ticker,
            'total': len(investments),
            'missing_acq': missing_acq,
            'missing_mat': missing_mat
        }
    except Exception as e:
        print(f"[{ticker}] Error: {e}")
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Focus on tickers with most missing dates
    tickers = ['ARCC', 'BBDC', 'BCSF', 'FSK', 'GBDC']  # Ares, BBDC, BCSF, FSK, GBDC
    
    print("Rerunning extraction for tickers with most missing dates...")
    print("This will use the enhanced date extraction logic.\n")
    
    results = []
    for ticker in tickers:
        result = rerun_ticker(ticker, years_back=1)
        if result:
            results.append(result)
    
    print("\n=== Summary ===")
    for r in results:
        print(f"{r['ticker']}: {r['missing_acq']}/{r['total']} missing acq dates, {r['missing_mat']}/{r['total']} missing mat dates")



