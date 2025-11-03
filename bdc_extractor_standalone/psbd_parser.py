#!/usr/bin/env python3
import re, os, csv, logging, requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class PSBDInvestment:
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


class PSBDExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "PSBD") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        return self.extract_from_url(txt_url, "Palmer_Square_Capital_BDC_Inc", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        r = requests.get(filing_url, headers=self.headers)
        r.raise_for_status()
        content = r.text

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
        invs: List[PSBDInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                invs.append(inv)

        # de-dup
        ded, seen = [], set()
        for inv in invs:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen: continue
            seen.add(combo); ded.append(inv)
        invs = ded

        total_principal = sum(x.principal_amount or 0 for x in invs)
        total_cost = sum(x.cost or 0 for x in invs)
        total_fair_value = sum(x.fair_value or 0 for x in invs)
        ind = defaultdict(int); ty = defaultdict(int)
        for x in invs:
            ind[x.industry] += 1; ty[x.investment_type] += 1

        out_dir = 'output'; os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'PSBD_Palmer_Square_Capital_BDC_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['company_name','industry','business_description','investment_type','acquisition_date','maturity_date','principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'])
            w.writeheader()
            for x in invs:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(x.investment_type)
                standardized_industry = standardize_industry(x.industry)
                standardized_ref_rate = standardize_reference_rate(x.reference_rate)
                
                w.writerow({'company_name':x.company_name,'industry':standardized_industry,'business_description':x.business_description,'investment_type':standardized_inv_type,'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardized_ref_rate,'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate})
        logger.info(f"Saved to {out_file}")
        return {'company_name':company_name,'cik':cik,'total_investments':len(invs),'total_principal':total_principal,'total_cost':total_cost,'total_fair_value':total_fair_value,'industry_breakdown':dict(ind),'investment_type_breakdown':dict(ty)}

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        res = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1); html = m.group(2)
            tm = tp.search(html)
            if not tm: continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', html)
            sd = re.search(r'<startDate>([^<]+)</startDate>', html)
            ed = re.search(r'<endDate>([^<]+)</endDate>', html)
            same = None
            em = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', html, re.DOTALL|re.IGNORECASE)
            if em: same = self._industry_member_to_name(em.group(1).strip())
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same if same else 'Unknown')
            res.append({'id':cid,'investment_identifier':ident,'company_name':parsed['company_name'],'industry':final_industry,'investment_type':parsed['investment_type'],'instant':inst.group(1) if inst else None,'start_date':sd.group(1) if sd else None,'end_date':ed.group(1) if ed else None})
        return res

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        return re.sub(r'\s+',' ', cleaned).strip()
    
    def _parse_identifier(self, identifier: str) -> Dict[str,str]:
        res={'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        ident_clean = re.sub(r'\s+',' ', identifier).strip()
        
        # PSBD format: "Debt Investments First Lien Senior Secured [Company] Industry [Industry] Interest Rate X.XX% ... Maturity Date MM/DD/YYYY"
        # Or: "CLO Mezzanine [Name] Industry [Industry] Interest Rate X.XX% ... Maturity Date MM/DD/YYYY"
        
        # Extract investment type (First Lien, Second Lien, CLO Mezzanine, etc.)
        inv_type_patterns = [
            r'(CLO\s+Mezzanine[^I]*)',
            r'(First\s+Lien(?:\s+Senior\s+Secured)?)',
            r'(Second\s+Lien(?:\s+Senior\s+Secured)?)',
            r'(Unitranche(?:\s+\d*)?)',
            r'(Senior\s+Secured(?:\s+\d*)?)',
            r'(Secured\s+Debt(?:\s+\d*)?)',
            r'(Unsecured\s+Debt(?:\s+\d*)?)',
            r'(Preferred\s+Equity)',
            r'(Preferred\s+Stock)',
            r'(Common\s+Stock(?:\s+\d*)?)',
            r'(Member\s+Units(?:\s+\d*)?)',
            r'(Warrants?)'
        ]
        it = None
        for p in inv_type_patterns:
            mm = re.search(p, ident_clean, re.IGNORECASE)
            if mm:
                it = mm.group(1).strip()
                break
        if it:
            res['investment_type'] = it
        
        # Extract industry: look for "Industry [Industry Name]" pattern
        # Try multiple patterns to catch industry name
        ind_match = re.search(r'Industry\s+([^I]+?)(?:\s+Interest\s+Rate|\s+Maturity\s+Date)', ident_clean, re.IGNORECASE)
        if not ind_match:
            # Fallback: industry name might be shorter and directly before Interest Rate
            ind_match = re.search(r'Industry\s+([A-Z][A-Za-z\s]+?)(?:\s+(?:Interest\s+Rate|Maturity\s+Date))', ident_clean, re.IGNORECASE)
        if ind_match:
            industry_raw = ind_match.group(1).strip()
            # Clean up - remove trailing commas, periods, etc.
            industry_raw = industry_raw.rstrip(',.').strip()
            # Remove common trailing descriptors
            industry_raw = re.sub(r'\s+(Inc|LLC|Corp|Ltd|Company|Holdings)$', '', industry_raw, flags=re.IGNORECASE)
            if industry_raw and len(industry_raw) > 2:
                res['industry'] = industry_raw
        
        # Extract company name - it's between investment type and "Industry"
        # Pattern: "[Investment Type] [Company Name] Industry"
        if it:
            # Find position of investment type
            it_pos = ident_clean.upper().find(it.upper())
            if it_pos >= 0:
                # Text after investment type, before "Industry"
                after_it = ident_clean[it_pos + len(it):].strip()
                ind_pos = after_it.upper().find('INDUSTRY')
                if ind_pos > 0:
                    company_raw = after_it[:ind_pos].strip()
                    # Clean up company name - remove common suffixes/prefixes that might be part of the identifier
                    company_raw = re.sub(r'\s+', ' ', company_raw).strip()
                    # Remove trailing words that might be descriptors
                    # Keep the main company name (usually ends before common descriptors)
                    # For PSBD, company name is usually the main part before Industry
                    if company_raw:
                        # Remove "Senior Secured" if it appears after the company name
                        company_raw = re.sub(r'\s+Senior\s+Secured\s*$', '', company_raw, flags=re.IGNORECASE)
                        # Strip footnote references
                        company_raw = self._strip_footnote_refs(company_raw)
                        res['company_name'] = company_raw
        else:
            # Fallback: try to extract company name before "Industry" or at the start
            parts = re.split(r'\s+Industry\s+', ident_clean, flags=re.IGNORECASE, maxsplit=1)
            if len(parts) > 1:
                # Remove "Debt Investments" prefix if present
                candidate = parts[0].strip()
                candidate = re.sub(r'^Debt\s+Investments\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^CLO\s+Mezzanine\s+', '', candidate, flags=re.IGNORECASE)
                if candidate:
                    candidate = self._strip_footnote_refs(candidate)
                    res['company_name'] = candidate
        
        # Strip footnote refs from industry and investment type
        if res['industry'] != 'Unknown':
            res['industry'] = self._strip_footnote_refs(res['industry'])
        if res['investment_type'] != 'Unknown':
            res['investment_type'] = self._strip_footnote_refs(res['investment_type'])
        
        return res

    def _extract_facts(self, content: str) -> Dict[str,List[Dict]]:
        facts=defaultdict(list)
        sp=re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
        for concept,cref,val in sp.findall(content):
            if val and cref: facts[cref].append({'concept':concept,'value':val.strip()})
        ixp=re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name=m.group(1); cref=m.group(2); html=m.group(4)
            if not cref: continue
            txt=re.sub(r'<[^>]+>','',html).strip()
            if txt: facts[cref].append({'concept':name,'value':txt})
            start=max(0,m.start()-3000); end=min(len(content), m.end()+3000); window=content[start:end]
            ref=re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref: facts[cref].append({'concept':'derived:ReferenceRateToken','value':ref.group(1).replace('+','').upper()})
            floor=re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor: facts[cref].append({'concept':'derived:FloorRate','value':floor.group(1)})
            pik=re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik: facts[cref].append({'concept':'derived:PIKRate','value':pik.group(1)})
            dates=re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value':dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value':dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value':dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[PSBDInvestment]:
        if context['company_name']=='Unknown': return None
        inv=PSBDInvestment(company_name=context['company_name'],investment_type=context['investment_type'],industry=context['industry'],context_ref=context['id'])
        for f in facts:
            c=f['concept']; v=f['value']; v=v.replace(',',''); cl=c.lower()
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
                inv.spread=self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate=self._percent(v); continue
            if cl=='derived:referenceratetoken': inv.reference_rate=v.upper(); continue
            if cl=='derived:floorrate': inv.floor_rate=self._percent(v); continue
            if cl=='derived:pikrate': inv.pik_rate=self._percent(v); continue
            if cl=='derived:acquisitiondate': inv.acquisition_date=v; continue
            if cl=='derived:maturitydate': inv.maturity_date=v; continue
        if not inv.acquisition_date and context.get('start_date'): inv.acquisition_date=context['start_date'][:10]
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value): return inv
        return None

    def _percent(self, s: str) -> str:
        try: v=float(s)
        except: return f"{s}%"
        if 0<abs(v)<=1.0: v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={}; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
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
    ex=PSBDExtractor()
    try:
        res=ex.extract_from_ticker('PSBD')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()






