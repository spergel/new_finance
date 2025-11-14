#!/usr/bin/env python3
"""
Script to batch update all parsers to use standardization.
This adds the import and applies standardization to writer.writerow calls.
"""

import re
import os
from pathlib import Path

# List of parsers we've already updated
UPDATED_PARSERS = ['bcsf_parser.py', 'ccap_parser.py', 'cgbd_parser.py', 'fdus_parser.py']

# Standard import statement
STANDARD_IMPORT = """from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)"""

# Pattern to find and replace writer.writerow sections
def update_parser_file(filepath: str) -> bool:
    """Update a parser file to use standardization."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Step 1: Add standardization import
    if 'from standardization import' not in content:
        # Find the import section
        import_pattern = r'(from sec_api_client import SECAPIClient\s+)(logger = logging\.getLogger)'
        if re.search(import_pattern, content):
            content = re.sub(
                r'(from sec_api_client import SECAPIClient)\s+(logger = logging\.getLogger)',
                r'\1\nfrom standardization import standardize_investment_type, standardize_industry, standardize_reference_rate\n\n\2',
                content
            )
    
    # Step 2: Find and update writer.writerow calls
    # Pattern 1: Direct writerow with inv object
    writerow_pattern1 = r'(writer\.writeheader\(\)\s+for inv in (?:investments|result\[\'investments\'\]):\s+)(writer\.writerow\(\{)'
    if re.search(writerow_pattern1, content, re.DOTALL):
        # Check if standardization is already applied
        if 'standardized_inv_type = standardize_investment_type' not in content:
            content = re.sub(
                r'(writer\.writeheader\(\)\s+for inv in (?:investments|result\[\'investments\'\]):\s+)(writer\.writerow\(\{)',
                r'\1# Apply standardization\n                standardized_inv_type = standardize_investment_type(inv.investment_type)\n                standardized_industry = standardize_industry(inv.industry)\n                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)\n                \n                \2',
                content,
                flags=re.DOTALL
            )
            
            # Update the writerow dict to use standardized values
            content = re.sub(
                r"('industry':\s+)inv\.industry,",
                r"\1standardized_industry,",
                content
            )
            content = re.sub(
                r"('investment_type':\s+)inv\.investment_type,",
                r"\1standardized_inv_type,",
                content
            )
            content = re.sub(
                r"('reference_rate':\s+)inv\.reference_rate,",
                r"\1standardized_ref_rate,",
                content
            )
    
    # Pattern 2: Using self._strip_footnote_refs
    if "'industry': self._strip_footnote_refs(inv.industry)" in content:
        if 'standardized_inv_type = standardize_investment_type' not in content:
            content = re.sub(
                r"(writer\.writeheader\(\)\s+for inv in investments:\s+)",
                r"\1# Apply standardization\n                standardized_inv_type = standardize_investment_type(self._strip_footnote_refs(inv.investment_type))\n                standardized_industry = standardize_industry(self._strip_footnote_refs(inv.industry))\n                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)\n                \n                ",
                content,
                flags=re.DOTALL
            )
            content = re.sub(
                r"('industry':\s+)self\._strip_footnote_refs\(inv\.industry\),",
                r"\1standardized_industry,",
                content
            )
            content = re.sub(
                r"('investment_type':\s+)self\._strip_footnote_refs\(inv\.investment_type\),",
                r"\1standardized_inv_type,",
                content
            )
            content = re.sub(
                r"('reference_rate':\s+)inv\.reference_rate,",
                r"\1standardized_ref_rate,",
                content
            )
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

if __name__ == '__main__':
    parser_dir = Path(__file__).parent
    parser_files = list(parser_dir.glob('*_parser.py'))
    
    updated_count = 0
    for parser_file in sorted(parser_files):
        if parser_file.name in UPDATED_PARSERS:
            print(f"Skipping {parser_file.name} (already updated)")
            continue
            
        print(f"Updating {parser_file.name}...")
        if update_parser_file(str(parser_file)):
            updated_count += 1
            print(f"  ✓ Updated {parser_file.name}")
        else:
            print(f"  - No changes needed for {parser_file.name}")
    
    print(f"\nUpdated {updated_count} parser files.")

"""
Script to batch update all parsers to use standardization.
This adds the import and applies standardization to writer.writerow calls.
"""

import re
import os
from pathlib import Path

# List of parsers we've already updated
UPDATED_PARSERS = ['bcsf_parser.py', 'ccap_parser.py', 'cgbd_parser.py', 'fdus_parser.py']

# Standard import statement
STANDARD_IMPORT = """from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)"""

# Pattern to find and replace writer.writerow sections
def update_parser_file(filepath: str) -> bool:
    """Update a parser file to use standardization."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Step 1: Add standardization import
    if 'from standardization import' not in content:
        # Find the import section
        import_pattern = r'(from sec_api_client import SECAPIClient\s+)(logger = logging\.getLogger)'
        if re.search(import_pattern, content):
            content = re.sub(
                r'(from sec_api_client import SECAPIClient)\s+(logger = logging\.getLogger)',
                r'\1\nfrom standardization import standardize_investment_type, standardize_industry, standardize_reference_rate\n\n\2',
                content
            )
    
    # Step 2: Find and update writer.writerow calls
    # Pattern 1: Direct writerow with inv object
    writerow_pattern1 = r'(writer\.writeheader\(\)\s+for inv in (?:investments|result\[\'investments\'\]):\s+)(writer\.writerow\(\{)'
    if re.search(writerow_pattern1, content, re.DOTALL):
        # Check if standardization is already applied
        if 'standardized_inv_type = standardize_investment_type' not in content:
            content = re.sub(
                r'(writer\.writeheader\(\)\s+for inv in (?:investments|result\[\'investments\'\]):\s+)(writer\.writerow\(\{)',
                r'\1# Apply standardization\n                standardized_inv_type = standardize_investment_type(inv.investment_type)\n                standardized_industry = standardize_industry(inv.industry)\n                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)\n                \n                \2',
                content,
                flags=re.DOTALL
            )
            
            # Update the writerow dict to use standardized values
            content = re.sub(
                r"('industry':\s+)inv\.industry,",
                r"\1standardized_industry,",
                content
            )
            content = re.sub(
                r"('investment_type':\s+)inv\.investment_type,",
                r"\1standardized_inv_type,",
                content
            )
            content = re.sub(
                r"('reference_rate':\s+)inv\.reference_rate,",
                r"\1standardized_ref_rate,",
                content
            )
    
    # Pattern 2: Using self._strip_footnote_refs
    if "'industry': self._strip_footnote_refs(inv.industry)" in content:
        if 'standardized_inv_type = standardize_investment_type' not in content:
            content = re.sub(
                r"(writer\.writeheader\(\)\s+for inv in investments:\s+)",
                r"\1# Apply standardization\n                standardized_inv_type = standardize_investment_type(self._strip_footnote_refs(inv.investment_type))\n                standardized_industry = standardize_industry(self._strip_footnote_refs(inv.industry))\n                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)\n                \n                ",
                content,
                flags=re.DOTALL
            )
            content = re.sub(
                r"('industry':\s+)self\._strip_footnote_refs\(inv\.industry\),",
                r"\1standardized_industry,",
                content
            )
            content = re.sub(
                r"('investment_type':\s+)self\._strip_footnote_refs\(inv\.investment_type\),",
                r"\1standardized_inv_type,",
                content
            )
            content = re.sub(
                r"('reference_rate':\s+)inv\.reference_rate,",
                r"\1standardized_ref_rate,",
                content
            )
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

if __name__ == '__main__':
    parser_dir = Path(__file__).parent
    parser_files = list(parser_dir.glob('*_parser.py'))
    
    updated_count = 0
    for parser_file in sorted(parser_files):
        if parser_file.name in UPDATED_PARSERS:
            print(f"Skipping {parser_file.name} (already updated)")
            continue
            
        print(f"Updating {parser_file.name}...")
        if update_parser_file(str(parser_file)):
            updated_count += 1
            print(f"  ✓ Updated {parser_file.name}")
        else:
            print(f"  - No changes needed for {parser_file.name}")
    
    print(f"\nUpdated {updated_count} parser files.")























