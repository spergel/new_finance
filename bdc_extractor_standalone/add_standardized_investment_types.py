#!/usr/bin/env python3
"""
Add standardized investment types to existing CSV files while preserving original values.

This script:
1. Reads all investment CSV files in the output directory
2. Adds a new 'investment_type_standardized' column
3. Uses the standardization module to map original investment types to standard values
4. Preserves the original 'investment_type' column
5. Writes the updated CSV files back
"""

import os
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add the current directory to the path so we can import standardization
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from standardization import standardize_investment_type


def process_csv_file(file_path: Path, output_dir: Path) -> Dict[str, any]:
    """
    Process a single CSV file to add standardized investment type column.
    
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
            
            # Check if standardized column already exists - if so, we'll update it
            has_standardized_column = 'investment_type_standardized' in fieldnames
            if has_standardized_column:
                print(f"  [UPDATE] {file_path.name} already has 'investment_type_standardized' column, updating values...")
            
            # Read all rows
            for row in reader:
                rows.append(row)
                stats['rows_processed'] += 1
        
        if not rows:
            print(f"  [WARN] {file_path.name} is empty, skipping...")
            return stats
        
        # Add standardized column to fieldnames (insert after investment_type) if it doesn't exist
        if has_standardized_column:
            # Column already exists, keep existing fieldnames
            new_fieldnames = fieldnames
        elif 'investment_type' in fieldnames:
            investment_type_idx = fieldnames.index('investment_type')
            new_fieldnames = (
                fieldnames[:investment_type_idx + 1] + 
                ['investment_type_standardized'] + 
                fieldnames[investment_type_idx + 1:]
            )
        else:
            # If investment_type column doesn't exist, add both columns at the end
            new_fieldnames = fieldnames + ['investment_type', 'investment_type_standardized']
        
        # Process each row to add standardized investment type
        for row in rows:
            original_type = row.get('investment_type', '').strip()
            
            # Standardize the investment type
            standardized_type = standardize_investment_type(original_type)
            row['investment_type_standardized'] = standardized_type
            
            # If investment_type was missing, preserve the standardized value as original too
            if not original_type and 'investment_type' not in row:
                row['investment_type'] = standardized_type
            
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
        print(f"❌ Output directory not found: {output_dir}")
        return
    
    # Find all investment CSV files
    csv_files = list(output_dir.glob('*_investments.csv'))
    
    if not csv_files:
        print(f"❌ No investment CSV files found in {output_dir}")
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
    
    print("\n[DONE] All CSV files now have 'investment_type_standardized' column.")


if __name__ == '__main__':
    main()

