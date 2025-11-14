#!/usr/bin/env python3
"""
Extract ALL XBRL facts/axes for each investment context.

For each investment identified by InvestmentIdentifierAxis, extract every
fact and axis that references that context to see what data is available.
"""

import os
import re
import logging
import csv
import json
from typing import List, Dict, Set, Optional
from collections import defaultdict
import requests

from sec_api_client import SECAPIClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Tickers that need full fact extraction (not BCSF, FDUS, MSDL, TRIN)
TICKERS_NEED_FULL_FACTS = [
    'ARCC', 'CGBD', 'CSWC', 'FSK', 'GBDC', 'GLAD', 'MAIN',
    'MRCC', 'MSIF', 'NCDL', 'NMFC', 'OBDC', 'OFS', 'OXSQ', 'PFX',
    'PSEC', 'RAND', 'SCM', 'SSSS', 'TPVG', 'WHF'
]

# Tickers that have all data in XBRL (just need reparse)
TICKERS_REPARSE_ONLY = ['BCSF', 'FDUS', 'MSDL', 'TRIN']

def extract_all_facts_for_investment(ticker: str) -> Dict:
    """Extract all facts for each investment context."""
    logger.info(f"Extracting all facts for {ticker}")
    
    sec_client = SECAPIClient()
    
    # Get CIK
    cik = sec_client.get_cik(ticker)
    if not cik:
        logger.error(f"Could not find CIK for {ticker}")
        return {'ticker': ticker, 'error': 'CIK not found', 'investments': []}
    
    # Get latest 10-Q
    index_url = sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
    if not index_url:
        logger.error(f"Could not find 10-Q filing for {ticker}")
        return {'ticker': ticker, 'error': '10-Q not found', 'investments': []}
    
    # Get XBRL URL
    match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
    if not match:
        logger.error(f"Could not parse accession for {ticker}")
        return {'ticker': ticker, 'error': 'Could not parse accession', 'investments': []}
    
    accession = match.group(1)
    accession_no_hyphens = accession.replace('-', '')
    txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
    
    logger.info(f"Downloading XBRL from: {txt_url}")
    
    try:
        resp = requests.get(txt_url, headers=sec_client.headers)
        resp.raise_for_status()
        content = resp.text
        
        # Extract investment contexts
        investment_contexts = _extract_investment_contexts(content)
        logger.info(f"Found {len(investment_contexts)} investment contexts")
        
        # Extract all facts
        all_facts = _extract_all_facts(content)
        logger.info(f"Found {len(all_facts)} total facts")
        
        # Group facts by context
        facts_by_context = defaultdict(list)
        for fact in all_facts:
            context_ref = fact.get('contextRef')
            if context_ref:
                facts_by_context[context_ref].append(fact)
        
        # Build investment records with all facts
        investments = []
        for ctx_id, ctx_info in investment_contexts.items():
            # Get all facts for this context
            facts = facts_by_context.get(ctx_id, [])
            
            # Build investment record
            inv = {
                'context_ref': ctx_id,
                'company_name': ctx_info.get('company_name', ''),
                'investment_type': ctx_info.get('investment_type', ''),
                'industry': ctx_info.get('industry', ''),
                'identifier': ctx_info.get('identifier', ''),
            }
            
            # Add all facts as separate fields
            fact_dict = {}
            for fact in facts:
                concept = fact.get('concept', '')
                value = fact.get('value', '')
                unit = fact.get('unit', '')
                
                # Store fact
                fact_dict[concept] = {
                    'value': value,
                    'unit': unit
                }
                
                # Also add as flat fields for common concepts
                concept_clean = concept.replace('us-gaap:', '').replace('dei:', '').lower()
                if 'principalamount' in concept_clean or 'ownedbalanceprincipalamount' in concept_clean:
                    inv['principal_amount'] = value
                elif 'cost' in concept_clean and ('amortized' in concept_clean or 'basis' in concept_clean):
                    inv['cost_basis'] = value
                elif 'fairvalue' in concept_clean:
                    inv['fair_value'] = value
                elif 'maturitydate' in concept_clean or 'maturity' in concept_clean:
                    inv['maturity_date'] = value
                elif 'acquisitiondate' in concept_clean or 'investmentdate' in concept_clean:
                    inv['acquisition_date'] = value
                elif 'interestrate' in concept_clean or 'statedpercentage' in concept_clean:
                    inv['interest_rate'] = value
                elif 'reference' in concept_clean and 'rate' in concept_clean:
                    inv['reference_rate'] = value
                elif 'spread' in concept_clean:
                    inv['spread'] = value
                elif 'floor' in concept_clean:
                    inv['floor_rate'] = value
                elif 'pik' in concept_clean:
                    inv['pik_rate'] = value
            
            # Store all facts as JSON
            inv['all_facts_json'] = json.dumps(fact_dict)
            inv['fact_count'] = len(facts)
            
            investments.append(inv)
        
        logger.info(f"Built {len(investments)} investment records with all facts")
        
        return {
            'ticker': ticker,
            'cik': cik,
            'accession': accession,
            'total_investments': len(investments),
            'investments': investments,
            'error': None
        }
    except Exception as e:
        logger.error(f"Error extracting {ticker}: {e}", exc_info=True)
        return {'ticker': ticker, 'error': str(e), 'investments': []}

