#!/usr/bin/env python3
"""
Generate static JSON datasets for the frontend from historical investments.

Outputs under: ../frontend/public/data/
- index.json
- {TICKER}/periods.json
- {TICKER}/latest.json
- {TICKER}/investments_{YYYY-MM-DD}.json
- {TICKER}/{TICKER}_all_periods.zip (JSON)
- {TICKER}/{TICKER}_all_periods_csv.zip (CSV)
"""

import os
import json
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional
import csv
import traceback
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

try:
    import yfinance as yf  # type: ignore
except Exception:
    yf = None  # optional dependency; profile generation will be skipped if missing

from historical_investment_extractor import HistoricalInvestmentExtractor
from financials_extractor import FinancialsExtractor
from bdc_config import BDC_UNIVERSE
from sec_api_client import SECAPIClient
import re

ROOT = os.path.dirname(os.path.dirname(__file__))
PUBLIC_DATA_DIR = os.path.join(ROOT, 'frontend', 'public', 'data')


def _safe_ticker_dir(ticker: str) -> str:
    d = os.path.join(PUBLIC_DATA_DIR, ticker.upper())
    os.makedirs(d, exist_ok=True)
    return d


def _group_by_period(investments: List[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = {}
    for inv in investments:
        period = getattr(inv, 'reporting_period', None) if not isinstance(inv, dict) else inv.get('reporting_period')
        if not period:
            continue
        grouped.setdefault(period, []).append(inv)
    return grouped


def _to_plain(row):
    if isinstance(row, dict):
        return row
    # Try dataclass-like / object with __dict__
    try:
        return {k: v for k, v in vars(row).items()}
    except Exception:
        # Fallback: try attribute names commonly used
        fields = [
            'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
            'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate',
            'reporting_period','filing_date','accession_number','commitment_limit','undrawn_commitment',
            'shares_units','percent_net_assets','currency',
            'geographic_location','credit_rating','payment_status'
        ]
        out = {}
        for f in fields:
            try:
                out[f] = getattr(row, f, None)
            except Exception:
                out[f] = None
        return out


def extract_financials_for_period(
    ticker: str,
    name: str,
    period: str,
    filing_date: str,
    accession_number: str,
    txt_url: str
) -> Optional[Dict]:
    """Extract financials for a specific period."""
    try:
        extractor = FinancialsExtractor()
        financials = extractor.extract_from_url(
            txt_url,
            ticker,
            name,
            reporting_period=period
        )
        financials['filing_date'] = filing_date
        financials['accession_number'] = accession_number
        financials['generated_at'] = datetime.now(timezone.utc).isoformat() + 'Z'
        return financials
    except Exception as e:
        print(f"Warning: failed to extract financials for {ticker} period {period}: {e}")
        traceback.print_exc()
        return None


def write_company_files(ticker: str, name: str, investments: List[Dict], 
                       filings_by_period: Dict[str, Dict] = None) -> Dict:
    """
    Write company data files.
    
    Args:
        ticker: Stock ticker
        name: Company name
        investments: List of investment dicts
        filings_by_period: Optional dict mapping period -> {txt_url, filing_date, accession_number}
    """
    out_dir = _safe_ticker_dir(ticker)
    grouped = _group_by_period(investments)

    periods = sorted(grouped.keys())
    latest = periods[-1] if periods else None
    
    # Extract filing info from investments if not provided
    if not filings_by_period:
        filings_by_period = {}
        for inv in investments:
            period = inv.get('reporting_period') if isinstance(inv, dict) else getattr(inv, 'reporting_period', None)
            if period and period not in filings_by_period:
                filings_by_period[period] = {
                    'filing_date': inv.get('filing_date') if isinstance(inv, dict) else getattr(inv, 'filing_date', None),
                    'accession_number': inv.get('accession_number') if isinstance(inv, dict) else getattr(inv, 'accession_number', None),
                }

    # Write period snapshots (JSON + CSV)
    csv_fieldnames = [
        'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
        'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate',
        'reporting_period','filing_date','accession_number','commitment_limit','undrawn_commitment',
        'shares_units','percent_net_assets','currency',
        'geographic_location','credit_rating','payment_status'
    ]

    for period, rows in grouped.items():
        plain_rows = [_to_plain(r) for r in rows]
        payload = {
            'ticker': ticker.upper(),
            'name': name,
            'period': period,
            'filing_date': plain_rows[0].get('filing_date') if plain_rows else None,
            'accession_number': plain_rows[0].get('accession_number') if plain_rows else None,
            'investments': plain_rows,
            'generated_at': datetime.now(timezone.utc).isoformat() + 'Z'
        }
        json_fname = os.path.join(out_dir, f"investments_{period}.json")
        with open(json_fname, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)

        csv_fname = os.path.join(out_dir, f"investments_{period}.csv")
        with open(csv_fname, 'w', newline='', encoding='utf-8') as fcsv:
            writer = csv.DictWriter(fcsv, fieldnames=csv_fieldnames)
            writer.writeheader()
            for r in plain_rows:
                writer.writerow({k: r.get(k, '') for k in csv_fieldnames})
        
        # Extract and write financials for this period
        filing_info = filings_by_period.get(period, {})
        if filing_info.get('txt_url'):
            financials = extract_financials_for_period(
                ticker, name, period,
                filing_info.get('filing_date'),
                filing_info.get('accession_number'),
                filing_info['txt_url']
            )
            if financials:
                financials_fname = os.path.join(out_dir, f"financials_{period}.json")
                with open(financials_fname, 'w', encoding='utf-8') as f:
                    json.dump(financials, f, ensure_ascii=False)

    # Write periods.json
    with open(os.path.join(out_dir, 'periods.json'), 'w', encoding='utf-8') as f:
        json.dump(periods, f)

    # Write latest.json
    latest_payload = {
        'ticker': ticker.upper(),
        'name': name,
        'latest_period': latest,
        'generated_at': datetime.now(timezone.utc).isoformat() + 'Z'
    }
    with open(os.path.join(out_dir, 'latest.json'), 'w', encoding='utf-8') as f:
        json.dump(latest_payload, f)

    # Zip all period JSONs (investments + financials)
    zip_json_path = os.path.join(out_dir, f"{ticker.upper()}_all_periods.zip")
    with zipfile.ZipFile(zip_json_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for period in periods:
            # Add investments file
            json_name = f"investments_{period}.json"
            json_path = os.path.join(out_dir, json_name)
            if os.path.exists(json_path):
                zf.write(json_path, arcname=json_name)
            # Add financials file if it exists
            financials_name = f"financials_{period}.json"
            financials_path = os.path.join(out_dir, financials_name)
            if os.path.exists(financials_path):
                zf.write(financials_path, arcname=financials_name)

    # Zip all period CSVs
    zip_csv_path = os.path.join(out_dir, f"{ticker.upper()}_all_periods_csv.zip")
    with zipfile.ZipFile(zip_csv_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for period in periods:
            csv_name = f"investments_{period}.csv"
            zf.write(os.path.join(out_dir, csv_name), arcname=csv_name)

    # Write Yahoo profile (optional)
    try:
        if yf is not None:
            t = yf.Ticker(ticker)
            info = t.info or {}
            price_keys = [
                'regularMarketPrice','regularMarketChange','regularMarketChangePercent','currency',
                'regularMarketPreviousClose','regularMarketOpen','regularMarketDayHigh','regularMarketDayLow'
            ]
            summary_keys = ['marketCap','dividendYield','trailingPE','forwardPE','beta']
            asset_keys = ['sector','industry','website','longBusinessSummary','city','state','country','fullTimeEmployees']

            def pick(src, keys):
                return {k: src.get(k) for k in keys if k in src}

            profile_payload = {
                'ticker': ticker.upper(),
                'name': name,
                'price': pick(info, price_keys),
                'summaryDetail': pick(info, summary_keys),
                'assetProfile': pick(info, asset_keys),
                'generated_at': datetime.now(timezone.utc).isoformat() + 'Z'
            }
            with open(os.path.join(out_dir, 'profile.json'), 'w', encoding='utf-8') as f:
                json.dump(profile_payload, f, ensure_ascii=False)
        else:
            # Note: yfinance not installed; skip
            pass
    except Exception:
        print(f"Warning: failed to write profile for {ticker}")
        traceback.print_exc()

    return {
        'ticker': ticker.upper(),
        'name': name,
        'periods': periods,
        'latest': latest
    }


def build_index(entries: List[Dict]):
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    idx = {
        'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
        'bdcs': entries
    }
    with open(os.path.join(PUBLIC_DATA_DIR, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False)


def process_single_ticker(bdc: Dict, years_back: int) -> Optional[Dict]:
    """Process a single ticker - can be run in parallel."""
    ticker = bdc['ticker']
    name = bdc['name']
    try:
        extractor = HistoricalInvestmentExtractor()
        sec_client = SECAPIClient()

        print(f"[{ticker}] Starting extraction...")

        # Extract investments
        investments = extractor.extract_historical_investments(ticker=ticker, years_back=years_back)
        if not investments:
            print(f"[{ticker}] No investments extracted")
            return None

        print(f"[{ticker}] Extracted {len(investments)} investments")

        # Get filing info for financials extraction
        filings_by_period: Dict[str, Dict] = {}
        filings = sec_client.get_historical_10q_filings(ticker, years_back=years_back)

        for filing_info in filings:
            txt_url = extractor._get_filing_txt_url(filing_info)
            if not txt_url:
                continue

            # Try to get period_end, but also store by filing_date
            try:
                response = requests.get(
                    txt_url,
                    headers={'User-Agent': 'BDC-Extractor/1.0 contact@example.com'},
                    timeout=30,
                )
                filing_content = response.text if response.status_code == 200 else None
            except Exception:
                filing_content = None

            period_end = extractor._extract_period_end_date(filing_info, filing_content)
            filing_date = filing_info['date']

            filing_data = {
                'txt_url': txt_url,
                'filing_date': filing_date,
                'accession_number': filing_info['accession'],
            }

            # Store by both period_end (if available) and filing_date
            if period_end:
                filings_by_period[period_end] = filing_data
            filings_by_period[filing_date] = filing_data

        print(f"[{ticker}] Writing files...")
        entry = write_company_files(ticker, name, investments, filings_by_period)
        print(f"[{ticker}] ✅ Complete - {len(entry.get('periods', []))} periods")
        return entry
    except Exception as e:
        print(f"[{ticker}] ❌ Error: {e}")
        traceback.print_exc()
        return None


def main(years_back: int = 5, tickers: List[str] = None, max_workers: int = 5):
    """
    Main function with parallel processing.
    
    Args:
        years_back: Number of years to look back
        tickers: Optional list of specific tickers to process
        max_workers: Number of parallel workers (default: 5 to respect SEC rate limits)
    """
    selected = [b for b in BDC_UNIVERSE if (not tickers or b['ticker'].upper() in [t.upper() for t in tickers])]
    
    print(f"Processing {len(selected)} BDCs with {max_workers} parallel workers...")
    print(f"Years back: {years_back}")
    print("="*80)
    
    entries: List[Dict] = []
    
    # Process tickers in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(process_single_ticker, bdc, years_back): bdc['ticker']
            for bdc in selected
        }
        
        # Process results as they complete
        completed = 0
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                entry = future.result()
                if entry:
                    entries.append(entry)
                completed += 1
                print(f"Progress: {completed}/{len(selected)} tickers completed")
            except Exception as e:
                print(f"[{ticker}] Failed with exception: {e}")
                traceback.print_exc()

    print("="*80)
    print(f"Building index for {len(entries)} BDCs...")
    build_index(entries)
    print(f"✅ Wrote index and company files to {PUBLIC_DATA_DIR}")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--years-back', type=int, default=5)
    p.add_argument('--ticker', action='append')
    p.add_argument('--max-workers', type=int, default=5, 
                   help='Number of parallel workers (default: 5, increase for faster processing but watch SEC rate limits)')
    args = p.parse_args()
    main(years_back=args.years_back, tickers=args.ticker, max_workers=args.max_workers)
