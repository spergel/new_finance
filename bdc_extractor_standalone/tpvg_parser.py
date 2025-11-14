#!/usr/bin/env python3
import re, os, csv, logging, requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class TPVGInvestment:
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


class TPVGExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "TPVG") -> Dict:
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
        return self.extract_from_url(txt_url, "TriplePoint_Venture_Growth_BDC", cik)

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
        invs: List[TPVGInvestment] = []
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

        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'TPVG_TriplePoint_Venture_Growth_BDC_investments.csv')
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
        inv_dicts = [{'company_name':x.company_name,'industry':standardize_industry(x.industry),'business_description':x.business_description,'investment_type':standardize_investment_type(x.investment_type),'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardize_reference_rate(x.reference_rate),'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate} for x in invs]
        return {'company_name':company_name,'cik':cik,'total_investments':len(invs),'investments':inv_dicts,'total_principal':total_principal,'total_cost':total_cost,'total_fair_value':total_fair_value,'industry_breakdown':dict(ind),'investment_type_breakdown':dict(ty)}

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
            res.append({'id':cid,'investment_identifier':ident,'company_name':parsed['company_name'],'industry':same or parsed['industry'],'investment_type':parsed['investment_type'],'instant':inst.group(1) if inst else None,'start_date':sd.group(1) if sd else None,'end_date':ed.group(1) if ed else None})
        return res

    def _parse_identifier(self, identifier: str) -> Dict[str,str]:
        res={'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        
        # More comprehensive investment type patterns - ordered from specific to general
        type_patterns = [
            r'First\s+Lien\s+Secured\s+Delayed\s+Draw\s+Loan',
            r'First\s+Lien\s+Secured\s+Revolving\s+Loan',
            r'First\s+Lien\s+Secured\s+Term\s+Loan',
            r'First\s+Lien\s+Secured\s+.*',
            r'First\s+lien\s+.*',
            r'Second\s+Lien\s+Secured\s+Term\s+Loan',
            r'Second\s+Lien\s+Secured\s+.*',
            r'Second\s+lien\s+.*',
            r'Unitranche\s*\d*',
            r'Senior\s+secured\s+\d*',
            r'Secured\s+Debt\s*\d*',
            r'Unsecured\s+Debt\s*\d*',
            r'Preferred\s+Equity',
            r'Preferred\s+Stock',
            r'Preferred\s+Shares',
            r'Common\s+Stock\s*\d*',
            r'Common\s+Equity',
            r'Common\s+Shares',
            r'Member\s+Units\s*\d*',
            r'Member\s+Interests',
            r'Equity',
            r'Interests',
            r'Warrants?',
        ]
        
        # Try to find investment type in the full identifier first
        it = None
        it_match = None
        for p in type_patterns:
            mm = re.search(p, identifier, re.IGNORECASE)
            if mm:
                it = mm.group(0).strip()
                it_match = mm
                break
        
        # If found, extract company name by removing the investment type
        if it and it_match:
            company = identifier[:it_match.start()].strip()
            # If there's a comma, prefer part before last comma
            if ',' in company:
                last_comma = company.rfind(',')
                company = company[:last_comma].strip()
            res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',').strip()
            res['investment_type'] = it
        else:
            # Fallback: try comma-separated format
            if ',' in identifier:
                last = identifier.rfind(',')
                company = identifier[:last].strip()
                tail = identifier[last+1:].strip()
            else:
                company = identifier.strip()
                tail = ''
            
            res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',').strip()
            
            # Try patterns on tail
            if tail:
                for p in type_patterns:
                    mm = re.search(p, tail, re.IGNORECASE)
                    if mm:
                        it = mm.group(0).strip()
                        break
                if not it:
                    it = tail.strip()
            
            if it:
                res['investment_type'] = it
        
        return res

    def _extract_facts(self, content: str) -> Dict[str,List[Dict]]:
        facts=defaultdict(list)
        # Extract standard XBRL facts and capture unitRef for currency
        sp=re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept=match.group(1); cref=match.group(2); unit_ref=match.group(3); val=match.group(4)
            if val and cref:
                fact_entry={'concept':concept,'value':val.strip()}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match=re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match: fact_entry['currency']=currency_match.group(1)
                facts[cref].append(fact_entry)
        ixp=re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:unitRef="([^"]*)")?[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
        for m in ixp.finditer(content):
            name=m.group(1); cref=m.group(2); unit_ref=m.group(3); html=m.group(5)
            if not cref: continue
            txt=re.sub(r'<[^>]+>','',html).strip()
            if txt:
                fact_entry={'concept':name,'value':txt}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match=re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match: fact_entry['currency']=currency_match.group(1)
                facts[cref].append(fact_entry)
            start=max(0,m.start()-3000); end=min(len(content), m.end()+3000); window=content[start:end]
            ref=re.search(r'\b(SOFR\+|PRIME\+|LIBOR\+|Base Rate\+|EURIBOR\+)\b', window, re.IGNORECASE)
            if ref: facts[cref].append({'concept':'derived:ReferenceRateToken','value':ref.group(1).replace('+','').upper()})
            floor=re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if floor: facts[cref].append({'concept':'derived:FloorRate','value':floor.group(1)})
            pik=re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
            if pik: facts[cref].append({'concept':'derived:PIKRate','value':pik.group(1)})
            # Try multiple date patterns
            dates=[]
            dates.extend(re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', window))
            dates.extend(re.findall(r'\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{1,2}/\d{4}\b', window))
            if dates:
                # Remove duplicates
                seen=set(); unique_dates=[]
                for d in dates:
                    if d not in seen: seen.add(d); unique_dates.append(d)
                if len(unique_dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value':unique_dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value':unique_dates[-1]})
                elif len(unique_dates)==1:
                    date_idx=window.find(unique_dates[0])
                    date_context=window[max(0,date_idx-50):min(len(window),date_idx+50)]
                    if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', date_context, re.IGNORECASE):
                        facts[cref].append({'concept':'derived:AcquisitionDate','value':unique_dates[0]})
                    else:
                        facts[cref].append({'concept':'derived:MaturityDate','value':unique_dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[TPVGInvestment]:
        if context['company_name']=='Unknown': return None
        inv=TPVGInvestment(company_name=context['company_name'],investment_type=context['investment_type'],industry=context['industry'],context_ref=context['id'])
        for f in facts:
            c=f['concept']; v=f['value']; v_clean=v.replace(',','').strip(); cl=c.lower()
            if any(k in cl for k in ['principalamount','ownedbalanceprincipalamount','outstandingprincipal']):
                try: inv.principal_amount=float(v_clean)
                except: pass; continue
            if ('cost' in cl and ('amortized' in cl or 'basis' in cl)) or 'ownedatcost' in cl:
                try: inv.cost=float(v_clean)
                except: pass; continue
            if 'fairvalue' in cl or ('fair' in cl and 'value' in cl) or 'ownedatfairvalue' in cl:
                try: inv.fair_value=float(v_clean)
                except: pass; continue
            # Maturity date
            if 'maturitydate' in cl or ('maturity' in cl and 'date' in cl) or cl=='derived:maturitydate':
                inv.maturity_date=v.strip()
                continue
            # Acquisition date
            if 'acquisitiondate' in cl or 'investmentdate' in cl or cl=='derived:acquisitiondate':
                inv.acquisition_date=v.strip()
                continue
            # Reference rate (check BEFORE interest rate)
            if cl=='derived:referenceratetoken' or 'variableinterestratetype' in cl or ('reference' in cl and 'rate' in cl):
                if 'sofr' in cl or 'sofr' in v.lower():
                    inv.reference_rate='SOFR'
                elif 'libor' in cl or 'libor' in v.lower():
                    inv.reference_rate='LIBOR'
                elif 'prime' in cl or 'prime' in v.lower():
                    inv.reference_rate='PRIME'
                elif v and not v.startswith('http'):
                    inv.reference_rate=v.upper().strip()
                continue
            # Interest rate (skip if URL)
            if 'interestrate' in cl and 'floor' not in cl:
                if v and not v.startswith('http'):
                    inv.interest_rate=self._percent(v_clean)
                continue
            # Spread
            if 'spread' in cl or ('basis' in cl and 'spread' in cl) or 'investmentbasisspreadvariablerate' in cl:
                inv.spread=self._percent(v_clean)
                continue
            # Floor rate
            if 'floor' in cl and 'rate' in cl or cl=='derived:floorrate':
                inv.floor_rate=self._percent(v_clean)
                continue
            # PIK rate
            if 'pik' in cl and 'rate' in cl or cl=='derived:pikrate':
                inv.pik_rate=self._percent(v_clean)
                continue
            # Extract shares/units for equity investments
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val=v.strip().replace(',','')
                    float(shares_val)  # Validate
                    inv.shares_units=shares_val
                except: pass
                continue
            # Extract currency from fact metadata
            if 'currency' in f: inv.currency=f.get('currency')
        if not inv.acquisition_date and context.get('start_date'): inv.acquisition_date=context['start_date'][:10]
        # Heuristic for commitment_limit and undrawn_commitment
        if inv.fair_value and not inv.principal_amount: inv.commitment_limit=inv.fair_value
        elif inv.fair_value and inv.principal_amount:
            if inv.fair_value>inv.principal_amount:
                inv.commitment_limit=inv.fair_value
                inv.undrawn_commitment=inv.fair_value-inv.principal_amount
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
    # HTML Schedule of Investments extraction (mirrors WHF header-mapped flow)
    import requests
    from bs4 import BeautifulSoup
    
    # Import BeautifulSoup at module level for type hints
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from bs4 import BeautifulSoup

    def normalize_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def normalize_key(text: str) -> str:
        return normalize_text(text).lower()

    def strip_footnote_refs(text: Optional[str]) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        return normalize_text(cleaned)

    def extract_tables_under_heading(soup: BeautifulSoup) -> List[BeautifulSoup]:
        matches: List[BeautifulSoup] = []
        def contains_date_like(blob: str) -> bool:
            return re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", blob, re.IGNORECASE) is not None
        required_any = [
            "schedule of investments",
            "continued",
            "unaudited",
            "dollar amounts in thousands",
        ]
        def heading_matches(blob: str) -> bool:
            blob_l = blob
            if "schedule of investments" not in blob_l:
                return False
            if not contains_date_like(blob_l):
                count = sum(1 for t in required_any if t in blob_l)
                if count < 2:
                    return False
            return True
        for table in soup.find_all("table"):
            context_texts = []
            cur = table
            for _ in range(12):
                prev = cur.find_previous(string=True)
                if not prev:
                    break
                txt = normalize_key(prev if isinstance(prev, str) else prev.get_text(" ", strip=True))
                if txt:
                    context_texts.append(txt)
                cur = prev.parent if hasattr(prev, "parent") else None
                if not cur:
                    break
            context_blob = " ".join(context_texts)
            if heading_matches(context_blob):
                matches.append(table)
        # Fallback: detect by header row keywords if context scan found nothing
        if not matches:
            key_sets = [
                {"issuer","investment","fair","value"},
                {"issuer","principal","amortized","cost"},
                {"investment type","maturity","date","principal"},
                {"portfolio company","type of investment","outstanding principal","fair value"}
            ]
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                if not rows:
                    continue
                # take first 1-3 rows as potential header block
                header_blob = " ".join(normalize_key(x.get_text(" ", strip=True)) for x in rows[:3])
                for keys in key_sets:
                    if all(k in header_blob for k in keys):
                        matches.append(table)
                        break
        return matches

    def table_to_rows(table: BeautifulSoup) -> List[List[str]]:
        rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            vals: List[str] = []
            for c in cells:
                txt = c.get_text(" ", strip=True)
                txt = txt.replace("\u200b", "").replace("\xa0", " ")
                vals.append(normalize_text(txt))
            rows.append(vals)
        return rows

    def compact_row(cells: List[str]) -> List[str]:
        filtered = [x for x in cells if x not in ("", "-")]
        merged: List[str] = []
        i = 0
        while i < len(filtered):
            cur = filtered[i]
            nxt = filtered[i+1] if i+1 < len(filtered) else None
            if cur == "$" and nxt and re.match(r"^\d[\d,\.]*$", nxt):
                merged.append(f"${nxt}")
                i += 2
                continue
            if re.match(r"^\d[\d,\.]*$", cur) and nxt == "%":
                merged.append(f"{cur}%")
                i += 2
                continue
            merged.append(cur)
            i += 1
        return merged

    def find_header_map(rows: List[List[str]]) -> Optional[Dict[str,int]]:
        for r in rows[:12]:
            header_cells = compact_row(r)
            keys = [normalize_key(c) for c in header_cells]
            def find_idx(patterns: List[str]) -> Optional[int]:
                for i,k in enumerate(keys):
                    if any(p in k for p in patterns):
                        return i
                return None
            idx_company = find_idx(["issuer","company","portfolio company"]) 
            idx_type = find_idx(["investment type","type of investment","security type","class"]) 
            idx_floor = find_idx(["floor"]) 
            idx_ref = find_idx(["reference rate"]) 
            idx_spread = find_idx(["spread above index","spread"]) 
            idx_rate = find_idx(["interest rate"]) 
            idx_acq = find_idx(["acquisition date"]) 
            idx_mat = find_idx(["maturity date"]) 
            idx_prin = find_idx(["outstanding principal","principal","share amount","principal/share amount"]) 
            idx_cost = find_idx(["amortized cost","cost"]) 
            idx_fv = find_idx(["fair value"]) 
            idx_pct = find_idx(["percentage of net assets","% of net assets","as a percentage of net assets"]) 
            if idx_company is not None and idx_type is not None and idx_prin is not None and idx_fv is not None:
                return {"company":idx_company,"type":idx_type,"floor":-1 if idx_floor is None else idx_floor,"ref":-1 if idx_ref is None else idx_ref,"spread":-1 if idx_spread is None else idx_spread,"rate":-1 if idx_rate is None else idx_rate,"acq":-1 if idx_acq is None else idx_acq,"mat":-1 if idx_mat is None else idx_mat,"prin":idx_prin,"cost":-1 if idx_cost is None else idx_cost,"fv":idx_fv,"pct":-1 if idx_pct is None else idx_pct}
        return None

    def parse_section_tables(tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
        records: List[Dict[str, Optional[str]]] = []

        def has_percent(tokens: List[str]) -> bool:
            return any(re.search(r"\d(\.\d+)?%$", t) or " % " in f" {t} " or "cash /" in t.lower() or "pik" in t.lower() for t in tokens)
        def has_spread_token(tokens: List[str]) -> bool:
            return any(t.upper().startswith(("SOFR+","PRIME+","LIBOR+","BASE RATE+","SOFR","PRIME","LIBOR","BASE RATE")) for t in tokens)
        def has_date(tokens: List[str]) -> bool:
            return any(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", t) for t in tokens)
        def is_section_header(text: str) -> bool:
            t = text.lower(); return any(k in t for k in ["investments","non-control","non-affiliate"]) 

        for table in tables:
            rows = table_to_rows(table)
            if not rows: continue
            header_map = find_header_map(rows) or {}
            last_company: Optional[str] = None; last_industry: Optional[str] = None
            for r in rows:
                row = compact_row(r)
                if not row: continue
                row_l = " ".join(normalize_key(c) for c in row)
                if all(tok in row_l for tok in ["issuer","investment","fair","value"]) and ("acquisition" in row_l or "maturity" in row_l):
                    continue
                first = row[0]
                if is_section_header(first): continue
                detail_signals = has_percent(row) or has_spread_token(row) or has_date(row)
                first_l = normalize_key(first)
                # If the first cell looks like an instrument type, force detail
                if any(k in first_l for k in ["loan","revolver","convertible","warrant","equity","note"]):
                    detail_signals = True
                # If the first cell looks like a company name (e.g., contains LLC/Inc/Ltd/Corp or a comma)
                # and does NOT look like an instrument label, treat as a company row even if dates are present
                nameish = ("," in first) or bool(re.search(r"\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|holdings|group|s\.à\s*r\.l\.|limited|plc)\b", first, re.IGNORECASE))
                if nameish and not any(k in first_l for k in ["loan","revolver","convertible","warrant","equity","note"]):
                    detail_signals = False
                if first and not detail_signals:
                    non_empty_others = [c for c in row[1:] if c and c not in ("$","%")]
                    if not non_empty_others:
                        last_industry = first.strip()
                    else:
                        last_company = first.strip()
                        cand_ind = None
                        for cell in row[1:]:
                            if not cell:
                                continue
                            txt = cell.strip()
                            # Reject pure numbers/currency tokens for industry
                            if re.match(r"^\$?\d[\d,]*$", txt):
                                continue
                            if has_percent([txt]) or has_date([txt]) or has_spread_token([txt]):
                                continue
                            # Prefer tokens containing letters
                            if re.search(r"[A-Za-z]", txt):
                                cand_ind = txt; break
                        if cand_ind: last_industry = cand_ind
                    continue

                inv_type = first.strip(); interest_rate = next((c for c in row if re.search(r"\d(\.\d+)?%", c)), None)
                spread_val = None
                for i,c in enumerate(row):
                    cu = c.upper()
                    if any(cu.startswith(tok) for tok in ["SOFR+","PRIME+","LIBOR+","BASE RATE+"]):
                        if i+1 < len(row):
                            nxt=row[i+1]; spread_val = nxt if nxt.endswith('%') else (nxt+'%' if re.match(r"^\d+(\.\d+)?$", nxt) else nxt); break
                ref_token = None
                if header_map:
                    def get(idx: int) -> Optional[str]: return row[idx] if 0<=idx<len(row) else None
                    company_cell=get(header_map.get('company',-1)); it_cell=get(header_map.get('type',-1)); ref_cell=get(header_map.get('ref',-1))
                    rate_cell=get(header_map.get('rate',-1)); spread_cell=get(header_map.get('spread',-1)); acq_cell=get(header_map.get('acq',-1)); mat_cell=get(header_map.get('mat',-1))
                    prin_cell=get(header_map.get('prin',-1)); cost_cell=get(header_map.get('cost',-1)); fv_cell=get(header_map.get('fv',-1)); pct_cell=get(header_map.get('pct',-1))
                    # Skip subtotal/total rows
                    if company_cell and normalize_key(company_cell).startswith('total '):
                        continue
                    # Validate and assign with guards (avoid date/money bleeding into wrong columns)
                    if it_cell and re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", it_cell):
                        # this is actually a date sitting where type would be; ignore
                        pass
                    elif it_cell:
                        inv_type = it_cell
                    if rate_cell and re.search(r"%", rate_cell):
                        interest_rate = rate_cell
                    if spread_cell and re.search(r"%", spread_cell):
                        spread_val = spread_cell
                    if ref_cell:
                        ref_token = ref_cell
                    acq = acq_cell if (acq_cell and re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", acq_cell)) else None
                    mat = mat_cell if (mat_cell and re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", mat_cell)) else None
                    # Validate company cell; if it doesn't look like a name, ignore and keep last_company
                    nameish_cc = bool(company_cell) and ("," in company_cell or re.search(r"\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|holdings|group|s\.à\s*r\.l\.|limited|plc)\b", company_cell, re.IGNORECASE))
                    is_instrument_cc = bool(company_cell) and any(k in normalize_key(company_cell) for k in ["loan","revolver","convertible","warrant","equity","note"]) 
                    if nameish_cc and not is_instrument_cc:
                        last_company = company_cell
                        company_for_row = company_cell
                    else:
                        company_for_row = last_company or ""
                    money = [prin_cell, cost_cell, fv_cell]
                else:
                    company_for_row = last_company or ""
                    dates=[c for c in row if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", c)]
                    acq = dates[0] if dates else None; mat = dates[1] if len(dates)>1 else None
                    money=[c for c in row if c.startswith('$') or re.match(r"^\$?\d[\d,]*$", c)]
                    for tok in row:
                        m=re.match(r"^(SOFR|SONIA|PRIME|LIBOR|BASE RATE|EURIBOR)(?:\s*\([^)]*\))?$", tok, re.IGNORECASE)
                        if m: ref_token=tok; break

                def parse_terms_from_type(type_text: str) -> Dict[str, Optional[str]]:
                    res = {"ref": None, "spread": None, "floor": None, "pik": None, "eot": None, "fixed": None}
                    t = type_text or ""
                    # Reference rate tokens embedded in type
                    m = re.search(r"\b(SOFR(?:\s*\([^)]*\))?|PRIME|LIBOR|EURIBOR|BASE\s*RATE)\b", t, re.IGNORECASE)
                    if m: res["ref"] = m.group(1)
                    # Spread (Prime + X% interest rate)
                    m = re.search(r"(?:Prime|SOFR|LIBOR|EURIBOR|Base\s*Rate)\s*\+\s*([\d\.]+)\s*%\s*(?:cash\s+)?interest\s*rate", t, re.IGNORECASE)
                    if m: res["spread"] = f"{m.group(1)}%"
                    # Fixed interest rate (11.75% interest rate)
                    m = re.search(r"([\d\.]+)\s*%\s*interest\s*rate", t, re.IGNORECASE)
                    if m: res["fixed"] = f"{m.group(1)}%"
                    # PIK interest
                    m = re.search(r"([\d\.]+)\s*%\s*PIK\s*interest", t, re.IGNORECASE)
                    if m: res["pik"] = f"{m.group(1)}%"
                    # Floor
                    m = re.search(r"([\d\.]+)\s*%\s*floor", t, re.IGNORECASE)
                    if m: res["floor"] = f"{m.group(1)}%"
                    # EOT payment
                    m = re.search(r"([\d\.]+)\s*%\s*EOT\s*payment", t, re.IGNORECASE)
                    if m: res["eot"] = f"{m.group(1)}%"
                    return res

                # Derive missing rate details from the investment_type text
                if inv_type:
                    terms = parse_terms_from_type(inv_type)
                    if not ref_token and terms["ref"]: ref_token = terms["ref"]
                    if not spread_val and terms["spread"]: spread_val = terms["spread"]
                    # Prefer explicit interest_rate column; otherwise use fixed rate parsed from type
                    if not interest_rate and terms["fixed"]: interest_rate = terms["fixed"]
                    floor_rate_val = terms["floor"]
                    pik_rate_val = terms["pik"]
                    eot_val = terms["eot"]
                else:
                    floor_rate_val = None; pik_rate_val = None; eot_val = None

                def parse_number_local(text: Optional[str]) -> Optional[float]:
                    if not text: return None
                    t=text.replace("\xa0"," ").replace(",","" ).strip().replace('$','')
                    if t in ("—","—%","— $"): return None
                    if t.endswith('%'):
                        try: return float(t[:-1])
                        except: return None
                    try: return float(t)
                    except: return None

                principal = parse_number_local(money[0]) if len(money)>=1 else None
                cost = parse_number_local(money[1]) if len(money)>=2 else None
                fair_value = parse_number_local(money[2]) if len(money)>=3 else None
                pct_nav = None
                if header_map and header_map.get('pct',-1) >= 0:
                    pct_cell_val = row[header_map['pct']] if header_map['pct'] < len(row) else None
                    if pct_cell_val:
                        pct_nav = parse_number_local(pct_cell_val if not pct_cell_val.endswith('%') else pct_cell_val)
                else:
                    percent_tokens=[c for c in row if c.endswith('%')]
                    if percent_tokens:
                        try: pct_nav = float(percent_tokens[-1].rstrip('%'))
                        except: pct_nav=None

                # If after mapping company still missing, treat as continuation of previous company
                company_clean = strip_footnote_refs(company_for_row or last_company or "")
                # Final safeguards: if company looks like an instrument label, a date, or a number, use last_company
                if (not company_clean) or re.search(r"\b(loan|revolver|convertible|warrant|equity|note)\b", normalize_key(company_clean)) or re.match(r"^(\$?\d[\d,]*|\d{1,2}/\d{1,2}/\d{2,4})$", company_clean):
                    if last_company:
                        company_clean = last_company
                # Normalize investment type to a base label (strip detail parentheticals)
                base_type = normalize_key(inv_type or "")
                if 'revolver' in base_type:
                    inv_type_norm = 'Revolver'
                elif 'convertible' in base_type:
                    inv_type_norm = 'Convertible Note'
                elif 'warrant' in base_type:
                    inv_type_norm = 'Warrants'
                elif 'equity' in base_type and 'preferred' in base_type:
                    inv_type_norm = 'Preferred Equity'
                elif 'equity' in base_type or 'common stock' in base_type:
                    inv_type_norm = 'Equity'
                elif 'growth capital loan' in base_type:
                    inv_type_norm = 'Growth Capital Loan'
                else:
                    # default to first token before '(' as readable label
                    inv_type_norm = (inv_type or '').split('(')[0].strip() or (inv_type or '')
                inv_type_clean = strip_footnote_refs(inv_type_norm)
                # Ensure industry looks textual; otherwise keep previous valid industry
                candidate_industry = (last_industry or "").strip()
                if not candidate_industry or re.match(r"^\$?\d[\d,]*$", candidate_industry):
                    industry_clean = ""
                else:
                    industry_clean = strip_footnote_refs(candidate_industry)
                # Drop rows that are header/subtotal artifacts (no money, no dates, and company empty)
                has_money = any([principal, cost, fair_value])
                has_dates = bool(acq or mat)
                if not company_clean and not has_money and not has_dates:
                    continue
                records.append({
                    'company_name': company_clean,
                    'investment_type': inv_type_clean,
                    'industry': industry_clean,
                    'interest_rate': interest_rate,
                    'reference_rate': ref_token,
                    'spread': spread_val,
                    'acquisition_date': acq,
                    'maturity_date': mat,
                    'principal_amount': principal,
                    'amortized_cost': cost,
                    'fair_value': fair_value,
                    'floor_rate': floor_rate_val,
                    'pik_rate': pik_rate_val,
                    'eot_payment': eot_val,
                    'percent_of_net_assets': pct_nav,
                })
        # Post-pass: fix continuation rows whose company_name ended up numeric/date/instrument tokens
        last_good_company: Optional[str] = None
        for r in records:
            name = (r.get('company_name') or '').strip()
            name_l = normalize_key(name)
            is_bad = (
                (not name) or
                bool(re.match(r'^\$?\d[\d,]*$', name)) or
                bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', name)) or
                any(k in name_l for k in ['loan','revolver','convertible','warrant','equity','note'])
            )
            if is_bad and last_good_company:
                r['company_name'] = last_good_company
            elif not is_bad:
                last_good_company = name

        # Post-pass 2: carry-forward industry and dates within the same company block when missing
        last_company: Optional[str] = None
        last_industry_by_company: Dict[str, str] = {}
        last_dates_by_company: Dict[str, Dict[str, Optional[str]]] = {}
        for r in records:
            cname = r.get('company_name') or ''
            if cname:
                last_company = cname
            if not last_company:
                continue
            # Industry carry-forward
            ind = (r.get('industry') or '').strip()
            if ind:
                last_industry_by_company[last_company] = ind
            elif last_company in last_industry_by_company:
                r['industry'] = last_industry_by_company[last_company]
            # Dates carry-forward only if missing and previous for the same company exist
            acq = r.get('acquisition_date') or ''
            mat = r.get('maturity_date') or ''
            if acq or mat:
                last_dates_by_company[last_company] = {'acq': acq or last_dates_by_company.get(last_company,{}).get('acq'), 'mat': mat or last_dates_by_company.get(last_company,{}).get('mat')}
            else:
                prev = last_dates_by_company.get(last_company)
                if prev:
                    if not acq and prev.get('acq'):
                        r['acquisition_date'] = prev.get('acq')
                    if not mat and prev.get('mat'):
                        r['maturity_date'] = prev.get('mat')
        
        # Deduplicate records based on company + type + principal + cost + fair_value
        seen = set()
        deduped_records = []
        for r in records:
            # Create a key for deduplication
            company = (r.get('company_name') or '').strip()
            inv_type = (r.get('investment_type') or '').strip()
            principal = r.get('principal_amount')
            cost = r.get('amortized_cost')
            fair_value = r.get('fair_value')
            
            # Convert None to 0 for comparison, but keep original None values
            key = (
                company.lower(),
                inv_type.lower(),
                principal if principal is not None else 0,
                cost if cost is not None else 0,
                fair_value if fair_value is not None else 0
            )
            
            if key not in seen:
                seen.add(key)
                deduped_records.append(r)
            # Skip if we've seen this exact combination before
        
        return deduped_records

    client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
    index_url = client.get_filing_index_url("TPVG", "10-Q")
    if not index_url:
        print("Could not find latest 10-Q for TPVG"); return
    docs = client.get_documents_from_index(index_url)
    htm_docs = [d for d in docs if d.filename.lower().endswith('.htm')]
    all_records: List[Dict[str, Optional[str]]] = []
    tables: List[BeautifulSoup] = []
    for doc in htm_docs:
        try:
            resp = requests.get(doc.url, headers=client.headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            cand_tables = extract_tables_under_heading(soup)
            cand_records = parse_section_tables(cand_tables)
            if cand_records:
                all_records.extend(cand_records)
                tables.extend(cand_tables)
        except Exception:
            continue
    
    # Deduplicate across all records from all documents/tables
    # Use company + type + principal + dates as key (ignore cost/fair_value which may vary)
    seen = set()
    records = []
    for r in all_records:
        company = (r.get('company_name') or '').strip()
        inv_type = (r.get('investment_type') or '').strip()
        principal = r.get('principal_amount')
        acq_date = (r.get('acquisition_date') or '').strip()
        mat_date = (r.get('maturity_date') or '').strip()
        
        # Create deduplication key: company + type + principal + dates
        # This catches duplicates from different tables even if cost/fair_value differ slightly
        key = (
            company.lower(),
            inv_type.lower(),
            principal if principal is not None else 0,
            acq_date.lower(),
            mat_date.lower()
        )
        
        if key not in seen:
            seen.add(key)
            records.append(r)
        else:
            # If we've seen this key, keep the one with more complete data (non-null cost/fair_value)
            existing_idx = next(i for i, rec in enumerate(records) if 
                (rec.get('company_name') or '').strip().lower() == company.lower() and
                (rec.get('investment_type') or '').strip().lower() == inv_type.lower() and
                rec.get('principal_amount') == principal and
                (rec.get('acquisition_date') or '').strip().lower() == acq_date.lower() and
                (rec.get('maturity_date') or '').strip().lower() == mat_date.lower())
            existing = records[existing_idx]
            # Prefer record with non-null cost or fair_value
            if (r.get('amortized_cost') is not None or r.get('fair_value') is not None) and \
               existing.get('amortized_cost') is None and existing.get('fair_value') is None:
                records[existing_idx] = r
    
    if not records:
        print("No schedule tables found in filing HTMLs for TPVG")
        # still write empty CSV/tables dirs for consistency

    out_dir = os.path.join(os.path.dirname(__file__), 'output'); os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, 'TPVG_Schedule_Continued_latest.csv')
    fieldnames = ['company_name','investment_type','industry','interest_rate','reference_rate','spread','acquisition_date','maturity_date','principal_amount','amortized_cost','fair_value','floor_rate','pik_rate','eot_payment','percent_of_net_assets']
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            # Apply standardization
            if 'investment_type' in r:
                r['investment_type'] = standardize_investment_type(r.get('investment_type'))
            if 'industry' in r:
                r['industry'] = standardize_industry(r.get('industry'))
            if 'reference_rate' in r:
                r['reference_rate'] = standardize_reference_rate(r.get('reference_rate')) or ''
            w.writerow(r)
    print(f"Saved {len(records)} rows to {out_csv}")

    tables_dir = os.path.join(out_dir, 'tpvg_tables'); os.makedirs(tables_dir, exist_ok=True)
    for i,t in enumerate(tables,1):
        simple = BeautifulSoup(str(t), 'html.parser').find('table')
        if not simple: continue
        for ix in simple.find_all(lambda el: isinstance(el.name,str) and el.name.lower().startswith('ix:')):
            ix.replace_with(ix.get_text(' ', strip=True))
        def strip_attrs(el):
            if hasattr(el,'attrs'): el.attrs = {}
            for child in getattr(el,'children',[]): strip_attrs(child)
        strip_attrs(simple)
        with open(os.path.join(tables_dir, f'tpvg_table_{i}.html'), 'w', encoding='utf-8') as fh:
            fh.write(str(simple))
    print(f"Saved {len(tables)} simplified tables to {tables_dir}")

if __name__=='__main__':
    main()



    def normalize_key(text: str) -> str:
        return normalize_text(text).lower()

    def strip_footnote_refs(text: Optional[str]) -> str:
        if not text:
            return ""
