#!/usr/bin/env python3
"""
Fix common syntax errors in parser files.

Fixes:
1. Unterminated triple-quoted strings (finds and closes them)
2. Indentation errors (fixes common patterns)
3. Tab/space mixing (converts tabs to spaces)
"""

import os
import re
import sys

PARSERS_TO_FIX = {
    'msdl_parser.py': {'line': 347, 'type': 'unterminated_string'},
    'cswc_parser.py': {'line': 529, 'type': 'indent'},
    'gsbd_parser.py': {'line': 708, 'type': 'unterminated_string'},
    'psec_parser.py': {'line': 349, 'type': 'unterminated_string'},
    'nmfc_parser.py': {'line': 1026, 'type': 'unterminated_string'},
    'pflt_parser.py': {'line': 620, 'type': 'unterminated_string'},
    'cgbd_parser.py': {'line': 607, 'type': 'indent'},
    'bbdc_parser.py': {'line': 449, 'type': 'indent'},
    'fdus_parser.py': {'line': 797, 'type': 'unterminated_string'},
    'slrc_parser.py': {'line': 595, 'type': 'unterminated_string'},
    'bcsf_parser.py': {'line': 631, 'type': 'tabs'},
    'tcpc_parser.py': {'line': 1060, 'type': 'unterminated_string'},
    'cion_parser.py': {'line': 583, 'type': 'unterminated_string'},
    'ncdl_parser.py': {'line': 446, 'type': 'unterminated_string'},
}

def fix_unterminated_string(filepath, problem_line):
    """Fix unterminated triple-quoted strings."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the problematic line
    if problem_line > len(lines):
        print(f"  Line {problem_line} is beyond file length ({len(lines)} lines)")
        return False
    
    # Look for triple quotes that aren't closed
    for i in range(max(0, problem_line - 10), min(len(lines), problem_line + 50)):
        line = lines[i]
        # Check if this line has an opening """ without closing
        if '"""' in line:
            # Count quotes
            quote_count = line.count('"""')
            if quote_count == 1:  # Only opening, no closing
                # Try to find where it should close
                # Look ahead for the next """ or end of function/class
                for j in range(i + 1, min(len(lines), i + 200)):
                    if '"""' in lines[j]:
                        # Found closing quote, but might be on wrong line
                        break
                else:
                    # No closing found - add it at end of docstring content
                    # Find the end of the docstring by looking for next def/class or blank line
                    for j in range(i + 1, min(len(lines), i + 50)):
                        if lines[j].strip().startswith('def ') or lines[j].strip().startswith('class '):
                            # Insert closing """ before this line
                            indent = len(lines[i]) - len(lines[i].lstrip())
                            lines.insert(j, ' ' * indent + '"""\n')
                            print(f"  Fixed: Added closing \"\"\" before line {j+1}")
                            break
                    else:
                        # Just add it after the opening line
                        indent = len(lines[i]) - len(lines[i].lstrip())
                        next_line_idx = i + 1
                        if next_line_idx < len(lines):
                            lines.insert(next_line_idx, ' ' * indent + '"""\n')
                            print(f"  Fixed: Added closing \"\"\" after line {i+1}")
                        else:
                            lines.append(' ' * indent + '"""\n')
                            print(f"  Fixed: Added closing \"\"\" at end of file")
                    break
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    return True

def fix_indentation(filepath, problem_line):
    """Fix indentation errors."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if problem_line > len(lines):
        return False
    
    # Check context around the problem line
    problem_idx = problem_line - 1
    line = lines[problem_idx]
    
    # Get indentation of previous non-empty line
    prev_indent = 0
    for i in range(problem_idx - 1, max(0, problem_idx - 10), -1):
        if lines[i].strip():
            prev_indent = len(lines[i]) - len(lines[i].lstrip())
            break
    
    # Fix the indentation
    stripped = line.lstrip()
    if stripped:
        # Use same indent as previous line or one level more if it looks like continuation
        if stripped.startswith('if ') or stripped.startswith('def ') or stripped.startswith('class '):
            new_indent = prev_indent
        else:
            new_indent = prev_indent + 4  # Standard Python indent
        lines[problem_idx] = ' ' * new_indent + stripped
        print(f"  Fixed: Adjusted indentation on line {problem_line}")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    return True

def fix_tabs(filepath, problem_line):
    """Convert tabs to spaces."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace tabs with 4 spaces
    new_content = content.replace('\t', '    ')
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  Fixed: Converted tabs to spaces")
        return True
    return False

def main():
    """Fix all parser syntax errors."""
    print("="*80)
    print("FIXING PARSER SYNTAX ERRORS")
    print("="*80)
    print()
    
    fixed = 0
    failed = 0
    
    for filename, info in PARSERS_TO_FIX.items():
        filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), filename)
        if not os.path.exists(filepath):
            print(f"[SKIP] {filename} - file not found")
            continue
        
        print(f"Fixing {filename}...")
        
        try:
            if info['type'] == 'unterminated_string':
                if fix_unterminated_string(filepath, info['line']):
                    fixed += 1
                else:
                    failed += 1
            elif info['type'] == 'indent':
                if fix_indentation(filepath, info['line']):
                    fixed += 1
                else:
                    failed += 1
            elif info['type'] == 'tabs':
                if fix_tabs(filepath, info['line']):
                    fixed += 1
                else:
                    failed += 1
            
            # Verify the fix
            try:
                compile(open(filepath).read(), filepath, 'exec')
                print(f"  [OK] Syntax is now valid")
            except SyntaxError as e:
                print(f"  [WARNING] Still has syntax error: {e}")
                failed += 1
        except Exception as e:
            print(f"  [ERROR] Failed to fix: {e}")
            failed += 1
        print()
    
    print("="*80)
    print(f"Fixed: {fixed}, Failed: {failed}")
    print("="*80)

if __name__ == '__main__':
    main()






