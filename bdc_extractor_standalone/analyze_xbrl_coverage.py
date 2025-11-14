#!/usr/bin/env python3
"""
Analyze XBRL field coverage for all extracted tickers.
"""

import csv
import os
from collections import defaultdict

TICKERS = [
    'ARCC', 'BCSF', 'CGBD', 'CSWC', 'FDUS', 'FSK', 'GBDC', 'GLAD', 'MAIN',
    'MRCC', 'MSDL', 'MSIF', 'NCDL', 'NMFC', 'OBDC', 'OFS', 'OXSQ', 'PFX',
    'PSEC', 'RAND', 'SCM', 'TPVG', 'TRIN', 'WHF'
]

def analyze_ticker(ticker: str, xbrl_dir: str) -> dict:
    """Analyze XBRL field coverage for a ticker."""
    filepath = os.path.join(xbrl_dir, f'{ticker}_xbrl_raw.csv')
    
    if not os.path.exists(filepath):
        return {'ticker': ticker, 'error': 'File not found'}
    
    field_counts = defaultdict(int)
    total_rows = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        for row in reader:
            total_rows += 1
            for field in fieldnames:
                if row.get(field) and row[field].strip():
                    field_counts[field] += 1
    
    coverage = {}
    for field in fieldnames:
        if total_rows > 0:
            coverage[field] = {
                'count': field_counts[field],
                'pct': (field_counts[field] / total_rows) * 100
            }
        else:
            coverage[field] = {'count': 0, 'pct': 0}
    
    return {
        'ticker': ticker,
        'total_rows': total_rows,
        'coverage': coverage,
        'fields': fieldnames
    }

def main():
    """Analyze all tickers."""
    xbrl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'xbrl_raw')
    
    results = {}
    for ticker in TICKERS:
        results[ticker] = analyze_ticker(ticker, xbrl_dir)
    
    # Key fields to check
    key_fields = [
        'company_name', 'investment_type', 'industry', 'business_description',
        'principal_amount', 'cost_basis', 'fair_value',
        'maturity_date', 'acquisition_date',
        'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate'
    ]
    
    print("=" * 100)
    print("XBRL FIELD COVERAGE ANALYSIS")
    print("=" * 100)
    print(f"\n{'Ticker':<6} {'Total':<6} ", end='')
    for field in key_fields:
        print(f'{field[:12]:<12}', end='')
    print()
    print("-" * 100)
    
    for ticker in TICKERS:
        r = results[ticker]
        if 'error' in r:
            print(f"{ticker:<6} ERROR: {r['error']}")
            continue
        
        total = r['total_rows']
        print(f"{ticker:<6} {total:<6} ", end='')
        
        for field in key_fields:
            if field in r['coverage']:
                pct = r['coverage'][field]['pct']
                if pct > 90:
                    symbol = '✓'
                elif pct > 50:
                    symbol = '~'
                else:
                    symbol = '✗'
                print(f'{symbol} {pct:5.1f}%  ', end='')
            else:
                print(f'✗   0.0%  ', end='')
        print()
    
    print("\n" + "=" * 100)
    print("Legend: ✓ = >90%, ~ = 50-90%, ✗ = <50%")
    print("=" * 100)

if __name__ == '__main__':
    main()

