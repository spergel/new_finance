#!/usr/bin/env python3
"""Quick test of key parsers after fixes."""
import sys
import os
import logging
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from historical_investment_extractor import HistoricalInvestmentExtractor

logging.basicConfig(level=logging.WARNING)

e = HistoricalInvestmentExtractor()
test_tickers = ['TRIN', 'BXSL', 'ARCC', 'MAIN']

print('Quick test of key parsers:')
print('=' * 50)
for ticker in test_tickers:
    start = time.time()
    try:
        invs = e.extract_historical_investments(ticker, years_back=1)
        elapsed = time.time() - start
        print(f'{ticker}: {len(invs)} investments in {elapsed:.1f}s')
    except Exception as ex:
        elapsed = time.time() - start
        print(f'{ticker}: ERROR after {elapsed:.1f}s - {ex}')

