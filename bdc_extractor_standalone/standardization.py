#!/usr/bin/env python3
"""
Standardization module for BDC investment data.

Maps various company-specific naming conventions to standardized values
for investment types, industries, and reference rates.
"""

import re
from typing import Optional, Dict, List, Tuple

# Investment Type Mappings
# Priority: Most specific first (revolver/delayed draw before base type)
INVESTMENT_TYPE_MAPPINGS: List[Tuple[str, str]] = [
    # Specific variations first
    (r'First\s+Lien\s+Senior\s+Secured\s+Loan\s*-\s*Revolver', 'First Lien Debt - Revolver'),
    (r'First\s+Lien\s+Senior\s+Secured\s+Loan\s*-\s*Delayed\s+Draw', 'First Lien Debt - Delayed Draw'),
    (r'First\s+Lien\s+Revolver', 'First Lien Debt - Revolver'),
    (r'First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan', 'First Lien Debt - Delayed Draw'),
    (r'Unitranche\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan', 'First Lien Debt - Delayed Draw'),
    (r'Senior\s+Secured\s+First\s+Lien\s+Revolver', 'First Lien Debt - Revolver'),
    (r'Senior\s+Secured\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan', 'First Lien Debt - Delayed Draw'),
    
    # Base types
    (r'First\s+Lien\s+Senior\s+Secured\s+Loan', 'First Lien Debt'),
    (r'First\s+Lien\s+Term\s+Loan', 'First Lien Debt'),
    (r'First\s+Lien\s+Senior\s+Secured\s+Term\s+Loan', 'First Lien Debt'),
    (r'Unitranche\s+First\s+Lien\s+Term\s+Loan', 'First Lien Debt'),
    (r'First\s+Lien\s+Secured\s+Debt', 'First Lien Debt'),
    (r'First\s+Lien\s+Debt', 'First Lien Debt'),
    (r'Senior\s+Secured\s+First\s+Lien\s+Term\s+Loan', 'First Lien Debt'),
    
    # Unitranche (only if explicitly stated, not just as part of first lien)
    (r'^Unitranche\s*$', 'Unitranche'),
    
    # Second Lien
    (r'Second\s+Lien\s+Senior\s+Secured\s+Loan', 'Second Lien Debt'),
    (r'Second\s+Lien\s+Term\s+Loan', 'Second Lien Debt'),
    (r'Second\s+Lien\s+Secured\s+Debt', 'Second Lien Debt'),
    (r'Second\s+Lien\s+Debt', 'Second Lien Debt'),
    
    # Subordinated
    (r'Subordinated\s+Debt', 'Subordinated Debt'),
    (r'Subordinated\s+Note', 'Subordinated Debt'),
    (r'CLO\s+Mezzanine', 'Subordinated Debt'),
    (r'Junior\s+Debt', 'Subordinated Debt'),
    (r'Mezzanine\s+Debt', 'Subordinated Debt'),
    
    # Unsecured
    (r'Unsecured\s+Debt', 'Unsecured Debt'),
    (r'Unsecured\s+Note', 'Unsecured Debt'),
    (r'Senior\s+Unsecured\s+Debt', 'Unsecured Debt'),
    
    # Equity
    (r'Common\s+Equity', 'Common Equity'),
    (r'Common\s+Stock', 'Common Equity'),
    (r'Member\s+Units', 'Common Equity'),
    (r'Common\s+Shares', 'Common Equity'),
    
    (r'Preferred\s+Equity', 'Preferred Equity'),
    (r'Preferred\s+Stock', 'Preferred Equity'),
    (r'Preferred\s+Shares', 'Preferred Equity'),
    
    (r'Warrants?', 'Warrants'),
    (r'Stock\s+Warrants?', 'Warrants'),
    
    # Other
    (r'Promissory\s+Note', 'Promissory Note'),
    (r'Note\s+Payable', 'Promissory Note'),
]


