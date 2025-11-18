#!/usr/bin/env python3
"""
Remove exact duplicate rows from all investment CSV files.
"""
import pandas as pd
from pathlib import Path

def remove_exact_duplicates(csv_path: Path) -> int:
    """Remove exact duplicate rows from a CSV file."""
    try:
        df = pd.read_csv(csv_path)
        original_count = len(df)
        
        # Remove exact duplicates, keeping first occurrence
        df_cleaned = df.drop_duplicates(keep='first')
        removed_count = original_count - len(df_cleaned)
        
        if removed_count > 0:
            df_cleaned.to_csv(csv_path, index=False)
            print(f"{csv_path.name}: Removed {removed_count} exact duplicates ({original_count} -> {len(df_cleaned)})")
            return removed_count
        return 0
    except Exception as e:
        print(f"Error processing {csv_path.name}: {e}")
        return 0

if __name__ == "__main__":
    output_dir = Path('output')
    csv_files = sorted(output_dir.glob('*_investments.csv'))
    
    total_removed = 0
    files_cleaned = 0
    
    print("=== Removing Exact Duplicates ===\n")
    
    for csv_file in csv_files:
        removed = remove_exact_duplicates(csv_file)
        if removed > 0:
            total_removed += removed
            files_cleaned += 1
    
    print(f"\n=== Summary ===")
    print(f"Files cleaned: {files_cleaned}")
    print(f"Total rows removed: {total_removed}")



