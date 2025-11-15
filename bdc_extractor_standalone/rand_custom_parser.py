#!/usr/bin/env python3
"""
RAND (Rand Capital Corp) Custom Investment Extractor
Parses investment data from RAND_all_facts.csv with proper company name extraction.
"""

import os
import re
import json
import csv
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from pathlib import Path
from datetime import datetime

from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


def parse_rand_identifier(identifier: str) -> Dict[str, str]:
    """Parse RAND identifier to extract company name and investment type.
    
    Examples:
    - "Applied Image, Inc. - $1,750,000 Term Note at 12%" 
      -> company: "Applied Image, Inc.", type: "Term Note"
    - "BMP Food Service Supply Holdco, LLC - $6,835,000 Third Amended and Restated Term Note, $400,000 in principal amount at 13%"
      -> company: "BMP Food Service Supply Holdco, LLC", type: "Term Note"
    - "Carolina Skiff LLC - 6.0825% Class A Common Membership Interest"
      -> company: "Carolina Skiff LLC", type: "Common Equity"
    """
    if not identifier:
        return {'company_name': 'Unknown', 'investment_type': 'Unknown'}
    
    # Decode HTML entities
    identifier = identifier.replace('&amp;', '&').replace('&#x2019;', "'")
    
    # Pattern: "Company Name - Investment Description" or "Company Name -Investment Description"
    # Try different separators
    company_name = identifier
    investment_desc = ''
    
    # Try " - " (with spaces)
    if ' - ' in identifier:
        parts = identifier.split(' - ', 1)
        company_name = parts[0].strip()
        investment_desc = parts[1].strip()
    # Try " -" (space dash, no space after)
    elif re.search(r'\s+-\s*[A-Z$]', identifier):
        match = re.search(r'\s+-\s*', identifier)
        if match:
            company_name = identifier[:match.start()].strip()
            investment_desc = identifier[match.end():].strip()
    # Try to find where company name ends (look for investment indicators)
    else:
        # Look for patterns that indicate start of investment description:
        # - "$" followed by numbers
        # - Investment type keywords
        # - Numbers followed by "Class", "Series", "shares", "Units"
        match = re.search(r'\s+-\s*|\s+\$\d|Term Note|Warrant|Preferred|Common|Units|Class [A-Z]|Series [A-Z]|\d+\s+(?:Class|Series|shares|Units)', identifier, re.IGNORECASE)
        if match:
            company_name = identifier[:match.start()].strip()
            investment_desc = identifier[match.start():].strip()
            # Clean up: remove leading dash if present
            investment_desc = re.sub(r'^\s*-\s*', '', investment_desc)
    
    # Clean company name: remove trailing numbers that are part of investment description
    # Pattern: "Company Name 1,234" -> "Company Name" (if followed by investment keywords)
    company_clean_match = re.match(r'^(.+?)\s+(\d+(?:,\d+)*)\s*$', company_name)
    if company_clean_match:
        base_name = company_clean_match.group(1)
        number_part = company_clean_match.group(2)
        # If the identifier contains investment keywords after this, the number is part of investment
        if investment_desc or any(kw in identifier.lower() for kw in ['class', 'series', 'shares', 'units', 'note', 'warrant']):
            company_name = base_name.strip()
            # Add the number back to investment_desc if it was separated
            if not investment_desc and number_part:
                investment_desc = f"{number_part} {identifier[len(company_name + ' ' + number_part):].strip()}"
    
    # Extract investment type from description
    investment_type = 'Unknown'
    
    # Common investment type patterns
    type_patterns = [
        (r'Term\s+Note', 'Term Note'),
        (r'Subordinated\s+Secured\s+Promissory\s+Note', 'Subordinated Debt'),
        (r'Amended\s+and\s+Restated\s+Term\s+Note', 'Term Note'),
        (r'Replacement\s+Term\s+Note', 'Term Note'),
        (r'Convertible\s+Note', 'Convertible Debt'),
        (r'Secured\s+Note', 'Term Note'),
        (r'Term\s+Loan', 'Term Loan'),
        (r'Revolver', 'Revolving Credit'),
        (r'Revolving\s+Credit', 'Revolving Credit'),
        (r'Preferred\s+Equity', 'Preferred Equity'),
        (r'Preferred\s+Stock', 'Preferred Equity'),
        (r'Preferred\s+Interest', 'Preferred Equity'),
        (r'Class\s+[A-Z][0-9]?\s+Preferred', 'Preferred Equity'),
        (r'Series\s+[A-Z][0-9]?\s+Preferred', 'Preferred Equity'),
        (r'Common\s+Equity', 'Common Equity'),
        (r'Common\s+Stock', 'Common Equity'),
        (r'Common\s+shares?', 'Common Equity'),
        (r'Class\s+[A-Z][0-9]?\s+Common', 'Common Equity'),
        (r'Membership\s+Interest', 'Common Equity'),
        (r'Class\s+[A-Z][0-9]?\s+Units?', 'Common Equity'),
        (r'Warrant', 'Warrant'),
        (r'Units?\s+of\s+', 'Common Equity'),
    ]
    
    for pattern, inv_type in type_patterns:
        if re.search(pattern, investment_desc, re.IGNORECASE):
            investment_type = inv_type
            break
    
    # If still unknown, try to infer from description
    if investment_type == 'Unknown' and investment_desc:
        if any(word in investment_desc.lower() for word in ['note', 'loan', 'debt']):
            investment_type = 'Term Note'
        elif any(word in investment_desc.lower() for word in ['preferred', 'series']):
            investment_type = 'Preferred Equity'
        elif any(word in investment_desc.lower() for word in ['common', 'units', 'shares']):
            investment_type = 'Common Equity'
        elif 'warrant' in investment_desc.lower():
            investment_type = 'Warrant'
    
    return {
        'company_name': company_name,
        'investment_type': investment_type
    }


