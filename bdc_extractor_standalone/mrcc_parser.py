#!/usr/bin/env python3
import re, os, csv, logging, requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class MRCCInvestment:
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


class MRCCExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "MRCC") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        # Prefer HTML main document first
        documents = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm')), None)
        if main_html:
            logger.info(f"Found main HTML: {main_html.url}")
            return self.extract_from_html_url(main_html.url, "Monroe Capital Corp", cik)
        # Fallback to XBRL text
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        return self.extract_from_url(txt_url, "Monroe_Capital_Corp", cik)

    def extract_from_html_url(self, html_url: str, company_name: str, cik: str) -> Dict:
        logger.info(f"Downloading HTML from: {html_url}")
        resp = requests.get(html_url, headers=self.headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        logger.info("Downloaded and parsed HTML")

        tables = self._find_schedule_tables(soup)
        logger.info(f"Found {len(tables)} schedule tables")
        if not tables:
            logger.warning("No schedule tables found, falling back to XBRL")
            return self._fallback_to_xbrl(html_url, company_name, cik)

        self._save_simplified_tables(tables, cik)
        investments = self._parse_html_tables(tables)
        logger.info(f"Built {len(investments)} investments from HTML")

        if not investments:
            logger.warning("HTML parsing yielded 0 investments; falling back to XBRL")
            return self._fallback_to_xbrl(html_url, company_name, cik)

        # de-dup similar to XBRL path
        ded, seen = [], set()
        for x in investments:
            key = (x.company_name, x.investment_type, x.maturity_date or '')
            val = (x.principal_amount or 0.0, x.cost or 0.0, x.fair_value or 0.0)
            combo = (key, val)
            if combo in seen: continue
            seen.add(combo); ded.append(x)
        investments = ded

        total_principal = sum(x.principal_amount or 0 for x in investments)
        total_cost = sum(x.cost or 0 for x in investments)
        total_fair_value = sum(x.fair_value or 0 for x in investments)
        ind = defaultdict(int); ty = defaultdict(int)
        for x in investments:
            ind[x.industry] += 1; ty[x.investment_type] += 1

        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'MRCC_Monroe_Capital_Corp_investments.csv')
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['company_name','industry','business_description','investment_type','acquisition_date','maturity_date','principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'])
            w.writeheader()
            for x in investments:
                w.writerow({
                    'company_name': x.company_name,
                    'industry': standardize_industry(x.industry),
                    'business_description': x.business_description,
                    'investment_type': standardize_investment_type(x.investment_type),
                    'acquisition_date': x.acquisition_date,
                    'maturity_date': x.maturity_date,
                    'principal_amount': x.principal_amount,
                    'cost': x.cost,
                    'fair_value': x.fair_value,
                    'interest_rate': x.interest_rate,
                    'reference_rate': standardize_reference_rate(x.reference_rate),
                    'spread': x.spread,
                    'floor_rate': x.floor_rate,
                    'pik_rate': x.pik_rate,
                })
        logger.info(f"Saved to {out_file}")
        # Convert investments to dict format
        investment_dicts = []
        for x in investments:
            investment_dicts.append({
                'company_name': x.company_name,
                'industry': standardize_industry(x.industry),
                'business_description': x.business_description,
                'investment_type': standardize_investment_type(x.investment_type),
                'acquisition_date': x.acquisition_date,
                'maturity_date': x.maturity_date,
                'principal_amount': x.principal_amount,
                'cost': x.cost,
                'fair_value': x.fair_value,
                'interest_rate': x.interest_rate,
                'reference_rate': standardize_reference_rate(x.reference_rate),
                'spread': x.spread,
                'floor_rate': x.floor_rate,
                'pik_rate': x.pik_rate,
                'shares_units': x.shares_units,
                'percent_net_assets': x.percent_net_assets,
                'currency': x.currency,
                'commitment_limit': x.commitment_limit,
                'undrawn_commitment': x.undrawn_commitment,
            })
        return {'company_name':company_name,'cik':cik,'total_investments':len(investments),'investments':investment_dicts,'total_principal':total_principal,'total_cost':total_cost,'total_fair_value':total_fair_value,'industry_breakdown':dict(ind),'investment_type_breakdown':dict(ty)}

    def _fallback_to_xbrl(self, html_url: str, company_name: str, cik: str) -> Dict:
        m = re.search(r'/(\d{10}-\d{2}-\d{6})\.htm', html_url)
        if not m:
            m2 = re.search(r'/(\d{10})(\d{2})(\d{6})', html_url)
            if m2:
                accession = f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
            else:
                raise ValueError(f"Could not parse accession number from {html_url}")
        else:
            accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        logger.info(f"Falling back to XBRL: {txt_url}")
        return self.extract_from_url(txt_url, company_name, cik)

    def _normalize_text(self, s: str) -> str:
        return ' '.join((s or '').split())

    def _find_schedule_tables(self, soup: BeautifulSoup) -> List[BeautifulSoup]:
        tables = []
        all_tables = soup.find_all('table')
        required_all = ["schedule", "investment"]
        required_any = ["monroe", "consolidated schedule"]
        for t in all_tables:
            prev_text = []
            for prev in t.find_all_previous(string=True, limit=12):
                txt = (prev or '').strip()
                if txt:
                    prev_text.append(txt.lower())
            blob = ' '.join(prev_text)
            if all(k in blob for k in required_all) or any(k in blob for k in required_any):
                tables.append(t)
        if not tables:
            logger.warning("No schedule-heading matches found; returning first 30 tables for QA")
            return all_tables[:30]
        return tables

    def _table_to_rows(self, table: BeautifulSoup) -> List[List[str]]:
        rows = []
        for tr in table.find_all('tr'):
            cells = tr.find_all(['td','th'])
            if not cells:
                continue
            vals = [ self._normalize_text(c.get_text(' ', strip=True)) for c in cells ]
            rows.append(vals)
        return rows

    def _simplify_table(self, table: BeautifulSoup) -> str:
        simple = BeautifulSoup(str(table), 'html.parser').find('table')
        if not simple:
            return '<table></table>'
        for ix in simple.find_all(lambda t: isinstance(t.name, str) and t.name.lower().startswith('ix:')):
            ix.replace_with(ix.get_text(' ', strip=True))
        def strip_attrs(el):
            if hasattr(el, 'attrs'):
                el.attrs = {}
            for ch in getattr(el, 'children', []):
                strip_attrs(ch)
        strip_attrs(simple)
        for tag_name in ['span','div','b','strong','i','em','u']:
            for t in simple.find_all(tag_name):
                t.unwrap()
        allowed = { 'table','thead','tbody','tr','th','td' }
        for tag in list(simple.find_all(True)):
            if tag.name not in allowed:
                tag.unwrap()
        return str(simple)

    def _save_simplified_tables(self, tables: List[BeautifulSoup], cik: str):
        out_dir = os.path.join('output', 'mrcc_tables')
        os.makedirs(out_dir, exist_ok=True)
        for i, t in enumerate(tables, 1):
            html = self._simplify_table(t)
            with open(os.path.join(out_dir, f'mrcc_table_{i}.html'), 'w', encoding='utf-8') as f:
                f.write(html)
        logger.info(f"Saved {len(tables)} simplified tables to {out_dir}")

    def _parse_html_tables(self, tables: List[BeautifulSoup]) -> List[MRCCInvestment]:
        investments: List[MRCCInvestment] = []
        def to_float(s: Optional[str]) -> Optional[float]:
            if not s: return None
            t = s.replace('\xa0',' ').replace(',','').replace('$','').strip()
            if t in ('—','-',''): return None
            try:
                return float(t)
            except: return None
        def find_value(row: List[str], idx: Optional[int], max_ahead: int = 8) -> Optional[str]:
            if idx is None: return None
            for i in range(idx, min(idx+max_ahead, len(row))):
                v = row[i].strip()
                if v and v not in ('—','-',''):
                    return v
            return None
        def find_amount(row: List[str], idx: Optional[int]) -> Optional[float]:
            if idx is None: return None
            for i in range(idx, min(idx+10, len(row))):
                v = to_float(row[i])
                if v is not None and v >= 100:  # skip percents
                    return v
            return None
        def parse_date(s: str) -> Optional[str]:
            if not s: return None
            m1 = re.search(r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})', s)
            if m1:
                mon = {'january':'01','february':'02','march':'03','april':'04','may':'05','june':'06','july':'07','august':'08','september':'09','october':'10','november':'11','december':'12'}.get(m1.group(1).lower())
                if mon: return f"{m1.group(3)}-{mon}-{m1.group(2).zfill(2)}"
            m2 = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
            if m2:
                return f"{m2.group(3)}-{m2.group(1).zfill(2)}-{m2.group(2).zfill(2)}"
            return None

        last_company = None
        last_industry = None
        for table in tables:
            rows = self._table_to_rows(table)
            if not rows: continue
            col = {}; in_body = False
            for r in rows:
                if not in_body:
                    header = ' '.join(r).lower()
                    if ('portfolio company' in header or 'company' in header) and ('investment' in header or 'type' in header or 'fair value' in header):
                        for i, cell in enumerate(r):
                            c = cell.lower()
                            if 'portfolio company' in c or ('company' in c and 'business' not in c): col['company']=i
                            elif 'business description' in c: col['business']=i
                            elif 'industry' in c or 'sector' in c: col['sector']=i
                            elif 'type of investment' in c or ('investment' in c and 'type' in c): col['type']=i
                            elif 'total rate' in c or 'interest rate' in c: col['rate']=i
                            elif 'reference rate' in c or 'index' in c: col['index']=i
                            elif 'margin' in c or 'spread' in c: col['margin']=i
                            elif 'pik' in c: col['pik']=i
                            elif 'maturity' in c: col['maturity']=i
                            elif 'principal' in c: col['principal']=i
                            elif 'cost' in c: col['cost']=i
                            elif 'fair value' in c: col['value']=i
                        in_body = True
                        continue
                    else:
                        continue
                # data rows
                first = r[0].strip() if r else ''
                if not first and last_company:
                    company = last_company; industry = last_industry
                else:
                    company = re.sub(r'\s*\(\d+\)(?:\(\d+\))*\s*','', first).strip()
                    low = company.lower()
                    if not company or any(tok in low for tok in ['non-affiliate','affiliate','total','warrants','investments','—']):
                        continue
                    last_company = company
                    si = col.get('sector')
                    industry = find_value(r, si) or last_industry or 'Unknown'
                    last_industry = industry

                inv_type = find_value(r, col.get('type')) or 'Unknown'
                business = find_value(r, col.get('business'))

                interest_rate = None; reference_rate=None; spread=None; floor_rate=None; pik_rate=None
                acquisition_date=None; maturity_date=None
                principal=None; cost=None; value=None

                # rates
                ri = col.get('rate')
                rv = find_value(r, ri+1 if ri is not None else None)
                if rv:
                    if ri is not None and ri+2 < len(r) and r[ri+2].strip()=='%':
                        interest_rate = f"{rv}%"
                    elif '%' in rv:
                        interest_rate = rv
                ii = col.get('index')
                if ii is not None:
                    idx = find_value(r, ii)
                    if idx:
                        up = idx.upper().replace('SF+','SOFR').replace('SF','SOFR')
                        if '+' in up:
                            parts = up.split('+'); reference_rate = parts[0].strip()
                            sp = parts[1].strip()
                            spread = f"{sp}%" if sp and not sp.endswith('%') else sp
                        else:
                            reference_rate = up
                mi = col.get('margin')
                if mi is not None and not spread:
                    marg = find_value(r, mi)
                    if marg:
                        if mi+1 < len(r) and r[mi+1].strip()=='%': spread = f"{marg}%"
                        elif '%' in marg: spread = marg
                pi = col.get('pik')
                if pi is not None:
                    pv = find_value(r, pi)
                    if pv:
                        if pi+1 < len(r) and r[pi+1].strip()=='%': pik_rate = f"{pv}%"
                        elif '%' in pv: pik_rate = pv

                # dates
                mi2 = col.get('maturity')
                if mi2 is not None:
                    dm = find_value(r, mi2+1)
                    if dm: maturity_date = parse_date(dm)

                # amounts (likely in actual dollars for MRCC)
                principal = find_amount(r, col.get('principal'))
                cost = find_amount(r, col.get('cost'))
                value = find_amount(r, col.get('value'))

                if company and (principal or cost or value):
                    investments.append(MRCCInvestment(
                        company_name=company,
                        business_description=business,
                        investment_type=inv_type,
                        industry=industry,
                        acquisition_date=acquisition_date,
                        maturity_date=maturity_date,
                        principal_amount=principal,
                        cost=cost,
                        fair_value=value,
                        interest_rate=interest_rate,
                        reference_rate=reference_rate,
                        spread=spread,
                        floor_rate=floor_rate,
                        pik_rate=pik_rate,
                    ))
        return investments

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
        invs: List[MRCCInvestment] = []
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
        out_file = os.path.join(out_dir, 'MRCC_Monroe_Capital_Corp_investments.csv')
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
        investment_dicts = [{'company_name':x.company_name,'industry':standardize_industry(x.industry),'business_description':x.business_description,'investment_type':standardize_investment_type(x.investment_type),'acquisition_date':x.acquisition_date,'maturity_date':x.maturity_date,'principal_amount':x.principal_amount,'cost':x.cost,'fair_value':x.fair_value,'interest_rate':x.interest_rate,'reference_rate':standardize_reference_rate(x.reference_rate),'spread':x.spread,'floor_rate':x.floor_rate,'pik_rate':x.pik_rate} for x in invs]
        return {'company_name':company_name,'cik':cik,'total_investments':len(invs),'investments':investment_dicts,'total_principal':total_principal,'total_cost':total_cost,'total_fair_value':total_fair_value,'industry_breakdown':dict(ind),'investment_type_breakdown':dict(ty)}

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
        
        # MRCC format: "Company Name, Investment Type, Affiliation Status"
        # Example: "BTR Opco LLC (Delayed Draw), Senior Secured Loans, Non-Affiliated"
        # Or: "Lifted Trucks Holdings, LLC, Senior Secured Loans 1, Non-Affiliated"
        # Company name may contain commas (e.g., "Company Name, LLC")
        
        # Investment type keywords to identify where investment type starts
        investment_type_keywords = [
            'senior secured loans', 'senior secured', 'first lien', 'second lien',
            'revolver', 'revolving', 'term loan', 'delayed draw', 'secured debt',
            'unsecured debt', 'preferred equity', 'preferred stock', 'common stock',
            'common equity', 'warrants', 'member units', 'equity investments',
            'equity securities', 'junior secured'
        ]
        
        # Affiliation keywords (always at the end)
        affiliation_keywords = ['non-affiliated', 'affiliated', 'non-affiliate', 'affiliate']
        
        # Find where investment type starts by looking for keywords
        identifier_lower = identifier.lower()
        investment_type_start_idx = -1
        investment_type_keyword = None
        
        for keyword in investment_type_keywords:
            # Look for keyword after a comma (to avoid matching in company name)
            pattern = r',\s*([^,]*' + re.escape(keyword) + r'[^,]*)'
            match = re.search(pattern, identifier_lower)
            if match:
                # Find the position in the original string
                match_pos = identifier_lower.find(match.group(0))
                if investment_type_start_idx == -1 or match_pos < investment_type_start_idx:
                    investment_type_start_idx = match_pos
                    investment_type_keyword = keyword
        
        if investment_type_start_idx > 0:
            # Found investment type - split there
            company = identifier[:investment_type_start_idx].strip().rstrip(',')
            rest = identifier[investment_type_start_idx+1:].strip()
            
            # Check if there's affiliation at the end
            parts_after = [p.strip() for p in rest.split(',')]
            if len(parts_after) >= 2:
                # Last part is likely affiliation
                last_part = parts_after[-1].lower()
                if any(aff in last_part for aff in affiliation_keywords):
                    # Remove affiliation, rest is investment type
                    investment_type = ','.join(parts_after[:-1]).strip()
                else:
                    investment_type = rest
            else:
                investment_type = rest
        else:
            # No investment type keyword found - try to parse by commas
            parts = [p.strip() for p in identifier.split(',')]
            
            if len(parts) >= 3:
                # Likely: Company, Investment Type, Affiliation
                # But company might have comma, so check last part for affiliation
                last_part = parts[-1].lower()
                if any(aff in last_part for aff in affiliation_keywords):
                    # Last is affiliation, second-to-last might be investment type
                    # But company might have comma, so join first N-2 parts
                    company = ','.join(parts[:-2]).strip()
                    investment_type = parts[-2]
                else:
                    # No affiliation, join first N-1 parts as company
                    company = ','.join(parts[:-1]).strip()
                    investment_type = parts[-1]
            elif len(parts) == 2:
                # Could be: Company, Investment Type OR Company, Affiliation
                second = parts[1].lower()
                if any(aff in second for aff in affiliation_keywords):
                    # It's affiliation
                    company = parts[0]
                    investment_type = 'Unknown'
                else:
                    # Assume it's investment type
                    company = parts[0]
                    investment_type = parts[1]
            else:
                # Single part
                company = identifier.strip()
                investment_type = 'Unknown'
        
        # Clean company name - remove investment type patterns that might be embedded
        # But preserve company suffixes like LLC, Inc., etc.
        company_orig = company
        company = re.sub(r'\s*\([^)]*\)\s*$', '', company)  # Remove trailing parentheticals like "(Delayed Draw)"
        company = re.sub(r'\s*,\s*Senior\s+Secured\s+Loans.*$', '', company, flags=re.IGNORECASE)
        company = re.sub(r'\s*,\s*First\s+Lien.*$', '', company, flags=re.IGNORECASE)
        company = re.sub(r'\s*,\s*Second\s+Lien.*$', '', company, flags=re.IGNORECASE)
        company = re.sub(r'\s+', ' ', company).strip()
        
        # If we removed too much and company is now too short, use original
        if len(company) < 3 and len(company_orig) > len(company):
            company = company_orig
        
        # Clean investment type
        investment_type = re.sub(r'\s+\d+$', '', investment_type)  # Remove trailing numbers like "1", "2"
        investment_type = investment_type.strip()
        
        # Normalize investment type patterns
        inv_type_lower = investment_type.lower()
        if 'senior secured loans' in inv_type_lower or 'senior secured' in inv_type_lower:
            if 'first lien' in inv_type_lower:
                investment_type = 'First Lien Senior Secured Loans'
            elif 'second lien' in inv_type_lower:
                investment_type = 'Second Lien Senior Secured Loans'
            else:
                investment_type = 'Senior Secured Loans'
        elif 'first lien' in inv_type_lower:
            investment_type = 'First Lien Debt'
        elif 'second lien' in inv_type_lower:
            investment_type = 'Second Lien Debt'
        elif 'revolver' in inv_type_lower or 'revolving' in inv_type_lower:
            investment_type = 'Revolving Credit Facility'
        elif 'term loan' in inv_type_lower:
            investment_type = 'Term Loan'
        elif 'delayed draw' in inv_type_lower:
            investment_type = 'Delayed Draw Term Loan'
        elif 'common equity' in inv_type_lower or 'equity investments' in inv_type_lower:
            investment_type = 'Common Equity'
        elif 'preferred equity' in inv_type_lower or 'preferred stock' in inv_type_lower:
            investment_type = 'Preferred Equity'
        elif 'warrants' in inv_type_lower:
            investment_type = 'Warrants'
        elif inv_type_lower in ['llc', 'inc.', 'inc', 'corp.', 'corp', 'ltd.', 'ltd', 'lp', 'llp']:
            # This is a company suffix, not investment type
            investment_type = 'Unknown'
        
        res['company_name'] = company if company else 'Unknown'
        res['investment_type'] = investment_type if investment_type and investment_type != 'Unknown' else 'Unknown'
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[MRCCInvestment]:
        if context['company_name']=='Unknown': return None
        inv=MRCCInvestment(company_name=context['company_name'],investment_type=context['investment_type'],industry=context['industry'],context_ref=context['id'])
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
    ex=MRCCExtractor()
    try:
        res=ex.extract_from_ticker('MRCC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()
