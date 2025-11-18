#!/usr/bin/env python3
"""
Script to systematically update all XBRL parsers with new fields:
- shares_units
- percent_net_assets
- currency
- commitment_limit
- undrawn_commitment
"""

import re
import os
from pathlib import Path

# List of parsers to update (those with XBRL extraction)
PARSERS_TO_UPDATE = [
    'cswc_parser.py',
    'cgbd_parser.py',
    'obdc_parser.py',
    'gbdc_parser.py',
    'psec_parser.py',
    'cion_parser.py',
    'ocsl_parser.py',
    'gsbd_parser.py',
    'bbdc_parser.py',
    'nmfc_parser.py',
    'slrc_parser.py',
    'pflt_parser.py',
    'mrcc_parser.py',
    'ofs_parser.py',
    'gain_parser.py',
    'oxsq_parser.py',
    'tpvg_parser.py',
    'pfx_parser.py',
    'icmb_parser.py',
    'lien_parser.py',
    'lrfc_parser.py',
    'psbd_parser.py',
    'ncdl_parser.py',
]

def update_dataclass(content: str, class_name: str) -> str:
    """Add new fields to Investment dataclass."""
    # Find the dataclass definition
    pattern = rf'@dataclass\s+class {class_name}Investment:.*?(?=\nclass|\n@|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return content
    
    dataclass_content = match.group(0)
    
    # Check if fields already exist
    if 'shares_units' in dataclass_content:
        return content  # Already updated
    
    # Find the last field before closing
    # Look for context_ref or the last field
    if 'context_ref' in dataclass_content:
        # Insert before context_ref
        new_fields = """    shares_units: Optional[str] = None
    percent_net_assets: Optional[str] = None
    currency: Optional[str] = None
    commitment_limit: Optional[float] = None
    undrawn_commitment: Optional[float] = None
    context_ref: Optional[str] = None"""
        dataclass_content = re.sub(
            r'(\s+context_ref: Optional\[str\] = None)',
            new_fields,
            dataclass_content
        )
    else:
        # Append at the end
        new_fields = """
    shares_units: Optional[str] = None
    percent_net_assets: Optional[str] = None
    currency: Optional[str] = None
    commitment_limit: Optional[float] = None
    undrawn_commitment: Optional[float] = None"""
        # Find the last field and add after it
        dataclass_content = re.sub(
            r'(\s+pik_rate: Optional\[str\] = None)',
            r'\1' + new_fields,
            dataclass_content
        )
    
    # Replace in original content
    return content[:match.start()] + dataclass_content + content[match.end():]

def update_extract_facts(content: str) -> str:
    """Update _extract_facts to capture unitRef for currency."""
    # Update standard XBRL pattern
    old_pattern = r'(sp = re\.compile\(r\'<\(\[^>\s:\]+:\[^>\s\]\+\)\[^>\]\*contextRef="\(\[^"\]\*\)"\[^>\]\*>\(\[^<\]\*\)</\\1>\', re\.DOTALL\))'
    new_pattern = r'sp = re.compile(r\'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\\1>\', re.DOTALL)'
    
    # Check if already updated
    if 'unitRef="([^"]*)"' in content:
        return content
    
    # Update the pattern
    content = re.sub(
        r'sp = re\.compile\(r\'<\(\[^>\s:\]+:\[^>\s\]\+\)\[^>\]\*contextRef="\(\[^"\]\*\)"\[^>\]\*>\(\[^<\]\*\)</\\1>\'',
        r"sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef=\"([^\"]*)\"[^>]*(?:unitRef=\"([^\"]*)\")?[^>]*>([^<]*)</\\1>'",
        content
    )
    
    # Update the loop to capture unitRef
    old_loop = r'for (concept|match), cref, val in sp\.findall\(content\):'
    if re.search(old_loop, content):
        # Replace with match-based approach
        content = re.sub(
            r'for (concept|match), cref, val in sp\.findall\(content\):',
            r'for match in sp.finditer(content):',
            content
        )
        # Update the body
        content = re.sub(
            r'(\s+)concept = match\.group\(1\)\s+cref = match\.group\(2\)\s+val = match\.group\(3\)',
            r'\1concept = match.group(1)\n\1cref = match.group(2)\n\1unit_ref = match.group(3)\n\1val = match.group(4)',
            content
        )
        # Add currency extraction
        content = re.sub(
            r'(\s+if val and cref:\s+)(facts\[cref\]\.append\(\{\'concept\': concept, \'value\': val\.strip\(\)\}\))',
            r'\1fact_entry = {\'concept\': concept, \'value\': val.strip()}\n\1if unit_ref:\n\1    currency_match = re.search(r\'\\b([A-Z]{3})\\b\', unit_ref.upper())\n\1    if currency_match:\n\1        fact_entry[\'currency\'] = currency_match.group(1)\n\1facts[cref].append(fact_entry)',
            content
        )
    
    # Update ix:nonFraction pattern
    old_ix = r'ixp = re\.compile\(r\'<ix:nonFraction\[^>\]\*?name="\(\[^"\]\+\)"\[^>\]\*?contextRef="\(\[^"\]\+\)"\[^>\]\*?\(?:id="\(\[^"\]\+\)"\)\?\[^>\]\*>(.*?)</ix:nonFraction>\''
    if re.search(old_ix, content) and 'unitRef' not in content:
        content = re.sub(
            r'ixp = re\.compile\(r\'<ix:nonFraction\[^>\]\*?name="\(\[^"\]\+\)"\[^>\]\*?contextRef="\(\[^"\]\+\)"\[^>\]\*?\(?:id="\(\[^"\]\+\)"\)\?\[^>\]\*>(.*?)</ix:nonFraction>\'',
            r"ixp = re.compile(r'<ix:nonFraction[^>]*?name=\"([^\"]+)\"[^>]*?contextRef=\"([^\"]+)\"[^>]*?(?:unitRef=\"([^\"]*)\")?[^>]*?(?:id=\"([^\"]+)\")?[^>]*>(.*?)</ix:nonFraction>'",
            content
        )
        # Update the loop
        content = re.sub(
            r'name = m\.group\(1\); cref = m\.group\(2\); html = m\.group\(4\)',
            r'name = m.group(1); cref = m.group(2); unit_ref = m.group(3); html = m.group(5)',
            content
        )
        # Add currency extraction in fact entry
        content = re.sub(
            r'(\s+if txt:\s+)(facts\[cref\]\.append\(\{\'concept\': name, \'value\': txt\}\))',
            r'\1fact_entry = {\'concept\': name, \'value\': txt}\n\1if unit_ref:\n\1    currency_match = re.search(r\'\\b([A-Z]{3})\\b\', unit_ref.upper())\n\1    if currency_match:\n\1        fact_entry[\'currency\'] = currency_match.group(1)\n\1facts[cref].append(fact_entry)',
            content
        )
    
    return content

