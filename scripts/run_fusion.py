#!/usr/bin/env python3
"""Run data fusion to combine XBRL and LLM data."""
import sys
import json
from core.data_fusion import fuse_data
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares
from core.securities_features_extractor import SecuritiesFeaturesExtractor

def main(ticker='JXN'):
    print(f"Data Fusion for {ticker}")
    print("="*80)
    
    # Get XBRL data
    print("\n[1/3] Extracting from 10-Q...")
    xbrl_result = extract_xbrl_preferred_shares(ticker)
    xbrl_count = len(xbrl_result.get('securities', []))
    print(f"  Found {xbrl_count} securities from XBRL")
    
    # Get LLM data
    print("\n[2/3] Extracting from 424B...")
    extractor = SecuritiesFeaturesExtractor()
    llm_result = extractor.extract_securities_features(ticker)
    llm_result_dict = {
        'ticker': llm_result.ticker,
        'securities': [sec.dict() for sec in llm_result.securities]
    }
    llm_count = len(llm_result_dict.get('securities', []))
    print(f"  Found {llm_count} securities from LLM")
    
    # Fuse
    print("\n[3/3] Fusing data...")
    fused = fuse_data(ticker, xbrl_result, llm_result_dict)
    
    print(f"\nFused Result:")
    print(f"  Total securities: {fused['total_securities']}")
    print(f"  With LLM data: {fused['securities_with_llm_data']}")
    
    # Save
    output_file = f'{ticker}/{ticker}_fused_preferred_shares.json'
    with open(output_file, 'w') as f:
        json.dump(fused, f, indent=2, default=str)
    
    print(f"\nSaved to: {output_file}")
    
    # Print sample
    print("\n" + "="*80)
    print("SAMPLE OUTPUT (first security):")
    print("="*80)
    if fused['securities']:
        sec = fused['securities'][0]
        print(json.dumps(sec, indent=2, default=str))
    
    return fused

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'JXN'
    main(ticker)


