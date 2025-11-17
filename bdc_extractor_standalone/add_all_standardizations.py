#!/usr/bin/env python3
"""
Add standardized columns for industries and reference rates to existing CSV files.

This script:
1. Adds 'industry_standardized' column
2. Adds 'reference_rate_standardized' column (if not already present)
3. Preserves original values
4. Uses the standardization module to map values
"""

import os
import csv
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional

# Add the current directory to the path so we can import standardization
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from standardization import standardize_industry, standardize_reference_rate


def clean_reference_rate(raw_rate: Optional[str]) -> Optional[str]:
    """
    Clean reference rate before standardization.
    Removes frequency indicators like (Q), (M), (S), etc.
    """
    if not raw_rate or raw_rate.strip() == '':
        return None
    
    raw_rate = raw_rate.strip()
    
    # Remove common invalid values
    if raw_rate in ['—', '-', '%', 'RATE', '']:
        return None
    
    # Remove frequency indicators: (Q), (M), (S), (3M), (1M), etc.
    raw_rate = re.sub(r'\s*\([QMS\d]+\)\s*$', '', raw_rate, flags=re.IGNORECASE)
    
    # Remove trailing + signs (formula fragments)
    raw_rate = re.sub(r'\s*\+\s*$', '', raw_rate)
    
    # Handle formula fragments like "SF +" -> "SOFR", "E +" -> "EURIBOR"
    if raw_rate.upper() in ['SF', 'S']:
        return 'SOFR'
    elif raw_rate.upper() in ['E', 'SN']:
        return 'EURIBOR'
    elif raw_rate.upper() in ['L']:
        return 'LIBOR'
    elif raw_rate.upper() in ['P']:
        return 'PRIME'
    elif raw_rate.upper() in ['F']:
        return 'FED FUNDS'
    elif raw_rate.upper() in ['C', 'CA']:
        return 'CDOR'
    
    return raw_rate


def process_csv_file(file_path: Path, output_dir: Path) -> Dict[str, any]:
    """
    Process a single CSV file to add standardized columns.
    
    Args:
        file_path: Path to the input CSV file
        output_dir: Directory to write the updated CSV file
        
    Returns:
        Dictionary with processing statistics
    """
    stats = {
        'file': file_path.name,
        'rows_processed': 0,
        'rows_updated': 0,
        'errors': []
    }
    
    try:
        # Read the CSV file
        rows = []
        fieldnames = []
        
        with open(file_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            
            # Check which standardized columns already exist
            has_industry_std = 'industry_standardized' in fieldnames
            has_ref_rate_std = 'reference_rate_standardized' in fieldnames
            
            if has_industry_std and has_ref_rate_std:
                print(f"  [SKIP] {file_path.name} already has standardized columns")
                return stats
            
            # Read all rows
            for row in reader:
                rows.append(row)
                stats['rows_processed'] += 1
        
        if not rows:
            print(f"  [WARN] {file_path.name} is empty, skipping...")
            return stats
        
        # Add standardized columns to fieldnames
        new_fieldnames = list(fieldnames)
        
        # Add industry_standardized after industry
        if not has_industry_std and 'industry' in fieldnames:
            industry_idx = fieldnames.index('industry')
            new_fieldnames.insert(industry_idx + 1, 'industry_standardized')
        elif not has_industry_std:
            new_fieldnames.append('industry_standardized')
        
        # Add reference_rate_standardized after reference_rate
        if not has_ref_rate_std and 'reference_rate' in fieldnames:
            ref_rate_idx = fieldnames.index('reference_rate')
            new_fieldnames.insert(ref_rate_idx + 1, 'reference_rate_standardized')
        elif not has_ref_rate_std:
            new_fieldnames.append('reference_rate_standardized')
        
        # Process each row to add standardized values
        for row in rows:
            # Standardize industry
            if not has_industry_std:
                original_industry = row.get('industry', '').strip()
                standardized_industry = standardize_industry(original_industry)
                row['industry_standardized'] = standardized_industry
            
            # Standardize reference rate
            if not has_ref_rate_std:
                original_ref_rate = row.get('reference_rate', '').strip()
                cleaned_ref_rate = clean_reference_rate(original_ref_rate)
                standardized_ref_rate = standardize_reference_rate(cleaned_ref_rate) if cleaned_ref_rate else None
                row['reference_rate_standardized'] = standardized_ref_rate or ''
            
            stats['rows_updated'] += 1
        
        # Write the updated CSV file
        output_path = output_dir / file_path.name
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"  [OK] {file_path.name}: {stats['rows_updated']} rows updated")
        
    except Exception as e:
        error_msg = f"Error processing {file_path.name}: {str(e)}"
        stats['errors'].append(error_msg)
        print(f"  [ERROR] {error_msg}")
    
    return stats


def main():
    """Main entry point."""
    # Get the output directory (one level up from bdc_extractor_standalone)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_dir = project_root / 'output'
    
    if not output_dir.exists():
        print(f"[ERROR] Output directory not found: {output_dir}")
        return
    
    # Find all investment CSV files
    csv_files = list(output_dir.glob('*_investments.csv'))
    
    if not csv_files:
        print(f"[ERROR] No investment CSV files found in {output_dir}")
        return
    
    print(f"Found {len(csv_files)} investment CSV files")
    print(f"Processing files in: {output_dir}\n")
    
    # Process each file
    all_stats = []
    for csv_file in sorted(csv_files):
        stats = process_csv_file(csv_file, output_dir)
        all_stats.append(stats)
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    total_files = len(all_stats)
    total_rows = sum(s['rows_processed'] for s in all_stats)
    total_updated = sum(s['rows_updated'] for s in all_stats)
    total_errors = sum(len(s['errors']) for s in all_stats)
    
    print(f"Files processed: {total_files}")
    print(f"Total rows processed: {total_rows}")
    print(f"Total rows updated: {total_updated}")
    print(f"Total errors: {total_errors}")
    
    if total_errors > 0:
        print("\n[WARN] Errors encountered:")
        for stats in all_stats:
            for error in stats['errors']:
                print(f"  - {error}")
    
    print("\n[DONE] Standardized columns added to CSV files.")


if __name__ == '__main__':
    main()

