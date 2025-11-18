#!/usr/bin/env python3
"""Assess feasibility of creating custom HTML parsers for all BDCs."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
from pathlib import Path
from sec_api_client import SECAPIClient
from bs4 import BeautifulSoup
import requests

def get_parsers_with_html():
    """Get list of parsers that already use HTML parsing."""
    html_parsers = [
        'arcc', 'htgc', 'mrcc', 'trin', 'ssss', 'tpvg', 'tslx', 'whf', 'ncdl'
    ]
    return html_parsers

def get_parsers_with_xbrl_only():
    """Get list of parsers that use XBRL only (might benefit from HTML)."""
    xbrl_only = [
        'bbdc', 'bcsf', 'ccap', 'cgbd', 'cion', 'cswc', 'fdus', 'fsk', 'gbdc',
        'glad', 'gain', 'gsbd', 'lrfc', 'msdl', 'msif', 'nmfc', 'obdc', 'ocsl',
        'pflt', 'psec', 'trin', 'whf'
    ]
    return xbrl_only

def check_html_availability(ticker: str) -> tuple[bool, str]:
    """Check if HTML tables are available for a ticker."""
    try:
        client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
        cik = client.get_cik(ticker)
        if not cik:
            return False, "No CIK"
        
        index_url = client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            return False, "No 10-Q filing"
        
        documents = client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
        
        if not main_html:
            return False, "No HTML document"
        
        # Try to find schedule tables
        response = requests.get(main_html.url, headers={'User-Agent': 'BDC-Extractor/1.0'})
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        
        # Look for schedule of investments
        schedule_keywords = ['schedule', 'investment', 'portfolio company']
        found_schedule = False
        for table in tables[:10]:  # Check first 10 tables
            table_text = table.get_text().lower()
            if any(keyword in table_text for keyword in schedule_keywords):
                found_schedule = True
                break
        
        return found_schedule, main_html.url if found_schedule else "No schedule table found"
    
    except Exception as e:
        return False, f"Error: {str(e)}"

def analyze_missing_dates():
    """Analyze which BDCs have the most missing dates."""
    csv_files = list(Path('output').glob('*_investments.csv'))
    
    results = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            ticker = csv_file.stem.split('_')[0]
            
            total = len(df)
            missing_acq = df['acquisition_date'].isna().sum()
            missing_mat = df['maturity_date'].isna().sum()
            missing_any = (df['acquisition_date'].isna() & df['maturity_date'].isna()).sum()
            
            results.append({
                'ticker': ticker,
                'total': total,
                'missing_acq': missing_acq,
                'missing_mat': missing_mat,
                'missing_any': missing_any,
                'pct_missing': 100 * missing_any / total if total > 0 else 0
            })
        except Exception as e:
            print(f"Error processing {csv_file}: {e}")
    
    return pd.DataFrame(results).sort_values('missing_any', ascending=False)

if __name__ == '__main__':
    print("=" * 80)
    print("CUSTOM PARSER FEASIBILITY ASSESSMENT")
    print("=" * 80)
    print()
    
    # Analyze missing dates
    print("Analyzing missing dates...")
    df = analyze_missing_dates()
    
    print("\nTop 15 BDCs with most missing dates:")
    print(df.head(15).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("FEASIBILITY ASSESSMENT")
    print("=" * 80)
    print()
    print("EASY (Already have HTML parsing):")
    html_parsers = get_parsers_with_html()
    print(f"   {len(html_parsers)} parsers: {', '.join(html_parsers)}")
    print()
    
    print("MEDIUM (XBRL-only, but HTML available):")
    print("   These would benefit from custom HTML parsers:")
    top_candidates = df.head(10)
    for _, row in top_candidates.iterrows():
        ticker = row['ticker'].upper()
        if ticker.lower() not in html_parsers:
            has_html, status = check_html_availability(ticker)
            status_icon = "[OK]" if has_html else "[NO]"
            print(f"   {status_icon} {ticker}: {row['missing_any']} missing dates ({row['pct_missing']:.1f}%) - {status}")
    
    print()
    print("=" * 80)
    print("ESTIMATED EFFORT")
    print("=" * 80)
    print()
    print("For each custom parser:")
    print("  1. Extract sample HTML table (5 min)")
    print("  2. Analyze table structure (10 min)")
    print("  3. Write custom parser (30-60 min)")
    print("  4. Test and debug (15-30 min)")
    print("  Total: ~1-2 hours per parser")
    print()
    print(f"Top 10 candidates: ~10-20 hours total")
    print()
    print("RECOMMENDATION:")
    print("  Start with top 5-10 BDCs with most missing dates")
    print("  Focus on ones where HTML tables are clearly available")
    print("  Use ARCC custom parser as a template")

