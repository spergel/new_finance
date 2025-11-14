#!/usr/bin/env python3
"""
Validation script to check for parsing errors in investment types and business types.

This script analyzes BDC investment CSV files to identify:
1. Companies with inconsistent industries (parsing error indicator)
2. Suspicious company names that look like investment types or industries
3. Investment types that look like company names
4. Overall consistency patterns
"""

import csv
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Common investment type keywords (should not appear as company names)
INVESTMENT_TYPE_KEYWORDS = {
    'first lien', 'second lien', 'subordinated', 'senior secured', 'junior debt',
    'mezzanine', 'unitranche', 'revolver', 'term loan', 'delayed draw',
    'preferred', 'common', 'equity', 'warrant', 'warrants', 'debt', 'loan',
    'notes', 'bonds', 'sr secured', 'secured', 'unsecured'
}

# Common industry keywords (should not appear as company names)
INDUSTRY_KEYWORDS = {
    'software', 'technology', 'healthcare', 'health care', 'consumer',
    'services', 'financial', 'diversified', 'business', 'energy', 'real estate',
    'management', 'development', 'equipment', 'hardware', 'internet', 'media',
    'engineering', 'insurance', 'utilities', 'hotel', 'gaming', 'leisure',
    'transportation', 'cargo', 'chemicals', 'plastics', 'rubber', 'metals',
    'mining', 'containers', 'packaging', 'glass'
}

# Suspicious patterns that indicate parsing errors
SUSPICIOUS_COMPANY_PATTERNS = [
    r'^(First|Second|Subordinated|Senior|Junior|Mezzanine|Unitranche)',
    r'(Lien|Debt|Loan|Revolver|Term|Draw|Secured|Unsecured)$',
    r'^(Software|Technology|Hardware|Internet|Media|Engineering)',
    r'^(Diversified|Business|Consumer|Financial|Energy|Real Estate)',
    r'^(Equipment|Services|Management|Development|Insurance|Utilities)',
    r'^(Hotel|Gaming|Leisure|Transportation|Cargo|Chemicals)',
    r'^(Metals|Mining|Containers|Packaging|Glass)',
    r'^(Sr|Sr\.)\s+Secured',
    r'^Inc\.\s+Class\s+[A-Z]',
    r'^Preferred\s+Units?$',
    r'^Common\s+(Equity|Units?|Membership)?$',
    r'^Warrants?$',
    r'^Equity\s+(Securities)?$',
    r'^Debt\s+Investments?$',
]


def normalize_company_name(name: str) -> str:
    """Normalize company name for comparison."""
    if not name:
        return ""
    # Remove common suffixes and clean up
    name = re.sub(r'\s*\([^)]*\)\s*', '', name)  # Remove parentheticals
    name = re.sub(r'\s*,\s*(Inc\.?|LLC|L\.P\.|Corp\.?|Corporation|Company|Co\.?)\s*$', '', name, flags=re.IGNORECASE)
    return name.strip()


def is_suspicious_company_name(name: str) -> bool:
    """Check if a company name looks suspicious (might be an investment type or industry)."""
    if not name:
        return False
    
    name_lower = name.lower().strip()
    
    # Check against keywords
    for keyword in INVESTMENT_TYPE_KEYWORDS:
        if keyword in name_lower and len(name_lower) < 50:  # Short names with keywords are suspicious
            return True
    
    for keyword in INDUSTRY_KEYWORDS:
        if keyword in name_lower and len(name_lower) < 50:
            return True
    
    # Check against patterns
    for pattern in SUSPICIOUS_COMPANY_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    
    return False


