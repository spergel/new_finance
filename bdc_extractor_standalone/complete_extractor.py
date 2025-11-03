#!/usr/bin/env python3
"""
Complete BDC Investment Extractor

Step 1: Extract investments from XBRL (company names, types, financial values)
Step 2: Parse HTML table to get industries, dates, and other details
Step 3: Merge by matching company name + investment type
"""

import os
import json
import logging
import re
import requests
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
from bs4 import BeautifulSoup

from xbrl_typed_extractor import TypedMemberExtractor, BDCInvestment, BDCExtractionResult

logger = logging.getLogger(__name__)

class CompleteBDCExtractor:
    """Complete extractor combining XBRL and HTML parsing."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        """Initialize the extractor."""
        self.headers = {'User-Agent': user_agent}
        self.xbrl_extractor = TypedMemberExtractor(user_agent)
    
    def extract_from_filing(self, txt_url: str, htm_url: str, company_name: str = None, cik: str = None) -> BDCExtractionResult:
        """
        Extract complete BDC investment data.
        
        Args:
            txt_url: URL to the .txt file (contains XBRL)
            htm_url: URL to the .htm file (contains HTML tables)
            company_name: Company name
            cik: Company CIK
        """
        
        logger.info(f"Starting complete extraction...")
        logger.info(f"XBRL source: {txt_url}")
        logger.info(f"HTML source: {htm_url}")
        
        # Step 1: Extract from XBRL
        xbrl_result = self.xbrl_extractor.extract_from_url(txt_url, company_name, cik)
        logger.info(f"XBRL extraction: {xbrl_result.total_investments} investments")
        
        # Step 2: Parse HTML table
        html_data = self._parse_html_table(htm_url)
        logger.info(f"HTML extraction: {len(html_data)} entries")
        
        # Step 3: Merge data
        merged_investments = self._merge_data(xbrl_result.investments, html_data)
        logger.info(f"Merged: {len(merged_investments)} investments")
        
        # Recalculate breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in merged_investments:
            industry_breakdown[inv['industry']] += 1
            investment_type_breakdown[inv['investment_type']] += 1
        
        # Create result
        result = BDCExtractionResult(
            company_name=company_name or "Unknown BDC",
            cik=cik or "",
            filing_date=xbrl_result.filing_date,
            filing_url=txt_url,
            extraction_date=datetime.now().isoformat(),
            total_investments=len(merged_investments),
            total_principal=sum(inv.get('principal_amount') or 0 for inv in merged_investments),
            total_cost=sum(inv.get('cost_basis') or 0 for inv in merged_investments),
            total_fair_value=sum(inv.get('fair_value') or 0 for inv in merged_investments),
            investments=merged_investments,
            industry_breakdown=dict(industry_breakdown),
            investment_type_breakdown=dict(investment_type_breakdown)
        )
        
        return result
    
    def _parse_html_table(self, htm_url: str) -> List[Dict]:
        """Parse the HTML investment schedule table."""
        
        logger.info(f"Parsing HTML from: {htm_url}")
        response = requests.get(htm_url, headers=self.headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        html_entries = []
        current_industry = "Unknown"
        
        # Find tables
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                
                # Check for industry header
                first_cell_text = cells[0].get_text(strip=True)
                
                # Industry headers are typically bold and contain industry keywords
                if self._is_industry_header(first_cell_text, row):
                    current_industry = self._clean_industry_name(first_cell_text)
                    logger.debug(f"Found industry: {current_industry}")
                    continue
                
                # Check if this is an investment row
                if self._is_investment_row(cells, first_cell_text):
                    entry = self._parse_investment_row(cells, current_industry)
                    if entry:
                        html_entries.append(entry)
        
        return html_entries
    
    def _is_industry_header(self, text: str, row) -> bool:
        """Check if this is an industry header row."""
        
        # Industry headers are section headers, usually bold
        # They don't have many cells (unlike data rows)
        cells = row.find_all(['td', 'th'])
        
        # Industry headers typically span columns or are in the first cell only
        if len(cells) > 5:
            return False  # Too many cells to be a header
        
        # Check for industry keywords
        industry_keywords = [
            'Software and Services', 'Healthcare', 'Technology', 'Financial Services',
            'Commercial and Professional Services', 'Insurance', 'Consumer',
            'Industrial', 'Energy', 'Materials', 'Transportation', 'Food and Beverage',
            'Telecommunications', 'Media', 'Entertainment', 'Utilities',
            'Pharmaceuticals', 'Biotechnology', 'Life Sciences'
        ]
        
        return any(keyword in text for keyword in industry_keywords) and not text.startswith('Total')
    
    def _clean_industry_name(self, text: str) -> str:
        """Clean up industry name."""
        # Remove trailing numbers and special characters
        text = re.sub(r'\s+\d+.*$', '', text)
        return text.strip()
    
    def _is_investment_row(self, cells: List, first_cell_text: str) -> bool:
        """Check if this row contains investment data."""
        
        if len(cells) < 8:  # Investment rows typically have many columns
            return False
        
        # Skip if starts with Total, blank, or common headers
        if not first_cell_text:
            return False
        if first_cell_text.startswith('Total'):
            return False
        if first_cell_text.lower() in ['company', 'investment', 'business description']:
            return False
        
        # Investment rows usually have company indicators
        company_indicators = ['LLC', 'Inc.', 'Corp', 'Ltd', 'Holdings', 'LP', 'Limited', 'L.P.']
        has_company_indicator = any(ind in first_cell_text for ind in company_indicators)
        
        # Or they have numbers (footnote references like (13), (4), etc.)
        has_footnote = re.search(r'\(\d+\)', first_cell_text)
        
        return has_company_indicator or has_footnote
    
    def _parse_investment_row(self, cells: List, industry: str) -> Optional[Dict]:
        """Parse an investment row from the HTML table."""
        
        try:
            # For ARES format (adjust column indices for other BDCs):
            # Col 0: Company name (with footnotes)
            # Col 1: Business description  
            # Col 2: Investment type
            # Col 3: Coupon rate
            # Col 4: Reference rate
            # Col 5: Spread
            # Col 6: Acquisition date
            # Col 7: Maturity date
            # Col 8: Shares/Units
            # Col 9: Principal
            # Col 10: Amortized Cost
            # Col 11: Fair Value
            # Col 12: % of Net Assets
            
            company_name_raw = cells[0].get_text(strip=True) if len(cells) > 0 else ""
            business_desc = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            investment_type = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            
            # Clean company name (remove footnotes)
            company_name = re.sub(r'\s*\(\d+\)', '', company_name_raw).strip()
            
            # Extract dates
            acquisition_date = cells[6].get_text(strip=True) if len(cells) > 6 else ""
            maturity_date = cells[7].get_text(strip=True) if len(cells) > 7 else ""
            
            # Clean dates (remove dashes which mean N/A)
            if acquisition_date == '—' or not acquisition_date:
                acquisition_date = None
            if maturity_date == '—' or not maturity_date:
                maturity_date = None
            
            # Only return if we have a company name and investment type
            if not company_name or not investment_type:
                return None
            
            return {
                'company_name': company_name,
                'business_description': business_desc,
                'investment_type': investment_type,
                'industry': industry,
                'acquisition_date': acquisition_date,
                'maturity_date': maturity_date
            }
        
        except Exception as e:
            logger.warning(f"Failed to parse row: {e}")
            return None
    
    def _merge_data(self, xbrl_investments: List[Dict], html_data: List[Dict]) -> List[Dict]:
        """Merge XBRL and HTML data by matching company name + investment type."""
        
        # Create lookup by normalized company name + investment type
        html_lookup = {}
        for entry in html_data:
            key = self._create_match_key(entry['company_name'], entry['investment_type'])
            if key:
                # Store all HTML entries for this key (there might be multiple)
                if key not in html_lookup:
                    html_lookup[key] = []
                html_lookup[key].append(entry)
        
        logger.info(f"HTML lookup created with {len(html_lookup)} unique keys")
        
        # Debug: Show some HTML keys
        if html_lookup:
            logger.info("Sample HTML keys:")
            for i, key in enumerate(list(html_lookup.keys())[:5]):
                logger.info(f"  {i+1}. {key}")
        
        # Debug: Show some XBRL keys
        if xbrl_investments:
            logger.info("Sample XBRL keys:")
            for i, inv in enumerate(xbrl_investments[:5]):
                key = self._create_match_key(inv['company_name'], inv['investment_type'])
                logger.info(f"  {i+1}. {key}")
        
        # Merge
        merged = []
        matched = 0
        
        for inv in xbrl_investments:
            key = self._create_match_key(inv['company_name'], inv['investment_type'])
            
            if key in html_lookup:
                # Take the first match (there might be multiple, but they should have same industry/dates)
                html_entry = html_lookup[key][0]
                
                # Merge HTML data into XBRL data
                inv['industry'] = html_entry.get('industry', 'Unknown')
                inv['acquisition_date'] = html_entry.get('acquisition_date')
                inv['maturity_date'] = html_entry.get('maturity_date')
                inv['business_description'] = html_entry.get('business_description')
                matched += 1
            
            merged.append(inv)
        
        match_rate = (matched / len(xbrl_investments) * 100) if xbrl_investments else 0
        logger.info(f"Matched {matched}/{len(xbrl_investments)} investments ({match_rate:.1f}%)")
        
        return merged
    
    def _create_match_key(self, company_name: str, investment_type: str) -> str:
        """Create a normalized key for matching XBRL and HTML data."""
        
        # Normalize company name
        company = self._normalize_text(company_name)
        
        # Normalize investment type
        inv_type = self._normalize_investment_type(investment_type)
        
        return f"{company}|{inv_type}"
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching."""
        if not text:
            return ""
        
        # Lowercase
        text = text.lower()
        
        # Remove punctuation and extra spaces
        text = re.sub(r'[^\w\s]', '', text)
        text = ' '.join(text.split())
        
        return text
    
    def _normalize_investment_type(self, inv_type: str) -> str:
        """Normalize investment type for matching."""
        if not inv_type:
            return "unknown"
        
        # Normalize variations
        inv_type = inv_type.lower()
        inv_type = re.sub(r'[^\w\s]', '', inv_type)
        inv_type = ' '.join(inv_type.split())
        
        # Remove trailing numbers like "1", "2", etc. (these are sequence numbers)
        inv_type = re.sub(r'\s+\d+$', '', inv_type)
        
        return inv_type
    
    def save_results(self, result: BDCExtractionResult, output_dir: str = 'output'):
        """Save extraction results."""
        self.xbrl_extractor.save_results(result, output_dir)