# Industry Mappings
# Priority: Most specific/longest first
INDUSTRY_MAPPINGS: List[Tuple[str, str]] = [
    # Technology & Software - most specific first
    (r'Software\s*&\s*Services', 'Software'),
    (r'Software\s+Services', 'Software'),
    (r'^Software\s*$', 'Software'),
    
    (r'Information\s+Technology\s+Services', 'Information Technology Services'),
    (r'IT\s+Services', 'Information Technology Services'),
    (r'Technology\s+Services', 'Information Technology Services'),
    
    (r'High\s+Tech\s+Industries', 'High Tech Industries'),
    (r'^Technology\s*$', 'High Tech Industries'),
    (r'^Tech\s*$', 'High Tech Industries'),
    
    (r'^Telecommunications\s*$', 'Telecommunications'),
    (r'^Telecom\s*$', 'Telecommunications'),
    
    # Healthcare - most specific first
    (r'Healthcare\s*&\s*Pharmaceuticals', 'Healthcare & Pharmaceuticals'),
    (r'Healthcare\s*&\s*Pharma', 'Healthcare & Pharmaceuticals'),
    (r'Health\s+Care\s+Equipment\s*&\s*Services', 'Healthcare & Pharmaceuticals'),
    (r'Pharmaceuticals\s+Biotechnology\s+Life\s+Sciences', 'Healthcare & Pharmaceuticals'),
    (r'Biotechnology\s+Life\s+Sciences', 'Healthcare & Pharmaceuticals'),
    (r'Healthcare\s+Products', 'Healthcare & Pharmaceuticals'),
    (r'Health\s+Products', 'Healthcare & Pharmaceuticals'),
    (r'^Healthcare\s*$', 'Healthcare & Pharmaceuticals'),
    (r'^Health\s+Care\s*$', 'Healthcare & Pharmaceuticals'),
    (r'^Pharmaceuticals\s*$', 'Healthcare & Pharmaceuticals'),
    
    (r'Medical\s+Services', 'Medical Services'),
    (r'Healthcare\s+Services', 'Medical Services'),  # When specifically medical services
    
    # Financial Services
    (r'Diversified\s+Financial\s+Services', 'Diversified Financial Services'),
    (r'Diversified\s+Financials', 'Diversified Financial Services'),
    (r'^Financial\s+Services\s*$', 'Diversified Financial Services'),
    (r'^Finance\s*$', 'Diversified Financial Services'),
    (r'FIRE:\s*Finance', 'Diversified Financial Services'),
    
    (r'^Insurance\s*$', 'Insurance'),
    (r'FIRE:\s*Insurance', 'Insurance'),
    
    (r'^Banking\s*$', 'Banking & Finance'),
    (r'Banking\s*&\s*Finance', 'Banking & Finance'),
    
    # Business Services
    (r'Business\s+Services', 'Business Services'),
    (r'Services:\s*Business', 'Business Services'),
    (r'Commercial\s*&\s*Professional\s+Services', 'Business Services'),
    (r'Professional\s+Services', 'Business Services'),
    
    (r'Consumer\s+Services', 'Consumer Services'),
    (r'Services:\s*Consumer', 'Consumer Services'),
    
    (r'Environmental\s+Industries', 'Environmental Industries'),
    (r'Environmental\s+Services', 'Environmental Industries'),
    
    (r'Utilities:\s*Services', 'Utilities: Services'),
    (r'Utilities:\s*Water', 'Utilities: Water'),
    (r'^Utilities\s*$', 'Utilities: Services'),
    (r'Water\s+Utilities', 'Utilities: Water'),
    
    # Manufacturing & Industrial
    (r'Aerospace\s*&\s*Defense', 'Aerospace & Defense'),
    (r'^Aerospace\s*$', 'Aerospace & Defense'),
    (r'Defense\s+Manufacturing', 'Aerospace & Defense'),
    
    (r'Capital\s+Equipment', 'Capital Equipment'),
    (r'Equipment\s+Manufacturing', 'Capital Equipment'),
    
    (r'Component\s+Manufacturing', 'Component Manufacturing'),
    (r'^Components\s*$', 'Component Manufacturing'),
    
    (r'^Automotive\s*$', 'Automotive'),
    (r'Automobiles\s*&\s*Components', 'Automotive'),
    
    (r'Construction\s*&\s*Building', 'Construction & Building'),
    (r'^Construction\s*$', 'Construction & Building'),
    
    # Consumer Goods
    (r'Consumer\s+Goods:\s*Durable', 'Consumer Goods: Durable'),
    (r'Durable\s+Goods', 'Consumer Goods: Durable'),
    (r'Durables\s*&\s*Apparel', 'Consumer Goods: Durable'),
    
    (r'Consumer\s+Goods:\s*Non-Durable', 'Consumer Goods: Non-Durable'),
    (r'Non-Durable\s+Goods', 'Consumer Goods: Non-Durable'),
    
    (r'Consumer\s+Products', 'Consumer Products'),
    (r'^Consumer\s*$', 'Consumer Products'),
    
    (r'^Retail\s*$', 'Retail'),
    (r'^Retailing\s*$', 'Retail'),
    
    # Materials & Chemicals
    (r'Chemicals,\s*Plastics\s*&\s*Rubber', 'Chemicals, Plastics & Rubber'),
    (r'Chemicals\s*&\s*Materials', 'Chemicals, Plastics & Rubber'),
    
    (r'Containers,\s*Packaging\s*&\s*Glass', 'Containers, Packaging & Glass'),
    (r'^Packaging\s*$', 'Containers, Packaging & Glass'),
    
    (r'Metals\s*&\s*Mining', 'Metals & Mining'),
    (r'^Metals\s*$', 'Metals & Mining'),
    (r'^Mining\s*$', 'Metals & Mining'),
    
    # Energy & Utilities
    (r'Energy\s+Electicity', 'Energy'),  # Fix typo
    (r'^Electicity\s*$', 'Energy'),  # Fix typo
    (r'^Energy\s*$', 'Energy'),
    (r'Oil\s*&\s*Gas', 'Energy'),
    
    # Transportation
    (r'Transportation:\s*Cargo', 'Transportation: Cargo'),
    (r'Transportation\s+services', 'Transportation: Cargo'),
    (r'Transportation\s*&\s*Logistics', 'Transportation: Cargo'),
    (r'^Logistics\s*$', 'Transportation: Cargo'),
    
    # Media & Entertainment
    (r'Media:\s*Diversified\s*&\s*Production', 'Media: Diversified & Production'),
    (r'Media\s*&\s*Entertainment', 'Media: Diversified & Production'),
    (r'^Entertainment\s*$', 'Media: Diversified & Production'),
    
    (r'Leisure\s+Products\s*&\s*Services\s*\d*', 'Leisure Products & Services'),  # Strip trailing numbers
    (r'Hotel,\s*Gaming\s*&\s*Leisure', 'Leisure Products & Services'),
    (r'^Leisure\s*$', 'Leisure Products & Services'),
    (r'^Hospitality\s*$', 'Leisure Products & Services'),
    
    # Food & Beverage
    (r'Beverage,\s*Food\s*&\s*Tobacco', 'Food & Beverage'),
    (r'Food\s*&\s*Beverage', 'Food & Beverage'),
    (r'^Beverage\s*$', 'Food & Beverage'),
    (r'^Beverages\s*$', 'Food & Beverage'),
    
    (r'Restaurant\s+Services', 'Restaurant & Food Services'),
    (r'Food\s+Services', 'Restaurant & Food Services'),
    
    # Real Estate
    (r'^Real\s+Estate\s*$', 'Real Estate'),
    (r'REIT', 'Real Estate'),
    (r'Real\s+Estate\s+Services', 'Real Estate'),
    (r'FIRE:\s*Real\s+Estate', 'Real Estate'),
    
    # Investment Vehicles
    (r'Investment\s+Vehicles', 'Investment Vehicles'),
    (r'CLO', 'Investment Vehicles'),
    (r'BDC\s+Funds', 'Investment Vehicles'),
    
    # Wholesale & Distribution
    (r'^Wholesale\s*$', 'Wholesale'),
    (r'Wholesale\s+Distribution', 'Wholesale'),
    
    (r'^Distribution\s*$', 'Distribution'),
    (r'Distribution\s+Services', 'Distribution'),
]


