#!/usr/bin/env python3
"""
Clean up the bdc_extractor_standalone repo by removing test/debug files.
"""

import os
import shutil

# Files to remove (test, debug, inspect, check, analyze, etc.)
PATTERNS_TO_REMOVE = [
    'test_',
    'debug_',
    'inspect_',
    'check_',
    'analyze_',
    'verify_',
    'regenerate_',
    'fix_',
    'tmp_',
]

# Files to keep (important scripts)
KEEP_FILES = {
    'test_all_parsers.py',  # Might be useful
    'run_all_parsers.py',   # Main runner
}

# Directories to keep
KEEP_DIRS = {
    'output',
    'data',
    'frontend',
    'scripts',
    'raw_tables',
    'temp_filings',
    '__pycache__',
}

def should_remove(filename: str) -> bool:
    """Check if a file should be removed."""
    if filename in KEEP_FILES:
        return False
    
    for pattern in PATTERNS_TO_REMOVE:
        if filename.startswith(pattern):
            return True
    
    return False

def cleanup_directory(directory: str):
    """Remove test/debug files from directory."""
    removed = []
    kept = []
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        
        # Skip directories
        if os.path.isdir(filepath):
            if filename not in KEEP_DIRS:
                # Check if directory should be removed
                if any(filename.startswith(p) for p in PATTERNS_TO_REMOVE):
                    try:
                        shutil.rmtree(filepath)
                        removed.append(f"DIR: {filename}")
                    except Exception as e:
                        print(f"Error removing {filename}: {e}")
            continue
        
        # Skip non-Python files (except specific ones)
        if not filename.endswith('.py'):
            continue
        
        if should_remove(filename):
            try:
                os.remove(filepath)
                removed.append(filename)
            except Exception as e:
                print(f"Error removing {filename}: {e}")
        else:
            kept.append(filename)
    
    return removed, kept

def main():
    """Main cleanup function."""
    directory = os.path.dirname(__file__)
    
    print("Cleaning up bdc_extractor_standalone directory...")
    print(f"Directory: {directory}\n")
    
    removed, kept = cleanup_directory(directory)
    
    print(f"Removed {len(removed)} files:")
    for f in sorted(removed):
        print(f"  - {f}")
    
    print(f"\nKept {len(kept)} Python files")
    print("=" * 80)

if __name__ == '__main__':
    main()

