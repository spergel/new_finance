#!/usr/bin/env python3
"""Improve HTML fallback matching with fuzzy matching and better normalization."""

import re
from difflib import SequenceMatcher

def normalize_company_name(name: str) -> str:
    """Normalize company name for better matching."""
    if not name:
        return ""
    
    # Convert to lowercase
    name = name.lower().strip()
    
    # Remove common suffixes and legal entities
    name = re.sub(r'\s*(inc\.?|incorporated|corp\.?|corporation|ltd\.?|limited|llc\.?|lp\.?|l\.p\.?|l\.l\.c\.?)\s*$', '', name)
    
    # Remove parentheticals (like "(f/k/a ...)")
    name = re.sub(r'\s*\([^)]*\)\s*', ' ', name)
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Remove common prefixes
    name = re.sub(r'^(the\s+)', '', name)
    
    return name

def fuzzy_match_company_names(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """Check if two company names are similar enough to match."""
    norm1 = normalize_company_name(name1)
    norm2 = normalize_company_name(name2)
    
    if not norm1 or not norm2:
        return False
    
    # Exact match after normalization
    if norm1 == norm2:
        return True
    
    # Check if one contains the other (for partial matches)
    if norm1 in norm2 or norm2 in norm1:
        return True
    
    # Use sequence matcher for fuzzy matching
    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    return similarity >= threshold

def improve_merge_logic():
    """Return improved merge logic code snippet."""
    return '''
    def _merge_html_data(self, investments: List[Investment], html_data: Dict[str, Dict]):
        """Merge HTML-extracted optional fields into XBRL investments with improved matching."""
        html_by_name = html_data.get('by_name', {})
        html_by_name_type = html_data.get('by_name_type', {})
        
        # Also create a normalized lookup for fuzzy matching
        html_by_normalized = {}
        for html_inv in html_data.get('by_name', {}).values():
            company_name = html_inv.get('company_name', '').strip()
            if company_name:
                normalized = normalize_company_name(company_name)
                if normalized and normalized not in html_by_normalized:
                    html_by_normalized[normalized] = html_inv
        
        merged_count = 0
        for inv in investments:
            company_name_lower = inv.company_name.strip().lower()
            investment_type_lower = inv.investment_type.strip().lower()
            
            html_inv = None
            
            # Strategy 1: Try exact match first (company_name + investment_type)
            key = (company_name_lower, investment_type_lower)
            html_inv = html_by_name_type.get(key)
            
            # Strategy 2: Fallback to company name only
            if not html_inv:
                html_inv = html_by_name.get(company_name_lower)
            
            # Strategy 3: Try normalized matching
            if not html_inv:
                normalized = normalize_company_name(inv.company_name)
                html_inv = html_by_normalized.get(normalized)
            
            # Strategy 4: Fuzzy matching (last resort)
            if not html_inv:
                for html_name, html_inv_candidate in html_by_name.items():
                    if fuzzy_match_company_names(inv.company_name, html_name, threshold=0.8):
                        html_inv = html_inv_candidate
                        break
            
            if html_inv:
                merged = False
                # Only fill in missing fields (same as before)
                # ... rest of merge logic ...
                
                if merged:
                    merged_count += 1
        
        if merged_count > 0:
            logger.info(f"HTML fallback: Merged data for {merged_count} investments")
    '''

if __name__ == '__main__':
    print("Improved matching functions:")
    print("1. normalize_company_name() - Normalizes company names")
    print("2. fuzzy_match_company_names() - Fuzzy matching with threshold")
    print("3. Improved merge logic with 4 matching strategies")
    
    # Test normalization
    test_names = [
        "BRANDNER DESIGN LLC",
        "BRANDNER DESIGN, LLC",
        "Brandner Design Inc.",
        "The Brandner Design Corporation"
    ]
    
    print("\nNormalization test:")
    for name in test_names:
        print(f"  '{name}' -> '{normalize_company_name(name)}'")
    
    print("\nFuzzy matching test:")
    print(f"  'BRANDNER DESIGN LLC' vs 'BRANDNER DESIGN, LLC': {fuzzy_match_company_names('BRANDNER DESIGN LLC', 'BRANDNER DESIGN, LLC')}")
    print(f"  'BRANDNER DESIGN LLC' vs 'Brandner Design Inc.': {fuzzy_match_company_names('BRANDNER DESIGN LLC', 'Brandner Design Inc.')}")




