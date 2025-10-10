#!/usr/bin/env python3
"""
Data Fusion Module

Combines data from multiple sources:
1. Regex extraction from 10-Q (basic financial terms)
2. LLM extraction from 424B (complex narrative features)

Strategy:
- 10-Q data is the "source of truth" for current financial terms
- 424B data provides additional detail on conversion, redemption, governance
- Merge by series name with confidence-based conflict resolution
"""

import logging
from typing import Dict, List, Optional
from datetime import date

logger = logging.getLogger(__name__)


def merge_series_data(xbrl_data: Dict, llm_security: Dict) -> Dict:
    """
    Merge data from 10-Q (XBRL) and 424B (LLM) for a single series.
    
    Priority:
    - Financial terms (dividend rate, shares, liquidation preference): XBRL wins
    - Narrative features (conversion terms, governance, provisions): LLM wins
    - Description: Prefer longer/more detailed version
    
    Args:
        xbrl_data: Dict from 10-Q extraction (has: series, dividend_rate, etc.)
        llm_security: Dict from 424B LLM extraction (has: redemption_terms, etc.)
    
    Returns:
        Merged dict with combined data
    """
    merged = {}
    
    # Core identifiers
    merged['series_name'] = xbrl_data.get('series_name') or xbrl_data.get('series')
    merged['ticker'] = xbrl_data.get('ticker') or llm_security.get('company')
    
    # Description: prefer LLM (usually more detailed)
    llm_desc = llm_security.get('description', '')
    xbrl_desc = xbrl_data.get('description', '')
    merged['description'] = llm_desc if len(llm_desc) > len(xbrl_desc) else xbrl_desc
    
    # Financial terms: ALWAYS prefer XBRL (current source of truth)
    merged['dividend_rate'] = xbrl_data.get('dividend_rate')
    merged['outstanding_shares'] = xbrl_data.get('outstanding_shares')
    merged['authorized_shares'] = xbrl_data.get('authorized_shares')
    merged['liquidation_preference'] = xbrl_data.get('liquidation_preference_per_share')
    merged['par_value'] = xbrl_data.get('par_value')
    merged['is_cumulative'] = xbrl_data.get('is_cumulative')
    
    # Additional XBRL fields (if available)
    merged['voting_rights'] = xbrl_data.get('voting_rights')
    merged['ranking'] = xbrl_data.get('ranking')
    merged['payment_frequency'] = xbrl_data.get('payment_frequency')
    merged['call_date'] = xbrl_data.get('call_date')
    
    # Narrative features: prefer LLM (more detailed)
    merged['conversion_terms'] = llm_security.get('conversion_terms')
    merged['redemption_terms'] = llm_security.get('redemption_terms')
    merged['special_features'] = llm_security.get('special_features')
    
    # Metadata
    merged['xbrl_confidence'] = xbrl_data.get('confidence')
    merged['llm_confidence'] = llm_security.get('extraction_confidence')
    merged['filing_date_10q'] = xbrl_data.get('filing_date')
    merged['filing_date_424b'] = llm_security.get('filing_date')
    merged['source_filing'] = llm_security.get('source_filing')
    
    return merged


def match_llm_to_xbrl(xbrl_securities: List[Dict], llm_securities: List[Dict]) -> List[Dict]:
    """
    Match LLM-extracted securities to XBRL securities by series name.
    
    Args:
        xbrl_securities: List of securities from 10-Q extraction
        llm_securities: List of securities from 424B LLM extraction
    
    Returns:
        List of matched securities with both sources
    """
    # Index LLM securities by series name (extracted from description or ID)
    llm_by_series = {}
    for llm_sec in llm_securities:
        # Try to extract series name from security_id or description
        series = extract_series_name(llm_sec)
        if series:
            # Keep the most detailed LLM extraction for each series
            if series not in llm_by_series:
                llm_by_series[series] = llm_sec
            else:
                # If multiple LLM extractions for same series, keep the more detailed one
                existing = llm_by_series[series]
                if count_non_null_fields(llm_sec) > count_non_null_fields(existing):
                    llm_by_series[series] = llm_sec
    
    logger.info(f"Indexed {len(llm_by_series)} LLM securities by series: {list(llm_by_series.keys())}")
    
    # Merge each XBRL security with its corresponding LLM data (if found)
    merged_securities = []
    for xbrl_sec in xbrl_securities:
        series = xbrl_sec.get('series_name') or xbrl_sec.get('series')
        
        if series and series in llm_by_series:
            # Match found - merge data
            merged = merge_series_data(xbrl_sec, llm_by_series[series])
            merged['has_llm_data'] = True
            logger.info(f"Merged data for Series {series} (XBRL + LLM)")
        else:
            # No LLM data - use XBRL only
            merged = {
                'series_name': series,
                'ticker': xbrl_sec.get('ticker'),
                'description': xbrl_sec.get('description'),
                'dividend_rate': xbrl_sec.get('dividend_rate'),
                'outstanding_shares': xbrl_sec.get('outstanding_shares'),
                'authorized_shares': xbrl_sec.get('authorized_shares'),
                'liquidation_preference': xbrl_sec.get('liquidation_preference_per_share'),
                'par_value': xbrl_sec.get('par_value'),
                'is_cumulative': xbrl_sec.get('is_cumulative'),
                'voting_rights': xbrl_sec.get('voting_rights'),
                'ranking': xbrl_sec.get('ranking'),
                'payment_frequency': xbrl_sec.get('payment_frequency'),
                'call_date': xbrl_sec.get('call_date'),
                'conversion_terms': None,
                'redemption_terms': None,
                'special_features': None,
                'xbrl_confidence': xbrl_sec.get('confidence'),
                'llm_confidence': None,
                'filing_date_10q': xbrl_sec.get('filing_date'),
                'filing_date_424b': None,
                'source_filing': '10-Q only',
                'has_llm_data': False
            }
            logger.info(f"Using XBRL-only data for Series {series} (no matching 424B)")
        
        merged_securities.append(merged)
    
    return merged_securities