# Reference Rate Mappings
REFERENCE_RATE_MAPPINGS: List[Tuple[str, str]] = [
    (r'^SOFR\s*$', 'SOFR'),
    (r'Secured\s+Overnight\s+Financing\s+Rate', 'SOFR'),
    (r'^S\s*$', 'SOFR'),  # In formulas like "S + 5%"
    
    (r'^LIBOR\s*$', 'LIBOR'),
    (r'London\s+Interbank\s+Offered\s+Rate', 'LIBOR'),
    (r'^L\s*$', 'LIBOR'),  # In formulas
    
    (r'^PRIME\s*$', 'PRIME'),
    (r'Prime\s+Rate', 'PRIME'),
    (r'^P\s*$', 'PRIME'),  # In formulas
    
    (r'^EURIBOR\s*$', 'EURIBOR'),
    (r'Euro\s+Interbank\s+Offered\s+Rate', 'EURIBOR'),
    (r'^E\s*$', 'EURIBOR'),  # In formulas
    (r'^SN\s*$', 'EURIBOR'),  # Sometimes used for EURIBOR
    
    (r'^FED\s+FUNDS\s*$', 'FED FUNDS'),
    (r'Federal\s+Funds\s+Rate', 'FED FUNDS'),
    (r'Federal\s+Funds', 'FED FUNDS'),
    (r'^F\s*$', 'FED FUNDS'),  # In formulas
    
    (r'^CDOR\s*$', 'CDOR'),
    (r'Canadian\s+Dollar\s+Offered\s+Rate', 'CDOR'),
    (r'^C\s*$', 'CDOR'),  # In formulas
    
    (r'^BASE\s+RATE\s*$', 'BASE RATE'),
    (r'Base\s+Rate', 'BASE RATE'),
    (r'Benchmark\s+Rate', 'BASE RATE'),
]


