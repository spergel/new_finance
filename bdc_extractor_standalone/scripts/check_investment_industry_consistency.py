#!/usr/bin/env python3
"""
Check for consistency in investment types and industries across BDCs.

This script identifies potential parsing errors by:
1. Checking if investment types and industries are consistent for each BDC
2. Looking for cases where investment types look like industries (or vice versa)
3. Finding unusual variations that might indicate parsing errors
"""

import os
import sys
import csv
import json
import glob
from collections import defaultdict
from typing import Dict, List, Set

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from standardization import standardize_investment_type, standardize_industry

# Known industry names (to detect if they're being used as investment types)
KNOWN_INDUSTRIES = {
    'Software', 'Healthcare & Pharmaceuticals', 'Business Services', 'Consumer Services',
    'Diversified Financial Services', 'Technology', 'Media', 'Retail', 'Energy',
    'Aerospace & Defense', 'Automotive', 'Construction & Building', 'Food & Beverage',
    'Real Estate', 'Telecommunications', 'Transportation', 'Wholesale', 'Distribution'
}

# Known investment types (to detect if they're being used as industries)
KNOWN_INVESTMENT_TYPES = {
    'First Lien Debt', 'Second Lien Debt', 'Subordinated Debt', 'Unsecured Debt',
    'Common Equity', 'Preferred Equity', 'Warrants', 'Unitranche'
}


def analyze_bdc_data(csv_file: str) -> Dict:
    """Analyze investment types and industries for a single BDC."""
    ticker = os.path.basename(csv_file).split('_')[0].upper()
    
    investment_types = defaultdict(int)
    industries = defaultdict(int)
    investment_type_raw = defaultdict(set)  # Track raw values before standardization
    industry_raw = defaultdict(set)
    
    # Track potential errors
    potential_errors = {
        'industry_as_investment_type': [],
        'investment_type_as_industry': [],
        'unusual_investment_types': [],
        'unusual_industries': [],
        'numeric_investment_types': [],  # Investment types that are just numbers
        'html_entities': [],  # Investment types/industries with HTML entities
        'reference_rate_as_investment_type': [],  # Reference rates used as investment types
    }
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                inv_type = row.get('investment_type', '').strip()
                industry = row.get('industry', '').strip()
                
                if inv_type:
                    investment_types[inv_type] += 1
                    investment_type_raw[inv_type].add(inv_type)
                    
                    # Check if investment type looks like an industry
                    if inv_type in KNOWN_INDUSTRIES:
                        potential_errors['industry_as_investment_type'].append({
                            'company': row.get('company_name', ''),
                            'investment_type': inv_type,
                            'industry': industry
                        })
                    
                    # Check for numeric investment types (likely parsing error)
                    if inv_type.strip().isdigit():
                        potential_errors['numeric_investment_types'].append({
                            'company': row.get('company_name', ''),
                            'investment_type': inv_type,
                            'industry': industry
                        })
                    
                    # Check for HTML entities
                    if '&#' in inv_type or '&amp;' in inv_type or '&lt;' in inv_type or '&gt;' in inv_type:
                        potential_errors['html_entities'].append({
                            'company': row.get('company_name', ''),
                            'investment_type': inv_type,
                            'industry': industry
                        })
                    
                    # Check for reference rates used as investment types
                    ref_rate_keywords = ['LIBOR', 'SOFR', 'PRIME', 'EURIBOR', 'FED FUNDS', 'CDOR', 'BASE RATE']
                    if any(keyword in inv_type.upper() for keyword in ref_rate_keywords):
                        if not any(inv_keyword in inv_type.upper() for inv_keyword in ['DEBT', 'LOAN', 'NOTE', 'EQUITY', 'WARRANT']):
                            potential_errors['reference_rate_as_investment_type'].append({
                                'company': row.get('company_name', ''),
                                'investment_type': inv_type,
                                'industry': industry
                            })
                    
                    # Check for unusual investment types
                    if inv_type not in KNOWN_INVESTMENT_TYPES and not any(
                        known in inv_type for known in KNOWN_INVESTMENT_TYPES
                    ):
                        if inv_type not in ['Unknown', ''] and not inv_type.strip().isdigit():
                            potential_errors['unusual_investment_types'].append(inv_type)
                
                if industry:
                    industries[industry] += 1
                    industry_raw[industry].add(industry)
                    
                    # Check if industry looks like an investment type
                    if industry in KNOWN_INVESTMENT_TYPES:
                        potential_errors['investment_type_as_industry'].append({
                            'company': row.get('company_name', ''),
                            'investment_type': inv_type,
                            'industry': industry
                        })
                    
                    # Check for HTML entities
                    if '&#' in industry or '&amp;' in industry or '&lt;' in industry or '&gt;' in industry:
                        potential_errors['html_entities'].append({
                            'company': row.get('company_name', ''),
                            'investment_type': inv_type,
                            'industry': industry
                        })
                    
                    # Check for unusual industries
                    if industry not in KNOWN_INDUSTRIES and not any(
                        known in industry for known in KNOWN_INDUSTRIES
                    ):
                        if industry not in ['Unknown', '']:
                            potential_errors['unusual_industries'].append(industry)
    
    except Exception as e:
        return {'error': str(e)}
    
    return {
        'ticker': ticker,
        'investment_types': dict(investment_types),
        'industries': dict(industries),
        'investment_type_count': len(investment_types),
        'industry_count': len(industries),
        'potential_errors': potential_errors
    }


