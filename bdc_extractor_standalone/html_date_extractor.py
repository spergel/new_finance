#!/usr/bin/env python3
"""
Helper functions for extracting dates from HTML tables.
Used across multiple parsers to improve date extraction consistency.
"""

import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup

def find_maturity_date_column(header_row, cell_texts: List[str]) -> Optional[int]:
    """
    Find the column index for maturity date in a table header.
    Returns the column index or None if not found.
    """
    if not header_row:
        return None
    
    # Get all header cells
    header_cells = header_row.find_all(['th', 'td'])
    header_texts = [cell.get_text(" ", strip=True).lower() for cell in header_cells]
    
    # Patterns to match maturity date columns
    maturity_patterns = [
        r'maturity\s+date',
        r'maturity',
        r'due\s+date',
        r'due',
        r'maturity\s+date\s*\([^)]*\)',  # "Maturity Date (MM/DD/YYYY)"
    ]
    
    for i, header_text in enumerate(header_texts):
        for pattern in maturity_patterns:
            if re.search(pattern, header_text, re.IGNORECASE):
                return i
    
    # Also check cell_texts if provided (for cases where we're iterating rows)
    if cell_texts:
        for i, text in enumerate(cell_texts):
            text_lower = text.lower()
            for pattern in maturity_patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return i
    
    return None

def extract_maturity_date_from_cell(cell) -> Optional[str]:
    """
    Extract maturity date from a table cell.
    Handles various formats: MM/DD/YYYY, YYYY-MM-DD, Month DD, YYYY, etc.
    """
    if not cell:
        return None
    
    # Get text from cell
    if isinstance(cell, str):
        cell_text = cell
    else:
        cell_text = cell.get_text(" ", strip=True)
    
    if not cell_text or cell_text in ['—', '-', '', 'N/A', 'N/A', '—', '—']:
        return None
    
    # Try to extract date from XBRL tags first (if present)
    if hasattr(cell, 'prettify'):
        cell_html = str(cell)
        # Look for XBRL date tags
        xbrl_date_match = re.search(
            r'<ix:nonnumeric[^>]*name=["\'][^"\']*maturity[^"\']*["\'][^>]*>([^<]+)</ix:nonnumeric>',
            cell_html, re.IGNORECASE
        )
        if xbrl_date_match:
            date_str = xbrl_date_match.group(1).strip()
            normalized = normalize_date(date_str)
            if normalized:
                return normalized
    
    # Try various date patterns
    date_patterns = [
        r'(\d{1,2}/\d{1,2}/\d{4})',  # MM/DD/YYYY
        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
        r'([A-Za-z]+\s+\d{1,2},\s*\d{4})',  # Month DD, YYYY
        r'([A-Za-z]+\s+\d{4})',  # Month YYYY
        r'(\d{1,2}/\d{4})',  # MM/YYYY
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, cell_text)
        if match:
            date_str = match.group(1)
            normalized = normalize_date(date_str)
            if normalized:
                return normalized
    
    return None

def extract_maturity_date_from_row(cells: List, cell_texts: List[str], 
                                   maturity_col: Optional[int] = None) -> Optional[str]:
    """
    Extract maturity date from a table row.
    If maturity_col is provided, uses that column. Otherwise searches all cells.
    """
    # If we know the column, use it
    if maturity_col is not None and maturity_col < len(cells):
        cell = cells[maturity_col]
        date = extract_maturity_date_from_cell(cell)
        if date:
            return date
    
    # Otherwise, search all cells for date patterns
    for i, cell in enumerate(cells):
        if i == maturity_col:  # Skip if we already checked this
            continue
        date = extract_maturity_date_from_cell(cell)
        if date:
            # Prefer dates that look like maturity dates (future dates, or far dates)
            # For now, just return the first valid date found
            return date
    
    return None

def normalize_date(date_str: str) -> Optional[str]:
    """
    Normalize date string to YYYY-MM-DD format.
    Handles various input formats.
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Remove common prefixes/suffixes
    date_str = re.sub(r'^(maturity|due|date)[:\s]*', '', date_str, flags=re.IGNORECASE)
    date_str = date_str.strip()
    
    # Pattern 1: MM/DD/YYYY
    match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if match:
        month = match.group(1).zfill(2)
        day = match.group(2).zfill(2)
        year = match.group(3)
        return f"{year}-{month}-{day}"
    
    # Pattern 2: YYYY-MM-DD
    match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if match:
        return date_str  # Already in correct format
    
    # Pattern 3: Month DD, YYYY (e.g., "September 30, 2025")
    month_names = {
        'january': '01', 'february': '02', 'march': '03', 'april': '04',
        'may': '05', 'june': '06', 'july': '07', 'august': '08',
        'september': '09', 'october': '10', 'november': '11', 'december': '12'
    }
    match = re.match(r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', date_str, re.IGNORECASE)
    if match:
        month_name = match.group(1).lower()
        day = match.group(2).zfill(2)
        year = match.group(3)
        month = month_names.get(month_name)
        if month:
            return f"{year}-{month}-{day}"
    
    # Pattern 4: Month YYYY (e.g., "September 2025")
    match = re.match(r'([A-Za-z]+)\s+(\d{4})', date_str, re.IGNORECASE)
    if match:
        month_name = match.group(1).lower()
        year = match.group(2)
        month = month_names.get(month_name)
        if month:
            return f"{year}-{month}-01"  # Default to first of month
    
    # Pattern 5: MM/YYYY
    match = re.match(r'(\d{1,2})/(\d{4})', date_str)
    if match:
        month = match.group(1).zfill(2)
        year = match.group(2)
        return f"{year}-{month}-01"  # Default to first of month
    
    return None

def find_date_columns_in_table(table) -> Dict[str, int]:
    """
    Find all date-related columns in a table.
    Returns a dict mapping column type to column index.
    """
    columns = {}
    
    # Find header row
    rows = table.find_all('tr')
    if not rows:
        return columns
    
    # Check first few rows for headers
    for row in rows[:5]:
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue
        
        cell_texts = [cell.get_text(" ", strip=True).lower() for cell in cells]
        header_text = " ".join(cell_texts)
        
        # Check if this looks like a header row
        if any(kw in header_text for kw in ['company', 'investment', 'type', 'principal', 'fair value']):
            # Map columns
            for i, text in enumerate(cell_texts):
                if 'maturity' in text and 'date' in text:
                    columns['maturity_date'] = i
                elif 'acquisition' in text and 'date' in text:
                    columns['acquisition_date'] = i
                elif 'investment' in text and 'date' in text:
                    columns['acquisition_date'] = i
                elif text == 'maturity' and 'maturity_date' not in columns:
                    columns['maturity_date'] = i
                elif 'due' in text and 'date' in text:
                    columns['maturity_date'] = i
            
            if columns:
                break
    
    return columns

