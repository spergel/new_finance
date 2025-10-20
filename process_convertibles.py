#!/usr/bin/env python3
"""
Process convertible preferred stocks from convertibles.csv and save JSON outputs
"""

import csv
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.securities_features_extractor import extract_preferred_stocks_simple

def extract_ticker_from_symbol(symbol):
    """Extract the base ticker from symbols like 'WFC/PRL' or 'BAC/PRL'."""
    # Handle formats like TICKER/PRX
    if '/' in symbol:
        return symbol.split('/')[0]
    # Handle formats like TICKERPRX
    elif symbol.endswith(('PR', 'PRA', 'PRB', 'PRC', 'PRD', 'PRE', 'PRF', 'PRG', 'PRH', 'PRI', 'PRJ', 'PRK', 'PRL', 'PRM', 'PRN', 'PRO', 'PRP', 'PRQ', 'PRR', 'PRS', 'PRT', 'PRU', 'PRV', 'PRW', 'PRX', 'PRY', 'PRZ')):
        # Try to find where the ticker ends and preferred suffix begins
        for suffix in ['PR', 'PRA', 'PRB', 'PRC', 'PRD', 'PRE', 'PRF', 'PRG', 'PRH', 'PRI', 'PRJ', 'PRK', 'PRL', 'PRM', 'PRN', 'PRO', 'PRP', 'PRQ', 'PRR', 'PRS', 'PRT', 'PRU', 'PRV', 'PRW', 'PRX', 'PRY', 'PRZ']:
            if symbol.endswith(suffix):
                return symbol[:-len(suffix)]
    return symbol

def main():
    # Read convertible preferred stocks from CSV
    convertible_stocks = []
    with open('convertibles.csv', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, quotechar='"', delimiter=',')
        for row in reader:
            if row.get('Convertible') == 'Yes':
                symbol = row['Symbol']
                ticker = extract_ticker_from_symbol(symbol)
                convertible_stocks.append({
                    'symbol': symbol,
                    'ticker': ticker,
                    'description': row['Description']
                })

    print(f"Found {len(convertible_stocks)} convertible preferred stocks")
    print()

    # Process first 10 convertible stocks
    processed = 0
    successful = 0

    for stock in convertible_stocks[:10]:  # Process first 10
        print(f"Processing {stock['symbol']} ({stock['ticker']}) - {stock['description']}")

        try:
            result = extract_preferred_stocks_simple(stock['ticker'])

            if result and result.total_securities > 0:
                successful += 1
                print(f"  SUCCESS: Found {result.total_securities} securities")
                print(f"  JSON saved to: output/llm/{result.ticker}_securities_features.json")
            else:
                print("  NO SECURITIES FOUND")
        except Exception as e:
            print(f"  ERROR: {e}")

        processed += 1
        print()

    print(f"Summary: {successful}/{processed} successful extractions")
    print("JSON files saved to output/llm/ directory")

if __name__ == "__main__":
    main()
