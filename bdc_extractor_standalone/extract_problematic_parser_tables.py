#!/usr/bin/env python3
"""
Extract HTML tables from problematic BDC parsers for analysis and custom parser creation.

This script extracts all investment schedule tables from the latest 10-Q filings
for BDCs with the lowest coverage rates, similar to what was done for ARCC.
"""

import os
import re
import logging
from typing import List, Optional
import requests
from bs4 import BeautifulSoup

from sec_api_client import SECAPIClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Top problematic parsers based on PARSER_TEST_RESULTS.md (sorted by worst coverage first)
PROBLEMATIC_PARSERS = [
    ('MAIN', 'Main Street Capital Corp', 51.7),  # Worst coverage
    ('NCDL', 'Nuveen Churchill Direct Lending Corp', 62.5),
    ('OBDC', 'Blue Owl Capital Corp', 62.6),
    ('TRIN', 'Trinity Capital Inc', 62.8),
    ('MFIC', 'Midcap Financial Investment Corp', 63.4),
    ('CGBD', 'TCG BDC Inc', 65.9),
    ('CION', 'CION Investment Corp', 68.6),
    ('GBDC', 'Golub Capital BDC Inc', 68.7),
    ('FSK', 'FS KKR Capital Corp', 68.7),
    ('CSWC', 'Capital Southwest Corp', 69.9),
    ('MSDL', 'Morgan Stanley Direct Lending Fund', 69.8),
    ('PSEC', 'Prospect Capital Corp', 69.0),
    ('PFLT', 'PennantPark Floating Rate Capital Ltd', 67.8),
    ('GAIN', 'Gladstone Investment Corp', 67.1),
    ('OCSL', 'Oaktree Specialty Lending Corp', 72.0),
    ('BBDC', 'Barings BDC Inc', 72.7),
    ('NMFC', 'New Mountain Finance Corp', 73.2),
    ('BCSF', 'Bain Capital Specialty Finance Inc', 79.7),
    ('TCPC', 'Blackrock TCP Capital Corp', 76.9),
    ('TSLX', 'Sixth Street Specialty Lending Inc', 76.9),
    ('HTGC', 'Hercules Capital Inc', 70.4),
    ('FDUS', 'Fidus Investment Corp', 76.0),
]


