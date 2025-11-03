#!/usr/bin/env python3
"""
Custom MAIN (Main Street Capital) Investment Extractor

MAIN uses InvestmentIdentifierAxis with strings like:
"[Company Name], Secured Debt 1" or "[Company Name], Preferred Member Units" etc.
We parse company name and investment type from the identifier and extract facts.
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate
from dataclasses import dataclass
import requests
import csv
import os

logger = logging.getLogger(__name__)

@dataclass
class MAINInvestment:
    company_name: str
    business_description: Optional[str] = None
    investment_type: str = "Unknown"
    industry: str = "Unknown"
    acquisition_date: Optional[str] = None
    maturity_date: Optional[str] = None
    principal_amount: Optional[float] = None
    cost: Optional[float] = None
    fair_value: Optional[float] = None
    interest_rate: Optional[str] = None
    reference_rate: Optional[str] = None
    spread: Optional[str] = None
    floor_rate: Optional[str] = None
    pik_rate: Optional[str] = None
    context_ref: Optional[str] = None


def _normalize_company_name(raw: str) -> str:
    """Normalize company name by removing embedded investment types and normalizing punctuation."""
    name = raw or ''
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove trailing commas and periods
    name = name.rstrip('., ').strip()
    return name


def _normalize_main_row(row: Dict) -> Dict:
    """Normalize a MAIN investment row to ARCC format."""
    normalized = {
        'company_name': (row.get('company_name') or '').strip(),
        'industry': (row.get('industry') or '').strip() or '',
        'business_description': (row.get('business_description') or '').strip() or '',
        'investment_type': (row.get('investment_type') or '').strip() or 'Unknown',
        'acquisition_date': (row.get('acquisition_date') or '').strip() or '',
        'maturity_date': (row.get('maturity_date') or '').strip() or '',
        'principal_amount': row.get('principal_amount') or '',
        'cost': row.get('cost') or '',
        'fair_value': row.get('fair_value') or '',
        'interest_rate': (row.get('interest_rate') or '').strip() or '',
        'reference_rate': (row.get('reference_rate') or '').strip() or '',
        'spread': (row.get('spread') or '').strip() or '',
        'commitment_limit': '',
        'undrawn_commitment': ''
    }
    
    # Normalize company name
    normalized['company_name'] = _normalize_company_name(normalized['company_name'])
    
    # Normalize investment_type
    inv_type = normalized['investment_type'].lower()
    
    # MAIN uses patterns like "Secured Debt 1", "Secured Debt 2"
    if 'secured debt' in inv_type:
        normalized['investment_type'] = 'First lien senior secured loan'
    elif 'unsecured debt' in inv_type:
        normalized['investment_type'] = 'Unsecured debt'
    elif 'preferred member units' in inv_type or 'preferred equity' in inv_type:
        normalized['investment_type'] = 'Preferred equity'
    elif 'preferred stock' in inv_type:
        normalized['investment_type'] = 'Preferred equity'
    elif 'member units' in inv_type or 'common stock' in inv_type:
        normalized['investment_type'] = 'Equity'
    elif 'warrants' in inv_type or 'warrant' in inv_type:
        normalized['investment_type'] = 'Warrants'
    
    # Fix interest rates - MAIN seems to store rates as decimals (0.1295% should be 12.95%)
    interest_rate_str = normalized.get('interest_rate', '').strip()
    if interest_rate_str:
        try:
            # Remove % if present
            rate_val = float(interest_rate_str.rstrip('%').strip())
            # If rate is < 1, it's likely a decimal (multiply by 100)
            if rate_val < 1.0 and rate_val > 0:
                rate_val *= 100.0
            normalized['interest_rate'] = f"{rate_val:.2f}%"
        except (ValueError, TypeError):
            # Keep original if can't parse
            pass
    
    # Fix spreads similarly
    spread_str = normalized.get('spread', '').strip()
    if spread_str:
        try:
            spread_val = float(spread_str.rstrip('%').strip())
            if spread_val < 1.0 and spread_val > 0:
                spread_val *= 100.0
            normalized['spread'] = f"{spread_val:.2f}%"
        except (ValueError, TypeError):
            pass
    
    # Format financial values
    for field in ['principal_amount', 'cost', 'fair_value']:
        val = normalized[field]
        if val is None or val == '':
            normalized[field] = ''
        elif isinstance(val, (int, float)):
            pass
        elif isinstance(val, str):
            try:
                cleaned = val.replace(',', '').strip()
                if cleaned:
                    normalized[field] = float(cleaned)
                else:
                    normalized[field] = ''
            except (ValueError, TypeError):
                normalized[field] = ''
    
    return normalized


class MAINExtractor:
    """Custom extractor for Main Street Capital (MAIN) investments."""

    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "MAIN") -> Dict:
        logger.info(f"Extracting investments for {ticker}")

        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")

        logger.info(f"Found CIK: {cik}")

        filing_index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not filing_index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")

        logger.info(f"Found filing index: {filing_index_url}")

        accession_match = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', filing_index_url)
        if not accession_match:
            raise ValueError(f"Could not parse accession number from {filing_index_url}")

        accession = accession_match.group(1)
        accession_no_hyphens = accession.replace('-', '')

        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        logger.info(f"XBRL URL: {txt_url}")

        return self.extract_from_url(txt_url, "Main_Street_Capital", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")

        response = requests.get(filing_url, headers=self.headers)
        response.raise_for_status()
        content = response.text

        logger.info(f"Downloaded {len(content)} characters")

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")

        # Keep only latest reporting instant to avoid prior-period duplicates
        selected_instant = self._select_reporting_instant(contexts)
        if selected_instant:
            contexts = [c for c in contexts if c.get('instant') == selected_instant]
            logger.info(f"Filtered contexts to instant {selected_instant}: {len(contexts)} remaining")

        # Build industry index by instant to enrich when same-context member absent
        industry_by_instant = self._build_industry_index(content)
        if industry_by_instant:
            logger.info(f"Built industry index for {len(industry_by_instant)} instants")

        for ctx in contexts:
            if (not ctx.get('industry')) or ctx['industry'] == 'Unknown':
                inst = ctx.get('instant')
                if inst and inst in industry_by_instant:
                    ctx['industry'] = industry_by_instant[inst]

        facts_by_context = self._extract_facts(content)
        logger.info(f"Found facts for {len(facts_by_context)} contexts")

        investments: List[MAINInvestment] = []
        for ctx in contexts:
            investment = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if investment:
                investments.append(investment)

        # De-duplicate: keep first per (company, type, maturity) when identical values
        deduped: List[MAINInvestment] = []
        seen = set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val_key = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val_key)
            if combo in seen:
                continue
            seen.add(combo)
            deduped.append(inv)
        investments = deduped

        logger.info(f"Built {len(investments)} investments")

        # Convert to dict format for normalization
        investment_dicts = []
        for inv in investments:
            investment_dicts.append({
                'company_name': inv.company_name,
                'industry': inv.industry,
                'business_description': inv.business_description,
                'investment_type': inv.investment_type,
                'acquisition_date': inv.acquisition_date,
                'maturity_date': inv.maturity_date,
                'principal_amount': inv.principal_amount,
                'cost': inv.cost,
                'fair_value': inv.fair_value,
                'interest_rate': inv.interest_rate,
                'reference_rate': inv.reference_rate,
                'spread': inv.spread,
                'floor_rate': inv.floor_rate,
                'pik_rate': inv.pik_rate,
            })
        
        # Normalize all investments
        normalized_rows = []
        seen_keys = set()
        duplicates_count = 0
        empty_rows_count = 0
        
        for inv in investment_dicts:
            normalized = _normalize_main_row(inv)
            
            # Filter out rows with no meaningful financial data
            has_principal = normalized.get('principal_amount') and str(normalized['principal_amount']).strip() != ''
            has_cost = normalized.get('cost') and str(normalized['cost']).strip() != ''
            has_fair_value = normalized.get('fair_value') and str(normalized['fair_value']).strip() != ''
            
            if not (has_principal or has_cost or has_fair_value):
                empty_rows_count += 1
                continue
            
            # Create deduplication key
            company = normalized.get('company_name', '').strip()
            inv_type = normalized.get('investment_type', '').strip()
            
            if not company or company == '':
                empty_rows_count += 1
                continue
                
            key = (company.lower(), inv_type.lower())
            
            # Check for duplicates
            if key in seen_keys:
                duplicates_count += 1
                continue
            
            seen_keys.add(key)
            normalized_rows.append(normalized)
        
        if duplicates_count > 0:
            logger.info(f"Filtered out {duplicates_count} duplicate rows")
        if empty_rows_count > 0:
            logger.info(f"Filtered out {empty_rows_count} rows with no financial data")

        total_principal = sum(float(r.get('principal_amount') or 0) for r in normalized_rows)
        total_cost = sum(float(r.get('cost') or 0) for r in normalized_rows)
        total_fair_value = sum(float(r.get('fair_value') or 0) for r in normalized_rows)

        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        for r in normalized_rows:
            industry_breakdown[r.get('industry', 'Unknown')] += 1
            investment_type_breakdown[r.get('investment_type', 'Unknown')] += 1

        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(normalized_rows),
            'investments': normalized_rows,  # Return normalized dicts instead of dataclass objects
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        contexts: List[Dict] = []

        context_pattern = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        typed_member_pattern = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>',
            re.DOTALL
        )

        for match in context_pattern.finditer(content):
            ctx_id = match.group(1)
            ctx_content = match.group(2)

            typed_match = typed_member_pattern.search(ctx_content)
            if not typed_match:
                continue

            identifier = typed_match.group(1).strip()
            parsed = self._parse_main_identifier(identifier)

            instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
            start_match = re.search(r'<startDate>([^<]+)</startDate>', ctx_content)
            end_match = re.search(r'<endDate>([^<]+)</endDate>', ctx_content)

            # Prefer industry explicitMember present in the same context
            same_ctx_industry = None
            same_ctx_explicit = re.search(
                r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>',
                ctx_content, re.DOTALL | re.IGNORECASE
            )
            if same_ctx_explicit:
                same_ctx_industry = self._industry_member_to_name(same_ctx_explicit.group(1).strip())

            contexts.append({
                'id': ctx_id,
                'investment_identifier': identifier,
                'company_name': parsed['company_name'],
                'industry': same_ctx_industry or parsed['industry'],
                'investment_type': parsed['investment_type'],
                'instant': instant_match.group(1) if instant_match else None,
                'start_date': start_match.group(1) if start_match else None,
                'end_date': end_match.group(1) if end_match else None
            })

        return contexts

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates = []
        for c in contexts:
            inst = c.get('instant')
            if inst and re.match(r'^\d{4}-\d{2}-\d{2}$', inst):
                dates.append(inst)
        if not dates:
            return None
        return max(dates)

    def _parse_main_identifier(self, identifier: str) -> Dict[str, str]:
        result = {
            'company_name': 'Unknown',
            'industry': 'Unknown',
            'investment_type': 'Unknown'
        }

        # Split on last comma to separate company and type, but allow types with numbers
        if ',' in identifier:
            last_comma = identifier.rfind(',')
            company = identifier[:last_comma].strip()
            tail = identifier[last_comma + 1:].strip()
        else:
            company = identifier.strip()
            tail = ''

        result['company_name'] = re.sub(r'\s+', ' ', company).rstrip(',')

        type_patterns = [
            r'Secured\s+Debt\s*\d*$',
            r'Unsecured\s+Debt\s*\d*$',
            r'Preferred\s+Member\s+Units\s*\d*$',
            r'Preferred\s+Equity$',
            r'Preferred\s+Stock$',
            r'Common\s+Stock\s*\d*$',
            r'Member\s+Units\s*\d*$',
            r'Warrants?$',
        ]

        itype = None
        for pattern in type_patterns:
            m = re.search(pattern, tail, re.IGNORECASE)
            if m:
                itype = m.group(0)
                break
        if not itype and tail:
            itype = tail
        if itype:
            result['investment_type'] = itype
        return result

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts_by_context: Dict[str, List[Dict]] = defaultdict(list)

        # Standard facts
        standard_fact_pattern = re.compile(
            r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>',
            re.DOTALL
        )
        for concept, context_ref, value in standard_fact_pattern.findall(content):
            if value and context_ref:
                facts_by_context[context_ref].append({'concept': concept, 'value': value.strip()})

        # Inline facts + derived tokens/dates
        ix_fact_pattern = re.compile(
            r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>',
            re.DOTALL | re.IGNORECASE
        )
        for match in ix_fact_pattern.finditer(content):
            name = match.group(1)
            context_ref = match.group(2)
            value_html = match.group(4)
            if not context_ref:
                continue
            value_text = re.sub(r'<[^>]+>', '', value_html).strip()
            if value_text:
                facts_by_context[context_ref].append({'concept': name, 'value': value_text})

            start_idx = max(0, match.start() - 3000)
            end_idx = min(len(content), match.end() + 3000)
            window = content[start_idx:end_idx]

            # Reference rate with optional frequency like SOFR (Q/M/S)
            ref_freq = re.search(r'\b(SOFR|SONIA|PRIME|LIBOR|BASE RATE|EURIBOR)\b\s*(?:\((Q|M|S)\))?', window, re.IGNORECASE)
            if ref_freq:
                token = ref_freq.group(1).upper()
                freq = ref_freq.group(2).upper() if ref_freq.group(2) else None
                facts_by_context[context_ref].append({'concept': 'derived:ReferenceRateToken', 'value': f"{token} ({freq})" if freq else token})

            floor_match = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor_match:
                facts_by_context[context_ref].append({'concept': 'derived:FloorRate', 'value': floor_match.group(1)})

            pik_match = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik_match:
                facts_by_context[context_ref].append({'concept': 'derived:PIKRate', 'value': pik_match.group(1)})

            date_matches = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if date_matches:
                if len(date_matches) >= 2:
                    facts_by_context[context_ref].append({'concept': 'derived:AcquisitionDate', 'value': date_matches[0]})
                    facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': date_matches[-1]})
                else:
                    facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': date_matches[0]})

        return facts_by_context

    def _percent(self, s: str) -> str:
        try:
            v = float(s)
        except Exception:
            try:
                v = float(re.sub(r'[^\d\.\-]', '', s))
            except Exception:
                return f"{s}%"
        if 0 < abs(v) <= 1.0:
            v *= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[MAINInvestment]:
        if context['company_name'] == 'Unknown':
            return None

        investment = MAINInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )

        for fact in facts:
            concept = fact['concept']
            value_str = fact['value']
            value_str = value_str.replace(',', '')

            concept_lower = concept.lower()

            if any(k in concept_lower for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal']):
                try:
                    investment.principal_amount = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if ('cost' in concept_lower and ('amortized' in concept_lower or 'basis' in concept_lower)) or 'ownedatcost' in concept_lower:
                try:
                    investment.cost = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if 'fairvalue' in concept_lower or ('fair' in concept_lower and 'value' in concept_lower) or 'ownedatfairvalue' in concept_lower:
                try:
                    investment.fair_value = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue

            if 'investmentbasisspreadvariablerate' in concept_lower:
                investment.spread = self._percent(value_str)
                continue
            if 'investmentinterestrate' in concept_lower:
                investment.interest_rate = self._percent(value_str)
                continue
            if concept_lower == 'derived:referenceratetoken':
                investment.reference_rate = value_str.upper()
                continue
            if concept_lower == 'derived:floorrate':
                investment.floor_rate = self._percent(value_str)
                continue
            if concept_lower == 'derived:pikrate':
                investment.pik_rate = self._percent(value_str)
                continue
            if concept_lower == 'derived:acquisitiondate':
                investment.acquisition_date = value_str
                continue
            if concept_lower == 'derived:maturitydate':
                investment.maturity_date = value_str
                continue

        if not investment.acquisition_date and context.get('start_date'):
            investment.acquisition_date = context['start_date'][:10]

        if investment.company_name and (investment.principal_amount or investment.cost or investment.fair_value):
            return investment
        return None

    def _build_industry_index(self, content: str) -> Dict[str, str]:
        """Map instants to readable industry names using EquitySecuritiesByIndustryAxis if present."""
        industry_by_instant: Dict[str, str] = {}
        context_pattern = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        explicit_member_pattern = re.compile(
            r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>',
            re.DOTALL | re.IGNORECASE
        )
        for match in context_pattern.finditer(content):
            ctx_content = match.group(2)
            instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
            instant = instant_match.group(1) if instant_match else None
            if not instant:
                continue
            m = explicit_member_pattern.search(ctx_content)
            if not m:
                continue
            member_qname = m.group(1).strip()
            readable = self._industry_member_to_name(member_qname)
            if readable:
                industry_by_instant[instant] = readable
        return industry_by_instant

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local = qname.split(':', 1)[-1] if ':' in qname else qname
        local = re.sub(r'Member$', '', local)
        had_sector = False
        if local.endswith('Sector'):
            had_sector = True
            local = local[:-6]
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+', ' ', words).strip()
        return words if words else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = MAINExtractor()
    try:
        result = extractor.extract_from_ticker("MAIN")
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")

        print(f"\n[SAMPLE] Sample Investments:")
        for i, inv in enumerate(result['investments'][:5]):
            print(f"\n{i+1}. {inv.get('company_name', 'Unknown')}")
            print(f"   Type: {inv.get('investment_type', 'Unknown')}")
            if inv.get('maturity_date'):
                print(f"   Maturity: {inv.get('maturity_date')}")
            if inv.get('fair_value'):
                print(f"   Fair Value: ${float(inv.get('fair_value') or 0):,.0f}")

        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "MAIN_Main_Street_Capital_investments.csv")
        
        fieldnames = [
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
            'interest_rate', 'reference_rate', 'spread',
            'commitment_limit', 'undrawn_commitment'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for inv in result['investments']:
                # Apply standardization
                if 'investment_type' in inv:
                    inv['investment_type'] = standardize_investment_type(inv.get('investment_type'))
                if 'industry' in inv:
                    inv['industry'] = standardize_industry(inv.get('industry'))
                if 'reference_rate' in inv:
                    inv['reference_rate'] = standardize_reference_rate(inv.get('reference_rate')) or ''
                
                writer.writerow({k: (inv.get(k) if inv.get(k) is not None else '') for k in fieldnames})
        print(f"\n[SAVED] Results saved to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()



        except Exception:
            try:
                v = float(re.sub(r'[^\d\.\-]', '', s))
            except Exception:
                return f"{s}%"
        if 0 < abs(v) <= 1.0:
            v *= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[MAINInvestment]:
        if context['company_name'] == 'Unknown':
            return None

        investment = MAINInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )

        for fact in facts:
            concept = fact['concept']
            value_str = fact['value']
            value_str = value_str.replace(',', '')

            concept_lower = concept.lower()

            if any(k in concept_lower for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal']):
                try:
                    investment.principal_amount = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if ('cost' in concept_lower and ('amortized' in concept_lower or 'basis' in concept_lower)) or 'ownedatcost' in concept_lower:
                try:
                    investment.cost = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if 'fairvalue' in concept_lower or ('fair' in concept_lower and 'value' in concept_lower) or 'ownedatfairvalue' in concept_lower:
                try:
                    investment.fair_value = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue

            if 'investmentbasisspreadvariablerate' in concept_lower:
                investment.spread = self._percent(value_str)
                continue
            if 'investmentinterestrate' in concept_lower:
                investment.interest_rate = self._percent(value_str)
                continue
            if concept_lower == 'derived:referenceratetoken':
                investment.reference_rate = value_str.upper()
                continue
            if concept_lower == 'derived:floorrate':
                investment.floor_rate = self._percent(value_str)
                continue
            if concept_lower == 'derived:pikrate':
                investment.pik_rate = self._percent(value_str)
                continue
            if concept_lower == 'derived:acquisitiondate':
                investment.acquisition_date = value_str
                continue
            if concept_lower == 'derived:maturitydate':
                investment.maturity_date = value_str
                continue

        if not investment.acquisition_date and context.get('start_date'):
            investment.acquisition_date = context['start_date'][:10]

        if investment.company_name and (investment.principal_amount or investment.cost or investment.fair_value):
            return investment
        return None

    def _build_industry_index(self, content: str) -> Dict[str, str]:
        """Map instants to readable industry names using EquitySecuritiesByIndustryAxis if present."""
        industry_by_instant: Dict[str, str] = {}
        context_pattern = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        explicit_member_pattern = re.compile(
            r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>',
            re.DOTALL | re.IGNORECASE
        )
        for match in context_pattern.finditer(content):
            ctx_content = match.group(2)
            instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
            instant = instant_match.group(1) if instant_match else None
            if not instant:
                continue
            m = explicit_member_pattern.search(ctx_content)
            if not m:
                continue
            member_qname = m.group(1).strip()
            readable = self._industry_member_to_name(member_qname)
            if readable:
                industry_by_instant[instant] = readable
        return industry_by_instant

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local = qname.split(':', 1)[-1] if ':' in qname else qname
        local = re.sub(r'Member$', '', local)
        had_sector = False
        if local.endswith('Sector'):
            had_sector = True
            local = local[:-6]
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+', ' ', words).strip()
        return words if words else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = MAINExtractor()
    try:
        result = extractor.extract_from_ticker("MAIN")
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")

        print(f"\n[SAMPLE] Sample Investments:")
        for i, inv in enumerate(result['investments'][:5]):
            print(f"\n{i+1}. {inv.get('company_name', 'Unknown')}")
            print(f"   Type: {inv.get('investment_type', 'Unknown')}")
            if inv.get('maturity_date'):
                print(f"   Maturity: {inv.get('maturity_date')}")
            if inv.get('fair_value'):
                print(f"   Fair Value: ${float(inv.get('fair_value') or 0):,.0f}")

        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "MAIN_Main_Street_Capital_investments.csv")
        
        fieldnames = [
            'company_name', 'industry', 'business_description', 'investment_type',
            'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
            'interest_rate', 'reference_rate', 'spread',
            'commitment_limit', 'undrawn_commitment'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for inv in result['investments']:
                # Apply standardization
                if 'investment_type' in inv:
                    inv['investment_type'] = standardize_investment_type(inv.get('investment_type'))
                if 'industry' in inv:
                    inv['industry'] = standardize_industry(inv.get('industry'))
                if 'reference_rate' in inv:
                    inv['reference_rate'] = standardize_reference_rate(inv.get('reference_rate')) or ''
                
                writer.writerow({k: (inv.get(k) if inv.get(k) is not None else '') for k in fieldnames})
        print(f"\n[SAVED] Results saved to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


