#!/usr/bin/env python3
"""Enrich NMFC CSV with industries from HTML tables."""

import re
import logging
import csv
import requests
from typing import Dict, Optional
from bs4 import BeautifulSoup
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_industry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_industries_from_html(htm_url: str) -> Dict[str, str]:
    """Extract industry mappings from HTML tables."""
    industry_map = {}
    headers = {'User-Agent': 'BDC-Extractor/1.0 contact@example.com'}
    
    try:
        logger.info(f"Downloading HTML for industry extraction: {htm_url}")
        response = requests.get(htm_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find investment tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables")
        
        current_industry = "Unknown"
        current_company = None
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                if not any(cell_texts):
                    continue
                
                first_cell = cell_texts[0] if cell_texts else ""
                
                # Check if this is an industry header
                if _is_industry_header(first_cell, cell_texts):
                    current_industry = _clean_industry_name(first_cell)
                    logger.debug(f"Found industry: {current_industry}")
                    continue
                
                # Check if this is a company name row
                if len(cell_texts) > 0:
                    company_name = cell_texts[0].strip()
                    if company_name and _is_company_name(company_name, cell_texts):
                        # Clean company name
                        company_name = re.sub(r'\s*,\s*.*$', '', company_name)  # Remove suffixes after comma
                        company_name = re.sub(r'\s+\(.*?\)', '', company_name)  # Remove parentheticals
                        company_name = company_name.strip()
                        
                        if company_name and company_name != 'Unknown':
                            company_key = _normalize_company_name(company_name)
                            if current_industry and current_industry != 'Unknown':
                                industry_map[company_key] = current_industry
                                logger.debug(f"Mapped {company_name} -> {current_industry}")
        
        logger.info(f"Found {len(industry_map)} industry mappings from HTML")
        
    except Exception as e:
        logger.warning(f"Failed to extract industries from HTML: {e}")
    
    return industry_map


def _is_industry_header(first_cell: str, cell_texts: list) -> bool:
    """Check if this row is an industry header."""
    if not first_cell or len(first_cell) < 3:
        return False
    
    # Industry keywords
    industry_keywords = [
        'software', 'healthcare', 'technology', 'financial services',
        'commercial', 'professional services', 'insurance', 'consumer',
        'industrial', 'energy', 'materials', 'transportation', 'aerospace',
        'telecommunications', 'media', 'entertainment', 'utilities',
        'pharmaceuticals', 'biotechnology', 'food and beverage', 'retail',
        'business services', 'healthcare services', 'education', 'real estate'
    ]
    
    text_lower = first_cell.lower()
    
    # Must contain industry keyword
    has_industry = any(kw in text_lower for kw in industry_keywords)
    not_company = not any(indicator in text_lower for indicator in ['llc', 'inc.', 'corp', 'ltd', 'limited', 'holdings'])
    not_total = not text_lower.startswith('total')
    not_header = not any(kw in text_lower for kw in ['company', 'description', 'investment', 'coupon', 'maturity', 'principal'])
    
    return has_industry and not_company and not_total and not_header


def _is_company_name(text: str, cell_texts: list) -> bool:
    """Check if this looks like a company name."""
    if not text or len(text) < 2:
        return False
    
    # Company indicators
    has_company_indicator = any(indicator in text for indicator in ['LLC', 'Inc.', 'Corp', 'Ltd', 'Limited', 'Holdings', 'Holdco', 'LP', 'L.P.'])
    
    # Not a number or date
    is_not_numeric = not re.match(r'^[\d\s,\.\$%]+$', text)
    
    # Not an investment type
    investment_types = ['first lien', 'second lien', 'equity', 'preferred', 'common', 'warrant', 'note', 'loan']
    is_not_investment_type = not any(inv_type in text.lower() for inv_type in investment_types)
    
    return (has_company_indicator or (is_not_numeric and is_not_investment_type and len(text) > 5))


def _clean_industry_name(text: str) -> str:
    """Clean industry name."""
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common prefixes
    text = re.sub(r'^(industries?|sectors?|categories?):?\s*', '', text, flags=re.IGNORECASE)
    return text


def _normalize_company_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ''
    name = re.sub(r'\s+(LLC|Inc\.?|Corp\.?|L\.P\.?|LP|Ltd\.?|Limited|Holdings|Holdco)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[,\s]+', ' ', name).strip().lower()
    return name


def enrich_csv_with_industries(csv_file: str, industry_map: Dict[str, str], output_file: str):
    """Enrich CSV file with industries."""
    enriched_count = 0
    
    with open(csv_file, 'r', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        if not reader.fieldnames:
            logger.error("CSV file has no headers")
            return
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
            writer.writeheader()
            
            for row in reader:
                if row.get('industry', '').strip() in ('Unknown', ''):
                    company_name = row.get('company_name', '').strip()
                    if company_name:
                        # Remove suffixes from company name for matching
                        clean_name = re.sub(r'\s*,\s*.*$', '', company_name)
                        clean_name = re.sub(r'\s+\(.*?\)', '', clean_name)
                        company_key = _normalize_company_name(clean_name)
                        
                        # Try exact match
                        if company_key in industry_map:
                            row['industry'] = standardize_industry(industry_map[company_key])
                            enriched_count += 1
                        else:
                            # Try fuzzy matching
                            for key, industry in industry_map.items():
                                if company_key in key or key in company_key:
                                    row['industry'] = standardize_industry(industry)
                                    enriched_count += 1
                                    break
                
                writer.writerow(row)
    
    logger.info(f"Enriched {enriched_count} investments with industries")


def main():
    """Main entry point."""
    ticker = 'NMFC'
    sec_client = SECAPIClient()
    
    # Get latest filing
    cik = sec_client.get_cik(ticker)
    if not cik:
        logger.error(f"Could not find CIK for {ticker}")
        return
    
    index_url = sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=2025)
    if not index_url:
        logger.error(f"Could not find 10-Q filing for {ticker}")
        return
    
    # Get HTML URL
    documents = sec_client.get_documents_from_index(index_url)
    main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
    if not main_html:
        logger.error("Could not find HTML document")
        return
    
    htm_url = main_html.url
    logger.info(f"HTML URL: {htm_url}")
    
    # Extract industries
    industry_map = extract_industries_from_html(htm_url)
    logger.info(f"Found {len(industry_map)} industry mappings")
    
    if not industry_map:
        logger.warning("No industries found in HTML tables")
        return
    
    # Enrich CSV
    csv_file = '../output/NMFC_New_Mountain_Finance_Corp_investments.csv'
    output_file = csv_file  # Overwrite original
    enrich_csv_with_industries(csv_file, industry_map, output_file)
    
    logger.info("Done!")


if __name__ == "__main__":
    main()

