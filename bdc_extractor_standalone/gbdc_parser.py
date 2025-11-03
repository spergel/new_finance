#!/usr/bin/env python3
"""
Custom GBDC (Golub Capital BDC Inc) Investment Extractor

Identifier examples:
- "PPW Aero Buyer, Inc., One stop 1/2/3/4/5"
- "RJW Group Holdings, Inc., One stop 1/2"
- "Covercraft Parent III, Inc., Senior secured 1/2/3"

We parse company and type from InvestmentIdentifierAxis; enrich industry using
EquitySecuritiesByIndustryAxis (namespace often `gbdc:` like `gbdc:AerospaceAndDefenseSectorMember`).
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
class GBDCInvestment:
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


class GBDCExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def _normalize_company_name(self, raw: str) -> str:
        name = raw or ''
        name = re.sub(r'\s*\*\*\*\s*$', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        # Remove embedded instrument suffixes commonly present in identifier tails
        name = re.sub(r',\s*One\s*stop\b.*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r',\s*Senior\s+secured\b.*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r',\s*Secured\s+Debt\b.*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r',\s*Unsecured\s+Debt\b.*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r',\s*Term\s+Loan\b.*$', '', name, flags=re.IGNORECASE)
        # Normalize commas before entity suffixes
        name = re.sub(r',\s+(Inc|LLC|Ltd|Corp|Co|LP)\.?\b', r' \1', name, flags=re.IGNORECASE)
        # Normalize punctuation in suffixes
        name = re.sub(r'\bInc\.\b', 'Inc', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLLC\.?\b', 'LLC', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLtd\.\b', 'Ltd', name, flags=re.IGNORECASE)
        name = re.sub(r'\bCorp\.\b', 'Corp', name, flags=re.IGNORECASE)
        name = re.sub(r'\bCo\.\b', 'Co', name, flags=re.IGNORECASE)
        return name.rstrip('., ').strip()

    def _percent(self, s: str) -> str:
        try:
            v = float(s)
        except Exception:
            # If already like '10.5', still append % below
            try:
                v = float(re.sub(r'[^\d\.\-]', '', s))
            except Exception:
                return f"{s}%"
        if 0 < abs(v) <= 1.0:
            v *= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _normalize_gbdc_row(self, inv: GBDCInvestment) -> Dict:
        row = {
            'company_name': inv.company_name or '',
            'industry': inv.industry or '',
            'business_description': inv.business_description or '',
            'investment_type': inv.investment_type or 'Unknown',
            'acquisition_date': inv.acquisition_date or '',
            'maturity_date': inv.maturity_date or '',
            'principal_amount': inv.principal_amount if inv.principal_amount is not None else '',
            'cost': inv.cost if inv.cost is not None else '',
            'fair_value': inv.fair_value if inv.fair_value is not None else '',
            'interest_rate': inv.interest_rate or '',
            'reference_rate': inv.reference_rate or '',
            'spread': inv.spread or '',
            'commitment_limit': '',
            'undrawn_commitment': ''
        }
        row['company_name'] = self._normalize_company_name(row['company_name'])
        it = (row['investment_type'] or '').lower()
        cname_l = row['company_name'].lower()
        if 'one stop' in it:
            row['investment_type'] = 'Unitranche loan'
        elif 'senior secured' in it or 'secured debt' in it or 'first lien' in it:
            row['investment_type'] = 'First lien senior secured loan'
        elif 'second lien' in it:
            row['investment_type'] = 'Second lien senior secured loan'
        elif 'unsecured' in it:
            row['investment_type'] = 'Unsecured debt'
        elif 'preferred' in it or 'preferred' in cname_l:
            row['investment_type'] = 'Preferred equity'
        elif 'warrant' in it or 'warrants' in cname_l:
            row['investment_type'] = 'Warrants'
        elif 'common stock' in it or 'member units' in it or 'equity' in it:
            row['investment_type'] = 'Equity'
        # Numeric coercion
        for field in ['principal_amount', 'cost', 'fair_value']:
            val = row[field]
            if isinstance(val, str):
                try:
                    cleaned = val.replace(',', '').strip()
                    row[field] = float(cleaned) if cleaned else ''
                except Exception:
                    row[field] = ''
        return row

    def extract_from_ticker(self, ticker: str = "GBDC") -> Dict:
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
        return self.extract_from_url(txt_url, "Golub_Capital_BDC_Inc", cik)

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

        investments: List[GBDCInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # De-duplicate
        deduped: List[GBDCInvestment] = []
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

        # Normalize and de-duplicate by (company_name, investment_type)
        normalized_rows: List[Dict] = []
        seen_keys = set()
        for inv in investments:
            r = self._normalize_gbdc_row(inv)
            has_fin = any(bool(r.get(f)) for f in ['principal_amount','cost','fair_value'])
            if not has_fin:
                continue
            key = (r['company_name'].lower(), r['investment_type'].lower())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            normalized_rows.append(r)

        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(normalized_rows),
            'investments': normalized_rows,
            'total_principal': sum(float(r['principal_amount']) for r in normalized_rows if isinstance(r.get('principal_amount'), (int,float))),
            'total_cost': sum(float(r['cost']) for r in normalized_rows if isinstance(r.get('cost'), (int,float))),
            'total_fair_value': sum(float(r['fair_value']) for r in normalized_rows if isinstance(r.get('fair_value'), (int,float))),
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
            parsed = self._parse_gbdc_identifier(identifier)
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

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates = []
        for c in contexts:
            inst = c.get('instant')
            if inst and re.match(r'^\d{4}-\d{2}-\d{2}$', inst):
                dates.append(inst)
        if not dates:
            return None
        return max(dates)

    def _parse_gbdc_identifier(self, identifier: str) -> Dict[str, str]:
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
            r'One\s+stop\s*\d*$',
            r'Senior\s+secured\s*\d*$',
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[GBDCInvestment]:
        if context['company_name'] == 'Unknown':
            return None
        investment = GBDCInvestment(
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
                investment.floor_rate = f"{value_str}%"
                continue
            if concept_lower == 'derived:pikrate':
                investment.pik_rate = f"{value_str}%"
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
        if local.endswith('Sector'):
            local = local[:-6]
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+', ' ', words).strip()
        return words if words else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = GBDCExtractor()
    try:
        result = extractor.extract_from_ticker("GBDC")
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")

        print(f"\n[SAMPLE] Sample Investments:")
        for i, inv in enumerate(result['investments'][:5]):
            print(f"\n{i+1}. {inv.get('company_name','Unknown')}")
            print(f"   Type: {inv.get('investment_type','Unknown')}")
            if inv.get('maturity_date'):
                print(f"   Maturity: {inv.get('maturity_date')}")
            if inv.get('fair_value'):
                try:
                    fv = float(inv.get('fair_value') or 0)
                    print(f"   Fair Value: ${fv:,.0f}")
                except Exception:
                    pass

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "GBDC_Golub_Capital_BDC_Inc_investments.csv")
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'commitment_limit', 'undrawn_commitment'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in result['investments']:
                # Apply standardization
                if 'investment_type' in r:
                    r['investment_type'] = standardize_investment_type(r.get('investment_type'))
                if 'industry' in r:
                    r['industry'] = standardize_industry(r.get('industry'))
                if 'reference_rate' in r:
                    r['reference_rate'] = standardize_reference_rate(r.get('reference_rate')) or ''
                
                writer.writerow({k: (r.get(k) if r.get(k) is not None else '') for k in fieldnames})
        print(f"\n[SAVED] Results saved to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()



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
        if local.endswith('Sector'):
            local = local[:-6]
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+', ' ', words).strip()
        return words if words else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    extractor = GBDCExtractor()
    try:
        result = extractor.extract_from_ticker("GBDC")
        print(f"\n[SUCCESS] Extracted {result['total_investments']} investments")
        print(f"  Total Principal: ${result['total_principal']:,.0f}")
        print(f"  Total Cost: ${result['total_cost']:,.0f}")
        print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")

        print(f"\n[SAMPLE] Sample Investments:")
        for i, inv in enumerate(result['investments'][:5]):
            print(f"\n{i+1}. {inv.get('company_name','Unknown')}")
            print(f"   Type: {inv.get('investment_type','Unknown')}")
            if inv.get('maturity_date'):
                print(f"   Maturity: {inv.get('maturity_date')}")
            if inv.get('fair_value'):
                try:
                    fv = float(inv.get('fair_value') or 0)
                    print(f"   Fair Value: ${fv:,.0f}")
                except Exception:
                    pass

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "GBDC_Golub_Capital_BDC_Inc_investments.csv")
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'commitment_limit', 'undrawn_commitment'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in result['investments']:
                # Apply standardization
                if 'investment_type' in r:
                    r['investment_type'] = standardize_investment_type(r.get('investment_type'))
                if 'industry' in r:
                    r['industry'] = standardize_industry(r.get('industry'))
                if 'reference_rate' in r:
                    r['reference_rate'] = standardize_reference_rate(r.get('reference_rate')) or ''
                
                writer.writerow({k: (r.get(k) if r.get(k) is not None else '') for k in fieldnames})
        print(f"\n[SAVED] Results saved to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