def normalize_text(text: str) -> str:
    """Normalize text by collapsing whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
    """Normalize text to lowercase for matching."""
    return normalize_text(text).lower()


def extract_tables_with_schedule(soup: BeautifulSoup, ticker: str) -> List[BeautifulSoup]:
    """
    Extract tables that appear to be investment schedules.
    
    Looks for tables with context containing "schedule of investments" or similar phrases.
    Also checks table headers for investment-related columns.
    """
    matches = []
    
    # Common phrases that indicate investment schedule tables
    required_phrases = [
        "schedule of investments",
        "schedule of portfolio investments",
        "consolidated schedule of investments",
        "portfolio investments",
    ]
    
    # Keywords that indicate financial statements (to exclude)
    financial_statement_keywords = [
        "consolidated statements of assets and liabilities",
        "consolidated statements of operations",
        "consolidated statements of cash flows",
        "consolidated statements of changes in net assets",
        "assets",
        "liabilities",
        "operations",
        "cash flows",
    ]
    
    # Investment schedule column indicators
    investment_column_keywords = [
        "company", "issuer", "portfolio company",
        "investment", "type of investment",
        "maturity", "maturity date",
        "principal", "par amount",
        "cost", "amortized cost",
        "fair value",
        "interest rate", "coupon", "spread",
        "reference rate",
    ]
    
    def context_matches(blob: str) -> bool:
        """Check if context blob contains investment schedule indicators."""
        blob_lower = blob.lower()
        # Exclude financial statements
        if any(keyword in blob_lower for keyword in financial_statement_keywords):
            return False
        return any(phrase in blob_lower for phrase in required_phrases)
    
    def has_investment_columns(table: BeautifulSoup) -> bool:
        """Check if table has investment-related column headers."""
        rows = table.find_all("tr")
        if not rows:
            return False
        
        # Check first few rows for headers
        header_text = ""
        for row in rows[:3]:
            cells = row.find_all(["td", "th"])
            for cell in cells:
                text = normalize_key(cell.get_text(" ", strip=True))
                header_text += " " + text
        
        # Count how many investment keywords appear in headers
        matches = sum(1 for keyword in investment_column_keywords if keyword in header_text)
        return matches >= 3  # Need at least 3 investment-related columns
    
    def is_financial_statement(table: BeautifulSoup) -> bool:
        """Check if table is a financial statement (to exclude)."""
        rows = table.find_all("tr")
        if not rows:
            return False
        
        # Check first few rows for financial statement indicators
        header_text = ""
        for row in rows[:3]:
            cells = row.find_all(["td", "th"])
            for cell in cells:
                text = normalize_key(cell.get_text(" ", strip=True))
                header_text += " " + text
        
        return any(keyword in header_text for keyword in financial_statement_keywords)
    
    for table in soup.find_all("table"):
        # Skip if it's clearly a financial statement
        if is_financial_statement(table):
            continue
        
        context_texts = []
        cur = table
        
        # Look backwards through the document for context
        for _ in range(20):  # Check up to 20 elements back
            prev = cur.find_previous(string=True)
            if not prev:
                break
            
            txt = normalize_key(prev if isinstance(prev, str) else prev.get_text(" ", strip=True))
            if txt:
                context_texts.append(txt)
            
            cur = prev.parent if hasattr(prev, "parent") else None
            if not cur:
                break
        
        context_blob = " ".join(context_texts)
        
        # Match if context matches OR if table has investment columns
        if context_matches(context_blob) or has_investment_columns(table):
            matches.append(table)
    
    # If no matches found, try finding tables with investment columns (but not financial statements)
    if not matches:
        logger.warning(f"No tables found with schedule context for {ticker}, trying tables with investment columns...")
        all_tables = soup.find_all("table")
        for table in all_tables:
            rows = table.find_all("tr")
            # Must have many rows (investment tables are large) and investment columns
            if len(rows) > 20 and has_investment_columns(table) and not is_financial_statement(table):
                matches.append(table)
                if len(matches) >= 10:  # Limit to first 10 investment tables
                    break
    
    return matches


def simplify_table(table: BeautifulSoup) -> str:
    """Simplify HTML table by removing attributes and unnecessary tags."""
    simple = BeautifulSoup(str(table), "html.parser").find("table")
    if not simple:
        return "<table></table>"
    
    # Replace IX tags (XBRL inline tags)
    for ix in simple.find_all(lambda t: isinstance(t.name, str) and t.name.lower().startswith("ix:")):
        ix.replace_with(ix.get_text(" ", strip=True))
    
    # Strip all attributes
    def strip_attrs(el):
        if hasattr(el, "attrs"):
            el.attrs = {}
        for child in getattr(el, "children", []):
            strip_attrs(child)
    
    strip_attrs(simple)
    
    # Unwrap formatting tags
    for tag_name in ["span", "div", "b", "strong", "i", "em", "u", "font"]:
        for t in simple.find_all(tag_name):
            t.unwrap()
    
    # Remove empty rows
    for tr in simple.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells or not any(c.get_text(strip=True) for c in cells):
            tr.decompose()
    
    # Keep only basic table structure tags
    allowed = {"table", "thead", "tbody", "tr", "th", "td", "colgroup", "col"}
    for tag in list(simple.find_all(True)):
        if tag.name not in allowed:
            tag.unwrap()
    
    return str(simple)


def extract_tables_for_ticker(ticker: str, company_name: str) -> Optional[dict]:
    """Extract all investment schedule tables for a given ticker."""
    logger.info(f"Extracting tables for {ticker} ({company_name})...")
    
    client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
    
    # Get latest 10-Q
    index_url = client.get_filing_index_url(ticker, "10-Q")
    if not index_url:
        logger.error(f"Could not find latest 10-Q for {ticker}")
        return None
    
    # Get documents
    docs = client.get_documents_from_index(index_url)
    main_html = next(
        (d for d in docs if d.filename.lower().endswith(".htm") and "index" not in d.filename.lower()),
        None
    )
    
    if not main_html:
        logger.error(f"No main HTML document found for {ticker}")
        return None
    
    logger.info(f"Found HTML document: {main_html.filename}")
    
    # Fetch HTML
    resp = requests.get(main_html.url, headers=client.headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Extract tables
    tables = extract_tables_with_schedule(soup, ticker)
    logger.info(f"Found {len(tables)} investment schedule tables for {ticker}")
    
    if not tables:
        logger.warning(f"No investment tables found for {ticker}")
        return {
            'ticker': ticker,
            'company_name': company_name,
            'html_url': main_html.url,
            'tables': [],
            'table_count': 0
        }
    
    # Save simplified tables
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    tables_dir = os.path.join(output_dir, f"{ticker.lower()}_tables")
    os.makedirs(tables_dir, exist_ok=True)
    
    simplified_tables = []
    for i, table in enumerate(tables, 1):
        simple_html = simplify_table(table)
        table_file = os.path.join(tables_dir, f"{ticker.lower()}_table_{i}.html")
        
        with open(table_file, "w", encoding="utf-8") as f:
            f.write(simple_html)
        
        simplified_tables.append({
            'index': i,
            'file': table_file,
            'html': simple_html
        })
    
    logger.info(f"Saved {len(simplified_tables)} tables to {tables_dir}")
    
    return {
        'ticker': ticker,
        'company_name': company_name,
        'html_url': main_html.url,
        'tables': simplified_tables,
        'table_count': len(simplified_tables),
        'tables_dir': tables_dir
    }


def main():
    """Extract tables for all problematic parsers."""
    results = []
    
    for ticker, company_name, coverage in PROBLEMATIC_PARSERS:
        try:
            result = extract_tables_for_ticker(ticker, company_name)
            if result:
                result['coverage'] = coverage
                results.append(result)
                logger.info(f"✓ {ticker}: {result['table_count']} tables extracted")
            else:
                logger.warning(f"✗ {ticker}: Failed to extract tables")
        except Exception as e:
            logger.error(f"✗ {ticker}: Error - {e}")
            continue
    
    # Summary
    print("\n" + "="*80)
    print("EXTRACTION SUMMARY")
    print("="*80)
    print(f"\nTotal tickers processed: {len(results)}")
    print(f"Total tables extracted: {sum(r['table_count'] for r in results)}")
    print("\nResults by ticker:")
    print("-" * 80)
    
    for result in sorted(results, key=lambda x: x['coverage']):
        print(f"{result['ticker']:6s} | {result['company_name']:40s} | "
              f"Coverage: {result['coverage']:5.1f}% | "
              f"Tables: {result['table_count']:2d} | "
              f"Dir: {result.get('tables_dir', 'N/A')}")
    
    print("\n" + "="*80)
    print("Next steps:")
    print("1. Review the extracted tables in output/{ticker}_tables/ directories")
    print("2. Analyze table structures to understand column mappings")
    print("3. Create custom parsers similar to arcc_custom_parser.py")
    print("="*80)


if __name__ == "__main__":
    main()

