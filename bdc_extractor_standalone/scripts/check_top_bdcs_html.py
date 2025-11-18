#!/usr/bin/env python3
"""Check HTML table availability for top BDCs with missing dates."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sec_api_client import SECAPIClient
from bs4 import BeautifulSoup
import requests

# Top BDCs with most missing dates (excluding ones that already have HTML parsing)
TOP_BDCS = [
    ('MSDL', 692),
    ('PFLT', 636),
    ('BBDC', 634),
    ('GBDC', 615),
    ('NMFC', 584),
    ('MSIF', 489),
    ('OCSL', 452),
    ('OBDC', 371),
    ('CSWC', 361),
    ('CGBD', 333),
]

def check_html_availability(ticker: str) -> tuple[bool, str, str]:
    """Check if HTML tables are available for a ticker."""
    try:
        client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
        cik = client.get_cik(ticker)
        if not cik:
            return False, "No CIK", ""
        
        index_url = client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            return False, "No 10-Q filing", ""
        
        documents = client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
        
        if not main_html:
            return False, "No HTML document", ""
        
        # Try to find schedule tables
        response = requests.get(main_html.url, headers={'User-Agent': 'BDC-Extractor/1.0'}, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        
        # Look for schedule of investments
        schedule_keywords = ['schedule', 'investment', 'portfolio company', 'company', 'business description']
        found_schedule = False
        table_info = ""
        
        for i, table in enumerate(tables[:20]):  # Check first 20 tables
            table_text = table.get_text().lower()
            if any(keyword in table_text for keyword in schedule_keywords):
                # Check if it has the right structure (company name, investment type, dates)
                rows = table.find_all('tr')
                if len(rows) > 5:  # Has enough rows to be a data table
                    headers = rows[0].find_all(['td', 'th'])
                    header_text = ' '.join([h.get_text().lower() for h in headers[:10]])
                    if 'company' in header_text and ('investment' in header_text or 'type' in header_text):
                        found_schedule = True
                        table_info = f"Table {i+1}: {len(rows)} rows, {len(headers)} cols"
                        break
        
        if found_schedule:
            return True, main_html.url, table_info
        else:
            return False, f"No schedule table found ({len(tables)} tables checked)", ""
    
    except Exception as e:
        return False, f"Error: {str(e)}", ""

if __name__ == '__main__':
    print("=" * 80)
    print("CHECKING HTML AVAILABILITY FOR TOP BDCs")
    print("=" * 80)
    print()
    
    results = []
    for ticker, missing_count in TOP_BDCS:
        print(f"Checking {ticker} ({missing_count} missing dates)...", end=" ")
        has_html, status, info = check_html_availability(ticker)
        status_icon = "[OK]" if has_html else "[NO]"
        print(status_icon)
        results.append((ticker, missing_count, has_html, status, info))
    
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    
    print("PRIORITY 1 - HTML Available (create custom parsers):")
    for ticker, missing, has_html, status, info in results:
        if has_html:
            print(f"  {ticker}: {missing} missing dates - {status}")
            if info:
                print(f"    {info}")
    
    print()
    print("PRIORITY 2 - No HTML (improve XBRL/fallback instead):")
    for ticker, missing, has_html, status, info in results:
        if not has_html:
            print(f"  {ticker}: {missing} missing dates - {status}")



