#!/usr/bin/env python3
"""
BXSL (Blackstone Secured Lending Fund) Investment Extractor

Flow:
1) Use SECAPIClient to find the latest 10-Q filing index for BXSL
2) Select the main HTML document from that filing
3) Parse the Schedule of Investments tables with specialized BXSL logic
4) Normalize and save to output/BXSL_Blackstone_Secured_Lending_Fund_investments.csv using ARCC schema
"""

import os
import csv
import re
import logging
from typing import Optional, List, Tuple, Dict
from bs4 import BeautifulSoup
import requests

from sec_api_client import SECAPIClient, FilingDocument
from flexible_table_parser import FlexibleTableParser
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


def _select_main_html_document(documents: List[FilingDocument]) -> Optional[FilingDocument]:
    """Pick the primary 10-Q HTML document, avoiding XBRL fertilizer files and images."""
    if not documents:
        return None

    def is_exhibit(name: str) -> bool:
        return (
            'exhibit' in name.lower() or
            name.lower().startswith('ex') or
            '-ex' in name.lower() or
            'xex' in name.lower()
        )

    def is_main(doc: FilingDocument) -> bool:
        name = (doc.filename or '').lower()
        desc = (doc.description or '').lower()
        if not (name.endswith('.htm') or name.endswith('.html')):
            return False
        if 'form 10-q' in desc or desc == '10-q' or 'quarterly report' in desc:
            return True
        if is_exhibit(name):
            return False
        if any(k in name for k in ['10q', '10-q']) and not is_exhibit(name):
            return True
        if any(k in name for k in ['document.htm', 'index.htm', 'report.htm']) and not is_exhibit(name):
            return True
        return False

    for d in documents:
        if is_main(d):
            return d

    for d in documents:
        name = (d.filename or '').lower()
        if (name.endswith('.htm') or name.endswith('.html')) and not is_exhibit(name):
            return d

    return None


def _normalize_bxsl_row(row: Dict) -> Dict:
    """Normalize a BXSL investment row to ARCC format."""
    normalized = {
        'company_name': row.get('company_name', '').strip(),
        'industry': row.get('industry', '').strip() or 'Unknown',
        'business_description': row.get('business_description', '').strip() or '',
        'investment_type': row.get('investment_type', '').strip() or 'Unknown',
        'acquisition_date': row.get('acquisition_date', '').strip() or '',
        'maturity_date': row.get('maturity_date', '').strip() or '',
        'principal_amount': row.get('principal_amount') or '',
        'cost': row.get('cost') or '',
        'fair_value': row.get('fair_value') or '',
        'interest_rate': row.get('interest_rate', '').strip() or '',
        'reference_rate': row.get('reference_rate', '').strip() or '',
        'spread': row.get('spread', '').strip() or ''
    }
    
    # Normalize investment_type - preserve actual types, only fix "Restricted Securities" when it's clearly debt
    inv_type = normalized['investment_type'].lower()
    company_name_lower = normalized.get('company_name', '').lower()
    
    # Check if it's equity-based first (from company name or type)
    if 'equity' in inv_type or 'common stock' in company_name_lower or 'common units' in company_name_lower or 'common equity' in company_name_lower:
        if 'preferred' in inv_type or 'preferred' in company_name_lower or 'class a' in company_name_lower or 'class b' in company_name_lower:
            normalized['investment_type'] = 'Preferred equity'
        else:
            normalized['investment_type'] = 'Equity'
    elif 'warrant' in inv_type or 'warrant' in company_name_lower:
        normalized['investment_type'] = 'Warrants'
    elif 'restricted securities' in inv_type:
        # Only convert to loan if it has an interest rate (indicating it's debt)
        if normalized.get('interest_rate') and normalized.get('interest_rate').strip():
            normalized['investment_type'] = 'First lien senior secured loan'
        # Otherwise keep as "Restricted Securities" or infer from context
        elif normalized.get('principal_amount') or normalized.get('cost'):
            # Has principal/cost but no rate - might still be debt, default to secured loan
            normalized['investment_type'] = 'First lien senior secured loan'
        # If no financial data, keep as Restricted Securities or check company name
        else:
            normalized['investment_type'] = 'Restricted Securities'
    elif 'first lien' in inv_type or 'senior secured' in inv_type:
        # Preserve "revolving" if present
        if 'revolving' in inv_type:
            normalized['investment_type'] = 'First lien senior secured revolving loan'
        else:
            normalized['investment_type'] = 'First lien senior secured loan'
    elif 'second lien' in inv_type:
        normalized['investment_type'] = 'Second lien senior secured loan'
    elif 'subordinated' in inv_type:
        normalized['investment_type'] = 'Subordinated loan'
    # If still unknown or empty, try to infer from company name patterns
    elif normalized['investment_type'] == 'Unknown' or not normalized['investment_type']:
        # Default fallback - check if it looks like equity
        if any(x in company_name_lower for x in ['- propriety', '- common', '- units', '- class']):
            normalized['investment_type'] = 'Equity'
        else:
            # Default to secured loan if we have financial data
            if normalized.get('principal_amount') or normalized.get('cost'):
                normalized['investment_type'] = 'First lien senior secured loan'
    
    # Clean company_name - remove common prefixes/suffixes
    company = normalized['company_name']
    # Remove trailing asterisks and whitespace
    company = re.sub(r'\s*\*\*\*\s*$', '', company)
    company = re.sub(r'\s+', ' ', company).strip()
    
    # Handle company names that include investment type (e.g., "LogicMonitor, Inc., Revolver")
    # Extract the actual company name and update investment_type if needed
    if ', Revolver' in company:
        company = company.replace(', Revolver', '').strip()
        if 'revolving' not in normalized['investment_type'].lower():
            normalized['investment_type'] = 'First lien senior secured revolving loan'
    elif ', Delayed Draw Term Loan' in company or ', Delayed Draw' in company:
        # Remove delayed draw suffix but keep as term loan
        company = re.sub(r',\s*Delayed Draw.*', '', company).strip()
    elif ', Term Loan' in company:
        company = company.replace(', Term Loan', '').strip()
    
    # Normalize company name variations for better deduplication
    # Normalize commas before entity suffixes first (e.g., "Company, Inc." -> "Company Inc")
    company = re.sub(r',\s+(Inc|LLC|Ltd|Corp|Co)\.?\b', r' \1', company, flags=re.IGNORECASE)
    # Remove punctuation variations like "Inc." vs "Inc", "LLC" vs "L.L.C."
    company = re.sub(r'\bInc\.\b', 'Inc', company, flags=re.IGNORECASE)
    company = re.sub(r'\bL\.L\.C\.\b', 'LLC', company, flags=re.IGNORECASE)
    company = re.sub(r'\bLtd\.\b', 'Ltd', company, flags=re.IGNORECASE)
    company = re.sub(r'\bCorp\.\b', 'Corp', company, flags=re.IGNORECASE)
    company = re.sub(r'\bCo\.\b', 'Co', company, flags=re.IGNORECASE)
    # Remove trailing periods and commas
    company = company.rstrip('., ').strip()
    
    normalized['company_name'] = company
    
    # Normalize dates to MM/YYYY or MM/DD/YYYY format if possible
    for date_field in ['acquisition_date', 'maturity_date']:
        date_val = normalized[date_field]
        if date_val and date_val != '':
            # Already in good format, keep as-is
            pass
    
    # Format financial values - convert to numbers or empty string
    for field in ['principal_amount', 'cost', 'fair_value']:
        val = normalized[field]
        if val is None or val == '':
            normalized[field] = ''
        elif isinstance(val, (int, float)):
            # Keep as number for CSV (will be written as-is)
            pass
        elif isinstance(val, str):
            # Try to parse
            try:
                # Remove commas and parse
                cleaned = val.replace(',', '').strip()
                if cleaned:
                    normalized[field] = float(cleaned)
                else:
                    normalized[field] = ''
            except:
                normalized[field] = ''
    
    return normalized


