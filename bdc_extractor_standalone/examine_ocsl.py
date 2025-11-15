#!/usr/bin/env python3
"""Examine OCSL filing structure."""

import requests
from bs4 import BeautifulSoup
from sec_api_client import SECAPIClient

client = SECAPIClient()
cik = client.get_cik('OCSL')
index_url = client.get_filing_index_url('OCSL', '10-Q', cik=cik)
documents = client.get_documents_from_index(index_url)
main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)

if main_html:
    url = main_html.url
    headers = {'User-Agent': 'BDC-Extractor/1.0 contact@example.com'}
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.content, 'html.parser')
    
    # Find tables with investment-related keywords
    all_tables = soup.find_all('table')
    print(f"Found {len(all_tables)} total tables\n")
    
    # Look for investment schedule tables
    for i, table in enumerate(all_tables):
        table_text = table.get_text(' ', strip=True).lower()
        rows = table.find_all('tr')
        
        if any(kw in table_text for kw in ['schedule of investments', 'portfolio company', 'type of investment', 'fair value']):
            if len(rows) > 10:
                print(f"Table {i+1}: {len(rows)} rows")
                # Show header row
                for j, row in enumerate(rows[:10]):
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(' ', strip=True) for cell in cells]
                    if any(kw in ' '.join(cell_texts).lower() for kw in ['company', 'investment', 'type', 'principal', 'cost', 'fair value']):
                        print(f"  Header row (row {j+1}):")
                        for k, text in enumerate(cell_texts[:15]):
                            print(f"    Col {k}: {text[:50]}")
                        print()
                        # Show a few data rows
                        print("  Sample data rows:")
                        for k in range(j+1, min(j+6, len(rows))):
                            data_cells = rows[k].find_all(['td', 'th'])
                            data_texts = [cell.get_text(' ', strip=True) for cell in data_cells]
                            if any(data_texts):
                                print(f"    Row {k+1}: {data_texts[:8]}")
                        break
                print()