def standardize_investment_type(raw_type: Optional[str]) -> str:
    """
    Map raw investment type to standard name.
    
    Args:
        raw_type: Raw investment type string from parser
        
    Returns:
        Standardized investment type name
    """
    if not raw_type or raw_type.strip() == '':
        return 'Unknown'
    
    raw_type = raw_type.strip()
    
    # Remove common prefixes
    raw_type = re.sub(r'^Investment\s+Type\s+', '', raw_type, flags=re.IGNORECASE)
    raw_type = re.sub(r'\s+Investment\s+Type\s*$', '', raw_type, flags=re.IGNORECASE)
    
    # Try to match against mappings (in order - most specific first)
    for pattern, standard in INVESTMENT_TYPE_MAPPINGS:
        if re.search(pattern, raw_type, re.IGNORECASE):
            return standard
    
    # If no match found, return original (don't force to Unknown)
    return raw_type


def standardize_industry(raw_industry: Optional[str]) -> str:
    """
    Map raw industry name to standard name.
    
    Args:
        raw_industry: Raw industry string from parser
        
    Returns:
        Standardized industry name
    """
    if not raw_industry or raw_industry.strip() == '':
        return 'Unknown'
    
    raw_industry = raw_industry.strip()
    
    # Clean up common issues
    # Remove trailing numbers (e.g., "Leisure Products & Services 1")
    raw_industry = re.sub(r'\s+\d+\s*$', '', raw_industry)
    
    # Fix typos
    raw_industry = re.sub(r'Energy\s+Electicity', 'Energy', raw_industry, flags=re.IGNORECASE)
    raw_industry = re.sub(r'^Electicity\s*$', 'Energy', raw_industry, flags=re.IGNORECASE)
    
    # Try to match against mappings (in order - most specific first)
    for pattern, standard in INDUSTRY_MAPPINGS:
        if re.match(pattern, raw_industry, re.IGNORECASE):
            return standard
    
    # If no match found, return original (don't force to Unknown)
    return raw_industry


def standardize_reference_rate(raw_rate: Optional[str]) -> Optional[str]:
    """
    Map raw reference rate to standard name.
    
    Args:
        raw_rate: Raw reference rate string from parser
        
    Returns:
        Standardized reference rate name, or None if not found
    """
    if not raw_rate or raw_rate.strip() == '':
        return None
    
    raw_rate = raw_rate.strip().upper()
    
    # Try to match against mappings
    for pattern, standard in REFERENCE_RATE_MAPPINGS:
        if re.match(pattern, raw_rate, re.IGNORECASE):
            return standard
    
    # If no match found, return original (uppercased)
    return raw_rate


def standardize_spread(spread_val: Optional[str]) -> Optional[str]:
    """
    Format spread value as percentage string.
    
    Args:
        spread_val: Spread value (may be decimal, percentage, or basis points)
        
    Returns:
        Formatted spread as percentage string (e.g., "5.25%"), or None
    """
    if not spread_val:
        return None
    
    try:
        # Remove % if present
        val_str = str(spread_val).replace('%', '').strip()
        val = float(val_str)
        
        # If value > 20, assume it's in basis points
        if val > 20:
            val = val / 100.0
        
        # Format as percentage
        if val == int(val):
            return f"{int(val)}%"
        else:
            return f"{val:.4f}".rstrip('0').rstrip('.') + "%"
    except (ValueError, TypeError):
        # If can't parse, return as-is
        return str(spread_val) if spread_val else None