def main():
    """Test the complete extractor."""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    extractor = CompleteBDCExtractor()
    
    # ARES Capital Corp URLs
    cik = "1287750"
    accession = "000128775025000046"
    txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/0001287750-25-000046.txt"
    htm_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/arcc-20250930.htm"
    
    try:
        result = extractor.extract_from_filing(
            txt_url=txt_url,
            htm_url=htm_url,
            company_name="Ares Capital Corp",
            cik=cik
        )
        
        print(f"\n✅ Successfully extracted {result.total_investments} investments")
        print(f"   Filing Date: {result.filing_date}")
        print(f"   Total Cost: ${result.total_cost:,.0f}")
        print(f"   Total Fair Value: ${result.total_fair_value:,.0f}")
        
        print(f"\n📊 Industry Breakdown (Top 10):")
        for industry, count in sorted(result.industry_breakdown.items(), key=lambda x: -x[1])[:10]:
            print(f"   {industry}: {count}")
        
        print(f"\n🏦 Investment Type Breakdown (Top 10):")
        for inv_type, count in sorted(result.investment_type_breakdown.items(), key=lambda x: -x[1])[:10]:
            print(f"   {inv_type}: {count}")
        
        # Show sample investments
        print(f"\n📋 Sample Investments (First 5):")
        for i, inv in enumerate(result.investments[:5]):
            print(f"\n   {i+1}. {inv['company_name']}")
            print(f"      Industry: {inv['industry']}")
            print(f"      Type: {inv['investment_type']}")
            business_desc = inv.get('business_description') or 'N/A'
            print(f"      Business: {business_desc[:60] if len(business_desc) > 60 else business_desc}{'...' if len(business_desc) > 60 else ''}")
            print(f"      Acquisition: {inv.get('acquisition_date') or 'N/A'}")
            print(f"      Maturity: {inv.get('maturity_date') or 'N/A'}")
            if inv.get('fair_value'):
                print(f"      Fair Value: ${inv['fair_value']:,.0f}")
        
        # Data quality
        print(f"\n📈 Data Quality:")
        total = result.total_investments
        with_industry = sum(1 for inv in result.investments if inv['industry'] != 'Unknown')
        with_type = sum(1 for inv in result.investments if inv['investment_type'] != 'Unknown')
        with_acquisition = sum(1 for inv in result.investments if inv.get('acquisition_date'))
        with_maturity = sum(1 for inv in result.investments if inv.get('maturity_date'))
        with_fair_value = sum(1 for inv in result.investments if inv.get('fair_value'))
        
        print(f"   Industry: {with_industry}/{total} ({100*with_industry/total if total else 0:.1f}%)")
        print(f"   Investment Type: {with_type}/{total} ({100*with_type/total if total else 0:.1f}%)")
        print(f"   Acquisition Date: {with_acquisition}/{total} ({100*with_acquisition/total if total else 0:.1f}%)")
        print(f"   Maturity Date: {with_maturity}/{total} ({100*with_maturity/total if total else 0:.1f}%)")
        print(f"   Fair Value: {with_fair_value}/{total} ({100*with_fair_value/total if total else 0:.1f}%)")
        
        # Save
        extractor.save_results(result)
        print(f"\n💾 Results saved to output/")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

