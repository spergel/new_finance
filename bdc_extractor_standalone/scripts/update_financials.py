#!/usr/bin/env python3
"""Quick script to update financials with full statements."""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financials_extractor import FinancialsExtractor

# HTGC filing info
ticker = "HTGC"
name = "Hercules Capital Inc"
period = "2025-10-23"
txt_url = "https://www.sec.gov/Archives/edgar/data/0001280784/000128078425000041/0001280784-25-000041.txt"
filing_date = "2025-10-30"
accession_number = "0001280784-25-000041"

# Extract
extractor = FinancialsExtractor()
financials = extractor.extract_from_url(txt_url, ticker, name, reporting_period=period)
financials['filing_date'] = filing_date
financials['accession_number'] = accession_number

# Save
out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', 'public', 'data', ticker.upper())
os.makedirs(out_dir, exist_ok=True)
fname = os.path.join(out_dir, f"financials_{period}.json")
with open(fname, 'w', encoding='utf-8') as f:
    json.dump(financials, f, ensure_ascii=False, indent=2)

print(f"✅ Saved financials to {fname}")
print(f"📊 Full income statement items: {len(financials.get('full_income_statement', {}))}")
print(f"💰 Full cash flow statement items: {len(financials.get('full_cash_flow_statement', {}))}")









