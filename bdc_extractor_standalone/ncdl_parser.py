#!/usr/bin/env python3
"""
Custom NCDL (Nuveen Churchill Direct Lending Corp) Investment Extractor

Identifier examples (from inline XBRL InvestmentIdentifierAxis):
- "ERA Industries, LLC (BTX Precision), First Lien Debt"
- "First Lien Debt (Delayed Draw)"
- "Revolving Loan"
- "Subordinated Debt"

Captures reference spread (e.g., S + 4.75%), interest rates with Cash/PIK splits, dates, and amounts.
Includes latest-instant filtering and de-duplication; enriches industry via EquitySecuritiesByIndustryAxis.
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
class NCDLInvestment:
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


class NCDLExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "NCDL") -> Dict:
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
        return self.extract_from_url(txt_url, "Nuveen_Churchill_Direct_Lending_Corp", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        response = requests.get(filing_url, headers=self.headers)
        response.raise_for_status()
        content = response.text
        logger.info(f"Downloaded {len(content)} characters")

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")

        selected_instant = self._select_reporting_instant(contexts)
        if selected_instant:
            contexts = [c for c in contexts if c.get('instant') == selected_instant]
            logger.info(f"Filtered contexts to instant {selected_instant}: {len(contexts)} remaining")

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

        investments: List[NCDLInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # De-duplicate
        deduped: List[NCDLInvestment] = []
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

        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)

        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        for inv in investments:
            industry_breakdown[inv.industry] += 1
            investment_type_breakdown[inv.investment_type] += 1

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
            parsed = self._parse_ncdl_identifier(identifier)
            instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
            start_match = re.search(r'<startDate>([^<]+)</startDate>', ctx_content)
            end_match = re.search(r'<endDate>([^<]+)</endDate>', ctx_content)

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

    def _parse_ncdl_identifier(self, identifier: str) -> Dict[str, str]:
        result = {'company_name': 'Unknown', 'industry': 'Unknown', 'investment_type': 'Unknown'}
        if ',' in identifier:
            last_comma = identifier.rfind(',')
            company = identifier[:last_comma].strip()
            tail = identifier[last_comma + 1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        result['company_name'] = re.sub(r'\s+', ' ', company).rstrip(',')

        type_patterns = [
            r'First\s+Lien\s+Debt\s*\(Delayed\s+Draw\)$',
            r'First\s+Lien\s+Debt$',
            r'Revolving\s+Loan$',
            r'Subordinated\s+Debt$',
            r'Preferred\s+Equity$',
            r'Preferred\s+Stock$',
            r'Common\s+Stock$',
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
        standard_fact_pattern = re.compile(
            r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>',
            re.DOTALL
        )
        for concept, context_ref, value in standard_fact_pattern.findall(content):
            if value and context_ref:
                facts_by_context[context_ref].append({'concept': concept, 'value': value.strip()})

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

            # Reference rate tokens, including "S +" (SOFR/Secured Overnight Financing Rate often shortened to S)
            ref_match = re.search(r'\b(S\s*\+|SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref_match:
                token = ref_match.group(1)
                token_clean = 'SOFR' if token.strip().upper().startswith('S') else token.replace('+', '').upper()
                facts_by_context[context_ref].append({'concept': 'derived:ReferenceRateToken', 'value': token_clean})

            # Spread (e.g., S + 4.75%)
            spread_match = re.search(r'\b(?:S\s*\+|SOFR\s*\+)\s*([\d\.]+)\s*%?', window, re.IGNORECASE)
            if spread_match:
                facts_by_context[context_ref].append({'concept': 'derived:SpreadPct', 'value': spread_match.group(1)})

            # Cash/PIK split rates
            cash_match = re.search(r'(?:Cash)\)?\s*([\d\.]+)\s*%\s*\(Cash\)', window, re.IGNORECASE)
            if cash_match:
                facts_by_context[context_ref].append({'concept': 'derived:CashRate', 'value': cash_match.group(1)})
            pik_match = re.search(r'([\d\.]+)\s*%\s*\(PIK\)', window, re.IGNORECASE)
            if pik_match:
                facts_by_context[context_ref].append({'concept': 'derived:PIKRate', 'value': pik_match.group(1)})

            floor_match = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor_match:
                facts_by_context[context_ref].append({'concept': 'derived:FloorRate', 'value': floor_match.group(1)})

            date_matches = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if date_matches:
                if len(date_matches) >= 2:
                    facts_by_context[context_ref].append({'concept': 'derived:AcquisitionDate', 'value': date_matches[0]})
                    facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': date_matches[-1]})
                else:
                    facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': date_matches[0]})

        return facts_by_context

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[NCDLInvestment]:
        if context['company_name'] == 'Unknown':
            return None
        inv = NCDLInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        for fact in facts:
            concept = fact['concept']
            value_str = fact['value']
            value_str = value_str.replace(',', '')
            cl = concept.lower()
            if any(k in cl for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal']):
                try:
                    inv.principal_amount = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try:
                    inv.cost = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try:
                    inv.fair_value = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if cl == 'derived:referenceratetoken':
                inv.reference_rate = value_str.upper()
                continue
            if cl in ('derived:spreadpct',):
                inv.spread = f"{value_str}%"
                continue
            if cl in ('derived:cashrate',):
                # Represent as interest_rate when explicit cash is reported
                inv.interest_rate = f"{value_str}%"
                continue
            if cl in ('derived:pikrate',):
                inv.pik_rate = f"{value_str}%"
                continue
            if cl == 'derived:maturitydate':
                inv.maturity_date = value_str
                continue
            if cl == 'derived:acquisitiondate':
                inv.acquisition_date = value_str
                continue
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _build_industry_index(self, content: str) -> Dict[str, str]:
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
        if local.endswith('Sector'):
            local = local[:-6]
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+', ' ', words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates = []
        for c in contexts:
            inst = c.get('instant')
            if inst and re.match(r'^\d{4}-\d{2}-\d{2}$', inst):
                dates.append(inst)
        if not dates:
            return None
        return max(dates)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = NCDLExtractor()
    try:
        result = extractor.extract_from_ticker("NCDL")
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "NCDL_Nuveen_Churchill_Direct_Lending_Corp_investments.csv")
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate'
            ])
            writer.writeheader()
            for inv in result['investments']:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(inv.investment_type)
                standardized_industry = standardize_industry(inv.industry)
                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)
                
                writer.writerow({
                    'company_name': inv.company_name,
                    'industry': standardized_industry,
                    'business_description': inv.business_description,
                    'investment_type': standardized_inv_type,
                    'acquisition_date': inv.acquisition_date,
                    'maturity_date': inv.maturity_date,
                    'principal_amount': inv.principal_amount,
                    'cost': inv.cost,
                    'fair_value': inv.fair_value,
                    'interest_rate': inv.interest_rate,
                    'reference_rate': standardized_ref_rate,
                    'spread': inv.spread,
                    'floor_rate': inv.floor_rate,
                    'pik_rate': inv.pik_rate
                })
        print(f"\n[SAVED] Results saved to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()






Custom NCDL (Nuveen Churchill Direct Lending Corp) Investment Extractor

Identifier examples (from inline XBRL InvestmentIdentifierAxis):
- "ERA Industries, LLC (BTX Precision), First Lien Debt"
- "First Lien Debt (Delayed Draw)"
- "Revolving Loan"
- "Subordinated Debt"

Captures reference spread (e.g., S + 4.75%), interest rates with Cash/PIK splits, dates, and amounts.
Includes latest-instant filtering and de-duplication; enriches industry via EquitySecuritiesByIndustryAxis.
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
class NCDLInvestment:
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


class NCDLExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "NCDL") -> Dict:
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
        return self.extract_from_url(txt_url, "Nuveen_Churchill_Direct_Lending_Corp", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        response = requests.get(filing_url, headers=self.headers)
        response.raise_for_status()
        content = response.text
        logger.info(f"Downloaded {len(content)} characters")

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")

        selected_instant = self._select_reporting_instant(contexts)
        if selected_instant:
            contexts = [c for c in contexts if c.get('instant') == selected_instant]
            logger.info(f"Filtered contexts to instant {selected_instant}: {len(contexts)} remaining")

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

        investments: List[NCDLInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # De-duplicate
        deduped: List[NCDLInvestment] = []
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

        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)

        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        for inv in investments:
            industry_breakdown[inv.industry] += 1
            investment_type_breakdown[inv.investment_type] += 1

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
            parsed = self._parse_ncdl_identifier(identifier)
            instant_match = re.search(r'<instant>([^<]+)</instant>', ctx_content)
            start_match = re.search(r'<startDate>([^<]+)</startDate>', ctx_content)
            end_match = re.search(r'<endDate>([^<]+)</endDate>', ctx_content)

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

    def _parse_ncdl_identifier(self, identifier: str) -> Dict[str, str]:
        result = {'company_name': 'Unknown', 'industry': 'Unknown', 'investment_type': 'Unknown'}
        if ',' in identifier:
            last_comma = identifier.rfind(',')
            company = identifier[:last_comma].strip()
            tail = identifier[last_comma + 1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        result['company_name'] = re.sub(r'\s+', ' ', company).rstrip(',')

        type_patterns = [
            r'First\s+Lien\s+Debt\s*\(Delayed\s+Draw\)$',
            r'First\s+Lien\s+Debt$',
            r'Revolving\s+Loan$',
            r'Subordinated\s+Debt$',
            r'Preferred\s+Equity$',
            r'Preferred\s+Stock$',
            r'Common\s+Stock$',
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
        standard_fact_pattern = re.compile(
            r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>',
            re.DOTALL
        )
        for concept, context_ref, value in standard_fact_pattern.findall(content):
            if value and context_ref:
                facts_by_context[context_ref].append({'concept': concept, 'value': value.strip()})

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

            # Reference rate tokens, including "S +" (SOFR/Secured Overnight Financing Rate often shortened to S)
            ref_match = re.search(r'\b(S\s*\+|SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref_match:
                token = ref_match.group(1)
                token_clean = 'SOFR' if token.strip().upper().startswith('S') else token.replace('+', '').upper()
                facts_by_context[context_ref].append({'concept': 'derived:ReferenceRateToken', 'value': token_clean})

            # Spread (e.g., S + 4.75%)
            spread_match = re.search(r'\b(?:S\s*\+|SOFR\s*\+)\s*([\d\.]+)\s*%?', window, re.IGNORECASE)
            if spread_match:
                facts_by_context[context_ref].append({'concept': 'derived:SpreadPct', 'value': spread_match.group(1)})

            # Cash/PIK split rates
            cash_match = re.search(r'(?:Cash)\)?\s*([\d\.]+)\s*%\s*\(Cash\)', window, re.IGNORECASE)
            if cash_match:
                facts_by_context[context_ref].append({'concept': 'derived:CashRate', 'value': cash_match.group(1)})
            pik_match = re.search(r'([\d\.]+)\s*%\s*\(PIK\)', window, re.IGNORECASE)
            if pik_match:
                facts_by_context[context_ref].append({'concept': 'derived:PIKRate', 'value': pik_match.group(1)})

            floor_match = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor_match:
                facts_by_context[context_ref].append({'concept': 'derived:FloorRate', 'value': floor_match.group(1)})

            date_matches = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if date_matches:
                if len(date_matches) >= 2:
                    facts_by_context[context_ref].append({'concept': 'derived:AcquisitionDate', 'value': date_matches[0]})
                    facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': date_matches[-1]})
                else:
                    facts_by_context[context_ref].append({'concept': 'derived:MaturityDate', 'value': date_matches[0]})

        return facts_by_context

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[NCDLInvestment]:
        if context['company_name'] == 'Unknown':
            return None
        inv = NCDLInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        for fact in facts:
            concept = fact['concept']
            value_str = fact['value']
            value_str = value_str.replace(',', '')
            cl = concept.lower()
            if any(k in cl for k in ['principalamount', 'ownedbalanceprincipalamount', 'outstandingprincipal']):
                try:
                    inv.principal_amount = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try:
                    inv.cost = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try:
                    inv.fair_value = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if cl == 'derived:referenceratetoken':
                inv.reference_rate = value_str.upper()
                continue
            if cl in ('derived:spreadpct',):
                inv.spread = f"{value_str}%"
                continue
            if cl in ('derived:cashrate',):
                # Represent as interest_rate when explicit cash is reported
                inv.interest_rate = f"{value_str}%"
                continue
            if cl in ('derived:pikrate',):
                inv.pik_rate = f"{value_str}%"
                continue
            if cl == 'derived:maturitydate':
                inv.maturity_date = value_str
                continue
            if cl == 'derived:acquisitiondate':
                inv.acquisition_date = value_str
                continue
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _build_industry_index(self, content: str) -> Dict[str, str]:
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
        if local.endswith('Sector'):
            local = local[:-6]
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+', ' ', words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates = []
        for c in contexts:
            inst = c.get('instant')
            if inst and re.match(r'^\d{4}-\d{2}-\d{2}$', inst):
                dates.append(inst)
        if not dates:
            return None
        return max(dates)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = NCDLExtractor()
    try:
        result = extractor.extract_from_ticker("NCDL")
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "NCDL_Nuveen_Churchill_Direct_Lending_Corp_investments.csv")
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate'
            ])
            writer.writeheader()
            for inv in result['investments']:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(inv.investment_type)
                standardized_industry = standardize_industry(inv.industry)
                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)
                
                writer.writerow({
                    'company_name': inv.company_name,
                    'industry': standardized_industry,
                    'business_description': inv.business_description,
                    'investment_type': standardized_inv_type,
                    'acquisition_date': inv.acquisition_date,
                    'maturity_date': inv.maturity_date,
                    'principal_amount': inv.principal_amount,
                    'cost': inv.cost,
                    'fair_value': inv.fair_value,
                    'interest_rate': inv.interest_rate,
                    'reference_rate': standardized_ref_rate,
                    'spread': inv.spread,
                    'floor_rate': inv.floor_rate,
                    'pik_rate': inv.pik_rate
                })
        print(f"\n[SAVED] Results saved to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()





