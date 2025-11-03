#!/usr/bin/env python3
"""
CCAP (Crescent Capital BDC Inc) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filter; de-dup; industry enrichment.
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
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class CCAPInvestment:
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


class CCAPExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "CCAP") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        acc = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not acc:
            raise ValueError("Could not parse accession number")
        accession = acc.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Crescent_Capital_BDC_Inc", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        resp = requests.get(filing_url, headers=self.headers)
        resp.raise_for_status()
        content = resp.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
            logger.info(f"Filtered contexts to instant {sel}: {len(contexts)} remaining")

        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]

        facts_by_context = self._extract_facts(content)
        investments: List[CCAPInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # de-dup
        ded = []
        seen = set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen:
                continue
            seen.add(combo)
            ded.append(inv)
        investments = ded

        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        ind_br = defaultdict(int)
        type_br = defaultdict(int)
        for inv in investments:
            ind_br[inv.industry] += 1
            type_br[inv.investment_type] += 1

        out_dir = 'output'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'CCAP_Crescent_Capital_BDC_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
            ])
            writer.writeheader()
            for inv in investments:
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
                    'pik_rate': inv.pik_rate,
                })

        logger.info(f"Saved to {out_file}")
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(ind_br),
            'investment_type_breakdown': dict(type_br)
        }

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        contexts: List[Dict] = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1)
            chtml = m.group(2)
            tm = tp.search(chtml)
            if not tm:
                continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', chtml)
            sd = re.search(r'<startDate>([^<]+)</startDate>', chtml)
            ed = re.search(r'<endDate>([^<]+)</endDate>', chtml)
            same_ind = None
            sm = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', chtml, re.DOTALL|re.IGNORECASE)
            if sm:
                same_ind = self._industry_member_to_name(sm.group(1).strip())
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'business_description': parsed.get('business_description'),
                'investment_type': parsed['investment_type'],
                'maturity_date': parsed.get('maturity_date'),
                'acquisition_date': parsed.get('acquisition_date'),
                'pik_rate': parsed.get('pik_rate'),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # CCAP format: "Investments [Country] Debt Investments [Industry] [Company Name] Investment Type [Type] Interest Term S + [Spread] ([Floor] Floor) Interest Rate [Rate] Maturity/ Dissolution Date [Date]"
        # Or: "Equity Investments [Industry] [Company Name] Investment Type [Type]"
        
        # Extract dates first
        maturity_match = re.search(r'Maturity[^\d]*Dissolution\s+Date\s+(\d{1,2}/\d{4}|\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            date_str = maturity_match.group(1)
            # Handle MM/YYYY format (no day)
            if '/' in date_str and len(date_str.split('/')) == 2:
                month, year = date_str.split('/')
                date_str = f"{month}/01/{year}"
            # Normalize 2-digit year to 4-digit
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        # Extract reference rate and spread - pattern: "Interest Term S + 650" or "Interest Term SN + 625"
        # S = SOFR, E = EURIBOR, etc.
        ref_spread_match = re.search(r'Interest\s+Term\s+([SEN])\s*\+\s*(\d+)', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            rate_letter = ref_spread_match.group(1).upper()
            spread_val = ref_spread_match.group(2)
            if rate_letter == 'S':
                res['reference_rate'] = 'SOFR'
            elif rate_letter == 'E':
                res['reference_rate'] = 'EURIBOR'
            elif rate_letter == 'N':
                res['reference_rate'] = 'EURIBOR'  # SN might be EURIBOR
            else:
                res['reference_rate'] = rate_letter
            
            # Spread is in basis points, convert to percentage
            try:
                spread_bps = float(spread_val)
                spread_pct = spread_bps / 100.0
                res['spread'] = self._percent(str(spread_pct))
            except:
                res['spread'] = self._percent(spread_val)
        
        # Extract floor rate - pattern: "(100 Floor)" or "(75 Floor)"
        floor_match = re.search(r'\((\d+)\s*Floor\)', ident_clean, re.IGNORECASE)
        if floor_match:
            floor_bps = floor_match.group(1)
            try:
                floor_val = float(floor_bps) / 100.0  # Convert basis points to percentage
                res['floor_rate'] = self._percent(str(floor_val))
            except:
                res['floor_rate'] = self._percent(floor_bps)
        
        # Extract PIK rate - pattern: "(plus 200 PIK)" or "(plus 400 PIK)"
        pik_match = re.search(r'\(plus\s+(\d+)\s*PIK\)', ident_clean, re.IGNORECASE)
        if pik_match:
            pik_bps = pik_match.group(1)
            try:
                pik_val = float(pik_bps) / 100.0  # Convert basis points to percentage
                res['pik_rate'] = self._percent(str(pik_val))
            except:
                res['pik_rate'] = self._percent(pik_bps)
        
        # Extract interest rate - pattern: "Interest Rate 10.93" or "Interest Rate 8.80%"
        interest_rate_match = re.search(r'Interest\s+Rate\s+([\d\.]+)\s*%?', ident_clean, re.IGNORECASE)
        if interest_rate_match:
            res['interest_rate'] = self._percent(interest_rate_match.group(1))
        
        # Remove prefix: "Investments [Country] Debt Investments" or "Equity Investments"
        ident_clean = re.sub(r'^Investments\s+(?:United\s+States|United\s+Kingdom|Sweden|Canada)\s+Debt\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^Equity\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        
        # Extract industry - it comes after the prefix, before company name
        # Common industries in CCAP: "Health Care Equipment & Services", "Software & Services", "Commercial & Professional Services", "Consumer Services", "Diversified Financials", "Pharmaceuticals", "Retailing"
        common_industries = [
            'Health Care Equipment & Services', 'Software & Services', 'Commercial & Professional Services',
            'Consumer Services', 'Diversified Financials', 'Pharmaceuticals', 'Retailing',
            'Software', 'Commercial', 'Health Care', 'Consumer'
        ]
        
        industry_found = None
        industry_end_pos = 0
        
        for ind in common_industries:
            # Match industry as a phrase
            pattern = r'^' + re.escape(ind) + r'\s+'
            match = re.match(pattern, ident_clean, re.IGNORECASE)
            if match:
                industry_found = ind
                industry_end_pos = match.end()
                break
        
        if industry_found:
            res['industry'] = industry_found
        else:
            # Try to extract first few words as industry
            words = ident_clean.split()
            if len(words) >= 2:
                potential_industry = ' '.join(words[:2])
                if any(kw in potential_industry.lower() for kw in ['services', 'equipment', 'care', 'software', 'commercial', 'consumer']):
                    res['industry'] = potential_industry
                    industry_end_pos = len(potential_industry)
        
        # Text after industry (company name + investment type + rates)
        after_industry = ident_clean[industry_end_pos:].strip() if industry_end_pos > 0 else ident_clean
        
        # Extract investment type - look for "Investment Type" or patterns
        inv_type_patterns = [
            r'Investment\s+Type\s+(Unitranche\s+)?(First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|First\s+Lien\s+Term\s+Loan|First\s+Lien\s+Revolver|Senior\s+Secured\s+First\s+Lien\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Revolver|Common\s+Stock)',
            r'(Unitranche\s+)?First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Senior\s+Secured\s+First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Common\s+Stock'
        ]
        
        inv_type_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, after_industry, re.IGNORECASE)
            if match:
                inv_type_match = match
                inv_type_text = match.group(0)
                # Clean up
                inv_type_text = re.sub(r'\s+', ' ', inv_type_text).strip()
                # Normalize
                if 'Unitranche' in inv_type_text:
                    res['investment_type'] = inv_type_text
                elif 'First Lien Term Loan' in inv_type_text or 'First Lien Delayed Draw Term Loan' in inv_type_text:
                    res['investment_type'] = 'First Lien Debt'
                elif 'First Lien Revolver' in inv_type_text:
                    res['investment_type'] = 'First Lien Revolver'
                elif 'Common Stock' in inv_type_text:
                    res['investment_type'] = 'Common Equity'
                else:
                    res['investment_type'] = inv_type_text
                break
        
        # Extract company name - it's between industry and investment type
        if inv_type_match:
            company_text = after_industry[:inv_type_match.start()].strip()
        else:
            # Look for stop words before rate info
            stop_pattern = r'(Interest\s+Term|Investment\s+Type)'
            stop_match = re.search(stop_pattern, after_industry, re.IGNORECASE)
            if stop_match:
                company_text = after_industry[:stop_match.start()].strip()
            else:
                company_text = after_industry.split('Interest Term')[0].strip() if 'Interest Term' in after_industry else after_industry
        
        # Clean up company name - remove trailing "One" or investment type mentions
        company_text = re.sub(r'\s+One\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment\s+Type\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment&#160;Type\s*$', '', company_text, flags=re.IGNORECASE)
        
        # Remove industry prefixes that may have leaked in (e.g., "Equipment & Services" at start)
        # But be careful not to remove actual company name words
        industry_prefixes = [
            r'^Equipment\s+&amp;\s+Services\s+',
            r'^&amp;\s+Services\s+',
            r'^&amp;\s+Professional\s+Services\s+',
            r'^Pharmaceuticals,\s+Biotechnology\s+&amp;\s+Life\s+Sciences\s+',
        ]
        for prefix_pattern in industry_prefixes:
            company_text = re.sub(prefix_pattern, '', company_text, flags=re.IGNORECASE)
        
        # Clean up HTML entities
        company_text = company_text.replace('&amp;', '&')
        company_text = company_text.replace('&#160;', ' ')
        
        # Remove trailing commas and clean up
        company_text = company_text.rstrip(',')
        company_text = self._strip_footnote_refs(company_text)
        
        # If company name starts with "&" or common industry words, try to find actual entity name
        if company_text and (company_text.startswith('&') or any(company_text.lower().startswith(p.split()[0].lower()) for p in ['Equipment', 'Software', 'Commercial', 'Health Care'])):
            # Try to find entity pattern (LLC, Inc., Corp, etc.)
            entity_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|S\.A\.R\.L\.|AB|plc)(?:\s|$|,|\))', company_text, re.IGNORECASE)
            if entity_match:
                # Extract entity name and type
                entity_full = entity_match.group(0).strip()
                # Remove any leading industry words
                for prefix_pattern in industry_prefixes:
                    entity_full = re.sub(prefix_pattern, '', entity_full, flags=re.IGNORECASE)
                entity_full = entity_full.replace('&amp;', '&').strip()
                if entity_full:
                    company_text = entity_full
        
        if company_text and len(company_text) > 2:
            res['company_name'] = company_text
        
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
        for concept, cref, val in sp.findall(content):
            if val and cref:
                facts[cref].append({'concept': concept, 'value': val.strip()})
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1); cref = m.group(2); html = m.group(4)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                facts[cref].append({'concept': name, 'value': txt})
            start = max(0, m.start()-3000); end = min(len(content), m.end()+3000)
            window = content[start:end]
            ref = re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref:
                facts[cref].append({'concept':'derived:ReferenceRateToken','value': ref.group(1).replace('+','').upper()})
            floor = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor:
                facts[cref].append({'concept':'derived:FloorRate','value': floor.group(1)})
            pik = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik:
                facts[cref].append({'concept':'derived:PIKRate','value': pik.group(1)})
            dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[CCAPInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = CCAPInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v = v.replace(',',''); cl=c.lower()
            if any(k in cl for k in ['principalamount','ownedbalanceprincipalamount','outstandingprincipal']):
                try: inv.principal_amount=float(v)
                except: pass; continue
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: inv.cost=float(v)
                except: pass; continue
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: inv.fair_value=float(v)
                except: pass; continue
                continue
            if 'investmentbasisspreadvariablerate' in cl:
                inv.spread = self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v); continue
            if cl=='derived:referenceratetoken':
                inv.reference_rate = v.upper(); continue
            if cl=='derived:floorrate':
                inv.floor_rate = self._percent(v); continue
            if cl=='derived:pikrate':
                inv.pik_rate = self._percent(v); continue
            if cl=='derived:acquisitiondate':
                inv.acquisition_date = v; continue
            if cl=='derived:maturitydate':
                inv.maturity_date = v; continue
        # Fill missing fields from parsed identifier
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _percent(self, s: str) -> str:
        try:
            v=float(s)
        except:
            return f"{s}%"
        if 0<abs(v)<=1.0:
            v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={} ; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        ep=re.compile(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', re.DOTALL|re.IGNORECASE)
        for mm in cp.finditer(content):
            html=mm.group(2)
            inst=re.search(r'<instant>([^<]+)</instant>', html)
            inst=inst.group(1) if inst else None
            if not inst: continue
            em=ep.search(html)
            if not em: continue
            m[inst]=self._industry_member_to_name(em.group(1).strip())
        return m

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local=qname.split(':',1)[-1] if ':' in qname else qname
        local=re.sub(r'Member$','',local)
        if local.endswith('Sector'): local=local[:-6]
        words=re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words=re.sub(r'\bAnd\b','and',words)
        words=re.sub(r'\s+',' ',words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates=[c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=CCAPExtractor()
    try:
        res=ex.extract_from_ticker('CCAP')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""
CCAP (Crescent Capital BDC Inc) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filtering; de-dup; industry enrichment.
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
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class CCAPInvestment:
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


class CCAPExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "CCAP") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Crescent_Capital_BDC_Inc", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        resp = requests.get(filing_url, headers=self.headers)
        resp.raise_for_status()
        content = resp.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
            logger.info(f"Filtered contexts to instant {sel}: {len(contexts)} remaining")

        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]

        facts_by_context = self._extract_facts(content)
        investments: List[CCAPInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # de-dup
        ded = []
        seen = set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen:
                continue
            seen.add(combo)
            ded.append(inv)
        investments = ded

        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        ind_br = defaultdict(int)
        type_br = defaultdict(int)
        for inv in investments:
            ind_br[inv.industry] += 1
            type_br[inv.investment_type] += 1

        out_dir = 'output'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'CCAP_Crescent_Capital_BDC_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
            ])
            writer.writeheader()
            for inv in investments:
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
                    'pik_rate': inv.pik_rate,
                })

        logger.info(f"Saved to {out_file}")
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(ind_br),
            'investment_type_breakdown': dict(type_br)
        }

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        contexts: List[Dict] = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1)
            chtml = m.group(2)
            tm = tp.search(chtml)
            if not tm:
                continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', chtml)
            sd = re.search(r'<startDate>([^<]+)</startDate>', chtml)
            ed = re.search(r'<endDate>([^<]+)</endDate>', chtml)
            same_ind = None
            sm = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', chtml, re.DOTALL|re.IGNORECASE)
            if sm:
                same_ind = self._industry_member_to_name(sm.group(1).strip())
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'business_description': parsed.get('business_description'),
                'investment_type': parsed['investment_type'],
                'maturity_date': parsed.get('maturity_date'),
                'acquisition_date': parsed.get('acquisition_date'),
                'pik_rate': parsed.get('pik_rate'),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # CCAP format: "Investments [Country] Debt Investments [Industry] [Company Name] Investment Type [Type] Interest Term S + [Spread] ([Floor] Floor) Interest Rate [Rate] Maturity/ Dissolution Date [Date]"
        # Or: "Equity Investments [Industry] [Company Name] Investment Type [Type]"
        
        # Extract dates first
        maturity_match = re.search(r'Maturity[^\d]*Dissolution\s+Date\s+(\d{1,2}/\d{4}|\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            date_str = maturity_match.group(1)
            # Handle MM/YYYY format (no day)
            if '/' in date_str and len(date_str.split('/')) == 2:
                month, year = date_str.split('/')
                date_str = f"{month}/01/{year}"
            # Normalize 2-digit year to 4-digit
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        # Extract reference rate and spread - pattern: "Interest Term S + 650" or "Interest Term SN + 625"
        # S = SOFR, E = EURIBOR, etc.
        ref_spread_match = re.search(r'Interest\s+Term\s+([SEN])\s*\+\s*(\d+)', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            rate_letter = ref_spread_match.group(1).upper()
            spread_val = ref_spread_match.group(2)
            if rate_letter == 'S':
                res['reference_rate'] = 'SOFR'
            elif rate_letter == 'E':
                res['reference_rate'] = 'EURIBOR'
            elif rate_letter == 'N':
                res['reference_rate'] = 'EURIBOR'  # SN might be EURIBOR
            else:
                res['reference_rate'] = rate_letter
            
            # Spread is in basis points, convert to percentage
            try:
                spread_bps = float(spread_val)
                spread_pct = spread_bps / 100.0
                res['spread'] = self._percent(str(spread_pct))
            except:
                res['spread'] = self._percent(spread_val)
        
        # Extract floor rate - pattern: "(100 Floor)" or "(75 Floor)"
        floor_match = re.search(r'\((\d+)\s*Floor\)', ident_clean, re.IGNORECASE)
        if floor_match:
            floor_bps = floor_match.group(1)
            try:
                floor_val = float(floor_bps) / 100.0  # Convert basis points to percentage
                res['floor_rate'] = self._percent(str(floor_val))
            except:
                res['floor_rate'] = self._percent(floor_bps)
        
        # Extract PIK rate - pattern: "(plus 200 PIK)" or "(plus 400 PIK)"
        pik_match = re.search(r'\(plus\s+(\d+)\s*PIK\)', ident_clean, re.IGNORECASE)
        if pik_match:
            pik_bps = pik_match.group(1)
            try:
                pik_val = float(pik_bps) / 100.0  # Convert basis points to percentage
                res['pik_rate'] = self._percent(str(pik_val))
            except:
                res['pik_rate'] = self._percent(pik_bps)
        
        # Extract interest rate - pattern: "Interest Rate 10.93" or "Interest Rate 8.80%"
        interest_rate_match = re.search(r'Interest\s+Rate\s+([\d\.]+)\s*%?', ident_clean, re.IGNORECASE)
        if interest_rate_match:
            res['interest_rate'] = self._percent(interest_rate_match.group(1))
        
        # Remove prefix: "Investments [Country] Debt Investments" or "Equity Investments"
        ident_clean = re.sub(r'^Investments\s+(?:United\s+States|United\s+Kingdom|Sweden|Canada)\s+Debt\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^Equity\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        
        # Extract industry - it comes after the prefix, before company name
        # Common industries in CCAP: "Health Care Equipment & Services", "Software & Services", "Commercial & Professional Services", "Consumer Services", "Diversified Financials", "Pharmaceuticals", "Retailing"
        common_industries = [
            'Health Care Equipment & Services', 'Software & Services', 'Commercial & Professional Services',
            'Consumer Services', 'Diversified Financials', 'Pharmaceuticals', 'Retailing',
            'Software', 'Commercial', 'Health Care', 'Consumer'
        ]
        
        industry_found = None
        industry_end_pos = 0
        
        for ind in common_industries:
            # Match industry as a phrase
            pattern = r'^' + re.escape(ind) + r'\s+'
            match = re.match(pattern, ident_clean, re.IGNORECASE)
            if match:
                industry_found = ind
                industry_end_pos = match.end()
                break
        
        if industry_found:
            res['industry'] = industry_found
        else:
            # Try to extract first few words as industry
            words = ident_clean.split()
            if len(words) >= 2:
                potential_industry = ' '.join(words[:2])
                if any(kw in potential_industry.lower() for kw in ['services', 'equipment', 'care', 'software', 'commercial', 'consumer']):
                    res['industry'] = potential_industry
                    industry_end_pos = len(potential_industry)
        
        # Text after industry (company name + investment type + rates)
        after_industry = ident_clean[industry_end_pos:].strip() if industry_end_pos > 0 else ident_clean
        
        # Extract investment type - look for "Investment Type" or patterns
        inv_type_patterns = [
            r'Investment\s+Type\s+(Unitranche\s+)?(First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|First\s+Lien\s+Term\s+Loan|First\s+Lien\s+Revolver|Senior\s+Secured\s+First\s+Lien\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Revolver|Common\s+Stock)',
            r'(Unitranche\s+)?First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Senior\s+Secured\s+First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Common\s+Stock'
        ]
        
        inv_type_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, after_industry, re.IGNORECASE)
            if match:
                inv_type_match = match
                inv_type_text = match.group(0)
                # Clean up
                inv_type_text = re.sub(r'\s+', ' ', inv_type_text).strip()
                # Normalize
                if 'Unitranche' in inv_type_text:
                    res['investment_type'] = inv_type_text
                elif 'First Lien Term Loan' in inv_type_text or 'First Lien Delayed Draw Term Loan' in inv_type_text:
                    res['investment_type'] = 'First Lien Debt'
                elif 'First Lien Revolver' in inv_type_text:
                    res['investment_type'] = 'First Lien Revolver'
                elif 'Common Stock' in inv_type_text:
                    res['investment_type'] = 'Common Equity'
                else:
                    res['investment_type'] = inv_type_text
                break
        
        # Extract company name - it's between industry and investment type
        if inv_type_match:
            company_text = after_industry[:inv_type_match.start()].strip()
        else:
            # Look for stop words before rate info
            stop_pattern = r'(Interest\s+Term|Investment\s+Type)'
            stop_match = re.search(stop_pattern, after_industry, re.IGNORECASE)
            if stop_match:
                company_text = after_industry[:stop_match.start()].strip()
            else:
                company_text = after_industry.split('Interest Term')[0].strip() if 'Interest Term' in after_industry else after_industry
        
        # Clean up company name - remove trailing "One" or investment type mentions
        company_text = re.sub(r'\s+One\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment\s+Type\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment&#160;Type\s*$', '', company_text, flags=re.IGNORECASE)
        
        # Remove industry prefixes that may have leaked in (e.g., "Equipment & Services" at start)
        # But be careful not to remove actual company name words
        industry_prefixes = [
            r'^Equipment\s+&amp;\s+Services\s+',
            r'^&amp;\s+Services\s+',
            r'^&amp;\s+Professional\s+Services\s+',
            r'^Pharmaceuticals,\s+Biotechnology\s+&amp;\s+Life\s+Sciences\s+',
        ]
        for prefix_pattern in industry_prefixes:
            company_text = re.sub(prefix_pattern, '', company_text, flags=re.IGNORECASE)
        
        # Clean up HTML entities
        company_text = company_text.replace('&amp;', '&')
        company_text = company_text.replace('&#160;', ' ')
        
        # Remove trailing commas and clean up
        company_text = company_text.rstrip(',')
        company_text = self._strip_footnote_refs(company_text)
        
        # If company name starts with "&" or common industry words, try to find actual entity name
        if company_text and (company_text.startswith('&') or any(company_text.lower().startswith(p.split()[0].lower()) for p in ['Equipment', 'Software', 'Commercial', 'Health Care'])):
            # Try to find entity pattern (LLC, Inc., Corp, etc.)
            entity_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|S\.A\.R\.L\.|AB|plc)(?:\s|$|,|\))', company_text, re.IGNORECASE)
            if entity_match:
                # Extract entity name and type
                entity_full = entity_match.group(0).strip()
                # Remove any leading industry words
                for prefix_pattern in industry_prefixes:
                    entity_full = re.sub(prefix_pattern, '', entity_full, flags=re.IGNORECASE)
                entity_full = entity_full.replace('&amp;', '&').strip()
                if entity_full:
                    company_text = entity_full
        
        if company_text and len(company_text) > 2:
            res['company_name'] = company_text
        
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
        for concept, cref, val in sp.findall(content):
            if val and cref:
                facts[cref].append({'concept': concept, 'value': val.strip()})
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1); cref = m.group(2); html = m.group(4)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                facts[cref].append({'concept': name, 'value': txt})
            start = max(0, m.start()-3000); end = min(len(content), m.end()+3000)
            window = content[start:end]
            ref = re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref:
                facts[cref].append({'concept':'derived:ReferenceRateToken','value': ref.group(1).replace('+','').upper()})
            floor = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor:
                facts[cref].append({'concept':'derived:FloorRate','value': floor.group(1)})
            pik = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik:
                facts[cref].append({'concept':'derived:PIKRate','value': pik.group(1)})
            dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[CCAPInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = CCAPInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v = v.replace(',',''); cl=c.lower()
            if any(k in cl for k in ['principalamount','ownedbalanceprincipalamount','outstandingprincipal']):
                try: inv.principal_amount=float(v)
                except: pass; continue
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: inv.cost=float(v)
                except: pass; continue
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: inv.fair_value=float(v)
                except: pass; continue
                continue
            if 'investmentbasisspreadvariablerate' in cl:
                inv.spread = self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v); continue
            if cl=='derived:referenceratetoken':
                inv.reference_rate = v.upper(); continue
            if cl=='derived:floorrate':
                inv.floor_rate = self._percent(v); continue
            if cl=='derived:pikrate':
                inv.pik_rate = self._percent(v); continue
            if cl=='derived:acquisitiondate':
                inv.acquisition_date = v; continue
            if cl=='derived:maturitydate':
                inv.maturity_date = v; continue
        # Fill missing fields from parsed identifier
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _percent(self, s: str) -> str:
        try:
            v=float(s)
        except:
            return f"{s}%"
        if 0<abs(v)<=1.0:
            v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={} ; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        ep=re.compile(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', re.DOTALL|re.IGNORECASE)
        for mm in cp.finditer(content):
            html=mm.group(2)
            inst=re.search(r'<instant>([^<]+)</instant>', html)
            inst=inst.group(1) if inst else None
            if not inst: continue
            em=ep.search(html)
            if not em: continue
            m[inst]=self._industry_member_to_name(em.group(1).strip())
        return m

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local=qname.split(':',1)[-1] if ':' in qname else qname
        local=re.sub(r'Member$','',local)
        if local.endswith('Sector'): local=local[:-6]
        words=re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words=re.sub(r'\bAnd\b','and',words)
        words=re.sub(r'\s+',' ',words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates=[c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=CCAPExtractor()
    try:
        res=ex.extract_from_ticker('CCAP')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()



CCAP (Crescent Capital BDC Inc) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filter; de-dup; industry enrichment.
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
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class CCAPInvestment:
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


class CCAPExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "CCAP") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        acc = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not acc:
            raise ValueError("Could not parse accession number")
        accession = acc.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Crescent_Capital_BDC_Inc", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        resp = requests.get(filing_url, headers=self.headers)
        resp.raise_for_status()
        content = resp.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
            logger.info(f"Filtered contexts to instant {sel}: {len(contexts)} remaining")

        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]

        facts_by_context = self._extract_facts(content)
        investments: List[CCAPInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # de-dup
        ded = []
        seen = set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen:
                continue
            seen.add(combo)
            ded.append(inv)
        investments = ded

        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        ind_br = defaultdict(int)
        type_br = defaultdict(int)
        for inv in investments:
            ind_br[inv.industry] += 1
            type_br[inv.investment_type] += 1

        out_dir = 'output'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'CCAP_Crescent_Capital_BDC_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
            ])
            writer.writeheader()
            for inv in investments:
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
                    'pik_rate': inv.pik_rate,
                })

        logger.info(f"Saved to {out_file}")
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(ind_br),
            'investment_type_breakdown': dict(type_br)
        }

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        contexts: List[Dict] = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1)
            chtml = m.group(2)
            tm = tp.search(chtml)
            if not tm:
                continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', chtml)
            sd = re.search(r'<startDate>([^<]+)</startDate>', chtml)
            ed = re.search(r'<endDate>([^<]+)</endDate>', chtml)
            same_ind = None
            sm = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', chtml, re.DOTALL|re.IGNORECASE)
            if sm:
                same_ind = self._industry_member_to_name(sm.group(1).strip())
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'business_description': parsed.get('business_description'),
                'investment_type': parsed['investment_type'],
                'maturity_date': parsed.get('maturity_date'),
                'acquisition_date': parsed.get('acquisition_date'),
                'pik_rate': parsed.get('pik_rate'),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # CCAP format: "Investments [Country] Debt Investments [Industry] [Company Name] Investment Type [Type] Interest Term S + [Spread] ([Floor] Floor) Interest Rate [Rate] Maturity/ Dissolution Date [Date]"
        # Or: "Equity Investments [Industry] [Company Name] Investment Type [Type]"
        
        # Extract dates first
        maturity_match = re.search(r'Maturity[^\d]*Dissolution\s+Date\s+(\d{1,2}/\d{4}|\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            date_str = maturity_match.group(1)
            # Handle MM/YYYY format (no day)
            if '/' in date_str and len(date_str.split('/')) == 2:
                month, year = date_str.split('/')
                date_str = f"{month}/01/{year}"
            # Normalize 2-digit year to 4-digit
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        # Extract reference rate and spread - pattern: "Interest Term S + 650" or "Interest Term SN + 625"
        # S = SOFR, E = EURIBOR, etc.
        ref_spread_match = re.search(r'Interest\s+Term\s+([SEN])\s*\+\s*(\d+)', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            rate_letter = ref_spread_match.group(1).upper()
            spread_val = ref_spread_match.group(2)
            if rate_letter == 'S':
                res['reference_rate'] = 'SOFR'
            elif rate_letter == 'E':
                res['reference_rate'] = 'EURIBOR'
            elif rate_letter == 'N':
                res['reference_rate'] = 'EURIBOR'  # SN might be EURIBOR
            else:
                res['reference_rate'] = rate_letter
            
            # Spread is in basis points, convert to percentage
            try:
                spread_bps = float(spread_val)
                spread_pct = spread_bps / 100.0
                res['spread'] = self._percent(str(spread_pct))
            except:
                res['spread'] = self._percent(spread_val)
        
        # Extract floor rate - pattern: "(100 Floor)" or "(75 Floor)"
        floor_match = re.search(r'\((\d+)\s*Floor\)', ident_clean, re.IGNORECASE)
        if floor_match:
            floor_bps = floor_match.group(1)
            try:
                floor_val = float(floor_bps) / 100.0  # Convert basis points to percentage
                res['floor_rate'] = self._percent(str(floor_val))
            except:
                res['floor_rate'] = self._percent(floor_bps)
        
        # Extract PIK rate - pattern: "(plus 200 PIK)" or "(plus 400 PIK)"
        pik_match = re.search(r'\(plus\s+(\d+)\s*PIK\)', ident_clean, re.IGNORECASE)
        if pik_match:
            pik_bps = pik_match.group(1)
            try:
                pik_val = float(pik_bps) / 100.0  # Convert basis points to percentage
                res['pik_rate'] = self._percent(str(pik_val))
            except:
                res['pik_rate'] = self._percent(pik_bps)
        
        # Extract interest rate - pattern: "Interest Rate 10.93" or "Interest Rate 8.80%"
        interest_rate_match = re.search(r'Interest\s+Rate\s+([\d\.]+)\s*%?', ident_clean, re.IGNORECASE)
        if interest_rate_match:
            res['interest_rate'] = self._percent(interest_rate_match.group(1))
        
        # Remove prefix: "Investments [Country] Debt Investments" or "Equity Investments"
        ident_clean = re.sub(r'^Investments\s+(?:United\s+States|United\s+Kingdom|Sweden|Canada)\s+Debt\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^Equity\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        
        # Extract industry - it comes after the prefix, before company name
        # Common industries in CCAP: "Health Care Equipment & Services", "Software & Services", "Commercial & Professional Services", "Consumer Services", "Diversified Financials", "Pharmaceuticals", "Retailing"
        common_industries = [
            'Health Care Equipment & Services', 'Software & Services', 'Commercial & Professional Services',
            'Consumer Services', 'Diversified Financials', 'Pharmaceuticals', 'Retailing',
            'Software', 'Commercial', 'Health Care', 'Consumer'
        ]
        
        industry_found = None
        industry_end_pos = 0
        
        for ind in common_industries:
            # Match industry as a phrase
            pattern = r'^' + re.escape(ind) + r'\s+'
            match = re.match(pattern, ident_clean, re.IGNORECASE)
            if match:
                industry_found = ind
                industry_end_pos = match.end()
                break
        
        if industry_found:
            res['industry'] = industry_found
        else:
            # Try to extract first few words as industry
            words = ident_clean.split()
            if len(words) >= 2:
                potential_industry = ' '.join(words[:2])
                if any(kw in potential_industry.lower() for kw in ['services', 'equipment', 'care', 'software', 'commercial', 'consumer']):
                    res['industry'] = potential_industry
                    industry_end_pos = len(potential_industry)
        
        # Text after industry (company name + investment type + rates)
        after_industry = ident_clean[industry_end_pos:].strip() if industry_end_pos > 0 else ident_clean
        
        # Extract investment type - look for "Investment Type" or patterns
        inv_type_patterns = [
            r'Investment\s+Type\s+(Unitranche\s+)?(First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|First\s+Lien\s+Term\s+Loan|First\s+Lien\s+Revolver|Senior\s+Secured\s+First\s+Lien\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Revolver|Common\s+Stock)',
            r'(Unitranche\s+)?First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Senior\s+Secured\s+First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Common\s+Stock'
        ]
        
        inv_type_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, after_industry, re.IGNORECASE)
            if match:
                inv_type_match = match
                inv_type_text = match.group(0)
                # Clean up
                inv_type_text = re.sub(r'\s+', ' ', inv_type_text).strip()
                # Normalize
                if 'Unitranche' in inv_type_text:
                    res['investment_type'] = inv_type_text
                elif 'First Lien Term Loan' in inv_type_text or 'First Lien Delayed Draw Term Loan' in inv_type_text:
                    res['investment_type'] = 'First Lien Debt'
                elif 'First Lien Revolver' in inv_type_text:
                    res['investment_type'] = 'First Lien Revolver'
                elif 'Common Stock' in inv_type_text:
                    res['investment_type'] = 'Common Equity'
                else:
                    res['investment_type'] = inv_type_text
                break
        
        # Extract company name - it's between industry and investment type
        if inv_type_match:
            company_text = after_industry[:inv_type_match.start()].strip()
        else:
            # Look for stop words before rate info
            stop_pattern = r'(Interest\s+Term|Investment\s+Type)'
            stop_match = re.search(stop_pattern, after_industry, re.IGNORECASE)
            if stop_match:
                company_text = after_industry[:stop_match.start()].strip()
            else:
                company_text = after_industry.split('Interest Term')[0].strip() if 'Interest Term' in after_industry else after_industry
        
        # Clean up company name - remove trailing "One" or investment type mentions
        company_text = re.sub(r'\s+One\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment\s+Type\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment&#160;Type\s*$', '', company_text, flags=re.IGNORECASE)
        
        # Remove industry prefixes that may have leaked in (e.g., "Equipment & Services" at start)
        # But be careful not to remove actual company name words
        industry_prefixes = [
            r'^Equipment\s+&amp;\s+Services\s+',
            r'^&amp;\s+Services\s+',
            r'^&amp;\s+Professional\s+Services\s+',
            r'^Pharmaceuticals,\s+Biotechnology\s+&amp;\s+Life\s+Sciences\s+',
        ]
        for prefix_pattern in industry_prefixes:
            company_text = re.sub(prefix_pattern, '', company_text, flags=re.IGNORECASE)
        
        # Clean up HTML entities
        company_text = company_text.replace('&amp;', '&')
        company_text = company_text.replace('&#160;', ' ')
        
        # Remove trailing commas and clean up
        company_text = company_text.rstrip(',')
        company_text = self._strip_footnote_refs(company_text)
        
        # If company name starts with "&" or common industry words, try to find actual entity name
        if company_text and (company_text.startswith('&') or any(company_text.lower().startswith(p.split()[0].lower()) for p in ['Equipment', 'Software', 'Commercial', 'Health Care'])):
            # Try to find entity pattern (LLC, Inc., Corp, etc.)
            entity_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|S\.A\.R\.L\.|AB|plc)(?:\s|$|,|\))', company_text, re.IGNORECASE)
            if entity_match:
                # Extract entity name and type
                entity_full = entity_match.group(0).strip()
                # Remove any leading industry words
                for prefix_pattern in industry_prefixes:
                    entity_full = re.sub(prefix_pattern, '', entity_full, flags=re.IGNORECASE)
                entity_full = entity_full.replace('&amp;', '&').strip()
                if entity_full:
                    company_text = entity_full
        
        if company_text and len(company_text) > 2:
            res['company_name'] = company_text
        
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
        for concept, cref, val in sp.findall(content):
            if val and cref:
                facts[cref].append({'concept': concept, 'value': val.strip()})
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1); cref = m.group(2); html = m.group(4)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                facts[cref].append({'concept': name, 'value': txt})
            start = max(0, m.start()-3000); end = min(len(content), m.end()+3000)
            window = content[start:end]
            ref = re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref:
                facts[cref].append({'concept':'derived:ReferenceRateToken','value': ref.group(1).replace('+','').upper()})
            floor = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor:
                facts[cref].append({'concept':'derived:FloorRate','value': floor.group(1)})
            pik = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik:
                facts[cref].append({'concept':'derived:PIKRate','value': pik.group(1)})
            dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[CCAPInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = CCAPInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v = v.replace(',',''); cl=c.lower()
            if any(k in cl for k in ['principalamount','ownedbalanceprincipalamount','outstandingprincipal']):
                try: inv.principal_amount=float(v)
                except: pass; continue
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: inv.cost=float(v)
                except: pass; continue
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: inv.fair_value=float(v)
                except: pass; continue
                continue
            if 'investmentbasisspreadvariablerate' in cl:
                inv.spread = self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v); continue
            if cl=='derived:referenceratetoken':
                inv.reference_rate = v.upper(); continue
            if cl=='derived:floorrate':
                inv.floor_rate = self._percent(v); continue
            if cl=='derived:pikrate':
                inv.pik_rate = self._percent(v); continue
            if cl=='derived:acquisitiondate':
                inv.acquisition_date = v; continue
            if cl=='derived:maturitydate':
                inv.maturity_date = v; continue
        # Fill missing fields from parsed identifier
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _percent(self, s: str) -> str:
        try:
            v=float(s)
        except:
            return f"{s}%"
        if 0<abs(v)<=1.0:
            v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={} ; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        ep=re.compile(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', re.DOTALL|re.IGNORECASE)
        for mm in cp.finditer(content):
            html=mm.group(2)
            inst=re.search(r'<instant>([^<]+)</instant>', html)
            inst=inst.group(1) if inst else None
            if not inst: continue
            em=ep.search(html)
            if not em: continue
            m[inst]=self._industry_member_to_name(em.group(1).strip())
        return m

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local=qname.split(':',1)[-1] if ':' in qname else qname
        local=re.sub(r'Member$','',local)
        if local.endswith('Sector'): local=local[:-6]
        words=re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words=re.sub(r'\bAnd\b','and',words)
        words=re.sub(r'\s+',' ',words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates=[c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=CCAPExtractor()
    try:
        res=ex.extract_from_ticker('CCAP')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""
CCAP (Crescent Capital BDC Inc) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filtering; de-dup; industry enrichment.
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
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class CCAPInvestment:
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


class CCAPExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "CCAP") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Crescent_Capital_BDC_Inc", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        resp = requests.get(filing_url, headers=self.headers)
        resp.raise_for_status()
        content = resp.text

        contexts = self._extract_typed_contexts(content)
        logger.info(f"Found {len(contexts)} investment contexts with InvestmentIdentifierAxis")
        sel = self._select_reporting_instant(contexts)
        if sel:
            contexts = [c for c in contexts if c.get('instant') == sel]
            logger.info(f"Filtered contexts to instant {sel}: {len(contexts)} remaining")

        ind_by_inst = self._build_industry_index(content)
        for c in contexts:
            if (not c.get('industry')) or c['industry'] == 'Unknown':
                inst = c.get('instant')
                if inst and inst in ind_by_inst:
                    c['industry'] = ind_by_inst[inst]

        facts_by_context = self._extract_facts(content)
        investments: List[CCAPInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # de-dup
        ded = []
        seen = set()
        for inv in investments:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen:
                continue
            seen.add(combo)
            ded.append(inv)
        investments = ded

        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        ind_br = defaultdict(int)
        type_br = defaultdict(int)
        for inv in investments:
            ind_br[inv.industry] += 1
            type_br[inv.investment_type] += 1

        out_dir = 'output'
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'CCAP_Crescent_Capital_BDC_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
                'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
            ])
            writer.writeheader()
            for inv in investments:
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
                    'pik_rate': inv.pik_rate,
                })

        logger.info(f"Saved to {out_file}")
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(ind_br),
            'investment_type_breakdown': dict(type_br)
        }

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        contexts: List[Dict] = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(
            r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
            r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
            r'\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1)
            chtml = m.group(2)
            tm = tp.search(chtml)
            if not tm:
                continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', chtml)
            sd = re.search(r'<startDate>([^<]+)</startDate>', chtml)
            ed = re.search(r'<endDate>([^<]+)</endDate>', chtml)
            same_ind = None
            sm = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', chtml, re.DOTALL|re.IGNORECASE)
            if sm:
                same_ind = self._industry_member_to_name(sm.group(1).strip())
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'business_description': parsed.get('business_description'),
                'investment_type': parsed['investment_type'],
                'maturity_date': parsed.get('maturity_date'),
                'acquisition_date': parsed.get('acquisition_date'),
                'pik_rate': parsed.get('pik_rate'),
                'reference_rate': parsed.get('reference_rate'),
                'spread': parsed.get('spread'),
                'floor_rate': parsed.get('floor_rate'),
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # CCAP format: "Investments [Country] Debt Investments [Industry] [Company Name] Investment Type [Type] Interest Term S + [Spread] ([Floor] Floor) Interest Rate [Rate] Maturity/ Dissolution Date [Date]"
        # Or: "Equity Investments [Industry] [Company Name] Investment Type [Type]"
        
        # Extract dates first
        maturity_match = re.search(r'Maturity[^\d]*Dissolution\s+Date\s+(\d{1,2}/\d{4}|\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            date_str = maturity_match.group(1)
            # Handle MM/YYYY format (no day)
            if '/' in date_str and len(date_str.split('/')) == 2:
                month, year = date_str.split('/')
                date_str = f"{month}/01/{year}"
            # Normalize 2-digit year to 4-digit
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        # Extract reference rate and spread - pattern: "Interest Term S + 650" or "Interest Term SN + 625"
        # S = SOFR, E = EURIBOR, etc.
        ref_spread_match = re.search(r'Interest\s+Term\s+([SEN])\s*\+\s*(\d+)', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            rate_letter = ref_spread_match.group(1).upper()
            spread_val = ref_spread_match.group(2)
            if rate_letter == 'S':
                res['reference_rate'] = 'SOFR'
            elif rate_letter == 'E':
                res['reference_rate'] = 'EURIBOR'
            elif rate_letter == 'N':
                res['reference_rate'] = 'EURIBOR'  # SN might be EURIBOR
            else:
                res['reference_rate'] = rate_letter
            
            # Spread is in basis points, convert to percentage
            try:
                spread_bps = float(spread_val)
                spread_pct = spread_bps / 100.0
                res['spread'] = self._percent(str(spread_pct))
            except:
                res['spread'] = self._percent(spread_val)
        
        # Extract floor rate - pattern: "(100 Floor)" or "(75 Floor)"
        floor_match = re.search(r'\((\d+)\s*Floor\)', ident_clean, re.IGNORECASE)
        if floor_match:
            floor_bps = floor_match.group(1)
            try:
                floor_val = float(floor_bps) / 100.0  # Convert basis points to percentage
                res['floor_rate'] = self._percent(str(floor_val))
            except:
                res['floor_rate'] = self._percent(floor_bps)
        
        # Extract PIK rate - pattern: "(plus 200 PIK)" or "(plus 400 PIK)"
        pik_match = re.search(r'\(plus\s+(\d+)\s*PIK\)', ident_clean, re.IGNORECASE)
        if pik_match:
            pik_bps = pik_match.group(1)
            try:
                pik_val = float(pik_bps) / 100.0  # Convert basis points to percentage
                res['pik_rate'] = self._percent(str(pik_val))
            except:
                res['pik_rate'] = self._percent(pik_bps)
        
        # Extract interest rate - pattern: "Interest Rate 10.93" or "Interest Rate 8.80%"
        interest_rate_match = re.search(r'Interest\s+Rate\s+([\d\.]+)\s*%?', ident_clean, re.IGNORECASE)
        if interest_rate_match:
            res['interest_rate'] = self._percent(interest_rate_match.group(1))
        
        # Remove prefix: "Investments [Country] Debt Investments" or "Equity Investments"
        ident_clean = re.sub(r'^Investments\s+(?:United\s+States|United\s+Kingdom|Sweden|Canada)\s+Debt\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        ident_clean = re.sub(r'^Equity\s+Investments\s+', '', ident_clean, flags=re.IGNORECASE)
        
        # Extract industry - it comes after the prefix, before company name
        # Common industries in CCAP: "Health Care Equipment & Services", "Software & Services", "Commercial & Professional Services", "Consumer Services", "Diversified Financials", "Pharmaceuticals", "Retailing"
        common_industries = [
            'Health Care Equipment & Services', 'Software & Services', 'Commercial & Professional Services',
            'Consumer Services', 'Diversified Financials', 'Pharmaceuticals', 'Retailing',
            'Software', 'Commercial', 'Health Care', 'Consumer'
        ]
        
        industry_found = None
        industry_end_pos = 0
        
        for ind in common_industries:
            # Match industry as a phrase
            pattern = r'^' + re.escape(ind) + r'\s+'
            match = re.match(pattern, ident_clean, re.IGNORECASE)
            if match:
                industry_found = ind
                industry_end_pos = match.end()
                break
        
        if industry_found:
            res['industry'] = industry_found
        else:
            # Try to extract first few words as industry
            words = ident_clean.split()
            if len(words) >= 2:
                potential_industry = ' '.join(words[:2])
                if any(kw in potential_industry.lower() for kw in ['services', 'equipment', 'care', 'software', 'commercial', 'consumer']):
                    res['industry'] = potential_industry
                    industry_end_pos = len(potential_industry)
        
        # Text after industry (company name + investment type + rates)
        after_industry = ident_clean[industry_end_pos:].strip() if industry_end_pos > 0 else ident_clean
        
        # Extract investment type - look for "Investment Type" or patterns
        inv_type_patterns = [
            r'Investment\s+Type\s+(Unitranche\s+)?(First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|First\s+Lien\s+Term\s+Loan|First\s+Lien\s+Revolver|Senior\s+Secured\s+First\s+Lien\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Delayed\s+Draw\s+Term\s+Loan|Senior\s+Secured\s+First\s+Lien\s+Revolver|Common\s+Stock)',
            r'(Unitranche\s+)?First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Senior\s+Secured\s+First\s+Lien\s+(Term\s+Loan|Delayed\s+Draw\s+Term\s+Loan|Revolver)',
            r'Common\s+Stock'
        ]
        
        inv_type_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, after_industry, re.IGNORECASE)
            if match:
                inv_type_match = match
                inv_type_text = match.group(0)
                # Clean up
                inv_type_text = re.sub(r'\s+', ' ', inv_type_text).strip()
                # Normalize
                if 'Unitranche' in inv_type_text:
                    res['investment_type'] = inv_type_text
                elif 'First Lien Term Loan' in inv_type_text or 'First Lien Delayed Draw Term Loan' in inv_type_text:
                    res['investment_type'] = 'First Lien Debt'
                elif 'First Lien Revolver' in inv_type_text:
                    res['investment_type'] = 'First Lien Revolver'
                elif 'Common Stock' in inv_type_text:
                    res['investment_type'] = 'Common Equity'
                else:
                    res['investment_type'] = inv_type_text
                break
        
        # Extract company name - it's between industry and investment type
        if inv_type_match:
            company_text = after_industry[:inv_type_match.start()].strip()
        else:
            # Look for stop words before rate info
            stop_pattern = r'(Interest\s+Term|Investment\s+Type)'
            stop_match = re.search(stop_pattern, after_industry, re.IGNORECASE)
            if stop_match:
                company_text = after_industry[:stop_match.start()].strip()
            else:
                company_text = after_industry.split('Interest Term')[0].strip() if 'Interest Term' in after_industry else after_industry
        
        # Clean up company name - remove trailing "One" or investment type mentions
        company_text = re.sub(r'\s+One\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment\s+Type\s*$', '', company_text, flags=re.IGNORECASE)
        company_text = re.sub(r'\s+Investment&#160;Type\s*$', '', company_text, flags=re.IGNORECASE)
        
        # Remove industry prefixes that may have leaked in (e.g., "Equipment & Services" at start)
        # But be careful not to remove actual company name words
        industry_prefixes = [
            r'^Equipment\s+&amp;\s+Services\s+',
            r'^&amp;\s+Services\s+',
            r'^&amp;\s+Professional\s+Services\s+',
            r'^Pharmaceuticals,\s+Biotechnology\s+&amp;\s+Life\s+Sciences\s+',
        ]
        for prefix_pattern in industry_prefixes:
            company_text = re.sub(prefix_pattern, '', company_text, flags=re.IGNORECASE)
        
        # Clean up HTML entities
        company_text = company_text.replace('&amp;', '&')
        company_text = company_text.replace('&#160;', ' ')
        
        # Remove trailing commas and clean up
        company_text = company_text.rstrip(',')
        company_text = self._strip_footnote_refs(company_text)
        
        # If company name starts with "&" or common industry words, try to find actual entity name
        if company_text and (company_text.startswith('&') or any(company_text.lower().startswith(p.split()[0].lower()) for p in ['Equipment', 'Software', 'Commercial', 'Health Care'])):
            # Try to find entity pattern (LLC, Inc., Corp, etc.)
            entity_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|S\.A\.R\.L\.|AB|plc)(?:\s|$|,|\))', company_text, re.IGNORECASE)
            if entity_match:
                # Extract entity name and type
                entity_full = entity_match.group(0).strip()
                # Remove any leading industry words
                for prefix_pattern in industry_prefixes:
                    entity_full = re.sub(prefix_pattern, '', entity_full, flags=re.IGNORECASE)
                entity_full = entity_full.replace('&amp;', '&').strip()
                if entity_full:
                    company_text = entity_full
        
        if company_text and len(company_text) > 2:
            res['company_name'] = company_text
        
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
        for concept, cref, val in sp.findall(content):
            if val and cref:
                facts[cref].append({'concept': concept, 'value': val.strip()})
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1); cref = m.group(2); html = m.group(4)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                facts[cref].append({'concept': name, 'value': txt})
            start = max(0, m.start()-3000); end = min(len(content), m.end()+3000)
            window = content[start:end]
            ref = re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref:
                facts[cref].append({'concept':'derived:ReferenceRateToken','value': ref.group(1).replace('+','').upper()})
            floor = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor:
                facts[cref].append({'concept':'derived:FloorRate','value': floor.group(1)})
            pik = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik:
                facts[cref].append({'concept':'derived:PIKRate','value': pik.group(1)})
            dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[CCAPInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = CCAPInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v = v.replace(',',''); cl=c.lower()
            if any(k in cl for k in ['principalamount','ownedbalanceprincipalamount','outstandingprincipal']):
                try: inv.principal_amount=float(v)
                except: pass; continue
                continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: inv.cost=float(v)
                except: pass; continue
                continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: inv.fair_value=float(v)
                except: pass; continue
                continue
            if 'investmentbasisspreadvariablerate' in cl:
                inv.spread = self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._percent(v); continue
            if cl=='derived:referenceratetoken':
                inv.reference_rate = v.upper(); continue
            if cl=='derived:floorrate':
                inv.floor_rate = self._percent(v); continue
            if cl=='derived:pikrate':
                inv.pik_rate = self._percent(v); continue
            if cl=='derived:acquisitiondate':
                inv.acquisition_date = v; continue
            if cl=='derived:maturitydate':
                inv.maturity_date = v; continue
        # Fill missing fields from parsed identifier
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _percent(self, s: str) -> str:
        try:
            v=float(s)
        except:
            return f"{s}%"
        if 0<abs(v)<=1.0:
            v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={} ; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        ep=re.compile(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', re.DOTALL|re.IGNORECASE)
        for mm in cp.finditer(content):
            html=mm.group(2)
            inst=re.search(r'<instant>([^<]+)</instant>', html)
            inst=inst.group(1) if inst else None
            if not inst: continue
            em=ep.search(html)
            if not em: continue
            m[inst]=self._industry_member_to_name(em.group(1).strip())
        return m

    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        local=qname.split(':',1)[-1] if ':' in qname else qname
        local=re.sub(r'Member$','',local)
        if local.endswith('Sector'): local=local[:-6]
        words=re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words=re.sub(r'\bAnd\b','and',words)
        words=re.sub(r'\s+',' ',words).strip()
        return words if words else None

    def _select_reporting_instant(self, contexts: List[Dict]) -> Optional[str]:
        dates=[c.get('instant') for c in contexts if c.get('instant') and re.match(r'^\d{4}-\d{2}-\d{2}$', c.get('instant'))]
        return max(dates) if dates else None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=CCAPExtractor()
    try:
        res=ex.extract_from_ticker('CCAP')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()


