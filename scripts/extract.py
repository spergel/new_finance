#!/usr/bin/env python3
"""
Main extraction script - Extract preferred shares data from SEC filings

Usage:
    python extract.py JXN              # Extract all data for ticker JXN
    python extract.py JXN --llm-only   # Extract only LLM data (424B filings)
    python extract.py JXN --xbrl-only  # Extract only XBRL data (10-Q/10-K filings)
"""

import argparse
import logging
import sys
from core.securities_features_extractor import SecuritiesFeaturesExtractor
from core.corporate_actions_extractor import CorporateActionsExtractor
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_all(ticker: str, llm_only: bool = False, xbrl_only: bool = False):
    """
    Extract all preferred shares data for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        llm_only: Only extract LLM data (424B filings)
        xbrl_only: Only extract XBRL data (10-Q/10-K filings)
    """
    print(f"\n{'='*80}")
    print(f"  EXTRACTING PREFERRED SHARES DATA FOR {ticker}")
    print(f"{'='*80}\n")
    
    results = {}
    
    # Extract LLM data (424B filings - prospectus)
    if not xbrl_only:
        print("\n[1/3] Extracting Securities Features (LLM from 424B filings)...")
        print("-" * 80)
        try:
            extractor = SecuritiesFeaturesExtractor()
            securities_result = extractor.extract_securities_features(ticker)
            extractor.save_results(securities_result, ticker)
            results['securities'] = securities_result
            print(f"[OK] Found {len(securities_result.securities)} securities")
            print(f"[OK] Saved to: output/llm/{ticker}_securities_features.json")
        except Exception as e:
            logger.error(f"Failed to extract securities features: {e}")
            results['securities'] = None
        
        print("\n[2/3] Extracting Corporate Actions (LLM from 8-K/10-K/10-Q filings)...")
        print("-" * 80)
        try:
            extractor = CorporateActionsExtractor()
            actions_result = extractor.extract_corporate_actions(ticker)
            extractor.save_results(actions_result, ticker)
            results['actions'] = actions_result
            print(f"[OK] Found {actions_result.total_actions} corporate actions")
            print(f"[OK] Saved to: output/llm/{ticker}_corporate_actions.json")
        except Exception as e:
            logger.error(f"Failed to extract corporate actions: {e}")
            results['actions'] = None
    
    # Extract XBRL data (10-Q/10-K filings - structured financial data)
    if not llm_only:
        print("\n[3/3] Extracting XBRL Preferred Shares Data (10-Q/10-K filings)...")
        print("-" * 80)
        try:
            xbrl_result = extract_xbrl_preferred_shares(ticker)
            results['xbrl'] = xbrl_result
            
            if 'error' in xbrl_result:
                print(f"[ERROR] {xbrl_result['error']}")
            else:
                print(f"[OK] Found {xbrl_result.get('securities_found', 0)} securities with investment data")
                print(f"[OK] Series identified: {', '.join(xbrl_result.get('series_identified', []))}")
                print(f"[OK] CUSIPs identified: {', '.join(xbrl_result.get('cusips_identified', []))}")
                print(f"[OK] Average dividend rate: {xbrl_result.get('average_dividend_rate', 0.0)}%")
                print(f"[OK] Investment relevance score: {xbrl_result.get('investment_relevance_score', 0.0):.2f}")
                print(f"[OK] Saved to: output/xbrl/{ticker}_xbrl_data.json")
                print(f"[OK] Saved summary to: output/summaries/{ticker}_xbrl_summary.json")
        except Exception as e:
            logger.error(f"Failed to extract XBRL data: {e}")
            results['xbrl'] = None
    
    # Print summary
    print("\n" + "="*80)
    print("  EXTRACTION COMPLETE")
    print("="*80)
    print("\nOutput directories:")
    print("  - output/llm/        : LLM-extracted data from prospectuses")
    print("  - output/xbrl/       : XBRL-extracted data from financial reports")
    print("  - output/summaries/  : High-level summaries")
    print("  - output/fusion/     : Combined LLM + XBRL data (future)")
    print()
    
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract preferred shares data from SEC filings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python extract.py JXN              # Extract all data for JXN
  python extract.py JXN --llm-only   # Extract only LLM data
  python extract.py JXN --xbrl-only  # Extract only XBRL data
        """
    )
    
    parser.add_argument(
        'ticker',
        type=str,
        help='Stock ticker symbol (e.g., JXN, BAC, C)'
    )
    
    parser.add_argument(
        '--llm-only',
        action='store_true',
        help='Extract only LLM data from 424B filings'
    )
    
    parser.add_argument(
        '--xbrl-only',
        action='store_true',
        help='Extract only XBRL data from 10-Q/10-K filings'
    )
    
    args = parser.parse_args()
    
    if args.llm_only and args.xbrl_only:
        print("Error: Cannot specify both --llm-only and --xbrl-only")
        sys.exit(1)
    
    try:
        extract_all(args.ticker.upper(), llm_only=args.llm_only, xbrl_only=args.xbrl_only)
    except KeyboardInterrupt:
        print("\n\nExtraction cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