"""
Standardization module for BDC investment data.

Maps various company-specific naming conventions to standardized values
for investment types, industries, and reference rates.
"""

import re
from typing import Optional, Dict, List, Tuple

# Investment Type Mappings
# Priority: Most specific first (revolver/delayed draw before base type)
INVESTMENT_TYPE_MAPPINGS: List[Tuple[str, str]] = [
    # Specific variations first
    (r'First\s+Lien\s+Senior\s+Secured\s+Loan\s*-\s*Revolver', 'First Lien Debt - Revolver'),
    (r'First\s+Lien\s+Senior\s+Secured\s+Loan\s*-\s*Delayed\s+Draw', 'First Lien Debt - Delayed Draw'),
    (r'First\s+Lien\s+Revolver', 'First Lien Debt - Revolver'),
    (r'First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan', 'First Lien Debt - Delayed Draw'),
    (r'Unitranche\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan', 'First Lien Debt - Delayed Draw'),
    (r'Senior\s+Secured\s+First\s+Lien\s+Revolver', 'First Lien Debt - Revolver'),
    (r'Senior\s+Secured\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan', 'First Lien Debt - Delayed Draw'),
    
    # Base types
    (r'First\s+Lien\s+Senior\s+Secured\s+Loan', 'First Lien Debt'),
    (r'First\s+Lien\s+Term\s+Loan', 'First Lien Debt'),
    (r'First\s+Lien\s+Senior\s+Secured\s+Term\s+Loan', 'First Lien Debt'),
    (r'Unitranche\s+First\s+Lien\s+Term\s+Loan', 'First Lien Debt'),
    (r'First\s+Lien\s+Secured\s+Debt', 'First Lien Debt'),
    (r'First\s+Lien\s+Debt', 'First Lien Debt'),
    (r'Senior\s+Secured\s+First\s+Lien\s+Term\s+Loan', 'First Lien Debt'),
    
    # Unitranche (only if explicitly stated, not just as part of first lien)
    (r'^Unitranche\s*$', 'Unitranche'),
    
    # Second Lien
    (r'Second\s+Lien\s+Senior\s+Secured\s+Loan', 'Second Lien Debt'),
    (r'Second\s+Lien\s+Term\s+Loan', 'Second Lien Debt'),
    (r'Second\s+Lien\s+Secured\s+Debt', 'Second Lien Debt'),
    (r'Second\s+Lien\s+Debt', 'Second Lien Debt'),
    
    # Subordinated
    (r'Subordinated\s+Debt', 'Subordinated Debt'),
    (r'Subordinated\s+Note', 'Subordinated Debt'),
    (r'CLO\s+Mezzanine', 'Subordinated Debt'),
    (r'Junior\s+Debt', 'Subordinated Debt'),
    (r'Mezzanine\s+Debt', 'Subordinated Debt'),
    
    # Unsecured
    (r'Unsecured\s+Debt', 'Unsecured Debt'),
    (r'Unsecured\s+Note', 'Unsecured Debt'),
    (r'Senior\s+Unsecured\s+Debt', 'Unsecured Debt'),
    
    # Equity
    (r'Common\s+Equity', 'Common Equity'),
    (r'Common\s+Stock', 'Common Equity'),
    (r'Member\s+Units', 'Common Equity'),
    (r'Common\s+Shares', 'Common Equity'),
    
    (r'Preferred\s+Equity', 'Preferred Equity'),
    (r'Preferred\s+Stock', 'Preferred Equity'),
    (r'Preferred\s+Shares', 'Preferred Equity'),
    
    (r'Warrants?', 'Warrants'),
    (r'Stock\s+Warrants?', 'Warrants'),
    
    # Other
    (r'Promissory\s+Note', 'Promissory Note'),
    (r'Note\s+Payable', 'Promissory Note'),
]


