#!/usr/bin/env python3
"""
BDC Investment Extractor

Extracts investment data from BDC 10-Q filings with support for different table formats.
Handles both XBRL-heavy formats (like TPVG) and traditional table formats (like ARES).
"""

import os
import json
import logging
import re
from typing import List, Dict, Optional, Any
from datetime import datetime, date
from bs4 import BeautifulSoup
import requests
import csv
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class InvestmentType(str, Enum):
    """Types of BDC investments."""
    FIRST_LIEN_SENIOR_SECURED_LOAN = "first_lien_senior_secured_loan"
    SECOND_LIEN_SENIOR_SECURED_LOAN = "second_lien_senior_secured_loan"
    SENIOR_SUBORDINATED_LOAN = "senior_subordinated_loan"
    REVOLVER = "revolver"
    CONVERTIBLE_NOTE = "convertible_note"
    PREFERRED_STOCK = "preferred_stock"
    COMMON_STOCK = "common_stock"
    LIMITED_PARTNERSHIP_INTEREST = "limited_partnership_interest"
    WARRANT = "warrant"
    UNKNOWN = "unknown"

@dataclass
class BDCInvestment:
    """Represents a single BDC investment."""
    company_name: str
    business_description: Optional[str] = None
    investment_type: str = "unknown"
    coupon_rate: Optional[float] = None
    reference_rate: Optional[str] = None
    spread: Optional[float] = None
    acquisition_date: Optional[str] = None
    maturity_date: Optional[str] = None
    shares_units: Optional[str] = None
    principal_amount: Optional[float] = None
    amortized_cost: Optional[float] = None
    fair_value: Optional[float] = None
    percent_of_net_assets: Optional[float] = None
    industry: Optional[str] = None
    notes: Optional[str] = None

@dataclass
class BDCExtractionResult:
    """Result of BDC investment extraction."""
    company_name: str
    extraction_date: str
    total_investments: int
    total_principal: float
    total_cost: float
    total_fair_value: float
    investments: List[BDCInvestment]
    industry_breakdown: Dict[str, int]
    investment_type_breakdown: Dict[str, int]

