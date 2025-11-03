#!/usr/bin/env python3
"""
BBDC (Barings BDC Inc) Investment Extractor
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
class BBDCInvestment:
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


class BBDCExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "BBDC") -> Dict:
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
        return self.extract_from_url(txt_url, "Barings_BDC_Inc", cik)

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
        investments: List[BBDCInvestment] = []
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
        out_file = os.path.join(out_dir, 'BBDC_Barings_BDC_Inc_investments.csv')
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
            contexts.append({
                'id': cid,
                'investment_identifier': ident,
                'raw_identifier': ident,
                'company_name': parsed['company_name'],
                'industry': same_ind or parsed['industry'],
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None,
               'maturity_date': None}
        if ',' in identifier:
            last = identifier.rfind(',')
            company = identifier[:last].strip()
            tail = identifier[last+1:].strip()
        else:
            company = identifier.strip()
            tail = ''
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
            res['maturity_date'] = md.group(1)
        clean_company = re.sub(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*[\d\.]+%?', '', company, flags=re.IGNORECASE)
        clean_company = re.sub(r'\b(?:[\d\.]+\s*%\s*Floor|Floor\s*[\d\.]+\s*%)\b', '', clean_company, flags=re.IGNORECASE)
        clean_company = re.sub(r'\b(?:PIK\b[^\d%]{0,20}[\d\.]+\s*%|[\d\.]+\s*%\s*PIK)\b', '', clean_company, flags=re.IGNORECASE)
        clean_company = re.sub(r'\bMaturity\s*Date\s*\d{1,2}/\d{1,2}/\d{2,4}\b', '', clean_company, flags=re.IGNORECASE)
        clean_company = re.sub(r'\s+[\-\u2013]\s+.*$', '', clean_company).strip()
        res['company_name'] = re.sub(r'\s+',' ', clean_company).rstrip(',')
        patterns = [
            r'First\s+lien\s+.*$', r'Second\s+lien\s+.*$', r'Unitranche\s*\d*$', r'Senior\s+secured\s*\d*$',
            r'Secured\s+Debt\s*\d*$', r'Unsecured\s+Debt\s*\d*$', r'Preferred\s+Equity$', r'Preferred\s+Stock$',
            r'Common\s+Stock\s*\d*$', r'Member\s+Units\s*\d*$', r'Warrants?$'
        ]
        it = None
        for p in patterns:
            mm = re.search(p, tail, re.IGNORECASE)
            if mm:
                it = mm.group(0)
                break
        if not it and tail:
            it = tail
        if it:
            res['investment_type'] = it
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[BBDCInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = BBDCInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        raw_text = context.get('raw_identifier') or inv.company_name
        cleaned, tkns = self._extract_tokens_from_text(raw_text)
        if len(cleaned) <= len(inv.company_name) or inv.company_name.lower() in raw_text.lower():
            inv.company_name = cleaned
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
                inv.spread = self._format_spread(v)
                continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate = self._format_rate(v)
                continue
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
        if not inv.reference_rate and tkns.get('reference_rate'):
            inv.reference_rate = tkns['reference_rate']
        if not inv.spread and tkns.get('spread'):
            inv.spread = tkns['spread']
        if not inv.floor_rate and tkns.get('floor_rate'):
            inv.floor_rate = tkns['floor_rate']
        if not inv.pik_rate and tkns.get('pik_rate'):
            inv.pik_rate = tkns['pik_rate']
        if not inv.maturity_date and tkns.get('maturity_date'):
            inv.maturity_date = tkns['maturity_date']
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
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
    ex=BBDCExtractor()
    try:
        res=ex.extract_from_ticker('BBDC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





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
    ex=BBDCExtractor()
    try:
        res=ex.extract_from_ticker('BBDC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()




