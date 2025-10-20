#!/usr/bin/env python3
"""
Process more preferred stocks from the preferred_stocks_list.csv
"""

import csv
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.securities_features_extractor import extract_preferred_stocks_simple

def process_pending_stocks(start_index=9, count=5):
    """Process the next batch of pending preferred stocks"""

    # Read the preferred stocks list
    pending_stocks = []
    with open('preferred_stocks_list.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['status'] == 'pending':
                pending_stocks.append(row)

    # Process the specified batch
    batch = pending_stocks[start_index:start_index+count]
    print(f"Processing {len(batch)} stocks starting from index {start_index}:")
    print("="*80)

    processed = 0
    successful = 0

    for stock in batch:
        print(f"\nProcessing {stock['ticker']} - {stock['company_name']}")

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

    print(f"\nBatch Summary: {successful}/{processed} successful extractions")
    print("="*80)

if __name__ == "__main__":
    # Process the final pending stock (VNO)
    process_pending_stocks(start_index=17, count=1)