# Industry Mappings
# Priority: Most specific/longest first
INDUSTRY_MAPPINGS: List[Tuple[str, str]] = [
    # Technology & Software - most specific first
    (r'Software\s*&\s*Services', 'Software'),
    (r'Software\s+Services', 'Software'),
    (r'^Software\s*$', 'Software'),
    
    (r'Information\s+Technology\s+Services', 'Information Technology Services'),
    (r'IT\s+Services', 'Information Technology Services'),
    (r'Technology\s+Services', 'Information Technology Services'),
    
    (r'High\s+Tech\s+Industries', 'High Tech Industries'),
    (r'^Technology\s*$', 'High Tech Industries'),
    (r'^Tech\s*$', 'High Tech Industries'),
    
    (r'^Telecommunications\s*$', 'Telecommunications'),
    (r'^Telecom\s*$', 'Telecommunications'),
    
    # Healthcare - most specific first
    (r'Healthcare\s*&\s*Pharmaceuticals', 'Healthcare & Pharmaceuticals'),
    (r'Healthcare\s*&\s*Pharma', 'Healthcare & Pharmaceuticals'),
    (r'Health\s+Care\s+Equipment\s*&\s*Services', 'Healthcare & Pharmaceuticals'),
    (r'Pharmaceuticals\s+Biotechnology\s+Life\s+Sciences', 'Healthcare & Pharmaceuticals'),
    (r'Biotechnology\s+Life\s+Sciences', 'Healthcare & Pharmaceuticals'),
    (r'Healthcare\s+Products', 'Healthcare & Pharmaceuticals'),
    (r'Health\s+Products', 'Healthcare & Pharmaceuticals'),
    (r'^Healthcare\s*$', 'Healthcare & Pharmaceuticals'),
    (r'^Health\s+Care\s*$', 'Healthcare & Pharmaceuticals'),
    (r'^Pharmaceuticals\s*$', 'Healthcare & Pharmaceuticals'),
    
    (r'Medical\s+Services', 'Medical Services'),
    (r'Healthcare\s+Services', 'Medical Services'),  # When specifically medical services
    
    # Financial Services
    (r'Diversified\s+Financial\s+Services', 'Diversified Financial Services'),
    (r'Diversified\s+Financials', 'Diversified Financial Services'),
    (r'^Financial\s+Services\s*$', 'Diversified Financial Services'),
    (r'^Finance\s*$', 'Diversified Financial Services'),
    (r'FIRE:\s*Finance', 'Diversified Financial Services'),
    
    (r'^Insurance\s*$', 'Insurance'),
    (r'FIRE:\s*Insurance', 'Insurance'),
    
    (r'^Banking\s*$', 'Banking & Finance'),
    (r'Banking\s*&\s*Finance', 'Banking & Finance'),
    
    # Business Services
    (r'Business\s+Services', 'Business Services'),
    (r'Services:\s*Business', 'Business Services'),
    (r'Commercial\s*&\s*Professional\s+Services', 'Business Services'),
    (r'Professional\s+Services', 'Business Services'),
    
    (r'Consumer\s+Services', 'Consumer Services'),
    (r'Services:\s*Consumer', 'Consumer Services'),
    
    (r'Environmental\s+Industries', 'Environmental Industries'),
    (r'Environmental\s+Services', 'Environmental Industries'),
    
    (r'Utilities:\s*Services', 'Utilities: Services'),
    (r'Utilities:\s*Water', 'Utilities: Water'),
    (r'^Utilities\s*$', 'Utilities: Services'),
    (r'Water\s+Utilities', 'Utilities: Water'),
    
    # Manufacturing & Industrial
    (r'Aerospace\s*&\s*Defense', 'Aerospace & Defense'),
    (r'^Aerospace\s*$', 'Aerospace & Defense'),
    (r'Defense\s+Manufacturing', 'Aerospace & Defense'),
    
    (r'Capital\s+Equipment', 'Capital Equipment'),
    (r'Equipment\s+Manufacturing', 'Capital Equipment'),
    
    (r'Component\s+Manufacturing', 'Component Manufacturing'),
    (r'^Components\s*$', 'Component Manufacturing'),
    
    (r'^Automotive\s*$', 'Automotive'),
    (r'Automobiles\s*&\s*Components', 'Automotive'),
    
    (r'Construction\s*&\s*Building', 'Construction & Building'),
    (r'^Construction\s*$', 'Construction & Building'),
    
    # Consumer Goods
    (r'Consumer\s+Goods:\s*Durable', 'Consumer Goods: Durable'),
    (r'Durable\s+Goods', 'Consumer Goods: Durable'),
    (r'Durables\s*&\s*Apparel', 'Consumer Goods: Durable'),
    
    (r'Consumer\s+Goods:\s*Non-Durable', 'Consumer Goods: Non-Durable'),
    (r'Non-Durable\s+Goods', 'Consumer Goods: Non-Durable'),
    
    (r'Consumer\s+Products', 'Consumer Products'),
    (r'^Consumer\s*$', 'Consumer Products'),
    
    (r'^Retail\s*$', 'Retail'),
    (r'^Retailing\s*$', 'Retail'),
    
    # Materials & Chemicals
    (r'Chemicals,\s*Plastics\s*&\s*Rubber', 'Chemicals, Plastics & Rubber'),
    (r'Chemicals\s*&\s*Materials', 'Chemicals, Plastics & Rubber'),
    
    (r'Containers,\s*Packaging\s*&\s*Glass', 'Containers, Packaging & Glass'),
    (r'^Packaging\s*$', 'Containers, Packaging & Glass'),
    
    (r'Metals\s*&\s*Mining', 'Metals & Mining'),
    (r'^Metals\s*$', 'Metals & Mining'),
    (r'^Mining\s*$', 'Metals & Mining'),
    
    # Energy & Utilities
    (r'Energy\s+Electicity', 'Energy'),  # Fix typo
    (r'^Electicity\s*$', 'Energy'),  # Fix typo
    (r'^Energy\s*$', 'Energy'),
    (r'Oil\s*&\s*Gas', 'Energy'),
    
    # Transportation
    (r'Transportation:\s*Cargo', 'Transportation: Cargo'),
    (r'Transportation\s+services', 'Transportation: Cargo'),
    (r'Transportation\s*&\s*Logistics', 'Transportation: Cargo'),
    (r'^Logistics\s*$', 'Transportation: Cargo'),
    
    # Media & Entertainment
    (r'Media:\s*Diversified\s*&\s*Production', 'Media: Diversified & Production'),
    (r'Media\s*&\s*Entertainment', 'Media: Diversified & Production'),
    (r'^Entertainment\s*$', 'Media: Diversified & Production'),
    
    (r'Leisure\s+Products\s*&\s*Services\s*\d*', 'Leisure Products & Services'),  # Strip trailing numbers
    (r'Hotel,\s*Gaming\s*&\s*Leisure', 'Leisure Products & Services'),
    (r'^Leisure\s*$', 'Leisure Products & Services'),
    (r'^Hospitality\s*$', 'Leisure Products & Services'),
    
    # Food & Beverage
    (r'Beverage,\s*Food\s*&\s*Tobacco', 'Food & Beverage'),
    (r'Food\s*&\s*Beverage', 'Food & Beverage'),
    (r'^Beverage\s*$', 'Food & Beverage'),
    (r'^Beverages\s*$', 'Food & Beverage'),
    
    (r'Restaurant\s+Services', 'Restaurant & Food Services'),
    (r'Food\s+Services', 'Restaurant & Food Services'),
    
    # Real Estate
    (r'^Real\s+Estate\s*$', 'Real Estate'),
    (r'REIT', 'Real Estate'),
    (r'Real\s+Estate\s+Services', 'Real Estate'),
    (r'FIRE:\s*Real\s+Estate', 'Real Estate'),
    
    # Investment Vehicles
    (r'Investment\s+Vehicles', 'Investment Vehicles'),
    (r'CLO', 'Investment Vehicles'),
    (r'BDC\s+Funds', 'Investment Vehicles'),
    
    # Wholesale & Distribution
    (r'^Wholesale\s*$', 'Wholesale'),
    (r'Wholesale\s+Distribution', 'Wholesale'),
    
    (r'^Distribution\s*$', 'Distribution'),
    (r'Distribution\s+Services', 'Distribution'),
]