def extract_series_name(llm_security: Dict) -> Optional[str]:
    """
    Extract series name from LLM security data.
    
    Tries multiple fields: security_id, description
    Looks for patterns like "Series A", "Series RR", etc.
    """
    import re
    
    # Check security_id first
    security_id = llm_security.get('security_id', '')
    match = re.search(r'Series\s+([A-Z]{1,3})\b', security_id, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # Check description
    description = llm_security.get('description', '')
    match = re.search(r'Series\s+([A-Z]{1,3})\b', description, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # Check if security_id itself is just a series letter(s)
    if security_id and len(security_id) <= 3 and security_id.isalpha():
        return security_id.upper()
    
    return None


def count_non_null_fields(data: Dict) -> int:
    """Count how many fields in a dict are non-null."""
    return sum(1 for v in data.values() if v is not None and v != '' and v != [])


def fuse_data(ticker: str, xbrl_result: Dict, llm_result: Dict) -> Dict:
    """
    Main fusion function: combines XBRL and LLM extraction results.
    
    Args:
        ticker: Company ticker symbol
        xbrl_result: Result from extract_xbrl_preferred_shares()
        llm_result: Result from extract_securities_features()
    
    Returns:
        Fused result with combined data
    """
    logger.info(f"Fusing data for {ticker}")
    
    xbrl_securities = xbrl_result.get('preferred_shares', []) or xbrl_result.get('securities', [])
    llm_securities = llm_result.get('securities', [])
    
    logger.info(f"XBRL: {len(xbrl_securities)} securities")
    logger.info(f"LLM: {len(llm_securities)} securities")
    
    # Add ticker to XBRL securities if missing
    for sec in xbrl_securities:
        if 'ticker' not in sec:
            sec['ticker'] = ticker
    
    # Match and merge
    merged_securities = match_llm_to_xbrl(xbrl_securities, llm_securities)
    
    return {
        'ticker': ticker,
        'extraction_date': str(date.today()),
        'total_securities': len(merged_securities),
        'securities_with_llm_data': sum(1 for s in merged_securities if s.get('has_llm_data')),
        'securities': merged_securities,
        'data_sources': {
            'xbrl_10q': xbrl_result.get('filing_type'),
            'llm_424b': 'available' if llm_securities else 'not_available'
        }
    }


if __name__ == "__main__":
    # Quick test
    import json
    from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares
    from core.securities_features_extractor import SecuritiesFeaturesExtractor
    
    ticker = 'JXN'
    
    print(f"Testing data fusion for {ticker}...")
    
    # Get XBRL data
    print("\n[1/3] Extracting from 10-Q...")
    xbrl_result = extract_xbrl_preferred_shares(ticker)
    
    # Get LLM data
    print("\n[2/3] Extracting from 424B...")
    extractor = SecuritiesFeaturesExtractor()
    llm_result = extractor.extract_securities_features(ticker)
    llm_result_dict = {
        'ticker': llm_result.ticker,
        'securities': [sec.dict() for sec in llm_result.securities]
    }
    
    # Fuse
    print("\n[3/3] Fusing data...")
    fused = fuse_data(ticker, xbrl_result, llm_result_dict)
    
    # Save
    output_file = f'output/{ticker}_fused_data.json'
    with open(output_file, 'w') as f:
        json.dump(fused, f, indent=2, default=str)
    
    print(f"\nFused data saved to: {output_file}")
    print(f"Total securities: {fused['total_securities']}")
    print(f"With LLM data: {fused['securities_with_llm_data']}")



