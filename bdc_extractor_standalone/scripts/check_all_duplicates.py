#!/usr/bin/env python3
"""
Check for duplicates across all investment CSV files.
"""
import pandas as pd
from pathlib import Path
import sys

def check_duplicates(file_path: Path):
    """Check for various types of duplicates in a CSV file."""
    issues = []
    try:
        df = pd.read_csv(file_path)
        total_rows = len(df)
        
        if total_rows == 0:
            return issues
        
        # 1. Exact duplicates
        exact_dups = df[df.duplicated(keep=False)]
        if not exact_dups.empty:
            issues.append(f"  [ALERT] {len(exact_dups)} exact duplicate rows")
        
        # 2. Duplicates by company_name + investment_type + principal_amount
        key_cols_principal = ['company_name', 'investment_type', 'principal_amount']
        if all(col in df.columns for col in key_cols_principal):
            df_filtered = df.dropna(subset=['principal_amount'])
            dups_principal = df_filtered[df_filtered.duplicated(subset=key_cols_principal, keep=False)]
            if not dups_principal.empty:
                issues.append(f"  [WARNING] {len(dups_principal)} duplicates by (company + type + principal)")
        
        # 3. Duplicates by company_name + investment_type + fair_value
        key_cols_fair = ['company_name', 'investment_type', 'fair_value']
        if all(col in df.columns for col in key_cols_fair):
            df_filtered = df.dropna(subset=['fair_value'])
            dups_fair = df_filtered[df_filtered.duplicated(subset=key_cols_fair, keep=False)]
            if not dups_fair.empty:
                issues.append(f"  [WARNING] {len(dups_fair)} duplicates by (company + type + fair_value)")
        
        # 4. Duplicates by company_name + investment_type + dates (likely same investment)
        key_cols_dates = ['company_name', 'investment_type', 'acquisition_date', 'maturity_date']
        if all(col in df.columns for col in key_cols_dates):
            # Fill NaN with empty string for comparison
            df_dates = df.copy()
            for col in ['acquisition_date', 'maturity_date']:
                df_dates[col] = df_dates[col].fillna('')
            dups_dates = df_dates[df_dates.duplicated(subset=key_cols_dates, keep=False)]
            if not dups_dates.empty:
                issues.append(f"  [WARNING] {len(dups_dates)} duplicates by (company + type + dates)")
        
        # 5. Companies with multiple investments of same type (likely different tranches, but worth checking)
        if 'company_name' in df.columns and 'investment_type' in df.columns:
            df_investments = df.dropna(subset=['principal_amount', 'fair_value'], how='all')
            grouped = df_investments.groupby(['company_name', 'investment_type'])
            multi_tranche = sum(1 for name_type, group in grouped if len(group) > 1)
            if multi_tranche > 0:
                issues.append(f"  [INFO] {multi_tranche} companies with multiple investments of same type")
        
    except Exception as e:
        issues.append(f"  [ERROR] {e}")
    
    return issues

if __name__ == "__main__":
    output_dir = Path('output')
    csv_files = sorted(output_dir.glob('*_investments.csv'))
    
    files_with_issues = []
    total_exact_dups = 0
    total_principal_dups = 0
    total_fair_dups = 0
    total_date_dups = 0
    
    print("=== Checking for Duplicates Across All Files ===\n")
    
    for csv_file in csv_files:
        issues = check_duplicates(csv_file)
        if issues:
            files_with_issues.append((csv_file.name, issues))
            # Count issues
            for issue in issues:
                if 'exact duplicate' in issue.lower():
                    total_exact_dups += 1
                elif 'principal' in issue.lower():
                    total_principal_dups += 1
                elif 'fair_value' in issue.lower():
                    total_fair_dups += 1
                elif 'dates' in issue.lower():
                    total_date_dups += 1
    
    if files_with_issues:
        print(f"Found issues in {len(files_with_issues)} files:\n")
        for filename, issues in files_with_issues:
            print(f"{filename}:")
            for issue in issues:
                print(issue)
            print()
    else:
        print("[OK] No duplicate issues found across all files")
    
    print(f"\n=== Summary ===")
    print(f"Files with exact duplicates: {sum(1 for _, issues in files_with_issues if any('exact duplicate' in i.lower() for i in issues))}")
    print(f"Files with principal-based duplicates: {sum(1 for _, issues in files_with_issues if any('principal' in i.lower() for i in issues))}")
    print(f"Files with fair_value-based duplicates: {sum(1 for _, issues in files_with_issues if any('fair_value' in i.lower() for i in issues))}")
    print(f"Files with date-based duplicates: {sum(1 for _, issues in files_with_issues if any('dates' in i.lower() for i in issues))}")



