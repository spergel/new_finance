#!/usr/bin/env python3
"""
Post-processing validation and cleanup for BDC investment data.

This module provides functions to clean up parsed investment data by:
1. Removing industry prefixes from company names
2. Validating that company names aren't investment types or industries
3. Ensuring consistent industries for the same company
"""

import re
from typing import Dict, List, Optional


# Investment type keywords (should not appear as company names)
INVESTMENT_TYPE_KEYWORDS = {
    'first lien', 'second lien', 'subordinated', 'senior secured', 'junior debt',
    'mezzanine', 'unitranche', 'revolver', 'term loan', 'delayed draw',
    'preferred', 'common', 'equity', 'warrant', 'warrants', 'debt', 'loan',
    'notes', 'bonds', 'sr secured', 'secured', 'unsecured'
}

# Industry keywords that shouldn't be standalone company names
INDUSTRY_KEYWORDS = {
    'software', 'technology', 'healthcare', 'health care', 'consumer',
    'services', 'financial', 'diversified', 'business', 'energy', 'real estate',
    'management', 'development', 'equipment', 'hardware', 'internet', 'media',
    'engineering', 'insurance', 'utilities', 'hotel', 'gaming', 'leisure',
    'transportation', 'cargo', 'chemicals', 'plastics', 'rubber', 'metals',
    'mining', 'containers', 'packaging', 'glass'
}


def is_investment_type(text: str) -> bool:
    """Check if text looks like an investment type."""
    if not text:
        return False
    
    text_lower = text.lower().strip()
    
    # Common investment type patterns
    investment_patterns = [
        r'^(first|second|subordinated|senior|junior|mezzanine|unitranche)',
        r'(lien|debt|loan|revolver|term|draw|secured|unsecured)$',
        r'^(sr|sr\.)\s+secured',
        r'^preferred\s+(equity|units?|stock)?$',
        r'^common\s+(equity|units?|membership|stock)?$',
        r'^warrants?$',
        r'^equity\s+(securities)?$',
        r'^debt\s+investments?$',
    ]
    
    for pattern in investment_patterns:
        if re.search(pattern, text_lower):
            return True
    
    # Check for investment type keywords in short text
    if len(text) < 50:
        for keyword in INVESTMENT_TYPE_KEYWORDS:
            if keyword in text_lower:
                return True
    
    return False


def is_industry_name(text: str) -> bool:
    """Check if text looks like an industry name."""
    if not text:
        return False
    
    text_lower = text.lower().strip()
    
    # But allow if it's followed by a company name (e.g., "Software Company Inc")
    if re.search(r'(inc\.?|llc|ltd\.?|corp\.?|corporation|company|co\.?)$', text_lower):
        return False
    
    # Common industry patterns
    industry_patterns = [
        r'^(diversified|business|consumer|financial|energy|real estate|internet|software|hardware|technology|healthcare|health care)',
        r'^(equipment|services|management|development|insurance|utilities|hotel|gaming|leisure|transportation|cargo|chemicals)',
        r'^(metals|mining|containers|packaging|glass|media|engineering|retail|aerospace|defense)',
        r'^(software|hardware|internet)\s+(and|&)',
        r'^(energy|equipment)\s+(and|&)',
        r'^(health\s+care|healthcare)\s+(technology|providers)',
    ]
    
    for pattern in industry_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def clean_company_name(name: str) -> str:
    """Clean company name by removing industry prefixes and normalizing."""
    if not name:
        return ""
    
    # Remove footnote patterns
    name = re.sub(r'\s*\([A-Z0-9]+\)', '', name)
    name = re.sub(r'\s*\([^)]*\d+[^)]*\)', '', name)
    
    # Remove industry prefixes that got mixed in
    industry_prefixes = [
        r'^(Diversified\s+(Consumer|Financial)\s+Services)\s+',
        r'^(Internet\s+Software\s+(and|&)\s+Services?)\s+',
        r'^(Software\s+(and|&)\s+Services?)\s+',
        r'^(Technology\s+Hardware)\s+',
        r'^(Energy\s+Equipment\s+(and|&)\s+Services?)\s+',
        r'^(Health\s+Care\s+Technology)\s+',
        r'^(Healthcare\s+Providers?\s+(and|&)\s+Services?)\s+',
        r'^(Real\s+Estate\s+Management)\s+',
        r'^(Debt\s+Investments?)\s+',
        r'^(Equity\s+Securities?)\s+',
    ]
    
    for pattern in industry_prefixes:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Remove trailing industry suffixes (but be careful - some companies legitimately have these)
    # Only remove if it's clearly an industry name, not part of company name
    industry_suffixes = [
        r'\s+(Software|Hardware|Technology|Services|Equipment|Management|Development)$',
    ]
    
    # Only remove if the name is suspiciously short or doesn't have a legal suffix
    if len(name) < 30 and not re.search(r'\b(inc\.?|llc|ltd\.?|corp\.?|corporation|company|co\.?)\b', name, re.IGNORECASE):
        for pattern in industry_suffixes:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Normalize whitespace
    name = ' '.join(name.split())
    
    return name.strip()