class BDCInvestmentExtractor:
    """Main class for extracting BDC investment data from SEC filings."""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'SEC-API-Client/1.0 (your-email@domain.com)'
        }
    
    def extract_bdc_investments(self, filing_url: str, company_name: str = None) -> BDCExtractionResult:
        """Extract BDC investment data from a 10-Q filing."""
        
        logger.info(f"Extracting BDC investments from: {filing_url}")
        
        try:
            # Fetch the filing
            response = requests.get(filing_url, headers=self.headers)
            response.raise_for_status()
            
            # Find the investment table section
            table_section = self._find_investment_table_section(response.text)
            if not table_section:
                raise ValueError("Investment table section not found")
            
            # Parse the table section
            soup = BeautifulSoup(table_section, 'html.parser')
            
            # Determine table format and extract accordingly
            if self._is_xbrl_heavy_format(soup):
                logger.info("Detected XBRL-heavy format (like TPVG)")
                investments = self._extract_xbrl_format(soup)
            else:
                logger.info("Detected traditional table format (like ARES)")
                investments = self._extract_traditional_format(soup)
            
            # Calculate totals and breakdowns
            total_principal = sum(inv.principal_amount or 0 for inv in investments)
            total_cost = sum(inv.amortized_cost or 0 for inv in investments)
            total_fair_value = sum(inv.fair_value or 0 for inv in investments)
            
            # Create industry and investment type breakdowns
            industry_breakdown = {}
            investment_type_breakdown = {}
            
            for inv in investments:
                industry = inv.industry or "Unknown"
                inv_type = inv.investment_type or "Unknown"
                
                industry_breakdown[industry] = industry_breakdown.get(industry, 0) + 1
                investment_type_breakdown[inv_type] = investment_type_breakdown.get(inv_type, 0) + 1
            
            return BDCExtractionResult(
                company_name=company_name or "Unknown BDC",
                extraction_date=datetime.now().isoformat(),
                total_investments=len(investments),
                total_principal=total_principal,
                total_cost=total_cost,
                total_fair_value=total_fair_value,
                investments=investments,
                industry_breakdown=industry_breakdown,
                investment_type_breakdown=investment_type_breakdown
            )
            
        except Exception as e:
            logger.error(f"Failed to extract BDC investments: {str(e)}")
            raise
    
    def _find_investment_table_section(self, text: str) -> Optional[str]:
        """Find the investment table section in the filing text."""
        
        # Look for various investment table markers
        markers = [
            'CONSOLIDATED SCHEDULE OF INVESTMENTS',
            'CONDENSED CONSOLIDATED SCHEDULE OF INVESTMENTS',
            'SCHEDULE OF INVESTMENTS',
            'INVESTMENT PORTFOLIO',
            'PORTFOLIO OF INVESTMENTS',
            'CONDENSED SCHEDULE OF INVESTMENTS',
            'CONSOLIDATED PORTFOLIO OF INVESTMENTS'
        ]
        
        for marker in markers:
            if marker in text:
                start_idx = text.find(marker)
                
                # Find end of table (look for next major section)
                end_markers = [
                    'Total Investments', 'Total Debt Investments', 'Total Equity Investments',
                    'See accompanying notes', 'NOTES TO CONSOLIDATED FINANCIAL STATEMENTS',
                    'CONSOLIDATED STATEMENTS OF OPERATIONS'
                ]
                
                end_idx = len(text)
                for end_marker in end_markers:
                    marker_idx = text.find(end_marker, start_idx)
                    if marker_idx != -1:
                        end_idx = min(end_idx, marker_idx + 2000)
                
                return text[start_idx:end_idx]
        
        # If no traditional markers found, check if it's XBRL-heavy
        xbrl_count = text.count('ix:nonFraction')
        if xbrl_count > 100:  # If many XBRL elements, assume it's XBRL format
            logger.info(f"Detected XBRL-heavy format with {xbrl_count} elements")
            # For XBRL format, return the entire text as the "section"
            return text
        
        return None
    
    def _is_xbrl_heavy_format(self, soup: BeautifulSoup) -> bool:
        """Determine if this is an XBRL-heavy format (like TPVG) or traditional format (like ARES)."""
        
        # Count XBRL elements
        xbrl_elements = soup.find_all(attrs={'name': True})
        
        # If we have many XBRL elements, it's likely XBRL-heavy format
        if len(xbrl_elements) > 50:
            return True
        
        # Check for traditional table structure
        tables = soup.find_all('table')
        if tables:
            # Look for traditional table headers
            for table in tables:
                headers = table.find_all(['th', 'td'])
                header_text = ' '.join([h.get_text(strip=True) for h in headers[:10]])
                
                if any(term in header_text.lower() for term in ['company', 'business description', 'investment', 'coupon']):
                    return False
        
        return True
    
    def _extract_xbrl_format(self, soup: BeautifulSoup) -> List[BDCInvestment]:
        """Extract investments from XBRL-heavy format (like TPVG)."""
        
        investments = []
        
        # Find all XBRL elements with investment data
        xbrl_elements = soup.find_all(attrs={'name': True})
        
        # Group by context to find related data
        context_groups = {}
        for elem in xbrl_elements:
            context = elem.get('contextref', '')
            name = elem.get('name', '')
            value = elem.get_text(strip=True)
            
            if context and context.startswith('c-'):
                if context not in context_groups:
                    context_groups[context] = {}
                context_groups[context][name] = value
        
        # Build industry mapping
        industry_mapping = self._build_industry_mapping(soup, context_groups)
        
        # Process each context group
        for context, data in context_groups.items():
            if not context or not context.startswith('c-'):
                continue
            
            # Extract investment details
            investment = BDCInvestment(
                company_name=self._find_company_name_for_context(soup, context),
                investment_type=self._extract_investment_type_xbrl(soup, context),
                acquisition_date=self._extract_date_xbrl(soup, context, 'acquisition'),
                maturity_date=self._extract_date_xbrl(soup, context, 'maturity'),
                principal_amount=self._extract_amount(data, 'us-gaap:InvestmentOwnedBalancePrincipalAmount'),
                amortized_cost=self._extract_amount(data, 'us-gaap:InvestmentOwnedAtCost'),
                fair_value=self._extract_amount(data, 'us-gaap:InvestmentOwnedAtFairValue'),
                coupon_rate=self._extract_rate(data, 'us-gaap:InvestmentInterestRate'),
                spread=self._extract_rate(data, 'us-gaap:InvestmentBasisSpreadVariableRate'),
                industry=industry_mapping.get(context, 'Unknown')
            )
            
            # Only add if we have meaningful data
            if investment.principal_amount or investment.amortized_cost or investment.fair_value:
                investments.append(investment)
        
        return investments
    
    def _extract_traditional_format(self, soup: BeautifulSoup) -> List[BDCInvestment]:
        """Extract investments from traditional table format (like ARES)."""
        
        investments = []
        current_industry = "Unknown"
        
        # Find all table rows
        rows = soup.find_all('tr')
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            # Check if this is an industry header row
            row_text = row.get_text(strip=True)
            if self._is_industry_header(row_text):
                current_industry = self._extract_industry_from_header(row_text)
                continue
            
            # Check if this is a company/investment row
            if self._is_investment_row(cells):
                investment = self._parse_investment_row(cells, current_industry)
                if investment:
                    investments.append(investment)
        
        return investments
    
    def _is_industry_header(self, text: str) -> bool:
        """Check if a row is an industry header."""
        
        industry_indicators = [
            'Software and Services', 'Healthcare', 'Technology', 'Financial Services',
            'Consumer', 'Industrial', 'Energy', 'Real Estate', 'Aerospace',
            'Business Applications', 'Communication', 'Database', 'E-Commerce',
            'Aerospace & Defense', 'Air Freight & Logistics', 'Auto Components',
            'Biotechnology', 'Building Products', 'Chemicals', 'Commercial Services & Supplies',
            'Construction & Engineering', 'Consumer Staples Distribution & Retail',
            'Containers & Packaging', 'Distributors', 'First Lien Debt'
        ]
        
        return any(indicator in text for indicator in industry_indicators)
    
    def _extract_industry_from_header(self, text: str) -> str:
        """Extract industry name from header text."""
        
        # Clean up the text and return the industry name
        return text.strip()
    
    def _is_investment_row(self, cells: List) -> bool:
        """Check if a row contains investment data."""
        
        if len(cells) < 3:
            return False
        
        # Look for company name patterns
        first_cell = cells[0].get_text(strip=True)
        
        # Skip empty rows, headers, and totals
        if not first_cell or first_cell.startswith('Total') or first_cell.startswith('Company') or first_cell.startswith('Investments'):
            return False
        
        # Look for company name patterns (usually contains LLC, Inc., Corp, etc.)
        company_indicators = ['LLC', 'Inc.', 'Corp', 'Ltd', 'Holdings', 'Group', 'AB', 'LP']
        return any(indicator in first_cell for indicator in company_indicators)
    
    def _parse_investment_row(self, cells: List, industry: str) -> Optional[BDCInvestment]:
        """Parse a single investment row from traditional format."""
        
        try:
            # Extract data from cells (adjust indices based on actual table structure)
            company_name = cells[0].get_text(strip=True) if len(cells) > 0 else ""
            business_description = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            investment_type = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            
            # Extract financial data
            principal = self._parse_amount(cells[9].get_text(strip=True)) if len(cells) > 9 else None
            cost = self._parse_amount(cells[10].get_text(strip=True)) if len(cells) > 10 else None
            fair_value = self._parse_amount(cells[11].get_text(strip=True)) if len(cells) > 11 else None
            
            # Extract dates
            acquisition_date = cells[6].get_text(strip=True) if len(cells) > 6 else ""
            maturity_date = cells[7].get_text(strip=True) if len(cells) > 7 else ""
            
            # Extract rates
            coupon_rate = self._parse_rate(cells[3].get_text(strip=True)) if len(cells) > 3 else None
            spread = self._parse_rate(cells[5].get_text(strip=True)) if len(cells) > 5 else None
            
            return BDCInvestment(
                company_name=company_name,
                business_description=business_description,
                investment_type=self._classify_investment_type(investment_type),
                coupon_rate=coupon_rate,
                spread=spread,
                acquisition_date=acquisition_date,
                maturity_date=maturity_date,
                principal_amount=principal,
                amortized_cost=cost,
                fair_value=fair_value,
                industry=industry
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse investment row: {str(e)}")
            return None
    
    def _classify_investment_type(self, investment_text: str) -> str:
        """Classify investment type from description."""
        
        if not investment_text:
            return "unknown"
        
        text_lower = investment_text.lower()
        
        if 'first lien senior secured loan' in text_lower:
            return "first_lien_senior_secured_loan"
        elif 'second lien senior secured loan' in text_lower:
            return "second_lien_senior_secured_loan"
        elif 'senior subordinated loan' in text_lower:
            return "senior_subordinated_loan"
        elif 'revolver' in text_lower or 'revolving' in text_lower:
            return "revolver"
        elif 'convertible note' in text_lower:
            return "convertible_note"
        elif 'preferred stock' in text_lower or 'preferred shares' in text_lower:
            return "preferred_stock"
        elif 'common stock' in text_lower or 'common shares' in text_lower:
            return "common_stock"
        elif 'limited partnership' in text_lower or 'partnership interest' in text_lower:
            return "limited_partnership_interest"
        elif 'warrant' in text_lower:
            return "warrant"
        else:
            return "unknown"
    
    def _parse_amount(self, text: str) -> Optional[float]:
        """Parse monetary amount from text."""
        
        if not text or text == '—':
            return None
        
        # Remove currency symbols and commas
        cleaned = re.sub(r'[$,]', '', text)
        
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    def _parse_rate(self, text: str) -> Optional[float]:
        """Parse interest rate from text."""
        
        if not text or text == '—':
            return None
        
        # Extract percentage
        match = re.search(r'(\d+\.?\d*)%', text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        
        return None
    
    def _build_industry_mapping(self, soup: BeautifulSoup, context_groups: Dict[str, Dict[str, str]]) -> Dict[str, str]:
        """Build a mapping of context to industry by analyzing table structure."""
        
        industry_mapping = {}
        
        # Industry headers to look for
        industry_headers = [
            'Aerospace and Defense', 'Business Applications Software', 
            'Business Products and Services', 'Business/Productivity Software',
            'Consumer Non-Durables', 'Real Estate Services', 'Shopping Facilitators',
            'Consumer Services', 'Healthcare Technology', 'Financial Services',
            'Technology Hardware', 'Software', 'Media and Entertainment',
            'Consumer Products and Services', 'Communication Software',
            'Consumer Retail', 'Database Software', 'E-Commerce - Clothing and Accessories',
            'Entertainment', 'Financial Institution and Services', 'Healthcare Technology',
            'Information Services (B2C)', 'Insurance', 'Real Estate Services'
        ]
        
        # Find all table rows
        rows = soup.find_all('tr')
        current_industry = "Unknown"
        
        for row in rows:
            text = row.get_text(strip=True)
            
            # Check if this row contains an industry header
            for industry in industry_headers:
                if industry in text and not text.startswith('Total'):
                    current_industry = industry
                    break
            
            # Look for XBRL elements in this row and assign them to current industry
            xbrl_elements = row.find_all(attrs={'contextref': True})
            for elem in xbrl_elements:
                context = elem.get('contextref', '')
                if context and context.startswith('c-'):
                    industry_mapping[context] = current_industry
        
        return industry_mapping
    
    def _find_company_name_for_context(self, soup: BeautifulSoup, context: str) -> str:
        """Find company name associated with a context."""
        
        context_elem = soup.find(attrs={'contextref': context})
        if context_elem:
            parent = context_elem.parent
            while parent:
                if parent.name == 'tr':
                    cells = parent.find_all('td')
                    if cells:
                        first_cell_text = cells[0].get_text(strip=True)
                        if first_cell_text and not first_cell_text.startswith('Total'):
                            return first_cell_text
                parent = parent.parent
                if parent and parent.name == 'table':
                    break
        return "Unknown Company"
    
    def _extract_investment_type_xbrl(self, soup: BeautifulSoup, context: str) -> str:
        """Extract investment type from XBRL format."""
        
        context_elem = soup.find(attrs={'contextref': context})
        if context_elem:
            parent = context_elem.parent
            while parent:
                if parent.name == 'tr':
                    cells = parent.find_all('td')
                    if len(cells) > 2:
                        investment_cell = cells[2]
                        text = investment_cell.get_text(strip=True)
                        if text and len(text) > 10:
                            return self._classify_investment_type(text)
                parent = parent.parent
                if parent and parent.name == 'table':
                    break
        return "unknown"
    
    def _extract_date_xbrl(self, soup: BeautifulSoup, context: str, date_type: str) -> str:
        """Extract date from XBRL format."""
        
        context_elem = soup.find(attrs={'contextref': context})
        if context_elem:
            parent = context_elem.parent
            while parent:
                if parent.name == 'tr':
                    cells = parent.find_all('td')
                    if len(cells) > 3:
                        if date_type == 'acquisition':
                            date_cell = cells[3]
                        else:
                            date_cell = cells[-1]
                        
                        date_text = date_cell.get_text(strip=True)
                        if date_text and len(date_text) > 5:
                            return date_text
                parent = parent.parent
                if parent and parent.name == 'table':
                    break
        return ""
    
    def _extract_amount(self, data: Dict[str, str], field_name: str) -> Optional[float]:
        """Extract monetary amount from XBRL data."""
        
        try:
            value = data.get(field_name, '0')
            return float(value) if value else None
        except (ValueError, TypeError):
            return None
    
    def _extract_rate(self, data: Dict[str, str], field_name: str) -> Optional[float]:
        """Extract interest rate from XBRL data."""
        
        try:
            value = data.get(field_name, '0')
            return float(value) if value else None
        except (ValueError, TypeError):
            return None
    
    def save_to_csv(self, result: BDCExtractionResult, filename: str = None):
        """Save BDC investment data to CSV."""
        
        if not result.investments:
            logger.warning("No investment data to save")
            return
        
        if filename is None:
            filename = f"{result.company_name.replace(' ', '_')}_bdc_investments.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'company_name', 'business_description', 'investment_type', 'coupon_rate',
                'reference_rate', 'spread', 'acquisition_date', 'maturity_date',
                'shares_units', 'principal_amount', 'amortized_cost', 'fair_value',
                'percent_of_net_assets', 'industry', 'notes'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for investment in result.investments:
                writer.writerow({
                    'company_name': investment.company_name,
                    'business_description': investment.business_description,
                    'investment_type': investment.investment_type,
                    'coupon_rate': investment.coupon_rate,
                    'reference_rate': investment.reference_rate,
                    'spread': investment.spread,
                    'acquisition_date': investment.acquisition_date,
                    'maturity_date': investment.maturity_date,
                    'shares_units': investment.shares_units,
                    'principal_amount': investment.principal_amount,
                    'amortized_cost': investment.amortized_cost,
                    'fair_value': investment.fair_value,
                    'percent_of_net_assets': investment.percent_of_net_assets,
                    'industry': investment.industry,
                    'notes': investment.notes
                })
        
        logger.info(f"Saved {len(result.investments)} investments to {filename}")
    
    def save_to_json(self, result: BDCExtractionResult, filename: str = None):
        """Save BDC investment data to JSON."""
        
        if filename is None:
            filename = f"{result.company_name.replace(' ', '_')}_bdc_investments.json"
        
        # Convert to dict for JSON serialization
        data = {
            'company_name': result.company_name,
            'extraction_date': result.extraction_date,
            'total_investments': result.total_investments,
            'total_principal': result.total_principal,
            'total_cost': result.total_cost,
            'total_fair_value': result.total_fair_value,
            'industry_breakdown': result.industry_breakdown,
            'investment_type_breakdown': result.investment_type_breakdown,
            'investments': [
                {
                    'company_name': inv.company_name,
                    'business_description': inv.business_description,
                    'investment_type': inv.investment_type,
                    'coupon_rate': inv.coupon_rate,
                    'reference_rate': inv.reference_rate,
                    'spread': inv.spread,
                    'acquisition_date': inv.acquisition_date,
                    'maturity_date': inv.maturity_date,
                    'shares_units': inv.shares_units,
                    'principal_amount': inv.principal_amount,
                    'amortized_cost': inv.amortized_cost,
                    'fair_value': inv.fair_value,
                    'percent_of_net_assets': inv.percent_of_net_assets,
                    'industry': inv.industry,
                    'notes': inv.notes
                }
                for inv in result.investments
            ]
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved investment data to {filename}")

def main():
    """Test the BDC investment extractor."""
    
    # Test with ARES Capital Corp
    extractor = BDCInvestmentExtractor()
    
    # You would provide the actual 10-Q URL here
    filing_url = "https://www.sec.gov/Archives/edgar/data/1287750/000128775025000025/0001287750-25-000025.txt"
    
    try:
        result = extractor.extract_bdc_investments(filing_url, "ARES Capital Corp")
        
        print(f"✅ Successfully extracted {result.total_investments} investments")
        print(f"Total Principal: ${result.total_principal:,.0f}")
        print(f"Total Cost: ${result.total_cost:,.0f}")
        print(f"Total Fair Value: ${result.total_fair_value:,.0f}")
        
        print(f"\n📊 Investment Types:")
        for inv_type, count in result.investment_type_breakdown.items():
            print(f"  {inv_type}: {count} investments")
        
        print(f"\n🏭 Industries:")
        for industry, count in result.industry_breakdown.items():
            print(f"  {industry}: {count} investments")
        
        # Save results
        extractor.save_to_csv(result)
        extractor.save_to_json(result)
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main()
