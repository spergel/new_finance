#!/usr/bin/env python3
"""
Analyze maturity date extraction status across all BDC parsers.
Focus on debt investments and identify what's still missing.
"""

import os
import pandas as pd
from pathlib import Path
from collections import defaultdict

def analyze_maturity_dates():
    """Analyze maturity date coverage for debt investments."""
    
    # Try multiple possible output directories
    script_dir = Path(__file__).parent
    possible_dirs = [
        script_dir / "output",
        script_dir.parent / "output",
        Path("output"),
        Path("../output"),
    ]
    
    output_dir = None
    for dir_path in possible_dirs:
        if dir_path.exists():
            output_dir = dir_path
            break
    
    if not output_dir:
        print("Output directory not found! Tried:", [str(d) for d in possible_dirs])
        return
    
    print(f"Using output directory: {output_dir.absolute()}")
    
    results = []
    
    # Find all historical investment CSV files
    import os
    all_files = os.listdir(output_dir)
    csv_files = [output_dir / f for f in all_files if f.endswith("_historical_investments.csv")]
    print(f"Found {len(csv_files)} historical investment CSV files")
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            
            # Extract ticker from filename
            ticker = csv_file.stem.split('_')[0]
            
            # Filter to debt investments
            debt_mask = df['investment_type'].str.contains(
                'debt|loan|note|lien|bond|secured', 
                case=False, 
                na=False
            )
            debt_df = df[debt_mask]
            
            if len(debt_df) == 0:
                continue
            
            # Count missing maturity dates
            total_debt = len(debt_df)
            missing_maturity = debt_df['maturity_date'].isna() | (debt_df['maturity_date'] == '') | (debt_df['maturity_date'] == 'N/A')
            missing_count = missing_maturity.sum()
            missing_pct = (missing_count / total_debt * 100) if total_debt > 0 else 0
            
            # Count missing acquisition dates
            missing_acq = debt_df['acquisition_date'].isna() | (debt_df['acquisition_date'] == '') | (debt_df['acquisition_date'] == 'N/A')
            missing_acq_count = missing_acq.sum()
            missing_acq_pct = (missing_acq_count / total_debt * 100) if total_debt > 0 else 0
            
            results.append({
                'ticker': ticker,
                'total_debt': total_debt,
                'missing_maturity': missing_count,
                'missing_maturity_pct': missing_pct,
                'missing_acquisition': missing_acq_count,
                'missing_acquisition_pct': missing_acq_pct,
                'has_maturity': total_debt - missing_count,
                'has_acquisition': total_debt - missing_acq_count
            })
            
        except Exception as e:
            print(f"Error processing {csv_file}: {e}")
            continue
    
    # Sort by missing maturity percentage (worst first)
    results.sort(key=lambda x: x['missing_maturity_pct'], reverse=True)
    
    # Print summary
    print("=" * 80)
    print("MATURITY DATE EXTRACTION STATUS - FOCUS ON DEBT INVESTMENTS")
    print("=" * 80)
    print()
    
    if not results:
        print("No results found! Check if output directory exists and contains CSV files.")
        return
    
    # Overall stats
    total_debt_all = sum(r['total_debt'] for r in results)
    total_missing_maturity = sum(r['missing_maturity'] for r in results)
    total_missing_acq = sum(r['missing_acquisition'] for r in results)
    
    print(f"OVERALL STATISTICS:")
    print(f"  Total debt investments: {total_debt_all:,}")
    if total_debt_all > 0:
        print(f"  Missing maturity_date: {total_missing_maturity:,} ({total_missing_maturity/total_debt_all*100:.1f}%)")
        print(f"  Missing acquisition_date: {total_missing_acq:,} ({total_missing_acq/total_debt_all*100:.1f}%)")
    else:
        print("  No debt investments found in any files!")
    print()
    
    # Critical issues - 100% missing maturity
    critical_maturity = [r for r in results if r['missing_maturity_pct'] == 100.0]
    if critical_maturity:
        print("=" * 80)
        print("🚨 CRITICAL: 100% MISSING MATURITY DATES (DEBT)")
        print("=" * 80)
        for r in critical_maturity:
            print(f"  {r['ticker']:6s} - {r['missing_maturity']:4d}/{r['total_debt']:4d} debt ({r['missing_maturity_pct']:.1f}%)")
        print()
    
    # High priority - 80-99% missing maturity
    high_priority = [r for r in results if 80.0 <= r['missing_maturity_pct'] < 100.0]
    if high_priority:
        print("=" * 80)
        print("⚠️  HIGH PRIORITY: 80-99% MISSING MATURITY DATES (DEBT)")
        print("=" * 80)
        for r in high_priority:
            print(f"  {r['ticker']:6s} - {r['missing_maturity']:4d}/{r['total_debt']:4d} debt ({r['missing_maturity_pct']:.1f}%) - Has: {r['has_maturity']}")
        print()
    
    # Medium priority - 50-79% missing maturity
    medium_priority = [r for r in results if 50.0 <= r['missing_maturity_pct'] < 80.0]
    if medium_priority:
        print("=" * 80)
        print("📊 MEDIUM PRIORITY: 50-79% MISSING MATURITY DATES (DEBT)")
        print("=" * 80)
        for r in medium_priority:
            print(f"  {r['ticker']:6s} - {r['missing_maturity']:4d}/{r['total_debt']:4d} debt ({r['missing_maturity_pct']:.1f}%) - Has: {r['has_maturity']}")
        print()
    
    # Good coverage - <50% missing maturity
    good_coverage = [r for r in results if r['missing_maturity_pct'] < 50.0]
    if good_coverage:
        print("=" * 80)
        print("✅ GOOD COVERAGE: <50% MISSING MATURITY DATES (DEBT)")
        print("=" * 80)
        for r in good_coverage:
            print(f"  {r['ticker']:6s} - {r['missing_maturity']:4d}/{r['total_debt']:4d} debt ({r['missing_maturity_pct']:.1f}%) - Has: {r['has_maturity']}")
        print()
    
    # Summary by status
    print("=" * 80)
    print("PARSER STATUS SUMMARY")
    print("=" * 80)
    
    # Check which parsers we've fixed
    fixed_parsers = ['CGBD', 'CSWC', 'MAIN']  # We just worked on these
    recently_fixed = [r for r in results if r['ticker'] in fixed_parsers]
    
    if recently_fixed:
        print("\nRecently Fixed Parsers (need to re-extract data):")
        for r in recently_fixed:
            status = "✅ Fixed" if r['missing_maturity_pct'] < 50 else "⚠️  Needs testing"
            print(f"  {r['ticker']:6s} - {status} - {r['missing_maturity_pct']:.1f}% missing (may need re-extraction)")
    
    # Still need fixing
    still_broken = [r for r in results if r['missing_maturity_pct'] >= 80 and r['ticker'] not in fixed_parsers]
    if still_broken:
        print("\nStill Need Fixing (80%+ missing maturity dates):")
        for r in still_broken:
            print(f"  {r['ticker']:6s} - {r['missing_maturity_pct']:.1f}% missing ({r['missing_maturity']}/{r['total_debt']} debt)")
    
    # Save detailed results
    df_results = pd.DataFrame(results)
    df_results.to_csv('maturity_date_status.csv', index=False)
    print(f"\n✅ Detailed results saved to maturity_date_status.csv")
    
    return results

if __name__ == "__main__":
    analyze_maturity_dates()

