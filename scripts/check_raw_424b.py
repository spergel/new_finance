#!/usr/bin/env python3
"""Check raw 424B filings for missing details."""
import sys
sys.path.insert(0, '.')

from core.sec_api_client import SECAPIClient
import re

def extract_key_info(text, ticker, series):
    """Extract key information from 424B text."""
    print(f"\n{'='*80}")
    print(f"{ticker} Series {series} - KEY INFORMATION FROM 424B")
    print("="*80)
    
    # Look for dividend rate
    div_patterns = [
        r'(\d+\.?\d*)\s*%.*?per\s+annum',
        r'dividend.*?rate.*?(\d+\.?\d*)\s*%',
        r'Series\s+' + series + r'.*?(\d+\.?\d*)\s*%',
    ]
    
    print("\n[DIVIDEND INFORMATION]")
    for pattern in div_patterns:
        matches = re.finditer(pattern, text[:20000], re.IGNORECASE | re.DOTALL)
        for match in matches:
            context_start = max(0, match.start() - 100)
            context_end = min(len(text), match.end() + 100)
            context = text[context_start:context_end].replace('\n', ' ')
            print(f"  Found: {match.group(0)[:150]}")
            break
    
    # Look for liquidation preference
    print("\n[LIQUIDATION PREFERENCE]")
    liq_patterns = [
        r'liquidation.*?preference.*?\$?([\d,]+\.?\d*)',
        r'\$?([\d,]+\.?\d*).*?per.*?share.*?liquidation',
        r'stated.*?value.*?\$?([\d,]+\.?\d*)',
    ]
    
    for pattern in liq_patterns:
        matches = re.finditer(pattern, text[:20000], re.IGNORECASE | re.DOTALL)
        for match in matches:
            context_start = max(0, match.start() - 100)
            context_end = min(len(text), match.end() + 100)
            context = text[context_start:context_end].replace('\n', ' ')
            print(f"  Found: {context[:200]}")
            break
    
    # Look for outstanding shares
    print("\n[SHARES OUTSTANDING]")
    shares_patterns = [
        r'([\d,]+)\s+shares.*?outstanding',
        r'outstanding.*?([\d,]+)\s+shares',
        r'issued.*?([\d,]+)\s+shares',
    ]
    
    for pattern in shares_patterns:
        matches = re.finditer(pattern, text[:30000], re.IGNORECASE)
        count = 0
        for match in matches:
            if count < 3:  # Show first 3 matches
                context_start = max(0, match.start() - 80)
                context_end = min(len(text), match.end() + 80)
                context = text[context_start:context_end].replace('\n', ' ')
                print(f"  Found: {context[:200]}")
                count += 1
    
    # Look for call date
    print("\n[CALL/REDEMPTION DATE]")
    call_patterns = [
        r'(on\s+or\s+after|after|beginning|commencing).*?(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
        r'redemption.*?date.*?(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
        r'callable.*?(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
    ]
    
    for pattern in call_patterns:
        matches = re.finditer(pattern, text[:30000], re.IGNORECASE)
        count = 0
        for match in matches:
            if count < 2:  # Show first 2 matches
                context_start = max(0, match.start() - 100)
                context_end = min(len(text), match.end() + 100)
                context = text[context_start:context_end].replace('\n', ' ')
                print(f"  Found: {context[:250]}")
                count += 1
    
    # Look for credit enhancement or special features
    print("\n[SPECIAL FEATURES / RISKS]")
    risk_keywords = ['dividend stopper', 'mandatory redemption', 'sinking fund', 
                     'subordinat', 'junior', 'defeasance', 'covenant']
    
    for keyword in risk_keywords:
        if keyword.lower() in text[:50000].lower():
            # Find context
            idx = text[:50000].lower().find(keyword.lower())
            context_start = max(0, idx - 100)
            context_end = min(len(text), idx + 200)
            context = text[context_start:context_end].replace('\n', ' ')
            print(f"  {keyword.upper()}: {context[:250]}")


def main():
    client = SECAPIClient()
    
    # B. Riley Series B
    print("\n" + "="*80)
    print("FETCHING B. RILEY SERIES B - 424B5")
    print("="*80)
    try:
        content = client.get_filing_by_accession('RILY', '0001213900-20-025061', '424B5')
        print(f"Retrieved {len(content):,} characters")
        extract_key_info(content, 'RILY', 'B')
    except Exception as e:
        print(f"Error: {e}")
    
    # Sotherly Series D
    print("\n\n" + "="*80)
    print("FETCHING SOTHERLY HOTELS SERIES D - 424B5")
    print("="*80)
    try:
        content = client.get_filing_by_accession('SOHO', '0001193125-19-105308', '424B5')
        print(f"Retrieved {len(content):,} characters")
        extract_key_info(content, 'SOHO', 'D')
    except Exception as e:
        print(f"Error: {e}")
    
    # Presidio Series D
    print("\n\n" + "="*80)
    print("FETCHING PRESIDIO PROPERTY SERIES D - 424B5")
    print("="*80)
    try:
        content = client.get_filing_by_accession('SQFT', '0001493152-24-024885', '424B5')
        print(f"Retrieved {len(content):,} characters")
        extract_key_info(content, 'SQFT', 'D')
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()

