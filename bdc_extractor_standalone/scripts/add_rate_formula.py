#!/usr/bin/env python3
"""Add rate_formula column to all investment CSV files."""
import pandas as pd
import os
import sys
from pathlib import Path

# Add parent directory to path to import standardization
sys.path.append(str(Path(__file__).parent.parent))
from standardization import calculate_rate_formula as calc_formula

def calculate_rate_formula(row):
    """Calculate rate formula from interest_rate, reference_rate, spread, and floor_rate."""
    return calc_formula(
        row.get('interest_rate'),
        row.get('reference_rate'),
        row.get('spread'),
        row.get('floor_rate')
    )

def add_rate_formula_to_file(filepath):
    """Add rate_formula column to a CSV file."""
    try:
        df = pd.read_csv(filepath)
        
        # Calculate rate_formula for each row
        df['rate_formula'] = df.apply(calculate_rate_formula, axis=1)
        
        # Reorder columns to put rate_formula after interest_rate
        cols = list(df.columns)
        if 'rate_formula' in cols and 'interest_rate' in cols:
            # Remove rate_formula from current position
            cols.remove('rate_formula')
            # Insert after interest_rate
            ir_idx = cols.index('interest_rate')
            cols.insert(ir_idx + 1, 'rate_formula')
            df = df[cols]
        
        # Save back
        df.to_csv(filepath, index=False)
        return True
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

if __name__ == '__main__':
    output_dir = Path('output')
    csv_files = list(output_dir.glob('*_investments.csv'))
    
    print(f"Processing {len(csv_files)} CSV files...")
    
    success = 0
    for csv_file in csv_files:
        if add_rate_formula_to_file(csv_file):
            success += 1
            print(f"[OK] {csv_file.name}")
        else:
            print(f"[FAIL] {csv_file.name}")
    
    print(f"\nCompleted: {success}/{len(csv_files)} files processed")

