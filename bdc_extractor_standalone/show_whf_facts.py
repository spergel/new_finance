#!/usr/bin/env python3
"""Show all facts for a specific WHF investment."""

import csv
import json

filepath = '../output/xbrl_all_facts/WHF_all_facts.csv'

with open(filepath, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if 'RCKC Acquisitions LLC First Lien Secured Delayed Draw Loan' in row.get('company_name', ''):
            print(f"Investment: {row['company_name']}")
            print(f"Context: {row['context_ref']}")
            print(f"Fact Count: {row['fact_count']}")
            print(f"\nExtracted Fields:")
            print(f"  principal_amount: {row.get('principal_amount', '')}")
            print(f"  fair_value: {row.get('fair_value', '')}")
            print(f"  maturity_date: {row.get('maturity_date', '')}")
            print(f"  acquisition_date: {row.get('acquisition_date', '')}")
            print(f"  interest_rate: {row.get('interest_rate', '')}")
            print(f"  spread: {row.get('spread', '')}")
            
            print(f"\nAll Facts (JSON):")
            facts_json = row.get('all_facts_json', '{}')
            try:
                facts = json.loads(facts_json)
                for concept, fact_data in sorted(facts.items()):
                    value = fact_data.get('value', '')
                    unit = fact_data.get('unit', '')
                    print(f"  {concept}: {value} {unit}")
            except Exception as e:
                print(f"Error parsing JSON: {e}")
            
            print("\n" + "=" * 80)
            break