def analyze_bdc_file(file_path: Path) -> Dict:
    """Analyze a single BDC investment file for inconsistencies."""
    results = {
        'file': str(file_path),
        'total_investments': 0,
        'companies': defaultdict(lambda: {
            'industries': set(),
            'investment_types': set(),
            'rows': []
        }),
        'suspicious_companies': [],
        'inconsistent_industries': [],
        'issues': []
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                results['total_investments'] += 1
                
                company_name = row.get('company_name', '').strip()
                industry = row.get('industry', '').strip()
                investment_type = row.get('investment_type', '').strip()
                
                if not company_name:
                    continue
                
                # Check for suspicious company names
                if is_suspicious_company_name(company_name):
                    results['suspicious_companies'].append({
                        'company': company_name,
                        'industry': industry,
                        'investment_type': investment_type,
                        'row_num': results['total_investments']
                    })
                
                # Track companies and their industries/investment types
                normalized_name = normalize_company_name(company_name)
                if normalized_name:
                    results['companies'][normalized_name]['industries'].add(industry if industry else 'Unknown')
                    results['companies'][normalized_name]['investment_types'].add(investment_type if investment_type else 'Unknown')
                    results['companies'][normalized_name]['rows'].append({
                        'company': company_name,
                        'industry': industry,
                        'investment_type': investment_type
                    })
        
        # Check for inconsistent industries (same company, different industries)
        for company, data in results['companies'].items():
            if len(data['industries']) > 1:
                # Filter out 'Unknown' - if all non-unknown industries are the same, it's OK
                non_unknown_industries = {ind for ind in data['industries'] if ind and ind != 'Unknown'}
                if len(non_unknown_industries) > 1:
                    results['inconsistent_industries'].append({
                        'company': company,
                        'industries': sorted(data['industries']),
                        'investment_types': sorted(data['investment_types']),
                        'count': len(data['rows'])
                    })
        
        # Generate summary
        if results['suspicious_companies']:
            results['issues'].append(f"Found {len(results['suspicious_companies'])} suspicious company names")
        if results['inconsistent_industries']:
            results['issues'].append(f"Found {len(results['inconsistent_industries'])} companies with inconsistent industries")
        
    except Exception as e:
        results['error'] = str(e)
        results['issues'].append(f"Error reading file: {e}")
    
    return results


def main():
    """Main validation function."""
    output_dir = Path(__file__).parent.parent / 'output'
    
    if not output_dir.exists():
        print(f"Output directory not found: {output_dir}")
        return
    
    # Get all investment CSV files
    investment_files = list(output_dir.glob('*_investments.csv'))
    historical_files = list(output_dir.glob('*_historical_investments.csv'))
    
    all_files = investment_files + historical_files
    
    if not all_files:
        print("No investment CSV files found in output directory")
        return
    
    print(f"Analyzing {len(all_files)} BDC investment files...\n")
    print("=" * 80)
    
    all_results = []
    total_suspicious = 0
    total_inconsistent = 0
    
    for file_path in sorted(all_files):
        results = analyze_bdc_file(file_path)
        all_results.append(results)
        
        bdc_name = file_path.stem.replace('_investments', '').replace('_historical_investments', '')
        
        if results.get('error'):
            print(f"\n[ERROR] {bdc_name}")
            print(f"   Error: {results['error']}")
            continue
        
        if not results['issues']:
            print(f"\n[OK] {bdc_name}: {results['total_investments']} investments - No issues found")
            continue
        
        print(f"\n[WARN] {bdc_name}: {results['total_investments']} investments")
        
        if results['suspicious_companies']:
            total_suspicious += len(results['suspicious_companies'])
            print(f"   [WARN] {len(results['suspicious_companies'])} suspicious company names:")
            for item in results['suspicious_companies'][:10]:  # Show first 10
                print(f"      - '{item['company']}' (Industry: {item['industry']}, Type: {item['investment_type']})")
            if len(results['suspicious_companies']) > 10:
                print(f"      ... and {len(results['suspicious_companies']) - 10} more")
        
        if results['inconsistent_industries']:
            total_inconsistent += len(results['inconsistent_industries'])
            print(f"   [WARN] {len(results['inconsistent_industries'])} companies with inconsistent industries:")
            for item in results['inconsistent_industries'][:10]:  # Show first 10
                print(f"      - '{item['company']}': {item['industries']} (appears {item['count']} times)")
            if len(results['inconsistent_industries']) > 10:
                print(f"      ... and {len(results['inconsistent_industries']) - 10} more")
    
    # Summary
    print("\n" + "=" * 80)
    print("\nSUMMARY")
    print("=" * 80)
    print(f"Total files analyzed: {len(all_files)}")
    print(f"Total suspicious company names: {total_suspicious}")
    print(f"Total companies with inconsistent industries: {total_inconsistent}")
    
    files_with_issues = sum(1 for r in all_results if r.get('issues'))
    print(f"Files with issues: {files_with_issues}")
    
    if total_suspicious > 0 or total_inconsistent > 0:
        print("\n[WARN] RECOMMENDATION: Review the flagged items above for potential parsing errors.")
        print("   Companies should have consistent industries across all their investments.")
        print("   Company names should not look like investment types or industries.")
    else:
        print("\n[OK] No issues found! All files appear to have consistent data.")


if __name__ == "__main__":
    main()

