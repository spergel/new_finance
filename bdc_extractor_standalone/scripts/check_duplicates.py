#!/usr/bin/env python3
"""
Check for duplicate entries in investment CSV files.
"""

import pandas as pd
import sys
from pathlib import Path

def check_duplicates(csv_path: str, verbose: bool = True):
    """Check for duplicates in a CSV file."""
    df = pd.read_csv(csv_path)
    
    print(f"\n=== Analyzing: {Path(csv_path).name} ===")
    print(f"Total rows: {len(df)}")
    
    # Check for exact duplicates (all columns match)
    exact_dupes = df[df.duplicated(keep=False)]
    if len(exact_dupes) > 0:
        print(f"\n[WARNING] Found {len(exact_dupes)} rows that are exact duplicates:")
        print(exact_dupes[['company_name', 'investment_type', 'principal_amount', 'fair_value']].to_string())
    else:
        print("[OK] No exact duplicates found")
    
    # Check for duplicates by company_name + investment_type + principal_amount
    key_cols = ['company_name', 'investment_type', 'principal_amount']
    if all(col in df.columns for col in key_cols):
        key_dupes = df[df.duplicated(subset=key_cols, keep=False)]
        if len(key_dupes) > 0:
            print(f"\n[WARNING] Found {len(key_dupes)} rows with duplicate company + type + principal:")
            print(key_dupes[['company_name', 'investment_type', 'principal_amount', 'fair_value', 'acquisition_date', 'maturity_date']].to_string())
        else:
            print("[OK] No duplicates by (company + type + principal)")
    
    # Check for duplicates by company_name + investment_type + fair_value
    key_cols2 = ['company_name', 'investment_type', 'fair_value']
    if all(col in df.columns for col in key_cols2):
        key_dupes2 = df[df.duplicated(subset=key_cols2, keep=False)]
        if len(key_dupes2) > 0:
            print(f"\n[WARNING] Found {len(key_dupes2)} rows with duplicate company + type + fair_value:")
            print(key_dupes2[['company_name', 'investment_type', 'fair_value', 'principal_amount', 'acquisition_date', 'maturity_date']].to_string())
        else:
            print("[OK] No duplicates by (company + type + fair_value)")
    
    # Check for same company + type but different amounts (might be multiple tranches)
    if 'company_name' in df.columns and 'investment_type' in df.columns:
        company_type_groups = df.groupby(['company_name', 'investment_type']).size()
        multiple_tranches = company_type_groups[company_type_groups > 1]
        if len(multiple_tranches) > 0:
            print(f"\n[INFO] Found {len(multiple_tranches)} companies with multiple investments of same type (likely different tranches):")
            for (company, inv_type), count in multiple_tranches.items():
                subset = df[(df['company_name'] == company) & (df['investment_type'] == inv_type)]
                print(f"\n  {company} - {inv_type} ({count} entries):")
                print(f"    Principal amounts: {subset['principal_amount'].tolist() if 'principal_amount' in subset.columns else 'N/A'}")
                print(f"    Fair values: {subset['fair_value'].tolist() if 'fair_value' in subset.columns else 'N/A'}")
                if 'acquisition_date' in subset.columns:
                    print(f"    Acquisition dates: {subset['acquisition_date'].fillna('N/A').tolist()}")
                if 'maturity_date' in subset.columns:
                    print(f"    Maturity dates: {subset['maturity_date'].fillna('N/A').tolist()}")
    
    # Check for rows with same company + type + all financial values (likely true duplicates)
    financial_cols = ['principal_amount', 'cost', 'fair_value']
    financial_cols = [col for col in financial_cols if col in df.columns]
    if financial_cols:
        dup_key = ['company_name', 'investment_type'] + financial_cols
        financial_dupes = df[df.duplicated(subset=dup_key, keep=False)]
        if len(financial_dupes) > 0:
            print(f"\n[ALERT] Found {len(financial_dupes)} rows with duplicate company + type + all financial values (likely true duplicates):")
            print(financial_dupes[['company_name', 'investment_type'] + financial_cols + ['acquisition_date', 'maturity_date']].to_string())
        else:
            print("[OK] No duplicates by (company + type + all financial values)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_duplicates.py <csv_file>")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    check_duplicates(csv_file, verbose=True)