def _extract_investment_contexts(content: str) -> Dict[str, Dict]:
    """Extract all investment contexts with InvestmentIdentifierAxis."""
    contexts = {}
    
    # Find all contexts with InvestmentIdentifierAxis
    context_pattern = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
    typed_member_pattern = re.compile(
        r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>\s*</xbrldi:typedMember>',
        re.DOTALL
    )
    
    for match in context_pattern.finditer(content):
        ctx_id = match.group(1)
        ctx_html = match.group(2)
        
        # Check if this context has InvestmentIdentifierAxis
        typed_match = typed_member_pattern.search(ctx_html)
        if not typed_match:
            continue
        
        identifier = typed_match.group(1).strip()
        
        # Extract instant date
        instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_html)
        instant = instant_match.group(1) if instant_match else None
        
        # Extract industry if present
        industry = 'Unknown'
        industry_match = re.search(
            r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>',
            ctx_html,
            re.DOTALL | re.IGNORECASE
        )
        if industry_match:
            industry_raw = industry_match.group(1).strip()
            industry = _clean_industry_name(industry_raw)
        
        # Parse identifier to extract company name and investment type
        parsed = _parse_identifier(identifier)
        
        contexts[ctx_id] = {
            'identifier': identifier,
            'company_name': parsed.get('company_name', identifier),
            'investment_type': parsed.get('investment_type', 'Unknown'),
            'industry': industry,
            'instant': instant
        }
    
    return contexts

def _parse_identifier(identifier: str) -> Dict[str, str]:
    """Parse investment identifier to extract company name and investment type."""
    # Basic parsing - can be enhanced per ticker
    res = {'company_name': identifier, 'investment_type': 'Unknown'}
    
    # Try to extract investment type patterns
    type_patterns = [
        r'(First\s+Lien[^,]*?)(?:,|$)',
        r'(Second\s+Lien[^,]*?)(?:,|$)',
        r'(Senior\s+Secured[^,]*?)(?:,|$)',
        r'(Preferred\s+Equity[^,]*?)(?:,|$)',
        r'(Common\s+Equity[^,]*?)(?:,|$)',
        r'(Term\s+Loan[^,]*?)(?:,|$)',
        r'(Revolving\s+Loan[^,]*?)(?:,|$)',
        r'(Delayed\s+Draw[^,]*?)(?:,|$)',
    ]
    
    for pattern in type_patterns:
        match = re.search(pattern, identifier, re.IGNORECASE)
        if match:
            res['investment_type'] = match.group(1).strip()
            # Remove type from company name
            res['company_name'] = re.sub(pattern, '', identifier, flags=re.IGNORECASE).strip(' ,')
            break
    
    return res