def check_consistency_across_periods(ticker: str, data_dir: str = 'frontend/public/data') -> Dict:
    """Check if investment types and industries are consistent across periods for a ticker."""
    ticker_dir = os.path.join(data_dir, ticker)
    if not os.path.exists(ticker_dir):
        return {'error': f'No data directory found for {ticker}'}
    
    # Find all investment JSON files
    json_files = glob.glob(os.path.join(ticker_dir, 'investments_*.json'))
    
    all_investment_types = set()
    all_industries = set()
    period_investment_types = defaultdict(set)
    period_industries = defaultdict(set)
    
    for json_file in json_files:
        period = os.path.basename(json_file).replace('investments_', '').replace('.json', '')
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                investments = data.get('investments', [])
                
                for inv in investments:
                    inv_type = inv.get('investment_type', '').strip()
                    industry = inv.get('industry', '').strip()
                    
                    if inv_type:
                        all_investment_types.add(inv_type)
                        period_investment_types[period].add(inv_type)
                    
                    if industry:
                        all_industries.add(industry)
                        period_industries[period].add(industry)
        except Exception as e:
            continue
    
    # Check for consistency
    inconsistencies = {
        'investment_types_vary': len(all_investment_types) > 20,  # More than 20 different types might indicate issues
        'industries_vary': len(all_industries) > 30,  # More than 30 different industries might indicate issues
        'investment_types': sorted(all_investment_types),
        'industries': sorted(all_industries),
        'period_count': len(json_files)
    }
    
    return inconsistencies


