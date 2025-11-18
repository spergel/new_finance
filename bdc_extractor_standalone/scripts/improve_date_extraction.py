#!/usr/bin/env python3
"""
Script to improve date extraction by parsing dates from XBRL identifiers
and HTML content for investments that are missing dates.
"""
import pandas as pd
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

def extract_dates_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract acquisition and maturity dates from text using multiple patterns."""
    if not text:
        return None, None
    
    acquisition_date = None
    maturity_date = None
    
    # Normalize text
    text = text.replace('&amp;', '&').replace('&#x2013;', '-').replace('&#x2014;', '-')
    
    # Acquisition date patterns (ordered by specificity)
    acq_patterns = [
        r'Initial\s+Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'Origination\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'Investment\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'Purchase\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})(?=.*\b(acquisition|origination|investment|purchase|initial)\s+date\b)',
    ]
    
    # Maturity date patterns
    mat_patterns = [
        r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'Maturity\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'Due\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'Due\s+(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})(?=.*\bmaturity\b)',
        r'(\d{1,2}/\d{1,2}/\d{4})(?=.*\bdue\b)',
    ]
    
    # Try acquisition patterns
    for pattern in acq_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            acquisition_date = match.group(1)
            break
    
    # Try maturity patterns
    for pattern in mat_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            maturity_date = match.group(1)
            break
    
    # If we found one date but not both, try to find all dates and infer
    if (acquisition_date and not maturity_date) or (maturity_date and not acquisition_date):
        all_dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', text)
        if len(all_dates) >= 2:
            if not acquisition_date:
                acquisition_date = all_dates[0]
            if not maturity_date:
                maturity_date = all_dates[-1]
        elif len(all_dates) == 1:
            # Check context around the date
            date_str = all_dates[0]
            date_idx = text.find(date_str)
            context = text[max(0, date_idx-50):min(len(text), date_idx+50)]
            if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', context, re.IGNORECASE):
                if not acquisition_date:
                    acquisition_date = date_str
            elif re.search(r'\b(maturity|due)\s+date\b', context, re.IGNORECASE):
                if not maturity_date:
                    maturity_date = date_str
    
    return acquisition_date, maturity_date

def improve_dates_for_file(csv_path: Path) -> int:
    """Improve date extraction for a single CSV file."""
    try:
        df = pd.read_csv(csv_path)
        if 'company_name' not in df.columns:
            return 0
        
        updates = 0
        
        # Try to extract dates from multiple sources
        for idx, row in df.iterrows():
            acq_date = row.get('acquisition_date')
            mat_date = row.get('maturity_date')
            
            # Skip if both dates already exist
            if pd.notna(acq_date) and pd.notna(mat_date):
                continue
            
            # Try to extract from company_name (sometimes contains date info)
            company_name = str(row.get('company_name', ''))
            if company_name and company_name != 'Unknown':
                acq, mat = extract_dates_from_text(company_name)
                if acq and pd.isna(acq_date):
                    df.at[idx, 'acquisition_date'] = acq
                    updates += 1
                if mat and pd.isna(mat_date):
                    df.at[idx, 'maturity_date'] = mat
                    updates += 1
            
            # Try to extract from investment_type if it contains date info
            inv_type = str(row.get('investment_type', ''))
            if inv_type and inv_type != 'Unknown':
                acq, mat = extract_dates_from_text(inv_type)
                if acq and pd.isna(acq_date):
                    df.at[idx, 'acquisition_date'] = acq
                    updates += 1
                if mat and pd.isna(mat_date):
                    df.at[idx, 'maturity_date'] = mat
                    updates += 1
            
            # Try to extract from industry if it contains date info
            industry = str(row.get('industry', ''))
            if industry and industry != 'Unknown':
                acq, mat = extract_dates_from_text(industry)
                if acq and pd.isna(acq_date):
                    df.at[idx, 'acquisition_date'] = acq
                    updates += 1
                if mat and pd.isna(mat_date):
                    df.at[idx, 'maturity_date'] = mat
                    updates += 1
        
        if updates > 0:
            df.to_csv(csv_path, index=False)
            print(f"Updated {updates} dates in {csv_path.name}")
        
        return updates
    except Exception as e:
        print(f"Error processing {csv_path.name}: {e}")
        return 0

if __name__ == "__main__":
    output_dir = Path('output')
    csv_files = list(output_dir.glob('*_investments.csv'))
    
    total_updates = 0
    for csv_file in csv_files:
        updates = improve_dates_for_file(csv_file)
        total_updates += updates
    
    print(f"\nTotal: Updated {total_updates} dates across {len(csv_files)} files")

