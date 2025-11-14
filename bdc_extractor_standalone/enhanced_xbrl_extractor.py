#!/usr/bin/env python3
"""
Enhanced XBRL Extractor that extracts ALL facts for each investment context.

This extracts every fact associated with each InvestmentIdentifierAxis context
to get complete data including dates, rates, spreads, etc.
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
import requests

logger = logging.getLogger(__name__)


class EnhancedXBRLExtractor:
    """Extracts all XBRL facts for each investment context."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
    
    def extract_all_facts_from_url(self, filing_url: str) -> Dict[str, List[Dict]]:
        """Extract all facts grouped by investment context."""
        logger.info(f"Downloading XBRL from: {filing_url}")
        
        response = requests.get(filing_url, headers=self.headers)
        response.raise_for_status()
        content = response.text
        
        logger.info(f"Downloaded {len(content)} characters")
        
        # Extract investment contexts
        investment_contexts = self._extract_investment_contexts(content)
        logger.info(f"Found {len(investment_contexts)} investment contexts")
        
        # Extract all facts
        all_facts = self._extract_all_facts(content)
        logger.info(f"Found {len(all_facts)} total facts")
        
        # Group facts by context
        facts_by_context = defaultdict(list)
        for fact in all_facts:
            context_ref = fact.get('contextRef')
            if context_ref:
                facts_by_context[context_ref].append(fact)
        
        return {
            'contexts': investment_contexts,
            'facts_by_context': dict(facts_by_context)
        }
    
    def _extract_investment_contexts(self, content: str) -> Dict[str, Dict]:
        """Extract all investment contexts with InvestmentIdentifierAxis."""
        contexts = {}
        
        context_pattern = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        typed_member_pattern = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>\s*</xbrldi:typedMember>',
            re.DOTALL
        )
        
        for match in context_pattern.finditer(content):
            ctx_id = match.group(1)
            ctx_html = match.group(2)
            
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
                industry = self._clean_industry_name(industry_raw)
            
            # Parse identifier to extract company name and investment type
            parsed = self._parse_identifier(identifier)
            
            contexts[ctx_id] = {
                'id': ctx_id,
                'identifier': identifier,
                'company_name': parsed.get('company_name', identifier),
                'investment_type': parsed.get('investment_type', 'Unknown'),
                'industry': industry,
                'instant': instant
            }
        
        return contexts
    
    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        """Parse investment identifier to extract company name and investment type."""
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
                res['company_name'] = re.sub(pattern, '', identifier, flags=re.IGNORECASE).strip(' ,')
                break
        
        return res
    
    def _clean_industry_name(self, industry: str) -> str:
        """Clean industry name from XBRL."""
        industry = re.sub(r'^[^:]+:', '', industry)
        industry = industry.replace('_', ' ').title()
        return industry
    
    def _extract_all_facts(self, content: str) -> List[Dict]:
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
    
    def build_investment_from_facts(self, context: Dict, facts: List[Dict]) -> Optional[Dict]:
        """Build investment dict from context and all facts."""
        if not context.get('company_name') or context.get('company_name') == 'Unknown':
            return None
        
        inv = {
            'company_name': context.get('company_name', ''),
            'investment_type': context.get('investment_type', 'Unknown'),
            'industry': context.get('industry', 'Unknown'),
            'context_ref': context.get('id', ''),
        }
        
        # Process all facts to extract fields
        for fact in facts:
            concept = fact.get('concept', '')
            value = fact.get('value', '')
            unit = fact.get('unit', '')
            
            if not value:
                continue
            
            concept_lower = concept.lower()
            
            # Principal amount
            if any(k in concept_lower for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal']):
                try:
                    inv['principal_amount'] = float(value.replace(',', ''))
                except:
                    pass
            
            # Cost basis
            elif any(k in concept_lower for k in ['cost', 'ownedatcost']) and 'amortized' in concept_lower or 'basis' in concept_lower:
                try:
                    inv['cost_basis'] = float(value.replace(',', ''))
                except:
                    pass
            
            # Fair value
            elif 'fairvalue' in concept_lower or ('fair' in concept_lower and 'value' in concept_lower):
                try:
                    inv['fair_value'] = float(value.replace(',', ''))
                except:
                    pass
            
            # Maturity date
            elif 'maturitydate' in concept_lower or 'maturity' in concept_lower:
                inv['maturity_date'] = value.strip()
            
            # Acquisition date
            elif 'acquisitiondate' in concept_lower or 'investmentdate' in concept_lower:
                inv['acquisition_date'] = value.strip()
            
            # Interest rate
            elif 'interestrate' in concept_lower and 'floor' not in concept_lower:
                try:
                    rate = float(value.replace(',', ''))
                    inv['interest_rate'] = f"{rate * 100:.2f}%" if rate < 1 else f"{rate:.2f}%"
                except:
                    inv['interest_rate'] = value.strip()
            
            # Reference rate (from variable interest rate type)
            elif 'variableinterestratetype' in concept_lower or 'reference' in concept_lower:
                # Extract rate name from URI or value
                if 'sofr' in concept_lower or 'sofr' in value.lower():
                    inv['reference_rate'] = 'SOFR'
                elif 'libor' in concept_lower or 'libor' in value.lower():
                    inv['reference_rate'] = 'LIBOR'
                elif 'prime' in concept_lower or 'prime' in value.lower():
                    inv['reference_rate'] = 'PRIME'
                elif value and not value.startswith('http'):
                    inv['reference_rate'] = value.strip()
            
            # Spread
            elif 'spread' in concept_lower or 'basis' in concept_lower and 'spread' in concept_lower:
                try:
                    spread = float(value.replace(',', ''))
                    inv['spread'] = f"{spread * 100:.2f}%" if spread < 1 else f"{spread:.2f}%"
                except:
                    inv['spread'] = value.strip()
            
            # Floor rate
            elif 'floor' in concept_lower:
                try:
                    floor = float(value.replace(',', ''))
                    inv['floor_rate'] = f"{floor * 100:.2f}%" if floor < 1 else f"{floor:.2f}%"
                except:
                    inv['floor_rate'] = value.strip()
            
            # PIK rate
            elif 'pik' in concept_lower:
                try:
                    pik = float(value.replace(',', ''))
                    inv['pik_rate'] = f"{pik * 100:.2f}%" if pik < 1 else f"{pik:.2f}%"
                except:
                    inv['pik_rate'] = value.strip()
        
        # Skip if no meaningful financial data
        if not inv.get('principal_amount') and not inv.get('cost_basis') and not inv.get('fair_value'):
            return None
        
        return inv

