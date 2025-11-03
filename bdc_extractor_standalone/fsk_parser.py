#!/usr/bin/env python3
"""
FSK (FS KKR Capital Corp) Investment Extractor

Strategy:
1) XBRL-first: parse InvestmentIdentifierAxis contexts if present (preferred)
2) Fallback: parse primary HTML filing tables via FlexibleTableParser

Outputs standardized CSV at output/FSK_FS_KKR_Capital_Corp_investments.csv
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass
import os
import csv
import requests

from sec_api_client import SECAPIClient
from flexible_table_parser import FlexibleTableParser
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class FSKInvestment:
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


class FSKExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.table_parser = FlexibleTableParser()

    def extract_from_ticker(self, ticker: str = "FSK") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        logger.info(f"Found CIK: {cik}")

        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        logger.info(f"Found filing index: {index_url}")

        accession_match = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not accession_match:
            raise ValueError(f"Could not parse accession number from {index_url}")
        accession = accession_match.group(1)
        accession_no_hyphens = accession.replace('-', '')

        # Try XBRL text bundle first
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        logger.info(f"XBRL URL: {txt_url}")

        try:
            return self.extract_xbrl(txt_url, "FS_KKR_Capital_Corp", cik)
        except Exception as e:
            logger.warning(f"XBRL extraction failed: {e}. Falling back to HTML table parsing.")
            return self.extract_html(index_url, "FS_KKR_Capital_Corp", cik)

    def extract_xbrl(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        resp = requests.get(filing_url, headers=self.headers)
        resp.raise_for_status()
        content = resp.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} InvestmentIdentifierAxis contexts")
        if not contexts:
            raise ValueError("No investment contexts found in XBRL")

        # Latest instant filter
        selected_instant = self._select_reporting_instant(contexts)
        if selected_instant:
            contexts = [c for c in contexts if c.get('instant') == selected_instant]
            logger.info(f"Filtered contexts to instant {selected_instant}: {len(contexts)} remaining")

        # Industry enrichment
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

        investments: List[FSKInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # De-dup
        deduped: List[FSKInvestment] = []
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

        return self._to_result(company_name, cik, investments)

    def extract_html(self, index_url: str, company_name: str, cik: str) -> Dict:
        # Use SEC client to pick the main HTML doc and parse tables
        docs = self.sec_client.get_documents_from_index(index_url)
        main_doc = None
        for d in docs:
            fn = d.filename.lower()
            if fn.endswith('.htm') and 'index' not in fn:
                main_doc = d
                break
        if not main_doc:
            raise ValueError("Could not find main HTML document for parsing")

        logger.info(f"Parsing HTML: {main_doc.url}")
        investments = self.table_parser.parse_html_filing(main_doc.url)

        # Convert parsed dicts into standardized rows
        std_investments: List[FSKInvestment] = []
        for it in investments:
            std_investments.append(FSKInvestment(
                company_name=it.get('company_name') or it.get('company') or '',
                business_description=it.get('business_description'),
                investment_type=it.get('investment_type') or it.get('type') or 'Unknown',
                industry=it.get('industry') or 'Unknown',
                acquisition_date=it.get('acquisition_date'),
                maturity_date=it.get('maturity_date'),
                principal_amount=it.get('principal_amount') or it.get('principal'),
                cost=it.get('cost') or it.get('amortized_cost'),
                fair_value=it.get('fair_value'),
                interest_rate=it.get('interest_rate'),
                reference_rate=it.get('reference_rate'),
                spread=it.get('spread'),
                floor_rate=it.get('floor_rate'),
                pik_rate=it.get('pik_rate')
            ))

        # De-dup
        deduped: List[FSKInvestment] = []
        seen = set()
        for inv in std_investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val_key = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val_key)
            if combo in seen:
                continue
            seen.add(combo)
            deduped.append(inv)

        return self._to_result(company_name, cik, deduped)

    def _to_result(self, company_name: str, cik: str, investments: List[FSKInvestment]) -> Dict:
        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        industry_breakdown = defaultdict(int)
        type_breakdown = defaultdict(int)
        for inv in investments:
            industry_breakdown[inv.industry] += 1
            type_breakdown[inv.investment_type] += 1
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'investments': investments,
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(type_breakdown)
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
            parsed = self._parse_identifier(identifier)
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

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        result = {'company_name': 'Unknown', 'industry': 'Unknown', 'investment_type': 'Unknown'}
        # Generic: split on last comma; tail is type
        if ',' in identifier:
            last_comma = identifier.rfind(',')
            company = identifier[:last_comma].strip()
            tail = identifier[last_comma + 1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        result['company_name'] = re.sub(r'\s+', ' ', company).rstrip(',')

        type_patterns = [
            r'One\s+stop\s*\d*$',
            r'Senior\s+secured\s*\d*$',
            r'Secured\s+Debt\s*\d*$',
            r'Unitranche\s*\d*$',
            r'First\s+lien\s+.*$',
            r'Second\s+lien\s+.*$',
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

            ref_match = re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref_match:
                token = ref_match.group(1)
                facts_by_context[context_ref].append({'concept': 'derived:ReferenceRateToken', 'value': token.replace('+', '').upper()})

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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[FSKInvestment]:
        if context['company_name'] == 'Unknown':
            return None
        investment = FSKInvestment(
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
                    investment.principal_amount = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try:
                    investment.cost = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try:
                    investment.fair_value = float(value_str)
                except (ValueError, TypeError):
                    pass
                continue
            if 'investmentbasisspreadvariablerate' in cl:
                investment.spread = self._format_percent(value_str)
                continue
            if 'investmentinterestrate' in cl:
                investment.interest_rate = self._format_percent(value_str)
                continue
            if cl == 'derived:referenceratetoken':
                investment.reference_rate = value_str.upper()
                continue
            if cl == 'derived:floorrate':
                investment.floor_rate = self._format_percent(value_str)
                continue
            if cl == 'derived:pikrate':
                investment.pik_rate = self._format_percent(value_str)
                continue
            if cl == 'derived:acquisitiondate':
                investment.acquisition_date = value_str
                continue
            if cl == 'derived:maturitydate':
                investment.maturity_date = value_str
                continue
        if not investment.acquisition_date and context.get('start_date'):
            investment.acquisition_date = context['start_date'][:10]
        if investment.company_name and (investment.principal_amount or investment.cost or investment.fair_value):
            return investment
        return None

    def _format_percent(self, value_str: str) -> str:
        """Normalize percent strings: if 0<value<=1 assume fraction and scale by 100."""
        try:
            v = float(value_str)
        except Exception:
            return f"{value_str}%"
        if 0 < abs(v) <= 1.0:
            v = v * 100.0
        # Use up to 4 decimals, trim trailing zeros
        s = f"{v:.4f}"
        s = s.rstrip('0').rstrip('.')
        return f"{s}%"


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = FSKExtractor()
    try:
        result = extractor.extract_from_ticker("FSK")
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")

        print(f"\n[SAMPLE] Sample Investments:")
        for i, inv in enumerate(result['investments'][:5]):
            print(f"\n{i+1}. {inv.company_name}")
            print(f"   Type: {inv.investment_type}")
            if inv.maturity_date:
                print(f"   Maturity: {inv.maturity_date}")
            if inv.fair_value:
                print(f"   Fair Value: ${inv.fair_value:,.0f}")

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "FSK_FS_KKR_Capital_Corp_investments.csv")
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




if __name__ == "__main__":
    main()



