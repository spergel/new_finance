#!/usr/bin/env python3
"""
XBRL Investment Extractor using InvestmentIdentifierAxis (typedMember)

This extracts investment data from the InvestmentIdentifierAxis dimension
which contains both company name and investment type in a single string.
"""

import os
import json
import logging
import re
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class BDCInvestment:
    """Represents a single BDC investment."""
    company_name: str
    business_description: Optional[str] = None
    investment_type: str = "Unknown"
    industry: str = "Unknown"
    acquisition_date: Optional[str] = None
    maturity_date: Optional[str] = None
    principal_amount: Optional[float] = None
    cost_basis: Optional[float] = None
    fair_value: Optional[float] = None
    interest_rate: Optional[float] = None
    basis_spread: Optional[float] = None
    floor_rate: Optional[float] = None
    eot_rate: Optional[float] = None
    pik_rate: Optional[float] = None
    context_ref: Optional[str] = None

@dataclass
class BDCExtractionResult:
    """Result of BDC investment extraction."""
    company_name: str
    cik: str
    filing_date: str
    filing_url: str
    extraction_date: str
    total_investments: int
    total_principal: float
    total_cost: float
    total_fair_value: float
    investments: List[Dict]
    industry_breakdown: Dict[str, int]
    investment_type_breakdown: Dict[str, int]