def _clean_industry_name(industry: str) -> str:
    """Clean industry name from XBRL."""
    # Remove namespace prefixes
    industry = re.sub(r'^[^:]+:', '', industry)
    # Convert to readable format
    industry = industry.replace('_', ' ').title()
    return industry

def _extract_all_facts(content: str) -> List[Dict]:
    """Extract all facts from XBRL content."""
    facts = []
    
    # Pattern 1: Standard XBRL facts
    fact_pattern = re.compile(
        r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>',
        re.DOTALL
    )
    
    for match in fact_pattern.finditer(content):
        concept = match.group(1)
        context_ref = match.group(2)
        unit_ref = match.group(3)
        value = match.group(4).strip()
        
        if not value:
            continue
        
        facts.append({
            'concept': concept,
            'contextRef': context_ref,
            'unit': unit_ref or '',
            'value': value
        })
    
    # Pattern 2: ix:nonFraction elements
    ixf_pattern = re.compile(
        r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:unitRef="([^"]*)")?[^>]*>(.*?)</ix:nonFraction>',
        re.DOTALL | re.IGNORECASE
    )
    
    for match in ixf_pattern.finditer(content):
        name = match.group(1)
        context_ref = match.group(2)
        unit_ref = match.group(3)
        html_content = match.group(4)
        
        # Extract text from HTML
        value = re.sub(r'<[^>]+>', '', html_content).strip()
        
        if not value:
            continue
        
        facts.append({
            'concept': name,
            'contextRef': context_ref,
            'unit': unit_ref or '',
            'value': value
        })
    
    return facts

def save_all_facts(results: List[Dict], output_dir: str):
    """Save all facts extraction results."""
    os.makedirs(output_dir, exist_ok=True)
    
    for result in results:
        if result.get('error'):
            logger.warning(f"Skipping {result['ticker']} due to error: {result['error']}")
            continue
        
        ticker = result['ticker']
        investments = result.get('investments', [])
        
        if not investments:
            logger.warning(f"No investments found for {ticker}")
            continue
        
        # Save detailed CSV with all facts
        output_file = os.path.join(output_dir, f'{ticker}_all_facts.csv')
        
        # Get all unique field names
        fieldnames = set()
        for inv in investments:
            fieldnames.update(inv.keys())
        
        # Prioritize common fields first
        priority_fields = [
            'context_ref', 'company_name', 'investment_type', 'industry',
            'principal_amount', 'cost_basis', 'fair_value',
            'maturity_date', 'acquisition_date',
            'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate',
            'fact_count', 'all_facts_json'
        ]
        
        fieldnames = [f for f in priority_fields if f in fieldnames] + \
                    sorted([f for f in fieldnames if f not in priority_fields])
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for inv in investments:
                row = {k: (str(v) if v is not None else '') for k, v in inv.items()}
                writer.writerow(row)
        
        logger.info(f"Saved {len(investments)} investments with all facts to {output_file}")

def main():
    """Extract all facts for specified tickers."""
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'xbrl_all_facts')
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    for ticker in TICKERS_NEED_FULL_FACTS:
        result = extract_all_facts_for_investment(ticker)
        results.append(result)
    
    # Save results
    save_all_facts(results, output_dir)
    
    # Print summary
    print("\n" + "=" * 80)
    print("ALL FACTS EXTRACTION SUMMARY")
    print("=" * 80)
    
    successful = [r for r in results if not r.get('error') and r.get('total_investments', 0) > 0]
    failed = [r for r in results if r.get('error')]
    
    print(f"\nSuccessful: {len(successful)}")
    for r in successful:
        print(f"  {r['ticker']}: {r['total_investments']} investments")
    
    if failed:
        print(f"\nFailed: {len(failed)}")
        for r in failed:
            print(f"  {r['ticker']}: {r.get('error', 'Unknown error')}")
    
    print("=" * 80)

if __name__ == '__main__':
    main()