def update_build_investment(content: str) -> str:
    """Update _build_investment to extract new fields."""
    # Find the return statement location
    return_pattern = r'if inv\.company_name and \(inv\.principal_amount or inv\.cost or inv\.fair_value\):\s+return inv\s+return None'
    
    if not re.search(return_pattern, content):
        return content
    
    # Check if already updated
    if 'Extract shares/units' in content and 'shares_units' in content:
        return content
    
    # Add extraction logic before return
    extraction_code = """
        # Extract shares/units and currency from facts
        for f in facts:
            c = f['concept']; v = f['value']; cl = c.lower()
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val = v.replace(',', '').strip()
                    float(shares_val)  # Validate
                    inv.shares_units = shares_val
                except: pass
            if 'currency' in f:
                inv.currency = f.get('currency')
        
        # Extract commitment_limit and undrawn_commitment for revolvers
        if 'revolving' in inv.investment_type.lower() or 'revolver' in inv.investment_type.lower():
            if inv.fair_value and not inv.principal_amount:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value
            elif inv.principal_amount and inv.fair_value:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value - inv.principal_amount if inv.fair_value > inv.principal_amount else 0
        
"""
    
    content = re.sub(
        r'(if inv\.company_name and \(inv\.principal_amount or inv\.cost or inv\.fair_value\):)',
        extraction_code + r'\1',
        content
    )
    
    return content

def update_return_dict(content: str, class_name: str) -> str:
    """Update return dictionary to include new fields."""
    # Find investment_dicts.append or similar
    pattern = rf"investment_dicts\.append\(\{{[^}}]*'pik_rate':[^}}]*\}}\)"
    
    if not re.search(pattern, content, re.DOTALL):
        return content
    
    # Check if already updated
    if "'shares_units':" in content:
        return content
    
    # Add new fields
    content = re.sub(
        r"('pik_rate': inv\.pik_rate,)\s*\}\)",
        r"\1\n                'shares_units': inv.shares_units,\n                'percent_net_assets': inv.percent_net_assets,\n                'currency': inv.currency,\n                'commitment_limit': inv.commitment_limit,\n                'undrawn_commitment': inv.undrawn_commitment,\n            })",
        content
    )
    
    return content

def main():
    base_dir = Path(__file__).parent.parent
    
    for parser_file in PARSERS_TO_UPDATE:
        parser_path = base_dir / parser_file
        if not parser_path.exists():
            print(f"Skipping {parser_file} - not found")
            continue
        
        print(f"Updating {parser_file}...")
        
        with open(parser_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Extract class name from filename
        class_name = parser_file.replace('_parser.py', '').upper()
        
        # Update dataclass
        content = update_dataclass(content, class_name)
        
        # Update _extract_facts
        content = update_extract_facts(content)
        
        # Update _build_investment
        content = update_build_investment(content)
        
        # Update return dict
        content = update_return_dict(content, class_name)
        
        if content != original_content:
            with open(parser_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  Updated {parser_file}")
        else:
            print(f"  No changes needed for {parser_file}")

if __name__ == '__main__':
    main()





