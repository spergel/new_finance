#!/usr/bin/env python3
"""Summarize current status of BDC extraction."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.analyze_investments import summarize_directory

if __name__ == '__main__':
    print("=" * 80)
    print("BDC EXTRACTION STATUS SUMMARY")
    print("=" * 80)
    print()
    
    summarize_directory(Path('output'))
    
    print()
    print("=" * 80)
    print("PARSERS WITH HTML FALLBACK (for date extraction):")
    print("=" * 80)
    parsers_with_fallback = [
        'BBDC', 'GBDC', 'CCAP', 'GLAD', 'GAIN', 'GSBD', 'FSK',
        'NCDL', 'TCPC', 'BCSF', 'MSDL', 'CGBD', 'CION', 'FDUS',
        'OCSL', 'OBDC', 'CSWC'
    ]
    print(f"Total: {len(parsers_with_fallback)} parsers")
    print(", ".join(parsers_with_fallback))
    print()
    print("=" * 80)
    print("RECENT IMPROVEMENTS:")
    print("=" * 80)
    print("✓ Added rate_formula column to all CSVs (shows 'SOFR + 5%' or '12.3% Fixed')")
    print("✓ Fixed GLAD and GAIN date extraction (GLAD: 88.8% dates, GAIN: 95.2% dates)")
    print("✓ HTML fallback implemented for 17 parsers")
    print("✓ Removed exact duplicates from all files")
    print("✓ Standardized investment types across all parsers")
