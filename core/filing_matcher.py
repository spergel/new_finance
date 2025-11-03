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
    
    # For each series, find the best matching filing using a simple score
    best_filings_per_series = {}

    for filing in filings:
        try:
            # Get filing content
            content = client.get_filing_by_accession(ticker, filing['accession'], filing['form'])
            if not content:
                continue

            # Lower-cased content and header slice for quick checks
            content_lower = content.lower()
            header_text = content_lower[:2000]

            for series in series_names:
                series_lower = series.lower()
                # Handle both "Series A" and "A" formats
                # Scoring criteria
                score = 0
                # Direct header mention of series
                if re.search(rf'\bseries\s+{re.escape(series_lower)}\b', header_text):
                    score += 3
                # Preferred context near header
                if re.search(rf'\bseries\s+{re.escape(series_lower)}\b.*?preferred\s+stock', header_text) or re.search(r'preferred\s+(stock|shares)', header_text):
                    score += 2
                # Presence of a section like "Description of the Series X Preferred Stock"
                has_series_section = bool(re.search(rf'description\s+of\s+the\s+series\s+{re.escape(series_lower)}\s+preferred\s+stock', content_lower))
                if has_series_section:
                    score += 6
                # Offering language specific to this series, within a tight window
                window_pattern = rf'(we\s+are\s+offering|public\s+offering\s+price|we\s+offer)[\s\S]{{0,400}}series\s+{re.escape(series_lower)}\b'
                m_off = re.search(window_pattern, content_lower)
                has_series_offering = bool(m_off)
                exclusive_offering = False
                if has_series_offering:
                    # Extract a local window and check if other series letters are co-mentioned
                    start = max(0, m_off.start() - 200)
                    end = min(len(content_lower), m_off.end() + 200)
                    win = content_lower[start:end]
                    other_series = [s for s in series_names if s.lower() != series_lower]
                    other_hits = 0
                    for os in other_series:
                        if re.search(rf'\bseries\s+{re.escape(os.lower())}\b', win):
                            other_hits += 1
                    if other_hits == 0:
                        exclusive_offering = True
                        score += 8
                    else:
                        # Non-exclusive offering mention: smaller boost and a slight penalty
                        score += 3
                        score -= min(2, other_hits)  # penalize omnibus offering mentions
                # Strong preferred indicators anywhere
                if any(k in content_lower for k in ['liquidation preference', 'dividend', 'cumulative']):
                    score += 1
                # Exclusion: if clearly a notes prospectus without preferred context
                if ('senior notes' in content_lower or 'notes due' in content_lower) and 'preferred stock' not in content_lower:
                    score = 0

                if score > 0:
                    existing = best_filings_per_series.get(series)
                    candidate = filing.copy()
                    candidate['content'] = content
                    candidate['matched_series'] = [series]
                    candidate['_score'] = score
                    candidate['_has_series_section'] = has_series_section
                    candidate['_has_series_offering'] = has_series_offering
                    candidate['_exclusive_offering'] = exclusive_offering

                    if not existing:
                        best_filings_per_series[series] = candidate
                        logger.info(f"Candidate for Series {series}: score={score} {filing['form']} ({filing['date']})")
                    else:
                        # Prefer filings that have offering language for the series, then explicit series section, then score/date
                        ex_off = existing.get('_has_series_offering', False)
                        ex_excl = existing.get('_exclusive_offering', False)
                        if (not ex_off and candidate['_has_series_offering']) \
                           or (ex_off == candidate['_has_series_offering'] and (not ex_excl and candidate.get('_exclusive_offering', False))) \
                           or (ex_off == candidate['_has_series_offering'] and ex_excl == candidate.get('_exclusive_offering', False) and (not existing.get('_has_series_section') and candidate['_has_series_section'])) \
                           or (ex_off == candidate['_has_series_offering'] and ex_excl == candidate.get('_exclusive_offering', False) and existing.get('_has_series_section') == candidate['_has_series_section'] and (score > existing.get('_score', 0) or (score == existing.get('_score', 0) and filing['date'] > existing['date']))):
                            best_filings_per_series[series] = candidate
                            logger.info(f"Updated candidate for Series {series}: score={score} {filing['form']} ({filing['date']})")
        
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

