#!/usr/bin/env python3
"""Analyze all facts extracted for investments."""

import csv
import json
import os
from collections import defaultdict

def analyze_ticker(ticker: str, facts_dir: str):
    """Analyze facts for a ticker."""
    filepath = os.path.join(facts_dir, f'{ticker}_all_facts.csv')
    
    if not os.path.exists(filepath):
        return None
    
    all_concepts = defaultdict(int)
    investments_with_facts = 0
    total_investments = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_investments += 1
            facts_json = row.get('all_facts_json', '{}')
            try:
                facts = json.loads(facts_json)
                if facts:
                    investments_with_facts += 1
                    for concept in facts.keys():
                        all_concepts[concept] += 1
            except:
                pass
    
    return {
        'ticker': ticker,
        'total_investments': total_investments,
        'investments_with_facts': investments_with_facts,
        'concepts': dict(all_concepts),
        'unique_concepts': len(all_concepts)
    }

def find_specific_investment(ticker: str, search_term: str, facts_dir: str):
    """Find a specific investment and show its facts."""
    filepath = os.path.join(facts_dir, f'{ticker}_all_facts.csv')
    
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if search_term.lower() in row.get('company_name', '').lower():
                facts_json = row.get('all_facts_json', '{}')
                try:
                    facts = json.loads(facts_json)
                    return {
                        'company_name': row.get('company_name', ''),
                        'context_ref': row.get('context_ref', ''),
                        'fact_count': row.get('fact_count', '0'),
                        'facts': facts
                    }
                except:
                    return {
                        'company_name': row.get('company_name', ''),
                        'context_ref': row.get('context_ref', ''),
                        'fact_count': row.get('fact_count', '0'),
                        'facts': {}
                    }
    return None

def main():
    """Main analysis."""
    facts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'xbrl_all_facts')
    
    tickers = ['WHF', 'ARCC', 'MAIN', 'MRCC', 'GLAD', 'OFS', 'OXSQ', 'PFX', 'PSEC', 'RAND', 'SCM', 'TPVG', 'TRIN']
    
    print("=" * 100)
    print("ALL FACTS ANALYSIS")
    print("=" * 100)
    
    # Analyze WHF specific investment
    print("\nWHF - RCKC Acquisitions LLC First Lien Secured Delayed Draw Loan:")
    print("-" * 100)
    whf_inv = find_specific_investment('WHF', 'RCKC Acquisitions LLC First Lien Secured Delayed Draw Loan', facts_dir)
    if whf_inv:
        print(f"Company: {whf_inv['company_name']}")
        print(f"Context: {whf_inv['context_ref']}")
        print(f"Total Facts: {whf_inv['fact_count']}")
        print(f"\nAll Fact Concepts ({len(whf_inv['facts'])}):")
        for concept, fact_data in sorted(whf_inv['facts'].items()):
            value = fact_data.get('value', '')
            unit = fact_data.get('unit', '')
            print(f"  {concept}: {value} {unit}")
    
    # Summary by ticker
    print("\n" + "=" * 100)
    print("SUMMARY BY TICKER")
    print("=" * 100)
    print(f"{'Ticker':<6} {'Investments':<12} {'With Facts':<12} {'Unique Concepts':<15} {'Top Concepts'}")
    print("-" * 100)
    
    for ticker in tickers:
        result = analyze_ticker(ticker, facts_dir)
        if result:
            top_concepts = sorted(result['concepts'].items(), key=lambda x: x[1], reverse=True)[:3]
            top_str = ', '.join([f"{c[0].split(':')[-1]}({c[1]})" for c in top_concepts])
            print(f"{ticker:<6} {result['total_investments']:<12} {result['investments_with_facts']:<12} {result['unique_concepts']:<15} {top_str}")

if __name__ == '__main__':
    main()