def validate_and_clean_investment(investment: Dict) -> Optional[Dict]:
    """Validate and clean a single investment record."""
    company_name = investment.get('company_name', '').strip()
    investment_type = investment.get('investment_type', '').strip()
    industry = investment.get('industry', '').strip()
    
    # Skip if company name is empty
    if not company_name:
        return None
    
    # Check if company name is actually an investment type
    if is_investment_type(company_name):
        # This shouldn't happen after our fixes, but handle it anyway
        return None
    
    # Check if company name is actually an industry
    if is_industry_name(company_name) and not re.search(r'\b(inc\.?|llc|ltd\.?|corp\.?|corporation|company|co\.?)\b', company_name, re.IGNORECASE):
        # This is an industry name, not a company
        return None
    
    # Clean company name
    cleaned_name = clean_company_name(company_name)
    
    if not cleaned_name:
        return None
    
    # Create cleaned investment
    cleaned = investment.copy()
    cleaned['company_name'] = cleaned_name
    
    return cleaned


def normalize_company_name_for_grouping(name: str) -> str:
    """Normalize company name for grouping (to find same companies with different variations)."""
    if not name:
        return ""
    
    # Remove common suffixes for grouping
    name = re.sub(r'\s*\([^)]*\)', '', name)  # Remove parentheticals
    name = re.sub(r'\s*,\s*(Inc\.?|LLC|L\.P\.|Corp\.?|Corporation|Company|Co\.?)\s*$', '', name, flags=re.IGNORECASE)
    name = name.lower().strip()
    
    return name


def ensure_consistent_industries(investments: List[Dict]) -> List[Dict]:
    """Ensure companies have consistent industries across all investments."""
    # Group investments by normalized company name
    by_company = {}
    for inv in investments:
        normalized = normalize_company_name_for_grouping(inv.get('company_name', ''))
        if normalized:
            if normalized not in by_company:
                by_company[normalized] = []
            by_company[normalized].append(inv)
    
    # For each company, find the most common non-Unknown industry
    company_industries = {}
    for normalized, company_invs in by_company.items():
        industries = {}
        for inv in company_invs:
            industry = inv.get('industry', 'Unknown').strip()
            if industry and industry != 'Unknown':
                industries[industry] = industries.get(industry, 0) + 1
        
        # Use most common industry, or first non-Unknown if tie
        if industries:
            most_common = max(industries.items(), key=lambda x: x[1])[0]
            company_industries[normalized] = most_common
    
    # Update investments with consistent industries
    cleaned = []
    for inv in investments:
        normalized = normalize_company_name_for_grouping(inv.get('company_name', ''))
        if normalized and normalized in company_industries:
            # Update industry if it's Unknown or inconsistent
            current_industry = inv.get('industry', 'Unknown').strip()
            if current_industry == 'Unknown' or (normalized in by_company and len(set(inv.get('industry', '') for inv in by_company[normalized])) > 1):
                inv = inv.copy()
                inv['industry'] = company_industries[normalized]
        cleaned.append(inv)
    
    return cleaned


def post_process_investments(investments: List[Dict]) -> List[Dict]:
    """Post-process a list of investments to clean and validate them."""
    # Step 1: Validate and clean individual investments
    cleaned = []
    for inv in investments:
        validated = validate_and_clean_investment(inv)
        if validated:
            cleaned.append(validated)
    
    # Step 2: Ensure consistent industries
    cleaned = ensure_consistent_industries(cleaned)
    
    return cleaned