def parse_json_facts(json_str: str) -> Dict:
    """Parse JSON facts string."""
    if not json_str or json_str == '{}':
        return {}
    try:
        return json.loads(json_str)
    except:
        return {}


def extract_value_from_json(facts_json: Dict, key: str) -> Optional[str]:
    """Extract value from JSON facts dictionary."""
    if not facts_json:
        return None
    
    # Try direct key match
    if key in facts_json:
        val = facts_json[key]
        if isinstance(val, dict):
            return val.get('value')
        return str(val)
    
    # Try case-insensitive match
    key_lower = key.lower()
    for k, v in facts_json.items():
        if k.lower() == key_lower:
            if isinstance(v, dict):
                return v.get('value')
            return str(v)
    
    return None


def format_percentage(value: Optional[str]) -> Optional[str]:
    """Format percentage value."""
    if not value:
        return None
    try:
        v = float(str(value).replace(',', ''))
        # If value is between 0 and 1, assume it's a decimal (0.12 -> 12%)
        if 0 < abs(v) <= 1.0:
            v *= 100.0
        return f"{v:.2f}%"
    except:
        return f"{value}%" if value else None


def parse_date(value: Optional[str]) -> Optional[str]:
    """Parse and normalize date."""
    if not value:
        return None
    # Try to parse various date formats
    date_patterns = [
        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
        r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY
    ]
    for pattern in date_patterns:
        match = re.search(pattern, str(value))
        if match:
            date_str = match.group(1)
            # Normalize to YYYY-MM-DD
            if '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 3:
                    month, day, year = parts
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            return date_str
    return str(value) if value else None


