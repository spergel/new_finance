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
        
        # Filter to latest reporting instant to avoid mixing quarterly and year-end data
        selected_instant = self._select_reporting_instant(contexts)
        if selected_instant:
            contexts = [c for c in contexts if c.get('instant') == selected_instant]
            logger.info(f"Filtered contexts to instant {selected_instant}: {len(contexts)} remaining")
        
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
                
                # Extract dates from XBRL context
                instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
                start_match = re.search(r'<startDate>([^<]+)</startDate>', ctx_content)
                end_match = re.search(r'<endDate>([^<]+)</endDate>', ctx_content)
                
                # Also try to extract dates from identifier string itself
                acq_date_from_id, mat_date_from_id = self._extract_dates_from_identifier(investment_identifier)
                
                # Prefer dates from identifier, fall back to XBRL context dates
                acquisition_date = acq_date_from_id or (start_match.group(1) if start_match else None)
                maturity_date = mat_date_from_id or (end_match.group(1) if end_match else None)
                
                context = {
                    'id': ctx_id,
                    'investment_identifier': investment_identifier,
                    'company_name': company_name,
                    'investment_type': investment_type,
                    'instant': instant_match.group(1) if instant_match else None,
                    'start_date': acquisition_date,
                    'end_date': maturity_date
                }
                
                contexts.append(context)
        
        return contexts
    
    def _extract_dates_from_identifier(self, identifier: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract acquisition and maturity dates from identifier string."""
        acquisition_date = None
        maturity_date = None
        
        # Normalize HTML entities
        import html
        ident_clean = html.unescape(identifier or "")
        
        # Acquisition date patterns
        acq_patterns = [
            r'Initial\s+Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
            r'Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
            r'Origination\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
            r'Investment\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
        ]
        
        # Maturity date patterns
        mat_patterns = [
            r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
            r'Maturity\s+(\d{1,2}/\d{1,2}/\d{4})',
            r'Due\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})',
            r'Due\s+(\d{1,2}/\d{1,2}/\d{4})',
        ]
        
        for pattern in acq_patterns:
            match = re.search(pattern, ident_clean, re.IGNORECASE)
            if match:
                acquisition_date = match.group(1)
                break
        
        for pattern in mat_patterns:
            match = re.search(pattern, ident_clean, re.IGNORECASE)
            if match:
                maturity_date = match.group(1)
                break
        
        return acquisition_date, maturity_date
    
    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        """Choose the latest instant (YYYY-MM-DD) among contexts, if available.
        
        This prevents mixing quarterly and year-end data in the same extraction.
        """
        dates = []
        for c in contexts:
            inst = c.get('instant')
            if inst and re.match(r'^\d{4}-\d{2}-\d{2}$', inst):
                dates.append(inst)
        if not dates:
            return None
        return max(dates)
    
    def _parse_investment_identifier(self, identifier: str) -> Tuple[str, str]:
        """
        Parse investment identifier into company name and investment type.
        
        Examples:
        - "Banyan Software Holdings, LLC, First lien senior secured loan"
        - "BRANDNER DESIGN, LLC, Revolving Loan"
        - "American Nuts, LLC, Secured Debt 1"
        - "Investment, Non-Affiliated Issuer, First Lien Debt, Company Name, Industry"
        - "Company, Industry, Investment Type"
        - "PPW Aero Buyer, Inc., One stop 1"
        - "Hg Genesis 8 Sumoco Limited, Unsecured facility"
        Returns: (company_name, investment_type)
        """
        
        # Remove common prefixes that appear at the start
        cleaned = identifier
        prefixes = [
            r'^Investment,\s*Non-Affiliated\s+Issuer,\s*',
            r'^Investment,\s*Non-Affiliate\s+Issuer,\s*',
            r'^Investment,\s*Affiliated\s+Issuer,\s*',
            r'^Investment,\s*Controlled\s+Affiliate,\s*',
            r'^Services\s+&\s+Supplies\s+',
            r'^Care\s+Providers\s+&\s+Services\s+',
            r'^Care\s+Equipment\s+&\s+Supplies\s+',
            r'^Equipment,\s+Instruments\s+&\s+Components\s+',
            r'^Defense\s+',
        ]
        for prefix in prefixes:
            cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
        
        # Common investment type patterns (order matters - check longer patterns first)
        investment_type_patterns = [
            'First lien senior secured revolving loan',
            'First lien senior secured loan',
            'First lien senior secured notes',
            'First lien - term loan a',
            'First lien - term loan b',
            'First lien term loan',
            'First lien',
            'Second lien senior secured loan',
            'Second lien senior secured notes',
            'Second lien',
            'Senior subordinated loan',
            'Subordinated loan',
            'Subordinated revolving loan',
            'Subordinated',
            'Senior secured notes',
            'Revolving loan',
            'Revolver',
            'One stop',
            'Unsecured facility',
            'Unsecured debt',
            'Unsecured notes',
            'Secured debt 1',
            'Secured debt 2',
            'Secured debt',
            'Preferred member units',
            'Preferred member',
            'Limited partnership interest',
            'Limited partnership interests',
            'Limited partner interest',
            'Limited partner interests',
            'Partnership units',
            'Partnership interest',
            'Preferred stock',
            'Preferred shares',
            'Preferred equity',
            'Junior preferred shares',
            'Redeemable shares',
            'Series A preferred units',
            'Series B preferred units',
            'Series C preferred units',
            'Series D preferred units',
            'Series A preferred',
            'Series B preferred',
            'Series C preferred',
            'Series D preferred',
            'Series A',
            'Series B',
            'Series C',
            'Series D',
            'Common stock',
            'Common shares',
            'Common units',
            'Common unit',
            'Ordinary shares',
            'Class A',
            'Class B',
            'Class C',
            'Class D',
            'Membership interest',
            'Membership interests',
            'Warrant',
            'Warrants',
            'units',
            'membership units',
            'convertible note',
            'convertible notes',
            'convertible shares',
            'simple agreement for future equity',
        ]
        
        # Try to find investment type in the identifier
        investment_type = "Unknown"
        company_name = cleaned
        
        # Handle complex formats with multiple commas
        # Pattern 1: "Company, Industry, Investment Type"
        # Pattern 2: "Company, Investment Type"
        # Pattern 3: "Investment, Non-Affiliated Issuer, First Lien Debt, Company, Industry"
        # Pattern 4: "First Lien Debt, Company, Industry" (after prefix removal)
        
        if ',' in cleaned:
            parts = [p.strip() for p in cleaned.split(',')]
            
            # Special case: "First Lien Debt, Company, Industry" format (after prefix removal)
            if len(parts) >= 3:
                first_part = parts[0]
                first_part_lower = first_part.lower()
                # Check if first part is an investment type
                for pattern in sorted(investment_type_patterns, key=len, reverse=True):
                    pattern_lower = pattern.lower()
                    if pattern_lower in first_part_lower:
                        # First part is investment type
                        investment_type = first_part
                        # Company might be just parts[1], or parts[1] + parts[2] if parts[2] looks like company suffix (LP, LLC, Inc., etc.)
                        # Check if parts[2] looks like industry or company suffix
                        third_part = parts[2] if len(parts) > 2 else None
                        industry_indicators = ['services', 'healthcare', 'technology', 'financial', 'consumer', 
                                              'industrial', 'energy', 'retail', 'manufacturing', 'aerospace',
                                              'defense', 'pharmaceuticals', 'media', 'telecommunications', 'durables',
                                              'household', 'data processing', 'outsourced', 'diversified', 'equipment',
                                              'storage', 'transportation', 'gas', 'oil', 'multi-sector', 'metal',
                                              'glass', 'plastic', 'containers', 'energy equipment']
                        
                        # Check if third part looks like industry
                        is_industry = third_part and any(ind in third_part.lower() for ind in industry_indicators)
                        # Check if third part looks like company suffix
                        is_company_suffix = third_part and re.search(r'\b(LP|LLC|Inc\.?|Corp\.?|Ltd\.?|Limited|LLP)\b', third_part, re.IGNORECASE)
                        
                        if is_industry:
                            # Third part is industry, company is just second part
                            company_name = parts[1]
                        elif is_company_suffix:
                            # Third part looks like company suffix, combine with second part
                            company_name = f"{parts[1]}, {third_part}"
                        else:
                            # Default: company is second part
                            company_name = parts[1]
                        break
            
            # If we have 3+ parts and haven't found investment type yet
            if investment_type == "Unknown" and len(parts) >= 3:
                # Check if last part is an investment type
                last_part = parts[-1]
                last_part_lower = last_part.lower()
                
                # Check if second-to-last might be industry (common industry patterns)
                second_last = parts[-2] if len(parts) >= 2 else None
                industry_indicators = ['services', 'healthcare', 'technology', 'financial', 'consumer', 
                                      'industrial', 'energy', 'retail', 'manufacturing', 'aerospace',
                                      'defense', 'pharmaceuticals', 'media', 'telecommunications', 'durables',
                                      'household', 'data processing', 'outsourced', 'equipment', 'storage',
                                      'transportation', 'gas', 'oil', 'multi-sector', 'sector', 'metal',
                                      'glass', 'plastic', 'containers', 'energy equipment']
                
                # If last part matches investment type pattern, use it
                for pattern in sorted(investment_type_patterns, key=len, reverse=True):
                    pattern_lower = pattern.lower()
                    if pattern_lower in last_part_lower or re.match(rf'^{re.escape(pattern_lower)}\s*\d*$', last_part_lower):
                        # Last part is investment type
                        investment_type = last_part
                        # Check if second-to-last looks like industry
                        is_industry = second_last and any(ind in second_last.lower() for ind in industry_indicators)
                        # Check if second-to-last is actually an investment type (like "Subordinated")
                        is_inv_type = second_last and any(pattern.lower() in second_last.lower() for pattern in investment_type_patterns)
                        
                        if is_industry:
                            # Second-to-last is industry, company is everything before that
                            # But check if there are more industry parts before that
                            company_parts = []
                            for i in range(len(parts) - 2):
                                part = parts[i]
                                # Check if this part looks like industry
                                part_is_industry = any(ind in part.lower() for ind in industry_indicators)
                                # Check if this part looks like company suffix
                                part_is_suffix = re.search(r'\b(Inc\.?|LLC|LP|Corp\.?|Ltd\.?|Limited|LLP)\b', part, re.IGNORECASE)
                                
                                if part_is_suffix:
                                    # This is part of company name (suffix), include it and everything before
                                    company_parts = parts[:i+1]
                                    break
                                elif not part_is_industry:
                                    # Not industry, likely part of company name
                                    company_parts.append(part)
                                # If it's industry, skip it
                            
                            if company_parts:
                                company_name = ','.join(company_parts).strip()
                            else:
                                # Fallback: everything before second-to-last
                                company_name = ','.join(parts[:-2]).strip()
                        elif not is_industry and second_last:
                            # Second-to-last is not industry, but check if it might still be industry
                            # (e.g., "Energy Equipment & Services" contains "equipment" but might not match all indicators)
                            second_last_lower = second_last.lower()
                            # More lenient check - if it contains multiple industry keywords, it's likely industry
                            industry_keyword_count = sum(1 for ind in industry_indicators if ind in second_last_lower)
                            if industry_keyword_count >= 1:  # At least one industry keyword
                                # Likely industry, exclude it
                                company_name = ','.join(parts[:-2]).strip()
                            else:
                                # Not clearly industry, might be part of company name
                                company_name = ','.join(parts[:-1]).strip()
                        elif is_inv_type:
                            # Second-to-last is also investment type, combine them
                            investment_type = f"{second_last}, {last_part}".strip(', ')
                            company_name = ','.join(parts[:-2]).strip()
                        else:
                            # Company name is everything before the last part
                            # But check if second-to-last looks like it could be part of company name
                            # (e.g., "Inc.", "LLC", "LP", etc.)
                            if second_last and re.search(r'\b(Inc\.?|LLC|LP|Corp\.?|Ltd\.?|Limited|LLP)\b', second_last, re.IGNORECASE):
                                # Second-to-last is likely part of company name, include it
                                company_name = ','.join(parts[:-1]).strip()
                            else:
                                # Check if second-to-last is a single word that might be industry
                                # If it's a short word and doesn't look like company suffix, might be industry
                                if second_last and len(second_last.split()) <= 3 and not re.search(r'\b(Inc\.?|LLC|LP|Corp\.?|Ltd\.?|Limited|LLP)\b', second_last, re.IGNORECASE):
                                    # Might be industry, exclude it
                                    company_name = ','.join(parts[:-2]).strip()
                                else:
                                    # Default: company name is everything before the last part
                                    company_name = ','.join(parts[:-1]).strip()
                        break
                    # Also check if pattern is in second-to-last and last is a number/variant
                    elif second_last and pattern_lower in second_last.lower():
                        # Second-to-last is investment type, last might be number/variant
                        investment_type = f"{second_last}, {last_part}".strip(', ')
                        company_name = ','.join(parts[:-2]).strip()
                        break
                
                # If we didn't find investment type yet, try simpler approach
                if investment_type == "Unknown":
                    # Try last comma approach
                    last_comma_idx = cleaned.rfind(',')
                    potential_company = cleaned[:last_comma_idx].strip()
                    potential_type = cleaned[last_comma_idx + 1:].strip()
                    
                    potential_type_lower = potential_type.lower()
                    for pattern in sorted(investment_type_patterns, key=len, reverse=True):
                        pattern_lower = pattern.lower()
                        # Check if pattern is at the start of potential_type (allowing for additional descriptive text)
                        if potential_type_lower.startswith(pattern_lower) or pattern_lower in potential_type_lower or re.match(rf'^{re.escape(pattern_lower)}\s*\d*', potential_type_lower):
                            company_name = potential_company
                            investment_type = potential_type
                            break
            elif len(parts) == 2:
                # Only 2 parts: "Company, Investment Type"
                potential_company = parts[0]
                potential_type = parts[1]
                
                potential_type_lower = potential_type.lower()
                for pattern in sorted(investment_type_patterns, key=len, reverse=True):
                    pattern_lower = pattern.lower()
                    if pattern_lower in potential_type_lower or re.match(rf'^{re.escape(pattern_lower)}\s*\d*$', potential_type_lower):
                        company_name = potential_company
                        investment_type = potential_type
                        break
        
        # If comma-based parsing didn't work, try pattern matching in the full identifier
        if investment_type == "Unknown":
            identifier_lower = cleaned.lower()
            for pattern in sorted(investment_type_patterns, key=len, reverse=True):
                pattern_lower = pattern.lower()
                if pattern_lower in identifier_lower:
                    idx = identifier_lower.find(pattern_lower)
                    if idx > 0:
                        company_name = cleaned[:idx].strip()
                        company_name = company_name.rstrip(', ')
                        investment_type = cleaned[idx:].strip()
                    break
        
        # Clean up company name - remove trailing numbers that might be investment variants
        # But preserve numbers that are part of company name (like "Company 123 LLC")
        if company_name and re.search(r'\s+\d+$', company_name):
            # Check if it's likely an investment variant (short number) vs company name part
            match = re.search(r'\s+(\d+)$', company_name)
            if match and len(match.group(1)) <= 2:  # 1-2 digit numbers are likely variants
                company_name = company_name[:match.start()].strip()
        
        # Clean up company name - fix spacing around commas
        if company_name:
            company_name = re.sub(r',\s*', ', ', company_name)  # Ensure space after comma
            company_name = company_name.strip()
        
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
        
        def _percent(v: str) -> Optional[str]:
            try:
                val = float(str(v).replace(',', '').replace('%', ''))
                if val < 1:
                    return f"{val * 100:.2f}%"
                else:
                    return f"{val:.2f}%"
            except:
                return str(v) if v else None
        
        # Extract financial data from facts
        cost_basis = None
        fair_value = None
        principal_amount = None
        maturity_date = None
        acquisition_date = None
        interest_rate = None
        reference_rate = None
        spread = None
        floor_rate = None
        pik_rate = None
        
        for fact in facts:
            concept = fact['concept']
            value = fact['value']
            if not value:
                continue
            
            v_clean = value.replace(',', '').strip()
            cl = concept.lower()
            
            try:
                if 'InvestmentOwnedAtCost' in concept or 'AmortizedCost' in concept or ('cost' in cl and ('amortized' in cl or 'basis' in cl)):
                    cost_basis = float(v_clean)
                elif 'InvestmentOwnedAtFairValue' in concept or 'FairValue' in concept or 'fairvalue' in cl:
                    fair_value = float(v_clean)
                elif 'InvestmentOwnedBalancePrincipalAmount' in concept or 'PrincipalAmount' in concept or 'principalamount' in cl:
                    principal_amount = float(v_clean)
                elif 'maturitydate' in cl or ('maturity' in cl and 'date' in cl):
                    maturity_date = value.strip()
                elif 'acquisitiondate' in cl or 'investmentdate' in cl:
                    acquisition_date = value.strip()
                elif 'interestrate' in cl and 'floor' not in cl:
                    interest_rate = _percent(v_clean)
                elif 'variableinterestratetype' in cl or ('reference' in cl and 'rate' in cl):
                    if 'sofr' in cl or 'sofr' in value.lower():
                        reference_rate = 'SOFR'
                    elif 'libor' in cl or 'libor' in value.lower():
                        reference_rate = 'LIBOR'
                    elif 'prime' in cl or 'prime' in value.lower():
                        reference_rate = 'PRIME'
                    elif value and not value.startswith('http'):
                        reference_rate = value.upper().strip()
                elif 'spread' in cl or ('basis' in cl and 'spread' in cl):
                    spread = _percent(v_clean)
                elif 'floor' in cl and 'rate' in cl:
                    floor_rate = _percent(v_clean)
                elif 'pik' in cl and 'rate' in cl:
                    pik_rate = _percent(v_clean)
            except (ValueError, TypeError):
                pass
        
        # Only create investment if we have meaningful data
        if not (cost_basis or fair_value or principal_amount):
            return None
        
        return BDCInvestment(
            company_name=company_name,
            investment_type=investment_type,
            industry=context.get('industry', 'Unknown'),
            acquisition_date=acquisition_date or context.get('start_date'),
            maturity_date=maturity_date or context.get('end_date'),
            principal_amount=principal_amount,
            cost_basis=cost_basis,
            fair_value=fair_value,
            interest_rate=interest_rate,
            basis_spread=spread,
            floor_rate=floor_rate,
            pik_rate=pik_rate,
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

        if not os.path.isabs(output_dir):
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_dir)
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

