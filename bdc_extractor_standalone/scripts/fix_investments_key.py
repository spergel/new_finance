#!/usr/bin/env python3
"""
Fix all parsers to include 'investments' key in their return dictionaries.
"""

import os
import re
import ast
import sys

# List of parsers that need fixing (those that return dicts but might not have 'investments')
PARSERS_TO_CHECK = [
    'tcpc_parser.py', 'nmfc_parser.py', 'gsbd_parser.py', 'psec_parser.py',
    'pflt_parser.py', 'fdus_parser.py', 'slrc_parser.py', 'cion_parser.py',
    'bcsf_parser.py', 'cgbd_parser.py', 'gbdc_parser.py', 'bbdc_parser.py',
    'obdc_parser.py', 'trin_parser.py', 'ncdl_parser.py', 'tslx_parser.py',
    'mfic_parser.py', 'gain_parser.py', 'ocsl_parser.py'
]

def find_return_dict_with_total_investments(filepath):
    """Find return statements that have 'total_investments' but no 'investments'."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find return statements with 'total_investments'
    pattern = r'return\s*\{[^}]*\'total_investments\':[^}]*\}'
    matches = re.finditer(pattern, content, re.DOTALL)
    
    fixes_needed = []
    for match in matches:
        return_block = match.group(0)
        # Check if 'investments' is already in the return
        if "'investments'" not in return_block and '"investments"' not in return_block:
            fixes_needed.append((match.start(), match.end(), return_block))
    
    return fixes_needed

def fix_parser(filepath):
    """Fix a parser file to add 'investments' key."""
    print(f"\nChecking {filepath}...")
    
    if not os.path.exists(filepath):
        print(f"  File not found: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        content = ''.join(lines)
    
    # Look for return statements in extract_from_url or extract_from_html_url methods
    # Pattern: return { ... 'total_investments': len(investments), ... }
    
    # Find the method that contains the return statement
    # We need to find where investments are built and convert them to dicts
    
    # Try to find the pattern where investments list exists but not in return
    # Look for: total_investments = len(investments) or similar
    
    # More targeted: find return dicts that have total_investments but check context
    fixes = find_return_dict_with_total_investments(filepath)
    
    if not fixes:
        # Check if it already has investments key
        if "'investments'" in content or '"investments"' in content:
            print(f"  Already has 'investments' key")
            return True
        else:
            print(f"  No return dict with 'total_investments' found or already fixed")
            return False
    
    # For now, let's manually fix the common pattern
    # We'll look for the pattern and add investments conversion
    
    # Pattern 1: investments is a list of objects (dataclass instances)
    # We need to convert them to dicts
    
    # Pattern 2: investments is already a list of dicts
    # We just need to add it to the return
    
    # Let's check what type investments is
    if 'investment_dicts' in content or 'normalized_rows' in content:
        # Already converting to dicts, just need to add to return
        pattern = r"('total_investments':\s*len\([^)]+\)),\s*\n\s*('total_principal':)"
        replacement = r"\1,\n            'investments': investment_dicts if 'investment_dicts' in locals() else normalized_rows if 'normalized_rows' in locals() else investments,\n            \2"
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"  Fixed: Added 'investments' key")
            return True
    
    print(f"  Needs manual fix - couldn't auto-detect pattern")
    return False

def main():
    """Fix all parsers."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    
    fixed = 0
    skipped = 0
    
    for parser_file in PARSERS_TO_CHECK:
        filepath = os.path.join(base_dir, parser_file)
        if fix_parser(filepath):
            fixed += 1
        else:
            skipped += 1
    
    print(f"\n{'='*80}")
    print(f"Fixed: {fixed}, Skipped: {skipped}")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()






