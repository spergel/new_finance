#!/usr/bin/env python3
"""Enrich NMFC CSV with industries from XBRL."""

import re
import logging
import csv
import requests
from typing import Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_industry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_industries_from_xbrl(txt_url: str) -> Dict[str, str]:
    """Extract industry mappings from XBRL using EquitySecuritiesByIndustryAxis."""
    industry_map = {}
    
    try:
        logger.info(f"Downloading XBRL for industry enrichment: {txt_url}")
        headers = {'User-Agent': 'BDC-Extractor/1.0 contact@example.com'}
        response = requests.get(txt_url, headers=headers)
        response.raise_for_status()
        content = response.text
        
        # Extract contexts with investment identifiers and industry axes
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>', re.DOTALL
        )
        ep = re.compile(
            r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>',
            re.DOTALL | re.IGNORECASE
        )
        
        context_count = 0
        typed_member_count = 0
        industry_member_count = 0
        
        for m in cp.finditer(content):
            context_count += 1
            cid = m.group(1)
            chtml = m.group(2)
            
            # Find investment identifier
            tm = tp.search(chtml)
            if not tm:
                continue
            
            typed_member_count += 1
            ident = tm.group(1).strip()
            
            # Parse identifier to get company name
            company_name = ident
            if ',' in ident:
                company_name = ident.split(',')[0].strip()
            elif ' - ' in ident:
                company_name = ident.split(' - ')[0].strip()
            elif '-' in ident and ' - ' not in ident:
                parts = ident.split('-')
                if len(parts) >= 2:
                    last_part = parts[-1].strip().lower()
                    if any(kw in last_part for kw in ['lien', 'loan', 'equity', 'note', 'secured']):
                        company_name = '-'.join(parts[:-1]).strip()
                    else:
                        company_name = ident
            
            # Clean company name
            company_name = re.sub(r'\s+', ' ', company_name).strip()
            if not company_name or company_name == 'Unknown':
                continue
            
            # Try to find industry from explicitMember
            em = ep.search(chtml)
            industry = None
            if em:
                industry_member_count += 1
                industry_qname = em.group(1).strip()
                industry = industry_member_to_name(industry_qname)
            
            if industry:
                company_key = normalize_company_name(company_name)
                industry_map[company_key] = industry
        
        logger.info(f"XBRL parsing: {context_count} contexts, {typed_member_count} typed members, {industry_member_count} industry members")
        
    except Exception as e:
        logger.warning(f"Failed to extract industries from XBRL: {e}")
    
    return industry_map


def industry_member_to_name(qname: str) -> Optional[str]:
    """Convert XBRL industry QName to readable name."""
    local = qname.split(':', 1)[-1] if ':' in qname else qname
    local = re.sub(r'Member$', '', local, flags=re.IGNORECASE)
    if local.endswith('Sector'):
        local = local[:-6]
    words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
    words = re.sub(r'\bAnd\b', 'and', words, flags=re.IGNORECASE)
    words = re.sub(r'\s+', ' ', words).strip()
    return words if words else None


def normalize_company_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ''
    name = re.sub(r'\s+(LLC|Inc\.?|Corp\.?|L\.P\.?|LP|Ltd\.?|Limited|Holdings|Holdco)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[,\s]+', ' ', name).strip().lower()
    return name


def enrich_csv_with_industries(csv_file: str, industry_map: Dict[str, str], output_file: str):
    """Enrich CSV file with industries from XBRL."""
    enriched_count = 0
    
    with open(csv_file, 'r', encoding='utf-8') as f_in, open(output_file, 'w', encoding='utf-8', newline='') as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
        writer.writeheader()
        
        for row in reader:
            if row.get('industry', '').strip() in ('Unknown', ''):
                company_name = row.get('company_name', '').strip()
                if company_name:
                    company_key = normalize_company_name(company_name)
                    
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
    
    # Get XBRL URL
    match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
    if not match:
        logger.error("Could not parse accession")
        return
    
    accession = match.group(1)
    accession_no_hyphens = accession.replace('-', '')
    txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
    
    # Extract industries
    industry_map = extract_industries_from_xbrl(txt_url)
    logger.info(f"Found {len(industry_map)} industry mappings")
    
    # Enrich CSV
    csv_file = '../output/NMFC_New_Mountain_Finance_Corp_investments.csv'
    output_file = csv_file  # Overwrite original
    enrich_csv_with_industries(csv_file, industry_map, output_file)
    
    logger.info("Done!")


if __name__ == "__main__":
    main()