from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class PSBDInvestment:
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


class PSBDExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "PSBD") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        return self.extract_from_url(txt_url, "Palmer_Square_Capital_BDC_Inc", cik)

    def extract_from_url(self, filing_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading XBRL from: {filing_url}")
        r = requests.get(filing_url, headers=self.headers)
        r.raise_for_status()
        content = r.text

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
        invs: List[PSBDInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                invs.append(inv)

        # de-dup
        ded, seen = [], set()
        for inv in invs:
            key = (inv.company_name, inv.investment_type, inv.maturity_date or '')
            val = (inv.principal_amount or 0.0, inv.cost or 0.0, inv.fair_value or 0.0)
            combo = (key, val)
            if combo in seen: continue
            seen.add(combo); ded.append(inv)
        invs = ded

        total_principal = sum(x.principal_amount or 0 for x in invs)
        total_cost = sum(x.cost or 0 for x in invs)
        total_fair_value = sum(x.fair_value or 0 for x in invs)
        ind = defaultdict(int); ty = defaultdict(int)
        for x in invs:
            ind[x.industry] += 1; ty[x.investment_type] += 1

        out_dir = 'output'; os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'PSBD_Palmer_Square_Capital_BDC_Inc_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['company_name','industry','business_description','investment_type','acquisition_date','maturity_date','principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'])
            w.writeheader()
            for x in invs:
                # Apply standardization
                standardized_inv_type = standardize_investment_type(x.investment_type)
                standardized_industry = standardize_industry(x.industry)
                standardized_ref_rate = standardize_reference_rate(x.reference_rate)
                
                w.writerow({'company_name':x.company_name,'industry':standardized_industry,'business_description':x.business_description,'investment_type':standardized_inv_type,'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardized_ref_rate,'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate})
        logger.info(f"Saved to {out_file}")
        return {'company_name':company_name,'cik':cik,'total_investments':len(invs),'total_principal':total_principal,'total_cost':total_cost,'total_fair_value':total_fair_value,'industry_breakdown':dict(ind),'investment_type_breakdown':dict(ty)}

    def _extract_typed_contexts(self, content: str) -> List[Dict]:
        res = []
        cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
        tp = re.compile(r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>\s*</xbrldi:typedMember>', re.DOTALL)
        for m in cp.finditer(content):
            cid = m.group(1); html = m.group(2)
            tm = tp.search(html)
            if not tm: continue
            ident = tm.group(1).strip()
            parsed = self._parse_identifier(ident)
            inst = re.search(r'<instant>([^<]+)</instant>', html)
            sd = re.search(r'<startDate>([^<]+)</startDate>', html)
            ed = re.search(r'<endDate>([^<]+)</endDate>', html)
            same = None
            em = re.search(r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>', html, re.DOTALL|re.IGNORECASE)
            if em: same = self._industry_member_to_name(em.group(1).strip())
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same if same else 'Unknown')
            res.append({'id':cid,'investment_identifier':ident,'company_name':parsed['company_name'],'industry':final_industry,'investment_type':parsed['investment_type'],'instant':inst.group(1) if inst else None,'start_date':sd.group(1) if sd else None,'end_date':ed.group(1) if ed else None})
        return res

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        return re.sub(r'\s+',' ', cleaned).strip()
    
    def _parse_identifier(self, identifier: str) -> Dict[str,str]:
        res={'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        ident_clean = re.sub(r'\s+',' ', identifier).strip()
        
        # PSBD format: "Debt Investments First Lien Senior Secured [Company] Industry [Industry] Interest Rate X.XX% ... Maturity Date MM/DD/YYYY"
        # Or: "CLO Mezzanine [Name] Industry [Industry] Interest Rate X.XX% ... Maturity Date MM/DD/YYYY"
        
        # Extract investment type (First Lien, Second Lien, CLO Mezzanine, etc.)
        inv_type_patterns = [
            r'(CLO\s+Mezzanine[^I]*)',
            r'(First\s+Lien(?:\s+Senior\s+Secured)?)',
            r'(Second\s+Lien(?:\s+Senior\s+Secured)?)',
            r'(Unitranche(?:\s+\d*)?)',
            r'(Senior\s+Secured(?:\s+\d*)?)',
            r'(Secured\s+Debt(?:\s+\d*)?)',
            r'(Unsecured\s+Debt(?:\s+\d*)?)',
            r'(Preferred\s+Equity)',
            r'(Preferred\s+Stock)',
            r'(Common\s+Stock(?:\s+\d*)?)',
            r'(Member\s+Units(?:\s+\d*)?)',
            r'(Warrants?)'
        ]
        it = None
        for p in inv_type_patterns:
            mm = re.search(p, ident_clean, re.IGNORECASE)
            if mm:
                it = mm.group(1).strip()
                break
        if it:
            res['investment_type'] = it
        
        # Extract industry: look for "Industry [Industry Name]" pattern
        # Try multiple patterns to catch industry name
        ind_match = re.search(r'Industry\s+([^I]+?)(?:\s+Interest\s+Rate|\s+Maturity\s+Date)', ident_clean, re.IGNORECASE)
        if not ind_match:
            # Fallback: industry name might be shorter and directly before Interest Rate
            ind_match = re.search(r'Industry\s+([A-Z][A-Za-z\s]+?)(?:\s+(?:Interest\s+Rate|Maturity\s+Date))', ident_clean, re.IGNORECASE)
        if ind_match:
            industry_raw = ind_match.group(1).strip()
            # Clean up - remove trailing commas, periods, etc.
            industry_raw = industry_raw.rstrip(',.').strip()
            # Remove common trailing descriptors
            industry_raw = re.sub(r'\s+(Inc|LLC|Corp|Ltd|Company|Holdings)$', '', industry_raw, flags=re.IGNORECASE)
            if industry_raw and len(industry_raw) > 2:
                res['industry'] = industry_raw
        
        # Extract company name - it's between investment type and "Industry"
        # Pattern: "[Investment Type] [Company Name] Industry"
        if it:
            # Find position of investment type
            it_pos = ident_clean.upper().find(it.upper())
            if it_pos >= 0:
                # Text after investment type, before "Industry"
                after_it = ident_clean[it_pos + len(it):].strip()
                ind_pos = after_it.upper().find('INDUSTRY')
                if ind_pos > 0:
                    company_raw = after_it[:ind_pos].strip()
                    # Clean up company name - remove common suffixes/prefixes that might be part of the identifier
                    company_raw = re.sub(r'\s+', ' ', company_raw).strip()
                    # Remove trailing words that might be descriptors
                    # Keep the main company name (usually ends before common descriptors)
                    # For PSBD, company name is usually the main part before Industry
                    if company_raw:
                        # Remove "Senior Secured" if it appears after the company name
                        company_raw = re.sub(r'\s+Senior\s+Secured\s*$', '', company_raw, flags=re.IGNORECASE)
                        # Strip footnote references
                        company_raw = self._strip_footnote_refs(company_raw)
                        res['company_name'] = company_raw
        else:
            # Fallback: try to extract company name before "Industry" or at the start
            parts = re.split(r'\s+Industry\s+', ident_clean, flags=re.IGNORECASE, maxsplit=1)
            if len(parts) > 1:
                # Remove "Debt Investments" prefix if present
                candidate = parts[0].strip()
                candidate = re.sub(r'^Debt\s+Investments\s+', '', candidate, flags=re.IGNORECASE)
                candidate = re.sub(r'^CLO\s+Mezzanine\s+', '', candidate, flags=re.IGNORECASE)
                if candidate:
                    candidate = self._strip_footnote_refs(candidate)
                    res['company_name'] = candidate
        
        # Strip footnote refs from industry and investment type
        if res['industry'] != 'Unknown':
            res['industry'] = self._strip_footnote_refs(res['industry'])
        if res['investment_type'] != 'Unknown':
            res['investment_type'] = self._strip_footnote_refs(res['investment_type'])
        
        return res

    def _extract_facts(self, content: str) -> Dict[str,List[Dict]]:
        facts=defaultdict(list)
        sp=re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
        for concept,cref,val in sp.findall(content):
            if val and cref: facts[cref].append({'concept':concept,'value':val.strip()})
        ixp=re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name=m.group(1); cref=m.group(2); html=m.group(4)
            if not cref: continue
            txt=re.sub(r'<[^>]+>','',html).strip()
            if txt: facts[cref].append({'concept':name,'value':txt})
            start=max(0,m.start()-3000); end=min(len(content), m.end()+3000); window=content[start:end]
            ref=re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref: facts[cref].append({'concept':'derived:ReferenceRateToken','value':ref.group(1).replace('+','').upper()})
            floor=re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor: facts[cref].append({'concept':'derived:FloorRate','value':floor.group(1)})
            pik=re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik: facts[cref].append({'concept':'derived:PIKRate','value':pik.group(1)})
            dates=re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
            if dates:
                if len(dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value':dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value':dates[-1]})
                else:
                    facts[cref].append({'concept':'derived:MaturityDate','value':dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[PSBDInvestment]:
        if context['company_name']=='Unknown': return None
        inv=PSBDInvestment(company_name=context['company_name'],investment_type=context['investment_type'],industry=context['industry'],context_ref=context['id'])
        for f in facts:
            c=f['concept']; v=f['value']; v=v.replace(',',''); cl=c.lower()
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
                inv.spread=self._percent(v); continue
            if 'investmentinterestrate' in cl:
                inv.interest_rate=self._percent(v); continue
            if cl=='derived:referenceratetoken': inv.reference_rate=v.upper(); continue
            if cl=='derived:floorrate': inv.floor_rate=self._percent(v); continue
            if cl=='derived:pikrate': inv.pik_rate=self._percent(v); continue
            if cl=='derived:acquisitiondate': inv.acquisition_date=v; continue
            if cl=='derived:maturitydate': inv.maturity_date=v; continue
        if not inv.acquisition_date and context.get('start_date'): inv.acquisition_date=context['start_date'][:10]
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value): return inv
        return None

    def _percent(self, s: str) -> str:
        try: v=float(s)
        except: return f"{s}%"
        if 0<abs(v)<=1.0: v*=100.0
        out=f"{v:.4f}".rstrip('0').rstrip('.')
        return f"{out}%"

    def _build_industry_index(self, content: str) -> Dict[str,str]:
        m={}; cp=re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
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
    ex=PSBDExtractor()
    try:
        res=ex.extract_from_ticker('PSBD')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





