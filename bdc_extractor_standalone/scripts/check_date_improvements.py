#!/usr/bin/env python3
"""Check date improvements for parsers with HTML fallback."""
import pandas as pd
from pathlib import Path

files = {
    'CCAP': 'CCAP_Crescent_Capital_BDC_Inc_investments.csv',
    'GLAD': 'GLAD_Gladstone_Capital_Corp_investments.csv',
    'GAIN': 'GAIN_Gladstone_Investment_Corp_investments.csv',
    'GSBD': 'GSBD_Goldman_Sachs_BDC_Inc_investments.csv',
}

output_dir = Path('output')
print("=== Date Extraction Results ===\n")

for ticker, filename in files.items():
    filepath = output_dir / filename
    if not filepath.exists():
        print(f"{ticker}: File not found")
        continue
    
    df = pd.read_csv(filepath)
    total = len(df)
    missing_acq = df['acquisition_date'].isna().sum()
    missing_mat = df['maturity_date'].isna().sum()
    with_dates = df[df['acquisition_date'].notna() | df['maturity_date'].notna()].shape[0]
    with_acq = df['acquisition_date'].notna().sum()
    with_mat = df['maturity_date'].notna().sum()
    
    print(f"{ticker}:")
    print(f"  Total: {total}")
    print(f"  Missing acquisition dates: {missing_acq}/{total} ({100*missing_acq/total:.1f}%)")
    print(f"  Missing maturity dates: {missing_mat}/{total} ({100*missing_mat/total:.1f}%)")
    print(f"  With dates: {with_dates}/{total} ({100*with_dates/total:.1f}%)")
    print(f"  With acquisition: {with_acq}/{total} ({100*with_acq/total:.1f}%)")
    print(f"  With maturity: {with_mat}/{total} ({100*with_mat/total:.1f}%)")
    print()



