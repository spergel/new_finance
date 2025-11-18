#!/usr/bin/env python3
"""
Generate all data files for all BDCs:
- investments_<period>.json from CSV files
- financials_<period>.json from SEC filings
- Update index.json
"""

import os
import json
import csv
import glob
from datetime import datetime, timezone
from typing import Dict, List, Optional
import traceback
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(ROOT, 'output')
PUBLIC_DATA_DIR = os.path.join(ROOT, 'frontend', 'public', 'data')

# Add parent directory to path for imports
import sys
sys.path.insert(0, ROOT)

from bdc_config import BDC_UNIVERSE


def load_csv_investments(csv_path: str) -> List[Dict]:
    """Load investments from CSV file."""
    investments = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                for field in ['principal_amount', 'cost', 'amortized_cost', 'fair_value']:
                    if field in row and row[field]:
                        try:
                            row[field] = float(row[field].replace(',', ''))
                        except (ValueError, AttributeError):
                            row[field] = None
                
                # Use cost if amortized_cost is missing
                if not row.get('amortized_cost') and row.get('cost'):
                    row['amortized_cost'] = row['cost']
                
                investments.append(row)
    except Exception as e:
        print(f"Error loading CSV {csv_path}: {e}")
    return investments


def generate_investments_json_from_csv(ticker: str, csv_path: str, period: str = None) -> Optional[Dict]:
    """Generate investments JSON from CSV file."""
    investments = load_csv_investments(csv_path)
    if not investments:
        return None
    
    # Try to infer period from filename or use latest
    if not period:
        # Check if filename has date pattern
        import re
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', csv_path)
        if date_match:
            period = date_match.group(1)
        else:
            period = datetime.now().strftime('%Y-%m-%d')
    
    # Try to load existing JSON to get metadata (form_type, accession_number, etc.)
    json_path = os.path.join(PUBLIC_DATA_DIR, ticker.upper(), f'investments_{period}.json')
    metadata = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                metadata = {
                    'filing_date': existing.get('filing_date'),
                    'accession_number': existing.get('accession_number'),
                    'form_type': existing.get('form_type'),
                }
        except:
            pass
    
    return {
        'ticker': ticker.upper(),
        'name': None,  # Will be filled from BDC_UNIVERSE
        'period': period,
        'filing_date': metadata.get('filing_date'),
        'accession_number': metadata.get('accession_number'),
        'form_type': metadata.get('form_type'),
        'investments': investments,
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }


def find_csv_files(ticker: str) -> List[str]:
    """Find all CSV files for a ticker."""
    pattern = os.path.join(OUTPUT_DIR, f'{ticker}_*_investments.csv')
    return glob.glob(pattern)


def ensure_ticker_dir(ticker: str) -> str:
    """Ensure ticker directory exists."""
    d = os.path.join(PUBLIC_DATA_DIR, ticker.upper())
    os.makedirs(d, exist_ok=True)
    return d


