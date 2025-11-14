#!/usr/bin/env python3
"""
Custom GBDC (Golub Capital BDC Inc) Investment Extractor

GBDC uses XBRL primarily with HTML table enhancement for dates and rates.
"""

import logging
import os
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import csv
from collections import defaultdict

from xbrl_typed_extractor import TypedMemberExtractor, BDCExtractionResult
from flexible_table_parser import FlexibleTableParser
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class GBDCCustomExtractor:
    """Custom extractor for GBDC that uses XBRL with HTML enhancement."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.xbrl_extractor = TypedMemberExtractor(user_agent)
        self.html_parser = FlexibleTableParser(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "GBDC") -> Dict:
        """Extract investments from GBDC's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        # Get URLs
        match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
        if not match:
            raise ValueError("Could not parse accession/URLs for GBDC")
        
        accession = match.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        
        # Get HTML URL
        documents = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()), None)
        if not main_html:
            raise ValueError("Could not find HTML document")
        
        htm_url = main_html.url
        logger.info(f"XBRL URL: {txt_url}")
        logger.info(f"HTML URL: {htm_url}")
        
        return self.extract_from_filing(txt_url, htm_url, "Golub Capital BDC Inc", cik, ticker)
    
    def extract_from_filing(self, txt_url: str, htm_url: str, company_name: str, cik: str, ticker: str = "GBDC") -> Dict:
        """Extract complete GBDC investment data from XBRL (primary) and HTML (enhancement)."""
        
        logger.info(f"Starting GBDC extraction from XBRL...")
        
        # Extract from XBRL (primary source)
        xbrl_result = self.xbrl_extractor.extract_from_url(txt_url, company_name, cik)
        logger.info(f"XBRL extraction: {xbrl_result.total_investments} investments")
        
        # Convert XBRL investments to dict format
        investments = []
        for inv in xbrl_result.investments:
            investments.append({
                'company_name': inv.get('company_name', ''),
                'business_description': inv.get('business_description', ''),
                'investment_type': inv.get('investment_type', ''),
                'industry': inv.get('industry', ''),
                'acquisition_date': inv.get('acquisition_date'),
                'maturity_date': inv.get('maturity_date'),
                'principal_amount': inv.get('principal_amount'),
                'cost': inv.get('cost_basis'),
                'fair_value': inv.get('fair_value'),
                'interest_rate': inv.get('interest_rate'),
                'reference_rate': inv.get('reference_rate'),
                'spread': inv.get('spread'),
                'floor_rate': inv.get('floor_rate'),
                'pik_rate': inv.get('pik_rate'),
                'shares_units': inv.get('shares_units'),
                'percent_net_assets': inv.get('percent_net_assets')
            })
        
        # Try to enhance with HTML data if available
        try:
            html_investments = self.html_parser.parse_html_filing(htm_url)
            if html_investments:
                logger.info(f"Found {len(html_investments)} investments in HTML, attempting to merge...")
                investments = self._merge_data(investments, html_investments)
        except Exception as e:
            logger.warning(f"HTML parsing failed, using XBRL only: {e}")
        
        # Recalculate totals
        total_principal = sum(inv.get('principal_amount') or 0 for inv in investments)
        total_cost = sum(inv.get('cost') or 0 for inv in investments)
        total_fair_value = sum(inv.get('fair_value') or 0 for inv in investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f'{ticker}_Golub_Capital_BDC_Inc_investments.csv')
        
        self._save_to_csv(investments, output_file)
        logger.info(f"Saved {len(investments)} investments to {output_file}")
        
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'investments': investments,
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _merge_data(self, xbrl_investments: List[Dict], html_investments: List[Dict]) -> List[Dict]:
        """Merge XBRL and HTML data, preferring HTML for descriptive fields."""
        # Simple matching by company name and investment type
        # This is a basic implementation - can be enhanced with fuzzy matching
        
        matched_html = set()
        
        for xbrl_inv in xbrl_investments:
            xbrl_company = self._normalize_company_name(xbrl_inv.get('company_name', ''))
            xbrl_type = xbrl_inv.get('investment_type', '').strip()
            
            # Try to find matching HTML investment
            for html_inv in html_investments:
                if id(html_inv) in matched_html:
                    continue
                
                html_company = self._normalize_company_name(html_inv.get('company_name', ''))
                html_type = html_inv.get('investment_type', '').strip()
                
                # Match by company name (fuzzy) and investment type
                if self._companies_match(xbrl_company, html_company):
                    # Check if investment types are compatible
                    if self._types_compatible(xbrl_type, html_type):
                        # Merge: HTML data overrides XBRL for descriptive fields
                        if html_inv.get('maturity_date'):
                            xbrl_inv['maturity_date'] = html_inv.get('maturity_date')
                        if html_inv.get('acquisition_date'):
                            xbrl_inv['acquisition_date'] = html_inv.get('acquisition_date')
                        if html_inv.get('interest_rate'):
                            xbrl_inv['interest_rate'] = html_inv.get('interest_rate')
                        if html_inv.get('reference_rate'):
                            xbrl_inv['reference_rate'] = html_inv.get('reference_rate')
                        if html_inv.get('spread'):
                            xbrl_inv['spread'] = html_inv.get('spread')
                        if html_inv.get('pik_rate'):
                            xbrl_inv['pik_rate'] = html_inv.get('pik_rate')
                        if html_inv.get('business_description'):
                            xbrl_inv['business_description'] = html_inv.get('business_description')
                        if html_inv.get('industry'):
                            xbrl_inv['industry'] = html_inv.get('industry')
                        
                        matched_html.add(id(html_inv))
                        break
        
        return xbrl_investments
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for matching."""
        if not name:
            return ''
        # Remove common suffixes and normalize
        name = re.sub(r'\s+(LLC|Inc\.?|Corp\.?|L\.P\.?|LP|Ltd\.?|Limited|Holdings|Holdco)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[,\s]+', ' ', name).strip().lower()
        return name
    
    def _companies_match(self, name1: str, name2: str) -> bool:
        """Check if two company names match (fuzzy)."""
        if not name1 or not name2:
            return False
        # Exact match
        if name1 == name2:
            return True
        # One contains the other (for cases like "Company" vs "Company, LLC")
        if name1 in name2 or name2 in name1:
            return True
        # Check if they share significant words
        words1 = set(name1.split())
        words2 = set(name2.split())
        if len(words1) > 0 and len(words2) > 0:
            common = words1.intersection(words2)
            if len(common) >= min(2, len(words1), len(words2)):
                return True
        return False
    
    def _types_compatible(self, type1: str, type2: str) -> bool:
        """Check if investment types are compatible."""
        if not type1 or not type2:
            return True  # Allow matching if one is missing
        type1_lower = type1.lower()
        type2_lower = type2.lower()
        # Exact match
        if type1_lower == type2_lower:
            return True
        # Check for common keywords
        debt_keywords = ['debt', 'loan', 'note', 'lien', 'secured']
        equity_keywords = ['equity', 'stock', 'warrant', 'preferred', 'common']
        
        type1_is_debt = any(k in type1_lower for k in debt_keywords)
        type2_is_debt = any(k in type2_lower for k in debt_keywords)
        type1_is_equity = any(k in type1_lower for k in equity_keywords)
        type2_is_equity = any(k in type2_lower for k in equity_keywords)
        
        # Don't match debt with equity
        if (type1_is_debt and type2_is_equity) or (type1_is_equity and type2_is_debt):
            return False
        
        return True
    
    def _save_to_csv(self, investments: List[Dict], output_file: str):
        """Save investments to CSV file."""
        fieldnames = [
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost',
            'fair_value', 'interest_rate', 'reference_rate', 'spread', 'floor_rate',
            'pik_rate'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for inv in investments:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(inv.get('investment_type', ''))
                standardized_industry = standardize_industry(inv.get('industry', ''))
                standardized_ref_rate = standardize_reference_rate(inv.get('reference_rate'))
                
                writer.writerow({
                    'company_name': inv.get('company_name', ''),
                    'industry': standardized_industry,
                    'business_description': inv.get('business_description', ''),
                    'investment_type': standardized_inv_type,
                    'acquisition_date': inv.get('acquisition_date'),
                    'maturity_date': inv.get('maturity_date'),
                    'principal_amount': inv.get('principal_amount'),
                    'cost': inv.get('cost'),
                    'fair_value': inv.get('fair_value'),
                    'interest_rate': inv.get('interest_rate'),
                    'reference_rate': standardized_ref_rate,
                    'spread': inv.get('spread'),
                    'floor_rate': inv.get('floor_rate'),
                    'pik_rate': inv.get('pik_rate'),
                })


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = GBDCCustomExtractor()
    try:
        result = extractor.extract_from_ticker("GBDC")
        print(f"\n✓ Successfully extracted {result.get('total_investments', 0)} investments")
        print(f"  Total Principal: ${result.get('total_principal', 0):,.0f}")
        print(f"  Total Cost: ${result.get('total_cost', 0):,.0f}")
        print(f"  Total Fair Value: ${result.get('total_fair_value', 0):,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()

