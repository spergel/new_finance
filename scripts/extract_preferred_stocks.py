#!/usr/bin/env python3
"""
Simplified Preferred Stock Extraction

Clean pipeline:
1. XBRL from 10-Q → series names, outstanding shares
2. Regex match 424B filings → find related prospectuses
3. LLM extract features → detailed terms from matched filings
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.securities_features_extractor import extract_preferred_stocks_simple

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_preferred_stocks.py <TICKER> [API_KEY]")
        sys.exit(1)

    ticker = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else os.getenv('GOOGLE_API_KEY')

    print(f"Extracting preferred stocks for {ticker}")
    print("=" * 50)

    try:
        result = extract_preferred_stocks_simple(ticker, api_key)

        print("\nEXTRACTION COMPLETE")
        print(f"Found {result.total_securities} securities")

        for i, security in enumerate(result.securities, 1):
            print(f"\n{i}. {security.security_id}")
            print(f"   Type: {security.security_type.value}")
            print(f"   Description: {security.description or 'N/A'}")

            # Key financial terms
            if security.dividend_rate:
                print(f"   Dividend Rate: {security.dividend_rate}%")
            if security.liquidation_preference:
                print(f"   Liquidation Preference: ${security.liquidation_preference}")
            if security.par_value:
                print(f"   Par Value: ${security.par_value}")

            # Offering info
            if security.original_offering_price:
                print(f"   Original Price: ${security.original_offering_price}")

            # Covenants
            if security.special_features and security.special_features.covenants:
                cov = security.special_features.covenants
                if cov.restricted_payments_covenant:
                    print(f"   Dividend Restrictions: {cov.restricted_payments_covenant[:100]}...")

            # Tax treatment
            if security.special_redemption_events and security.special_redemption_events.tax_treatment_notes:
                print(f"   Tax Treatment: {security.special_redemption_events.tax_treatment_notes}")

        # Save results
        if result.total_securities > 0:
            from core.securities_features_extractor import SecuritiesFeaturesExtractor
            extractor = SecuritiesFeaturesExtractor(api_key)
            extractor.save_results(result)
            print(f"\nResults saved to output/llm/{ticker}_securities_features.json")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