def main():
    """Main analysis function."""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    frontend_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', 'public', 'data')
    
    # Find all CSV files
    csv_files = glob.glob(os.path.join(output_dir, '*_investments.csv'))
    
    print("="*80)
    print("INVESTMENT TYPE AND INDUSTRY CONSISTENCY CHECK")
    print("="*80)
    print()
    
    results = {}
    all_errors = defaultdict(list)
    
    for csv_file in csv_files:
        ticker = os.path.basename(csv_file).split('_')[0].upper()
        print(f"Analyzing {ticker}...")
        
        result = analyze_bdc_data(csv_file)
        if 'error' in result:
            print(f"  ERROR: {result['error']}")
            continue
        
        results[ticker] = result
        
        # Check for errors
        errors = result['potential_errors']
        if errors['industry_as_investment_type']:
            all_errors['industry_as_investment_type'].extend([
                (ticker, err) for err in errors['industry_as_investment_type']
            ])
        
        if errors['investment_type_as_industry']:
            all_errors['investment_type_as_industry'].extend([
                (ticker, err) for err in errors['investment_type_as_industry']
            ])
        
        if errors['numeric_investment_types']:
            all_errors['numeric_investment_types'].extend([
                (ticker, err) for err in errors['numeric_investment_types']
            ])
        
        if errors['html_entities']:
            all_errors['html_entities'].extend([
                (ticker, err) for err in errors['html_entities']
            ])
        
        if errors['reference_rate_as_investment_type']:
            all_errors['reference_rate_as_investment_type'].extend([
                (ticker, err) for err in errors['reference_rate_as_investment_type']
            ])
        
        # Print summary
        print(f"  Investment Types: {result['investment_type_count']} unique")
        print(f"  Industries: {result['industry_count']} unique")
        
        if errors['industry_as_investment_type']:
            print(f"  WARNING: {len(errors['industry_as_investment_type'])} cases where industry used as investment type")
        
        if errors['investment_type_as_industry']:
            print(f"  WARNING: {len(errors['investment_type_as_industry'])} cases where investment type used as industry")
        
        if errors['numeric_investment_types']:
            print(f"  WARNING: {len(errors['numeric_investment_types'])} cases where investment type is just a number")
        
        if errors['html_entities']:
            print(f"  WARNING: {len(errors['html_entities'])} cases with HTML entities")
        
        if errors['reference_rate_as_investment_type']:
            print(f"  WARNING: {len(errors['reference_rate_as_investment_type'])} cases where reference rate used as investment type")
        
        # Show top investment types and industries
        top_inv_types = sorted(result['investment_types'].items(), key=lambda x: -x[1])[:5]
        top_industries = sorted(result['industries'].items(), key=lambda x: -x[1])[:5]
        
        print(f"  Top Investment Types: {', '.join([f'{k}({v})' for k, v in top_inv_types])}")
        print(f"  Top Industries: {', '.join([f'{k}({v})' for k, v in top_industries])}")
        print()
    
    # Print error summary
    print("="*80)
    print("ERROR SUMMARY")
    print("="*80)
    
    if all_errors['industry_as_investment_type']:
        print(f"\nWARNING: Industry used as Investment Type ({len(all_errors['industry_as_investment_type'])} cases):")
        for ticker, err in all_errors['industry_as_investment_type'][:10]:  # Show first 10
            print(f"  {ticker}: {err['company'][:50]} - Investment Type: '{err['investment_type']}', Industry: '{err['industry']}'")
        if len(all_errors['industry_as_investment_type']) > 10:
            print(f"  ... and {len(all_errors['industry_as_investment_type']) - 10} more")
    
    if all_errors['investment_type_as_industry']:
        print(f"\nWARNING: Investment Type used as Industry ({len(all_errors['investment_type_as_industry'])} cases):")
        for ticker, err in all_errors['investment_type_as_industry'][:10]:  # Show first 10
            print(f"  {ticker}: {err['company'][:50]} - Investment Type: '{err['investment_type']}', Industry: '{err['industry']}'")
        if len(all_errors['investment_type_as_industry']) > 10:
            print(f"  ... and {len(all_errors['investment_type_as_industry']) - 10} more")
    
    if all_errors['numeric_investment_types']:
        print(f"\n⚠️  Numeric Investment Types ({len(all_errors['numeric_investment_types'])} cases):")
        for ticker, err in all_errors['numeric_investment_types'][:10]:
            print(f"  {ticker}: {err['company'][:50]} - Investment Type: '{err['investment_type']}', Industry: '{err['industry']}'")
        if len(all_errors['numeric_investment_types']) > 10:
            print(f"  ... and {len(all_errors['numeric_investment_types']) - 10} more")
    
    if all_errors['html_entities']:
        print(f"\n⚠️  HTML Entities in Data ({len(all_errors['html_entities'])} cases):")
        for ticker, err in all_errors['html_entities'][:10]:
            print(f"  {ticker}: {err['company'][:50]} - Investment Type: '{err['investment_type']}', Industry: '{err['industry']}'")
        if len(all_errors['html_entities']) > 10:
            print(f"  ... and {len(all_errors['html_entities']) - 10} more")
    
    if all_errors['reference_rate_as_investment_type']:
        print(f"\n⚠️  Reference Rate used as Investment Type ({len(all_errors['reference_rate_as_investment_type'])} cases):")
        for ticker, err in all_errors['reference_rate_as_investment_type'][:10]:
            print(f"  {ticker}: {err['company'][:50]} - Investment Type: '{err['investment_type']}', Industry: '{err['industry']}'")
        if len(all_errors['reference_rate_as_investment_type']) > 10:
            print(f"  ... and {len(all_errors['reference_rate_as_investment_type']) - 10} more")
    
    # Check consistency across periods for a few tickers
    print("\n" + "="*80)
    print("CONSISTENCY ACROSS PERIODS")
    print("="*80)
    
    sample_tickers = list(results.keys())[:10]  # Check first 10
    for ticker in sample_tickers:
        consistency = check_consistency_across_periods(ticker, frontend_data_dir)
        if 'error' not in consistency:
            print(f"\n{ticker}:")
            print(f"  Periods: {consistency['period_count']}")
            print(f"  Unique Investment Types: {len(consistency['investment_types'])}")
            print(f"  Unique Industries: {len(consistency['industries'])}")
            
            if consistency['investment_types_vary']:
                print(f"  ⚠️  WARNING: High variation in investment types ({len(consistency['investment_types'])} unique)")
                print(f"     Sample: {', '.join(consistency['investment_types'][:10])}")
            
            if consistency['industries_vary']:
                print(f"  ⚠️  WARNING: High variation in industries ({len(consistency['industries'])} unique)")
                print(f"     Sample: {', '.join(consistency['industries'][:10])}")
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)


if __name__ == '__main__':
    main()

