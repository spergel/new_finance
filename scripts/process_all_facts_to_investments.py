"""
Process XBRL all_facts CSV files to create complete investment tables.

This script:
1. Filters to only the most recent "As_Of" context for each investment
2. Extracts all fields from the all_facts_json column
3. Creates final investment tables matching the structure of existing investment CSVs
"""

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime


def parse_context_date(context_ref: str) -> Optional[datetime]:
    """Extract date from context_ref like 'As_Of_9_30_2025' or 'As_Of_12_31_2024'."""
    # Match patterns like "As_Of_9_30_2025" or "As_Of_12_31_2024"
    match = re.search(r'As_Of_(\d+)_(\d+)_(\d+)', context_ref)
    if match:
        month, day, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            return None
    return None


def is_as_of_context(context_ref: str) -> bool:
    """Check if context is an 'As_Of' point-in-time context (not Duration)."""
    return context_ref.startswith('As_Of_')


def extract_value_from_json_fact(fact_dict: Dict, key: str) -> Optional[str]:
    """Extract value from a fact in the JSON structure."""
    if key in fact_dict:
        fact_data = fact_dict[key]
        if isinstance(fact_data, dict):
            return fact_data.get('value', '')
        return str(fact_data)
    return None


def parse_json_facts(all_facts_json: str) -> Dict:
    """Parse the all_facts_json string into a dictionary."""
    try:
        return json.loads(all_facts_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def parse_cgbd_company_name(company_name: str) -> Tuple[str, str]:
    """Parse CGBD company name format: 'Credit Fund,  Company Name, Industry' or 'Investment, Non-Affiliated Issuer,  Company Name, Industry'."""
    if not company_name:
        return '', 'Unknown'
    
    # Handle CGBD format: "Credit Fund,  ACR Group Borrower, LLC, Aerospace &amp; Defense"
    # or "Investment, Non-Affiliated Issuer,  AP Plastics Acquisition Holdings, LLC, Chemicals, Plastics &amp; Rubber"
    
    # Remove HTML entities
    company_name = company_name.replace('&amp;', '&')
    
    # Pattern: prefix, company name, industry (industry can have commas)
    # The identifier field has better structure: "Credit Fund, First Lien Debt, ACR Group Borrower, LLC, Aerospace & Defense"
    # So we know the pattern is: prefix, investment_type, company, industry
    
    # Try to match patterns
    # Pattern 1: "Credit Fund, First Lien Debt, Company, Industry" (from identifier field)
    # The identifier has investment type as separator, which makes parsing easier
    match = re.match(r'Credit Fund,\s+(?:First Lien Debt|Second Lien Debt|Unfunded Commitment),\s+(.+?),\s+(.+)$', company_name)
    if match:
        company = match.group(1).strip()
        industry = match.group(2).strip()
        # Remove trailing numbers from industry (e.g., "Aerospace & Defense 1" -> "Aerospace & Defense")
        industry = re.sub(r'\s+\d+$', '', industry)
        return company, industry
    
    # Pattern 1b: "Credit Fund,  Company, Industry" (without investment type)
    # Need to be smarter - find the last comma that separates company from industry
    # Company names typically end with LLC, Inc, Corp, LP, etc.
    match = re.match(r'Credit Fund,\s+(.+)$', company_name)
    if match:
        rest = match.group(1)
        # Split by comma and find where company name likely ends
        parts = [p.strip() for p in rest.split(',')]
        if len(parts) >= 2:
            # Look for company name ending pattern (LLC, Inc, Corp, LP, etc.)
            # Industry is everything after the company name
            # Try to find the split point - company name ends with suffix like LLC, Inc, etc.
            # Check each part to see if it's a company suffix
            for i in range(len(parts) - 1, 0, -1):
                # Check if parts[i] is a company suffix (LLC, Inc, Corp, LP, etc.)
                if re.match(r'^(LLC|Inc|Corp|LP|LLP|Ltd|Limited|Company|Holdings|Group)$', parts[i], re.IGNORECASE):
                    # Company name is everything up to and including the suffix (parts[0] to parts[i])
                    # Industry starts at parts[i+1]
                    company = ', '.join(parts[:i+1])
                    industry = ', '.join(parts[i+1:]) if i+1 < len(parts) else ''
                    industry = re.sub(r'\s+\d+$', '', industry)
                    return company, industry
                # Also check if parts[i-1] ends with a suffix word
                if re.search(r'\b(LLC|Inc|Corp|LP|LLP|Ltd|Limited|Company|Holdings|Group)\b$', parts[i-1], re.IGNORECASE):
                    # Company name includes the suffix (parts[0] to parts[i-1])
                    # Industry starts at parts[i]
                    company = ', '.join(parts[:i])
                    industry = ', '.join(parts[i:])
                    industry = re.sub(r'\s+\d+$', '', industry)
                    return company, industry
            # If no clear split, assume last part is industry
            company = ', '.join(parts[:-1])
            industry = parts[-1]
            industry = re.sub(r'\s+\d+$', '', industry)
            return company, industry
    
    # Pattern 2: "Investment, Non-Affiliated Issuer,  Company, Industry"
    # This is trickier because company and industry can both have commas
    # But looking at examples, the company usually ends with "LLC" or "Inc" or similar
    # and the industry is the last part after that
    match = re.match(r'Investment,\s+Non-Affiliated Issuer,\s+(.+)$', company_name)
    if match:
        rest = match.group(1)
        # Try to find where company name ends (usually at LLC, Inc, Corp, etc.)
        # and industry starts
        # Common pattern: "Company Name, LLC, Industry Name" or "Company Name, Industry Name"
        # Industry names are usually recognizable (Aerospace, Healthcare, Software, etc.)
        
        # Split by comma and work backwards
        parts = [p.strip() for p in rest.split(',')]
        if len(parts) >= 2:
            # Last part is likely industry, everything before is company
            # But we need to be smart - if last part is short or looks like industry
            industry = parts[-1]
            company = ', '.join(parts[:-1])
            
            # Remove trailing numbers from industry
            industry = re.sub(r'\s+\d+$', '', industry)
            return company, industry
    
    # If we can't parse it, return as-is
    return company_name, 'Unknown'


def extract_investment_fields(row: Dict, facts_json: Dict) -> Dict:
    """Extract all investment fields from row and JSON facts."""
    # Handle CGBD special format
    company_name_raw = row.get('company_name', '')
    industry_raw = row.get('industry', 'Unknown')
    identifier = row.get('identifier', '')
    
    # Check if this looks like CGBD format
    if 'Credit Fund,' in company_name_raw or ('Investment,' in company_name_raw and 'Non-Affiliated Issuer' in company_name_raw):
        # Try to use identifier field first (it has better structure)
        if identifier and ('Credit Fund,' in identifier or 'Investment,' in identifier):
            company_name, industry = parse_cgbd_company_name(identifier)
        else:
            company_name, industry = parse_cgbd_company_name(company_name_raw)
    else:
        company_name = company_name_raw
        industry = industry_raw if industry_raw != 'Unknown' else 'Unknown'
    
    inv = {
        'company_name': company_name,
        'industry': industry,
        'business_description': '',  # Usually not in XBRL
        'investment_type': row.get('investment_type', 'Unknown'),
        'acquisition_date': (row.get('acquisition_date', '') or 
                             extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentAcquisitionDate')),
        'maturity_date': (row.get('maturity_date', '') or 
                         extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentMaturityDate')),
        'principal_amount': (row.get('principal_amount', '') or 
                            extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentOwnedBalancePrincipalAmount')),
        'cost': (row.get('cost', '') or 
                extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentOwnedAtCost') or
                extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentOwnedAtAmortizedCost')),
        'fair_value': (row.get('fair_value', '') or 
                      extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentOwnedAtFairValue')),
        'interest_rate': (row.get('interest_rate', '') or 
                         extract_value_from_json_fact(facts_json, 'whfcl:InvestmentsInterestRate') or 
                         extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentInterestRate') or
                         extract_value_from_json_fact(facts_json, 'tpvg:InvestmentInterestRateEndOfTerm') or
                         extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentInterestRatePaidInKind')),
        'reference_rate': row.get('reference_rate', '') or _extract_reference_rate(facts_json),
        'spread': (row.get('spread', '') or 
                  extract_value_from_json_fact(facts_json, 'whfcl:InvestmentSpreadAboveIndex') or 
                  extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentSpread') or
                  extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentBasisSpreadVariableRate')),
        'floor_rate': (row.get('floor_rate', '') or 
                      extract_value_from_json_fact(facts_json, 'whfcl:InvestmentFloorRate') or 
                      extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentFloorRate') or
                      extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentInterestRateFloor')),
        'pik_rate': (row.get('pik_rate', '') or 
                    extract_value_from_json_fact(facts_json, 'whfcl:InvestmentPikInterestRate') or 
                    extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentPikInterestRate') or
                    extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentInterestRatePaidInKind')),
    }
    
    # Format percentages
    for field in ['interest_rate', 'spread', 'floor_rate', 'pik_rate']:
        if inv[field]:
            inv[field] = _format_percentage(inv[field])
    
    # Format numeric values (remove commas, convert to float then back to string)
    for field in ['principal_amount', 'cost', 'fair_value']:
        if inv[field]:
            try:
                val = float(str(inv[field]).replace(',', ''))
                inv[field] = f"{val:.0f}" if val == int(val) else f"{val:.2f}"
            except (ValueError, TypeError):
                pass
    
    return inv


def _extract_reference_rate(facts_json: Dict) -> Optional[str]:
    """Extract reference rate from various possible fields."""
    # Try different field names
    ref_rate = extract_value_from_json_fact(facts_json, 'us-gaap:InvestmentVariableInterestRateTypeExtensibleEnumeration')
    if ref_rate:
        # Extract readable name from URI
        if 'SOFR' in ref_rate or 'Sofr' in ref_rate:
            return 'SOFR'
        elif 'PRIME' in ref_rate or 'Prime' in ref_rate:
            return 'PRIME'
        elif 'LIBOR' in ref_rate or 'Libor' in ref_rate:
            return 'LIBOR'
        # Return the last part of the URI if it's a URI
        if '#' in ref_rate:
            return ref_rate.split('#')[-1].replace('Member', '')
    return None


def _format_percentage(value: str) -> str:
    """Format percentage value to standard format like '9.5%'."""
    try:
        # Remove commas and convert to float
        val = float(str(value).replace(',', '').replace('%', ''))
        # If value is less than 1, it's likely a decimal (0.095 = 9.5%)
        if 0 < val < 1:
            val = val * 100
        return f"{val:.2f}%"
    except (ValueError, TypeError):
        return str(value)


def get_investment_key(row: Dict) -> str:
    """Create a unique key for an investment (company_name + investment_type)."""
    company = row.get('company_name', '').strip()
    inv_type = row.get('investment_type', '').strip()
    identifier = row.get('identifier', '').strip()
    
    # Use identifier if available, otherwise combine company and type
    if identifier:
        return identifier
    return f"{company}|{inv_type}"


def process_all_facts_file(input_file: Path, output_file: Path):
    """Process a single all_facts CSV file to create investment table."""
    print(f"Processing {input_file.name}...")
    
    # Read all rows
    rows = []
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    
    if not rows:
        print(f"  No data found in {input_file.name}")
        return []
    
    # Group by investment key and find most recent As_Of context for each
    investments_by_key: Dict[str, List[Tuple[Optional[datetime], Dict]]] = defaultdict(list)
    has_date_contexts = False
    
    for row in rows:
        context_ref = row.get('context_ref', '')
        
        # Check if this file uses date-based contexts
        if is_as_of_context(context_ref):
            has_date_contexts = True
            # Parse date
            date = parse_context_date(context_ref)
            if not date:
                continue
        else:
            # For non-date contexts, use None as date (we'll take all unique investments)
            date = None
        
        # Create investment key
        key = get_investment_key(row)
        
        # Store with date
        investments_by_key[key].append((date, row))
    
    # For each investment, get the most recent row with substantial data
    latest_investments = []
    for key, dated_rows in investments_by_key.items():
        if has_date_contexts:
            # Sort by date (most recent first), filtering out None dates
            dated_rows_with_dates = [(d, r) for d, r in dated_rows if d is not None]
            if dated_rows_with_dates:
                dated_rows_with_dates.sort(key=lambda x: x[0], reverse=True)
                
                # Find the most recent context with substantial data
                # "Substantial" means fact_count > 2 or has financial data (principal_amount, cost, fair_value)
                best_row = None
                best_date = None
                
                for date, row in dated_rows_with_dates:
                    fact_count = int(row.get('fact_count', 0))
                    has_financial_data = bool(
                        row.get('principal_amount') or 
                        row.get('cost') or 
                        row.get('fair_value') or
                        row.get('maturity_date') or
                        row.get('interest_rate')
                    )
                    
                    # If this is the first row (most recent) or has substantial data, use it
                    if best_row is None:
                        best_row = row
                        best_date = date
                        # If the most recent has substantial data, use it
                        if fact_count > 2 or has_financial_data:
                            break
                    else:
                        # If we found a row with substantial data, use it
                        if fact_count > 2 or has_financial_data:
                            best_row = row
                            best_date = date
                            break
                
                if best_row:
                    # Try to merge data from other contexts if best_row is missing fields
                    # Check if we need to fill gaps from older contexts
                    if not (best_row.get('principal_amount') or best_row.get('cost') or best_row.get('fair_value')):
                        # Look for older contexts with financial data
                        for date, row in dated_rows_with_dates:
                            if row.get('principal_amount') or row.get('cost') or row.get('fair_value'):
                                # Merge: use best_row as base, fill in missing fields from row
                                if not best_row.get('principal_amount') and row.get('principal_amount'):
                                    best_row['principal_amount'] = row['principal_amount']
                                if not best_row.get('cost') and row.get('cost'):
                                    best_row['cost'] = row['cost']
                                if not best_row.get('fair_value') and row.get('fair_value'):
                                    best_row['fair_value'] = row['fair_value']
                                if not best_row.get('maturity_date') and row.get('maturity_date'):
                                    best_row['maturity_date'] = row['maturity_date']
                                if not best_row.get('interest_rate') and row.get('interest_rate'):
                                    best_row['interest_rate'] = row['interest_rate']
                                if not best_row.get('spread') and row.get('spread'):
                                    best_row['spread'] = row['spread']
                                # Also merge JSON facts if best_row has minimal facts
                                if int(best_row.get('fact_count', 0)) < 5:
                                    best_facts = parse_json_facts(best_row.get('all_facts_json', '{}'))
                                    other_facts = parse_json_facts(row.get('all_facts_json', '{}'))
                                    # Merge facts (best_row takes precedence)
                                    merged_facts = {**other_facts, **best_facts}
                                    best_row['all_facts_json'] = json.dumps(merged_facts)
                                    best_row['fact_count'] = str(len(merged_facts))
                                break
                    
                    latest_investments.append((best_date, best_row))
        else:
            # No dates - just take the first occurrence (assuming all are current)
            if dated_rows:
                latest_investments.append((None, dated_rows[0][1]))
    
    print(f"  Found {len(latest_investments)} unique investments (most recent context)")
    
    # Extract fields and build investment records
    investments = []
    for date, row in latest_investments:
        # Parse JSON facts
        facts_json_str = row.get('all_facts_json', '{}')
        facts_json = parse_json_facts(facts_json_str)
        
        # Extract all fields
        inv = extract_investment_fields(row, facts_json)
        investments.append(inv)
    
    # Sort by company name
    investments.sort(key=lambda x: x['company_name'])
    
    # Write output
    fieldnames = [
        'company_name', 'industry', 'business_description', 'investment_type',
        'acquisition_date', 'maturity_date', 'principal_amount', 'cost',
        'fair_value', 'interest_rate', 'reference_rate', 'spread',
        'floor_rate', 'pik_rate'
    ]
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(investments)
    
    print(f"  Wrote {len(investments)} investments to {output_file.name}")
    
    return investments
    
    return investments


def validate_investment_data(investments: List[Dict]) -> Dict:
    """Validate investment data and return quality metrics."""
    total = len(investments)
    if total == 0:
        return {'total': 0, 'coverage': {}}
    
    # Count investments with each field populated
    field_counts = {
        'company_name': sum(1 for inv in investments if inv.get('company_name')),
        'investment_type': sum(1 for inv in investments if inv.get('investment_type') and inv.get('investment_type') != 'Unknown'),
        'principal_amount': sum(1 for inv in investments if inv.get('principal_amount')),
        'cost': sum(1 for inv in investments if inv.get('cost')),
        'fair_value': sum(1 for inv in investments if inv.get('fair_value')),
        'maturity_date': sum(1 for inv in investments if inv.get('maturity_date')),
        'interest_rate': sum(1 for inv in investments if inv.get('interest_rate')),
        'reference_rate': sum(1 for inv in investments if inv.get('reference_rate')),
        'spread': sum(1 for inv in investments if inv.get('spread')),
    }
    
    # Calculate coverage percentages
    coverage = {field: (count / total * 100) for field, count in field_counts.items()}
    
    return {
        'total': total,
        'field_counts': field_counts,
        'coverage': coverage
    }


def main():
    """Process all all_facts CSV files."""
    input_dir = Path('output/xbrl_all_facts')
    output_dir = Path('output')
    
    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return
    
    # Find all all_facts CSV files
    all_facts_files = list(input_dir.glob('*_all_facts.csv'))
    
    if not all_facts_files:
        print(f"No all_facts CSV files found in {input_dir}")
        return
    
    # Tickers to skip (will be handled by custom scrapers)
    skip_tickers = {
        'ARCC', 'BCSF', 'CSWC', 'FSK', 'GBDC', 'GLAD', 'MAIN', 'MSIF', 
        'NCDL', 'NMFC', 'OBDC', 'OCSL', 'OFS', 'OXSQ', 'PFX', 'PSEC', 'SSSS'
    }
    
    # Filter out skipped tickers
    files_to_process = []
    skipped_count = 0
    for input_file in sorted(all_facts_files):
        ticker = input_file.stem.replace('_all_facts', '').upper()
        if ticker in skip_tickers:
            skipped_count += 1
            continue
        files_to_process.append(input_file)
    
    print(f"Found {len(all_facts_files)} all_facts files")
    print(f"Skipping {skipped_count} tickers (will use custom scrapers): {', '.join(sorted(skip_tickers))}")
    print(f"Processing {len(files_to_process)} files\n")
    
    # Track results for summary
    results = []
    
    for input_file in files_to_process:
        # Extract ticker from filename (e.g., WHF_all_facts.csv -> WHF)
        ticker = input_file.stem.replace('_all_facts', '').upper()
        
        # Determine output filename
        # Try to find existing investment file to match naming
        existing_files = list(output_dir.glob(f'{ticker}_*_investments.csv'))
        if existing_files:
            # Use existing filename pattern
            output_file = existing_files[0]
            print(f"Using existing output file: {output_file.name}")
        else:
            # Create new filename
            output_file = output_dir / f'{ticker}_investments.csv'
        
        try:
            # Process file and get investments
            investments = process_all_facts_file(input_file, output_file)
            
            # Validate data quality
            validation = validate_investment_data(investments)
            results.append({
                'ticker': ticker,
                'file': input_file.name,
                'validation': validation
            })
            
            # Print quick summary
            if validation['total'] > 0:
                print(f"  Data quality: {validation['coverage'].get('principal_amount', 0):.1f}% principal, "
                      f"{validation['coverage'].get('cost', 0):.1f}% cost, "
                      f"{validation['coverage'].get('fair_value', 0):.1f}% fair_value, "
                      f"{validation['coverage'].get('maturity_date', 0):.1f}% maturity_date")
            
        except Exception as e:
            print(f"  ERROR processing {input_file.name}: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'ticker': ticker,
                'file': input_file.name,
                'error': str(e)
            })
        
        print()
    
    # Print summary report
    print("\n" + "="*80)
    print("SUMMARY REPORT")
    print("="*80)
    print(f"{'Ticker':<8} {'Total':<8} {'Principal':<10} {'Cost':<10} {'Fair Val':<10} {'Maturity':<10} {'Int Rate':<10}")
    print("-"*80)
    
    for result in sorted(results, key=lambda x: x['ticker']):
        if 'error' in result:
            print(f"{result['ticker']:<8} ERROR: {result['error']}")
        elif result['validation']['total'] > 0:
            v = result['validation']
            print(f"{result['ticker']:<8} {v['total']:<8} "
                  f"{v['coverage'].get('principal_amount', 0):>6.1f}%  "
                  f"{v['coverage'].get('cost', 0):>6.1f}%  "
                  f"{v['coverage'].get('fair_value', 0):>6.1f}%  "
                  f"{v['coverage'].get('maturity_date', 0):>6.1f}%  "
                  f"{v['coverage'].get('interest_rate', 0):>6.1f}%")
        else:
            print(f"{result['ticker']:<8} 0 investments")
    
    print("="*80)


if __name__ == '__main__':
    main()
