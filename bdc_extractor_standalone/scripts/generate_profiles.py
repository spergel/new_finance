#!/usr/bin/env python3
"""
Fetch Yahoo Finance profile/quote data for each BDC ticker and write
frontend-friendly JSON files to ../frontend/public/data/{TICKER}/profile.json

Intended to be run on a schedule (e.g., daily via GitHub Actions).
"""

import os
import json
from datetime import datetime
from typing import List, Dict
import traceback

ROOT = os.path.dirname(os.path.dirname(__file__))
PUBLIC_DATA_DIR = os.path.join(ROOT, 'frontend', 'public', 'data')

from bdc_config import BDC_UNIVERSE

try:
    import yfinance as yf  # type: ignore
except Exception as e:
    raise SystemExit("yfinance is required for generate_profiles.py. Install with: pip install yfinance")


def _safe_dir(ticker: str) -> str:
    d = os.path.join(PUBLIC_DATA_DIR, ticker.upper())
    os.makedirs(d, exist_ok=True)
    return d


def _pick(src: Dict, keys: List[str]) -> Dict:
    return {k: src.get(k) for k in keys if k in src}


def build_profile_payload(ticker: str, name: str) -> Dict:
    t = yf.Ticker(ticker)
    info = t.info or {}

    price_keys = [
        'regularMarketPrice','regularMarketChange','regularMarketChangePercent','currency',
        'regularMarketPreviousClose','regularMarketOpen','regularMarketDayHigh','regularMarketDayLow',
        'fiftyTwoWeekHigh','fiftyTwoWeekLow'
    ]
    summary_keys = ['marketCap','dividendYield','trailingPE','forwardPE','beta','bookValue']
    asset_keys = ['sector','industry','website','longBusinessSummary','city','state','country','fullTimeEmployees']

    return {
        'ticker': ticker.upper(),
        'name': name,
        'price': _pick(info, price_keys),
        'summaryDetail': _pick(info, summary_keys),
        'assetProfile': _pick(info, asset_keys),
        'generated_at': datetime.utcnow().isoformat() + 'Z',
    }


def write_profile(ticker: str, name: str) -> None:
    out_dir = _safe_dir(ticker)
    payload = build_profile_payload(ticker, name)
    with open(os.path.join(out_dir, 'profile.json'), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)


def main(tickers: List[str] | None = None) -> None:
    selected = [b for b in BDC_UNIVERSE if (not tickers or b['ticker'].upper() in {t.upper() for t in tickers})]
    for b in selected:
        ticker, name = b['ticker'], b['name']
        try:
            write_profile(ticker, name)
            print(f"Wrote profile for {ticker}")
        except Exception:
            print(f"Failed to write profile for {ticker}")
            traceback.print_exc()


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--ticker', action='append', help='Limit to one or more tickers')
    args = p.parse_args()
    main(tickers=args.ticker)