def process_rand_all_facts(input_file: Path, output_file: Path) -> Dict:
    """Process RAND_all_facts.csv and generate investments CSV."""
    logger.info(f"Processing {input_file}")
    
    investments_by_key = {}  # key -> investment dict
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            identifier = row.get('identifier', '') or row.get('company_name', '')
            if not identifier:
                continue
            
            # Parse identifier to get company name and investment type
            parsed = parse_rand_identifier(identifier)
            company_name = parsed['company_name']
            investment_type = parsed['investment_type']
            
            if company_name == 'Unknown':
                continue
            
            # Create a key for grouping: company + investment type
            # For debt: use company + type + principal (if available)
            # For equity: use company + type + shares/units description
            principal = row.get('principal_amount', '') or ''
            if principal:
                try:
                    principal_val = float(str(principal).replace(',', ''))
                    key = f"{company_name}|{investment_type}|{principal_val:.0f}"
                except:
                    key = f"{company_name}|{investment_type}|{identifier[:50]}"
            else:
                # For equity, use identifier to distinguish different investments
                key = f"{company_name}|{investment_type}|{identifier[:100]}"
            
            # Get or create investment record
            if key not in investments_by_key:
                investments_by_key[key] = {
                    'company_name': company_name,
                    'industry': row.get('industry', 'Unknown'),
                    'business_description': '',
                    'investment_type': investment_type,
                    'acquisition_date': None,
                    'maturity_date': None,
                    'principal_amount': None,
                    'cost': None,
                    'fair_value': None,
                    'interest_rate': None,
                    'reference_rate': None,
                    'spread': None,
                    'floor_rate': None,
                    'pik_rate': None,
                }
            
            inv = investments_by_key[key]
            
            # Parse JSON facts
            facts_json = parse_json_facts(row.get('all_facts_json', '{}'))
            
            # Extract and merge data (prefer non-empty values)
            
            # Principal amount
            if not inv['principal_amount']:
                principal_val = row.get('principal_amount', '') or extract_value_from_json(facts_json, 'us-gaap:InvestmentOwnedBalancePrincipalAmount')
                if principal_val:
                    try:
                        inv['principal_amount'] = int(float(str(principal_val).replace(',', '')))
                    except:
                        pass
            
            # Cost
            if not inv['cost']:
                cost_val = extract_value_from_json(facts_json, 'us-gaap:InvestmentOwnedAtCost')
                if cost_val:
                    try:
                        inv['cost'] = int(float(str(cost_val).replace(',', '')))
                    except:
                        pass
            
            # Fair value
            if not inv['fair_value']:
                fv_val = row.get('fair_value', '') or extract_value_from_json(facts_json, 'us-gaap:InvestmentOwnedAtFairValue')
                if fv_val:
                    try:
                        inv['fair_value'] = int(float(str(fv_val).replace(',', '')))
                    except:
                        pass
            
            # Maturity date
            if not inv['maturity_date']:
                mat_val = row.get('maturity_date', '') or extract_value_from_json(facts_json, 'us-gaap:InvestmentMaturityDate')
                if mat_val:
                    inv['maturity_date'] = parse_date(mat_val)
            
            # Acquisition date
            if not inv['acquisition_date']:
                acq_val = row.get('acquisition_date', '') or extract_value_from_json(facts_json, 'us-gaap:InvestmentAcquisitionDate')
                if acq_val:
                    inv['acquisition_date'] = parse_date(acq_val)
            
            # Interest rate
            if not inv['interest_rate']:
                rate_val = row.get('interest_rate', '') or extract_value_from_json(facts_json, 'us-gaap:InvestmentInterestRate')
                if rate_val:
                    inv['interest_rate'] = format_percentage(rate_val)
            
            # PIK rate
            if not inv['pik_rate']:
                pik_val = extract_value_from_json(facts_json, 'us-gaap:InvestmentInterestRatePaidInKind')
                if pik_val:
                    inv['pik_rate'] = format_percentage(pik_val)
            
            # Spread
            if not inv['spread']:
                spread_val = extract_value_from_json(facts_json, 'us-gaap:InvestmentBasisSpreadVariableRate')
                if spread_val:
                    inv['spread'] = format_percentage(spread_val)
            
            # Reference rate (from identifier or facts)
            if not inv['reference_rate']:
                # Check identifier for rate references
                identifier_lower = identifier.lower()
                if 'sofr' in identifier_lower:
                    inv['reference_rate'] = 'SOFR'
                elif 'prime' in identifier_lower:
                    inv['reference_rate'] = 'PRIME'
                elif 'libor' in identifier_lower:
                    inv['reference_rate'] = 'LIBOR'
    
    # Convert to list and apply standardization
    investments = []
    for inv in investments_by_key.values():
        # Apply standardization
        inv['investment_type'] = standardize_investment_type(inv['investment_type'])
        inv['industry'] = standardize_industry(inv['industry'])
        if inv['reference_rate']:
            inv['reference_rate'] = standardize_reference_rate(inv['reference_rate'])
        
        investments.append(inv)
    
    # Write to CSV
    os.makedirs(output_file.parent, exist_ok=True)
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
            'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate'
        ])
        writer.writeheader()
        for inv in investments:
            writer.writerow(inv)
    
    logger.info(f"Wrote {len(investments)} investments to {output_file}")
    
    return {
        'total_investments': len(investments),
        'output_file': str(output_file)
    }


def main():
    """Main entry point."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Get paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    input_file = project_root / 'output' / 'xbrl_all_facts' / 'RAND_all_facts.csv'
    output_file = project_root / 'output' / 'RAND_Rand_Capital_Corp_investments.csv'
    
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return
    
    result = process_rand_all_facts(input_file, output_file)
    print(f"Processed {result['total_investments']} investments")
    print(f"Output saved to: {result['output_file']}")


if __name__ == '__main__':
    main()

