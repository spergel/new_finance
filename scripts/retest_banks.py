#!/usr/bin/env python3
"""Re-test BAC and C with new 424B filtering."""

from core.securities_features_extractor import extract_securities_features
import os
import json

api_key = os.getenv('GOOGLE_API_KEY')

for ticker in ['BAC', 'C']:
    print(f"\n{'='*80}")
    print(f"Re-extracting {ticker} with filtered 424Bs (no B2 noise)...")
    print(f"{'='*80}\n")
    
    try:
        result = extract_securities_features(ticker, api_key)
        
        print(f"Found {result.total_securities} securities for {ticker}\n")
        
        for sec in result.securities:
            print(f"  Security: {sec.security_id}")
            print(f"    Type: {sec.security_type.value}")
            print(f"    Filing Date: {sec.filing_date}")
            if sec.dividend_rate:
                print(f"    Dividend Rate: {sec.dividend_rate}%")
            if sec.liquidation_preference:
                print(f"    Liquidation Pref: ${sec.liquidation_preference:,.2f}")
            if sec.is_cumulative is not None:
                print(f"    Cumulative: {sec.is_cumulative}")
            print()
        
        # Save
        os.makedirs(ticker, exist_ok=True)
        filepath = f'{ticker}/{ticker}_enhanced_securities_features.json'
        with open(filepath, 'w') as f:
            json.dump(result.dict(), f, indent=2, default=str)
        print(f"Saved to {filepath}\n")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*80)
print("Extraction complete!")
print("="*80)




