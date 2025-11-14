#!/usr/bin/env python3
"""
Custom ARCC (Ares Capital Corporation) Investment Extractor

ARCC uses XBRL for investment data with enhanced fact extraction.
"""

import logging
import os
import re
from typing import List, Dict, Optional
import csv
from collections import defaultdict
import requests

from xbrl_typed_extractor import TypedMemberExtractor
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class ARCCCustomExtractor:
    """Custom extractor for ARCC that uses XBRL with enhanced fact extraction."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.user_agent = user_agent
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.xbrl_extractor = TypedMemberExtractor(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "ARCC") -> Dict:
        """Extract investments from ARCC's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        # Get XBRL URL
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        
        logger.info(f"Extracting from XBRL: {txt_url}")
        xbrl_result = self.xbrl_extractor.extract_from_url(txt_url, "Ares Capital Corporation", cik)
        
        # Convert to dict format
        investments = []
        for inv in xbrl_result.investments:
            investments.append({
                'company_name': inv.get('company_name', ''),
                'industry': inv.get('industry', 'Unknown'),
                'business_description': inv.get('business_description', ''),
                'investment_type': inv.get('investment_type', 'Unknown'),
                'acquisition_date': inv.get('acquisition_date'),
                'maturity_date': inv.get('maturity_date'),
                'principal_amount': inv.get('principal_amount'),
                'cost': inv.get('cost_basis'),
                'fair_value': inv.get('fair_value'),
                'interest_rate': inv.get('interest_rate'),
                'reference_rate': inv.get('reference_rate'),
                'spread': inv.get('basis_spread'),
                'floor_rate': inv.get('floor_rate'),
                'pik_rate': inv.get('pik_rate'),
            })
        
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
        output_file = os.path.join(output_dir, 'ARCC_Ares_Capital_Corporation_investments.csv')
        
        self._save_to_csv(investments, output_file)
        logger.info(f"Saved {len(investments)} investments to {output_file}")
        
        return {
            'company_name': 'Ares Capital Corporation',
            'cik': cik,
            'total_investments': len(investments),
            'investments': investments,
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
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
    
    extractor = ARCCCustomExtractor()
    try:
        result = extractor.extract_from_ticker("ARCC")
        print(f"\n✓ Successfully extracted {result.get('total_investments', 0)} investments")
        print(f"  Total Principal: ${result.get('total_principal', 0):,.0f}")
        print(f"  Total Cost: ${result.get('total_cost', 0):,.0f}")
        print(f"  Total Fair Value: ${result.get('total_fair_value', 0):,.0f}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
