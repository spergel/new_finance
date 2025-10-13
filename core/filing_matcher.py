#!/usr/bin/env python3
"""
Filing Matcher Module

Simple regex-based matching of 424B filings to securities from 10-Q.
Just looks for series mentions in the first 1000 characters of filings.
"""

import re
import logging
from typing import List, Dict, Optional
from core.sec_api_client import SECAPIClient

logger = logging.getLogger(__name__)


def match_series_to_424b(ticker: str, series_names: List[str], max_filings: int = 20) -> List[Dict]:
    """
    Find the BEST 424B filing for each series.

    Args:
        ticker: Company ticker
        series_names: List of series names (e.g., ["A", "B", "Series C"])
        max_filings: Maximum number of filings to check

    Returns:
        List of best matched filings - one per series
    """
    logger.info(f"Finding best 424B filings for {ticker} series: {series_names}")

    client = SECAPIClient()

    # Get recent 424B filings
    filings = client.get_all_424b_filings(
        ticker,
        max_filings=max_filings,
        filing_variants=['424B5', '424B3', '424B7']  # Actual issuances only
    )

    if not filings:
        logger.warning(f"No 424B filings found for {ticker}")
        return []

    # For each series, find the best matching filing
    best_filings_per_series = {}

    for filing in filings:
        try:
            # Get filing content
            content = client.get_filing_by_accession(ticker, filing['accession'], filing['form'])
            if not content:
                continue

            # Check first 1000 characters for series mentions
            header_text = content[:1000].lower()

            for series in series_names:
                series_lower = series.lower()
                # Handle both "Series A" and "A" formats
                patterns = [
                    rf'\bseries\s+{re.escape(series_lower)}\b',
                    rf'\b{re.escape(series_lower)}\s+series\b',
                ]

                found_match = False
                for pattern in patterns:
                    if re.search(pattern, header_text):
                        found_match = True
                        break

                if found_match:
                    # Choose the best filing for this series (prefer more recent)
                    if series not in best_filings_per_series:
                        best_filings_per_series[series] = filing.copy()
                        best_filings_per_series[series]['content'] = content
                        best_filings_per_series[series]['matched_series'] = [series]
                        logger.info(f"Found filing for Series {series}: {filing['form']} ({filing['date']})")
                    else:
                        # Keep the more recent filing
                        existing_date = best_filings_per_series[series]['date']
                        if filing['date'] > existing_date:
                            best_filings_per_series[series] = filing.copy()
                            best_filings_per_series[series]['content'] = content
                            best_filings_per_series[series]['matched_series'] = [series]

        except Exception as e:
            logger.error(f"Error processing filing {filing.get('accession')}: {e}")
            continue

    # Return the best filing for each series
    matched_filings = list(best_filings_per_series.values())
    logger.info(f"Selected {len(matched_filings)} best filings (one per series)")
    return matched_filings


if __name__ == "__main__":
    # Quick test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python filing_matcher.py <TICKER> <SERIES1> <SERIES2> ...")
        sys.exit(1)

    ticker = sys.argv[1]
    series_names = sys.argv[2:] if len(sys.argv) > 2 else []

    if not series_names:
        print(f"No series names provided. Use: python filing_matcher.py <TICKER> <SERIES1> <SERIES2> ...")
        sys.exit(1)

    # Match filings
    print(f"\nMatching 424B filings for series: {series_names}")
    matched = match_series_to_424b(ticker, series_names, max_filings=20)

    print(f"\nMatched {len(matched)} filings:")
    for filing in matched:
        print(f"  - {filing['form']} ({filing['date']}): Series {filing['matched_series']}")
        print(f"    URL: {filing.get('url', 'N/A')}")

