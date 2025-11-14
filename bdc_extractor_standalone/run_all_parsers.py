#!/usr/bin/env python3
"""
Run all BDC parsers to regenerate investment CSV files.

This script:
1. Clears the output folder (CSV files only)
2. Finds all parser files
3. Runs each parser's extract_from_ticker method
4. Reports results
"""

import os
import glob
import importlib
import logging
import traceback
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def clear_output_folder(output_dir: str = None):
    """Clear CSV files from output folder."""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    
    if not os.path.exists(output_dir):
        logger.info(f"Output directory {output_dir} does not exist, creating it")
        os.makedirs(output_dir, exist_ok=True)
        return
    
    csv_files = glob.glob(os.path.join(output_dir, '*.csv'))
    csv_count = len(csv_files)
    
    for csv_file in csv_files:
        try:
            os.remove(csv_file)
            logger.debug(f"Deleted {os.path.basename(csv_file)}")
        except Exception as e:
            logger.warning(f"Could not delete {csv_file}: {e}")
    
    logger.info(f"Cleared {csv_count} CSV files from output folder")

def find_parser_files() -> List[Tuple[str, str]]:
    """Find all parser files and their tickers."""
    parser_dir = os.path.dirname(__file__)
    parsers = []
    seen_tickers = set()
    
    # Get all parser files (including custom parsers that were renamed)
    parser_files = glob.glob(os.path.join(parser_dir, '*_parser.py'))
    # Also check for any remaining custom parsers
    custom_files = glob.glob(os.path.join(parser_dir, '*_custom_parser.py'))
    
    all_files = parser_files + custom_files
    
    for parser_file in all_files:
        basename = os.path.basename(parser_file)
        # Skip utility parsers
        if basename in ['flexible_table_parser.py', 'verbose_identifier_parser.py', 'xbrl_typed_extractor.py']:
            continue
        
        # Extract ticker from filename
        if '_custom_parser.py' in basename:
            ticker = basename.replace('_custom_parser.py', '').upper()
        else:
            ticker = basename.replace('_parser.py', '').upper()
        
        # Skip if we've already seen this ticker (prefer regular parser over custom)
        if ticker in seen_tickers:
            continue
        
        seen_tickers.add(ticker)
        parsers.append((ticker, parser_file))
    
    return sorted(parsers)

def get_extractor_class(module, ticker: str):
    """Get the extractor class from a module."""
    # Try common class name patterns
    class_names = [
        f'{ticker}Extractor',
        f'{ticker.upper()}Extractor',
        f'{ticker}CustomExtractor',  # For custom parsers
        f'{ticker.upper()}CustomExtractor',
        'Extractor',
        'CustomExtractor',
    ]
    
    for class_name in class_names:
        if hasattr(module, class_name):
            return getattr(module, class_name)
    
    # Special case: FDUS custom parser uses FDUSExtractor (not FDUSCustomExtractor)
    if ticker == 'FDUS' and hasattr(module, 'FDUSExtractor'):
        return getattr(module, 'FDUSExtractor')
    
    return None

def run_parser(ticker: str, parser_file: str) -> Dict:
    """Run a single parser and return results."""
    result = {
        'ticker': ticker,
        'parser_file': os.path.basename(parser_file),
        'status': 'unknown',
        'error': None,
        'investments_count': 0
    }
    
    try:
        # Import the parser module
        module_name = os.path.basename(parser_file).replace('.py', '')
        module = importlib.import_module(module_name)
        
        # Get extractor class
        extractor_class = get_extractor_class(module, ticker)
        if not extractor_class:
            result['status'] = 'skipped'
            result['error'] = f'No extractor class found in {parser_file}'
            logger.warning(f"⚠️  {ticker}: {result['error']}")
            return result
        
        # Create extractor instance
        extractor = extractor_class()
        
        # Check if extract_from_ticker exists
        if not hasattr(extractor, 'extract_from_ticker'):
            result['status'] = 'skipped'
            result['error'] = 'No extract_from_ticker method found'
            logger.warning(f"⚠️  {ticker}: {result['error']}")
            return result
        
        # Run the extractor
        logger.info(f"🔄 Running {ticker} parser...")
        # Some parsers might not take ticker as argument, try with and without
        try:
            data = extractor.extract_from_ticker(ticker)
        except TypeError:
            # Try without ticker argument (uses default)
            data = extractor.extract_from_ticker()
        
        # Extract investment count
        if isinstance(data, dict):
            result['investments_count'] = data.get('total_investments', 0)
        else:
            # Try to get from attributes if it's a dataclass/object (like BDCExtractionResult)
            result['investments_count'] = getattr(data, 'total_investments', 0)
            if result['investments_count'] == 0:
                # Try investments list length
                investments = getattr(data, 'investments', None)
                if investments:
                    result['investments_count'] = len(investments)
        
        result['status'] = 'success'
        logger.info(f"✅ {ticker}: Extracted {result['investments_count']} investments")
        
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
        logger.error(f"❌ {ticker}: Error - {e}")
        logger.debug(traceback.format_exc())
    
    return result

def main():
    """Main function to run all parsers."""
    print("=" * 80)
    print("RUNNING ALL BDC PARSERS")
    print("=" * 80)
    print()
    
    # Clear output folder
    logger.info("Clearing output folder...")
    clear_output_folder()
    print()
    
    # Find all parsers
    parsers = find_parser_files()
    logger.info(f"Found {len(parsers)} parser files")
    print()
    
    # Run each parser
    results = []
    for ticker, parser_file in parsers:
        result = run_parser(ticker, parser_file)
        results.append(result)
        print()  # Blank line between parsers
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    
    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] == 'error']
    skipped = [r for r in results if r['status'] == 'skipped']
    
    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")
    print(f"⚠️  Skipped: {len(skipped)}")
    print()
    
    if successful:
        print("Successful parsers:")
        for r in successful:
            print(f"  ✅ {r['ticker']}: {r['investments_count']} investments")
        print()
    
    if failed:
        print("Failed parsers:")
        for r in failed:
            print(f"  ❌ {r['ticker']}: {r['error']}")
        print()
    
    if skipped:
        print("Skipped parsers:")
        for r in skipped:
            print(f"  ⚠️  {r['ticker']}: {r['error']}")
        print()
    
    total_investments = sum(r['investments_count'] for r in successful)
    print(f"Total investments extracted: {total_investments}")
    print("=" * 80)

if __name__ == '__main__':
    main()