# Reference Rate Mappings
REFERENCE_RATE_MAPPINGS: List[Tuple[str, str]] = [
    (r'^SOFR\s*$', 'SOFR'),
    (r'Secured\s+Overnight\s+Financing\s+Rate', 'SOFR'),
    (r'^S\s*$', 'SOFR'),  # In formulas like "S + 5%"
    
    (r'^LIBOR\s*$', 'LIBOR'),
    (r'London\s+Interbank\s+Offered\s+Rate', 'LIBOR'),
    (r'^L\s*$', 'LIBOR'),  # In formulas
    
    (r'^PRIME\s*$', 'PRIME'),
    (r'Prime\s+Rate', 'PRIME'),
    (r'^P\s*$', 'PRIME'),  # In formulas
    
    (r'^EURIBOR\s*$', 'EURIBOR'),
    (r'Euro\s+Interbank\s+Offered\s+Rate', 'EURIBOR'),
    (r'^E\s*$', 'EURIBOR'),  # In formulas
    (r'^SN\s*$', 'EURIBOR'),  # Sometimes used for EURIBOR
    
    (r'^FED\s+FUNDS\s*$', 'FED FUNDS'),
    (r'Federal\s+Funds\s+Rate', 'FED FUNDS'),
    (r'Federal\s+Funds', 'FED FUNDS'),
    (r'^F\s*$', 'FED FUNDS'),  # In formulas
    
    (r'^CDOR\s*$', 'CDOR'),
    (r'Canadian\s+Dollar\s+Offered\s+Rate', 'CDOR'),
    (r'^C\s*$', 'CDOR'),  # In formulas
    
    (r'^BASE\s+RATE\s*$', 'BASE RATE'),
    (r'Base\s+Rate', 'BASE RATE'),
    (r'Benchmark\s+Rate', 'BASE RATE'),
]