class TypedMemberExtractor:
    """Extracts investments using InvestmentIdentifierAxis typedMember dimension."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        """Initialize the extractor."""
        self.headers = {'User-Agent': user_agent}
    
    def extract_from_url(self, filing_url: str, company_name: str = None, cik: str = None) -> BDCExtractionResult:
        """Extract BDC investment data from a filing URL."""
        
        logger.info(f"Downloading XBRL from: {filing_url}")
        
        # Download the XBRL content
        response = requests.get(filing_url, headers=self.headers)
        response.raise_for_status()
        content = response.text
        
        logger.info(f"Downloaded {len(content)} characters")
        
        # Extract contexts with typedMember InvestmentIdentifierAxis
        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        
        # Extract facts
        facts_by_context = self._extract_facts(content)
        logger.info(f"Found facts for {len(facts_by_context)} contexts")
        
        # Build investments
        investments = []
        for ctx in contexts:
            investment = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if investment:
                investments.append(investment)
        
        logger.info(f"Built {len(investments)} investments")
        
        # Calculate totals
        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost_basis or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in investments:
            industry_breakdown[inv.industry] += 1
            investment_type_breakdown[inv.investment_type] += 1
        
        # Extract filing date
        filing_date = self._extract_filing_date(content)
        
        return BDCExtractionResult(
            company_name=company_name or "Unknown BDC",
            cik=cik or "",
            filing_date=filing_date or "",
            filing_url=filing_url,
            extraction_date=datetime.now().isoformat(),
            total_investments=len(investments),
            total_principal=total_principal,
            total_cost=total_cost,
            total_fair_value=total_fair_value,
            investments=[asdict(inv) for inv in investments],
            industry_breakdown=dict(industry_breakdown),
            investment_type_breakdown=dict(investment_type_breakdown)
        )
    
    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        """Extract contexts with typedMember InvestmentIdentifierAxis."""
        
        contexts = []
        
        # Pattern to find contexts with typedMember dimension
        # <xbrli:context id="c-XX">
        #   <xbrli:entity>
        #     <xbrli:segment>
        #       <xbrldi:typedMember dimension="us-gaap:InvestmentIdentifierAxis">
        #         <us-gaap:InvestmentIdentifierAxis.domain>Company Name, Investment Type</...>
        context_pattern = re.compile(
            r'<context id="([^"]+)">(.*?)</context>',
            re.DOTALL
        )
        
        for match in context_pattern.finditer(content):
            ctx_id = match.group(1)
            ctx_content = match.group(2)
            
            # Look for typedMember with InvestmentIdentifierAxis
            # The pattern needs to handle whitespace/newlines between tags
            typed_member_pattern = re.compile(
                r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
                r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
                r'\s*</xbrldi:typedMember>',
                re.DOTALL
            )
            
            typed_match = typed_member_pattern.search(ctx_content)
            if typed_match:
                investment_identifier = typed_match.group(1).strip()
                
                # Parse company name and investment type from the identifier
                company_name, investment_type = self._parse_investment_identifier(investment_identifier)
                
                # Extract dates
                instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
                start_match = re.search(r'<startDate>([^<]+)</startDate>', ctx_content)
                end_match = re.search(r'<endDate>([^<]+)</endDate>', ctx_content)
                
                context = {
                    'id': ctx_id,
                    'investment_identifier': investment_identifier,
                    'company_name': company_name,
                    'investment_type': investment_type,
                    'instant': instant_match.group(1) if instant_match else None,
                    'start_date': start_match.group(1) if start_match else None,
                    'end_date': end_match.group(1) if end_match else None
                }
                
                contexts.append(context)
        
        return contexts
    
    def _parse_investment_identifier(self, identifier: str) -> Tuple[str, str]:
        """
        Parse investment identifier into company name and investment type.
        
        Example: "Banyan Software Holdings, LLC, First lien senior secured loan"
        Returns: ("Banyan Software Holdings, LLC", "First lien senior secured loan")
        """
        
        # Common investment type patterns
        investment_type_patterns = [
            'First lien senior secured loan',
            'First lien senior secured revolving loan',
            'Second lien senior secured loan',
            'Senior subordinated loan',
            'Subordinated loan',
            'Limited partnership interest',
            'Limited partnership interests',
            'Partnership units',
            'Partnership interest',
            'Preferred stock',
            'Preferred shares',
            'Series A preferred',
            'Series B preferred',
            'Common stock',
            'Common shares',
            'Class A',
            'Class B',
            'Warrant',
            'units',
            'membership units',
        ]
        
        # Try to find investment type in the identifier
        investment_type = "Unknown"
        company_name = identifier
        
        # Check each pattern (order matters - check longer patterns first)
        for pattern in sorted(investment_type_patterns, key=len, reverse=True):
            # Case-insensitive search
            pattern_lower = pattern.lower()
            identifier_lower = identifier.lower()
            
            if pattern_lower in identifier_lower:
                # Find the position
                idx = identifier_lower.find(pattern_lower)
                
                # Company name is everything before the investment type
                # Usually separated by ", "
                if idx > 0:
                    company_name = identifier[:idx].strip()
                    # Remove trailing comma and spaces
                    company_name = company_name.rstrip(', ')
                    
                    # Investment type is the matched pattern
                    investment_type = identifier[idx:].strip()
                    break
        
        return company_name, investment_type
    
    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        """Extract facts grouped by context."""
        
        facts_by_context = defaultdict(list)
        
        # Find all facts (elements with contextRef attribute)
        fact_pattern = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>')
        matches = fact_pattern.findall(content)
        
        for concept, context_ref, value in matches:
            if value:  # Only include facts with values
                facts_by_context[context_ref].append({
                    'concept': concept,
                    'value': value
                })
        
        return facts_by_context
    
    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[BDCInvestment]:
        """Build an investment from a context and its facts."""
        
        company_name = context['company_name']
        investment_type = context['investment_type']
        
        if not company_name:
            return None
        
        # Extract financial data from facts
        cost_basis = None
        fair_value = None
        principal_amount = None
        
        for fact in facts:
            concept = fact['concept']
            value = fact['value']
            
            try:
                if 'InvestmentOwnedAtCost' in concept or 'AmortizedCost' in concept:
                    cost_basis = float(value)
                elif 'InvestmentOwnedAtFairValue' in concept or 'FairValue' in concept:
                    fair_value = float(value)
                elif 'InvestmentOwnedBalancePrincipalAmount' in concept or 'PrincipalAmount' in concept:
                    principal_amount = float(value)
            except (ValueError, TypeError):
                pass
        
        # Only create investment if we have meaningful data
        if not (cost_basis or fair_value or principal_amount):
            return None
        
        return BDCInvestment(
            company_name=company_name,
            investment_type=investment_type,
            industry="Unknown",  # Will be filled from HTML table
            acquisition_date=context.get('start_date'),
            maturity_date=context.get('end_date'),
            principal_amount=principal_amount,
            cost_basis=cost_basis,
            fair_value=fair_value,
            context_ref=context['id']
        )
    
    def _extract_filing_date(self, content: str) -> Optional[str]:
        """Extract the filing date."""
        
        # Look for DocumentPeriodEndDate
        match = re.search(r'<dei:DocumentPeriodEndDate[^>]*>([^<]+)</dei:DocumentPeriodEndDate>', content)
        if match:
            return match.group(1)
        
        return None
    
    def save_results(self, result: BDCExtractionResult, output_dir: str = 'output'):
        """Save extraction results to JSON and CSV."""
        
        os.makedirs(output_dir, exist_ok=True)
        
        company_slug = result.company_name.replace(' ', '_').replace('.', '').replace(',', '')
        
        # Save full JSON
        json_path = os.path.join(output_dir, f'{company_slug}_typed_investments.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result.investments, f, indent=2)
        logger.info(f"Saved investments to {json_path}")
        
        # Save summary JSON
        summary_path = os.path.join(output_dir, f'{company_slug}_typed_summary.json')
        summary = {
            'company_name': result.company_name,
            'cik': result.cik,
            'filing_date': result.filing_date,
            'filing_url': result.filing_url,
            'extraction_date': result.extraction_date,
            'total_investments': result.total_investments,
            'total_principal': result.total_principal,
            'total_cost': result.total_cost,
            'total_fair_value': result.total_fair_value,
            'industry_breakdown': result.industry_breakdown,
            'investment_type_breakdown': result.investment_type_breakdown
        }
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Saved summary to {summary_path}")
        
        # Save CSV
        import csv
        csv_path = os.path.join(output_dir, f'{company_slug}_typed_investments.csv')
        if result.investments:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = result.investments[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for inv in result.investments:
                    # Apply standardization
                    if 'investment_type' in inv:
                        inv['investment_type'] = standardize_investment_type(inv.get('investment_type'))
                    if 'industry' in inv:
                        inv['industry'] = standardize_industry(inv.get('industry'))
                    if 'reference_rate' in inv:
                        inv['reference_rate'] = standardize_reference_rate(inv.get('reference_rate')) or ''
                    writer.writerow(inv)
            logger.info(f"Saved CSV to {csv_path}")


def main():
    """Test the extractor."""
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    extractor = TypedMemberExtractor()
    
    # Test with ARES Capital Corp
    # Use the .txt file URL which contains the XBRL
    filing_url = "https://www.sec.gov/Archives/edgar/data/1287750/000128775025000046/0001287750-25-000046.txt"
    
    try:
        result = extractor.extract_from_url(
            filing_url=filing_url,
            company_name="Ares Capital Corp",
            cik="0001287750"
        )
        
        print(f"\n✅ Successfully extracted {result.total_investments} investments")
        print(f"   Filing Date: {result.filing_date}")
        print(f"   Total Principal: ${result.total_principal:,.0f}")
        print(f"   Total Cost: ${result.total_cost:,.0f}")
        print(f"   Total Fair Value: ${result.total_fair_value:,.0f}")
        
        print(f"\n🏦 Investment Type Breakdown:")
        for inv_type, count in sorted(result.investment_type_breakdown.items(), key=lambda x: -x[1])[:15]:
            print(f"   {inv_type}: {count}")
        
        # Show sample investments
        print(f"\n📋 Sample Investments (First 10):")
        for i, inv in enumerate(result.investments[:10]):
            print(f"\n   {i+1}. {inv['company_name']}")
            print(f"      Type: {inv['investment_type']}")
            print(f"      Industry: {inv['industry']}")
            if inv.get('cost_basis'):
                print(f"      Cost: ${inv['cost_basis']:,.0f}")
            if inv.get('fair_value'):
                print(f"      Fair Value: ${inv['fair_value']:,.0f}")
        
        # Data quality
        print(f"\n📈 Data Quality:")
        total = result.total_investments
        with_type = sum(1 for inv in result.investments if inv['investment_type'] != 'Unknown')
        with_cost = sum(1 for inv in result.investments if inv.get('cost_basis'))
        with_fair_value = sum(1 for inv in result.investments if inv.get('fair_value'))
        
        print(f"   Investment Type: {with_type}/{total} ({100*with_type/total if total else 0:.1f}%)")
        print(f"   Cost Basis: {with_cost}/{total} ({100*with_cost/total if total else 0:.1f}%)")
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

