#!/usr/bin/env python3
"""Quick summary of maturity date status for debt investments."""

import pandas as pd

import os
from pathlib import Path

# Find the CSV file
script_dir = Path(__file__).parent
csv_path = script_dir.parent / 'output' / 'missing_dates_analysis.csv'
if not csv_path.exists():
    csv_path = script_dir / 'output' / 'missing_dates_analysis.csv'

df = pd.read_csv(csv_path)

# Remove duplicates (some files appear twice)
df = df.drop_duplicates(subset=['ticker'])

# Filter to debt investments
debt_df = df[df['debt_total'] > 0].copy()
debt_df = debt_df.sort_values('debt_pct_missing_mat', ascending=False)

print("=" * 80)
print("MATURITY DATE STATUS - DEBT INVESTMENTS (FOCUS)")
print("=" * 80)
print()

total_debt = debt_df['debt_total'].sum()
total_missing = debt_df['debt_missing_mat'].sum()
print(f"OVERALL: {total_missing:,}/{total_debt:,} ({total_missing/total_debt*100:.1f}%) missing maturity dates")
print()

# 100% missing
critical = debt_df[debt_df['debt_pct_missing_mat'] == 100.0]
if len(critical) > 0:
    print("🚨 100% MISSING MATURITY DATES:")
    for _, row in critical.iterrows():
        print(f"   {row['ticker']:6s} - {int(row['debt_missing_mat']):4d}/{int(row['debt_total']):4d} debt")
    print()

# 80-99% missing
high = debt_df[(debt_df['debt_pct_missing_mat'] >= 80) & (debt_df['debt_pct_missing_mat'] < 100)]
if len(high) > 0:
    print("⚠️  80-99% MISSING MATURITY DATES:")
    for _, row in high.iterrows():
        print(f"   {row['ticker']:6s} - {int(row['debt_missing_mat']):4d}/{int(row['debt_total']):4d} debt ({row['debt_pct_missing_mat']:.1f}%)")
    print()

# Good coverage
good = debt_df[debt_df['debt_pct_missing_mat'] < 20]
if len(good) > 0:
    print("✅ GOOD COVERAGE (<20% missing):")
    for _, row in good.iterrows():
        print(f"   {row['ticker']:6s} - {int(row['debt_missing_mat']):4d}/{int(row['debt_total']):4d} debt ({row['debt_pct_missing_mat']:.1f}% missing)")
    print()

print("=" * 80)
print("PRIORITY FIXES NEEDED (for maturity dates):")
print("=" * 80)
print()
print("HIGH PRIORITY (100% missing):")
for ticker in critical['ticker'].head(10):
    print(f"  - {ticker}")
print()
print("MEDIUM PRIORITY (80-99% missing):")
for ticker in high['ticker'].head(10):
    print(f"  - {ticker}")

