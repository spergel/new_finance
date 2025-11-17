#!/usr/bin/env python3
"""Analyze CSV files to identify standardization opportunities."""

import csv
from collections import Counter
from pathlib import Path

output_dir = Path(__file__).parent.parent / 'output'

industries = Counter()
ref_rates = Counter()
date_formats = Counter()
interest_rate_formats = Counter()

for csv_file in output_dir.glob('*_investments.csv'):
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Industries
                industry = row.get('industry', '').strip()
                if industry:
                    industries[industry] += 1
                
                # Reference rates
                ref_rate = row.get('reference_rate', '').strip()
                if ref_rate:
                    ref_rates[ref_rate] += 1
                
                # Date formats
                acq_date = row.get('acquisition_date', '').strip()
                if acq_date:
                    # Get format pattern (e.g., "MM/DD/YYYY", "MM/YYYY", "YYYY-MM-DD")
                    if '/' in acq_date:
                        parts = acq_date.split('/')
                        if len(parts) == 2:
                            date_formats['MM/YYYY'] += 1
                        elif len(parts) == 3:
                            date_formats['MM/DD/YYYY'] += 1
                    elif '-' in acq_date:
                        date_formats['YYYY-MM-DD'] += 1
                    else:
                        date_formats[f'OTHER: {acq_date[:10]}'] += 1
                
                # Interest rate formats
                int_rate = row.get('interest_rate', '').strip()
                if int_rate:
                    if '%' in int_rate:
                        interest_rate_formats['With %'] += 1
                    else:
                        interest_rate_formats['Without %'] += 1
    except Exception as e:
        print(f"Error reading {csv_file.name}: {e}")

print("=" * 60)
print("INDUSTRY STANDARDIZATION OPPORTUNITIES")
print("=" * 60)
print(f"\nTotal unique industries: {len(industries)}")
print("\nTop 20 Industries:")
for industry, count in industries.most_common(20):
    print(f"  {industry}: {count:,}")

print("\n" + "=" * 60)
print("REFERENCE RATE STANDARDIZATION OPPORTUNITIES")
print("=" * 60)
print(f"\nTotal unique reference rates: {len(ref_rates)}")
print("\nTop 20 Reference Rates:")
for ref_rate, count in ref_rates.most_common(20):
    print(f"  {ref_rate}: {count:,}")

print("\n" + "=" * 60)
print("DATE FORMAT ANALYSIS")
print("=" * 60)
print(f"\nDate format distribution:")
for fmt, count in date_formats.most_common(10):
    print(f"  {fmt}: {count:,}")

print("\n" + "=" * 60)
print("INTEREST RATE FORMAT ANALYSIS")
print("=" * 60)
for fmt, count in interest_rate_formats.most_common():
    print(f"  {fmt}: {count:,}")

# Check for "Unknown" industries
unknown_count = industries.get('Unknown', 0)
total_industries = sum(industries.values())
if unknown_count > 0:
    print("\n" + "=" * 60)
    print("INDUSTRY DATA QUALITY")
    print("=" * 60)
    print(f"Rows with 'Unknown' industry: {unknown_count:,} ({unknown_count/total_industries*100:.1f}%)")
    print(f"Total rows: {total_industries:,}")

