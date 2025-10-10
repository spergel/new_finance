#!/usr/bin/env python3
"""
Run enhanced extraction for multiple companies to test new preferred stock fields.
"""

import os
import json
from datetime import datetime
from core.securities_features_extractor import extract_securities_features

def run_extraction_for_companies(tickers):
    """Run extraction for multiple companies and save results."""
    
    api_key = os.getenv('GOOGLE_API_KEY')
    
    results = {}
    
    for ticker in tickers:
        print(f"\n{'='*80}")
        print(f"Extracting securities for {ticker}...")
        print(f"{'='*80}\n")
        
        try:
            result = extract_securities_features(ticker, api_key)
            
            # Save individual result
            output_dir = f"{ticker}"
            os.makedirs(output_dir, exist_ok=True)
            
            filename = f"{ticker}_enhanced_securities_features.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(result.dict(), f, indent=2, default=str)
            
            print(f"\n[OK] Saved {ticker} results to {filepath}")
            print(f"   Found {result.total_securities} securities")
            
            # Print summary
            for security in result.securities:
                print(f"\n   Security: {security.security_id}")
                print(f"   Type: {security.security_type.value}")
                
                if security.security_type.value == "preferred_stock":
                    print(f"   Liquidation Pref: ${security.liquidation_preference:,.2f}" if security.liquidation_preference else "   Liquidation Pref: N/A")
                    print(f"   Dividend Rate: {security.dividend_rate}%" if security.dividend_rate else "   Dividend Rate: N/A")
                    print(f"   Cumulative: {security.is_cumulative}" if security.is_cumulative is not None else "   Cumulative: N/A")
                    print(f"   Perpetual: {security.is_perpetual}" if security.is_perpetual is not None else "   Perpetual: N/A")
                    
                    if security.rate_reset_terms and security.rate_reset_terms.has_rate_reset:
                        print(f"   Rate Reset: YES (spread: {security.rate_reset_terms.reset_spread}%)")
                    
                    if security.depositary_shares_info and security.depositary_shares_info.is_depositary_shares:
                        print(f"   Depositary Shares: {security.depositary_shares_info.depositary_shares_issued:,}")
                        print(f"   Symbol: {security.depositary_shares_info.depositary_symbol}")
            
            results[ticker] = {
                'success': True,
                'total_securities': result.total_securities,
                'file': filepath
            }
            
        except Exception as e:
            print(f"\n[ERROR] Error extracting {ticker}: {e}")
            import traceback
            traceback.print_exc()
            results[ticker] = {
                'success': False,
                'error': str(e)
            }
    
    # Save summary
    summary_file = f"extraction_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*80}")
    print(f"Extraction complete! Summary saved to {summary_file}")
    print(f"{'='*80}\n")
    
    return results

if __name__ == "__main__":
    # Test with JXN and a few other companies known to have preferred stock
    tickers = [
        "JXN",    # Jackson Financial - has Series A preferred with rate reset
        "BAC",    # Bank of America - has multiple preferred series
        "C",      # Citigroup - has preferred stock
    ]
    
    print("Running enhanced extraction with new preferred stock fields...")
    print(f"Testing {len(tickers)} companies: {', '.join(tickers)}")
    
    results = run_extraction_for_companies(tickers)
    
    # Print final summary
    print("\nFinal Summary:")
    for ticker, result in results.items():
        if result['success']:
            print(f"  [OK] {ticker}: {result['total_securities']} securities extracted")
        else:
            print(f"  [ERROR] {ticker}: Failed - {result.get('error', 'Unknown error')}")

