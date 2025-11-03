#!/usr/bin/env python3
"""
CGBD (TCG BDC Inc) Investment Extractor
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
class CGBDInvestment:
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


class CGBDExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "CGBD") -> Dict:
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
        return self.extract_from_url(txt_url, "TCG_BDC_Inc", cik)

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
        investments: List[CGBDInvestment] = []
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
        out_file = os.path.join(out_dir, 'CGBD_TCG_BDC_Inc_investments.csv')
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
                'raw_identifier': ident,
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
               'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None,
               'maturity_date': None, 'acquisition_date': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # CGBD format: "Investment, Non-Affiliated Issuer, [Investment Type], [Company Name], [Industry]"
        # Example: "Investment, Non-Affiliated Issuer, First Lien Debt, 1251 Insurance Distribution Platform Payco, LP, Diversified Financial Services"
        
        # Remove prefix: "Investment, Non-Affiliated Issuer, " or "Investment, Affiliated Issuer, "
        ident_clean = re.sub(r'^Investment,\s*(?:Non-)?Affiliated\s+Issuer,\s+', '', ident_clean, flags=re.IGNORECASE)
        
        # Split by commas to parse the structure
        # Format should be: "[Investment Type], [Company Name with commas], [Industry]"
        parts = [p.strip() for p in ident_clean.split(',')]
        
        if len(parts) < 3:
            # Fallback to old logic if format doesn't match
            if ',' in identifier:
                last = identifier.rfind(',')
                company = identifier[:last].strip()
                tail = identifier[last+1:].strip()
            else:
                company = identifier.strip()
                tail = ''
            res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
            if tail:
                res['industry'] = tail
            return res
        
        # First part is investment type
        investment_type = parts[0].strip()
        
        # Normalize investment type
        if 'First Lien' in investment_type or 'First Lien Debt' in investment_type:
            res['investment_type'] = 'First Lien Debt'
        elif 'Second Lien' in investment_type or 'Second Lien Debt' in investment_type:
            res['investment_type'] = 'Second Lien Debt'
        elif 'Subordinated' in investment_type:
            res['investment_type'] = 'Subordinated Debt'
        elif 'Common Equity' in investment_type:
            res['investment_type'] = 'Common Equity'
        elif 'Preferred Equity' in investment_type:
            res['investment_type'] = 'Preferred Equity'
        elif 'Common Stock' in investment_type:
            res['investment_type'] = 'Common Stock'
        elif 'Preferred Stock' in investment_type:
            res['investment_type'] = 'Preferred Stock'
        elif 'Unitranche' in investment_type:
            res['investment_type'] = 'Unitranche'
        elif 'Warrants' in investment_type or 'Warrant' in investment_type:
            res['investment_type'] = 'Warrants'
        else:
            res['investment_type'] = investment_type
        
        # Last part is industry, but industry names might have commas
        # Common industry patterns that include commas:
        # "Containers, Packaging & Glass", "Finance and Insurance", etc.
        # Try to identify industry from common patterns
        common_industries = [
            'Diversified Financial Services', 'Healthcare & Pharmaceuticals', 'Aerospace & Defense',
            'Consumer Services', 'Containers, Packaging & Glass', 'Consumer Goods: Non-Durable',
            'Chemicals, Plastics & Rubber', 'Environmental Industries', 'Business Services',
            'Software', 'Construction & Building', 'High Tech Industries', 'Retail',
            'Transportation: Cargo', 'Transportation & Logistics', 'Food & Beverage',
            'Energy', 'Financial Services', 'Real Estate', 'Professional Services',
            'Media & Entertainment', 'Education', 'Healthcare', 'Manufacturing'
        ]
        
        # Try to find industry by matching from the end
        # Industries might span multiple comma-separated parts
        # e.g., "Containers, Packaging & Glass" appears as ["Containers", "Packaging & Glass"]
        industry_found = None
        industry_start_idx = len(parts)
        
        # Try matching from the end, combining parts as needed
        for start_idx in range(len(parts)-1, 0, -1):
            # Try combining 1, 2, or 3 parts from this position
            for num_parts in range(1, min(4, len(parts) - start_idx + 1)):
                test_industry = ','.join(parts[start_idx:start_idx+num_parts]).strip()
                for common_ind in common_industries:
                    # Normalize both for comparison
                    test_lower = test_industry.lower().replace('&amp;', '&').replace('&', 'and')
                    common_lower = common_ind.lower().replace('&', 'and')
                    
                    # Check if they match (allowing for some flexibility)
                    if (test_lower == common_lower or 
                        common_lower in test_lower or 
                        test_lower in common_lower or
                        # Match key words like "Packaging & Glass" matching "Containers, Packaging & Glass"
                        (len(common_lower.split()) > 2 and 
                         all(word in common_lower for word in test_lower.split() if len(word) > 3))):
                        industry_found = common_ind
                        industry_start_idx = start_idx
                        break
                if industry_found:
                    break
            if industry_found:
                break
        
        if industry_found:
            res['industry'] = self._strip_footnote_refs(industry_found)
            # Company name is everything between investment type and industry
            if industry_start_idx > 1:
                # Company name is everything between investment type (parts[0]) and industry start
                # But be careful: if company name itself has commas, we need to include those
                company_name_parts = parts[1:industry_start_idx]
                company_name = ','.join(company_name_parts).strip()
                company_name = self._strip_footnote_refs(company_name)
                
                # Clean up: remove trailing words that match the start of the industry
                # e.g., if company is "Company, Containers" and industry is "Containers, Packaging & Glass"
                # Split on commas first, then on spaces
                company_segments = [s.strip() for s in company_name.split(',')]
                industry_words = [w.strip() for w in industry_found.lower().replace('&', 'and').replace('&amp;', 'and').split(',')]
                
                # Check if last segment of company name matches first segment of industry
                if len(company_segments) > 0 and len(industry_words) > 0:
                    last_segment = company_segments[-1].lower().strip()
                    first_industry_segment = industry_words[0].lower().strip()
                    
                    # If they match, remove the last segment from company name
                    if last_segment == first_industry_segment:
                        company_segments = company_segments[:-1]
                        if company_segments:
                            company_name = ','.join(company_segments).strip()
                        else:
                            # Fallback: try word-level matching
                            company_words = company_name.split()
                            industry_first_word = industry_found.split(',')[0].split()[0].lower() if ',' in industry_found else industry_found.split()[0].lower()
                            if company_words and company_words[-1].lower().rstrip(',') == industry_first_word:
                                company_name = ' '.join(company_words[:-1]).strip().rstrip(',')
                
                res['company_name'] = company_name
        else:
            # Fallback: last part is industry
            industry = parts[-1].strip()
            res['industry'] = self._strip_footnote_refs(industry)
            # Everything in between is company name (may contain commas)
            if len(parts) > 2:
                company_name = ','.join(parts[1:-1]).strip()
                # Clean up company name
                company_name = self._strip_footnote_refs(company_name)
                res['company_name'] = company_name
        
        # Extract dates, rates, spreads from the original identifier if present
        tokens_text = identifier
        rr = re.search(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', tokens_text, re.IGNORECASE)
        if rr:
            rate = rr.group(1).upper()
            spread_raw = rr.group(2)
            try:
                sv = float(spread_raw)
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            res['reference_rate'] = rate
            res['spread'] = self._format_spread(str(sv))
        
        fl = re.search(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', tokens_text, re.IGNORECASE)
        if fl:
            floor_val = fl.group(1) or fl.group(2)
            res['floor_rate'] = self._percent(floor_val)
        
        pk = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', tokens_text, re.IGNORECASE)
        if pk:
            pik_val = pk.group(1) or pk.group(2)
            res['pik_rate'] = self._percent(pik_val)
        
        md = re.search(r'Maturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})', tokens_text, re.IGNORECASE)
        if md:
            date_str = md.group(1)
            # Normalize 2-digit year to 4-digit
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        ad = re.search(r'(?:Acquisition|Investment)\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})', tokens_text, re.IGNORECASE)
        if ad:
            date_str = ad.group(1)
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['acquisition_date'] = date_str
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[CGBDInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = CGBDInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        # Don't override company name if it was correctly parsed
        # Only extract tokens if needed
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
                inv.spread = self._format_spread(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._format_rate(v); continue
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
        if not inv.maturity_date:
            if context.get('maturity_date'):
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
        raw = str(s).strip().rstrip('%')
        try:
            v=float(raw)
        except:
            return f"{s}%"
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _extract_tokens_from_text(self, text: str):
        tokens = {'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None, 'maturity_date': None}
        original = text
        def rr_repl(m):
            rate = m.group(1).upper()
            spread_raw = m.group(2)
            try:
                sv = float(spread_raw)
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            tokens['reference_rate'] = rate
            tokens['spread'] = self._format_spread(str(sv))
            return ''
        text = re.sub(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', rr_repl, text, flags=re.IGNORECASE)
        def floor_repl(m):
            v = m.group(1) or m.group(2)
            tokens['floor_rate'] = self._percent(v)
            return ''
        text = re.sub(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', floor_repl, text, flags=re.IGNORECASE)
        def pik_repl(m):
            v = m.group(1) or m.group(2)
            tokens['pik_rate'] = self._percent(v)
            return ''
        text = re.sub(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', pik_repl, text, flags=re.IGNORECASE)
        def md_repl(m):
            tokens['maturity_date'] = m.group(1)
            return ''
        text = re.sub(r'\bMaturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})\b', md_repl, text, flags=re.IGNORECASE)
        text = re.sub(r'\s+[\-\u2013]\s+.*$', '', text).strip()
        text = re.sub(r'\s+', ' ', text).strip().rstrip(',')
        return (text if text else original), tokens

    def _format_spread(self, s: str) -> str:
        raw = str(s).strip().rstrip('%')
        try:
            v = float(raw)
        except:
            return self._percent(s)
        if v < 1:
            v *= 100.0
        elif v > 20:
            v /= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _format_rate(self, s: str) -> str:
        raw = str(s).strip().rstrip('%')
        try:
            v = float(raw)
        except:
            return self._percent(s)
        if v < 1:
            v *= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
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
    ex=CGBDExtractor()
    try:
        res=ex.extract_from_ticker('CGBD')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





                            if company_words and company_words[-1].lower().rstrip(',') == industry_first_word:
                                company_name = ' '.join(company_words[:-1]).strip().rstrip(',')
                
                res['company_name'] = company_name
        else:
            # Fallback: last part is industry
            industry = parts[-1].strip()
            res['industry'] = self._strip_footnote_refs(industry)
            # Everything in between is company name (may contain commas)
            if len(parts) > 2:
                company_name = ','.join(parts[1:-1]).strip()
                # Clean up company name
                company_name = self._strip_footnote_refs(company_name)
                res['company_name'] = company_name
        
        # Extract dates, rates, spreads from the original identifier if present
        tokens_text = identifier
        rr = re.search(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', tokens_text, re.IGNORECASE)
        if rr:
            rate = rr.group(1).upper()
            spread_raw = rr.group(2)
            try:
                sv = float(spread_raw)
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            res['reference_rate'] = rate
            res['spread'] = self._format_spread(str(sv))
        
        fl = re.search(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', tokens_text, re.IGNORECASE)
        if fl:
            floor_val = fl.group(1) or fl.group(2)
            res['floor_rate'] = self._percent(floor_val)
        
        pk = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', tokens_text, re.IGNORECASE)
        if pk:
            pik_val = pk.group(1) or pk.group(2)
            res['pik_rate'] = self._percent(pik_val)
        
        md = re.search(r'Maturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})', tokens_text, re.IGNORECASE)
        if md:
            date_str = md.group(1)
            # Normalize 2-digit year to 4-digit
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        ad = re.search(r'(?:Acquisition|Investment)\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})', tokens_text, re.IGNORECASE)
        if ad:
            date_str = ad.group(1)
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['acquisition_date'] = date_str
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[CGBDInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = CGBDInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        # Don't override company name if it was correctly parsed
        # Only extract tokens if needed
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
                inv.spread = self._format_spread(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._format_rate(v); continue
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
        if not inv.maturity_date:
            if context.get('maturity_date'):
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
        raw = str(s).strip().rstrip('%')
        try:
            v=float(raw)
        except:
            return f"{s}%"
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _extract_tokens_from_text(self, text: str):
        tokens = {'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None, 'maturity_date': None}
        original = text
        def rr_repl(m):
            rate = m.group(1).upper()
            spread_raw = m.group(2)
            try:
                sv = float(spread_raw)
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            tokens['reference_rate'] = rate
            tokens['spread'] = self._format_spread(str(sv))
            return ''
        text = re.sub(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', rr_repl, text, flags=re.IGNORECASE)
        def floor_repl(m):
            v = m.group(1) or m.group(2)
            tokens['floor_rate'] = self._percent(v)
            return ''
        text = re.sub(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', floor_repl, text, flags=re.IGNORECASE)
        def pik_repl(m):
            v = m.group(1) or m.group(2)
            tokens['pik_rate'] = self._percent(v)
            return ''
        text = re.sub(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', pik_repl, text, flags=re.IGNORECASE)
        def md_repl(m):
            tokens['maturity_date'] = m.group(1)
            return ''
        text = re.sub(r'\bMaturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})\b', md_repl, text, flags=re.IGNORECASE)
        text = re.sub(r'\s+[\-\u2013]\s+.*$', '', text).strip()
        text = re.sub(r'\s+', ' ', text).strip().rstrip(',')
        return (text if text else original), tokens

    def _format_spread(self, s: str) -> str:
        raw = str(s).strip().rstrip('%')
        try:
            v = float(raw)
        except:
            return self._percent(s)
        if v < 1:
            v *= 100.0
        elif v > 20:
            v /= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _format_rate(self, s: str) -> str:
        raw = str(s).strip().rstrip('%')
        try:
            v = float(raw)
        except:
            return self._percent(s)
        if v < 1:
            v *= 100.0
        out = f"{v:.4f}".rstrip('0').rstrip('.')
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
    ex=CGBDExtractor()
    try:
        res=ex.extract_from_ticker('CGBD')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()




