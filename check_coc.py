#!/usr/bin/env python3

from core.sec_api_client import SECAPIClient

client = SECAPIClient()

# Check recent preferred offerings for change of control provisions
tickers = ['KKR', 'APO', 'GTLS']

for ticker in tickers:
    print(f"\n=== {ticker} ===")
    try:
        filings = client.get_all_424b_filings(ticker, max_filings=3, filing_variants=['424B5', '424B3', '424B7'])

        for filing in filings[:2]:  # Check 2 most recent
            content = client.get_filing_by_accession(ticker, filing['accession'], filing['form'])
            if content:
                content_lower = content.lower()
                coc_terms = ['change of control', 'fundamental change']
                has_coc = any(term in content_lower for term in coc_terms)
                print(f"  {filing['date']} {filing['accession']}: Change of control: {has_coc}")
    except Exception as e:
        print(f"  Error: {e}")

