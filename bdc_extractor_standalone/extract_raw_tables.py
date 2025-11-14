#!/usr/bin/env python3
"""
Extract raw HTML tables from BDC filings, removing styling but preserving structure.
This helps visualize the actual table structure for debugging parsers.
"""

import os
import re
import logging
from pathlib import Path
from bs4 import BeautifulSoup
import requests
from typing import List, Dict, Optional

from historical_investment_extractor import HistoricalInvestmentExtractor
from bdc_config import BDC_UNIVERSE

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def clean_table_html(table) -> str:
    """Remove styling and attributes but preserve table structure."""
    # Create a copy to avoid modifying the original
    table_copy = BeautifulSoup(str(table), 'html.parser')
    
    # Remove all style attributes
    for tag in table_copy.find_all(True):
        # Remove style, class, id, and other styling attributes
        for attr in ['style', 'class', 'id', 'bgcolor', 'align', 'valign', 'width', 'height', 'cellpadding', 'cellspacing', 'border']:
            if attr in tag.attrs:
                del tag.attrs[attr]
        
        # Keep only essential attributes for table structure
        if tag.name in ['td', 'th']:
            # Keep colspan and rowspan (important for table structure)
            keep_attrs = {}
            if 'colspan' in tag.attrs:
                keep_attrs['colspan'] = tag.attrs['colspan']
            if 'rowspan' in tag.attrs:
                keep_attrs['rowspan'] = tag.attrs['rowspan']
            tag.attrs = keep_attrs
    
    return str(table_copy)


def is_schedule_table(table) -> bool:
    """Check if this table looks like a schedule of investments."""
    rows = table.find_all('tr')
    if not rows or len(rows) < 5:
        return False
    
    # Check first few rows for schedule indicators
    header_text = ""
    header_cells = []
    for row in rows[:3]:
        cells = row.find_all(['td', 'th'])
        for cell in cells:
            text = cell.get_text(" ", strip=True).lower().strip()
            if text:
                header_text += " " + text
                header_cells.append(text)
    
    # Must have portfolio company AND investment type AND at least one financial column
    has_portfolio_company = any('portfolio company' in text or ('company' in text and 'portfolio' in header_text) for text in header_cells)
    has_investment_type = any('investment type' in text or 'type of investment' in text for text in header_cells)
    has_financial = any(kw in header_text for kw in ['principal', 'fair value', 'cost', 'amortized cost', 'fair value'])
    
    # Also check for date columns
    has_dates = any(kw in header_text for kw in ['maturity date', 'maturity', 'acquisition date', 'investment date'])
    
    # Must have at least: portfolio company, investment type, and one financial column
    # AND dates (maturity or acquisition) - this is the key indicator
    # AND be a substantial table (at least 10 rows)
    if has_portfolio_company and has_investment_type and has_financial and has_dates:
        if len(rows) >= 10:  # Must be a substantial table
            return True
    
    return False


def extract_tables_from_filing(html_url: str, ticker: str) -> List[Dict]:
    """Extract schedule tables from a filing."""
    try:
        headers = {'User-Agent': 'BDC-Extractor/1.0 contact@example.com'}
        response = requests.get(html_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        
        schedule_tables = []
        for i, table in enumerate(tables):
            if is_schedule_table(table):
                cleaned_html = clean_table_html(table)
                schedule_tables.append({
                    'index': i,
                    'html': cleaned_html,
                    'raw_text': table.get_text(" ", strip=True)[:500]  # First 500 chars for preview
                })
        
        return schedule_tables
    except Exception as e:
        logger.error(f"Error extracting tables from {html_url}: {e}")
        return []


def main():
    """Extract raw tables from all BDCs."""
    output_dir = Path("raw_tables")
    output_dir.mkdir(exist_ok=True)
    
    extractor = HistoricalInvestmentExtractor()
    
    # Get list of tickers to process
    tickers = [bdc['ticker'] for bdc in BDC_UNIVERSE if bdc.get('ticker')]
    
    logger.info(f"Processing {len(tickers)} BDCs...")
    
    for ticker in tickers:
        logger.info(f"\n{'='*70}")
        logger.info(f"Processing {ticker}")
        logger.info(f"{'='*70}")
        
        try:
            # Get recent filing
            filings = extractor.sec_client.get_historical_10q_filings(ticker, years_back=1)
            if not filings:
                logger.warning(f"No filings found for {ticker}")
                continue
            
            filing = filings[0]
            html_url = extractor._get_filing_html_url(filing)
            
            if not html_url:
                logger.warning(f"No HTML URL found for {ticker}")
                continue
            
            logger.info(f"Filing: {filing.get('date')} - {html_url}")
            
            # Extract tables
            tables = extract_tables_from_filing(html_url, ticker)
            
            if not tables:
                logger.warning(f"No schedule tables found for {ticker}")
                continue
            
            logger.info(f"Found {len(tables)} schedule table(s)")
            
            # Save each table
            ticker_dir = output_dir / ticker
            ticker_dir.mkdir(exist_ok=True)
            
            for table_idx, table_data in enumerate(tables):
                # Save as HTML
                html_file = ticker_dir / f"table_{table_data['index']}.html"
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(f"<!-- Table {table_data['index']} from {ticker} -->\n")
                    f.write(f"<!-- Filing: {filing.get('date')} -->\n")
                    f.write(f"<!-- URL: {html_url} -->\n\n")
                    f.write(table_data['html'])
                
                logger.info(f"  Saved table {table_data['index']} to {html_file}")
                
                # Also save a text preview
                preview_file = ticker_dir / f"table_{table_data['index']}_preview.txt"
                with open(preview_file, 'w', encoding='utf-8') as f:
                    f.write(f"Table {table_data['index']} from {ticker}\n")
                    f.write(f"Filing: {filing.get('date')}\n")
                    f.write(f"URL: {html_url}\n\n")
                    f.write("Preview (first 500 chars):\n")
                    f.write(table_data['raw_text'])
            
            # Create index file
            index_file = ticker_dir / "index.txt"
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(f"BDC: {ticker}\n")
                f.write(f"Filing Date: {filing.get('date')}\n")
                f.write(f"HTML URL: {html_url}\n")
                f.write(f"Tables Found: {len(tables)}\n\n")
                for table_data in tables:
                    f.write(f"Table {table_data['index']}:\n")
                    f.write(f"  Preview: {table_data['raw_text'][:100]}...\n\n")
        
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            continue
    
    logger.info(f"\n{'='*70}")
    logger.info(f"Done! Tables saved to {output_dir}/")
    logger.info(f"{'='*70}")


if __name__ == "__main__":
    main()

