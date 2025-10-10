#!/usr/bin/env python3
"""
Filing Matcher Module

Matches 424B and other SEC filings to specific securities by analyzing content.
Supports preferred shares, senior notes, convertible notes, and other security types.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from core.sec_api_client import SECAPIClient

logger = logging.getLogger(__name__)


# Security type keyword mappings
SECURITY_TYPE_KEYWORDS = {
    'preferred_stock': [
        'preferred stock',
        'depositary shares',
        'perpetual preferred',
        'non-cumulative preferred',
        'noncumulative preferred'
    ],
    'senior_notes': [
        'senior notes',
        'senior debt securities',
        'senior unsecured notes',
        'debt securities'
    ],
    'subordinated_note': [
        'subordinated notes',
        'junior notes',
        'subordinated debt'
    ],
    'convertible_note': [
        'convertible notes',
        'convertible debt',
        'convertible senior notes'
    ],
    'convertible_preferred': [
        'convertible preferred stock',
        'convertible preferred shares'
    ]
}


def identify_security_type(text: str) -> Optional[str]:
    """
    Identify the security type from filing text.
    
    Args:
        text: Filing text (typically first few thousand characters)
    
    Returns:
        Security type string, or 'unknown' if not identified
    """
    text_lower = text.lower()
    
    # Check each security type
    for sec_type, keywords in SECURITY_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                logger.debug(f"Identified security type: {sec_type} (keyword: '{keyword}')")
                return sec_type
    
    return 'unknown'


def count_series_mentions(text: str, series_name: str) -> int:
    """
    Count how many times a series is mentioned in the text.
    
    Args:
        text: Filing text to search
        series_name: Series identifier (e.g., "Series A", "A", "Series RR", "RR")
    
    Returns:
        Count of series mentions
    """
    # Validate inputs
    if not text or not series_name or not series_name.strip():
        return 0
    
    text_lower = text.lower()
    series_name = series_name.strip()
    
    # Handle both "Series A" and "A" formats
    if series_name.lower().startswith('series '):
        series_lower = series_name.lower()
    else:
        series_lower = f'series {series_name.lower()}'
    
    # Additional validation: ensure we have a valid series letter/letters after "series "
    series_letter = series_lower.replace('series ', '').strip()
    if not series_letter or not series_letter.replace(' ', '').isalpha():
        return 0
    
    # Pattern to match "series X" with various endings
    # Use word boundary to avoid matching "series about" when looking for "series a"
    pattern = rf'\b{re.escape(series_lower)}\b'
    
    matches = list(re.finditer(pattern, text_lower))
    return len(matches)


def match_filing_to_securities(filing_text: str, known_securities: List[Dict]) -> Optional[Dict]:
    """
    Match a filing to known securities based on content analysis.
    
    Strategy:
    1. Identify security type from header
    2. Count series mentions in filing
    3. Match to security with highest frequency
    4. Return match with confidence score
    
    Args:
        filing_text: Complete filing text
        known_securities: List of securities from 10-Q extraction
    
    Returns:
        Dict with match information or None if no match
        {
            'matched_series': str,
            'security_type': str,
            'mention_count': int,
            'confidence': str,  # 'high', 'medium', 'low'
            'all_counts': Dict[str, int]
        }
    """
    if not filing_text or not known_securities:
        return None
    
    # Extract header and body sample for analysis
    header = filing_text[:5000]
    body_sample = filing_text[:25000]  # First 25K chars for frequency analysis
    
    # Step 1: Identify security type
    identified_type = identify_security_type(header)
    
    if not identified_type:
        logger.debug("Could not identify security type from filing header")
        # Don't immediately return None - still try to match by series
    
    # Step 2: Count series mentions for each known security
    series_counts = {}
    for security in known_securities:
        series = security.get('series_name')
        if not series:
            continue
        
        count = count_series_mentions(body_sample, series)
        if count > 0:
            series_counts[series] = count
            logger.debug(f"Series {series}: {count} mentions")
    
    # Step 3: Determine best match
    if not series_counts:
        logger.debug("No series mentions found in filing")
        return None
    
    # Find series with highest mention count
    best_series = max(series_counts, key=series_counts.get)
    best_count = series_counts[best_series]
    
    # Determine confidence based on mention count and clarity
    if best_count >= 15:
        confidence = 'high'
    elif best_count >= 8:
        confidence = 'medium'
    else:
        confidence = 'low'
    
    # Check if there's a clear winner (best count significantly higher than others)
    if len(series_counts) > 1:
        second_best_count = sorted(series_counts.values(), reverse=True)[1]
        if best_count < second_best_count * 2:
            # Ambiguous - multiple series with similar counts
            logger.warning(f"Ambiguous match: {best_series} ({best_count}) vs others")
            confidence = 'low' if confidence == 'high' else 'low'
    
    return {
        'matched_series': best_series,
        'security_type': identified_type,
        'series_mention_count': best_count,
        'confidence': confidence,
        'all_counts': series_counts
    }


def get_all_424b_with_content(ticker: str, max_filings: int = 100) -> List[Dict]:
    """
    Get all 424B filings for a ticker with their content.
    
    Args:
        ticker: Company ticker symbol
        max_filings: Maximum number of filings to fetch
    
    Returns:
        List of dicts with filing metadata and content
    """
    logger.info(f"Fetching 424B filings for {ticker} (max: {max_filings})")
    
    client = SECAPIClient()
    
    # Get all 424B filings metadata - FILTER to actual issuances (424B5, 424B3, 424B7)
    # Skip 424B2 (daily structured note shelf registrations that create noise)
    all_424b = client.get_all_424b_filings(
        ticker, 
        max_filings=max_filings,
        filing_variants=['424B5', '424B3', '424B7']  # Only actual equity/preferred issuances
    )
    
    if not all_424b:
        logger.warning(f"No 424B filings found for {ticker}")
        return []
    
    logger.info(f"Found {len(all_424b)} 424B filings for {ticker}")
    
    # Fetch content for each filing BY ACCESSION NUMBER
    filings_with_content = []
    for i, filing in enumerate(all_424b[:max_filings], 1):
        try:
            # Fetch the SPECIFIC filing by accession number (not just most recent)
            content = client.get_filing_by_accession(
                ticker,
                filing['accession'],
                filing['form']
            )
            
            if content:
                filing['content'] = content
                filing['content_length'] = len(content)
                filings_with_content.append(filing)
                logger.debug(f"[{i}/{len(all_424b)}] Fetched {filing['form']} from {filing['date']} "
                           f"(accession: {filing['accession']}, {len(content):,} chars)")
            else:
                logger.debug(f"[{i}/{len(all_424b)}] Could not fetch content for {filing['form']} "
                           f"from {filing['date']} (accession: {filing['accession']})")
        
        except Exception as e:
            logger.error(f"Error fetching filing {filing.get('accession')}: {e}")
            continue
    
    logger.info(f"Successfully fetched content for {len(filings_with_content)} filings")
    return filings_with_content


def match_all_filings_to_securities(ticker: str, known_securities: List[Dict], 
                                    max_filings: int = 100) -> List[Dict]:
    """
    Fetch all 424B filings and match them to known securities.
    
    Args:
        ticker: Company ticker symbol
        known_securities: List of securities from 10-Q extraction
        max_filings: Maximum number of filings to check
    
    Returns:
        List of matched filings with match metadata
    """
    # Get all 424B filings with content
    all_filings = get_all_424b_with_content(ticker, max_filings)
    
    if not all_filings:
        return []
    
    # Match each filing to known securities
    matched_filings = []
    for filing in all_filings:
        match_result = match_filing_to_securities(filing['content'], known_securities)
        
        if match_result and match_result['confidence'] in ['high', 'medium']:
            filing['matched_series'] = match_result['matched_series']
            filing['security_type'] = match_result['security_type']
            filing['match_confidence'] = match_result['confidence']
            filing['series_mention_count'] = match_result['series_mention_count']
            filing['all_series_counts'] = match_result['all_counts']
            
            # Remove content from the returned object to save memory
            filing_copy = filing.copy()
            filing_copy.pop('content', None)
            
            matched_filings.append(filing_copy)
            
            logger.info(f"Matched {filing['form']} ({filing['date']}) to Series {match_result['matched_series']} "
                       f"(confidence: {match_result['confidence']}, mentions: {match_result['series_mention_count']})")
        else:
            logger.debug(f"No match for {filing['form']} from {filing['date']}")
    
    logger.info(f"Matched {len(matched_filings)} of {len(all_filings)} filings to known securities")
    return matched_filings


if __name__ == "__main__":
    # Quick test
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python filing_matcher.py <TICKER>")
        sys.exit(1)
    
    ticker = sys.argv[1]
    
    # Get known securities from 10-Q
    from xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares
    xbrl_result = extract_xbrl_preferred_shares(ticker)
    securities = xbrl_result.get('securities', [])
    
    print(f"\nKnown securities from 10-Q: {len(securities)}")
    for sec in securities:
        print(f"  - Series {sec.get('series_name')}")
    
    # Match filings
    print(f"\nMatching 424B filings...")
    matched = match_all_filings_to_securities(ticker, securities, max_filings=50)
    
    print(f"\nMatched {len(matched)} filings:")
    for filing in matched:
        print(f"  - {filing['form']} ({filing['date']}): Series {filing['matched_series']} "
              f"({filing['match_confidence']} confidence, {filing['mention_count']} mentions)")

