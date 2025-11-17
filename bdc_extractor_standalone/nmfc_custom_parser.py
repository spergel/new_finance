#!/usr/bin/env python3
"""
Custom NMFC (New Mountain Finance Corp) Investment Extractor

NMFC uses XBRL primarily with HTML table enhancement for dates and rates.
Rewritten to use direct XBRL extraction (no TypedMemberExtractor dependency).
"""

import logging
import os
import re
import html
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import csv
from collections import defaultdict
from dataclasses import dataclass

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


@dataclass
class NMFCInvestment:
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
    shares_units: Optional[str] = None
    percent_net_assets: Optional[str] = None
    currency: Optional[str] = None
    commitment_limit: Optional[float] = None
    undrawn_commitment: Optional[float] = None


class NMFCCustomExtractor:
    """Custom extractor for NMFC that uses XBRL with HTML enhancement."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "NMFC", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from NMFC's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        # Get URLs
        match = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
        if not match:
            raise ValueError("Could not parse accession/URLs for NMFC")
        
        accession = match.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        
        return self.extract_from_url(txt_url, "New_Mountain_Finance_Corp", cik)
    
    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        """Extract complete NMFC investment data from XBRL."""
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
        investments: List[NMFCInvestment] = []
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

        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'NMFC_New_Mountain_Finance_Corp_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate',
                'shares_units', 'percent_net_assets', 'currency', 'commitment_limit', 'undrawn_commitment'
            ])
            writer.writeheader()
            for inv in investments:
                standardized_inv_type = standardize_investment_type(inv.investment_type)
                standardized_industry = standardize_industry(inv.industry)
                standardized_ref_rate = standardize_reference_rate(inv.reference_rate)
                
                writer.writerow({
                    'company_name': inv.company_name,
                    'industry': standardized_industry,
                    'business_description': inv.business_description or '',
                    'investment_type': standardized_inv_type,
                    'acquisition_date': inv.acquisition_date or '',
                    'maturity_date': inv.maturity_date or '',
                    'principal_amount': inv.principal_amount or '',
                    'cost': inv.cost or '',
                    'fair_value': inv.fair_value or '',
                    'interest_rate': inv.interest_rate or '',
                    'reference_rate': standardized_ref_rate or '',
                    'spread': inv.spread or '',
                    'floor_rate': inv.floor_rate or '',
                    'pik_rate': inv.pik_rate or '',
                    'shares_units': inv.shares_units or '',
                    'percent_net_assets': inv.percent_net_assets or '',
                    'currency': inv.currency or 'USD',
                    'commitment_limit': inv.commitment_limit or '',
                    'undrawn_commitment': inv.undrawn_commitment or '',
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
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same_ind if same_ind else 'Unknown')
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'raw_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': final_industry,
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res: Dict[str, Optional[str]] = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        text = html.unescape(identifier)
        
        # Remove leading classification phrases
        text = re.sub(r'^(Non-?Control/Non-?Affiliate Investments|Control/Non-?Affiliate Investments|Debt Investments|Equity Investments|Warrants)\s+', '', text, flags=re.IGNORECASE)
        
        # Try to find "Investment Type" as an anchor
        it_anchor = re.search(r'\bInvestment\s+Type\b', text, re.IGNORECASE)
        company_segment = text
        if it_anchor:
            company_segment = text[:it_anchor.start()].strip()
        
        # Remove any remaining "Warrants", "Debt Investments", "Equity Investments" prefixes
        company_segment = re.sub(r'^(Warrants|Debt Investments|Equity Investments)\s+', '', company_segment, flags=re.IGNORECASE)
        
        # Try to extract company name with proper entity suffix
        company_matches = list(re.finditer(r'([A-Z][A-Za-z0-9\s&,\-\.]+?(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.|SE|N\.V\.))\b', company_segment))
        if company_matches:
            company_match = company_matches[-1]
            company_name = company_match.group(1).strip().rstrip(',').strip()
            
            company_pos = company_match.start()
            if company_pos > 0:
                industry_text = company_segment[:company_pos].strip().rstrip(',').strip()
                industry_text = re.sub(r'^(Warrants|Debt Investments|Equity Investments)\s+', '', industry_text, flags=re.IGNORECASE)
                industry_text = self._clean_industry(industry_text)
                if industry_text and len(industry_text.split()) <= 6:
                    res['industry'] = industry_text
            
            res['company_name'] = company_name
        else:
            guessed = self._guess_company_from_text(company_segment)
            if guessed and guessed != 'Unknown':
                guessed = self._clean_company_name(guessed)
                if guessed and guessed != 'Unknown':
                    res['company_name'] = guessed
                    company_pos = company_segment.find(guessed)
                    if company_pos > 0:
                        industry_text = company_segment[:company_pos].strip().rstrip(',').strip()
                        industry_text = re.sub(r'^(Warrants|Debt Investments|Equity Investments)\s+', '', industry_text, flags=re.IGNORECASE)
                        industry_text = self._clean_industry(industry_text)
                        if industry_text and len(industry_text.split()) <= 6:
                            res['industry'] = industry_text
        
        # Investment type from the text around anchor
        tail = text[it_anchor.end():] if it_anchor else text
        inv_type = None
        for p in [r'Senior\s+Secured', r'First\s+Lien.*?Term\s+Loan', r'Second\s+Lien.*?Term\s+Loan', r'Unitranche', r'Revolver', r'Warrants?', r'Equity', r'Preferred\s+Stock', r'Common\s+Stock']:
            m = re.search(p, tail, re.IGNORECASE)
            if m:
                inv_type = m.group(0)
                break
        if inv_type:
            res['investment_type'] = inv_type.strip()
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept = match.group(1); cref = match.group(2); unit_ref = match.group(3); val = match.group(4)
            if val and cref:
                fact_entry = {'concept': concept, 'value': val.strip()}
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match: fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
        ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:unitRef="([^"]*)")?[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name = m.group(1); cref = m.group(2); unit_ref = m.group(3); html = m.group(5)
            if not cref: continue
            txt = re.sub(r'<[^>]+>', '', html).strip()
            if txt:
                fact_entry = {'concept': name, 'value': txt}
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match: fact_entry['currency'] = currency_match.group(1)
                facts[cref].append(fact_entry)
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
            dates = []
            dates.extend(re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', window))
            dates.extend(re.findall(r'\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{1,2}/\d{4}\b', window))
            if dates:
                seen = set(); unique_dates = []
                for d in dates:
                    if d not in seen: seen.add(d); unique_dates.append(d)
                if len(unique_dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[-1]})
                elif len(unique_dates)==1:
                    date_idx = window.find(unique_dates[0])
                    date_context = window[max(0,date_idx-50):min(len(window),date_idx+50)]
                    if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', date_context, re.IGNORECASE):
                        facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    else:
                        facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[NMFCInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = NMFCInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        raw = context.get('raw_identifier', '')
        toks = self._extract_tokens_from_identifier(raw)
        if toks.get('company_name') and len(toks['company_name']) <= len(inv.company_name):
            inv.company_name = toks['company_name']
        if toks.get('industry') and inv.industry in ('Unknown', None, ''):
            inv.industry = toks['industry']
        if toks.get('investment_type') and inv.investment_type in ('Unknown', None, ''):
            inv.investment_type = toks['investment_type']
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
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val = v.strip().replace(',', '')
                    float(shares_val)
                    inv.shares_units = shares_val
                except: pass
                continue
            if 'currency' in f: inv.currency = f.get('currency')
        if not inv.reference_rate and toks.get('reference_rate'):
            inv.reference_rate = toks['reference_rate']
        if not inv.spread and toks.get('spread'):
            inv.spread = toks['spread']
        if not inv.floor_rate and toks.get('floor_rate'):
            inv.floor_rate = toks['floor_rate']
        if not inv.interest_rate and toks.get('interest_rate'):
            inv.interest_rate = toks['interest_rate']
        if not inv.pik_rate and toks.get('pik_rate'):
            inv.pik_rate = toks['pik_rate']
        if not inv.acquisition_date and toks.get('acquisition_date'):
            inv.acquisition_date = toks['acquisition_date']
        if not inv.maturity_date and toks.get('maturity_date'):
            inv.maturity_date = toks['maturity_date']

        inv.company_name = self._clean_company_name(inv.company_name)

        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        if inv.fair_value and not inv.principal_amount: inv.commitment_limit = inv.fair_value
        elif inv.fair_value and inv.principal_amount:
            if inv.fair_value > inv.principal_amount:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value - inv.principal_amount
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _extract_tokens_from_identifier(self, text: str) -> Dict[str, Optional[str]]:
        out: Dict[str, Optional[str]] = {
            'company_name': None, 'industry': None, 'investment_type': None,
            'reference_rate': None, 'spread': None, 'floor_rate': None,
            'interest_rate': None, 'pik_rate': None,
            'acquisition_date': None, 'maturity_date': None
        }
        if not text:
            return out
        s = html.unescape(text)
        s = re.sub(r'^(Non-?Control/Non-?Affiliate Investments|Control/Non-?Affiliate Investments|Debt Investments|Equity Investments|Warrants)\s+', '', s, flags=re.IGNORECASE)
        acq = re.search(r'Initial\s+Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})', s, re.IGNORECASE)
        if acq:
            out['acquisition_date'] = acq.group(1)
        mat = re.search(r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})', s, re.IGNORECASE)
        if mat:
            out['maturity_date'] = mat.group(1)
        ref_spread = re.search(r'\b(SOFR|PRIME|LIBOR|BASE\s+RATE|EURIBOR)\s*\+\s*([\d\.]+)%', s, re.IGNORECASE)
        if ref_spread:
            out['reference_rate'] = ref_spread.group(1).upper().replace(' ', '')
            out['spread'] = self._format_spread(ref_spread.group(2))
        floor = re.search(r'\b(\d{1,2}\.\d{1,2}|\d{1,2})%\s*floor\b', s, re.IGNORECASE)
        if floor:
            out['floor_rate'] = self._percent(floor.group(1))
        floor2 = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)%', s, re.IGNORECASE)
        if floor2 and not out['floor_rate']:
            out['floor_rate'] = self._percent(floor2.group(1))
        pik = re.search(r'\b([\d\.]+)%\s*PIK\b', s, re.IGNORECASE)
        if pik:
            out['pik_rate'] = self._percent(pik.group(1))
        coup = re.search(r'Total\s+Coupon\s+([\d\.]+)%', s, re.IGNORECASE)
        if coup:
            out['interest_rate'] = self._percent(coup.group(1))
        it = re.search(r'Investment\s+Type\s+([^,]+)', s, re.IGNORECASE)
        if it:
            out['investment_type'] = it.group(1).strip()
        before_it = s.split('Investment Type', 1)[0] if 'Investment Type' in s else s
        before_it = before_it.strip()
        before_it = re.sub(r'^(Warrants|Debt Investments|Equity Investments)\s+', '', before_it, flags=re.IGNORECASE)
        company_matches = list(re.finditer(r'([A-Z][A-Za-z0-9\s&,\-\.]+?(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.|SE|N\.V\.))\b', before_it))
        if company_matches:
            company_match = company_matches[-1]
            company_name = company_match.group(1).strip().rstrip(',').strip()
            out['company_name'] = company_name
            company_pos = company_match.start()
            if company_pos > 0:
                industry_text = before_it[:company_pos].strip().rstrip(',').strip()
                industry_text = re.sub(r'^(Debt Investments|Equity Investments|Warrants)\s+', '', industry_text, flags=re.IGNORECASE)
                industry_text = self._clean_industry(industry_text)
                if industry_text and len(industry_text.split()) <= 6:
                    out['industry'] = industry_text
        else:
            guessed = self._guess_company_from_text(before_it)
            if guessed and guessed != 'Unknown':
                guessed = self._clean_company_name(guessed)
                if guessed and guessed != 'Unknown':
                    out['company_name'] = guessed
                    original_guessed = self._guess_company_from_text(before_it)
                    company_pos = before_it.find(original_guessed) if original_guessed else -1
                    if company_pos > 0:
                        industry_text = before_it[:company_pos].strip().rstrip(',').strip()
                        industry_text = re.sub(r'^(Debt Investments|Equity Investments|Warrants)\s+', '', industry_text, flags=re.IGNORECASE)
                        industry_text = self._clean_industry(industry_text)
                        if industry_text and len(industry_text.split()) <= 6:
                            out['industry'] = industry_text
        if out['company_name']:
            out['company_name'] = re.sub(r'\s+', ' ', out['company_name']).strip().rstrip(',')
        if out['industry']:
            out['industry'] = re.sub(r'\s+', ' ', out['industry']).strip().rstrip(',')
        return out

    def _guess_company_from_text(self, text: str) -> str:
        t = re.sub(r"\s+", " ", text).strip().strip(',')
        industry_prefixes = [
            r'^Application\s+Software\s+',
            r'^Technology\s+Hardware\s+&\s+Equipment\s+',
            r'^Financial\s+Services\s+',
            r'^Commercial\s+&\s+Professional\s+Services\s+',
            r'^Consumer\s+Staples\s+Distribution\s+&\s+Retail\s+',
            r'^Media\s+&\s+Entertainment\s+',
            r'^Insurance\s+',
            r'^Household\s+and\s+Personal\s+Products\s+',
        ]
        for prefix in industry_prefixes:
            t = re.sub(prefix, '', t, flags=re.IGNORECASE)
        m = re.search(r'([A-Z][\w.&()\- ]{2,}?(?:Inc\.?|Corporation|Corp\.?|Ltd\.?|LLC|L\.L\.C\.|SE|N\.V\.|Limited|Holdings?|Group|Company|Technologies|Technology|Bio|Insurance|Labs|Software|Systems|Solutions|Holdco))\b', t)
        if m:
            return m.group(1).strip()
        caps = re.findall(r'(?:\b[A-Z][a-zA-Z0-9.&()\-]+\b)', t)
        if len(caps) >= 2:
            filtered = [c for c in caps if c.lower() not in ['investment', 'type', 'debt', 'equity', 'warrants']]
            if len(filtered) >= 2:
                return ' '.join(filtered[-2:])
            elif len(filtered) >= 1:
                return filtered[-1]
            return ' '.join(caps[-2:])
        if len(caps) == 1 and len(caps[0]) > 3:
            return caps[0]
        return t if t and len(t) > 3 else 'Unknown'

    def _clean_industry(self, industry: str) -> Optional[str]:
        if not industry:
            return None
        s = html.unescape(industry)
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r'[A-Z][A-Za-z0-9\s&,\-\.]+?(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.|SE|N\.V\.|Group|Technologies|Technology|Software|Systems|Solutions|Holdco|Holdings)\b', '', s)
        s = re.sub(r'\([^)]*fka[^)]*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\([^)]*formerly[^)]*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\bfka\b', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\bformerly\b', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\([^)]*$', '', s)
        s = re.sub(r'^[^(]*\)', '', s)
        s = re.sub(r'\b(Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|LP|L\.P\.|Holdings|Holdco|Limited|Company|Co\.|SE|N\.V\.)\b', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^[,\s\.\-]+', '', s)
        s = re.sub(r'[,\s\.\-]+$', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if len(s) < 3:
            return None
        words = s.split()
        if len(words) == 1 and words[0].lower() in ['software', 'systems', 'technology', 'solutions', 'services', 'holdings', 'group']:
            return None
        if re.search(r'\d', s):
            return None
        return s if s else None

    def _clean_company_name(self, name: str) -> str:
        if not name:
            return name
        s = html.unescape(name)
        s = re.sub(r"\s+" , " ", s).strip().strip(',')
        s = re.sub(r'^(Warrants|Debt Investments|Equity Investments)\s+', '', s, flags=re.IGNORECASE)
        industry_prefixes = [
            r'^Application\s+Software\s+',
            r'^Technology\s+Hardware\s+&\s+Equipment\s+',
            r'^Financial\s+Services\s+',
            r'^Commercial\s+&\s+Professional\s+Services\s+',
            r'^Consumer\s+Staples\s+Distribution\s+&\s+Retail\s+',
            r'^Media\s+&\s+Entertainment\s+',
            r'^Insurance\s+',
            r'^Household\s+and\s+Personal\s+Products\s+',
            r'^Health\s+Care\s+Equipment\s+&\s+Services\s+',
            r'^Systems\s+',
            r'^Technology\s+',
        ]
        for prefix in industry_prefixes:
            s = re.sub(prefix, '', s, flags=re.IGNORECASE)
        s = re.sub(r'^(and|&|services|service|systems|application|applications|commercial|professional|supplies|software|technology|hardware|equipment|financial|insurance|media|entertainment|consumer|staples|distribution|retail|household|personal|products)\b\s+', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\b(Common|Preferred)\s+Stock\b$', '', s, flags=re.IGNORECASE).strip().strip(',')
        s = re.sub(r'\b(Investment|Investments|Debt|Equity|Warrants)\b$', '', s, flags=re.IGNORECASE).strip().strip(',')
        if s.strip() in ['Inc', 'LLC', 'Ltd', 'Corp', 'Inc.', 'LLC.', 'Ltd.', 'Corp.', 'Software', 'Systems', 'Technology']:
            return 'Unknown'
        if len(s.strip()) < 3:
            return 'Unknown'
        return s

    def _percent(self, s: str) -> str:
        raw = str(s).strip().rstrip('%')
        try:
            v=float(raw)
        except:
            return f"{s}%"
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

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
    ex=NMFCCustomExtractor()
    try:
        res=ex.extract_from_ticker('NMFC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()
