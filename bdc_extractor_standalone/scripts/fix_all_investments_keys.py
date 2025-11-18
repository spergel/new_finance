#!/usr/bin/env python3
"""
Fix all parsers to add 'investments' key to return dictionaries.
"""

import os
import re
import sys

# Files that need fixing - those with return statements that have 'total_investments' but no 'investments'
FILES_TO_FIX = {
    'nmfc_parser.py': 2,  # Has 2 return statements
    'trin_parser.py': 1,
    'bbdc_parser.py': 1,
    'cgbd_parser.py': 1,
    'bcsf_parser.py': 1,
    # Add more as needed
}

def fix_parser_file(filepath, num_returns=1):
    """Fix a parser file to add 'investments' key."""
    print(f"\nFixing {os.path.basename(filepath)}...")
    
    if not os.path.exists(filepath):
        print(f"  File not found")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Check if already has 'investments'
    if "'investments'" in content or '"investments"' in content:
        print(f"  Already has 'investments' key")
        return True
    
    # Find return statements with 'total_investments' but no 'investments'
    # Pattern: return {...'total_investments':...} (may be multi-line)
    
    # Look for the pattern where we have investments list and need to convert to dicts
    # or where we have normalized_rows
    
    # Strategy: Find where investments are built, then find the return statement after it
    # and add investment_dicts conversion
    
    # For parsers with dataclass investments, we need to convert them
    # For parsers with normalized_rows, we can use those directly
    
    fixed = False
    
    # Pattern 1: Has normalized_rows - just add it to return
    if 'normalized_rows' in content:
        # Find return statement and add 'investments': normalized_rows
        pattern = r"(return\s*\{[^}]*'total_investments':\s*len\(normalized_rows\),\s*)([^}]*\})"
        replacement = r"\1'investments': normalized_rows,\n            \2"
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"  Fixed: Added 'investments': normalized_rows")
            fixed = True
    
    # Pattern 2: Has investments list (dataclass instances) - need to convert
    if not fixed and 'investments: List[' in content and 'investment_dicts' not in content:
        # Find the return statement and add conversion code before it
        # Look for: logger.info(f"Saved to {out_file}")
        # Then: return {...}
        
        # Find the pattern where we write CSV and then return
        pattern = r"(logger\.info\(f\"Saved to \{out_file\}\"\)\s*\n\s*)(return\s*\{[^}]*'total_investments':\s*len\(investments\),\s*)([^}]*\})"
        
        def add_conversion(match):
            prefix = match.group(1)
            return_start = match.group(2)
            return_end = match.group(3)
            
            conversion_code = """        # Convert investments to dict format
        investment_dicts = []
        for inv in investments:
            standardized_inv_type = standardize_investment_type(inv.investment_type)
            standardized_industry = standardize_industry(inv.industry)
            standardized_ref_rate = standardize_reference_rate(inv.reference_rate)
            investment_dicts.append({
                'company_name': inv.company_name,
                'industry': standardized_industry,
                'business_description': inv.business_description,
                'investment_type': standardized_inv_type,
                'acquisition_date': inv.acquisition_date,
                'maturity_date': inv.maturity_date,
                'principal_amount': inv.principal_amount,
                'cost': inv.cost,
                'fair_value': inv.fair_value,
                'interest_rate': inv.interest_rate,
                'reference_rate': standardized_ref_rate,
                'spread': inv.spread,
                'floor_rate': inv.floor_rate,
                'pik_rate': inv.pik_rate,
            })
"""
            # Add 'investments' to return
            return_end = return_end.replace("'total_investments':", "'investments': investment_dicts,  # Add investments list for historical extractor\n            'total_investments':")
            
            return prefix + conversion_code + return_start + return_end
        
        new_content = re.sub(pattern, add_conversion, content, flags=re.DOTALL)
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"  Fixed: Added investment_dicts conversion")
            fixed = True
    
    # Pattern 3: Compact return statement (single line)
    if not fixed:
        # Look for: return {'company_name':...,'total_investments':len(investments),...}
        pattern = r"return\s*\{'company_name':([^,]+),'cik':([^,]+),'total_investments':len\(([^)]+)\),([^}]+)\}"
        
        def add_investments_compact(match):
            company = match.group(1)
            cik = match.group(2)
            inv_var = match.group(3)
            rest = match.group(4)
            
            # Check if inv_var is 'investments' (dataclass) or something else
            if inv_var == 'investments':
                # Need to convert
                return f"# Convert investments to dict format\n        investment_dicts = [{{'company_name': inv.company_name, 'industry': inv.industry, 'business_description': inv.business_description, 'investment_type': inv.investment_type, 'acquisition_date': inv.acquisition_date, 'maturity_date': inv.maturity_date, 'principal_amount': inv.principal_amount, 'cost': inv.cost, 'fair_value': inv.fair_value, 'interest_rate': inv.interest_rate, 'reference_rate': inv.reference_rate, 'spread': inv.spread, 'floor_rate': inv.floor_rate, 'pik_rate': inv.pik_rate}} for inv in investments]\n        return {{'company_name':{company},'cik':{cik},'total_investments':len({inv_var}),'investments':investment_dicts,{rest}}}"
            else:
                # Already a list of dicts
                return f"return {{'company_name':{company},'cik':{cik},'total_investments':len({inv_var}),'investments':{inv_var},{rest}}}"
        
        new_content = re.sub(pattern, add_investments_compact, content)
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"  Fixed: Added 'investments' to compact return")
            fixed = True
    
    if not fixed:
        print(f"  Could not auto-fix - needs manual inspection")
        return False
    
    return True

def main():
    """Fix all parser files."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    
    fixed = 0
    failed = 0
    
    for filename, num_returns in FILES_TO_FIX.items():
        filepath = os.path.join(base_dir, filename)
        if fix_parser_file(filepath, num_returns):
            fixed += 1
        else:
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"Fixed: {fixed}, Failed: {failed}")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()






