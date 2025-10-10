#!/usr/bin/env python3
"""Test data fusion with diverse companies."""
import sys
import json
from core.data_fusion import fuse_data
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares
from core.securities_features_extractor import SecuritiesFeaturesExtractor

def test_fusion(ticker):
    """Test fusion for a specific ticker."""
    print(f"\n{'='*80}")
    print(f"TESTING FUSION: {ticker}")
    print("="*80)
    
    try:
        # Get XBRL data
        print("\n[1/3] Extracting from 10-Q...")
        xbrl_result = extract_xbrl_preferred_shares(ticker)
        xbrl_count = len(xbrl_result.get('securities', []))
        print(f"  [OK] Found {xbrl_count} securities from XBRL")
        
        if xbrl_count == 0:
            print(f"  [SKIP] No preferred shares found for {ticker}")
            return None
        
        # Show XBRL series
        series_list = [s.get('series_name') or s.get('series') for s in xbrl_result.get('securities', [])]
        print(f"  Series: {', '.join(series_list)}")
        
        # Get LLM data
        print("\n[2/3] Extracting from 424B...")
        extractor = SecuritiesFeaturesExtractor()
        llm_result = extractor.extract_securities_features(ticker)
        llm_result_dict = {
            'ticker': llm_result.ticker,
            'securities': [sec.dict() for sec in llm_result.securities]
        }
        llm_count = len(llm_result_dict.get('securities', []))
        print(f"  [OK] Found {llm_count} securities from LLM")
        
        # Fuse
        print("\n[3/3] Fusing data...")
        fused = fuse_data(ticker, xbrl_result, llm_result_dict)
        
        print(f"\n  RESULTS:")
        print(f"  Total securities: {fused['total_securities']}")
        print(f"  With LLM data: {fused['securities_with_llm_data']}")
        print(f"  XBRL only: {fused['total_securities'] - fused['securities_with_llm_data']}")
        
        # Save
        output_file = f'{ticker}/{ticker}_fused_preferred_shares.json'
        with open(output_file, 'w') as f:
            json.dump(fused, f, indent=2, default=str)
        print(f"\n  Saved to: {output_file}")
        
        # Show sample
        if fused['securities']:
            sec = fused['securities'][0]
            print(f"\n  Sample (Series {sec.get('series_name')}):")
            print(f"    Dividend Rate: {sec.get('dividend_rate')}%")
            print(f"    Outstanding: {sec.get('outstanding_shares'):,}")
            print(f"    Par Value: ${sec.get('par_value'):,.0f}")
            print(f"    Has LLM Data: {sec.get('has_llm_data')}")
            if sec.get('redemption_terms'):
                call_date = sec['redemption_terms'].get('earliest_call_date')
                print(f"    Call Date: {call_date or 'Not callable'}")
        
        return fused
        
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Test fusion with multiple companies."""
    print("="*80)
    print("DATA FUSION - DIVERSE COMPANY TESTING")
    print("="*80)
    
    test_companies = [
        ("JXN", "Recent preferred (2023)"),
        ("C", "Multiple old series"),
        ("BAC", "Multi-letter series"),
        ("PSA", "REIT with preferred"),
    ]
    
    results = {}
    
    for ticker, description in test_companies:
        print(f"\n\nTesting {ticker} - {description}")
        print("-"*80)
        
        try:
            result = test_fusion(ticker)
            results[ticker] = {
                'success': result is not None,
                'total_securities': result['total_securities'] if result else 0,
                'with_llm': result['securities_with_llm_data'] if result else 0
            }
        except KeyboardInterrupt:
            print("\n\n[INTERRUPTED] Testing stopped")
            break
        except Exception as e:
            print(f"\n[ERROR] Failed: {e}")
            results[ticker] = {'success': False, 'total_securities': 0, 'with_llm': 0}
    
    # Summary
    print("\n\n" + "="*80)
    print("FUSION TEST SUMMARY")
    print("="*80)
    
    for ticker, result in results.items():
        status = "[OK]" if result['success'] else "[FAIL]"
        print(f"\n{status} {ticker}:")
        if result['success']:
            print(f"  Securities: {result['total_securities']}")
            print(f"  With LLM data: {result['with_llm']}")
            print(f"  XBRL only: {result['total_securities'] - result['with_llm']}")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()

