#!/usr/bin/env python3
"""
Fix remaining parsers to add 'investments' key to compact return statements.
"""

import os
import re

# Files with compact return statements that need fixing
FILES_TO_FIX = [
    'ofs_parser.py',
    'gain_parser.py',
    'oxsq_parser.py',
    'tpvg_parser.py',
    'pfx_parser.py',
    'icmb_parser.py',
    'lien_parser.py',
    'lrfc_parser.py',
    'psbd_parser.py',
    'rand_parser.py',
]

def fix_compact_return(filepath):
    """Fix compact return statements to add 'investments' key."""
    print(f"\nFixing {os.path.basename(filepath)}...")
    
    if not os.path.exists(filepath):
        print(f"  File not found")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already has 'investments'
    if "'investments'" in content or '"investments"' in content:
        print(f"  Already has 'investments' key")
        return True
    
    # Pattern: return {'company_name':...,'total_investments':len(invs),...}
    # Need to add 'investments':investment_dicts before 'total_investments'
    
    # Find all compact return statements
    pattern = r"return\s*\{'company_name':([^,]+),'cik':([^,]+),'total_investments':len\(([^)]+)\),([^}]+)\}"
    
    def add_investments(match):
        company = match.group(1)
        cik = match.group(2)
        inv_var = match.group(3)  # 'investments' or 'invs'
        rest = match.group(4)
        
        # Create conversion code
        conversion = f"# Convert {inv_var} to dict format\n        investment_dicts = [{{'company_name':x.company_name,'industry':standardize_industry(x.industry),'business_description':x.business_description,'investment_type':standardize_investment_type(x.investment_type),'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardize_reference_rate(x.reference_rate),'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate}} for x in {inv_var}]\n        "
        
        # Add 'investments' key before 'total_investments'
        new_return = f"return {{'company_name':{company},'cik':{cik},'total_investments':len({inv_var}),'investments':investment_dicts,{rest}}}"
        
        return conversion + new_return
    
    new_content = re.sub(pattern, add_investments, content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  Fixed: Added 'investments' key to return statements")
        return True
    else:
        print(f"  Could not find pattern to fix")
        return False

def main():
    """Fix all parser files."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    
    fixed = 0
    failed = 0
    
    for filename in FILES_TO_FIX:
        filepath = os.path.join(base_dir, filename)
        if fix_compact_return(filepath):
            fixed += 1
        else:
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"Fixed: {fixed}, Failed: {failed}")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()