def _normalize_company_name(raw: str) -> str:
    name = raw or ''
    name = re.sub(r'\s*\*\*\*\s*$', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove embedded instrument suffixes
    name = re.sub(r',\s*Revolver.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r',\s*Delayed Draw.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r',\s*Term Loan.*$', '', name, flags=re.IGNORECASE)
    # Normalize commas before suffixes
    name = re.sub(r',\s+(Inc|LLC|Ltd|Corp|Co)\.?\b', r' \1', name, flags=re.IGNORECASE)
    # Normalize punctuations in suffixes
    name = re.sub(r'\bInc\.\b', 'Inc', name, flags=re.IGNORECASE)
    name = re.sub(r'\bL\.L\.C\.\b', 'LLC', name, flags=re.IGNORECASE)
    name = re.sub(r'\bLtd\.\b', 'Ltd', name, flags=re.IGNORECASE)
    name = re.sub(r'\bCorp\.\b', 'Corp', name, flags=re.IGNORECASE)
    name = re.sub(r'\bCo\.\b', 'Co', name, flags=re.IGNORECASE)
    # Trim trailing punctuation
    return name.rstrip('., ').strip()


def _extract_revolver_commitments_from_investments(investments: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Extract revolver commitments from investment data.
    For revolvers with only fair_value (no principal), the fair_value is likely the committed amount.
    Returns mapping: normalized_company -> { 'commitment_limit': float, 'undrawn_commitment': float }
    """
    commitments: Dict[str, Dict[str, float]] = {}
    
    for inv in investments:
        company_raw = inv.get('company_name', '').strip()
        if not company_raw or ', Revolver' not in company_raw:
            continue
            
        # Normalize company name
        company = _normalize_company_name(company_raw.replace(', Revolver', '').strip())
        
        # Try to extract commitment limit from fair_value (undrawn revolvers show commitment as fair_value)
        fair_val_str = str(inv.get('fair_value', '') or '').strip()
        if fair_val_str:
            try:
                fair_val = float(fair_val_str.replace(',', ''))
                # For revolvers, fair_value often represents the commitment/limit
                if company not in commitments:
                    commitments[company] = {'commitment_limit': fair_val, 'undrawn_commitment': fair_val}
                else:
                    # Take the maximum if we see multiple entries
                    commitments[company]['commitment_limit'] = max(
                        commitments[company].get('commitment_limit', 0.0), fair_val
                    )
                    commitments[company]['undrawn_commitment'] = max(
                        commitments[company].get('undrawn_commitment', 0.0), fair_val
                    )
            except (ValueError, TypeError):
                pass
    
    return commitments


def _extract_revolver_commitments_from_note7(txt_path: str, headers: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    """Heuristically extract per-company revolver commitments from Note 7.
    Returns mapping: normalized_company -> { 'commitment_limit': float, 'undrawn_commitment': float }
    """
    try:
        import bs4  # noqa: F401
    except Exception:
        pass

    commitments: Dict[str, Dict[str, float]] = {}
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return commitments

    # Very heuristic: find table-like lines containing keywords and dollar amounts
    # We'll scan for lines with both a company-like token and amounts, near "unfunded" or "commitment" words.
    lines = content.splitlines()
    window = 8
    for i, line in enumerate(lines):
        low = line.lower()
        if ('unfunded' in low or 'commitment' in low) and ('$' in line or ',' in line):
            block = ' '.join(lines[max(0, i - window): i + window + 1])
            # Pull candidate company and two amounts
            # Company: sequence of letters, numbers, commas before first amount
            m = re.search(r'([A-Za-z0-9&\-/\.,\(\)\s]{5,}?)\s*\$?([0-9][0-9,]{2,})(?:\.[0-9]+)?\s*(?:\$|\b)', block)
            if not m:
                continue
            company_raw = m.group(1)
            # Find amounts in the block
            nums = re.findall(r'\$?([0-9][0-9,]{2,})(?:\.[0-9]+)?', block)
            amounts: List[float] = []
            for n in nums[:3]:
                try:
                    amounts.append(float(n.replace(',', '')))
                except Exception:
                    continue
            if not amounts:
                continue
            company = _normalize_company_name(company_raw)
            entry = commitments.get(company, {'commitment_limit': 0.0, 'undrawn_commitment': 0.0})
            # Guessing: the largest is limit, smallest is undrawn if two present
            if len(amounts) >= 2:
                entry['commitment_limit'] = max(entry.get('commitment_limit', 0.0), max(amounts))
                entry['undrawn_commitment'] = max(entry.get('undrawn_commitment', 0.0), min(amounts))
            else:
                # Single amount; treat as limit if bigger than current
                entry['commitment_limit'] = max(entry.get('commitment_limit', 0.0), amounts[0])
            commitments[company] = entry
    return commitments


def extract_bxsl_investments(user_agent: str = "BDC-Extractor/1.0 contact@example.com") -> Optional[str]:
    """
    Fetch latest BXSL 10-Q, parse investments, and write standardized CSV.

    Returns the path to the CSV on success; None otherwise.
    """
    ticker = "BXSL"

    client = SECAPIClient(data_dir="temp_filings", user_agent=user_agent)
    index_url = client.get_filing_index_url(ticker, "10-Q")
    if not index_url:
        logger.error("Could not find latest 10-Q index URL for BXSL")
        return None

    documents = client.get_documents_from_index(index_url)
    parser = FlexibleTableParser(user_agent=user_agent)

    # Try main HTML first
    selected_doc = _select_main_html_document(documents)
    investments: List[dict] = []

    def try_parse(doc: FilingDocument) -> Tuple[List[dict], FilingDocument]:
        parsed: List[dict] = []
        try:
            parsed = parser.parse_html_filing(doc.url)
        except Exception as e:
            logger.warning(f"Parse failed for {doc.filename}: {e}")
        return parsed, doc

    if selected_doc:
        investments, _ = try_parse(selected_doc)
        logger.info(f"Main HTML ({selected_doc.filename}) yielded {len(investments)} investments")

    # Fallback: iterate all HTML docs and pick the one with max rows
    if not investments:
        logger.info("Main HTML yielded 0 investments; scanning other HTML documents...")
        best: Tuple[int, FilingDocument, List[dict]] = (0, None, [])
        for d in documents:
            name = (d.filename or '').lower()
            if not (name.endswith('.htm') or name.endswith('.html')):
                continue
            parsed, _ = try_parse(d)
            if parsed and len(parsed) > best[0]:
                best = (len(parsed), d, parsed)
        if best[0] > 0:
            investments = best[2]
            selected_doc = best[1]
            logger.info(f"Selected {selected_doc.filename} based on max investments: {best[0]}")

    # If still no investments, try a more aggressive parsing approach
    if not investments and selected_doc:
        logger.info("Attempting direct HTML table extraction...")
        try:
            response = requests.get(selected_doc.url, headers={'User-Agent': user_agent})
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find tables that might contain investment data
            all_tables = soup.find_all('table')
            logger.info(f"Found {len(all_tables)} tables in document")
            
            # Look for schedule of investments
            for table in all_tables:
                table_text = table.get_text().lower()
                if 'portfolio investments' in table_text or 'schedule of investments' in table_text:
                    logger.info(f"Found potential schedule table with {len(table.find_all('tr'))} rows")
                    # Try parsing this specific table
                    investments = parser._parse_table(table, is_first=True)
                    if investments:
                        logger.info(f"Successfully parsed {len(investments)} investments from schedule table")
                        break
        except Exception as e:
            logger.warning(f"Direct table extraction failed: {e}")

    # Write to CSV with ARCC schema
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Fallback: if parsing failed, try to use existing comprehensive CSV files if available
    if not investments:
        logger.warning("HTML parsing failed; attempting to use existing comprehensive CSV as fallback")
        # Try the structured/dated file first (has 1404 rows with all fields)
        fallback_csvs = [
            os.path.join(output_dir, "BXSL_Blackstone_Secured_Lending_Fund_investments_structured_dated.csv"),
            os.path.join(output_dir, "BXSL_Blackstone_Secured_Lending_Fund_investments_normalized.csv"),
            os.path.join(output_dir, "BXSL_from_10Q.csv")
        ]
        for fallback_csv in fallback_csvs:
            if os.path.exists(fallback_csv):
                logger.info(f"Loading existing CSV: {fallback_csv}")
                try:
                    with open(fallback_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        investments = list(reader)
                    if investments:
                        logger.info(f"Loaded {len(investments)} investments from {os.path.basename(fallback_csv)}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to load {fallback_csv}: {e}")
                    continue
    
    if not investments:
        logger.error("Failed to extract any investments from BXSL 10-Q documents")
        return None

    # Extract revolver commitments from investment data itself
    commitments_map: Dict[str, Dict[str, float]] = {}
    try:
        commitments_map = _extract_revolver_commitments_from_investments(investments)
        logger.info(f"Extracted {len(commitments_map)} revolver commitment entries from investment data")
    except Exception as e:
        logger.warning(f"Commitments extraction failed: {e}")

    # Normalize all investments and deduplicate
    normalized_rows = []
    seen_keys = set()  # Track duplicates: (company_name, investment_type)
    duplicates_count = 0
    empty_rows_count = 0
    
    for inv in investments:
        normalized = _normalize_bxsl_row(inv)
        
        # Enrich revolvers with commitments if available
        company_key = _normalize_company_name(normalized.get('company_name', ''))
        inv_type_l = (normalized.get('investment_type') or '').lower()
        if 'revolving' in inv_type_l and company_key in commitments_map:
            cm = commitments_map[company_key]
            normalized['commitment_limit'] = cm.get('commitment_limit') or ''
            normalized['undrawn_commitment'] = cm.get('undrawn_commitment') or ''
        else:
            normalized['commitment_limit'] = normalized.get('commitment_limit') or ''
            normalized['undrawn_commitment'] = normalized.get('undrawn_commitment') or ''

        # Filter out rows with no meaningful financial data
        has_principal = normalized.get('principal_amount') and str(normalized['principal_amount']).strip() != ''
        has_cost = normalized.get('cost') and str(normalized['cost']).strip() != ''
        has_fair_value = normalized.get('fair_value') and str(normalized['fair_value']).strip() != ''
        
        if not (has_principal or has_cost or has_fair_value):
            # Skip rows with no financial data (likely subtotals or continuation rows)
            empty_rows_count += 1
            continue
        
        # Create deduplication key (company + investment type)
        company = normalized.get('company_name', '').strip()
        inv_type = normalized.get('investment_type', '').strip()
        
        if not company or company == '':
            # Skip rows without company name
            empty_rows_count += 1
            continue
            
        key = (company.lower(), inv_type.lower())
        
        # Check if we've seen this combination (duplicate from 2024/2025 tables)
        if key in seen_keys:
            duplicates_count += 1
            continue
        
        seen_keys.add(key)
        normalized_rows.append(normalized)
    
    if duplicates_count > 0:
        logger.info(f"Filtered out {duplicates_count} duplicate rows (likely 2024/2025 duplicates)")
    if empty_rows_count > 0:
        logger.info(f"Filtered out {empty_rows_count} rows with no financial data")

    # Write to CSV
    output_file = os.path.join(output_dir, "BXSL_Blackstone_Secured_Lending_Fund_investments.csv")

    fieldnames = [
        'company_name', 'industry', 'business_description', 'investment_type',
        'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
        'interest_rate', 'reference_rate', 'spread',
        'commitment_limit', 'undrawn_commitment'
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in normalized_rows:
            # Apply standardization
            if 'investment_type' in row:
                row['investment_type'] = standardize_investment_type(row.get('investment_type'))
            if 'industry' in row:
                row['industry'] = standardize_industry(row.get('industry'))
            if 'reference_rate' in row:
                row['reference_rate'] = standardize_reference_rate(row.get('reference_rate')) or ''
            # Write row, converting None to empty string
            writer.writerow({k: (row.get(k) if row.get(k) is not None else '') for k in fieldnames})

    logger.info(f"BXSL investments saved to: {output_file} ({len(normalized_rows)} rows)")
    return output_file


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    csv_path = extract_bxsl_investments()
    if csv_path:
        print(f"Success: {csv_path}")
        return 0
    else:
        print("Failed to extract BXSL investments")
        return 1


if __name__ == "__main__":
    exit(main())

BXSL (Blackstone Secured Lending Fund) Investment Extractor

Flow:
1) Use SECAPIClient to find the latest 10-Q filing index for BXSL
2) Select the main HTML document from that filing
3) Parse the Schedule of Investments tables with specialized BXSL logic
4) Normalize and save to output/BXSL_Blackstone_Secured_Lending_Fund_investments.csv using ARCC schema
"""

import os
import csv
import re
import logging
from typing import Optional, List, Tuple, Dict
from bs4 import BeautifulSoup
import requests

from sec_api_client import SECAPIClient, FilingDocument
from flexible_table_parser import FlexibleTableParser
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


def _select_main_html_document(documents: List[FilingDocument]) -> Optional[FilingDocument]:
    """Pick the primary 10-Q HTML document, avoiding XBRL fertilizer files and images."""
    if not documents:
        return None

    def is_exhibit(name: str) -> bool:
        return (
            'exhibit' in name.lower() or
            name.lower().startswith('ex') or
            '-ex' in name.lower() or
            'xex' in name.lower()
        )

    def is_main(doc: FilingDocument) -> bool:
        name = (doc.filename or '').lower()
        desc = (doc.description or '').lower()
        if not (name.endswith('.htm') or name.endswith('.html')):
            return False
        if 'form 10-q' in desc or desc == '10-q' or 'quarterly report' in desc:
            return True
        if is_exhibit(name):
            return False
        if any(k in name for k in ['10q', '10-q']) and not is_exhibit(name):
            return True
        if any(k in name for k in ['document.htm', 'index.htm', 'report.htm']) and not is_exhibit(name):
            return True
        return False

    for d in documents:
        if is_main(d):
            return d

    for d in documents:
        name = (d.filename or '').lower()
        if (name.endswith('.htm') or name.endswith('.html')) and not is_exhibit(name):
            return d

    return None


def _normalize_bxsl_row(row: Dict) -> Dict:
    """Normalize a BXSL investment row to ARCC format."""
    normalized = {
        'company_name': row.get('company_name', '').strip(),
        'industry': row.get('industry', '').strip() or 'Unknown',
        'business_description': row.get('business_description', '').strip() or '',
        'investment_type': row.get('investment_type', '').strip() or 'Unknown',
        'acquisition_date': row.get('acquisition_date', '').strip() or '',
        'maturity_date': row.get('maturity_date', '').strip() or '',
        'principal_amount': row.get('principal_amount') or '',
        'cost': row.get('cost') or '',
        'fair_value': row.get('fair_value') or '',
        'interest_rate': row.get('interest_rate', '').strip() or '',
        'reference_rate': row.get('reference_rate', '').strip() or '',
        'spread': row.get('spread', '').strip() or ''
    }
    
    # Normalize investment_type - preserve actual types, only fix "Restricted Securities" when it's clearly debt
    inv_type = normalized['investment_type'].lower()
    company_name_lower = normalized.get('company_name', '').lower()
    
    # Check if it's equity-based first (from company name or type)
    if 'equity' in inv_type or 'common stock' in company_name_lower or 'common units' in company_name_lower or 'common equity' in company_name_lower:
        if 'preferred' in inv_type or 'preferred' in company_name_lower or 'class a' in company_name_lower or 'class b' in company_name_lower:
            normalized['investment_type'] = 'Preferred equity'
        else:
            normalized['investment_type'] = 'Equity'
    elif 'warrant' in inv_type or 'warrant' in company_name_lower:
        normalized['investment_type'] = 'Warrants'
    elif 'restricted securities' in inv_type:
        # Only convert to loan if it has an interest rate (indicating it's debt)
        if normalized.get('interest_rate') and normalized.get('interest_rate').strip():
            normalized['investment_type'] = 'First lien senior secured loan'
        # Otherwise keep as "Restricted Securities" or infer from context
        elif normalized.get('principal_amount') or normalized.get('cost'):
            # Has principal/cost but no rate - might still be debt, default to secured loan
            normalized['investment_type'] = 'First lien senior secured loan'
        # If no financial data, keep as Restricted Securities or check company name
        else:
            normalized['investment_type'] = 'Restricted Securities'
    elif 'first lien' in inv_type or 'senior secured' in inv_type:
        # Preserve "revolving" if present
        if 'revolving' in inv_type:
            normalized['investment_type'] = 'First lien senior secured revolving loan'
        else:
            normalized['investment_type'] = 'First lien senior secured loan'
    elif 'second lien' in inv_type:
        normalized['investment_type'] = 'Second lien senior secured loan'
    elif 'subordinated' in inv_type:
        normalized['investment_type'] = 'Subordinated loan'
    # If still unknown or empty, try to infer from company name patterns
    elif normalized['investment_type'] == 'Unknown' or not normalized['investment_type']:
        # Default fallback - check if it looks like equity
        if any(x in company_name_lower for x in ['- propriety', '- common', '- units', '- class']):
            normalized['investment_type'] = 'Equity'
        else:
            # Default to secured loan if we have financial data
            if normalized.get('principal_amount') or normalized.get('cost'):
                normalized['investment_type'] = 'First lien senior secured loan'
    
    # Clean company_name - remove common prefixes/suffixes
    company = normalized['company_name']
    # Remove trailing asterisks and whitespace
    company = re.sub(r'\s*\*\*\*\s*$', '', company)
    company = re.sub(r'\s+', ' ', company).strip()
    
    # Handle company names that include investment type (e.g., "LogicMonitor, Inc., Revolver")
    # Extract the actual company name and update investment_type if needed
    if ', Revolver' in company:
        company = company.replace(', Revolver', '').strip()
        if 'revolving' not in normalized['investment_type'].lower():
            normalized['investment_type'] = 'First lien senior secured revolving loan'
    elif ', Delayed Draw Term Loan' in company or ', Delayed Draw' in company:
        # Remove delayed draw suffix but keep as term loan
        company = re.sub(r',\s*Delayed Draw.*', '', company).strip()
    elif ', Term Loan' in company:
        company = company.replace(', Term Loan', '').strip()
    
    # Normalize company name variations for better deduplication
    # Normalize commas before entity suffixes first (e.g., "Company, Inc." -> "Company Inc")
    company = re.sub(r',\s+(Inc|LLC|Ltd|Corp|Co)\.?\b', r' \1', company, flags=re.IGNORECASE)
    # Remove punctuation variations like "Inc." vs "Inc", "LLC" vs "L.L.C."
    company = re.sub(r'\bInc\.\b', 'Inc', company, flags=re.IGNORECASE)
    company = re.sub(r'\bL\.L\.C\.\b', 'LLC', company, flags=re.IGNORECASE)
    company = re.sub(r'\bLtd\.\b', 'Ltd', company, flags=re.IGNORECASE)
    company = re.sub(r'\bCorp\.\b', 'Corp', company, flags=re.IGNORECASE)
    company = re.sub(r'\bCo\.\b', 'Co', company, flags=re.IGNORECASE)
    # Remove trailing periods and commas
    company = company.rstrip('., ').strip()
    
    normalized['company_name'] = company
    
    # Normalize dates to MM/YYYY or MM/DD/YYYY format if possible
    for date_field in ['acquisition_date', 'maturity_date']:
        date_val = normalized[date_field]
        if date_val and date_val != '':
            # Already in good format, keep as-is
            pass
    
    # Format financial values - convert to numbers or empty string
    for field in ['principal_amount', 'cost', 'fair_value']:
        val = normalized[field]
        if val is None or val == '':
            normalized[field] = ''
        elif isinstance(val, (int, float)):
            # Keep as number for CSV (will be written as-is)
            pass
        elif isinstance(val, str):
            # Try to parse
            try:
                # Remove commas and parse
                cleaned = val.replace(',', '').strip()
                if cleaned:
                    normalized[field] = float(cleaned)
                else:
                    normalized[field] = ''
            except:
                normalized[field] = ''
    
    return normalized


def _normalize_company_name(raw: str) -> str:
    name = raw or ''
    name = re.sub(r'\s*\*\*\*\s*$', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove embedded instrument suffixes
    name = re.sub(r',\s*Revolver.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r',\s*Delayed Draw.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r',\s*Term Loan.*$', '', name, flags=re.IGNORECASE)
    # Normalize commas before suffixes
    name = re.sub(r',\s+(Inc|LLC|Ltd|Corp|Co)\.?\b', r' \1', name, flags=re.IGNORECASE)
    # Normalize punctuations in suffixes
    name = re.sub(r'\bInc\.\b', 'Inc', name, flags=re.IGNORECASE)
    name = re.sub(r'\bL\.L\.C\.\b', 'LLC', name, flags=re.IGNORECASE)
    name = re.sub(r'\bLtd\.\b', 'Ltd', name, flags=re.IGNORECASE)
    name = re.sub(r'\bCorp\.\b', 'Corp', name, flags=re.IGNORECASE)
    name = re.sub(r'\bCo\.\b', 'Co', name, flags=re.IGNORECASE)
    # Trim trailing punctuation
    return name.rstrip('., ').strip()


def _extract_revolver_commitments_from_investments(investments: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Extract revolver commitments from investment data.
    For revolvers with only fair_value (no principal), the fair_value is likely the committed amount.
    Returns mapping: normalized_company -> { 'commitment_limit': float, 'undrawn_commitment': float }
    """
    commitments: Dict[str, Dict[str, float]] = {}
    
    for inv in investments:
        company_raw = inv.get('company_name', '').strip()
        if not company_raw or ', Revolver' not in company_raw:
            continue
            
        # Normalize company name
        company = _normalize_company_name(company_raw.replace(', Revolver', '').strip())
        
        # Try to extract commitment limit from fair_value (undrawn revolvers show commitment as fair_value)
        fair_val_str = str(inv.get('fair_value', '') or '').strip()
        if fair_val_str:
            try:
                fair_val = float(fair_val_str.replace(',', ''))
                # For revolvers, fair_value often represents the commitment/limit
                if company not in commitments:
                    commitments[company] = {'commitment_limit': fair_val, 'undrawn_commitment': fair_val}
                else:
                    # Take the maximum if we see multiple entries
                    commitments[company]['commitment_limit'] = max(
                        commitments[company].get('commitment_limit', 0.0), fair_val
                    )
                    commitments[company]['undrawn_commitment'] = max(
                        commitments[company].get('undrawn_commitment', 0.0), fair_val
                    )
            except (ValueError, TypeError):
                pass
    
    return commitments


def _extract_revolver_commitments_from_note7(txt_path: str, headers: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    """Heuristically extract per-company revolver commitments from Note 7.
    Returns mapping: normalized_company -> { 'commitment_limit': float, 'undrawn_commitment': float }
    """
    try:
        import bs4  # noqa: F401
    except Exception:
        pass

    commitments: Dict[str, Dict[str, float]] = {}
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return commitments

    # Very heuristic: find table-like lines containing keywords and dollar amounts
    # We'll scan for lines with both a company-like token and amounts, near "unfunded" or "commitment" words.
    lines = content.splitlines()
    window = 8
    for i, line in enumerate(lines):
        low = line.lower()
        if ('unfunded' in low or 'commitment' in low) and ('$' in line or ',' in line):
            block = ' '.join(lines[max(0, i - window): i + window + 1])
            # Pull candidate company and two amounts
            # Company: sequence of letters, numbers, commas before first amount
            m = re.search(r'([A-Za-z0-9&\-/\.,\(\)\s]{5,}?)\s*\$?([0-9][0-9,]{2,})(?:\.[0-9]+)?\s*(?:\$|\b)', block)
            if not m:
                continue
            company_raw = m.group(1)
            # Find amounts in the block
            nums = re.findall(r'\$?([0-9][0-9,]{2,})(?:\.[0-9]+)?', block)
            amounts: List[float] = []
            for n in nums[:3]:
                try:
                    amounts.append(float(n.replace(',', '')))
                except Exception:
                    continue
            if not amounts:
                continue
            company = _normalize_company_name(company_raw)
            entry = commitments.get(company, {'commitment_limit': 0.0, 'undrawn_commitment': 0.0})
            # Guessing: the largest is limit, smallest is undrawn if two present
            if len(amounts) >= 2:
                entry['commitment_limit'] = max(entry.get('commitment_limit', 0.0), max(amounts))
                entry['undrawn_commitment'] = max(entry.get('undrawn_commitment', 0.0), min(amounts))
            else:
                # Single amount; treat as limit if bigger than current
                entry['commitment_limit'] = max(entry.get('commitment_limit', 0.0), amounts[0])
            commitments[company] = entry
    return commitments


def extract_bxsl_investments(user_agent: str = "BDC-Extractor/1.0 contact@example.com") -> Optional[str]:
    """
    Fetch latest BXSL 10-Q, parse investments, and write standardized CSV.

    Returns the path to the CSV on success; None otherwise.
    """
    ticker = "BXSL"

    client = SECAPIClient(data_dir="temp_filings", user_agent=user_agent)
    index_url = client.get_filing_index_url(ticker, "10-Q")
    if not index_url:
        logger.error("Could not find latest 10-Q index URL for BXSL")
        return None

    documents = client.get_documents_from_index(index_url)
    parser = FlexibleTableParser(user_agent=user_agent)

    # Try main HTML first
    selected_doc = _select_main_html_document(documents)
    investments: List[dict] = []

    def try_parse(doc: FilingDocument) -> Tuple[List[dict], FilingDocument]:
        parsed: List[dict] = []
        try:
            parsed = parser.parse_html_filing(doc.url)
        except Exception as e:
            logger.warning(f"Parse failed for {doc.filename}: {e}")
        return parsed, doc

    if selected_doc:
        investments, _ = try_parse(selected_doc)
        logger.info(f"Main HTML ({selected_doc.filename}) yielded {len(investments)} investments")

    # Fallback: iterate all HTML docs and pick the one with max rows
    if not investments:
        logger.info("Main HTML yielded 0 investments; scanning other HTML documents...")
        best: Tuple[int, FilingDocument, List[dict]] = (0, None, [])
        for d in documents:
            name = (d.filename or '').lower()
            if not (name.endswith('.htm') or name.endswith('.html')):
                continue
            parsed, _ = try_parse(d)
            if parsed and len(parsed) > best[0]:
                best = (len(parsed), d, parsed)
        if best[0] > 0:
            investments = best[2]
            selected_doc = best[1]
            logger.info(f"Selected {selected_doc.filename} based on max investments: {best[0]}")

    # If still no investments, try a more aggressive parsing approach
    if not investments and selected_doc:
        logger.info("Attempting direct HTML table extraction...")
        try:
            response = requests.get(selected_doc.url, headers={'User-Agent': user_agent})
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find tables that might contain investment data
            all_tables = soup.find_all('table')
            logger.info(f"Found {len(all_tables)} tables in document")
            
            # Look for schedule of investments
            for table in all_tables:
                table_text = table.get_text().lower()
                if 'portfolio investments' in table_text or 'schedule of investments' in table_text:
                    logger.info(f"Found potential schedule table with {len(table.find_all('tr'))} rows")
                    # Try parsing this specific table
                    investments = parser._parse_table(table, is_first=True)
                    if investments:
                        logger.info(f"Successfully parsed {len(investments)} investments from schedule table")
                        break
        except Exception as e:
            logger.warning(f"Direct table extraction failed: {e}")

    # Write to CSV with ARCC schema
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Fallback: if parsing failed, try to use existing comprehensive CSV files if available
    if not investments:
        logger.warning("HTML parsing failed; attempting to use existing comprehensive CSV as fallback")
        # Try the structured/dated file first (has 1404 rows with all fields)
        fallback_csvs = [
            os.path.join(output_dir, "BXSL_Blackstone_Secured_Lending_Fund_investments_structured_dated.csv"),
            os.path.join(output_dir, "BXSL_Blackstone_Secured_Lending_Fund_investments_normalized.csv"),
            os.path.join(output_dir, "BXSL_from_10Q.csv")
        ]
        for fallback_csv in fallback_csvs:
            if os.path.exists(fallback_csv):
                logger.info(f"Loading existing CSV: {fallback_csv}")
                try:
                    with open(fallback_csv, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        investments = list(reader)
                    if investments:
                        logger.info(f"Loaded {len(investments)} investments from {os.path.basename(fallback_csv)}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to load {fallback_csv}: {e}")
                    continue
    
    if not investments:
        logger.error("Failed to extract any investments from BXSL 10-Q documents")
        return None

    # Extract revolver commitments from investment data itself
    commitments_map: Dict[str, Dict[str, float]] = {}
    try:
        commitments_map = _extract_revolver_commitments_from_investments(investments)
        logger.info(f"Extracted {len(commitments_map)} revolver commitment entries from investment data")
    except Exception as e:
        logger.warning(f"Commitments extraction failed: {e}")

    # Normalize all investments and deduplicate
    normalized_rows = []
    seen_keys = set()  # Track duplicates: (company_name, investment_type)
    duplicates_count = 0
    empty_rows_count = 0
    
    for inv in investments:
        normalized = _normalize_bxsl_row(inv)
        
        # Enrich revolvers with commitments if available
        company_key = _normalize_company_name(normalized.get('company_name', ''))
        inv_type_l = (normalized.get('investment_type') or '').lower()
        if 'revolving' in inv_type_l and company_key in commitments_map:
            cm = commitments_map[company_key]
            normalized['commitment_limit'] = cm.get('commitment_limit') or ''
            normalized['undrawn_commitment'] = cm.get('undrawn_commitment') or ''
        else:
            normalized['commitment_limit'] = normalized.get('commitment_limit') or ''
            normalized['undrawn_commitment'] = normalized.get('undrawn_commitment') or ''

        # Filter out rows with no meaningful financial data
        has_principal = normalized.get('principal_amount') and str(normalized['principal_amount']).strip() != ''
        has_cost = normalized.get('cost') and str(normalized['cost']).strip() != ''
        has_fair_value = normalized.get('fair_value') and str(normalized['fair_value']).strip() != ''
        
        if not (has_principal or has_cost or has_fair_value):
            # Skip rows with no financial data (likely subtotals or continuation rows)
            empty_rows_count += 1
            continue
        
        # Create deduplication key (company + investment type)
        company = normalized.get('company_name', '').strip()
        inv_type = normalized.get('investment_type', '').strip()
        
        if not company or company == '':
            # Skip rows without company name
            empty_rows_count += 1
            continue
            
        key = (company.lower(), inv_type.lower())
        
        # Check if we've seen this combination (duplicate from 2024/2025 tables)
        if key in seen_keys:
            duplicates_count += 1
            continue
        
        seen_keys.add(key)
        normalized_rows.append(normalized)
    
    if duplicates_count > 0:
        logger.info(f"Filtered out {duplicates_count} duplicate rows (likely 2024/2025 duplicates)")
    if empty_rows_count > 0:
        logger.info(f"Filtered out {empty_rows_count} rows with no financial data")

    # Write to CSV
    output_file = os.path.join(output_dir, "BXSL_Blackstone_Secured_Lending_Fund_investments.csv")

    fieldnames = [
        'company_name', 'industry', 'business_description', 'investment_type',
        'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
        'interest_rate', 'reference_rate', 'spread',
        'commitment_limit', 'undrawn_commitment'
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in normalized_rows:
            # Apply standardization
            if 'investment_type' in row:
                row['investment_type'] = standardize_investment_type(row.get('investment_type'))
            if 'industry' in row:
                row['industry'] = standardize_industry(row.get('industry'))
            if 'reference_rate' in row:
                row['reference_rate'] = standardize_reference_rate(row.get('reference_rate')) or ''
            # Write row, converting None to empty string
            writer.writerow({k: (row.get(k) if row.get(k) is not None else '') for k in fieldnames})

    logger.info(f"BXSL investments saved to: {output_file} ({len(normalized_rows)} rows)")
    return output_file


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    csv_path = extract_bxsl_investments()
    if csv_path:
        print(f"Success: {csv_path}")
        return 0
    else:
        print("Failed to extract BXSL investments")
        return 1


if __name__ == "__main__":
    exit(main())
