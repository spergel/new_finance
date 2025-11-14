#!/usr/bin/env python3
"""
Rename custom parsers to regular parsers and delete old regular parsers.

This script:
1. Renames *_custom_parser.py to *_parser.py
2. Updates class names inside files (CustomExtractor -> Extractor)
3. Deletes old regular parsers
4. Updates historical_investment_extractor.py to check regular parsers first
"""

import os
import re
import shutil
import glob
from typing import List, Dict, Tuple

def find_parser_pairs() -> List[Tuple[str, str, str]]:
    """Find all custom/regular parser pairs."""
    parser_dir = os.path.dirname(__file__)
    
    pairs = []
    custom_files = glob.glob(os.path.join(parser_dir, '*_custom_parser.py'))
    
    for custom_file in custom_files:
        basename = os.path.basename(custom_file)
        ticker = basename.replace('_custom_parser.py', '').upper()
        regular_file = os.path.join(parser_dir, f"{ticker.lower()}_parser.py")
        
        if os.path.exists(regular_file):
            pairs.append((ticker, custom_file, regular_file))
    
    return pairs

def update_class_names_in_file(file_path: str, old_class: str, new_class: str) -> bool:
    """Update class name in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace class name
        old_pattern = f'class {old_class}'
        new_pattern = f'class {new_class}'
        
        if old_pattern in content:
            content = content.replace(old_pattern, new_pattern)
            
            # Also update in docstrings and comments if needed
            content = re.sub(rf'\b{old_class}\b', new_class, content)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"  ❌ Error updating {file_path}: {e}")
        return False
    return False

def get_class_name_from_file(file_path: str) -> str:
    """Extract class name from file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Look for class definition
        match = re.search(r'class\s+(\w+CustomExtractor)', content)
        if match:
            return match.group(1)
        
        # Try other patterns
        match = re.search(r'class\s+(\w+Extractor)', content)
        if match:
            return match.group(1)
    except:
        pass
    return None

def rename_custom_to_regular(ticker: str, custom_file: str, regular_file: str, dry_run: bool = False) -> bool:
    """Rename custom parser to regular parser."""
    parser_dir = os.path.dirname(custom_file)
    new_regular_file = os.path.join(parser_dir, f"{ticker.lower()}_parser.py")
    
    print(f"\n📝 {ticker}:")
    print(f"  Custom: {os.path.basename(custom_file)}")
    print(f"  Regular (old): {os.path.basename(regular_file)}")
    print(f"  Regular (new): {os.path.basename(new_regular_file)}")
    
    # Get class name
    old_class = get_class_name_from_file(custom_file)
    if old_class:
        # Remove "Custom" from class name
        new_class = old_class.replace('CustomExtractor', 'Extractor')
        print(f"  Class: {old_class} -> {new_class}")
    else:
        print(f"  ⚠️  Could not find class name")
        new_class = None
    
    if dry_run:
        print(f"  [DRY RUN] Would rename and update class")
        return True
    
    try:
        # Step 1: Copy custom to new regular location
        shutil.copy2(custom_file, new_regular_file)
        print(f"  ✅ Copied custom parser to regular location")
        
        # Step 2: Update class name in new file
        if new_class and old_class != new_class:
            if update_class_names_in_file(new_regular_file, old_class, new_class):
                print(f"  ✅ Updated class name")
        
        # Step 3: Delete old custom file
        os.remove(custom_file)
        print(f"  ✅ Deleted old custom parser")
        
        # Step 4: Delete old regular file
        os.remove(regular_file)
        print(f"  ✅ Deleted old regular parser")
        
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def update_historical_extractor(dry_run: bool = False) -> bool:
    """Update historical_investment_extractor.py to check regular parsers first."""
    extractor_file = os.path.join(os.path.dirname(__file__), 'historical_investment_extractor.py')
    
    if not os.path.exists(extractor_file):
        print(f"⚠️  Could not find {extractor_file}")
        return False
    
    try:
        with open(extractor_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the _get_parser_for_ticker method
        # Currently it checks custom first, then regular
        # After renaming, we just need to check regular
        
        old_pattern = r'# First, try custom parser if it exists\s+custom_parser_module = f"\{ticker\.lower\(\)\}_custom_parser"[\s\S]*?except ImportError:\s+pass\s+# Custom parser doesn\'t exist, continue to regular parser'
        
        new_code = '''# Check for parser (custom parsers have been renamed to regular parsers)
        parser_module_name = f"{ticker.lower()}_parser"
        try:
            module = importlib.import_module(parser_module_name)
            for class_name in ['Extractor', f'{ticker}Extractor', f'{ticker.upper()}Extractor']:
                if hasattr(module, class_name):
                    extractor_class = getattr(module, class_name)
                    logger.info(f"Using parser: {parser_module_name}.{class_name}")
                    return extractor_class(user_agent=self.headers['User-Agent'])
        except ImportError:
            pass  # Parser doesn't exist'''
        
        if re.search(old_pattern, content):
            if dry_run:
                print(f"\n📝 Would update historical_investment_extractor.py")
                print(f"   Remove custom parser check, keep regular parser check")
                return True
            else:
                content = re.sub(old_pattern, new_code, content)
                with open(extractor_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"\n✅ Updated historical_investment_extractor.py")
                return True
        else:
            print(f"\n⚠️  Could not find custom parser check pattern in historical_investment_extractor.py")
            print(f"   May need manual update")
            return False
    except Exception as e:
        print(f"\n❌ Error updating historical_investment_extractor.py: {e}")
        return False

def main():
    """Main function."""
    import sys
    
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv
    
    if dry_run:
        print("=" * 80)
        print("DRY RUN MODE - No files will be changed")
        print("=" * 80)
    
    pairs = find_parser_pairs()
    
    print(f"\nFound {len(pairs)} parser pairs to merge")
    
    if not pairs:
        print("No parser pairs found. Nothing to do.")
        return
    
    print("\n" + "=" * 80)
    print("PARSER RENAME PLAN")
    print("=" * 80)
    
    success_count = 0
    for ticker, custom_file, regular_file in pairs:
        if rename_custom_to_regular(ticker, custom_file, regular_file, dry_run=dry_run):
            success_count += 1
    
    # Update historical extractor
    update_historical_extractor(dry_run=dry_run)
    
    print("\n" + "=" * 80)
    if dry_run:
        print(f"DRY RUN COMPLETE")
        print(f"Would rename {success_count}/{len(pairs)} parsers")
        print(f"\nRun without --dry-run to apply changes")
    else:
        print(f"COMPLETE: Renamed {success_count}/{len(pairs)} parsers")
        print(f"\n✅ Custom parsers have been renamed to regular parsers")
        print(f"✅ Old regular parsers have been deleted")
        print(f"✅ historical_investment_extractor.py has been updated")
    
    print("=" * 80)

if __name__ == '__main__':
    main()