def standardize_investment_type(raw_type: Optional[str]) -> str:
    """
    Map raw investment type to standard name.
    
    Args:
        raw_type: Raw investment type string from parser
        
    Returns:
        Standardized investment type name
    """
    if not raw_type or raw_type.strip() == '':
        return 'Unknown'
    
    raw_type = raw_type.strip()
    
    # Remove common prefixes
    raw_type = re.sub(r'^Investment\s+Type\s+', '', raw_type, flags=re.IGNORECASE)
    raw_type = re.sub(r'\s+Investment\s+Type\s*$', '', raw_type, flags=re.IGNORECASE)
    
    # Try to match against mappings (in order - most specific first)
    for pattern, standard in INVESTMENT_TYPE_MAPPINGS:
        if re.search(pattern, raw_type, re.IGNORECASE):
            return standard
    
    # If no match found, return original (don't force to Unknown)
    return raw_type


def standardize_industry(raw_industry: Optional[str]) -> str:
    """
    Map raw industry name to standard name.
    
    Args:
        raw_industry: Raw industry string from parser
        
    Returns:
        Standardized industry name
    """
    if not raw_industry or raw_industry.strip() == '':
        return 'Unknown'
    
    raw_industry = raw_industry.strip()
    
    # Clean up common issues
    # Remove trailing numbers (e.g., "Leisure Products & Services 1")
    raw_industry = re.sub(r'\s+\d+\s*$', '', raw_industry)
    
    # Fix typos
    raw_industry = re.sub(r'Energy\s+Electicity', 'Energy', raw_industry, flags=re.IGNORECASE)
    raw_industry = re.sub(r'^Electicity\s*$', 'Energy', raw_industry, flags=re.IGNORECASE)
    
    # Try to match against mappings (in order - most specific first)
    for pattern, standard in INDUSTRY_MAPPINGS:
        if re.match(pattern, raw_industry, re.IGNORECASE):
            return standard
    
    # If no match found, return original (don't force to Unknown)
    return raw_industry


def standardize_reference_rate(raw_rate: Optional[str]) -> Optional[str]:
    """
    Map raw reference rate to standard name.
    
    Args:
        raw_rate: Raw reference rate string from parser
        
    Returns:
        Standardized reference rate name, or None if not found
    """
    if not raw_rate or raw_rate.strip() == '':
        return None
    
    raw_rate = raw_rate.strip().upper()
    
    # Try to match against mappings
    for pattern, standard in REFERENCE_RATE_MAPPINGS:
        if re.match(pattern, raw_rate, re.IGNORECASE):
            return standard
    
    # If no match found, return original (uppercased)
    return raw_rate


def standardize_spread(spread_val: Optional[str]) -> Optional[str]:
    """
    Format spread value as percentage string.
    
    Args:
        spread_val: Spread value (may be decimal, percentage, or basis points)
        
    Returns:
        Formatted spread as percentage string (e.g., "5.25%"), or None
    """
    if not spread_val:
        return None
    
    try:
        # Remove % if present
        val_str = str(spread_val).replace('%', '').strip()
        val = float(val_str)
        
        # If value > 20, assume it's in basis points
        if val > 20:
            val = val / 100.0
        
        # Format as percentage
        if val == int(val):
            return f"{int(val)}%"
        else:
            return f"{val:.4f}".rstrip('0').rstrip('.') + "%"
    except (ValueError, TypeError):
        # If can't parse, return as-is
        return str(spread_val) if spread_val else None