def process_ticker(ticker: str, name: str, extract_financials: bool = False):
    """Process a single ticker: generate investments JSON from CSV files."""
    print(f"\nProcessing {ticker} ({name})...")
    
    csv_files = find_csv_files(ticker)
    if not csv_files:
        print(f"  ⚠️  No CSV files found for {ticker}")
        return None
    
    ticker_dir = ensure_ticker_dir(ticker)
    periods = []
    
    # Process each CSV file
    for csv_path in sorted(csv_files):
        try:
            # Extract period and form_type from filename
            # Pattern: HTGC_YYYY_MM_DD_10_K_investments.csv or HTGC_YYYY_MM_DD_10_Q_investments.csv
            import re
            # Try pattern with underscores first (HTGC_2024_02_15_10_K_investments.csv)
            date_match = re.search(r'(\d{4})_(\d{2})_(\d{2})', os.path.basename(csv_path))
            if date_match:
                year, month, day = date_match.groups()
                period = f"{year}-{month}-{day}"
            else:
                # Try pattern with hyphens (YYYY-MM-DD)
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', csv_path)
                if date_match:
                    period = date_match.group(1)
                else:
                    # Use file modification time as fallback
                    mtime = os.path.getmtime(csv_path)
                    period = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
            
            # Extract form_type from filename (10-K or 10-Q)
            form_type_match = re.search(r'10[_-]([KQ])', os.path.basename(csv_path), re.IGNORECASE)
            form_type = None
            if form_type_match:
                form_type = f"10-{form_type_match.group(1).upper()}"
            
            # Generate JSON
            data = generate_investments_json_from_csv(ticker, csv_path, period)
            if not data:
                continue
            
            data['name'] = name
            # Set form_type from filename if not already set
            if form_type and not data.get('form_type'):
                data['form_type'] = form_type
            
            # Write JSON
            json_path = os.path.join(ticker_dir, f'investments_{period}.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            periods.append(period)
            print(f"  ✅ Generated investments_{period}.json ({len(data['investments'])} investments)")
            
            # Extract financials if requested
            if extract_financials:
                try:
                    from scripts.extract_financials_edgar import extract_financials_simple
                    # Get form_type from investment data
                    form_type = data.get('form_type')
                    accession_number = data.get('accession_number')
                    
                    print(f"  Extracting financials for {period} (form_type: {form_type})...")
                    financials = extract_financials_simple(
                        ticker, 
                        period, 
                        accession_number=accession_number,
                        form_type=form_type
                    )
                    
                    if financials:
                        # Save JSON
                        financials_json_path = os.path.join(ticker_dir, f'financials_{period}.json')
                        with open(financials_json_path, 'w', encoding='utf-8') as f:
                            json.dump(financials, f, ensure_ascii=False, indent=2)
                        print(f"  ✅ Generated financials_{period}.json")
                        
                        # CSVs are already saved by extract_financials_simple
                    else:
                        print(f"  ⚠️  Could not extract financials for {period}")
                except Exception as e:
                    print(f"  ⚠️  Error extracting financials for {period}: {e}")
                    traceback.print_exc()
            
        except Exception as e:
            print(f"  ❌ Error processing {csv_path}: {e}")
            traceback.print_exc()
    
    if not periods:
        return None
    
    # Write periods.json
    periods.sort()
    periods_path = os.path.join(ticker_dir, 'periods.json')
    with open(periods_path, 'w', encoding='utf-8') as f:
        json.dump(periods, f)
    
    # Write latest.json
    latest_path = os.path.join(ticker_dir, 'latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump({
            'ticker': ticker.upper(),
            'name': name,
            'latest_period': periods[-1] if periods else None,
            'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ Generated periods.json and latest.json ({len(periods)} periods)")
    
    return {
        'ticker': ticker.upper(),
        'name': name,
        'periods': periods,
        'latest': periods[-1] if periods else None
    }


def build_index(entries: List[Dict]):
    """Build and write index.json."""
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    index_path = os.path.join(PUBLIC_DATA_DIR, 'index.json')
    
    index = {
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'bdcs': entries
    }
    
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Generated index.json with {len(entries)} BDCs")


def main(tickers: List[str] = None, extract_financials: bool = False):
    """Main entry point."""
    print("=" * 60)
    print("Generating All BDC Data")
    print("=" * 60)
    
    entries = []
    selected = [b for b in BDC_UNIVERSE if (not tickers or b['ticker'].upper() in [t.upper() for t in tickers])]
    
    for bdc in selected:
        ticker = bdc['ticker']
        name = bdc['name']
        
        try:
            entry = process_ticker(ticker, name, extract_financials)
            if entry:
                entries.append(entry)
        except Exception as e:
            print(f"❌ Error processing {ticker}: {e}")
            traceback.print_exc()
            continue
    
    build_index(entries)
    print(f"\n✅ Done! Processed {len(entries)} BDCs")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate all data files for BDCs')
    parser.add_argument('--ticker', action='append', help='Process specific ticker(s)')
    parser.add_argument('--financials', action='store_true', help='Also extract financials (requires SEC API)')
    args = parser.parse_args()
    
    main(tickers=args.ticker, extract_financials=args.financials)

