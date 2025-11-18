#!/usr/bin/env python3
"""
GLAD (Gladstone Capital Corp) Investment Extractor
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
class GLADInvestment:
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


class GLADExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "GLAD", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        acc = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not acc:
            raise ValueError("Could not parse accession number")
        accession = acc.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Gladstone_Capital_Corp", cik)

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
        investments: List[GLADInvestment] = []
        for ctx in contexts:
            inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
            if inv:
                investments.append(inv)

        # HTML fallback for missing optional fields (acquisition_date, maturity_date, interest_rate)
        # Also add investments from HTML that aren't in XBRL
        html_data = self._extract_html_fallback(filing_url, investments)
        if html_data:
            self._merge_html_data(investments, html_data)
            # Add HTML investments that don't match any XBRL investments
            self._add_html_only_investments(investments, html_data)

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
        out_file = os.path.join(out_dir, 'GLAD_Gladstone_Capital_Corp_investments.csv')
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
        inv_dicts = [{'company_name':inv.company_name,'industry':standardize_industry(inv.industry),'business_description':inv.business_description,'investment_type':standardize_investment_type(inv.investment_type),'acquisition_date':inv.acquisition_date,'maturity_date':inv.maturity_date,'principal_amount':inv.principal_amount,'cost':inv.cost,'fair_value':inv.fair_value,'interest_rate':inv.interest_rate,'reference_rate':standardize_reference_rate(inv.reference_rate),'spread':inv.spread,'floor_rate':inv.floor_rate,'pik_rate':inv.pik_rate} for inv in investments]
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'investments': inv_dicts,
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
                'company_name': parsed['company_name'],
                'industry': same_ind or parsed['industry'],
                'investment_type': parsed['investment_type'],
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        
        # Decode HTML entities (like &#x2013; which is em dash)
        import html
        identifier = html.unescape(identifier)
        
        # Investment type patterns - search full identifier first
        type_patterns = [
            r'Term\s+Debt\s*\d*',
            r'Line\s+of\s+Credit',
            r'Convertible\s+Debt',
            r'Preferred\s+Stock',
            r'Common\s+Stock\s*\d*',
            r'First\s+Lien\s+Secured\s+.*',
            r'First\s+lien\s+.*',
            r'Second\s+Lien\s+Secured\s+.*',
            r'Second\s+lien\s+.*',
            r'Unitranche\s*\d*',
            r'Senior\s+secured\s+\d*',
            r'Secured\s+Debt\s*\d*',
            r'Unsecured\s+Debt\s*\d*',
            r'Preferred\s+Equity',
            r'Member\s+Units\s*\d*',
            r'Warrants?',
        ]
        
        # First, try to find investment type in the full identifier
        it = None
        it_match = None
        for p in type_patterns:
            mm = re.search(p, identifier, re.IGNORECASE)
            if mm:
                it = mm.group(0).strip()
                it_match = mm
                break
        
        # If found, extract company name by removing the investment type and separator
        if it and it_match:
            # Remove investment type and any separator (em dash, dash, etc.) before it
            company = identifier[:it_match.start()].strip()
            # Remove trailing separators (em dash, dash, etc.)
            company = re.sub(r'[\u2013\u2014\-–—]\s*$', '', company).strip()
            res['company_name'] = re.sub(r'\s+', ' ', company)
            res['investment_type'] = it
        else:
            # Fallback: split on last comma; tail is type
            if ',' in identifier:
                last = identifier.rfind(',')
                company = identifier[:last].strip()
                tail = identifier[last+1:].strip()
            else:
                company = identifier.strip()
                tail = ''
            res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
            if tail:
                res['investment_type'] = tail
        return res

    def _extract_facts(self, content: str) -> Dict[str, List[Dict]]:
        facts = defaultdict(list)
        # Extract standard XBRL facts and capture unitRef for currency
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept = match.group(1); cref = match.group(2); unit_ref = match.group(3); val = match.group(4)
            if val and cref:
                fact_entry = {'concept': concept, 'value': val.strip()}
                # Extract currency from unitRef if present
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
                # Extract currency from unitRef if present
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
            # Try multiple date patterns
            dates = []
            dates.extend(re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', window))
            dates.extend(re.findall(r'\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{1,2}/\d{4}\b', window))
            if dates:
                # Remove duplicates
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[GLADInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = GLADInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        for f in facts:
            c = f['concept']; v = f['value']; v_clean = v.replace(',','').strip(); cl=c.lower()
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
                inv.maturity_date = v.strip()
                continue
            # Acquisition date
            if 'acquisitiondate' in cl or 'investmentdate' in cl or cl=='derived:acquisitiondate':
                inv.acquisition_date = v.strip()
                continue
            # Interest rate (skip if URL)
            if 'interestrate' in cl and 'floor' not in cl:
                if v and not v.startswith('http'):
                    inv.interest_rate = self._percent(v_clean)
                continue
            # Reference rate (check BEFORE interest rate to avoid confusion)
            if cl=='derived:referenceratetoken' or 'variableinterestratetype' in cl or ('reference' in cl and 'rate' in cl):
                if 'sofr' in cl or 'sofr' in v.lower():
                    inv.reference_rate = 'SOFR'
                elif 'libor' in cl or 'libor' in v.lower():
                    inv.reference_rate = 'LIBOR'
                elif 'prime' in cl or 'prime' in v.lower():
                    inv.reference_rate = 'PRIME'
                elif v and not v.startswith('http'):
                    inv.reference_rate = v.upper().strip()
                continue
            # Spread
            if 'spread' in cl or ('basis' in cl and 'spread' in cl) or 'investmentbasisspreadvariablerate' in cl:
                inv.spread = self._percent(v_clean)
                continue
            # Floor rate
            if 'floor' in cl and 'rate' in cl or cl=='derived:floorrate':
                inv.floor_rate = self._percent(v_clean)
                continue
            # PIK rate
            if 'pik' in cl and 'rate' in cl or cl=='derived:pikrate':
                inv.pik_rate = self._percent(v_clean)
                continue
            # Extract shares/units for equity investments
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val = v.strip().replace(',', '')
                    float(shares_val)  # Validate
                    inv.shares_units = shares_val
                except: pass
                continue
            # Extract currency from fact metadata
            if 'currency' in f: inv.currency = f.get('currency')
        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        # Heuristic for commitment_limit and undrawn_commitment
        if inv.fair_value and not inv.principal_amount: inv.commitment_limit = inv.fair_value
        elif inv.fair_value and inv.principal_amount:
            if inv.fair_value > inv.principal_amount:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value - inv.principal_amount
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

    def _extract_html_fallback(self, filing_url: str, investments: List[GLADInvestment]) -> Optional[Dict[str, Dict]]:
        """Extract optional fields from HTML as fallback when XBRL doesn't have them."""
        try:
            from flexible_table_parser import FlexibleTableParser
            
            # Get HTML URL from index - construct index URL from .txt URL
            match = re.search(r'/edgar/data/(\d+)/(\d+)/([^/]+)\.txt', filing_url)
            if not match:
                logger.debug("Could not parse filing URL for HTML fallback")
                return None
            
            cik = match.group(1)
            accession_no_hyphens = match.group(2)
            filename_base = match.group(3).replace('.txt', '')
            # Construct index URL: replace the .txt filename with -index.html
            index_url = filing_url.replace(f"{filename_base}.txt", f"{filename_base}-index.html")
            
            # Get HTML document from index
            docs = self.sec_client.get_documents_from_index(index_url)
            main_doc = None
            for d in docs:
                fn = d.filename.lower() if d.filename else ''
                if fn.endswith('.htm') and 'index' not in fn:
                    main_doc = d
                    break
            
            if not main_doc:
                logger.debug(f"HTML fallback: No HTML document found in index")
                return None
            
            html_url = main_doc.url
            logger.info(f"HTML fallback: Using HTML URL: {html_url}")
            
            parser = FlexibleTableParser(user_agent=self.headers['User-Agent'])
            html_investments = parser.parse_html_filing(html_url)
            
            if not html_investments:
                logger.debug(f"HTML fallback: No investments extracted from {html_url}")
                return None
            
            logger.info(f"HTML fallback: Extracted {len(html_investments)} investments from HTML")
            
            # Initialize lookup dictionaries
            html_lookup_by_name = {}
            html_lookup_by_name_type = {}
            
            # Extract dates from company names and clean them for matching
            for html_inv in html_investments:
                company_name_raw = html_inv.get('company_name', '').strip()
                if not company_name_raw:
                    continue
                
                # Extract dates from company name (GLAD/GAIN format: "Company Name û term debt (..., due 2/2026)")
                if not html_inv.get('maturity_date'):
                    # Look for "due MM/YYYY" or "due MM/DD/YYYY" patterns
                    # Try multiple patterns to handle different formats
                    due_match = re.search(r'[Dd]ue\s+(\d{1,2})/(\d{4})', company_name_raw)
                    if not due_match:
                        due_match = re.search(r'[Dd]ue\s+(\d{1,2})/(\d{2})', company_name_raw)
                    if due_match:
                        month = due_match.group(1).zfill(2)
                        year_part = due_match.group(2)
                        if len(year_part) == 2:
                            # Assume 20XX for 2-digit years
                            year = f"20{year_part}"
                        else:
                            year = year_part
                        # Default to first day of month if only month/year
                        if len(due_match.group(2)) <= 2:
                            html_inv['maturity_date'] = f"{month}/01/{year}"
                        else:
                            day = due_match.group(2)[:2] if len(due_match.group(2)) > 2 else "01"
                            html_inv['maturity_date'] = f"{month}/{day}/{year}"
                
                # Clean company name: remove everything after "û" or similar separators
                # Pattern: "Company Name û term debt (...)" -> "Company Name"
                cleaned_name = re.sub(r'\s*[û–—\-]\s*.*$', '', company_name_raw, flags=re.IGNORECASE)
                cleaned_name = re.sub(r'\s*\(.*$', '', cleaned_name)  # Remove parenthetical notes
                cleaned_name = cleaned_name.strip()
                
                if cleaned_name:
                    company_name_lower = cleaned_name.lower()
                    investment_type = html_inv.get('investment_type', '').strip().lower()
                    
                    # Store cleaned name in the investment for matching
                    html_inv['_cleaned_company_name'] = cleaned_name
                    
                    # Primary lookup: by cleaned company name only
                    if company_name_lower not in html_lookup_by_name:
                        html_lookup_by_name[company_name_lower] = html_inv
                    
                    # Secondary lookup: by cleaned company name + investment type
                    key = (company_name_lower, investment_type)
                    html_lookup_by_name_type[key] = html_inv
            
            return {
                'by_name': html_lookup_by_name,
                'by_name_type': html_lookup_by_name_type,
                'all_investments': html_investments  # Store full list for adding unmatched investments
            }
        except Exception as e:
            logger.warning(f"HTML fallback extraction failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for better matching."""
        if not name:
            return ""
        name = name.lower().strip()
        # Remove separators and everything after (for HTML names with extra text)
        name = re.sub(r'\s*[û–—\-]\s*.*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(.*$', '', name)  # Remove parenthetical notes
        name = re.sub(r'\s*(inc\.?|incorporated|corp\.?|corporation|ltd\.?|limited|llc\.?|lp\.?|l\.p\.?|l\.l\.c\.?)\s*$', '', name)
        name = re.sub(r'\s*\([^)]*\)\s*', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        name = re.sub(r'^(the\s+)', '', name)
        return name
    
    def _fuzzy_match_company_names(self, name1: str, name2: str, threshold: float = 0.8) -> bool:
        """Check if two company names are similar enough to match."""
        from difflib import SequenceMatcher
        norm1 = self._normalize_company_name(name1)
        norm2 = self._normalize_company_name(name2)
        if not norm1 or not norm2:
            return False
        if norm1 == norm2:
            return True
        if norm1 in norm2 or norm2 in norm1:
            return True
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        return similarity >= threshold
    
    def _merge_html_data(self, investments: List[GLADInvestment], html_data: Dict[str, Dict]):
        """Merge HTML-extracted optional fields into XBRL investments."""
        html_by_name = html_data.get('by_name', {})
        html_by_name_type = html_data.get('by_name_type', {})
        
        # Create normalized lookup for fuzzy matching
        html_by_normalized = {}
        for html_inv in html_by_name.values():
            company_name = html_inv.get('company_name', '').strip()
            if company_name:
                normalized = self._normalize_company_name(company_name)
                if normalized and normalized not in html_by_normalized:
                    html_by_normalized[normalized] = html_inv
        
        merged_count = 0
        for inv in investments:
            company_name_lower = inv.company_name.strip().lower()
            investment_type_lower = inv.investment_type.strip().lower()
            
            html_inv = None
            
            # Strategy 1: Try exact match first (company_name + investment_type)
            key = (company_name_lower, investment_type_lower)
            html_inv = html_by_name_type.get(key)
            
            # Strategy 2: Fallback to company name only
            if not html_inv:
                html_inv = html_by_name.get(company_name_lower)
            
            # Strategy 3: Try normalized matching
            if not html_inv:
                normalized = self._normalize_company_name(inv.company_name)
                html_inv = html_by_normalized.get(normalized)
            
            # Strategy 4: Fuzzy matching (last resort)
            if not html_inv:
                for html_name, html_inv_candidate in html_by_name.items():
                    if self._fuzzy_match_company_names(inv.company_name, html_name, threshold=0.8):
                        html_inv = html_inv_candidate
                        break
            
            if html_inv:
                merged = False
                # Only fill in missing fields
                if not inv.acquisition_date and html_inv.get('acquisition_date'):
                    inv.acquisition_date = html_inv['acquisition_date']
                    merged = True
                if not inv.maturity_date and html_inv.get('maturity_date'):
                    inv.maturity_date = html_inv['maturity_date']
                    merged = True
                if not inv.interest_rate and html_inv.get('interest_rate'):
                    inv.interest_rate = html_inv['interest_rate']
                    merged = True
                if merged:
                    merged_count += 1
        
        if merged_count > 0:
            logger.info(f"HTML fallback: Merged data into {merged_count} investments")
    
    def _add_html_only_investments(self, investments: List[GLADInvestment], html_data: Dict[str, Dict]):
        """Add investments from HTML that don't match any XBRL investments."""
        html_by_name = html_data.get('by_name', {})
        html_by_name_type = html_data.get('by_name_type', {})
        html_all_investments = html_data.get('all_investments', [])
        
        # Track which HTML investments we've already matched
        matched_html_investments = set()
        
        # First pass: mark HTML investments that match XBRL
        for inv in investments:
            company_name_lower = inv.company_name.strip().lower()
            investment_type_lower = inv.investment_type.strip().lower()
            
            # Check by name+type
            key = (company_name_lower, investment_type_lower)
            if key in html_by_name_type:
                html_inv = html_by_name_type[key]
                matched_html_investments.add(id(html_inv))
            
            # Check by name only
            if company_name_lower in html_by_name:
                html_inv = html_by_name[company_name_lower]
                matched_html_investments.add(id(html_inv))
        
        # Second pass: add HTML investments that weren't matched
        added_count = 0
        for html_inv in html_all_investments:
            if id(html_inv) in matched_html_investments:
                continue
            
            # Create new investment from HTML
            company_name = html_inv.get('company_name', '').strip()
            if not company_name:
                continue
            
            # Filter out invalid rows
            company_name_lower = company_name.lower()
            
            # Skip industry headers and aggregate rows
            skip_patterns = [
                r'^total\s+',  # "Total Secured First Lien Debt", "Total Common Equity"
                r'^tOTAL\s+',  # "TOTAL INVESTMENTS"
                r'^non\s*[-/]',  # "NON-CONTROL/NON-AFFILIATE INVESTMENTS"
                r'^affiliate\s+investments',  # "AFFILIATE INVESTMENTS"
                r'^control\s+investments',  # "CONTROL INVESTMENTS"
                r'^company\s+and\s+investment',  # "Company and Investment"
                r'^secured\s+(first|second)\s+lien\s+debt',  # "Secured First Lien Debt"
                r'^unsecured\s+debt$',  # "Unsecured Debt"
                r'^preferred\s+equity$',  # "Preferred Equity" (aggregate)
                r'^common\s+equity$',  # "Common Equity" (aggregate)
                r'^first\s+lien\s+debt$',  # "First Lien Debt" (aggregate)
                r'^second\s+lien\s+debt$',  # "Second Lien Debt" (aggregate)
                r'^warrants?$',  # "Warrants" (aggregate)
                r'^limited\s+partnership\s+interest$',  # "Limited Partnership Interest" (aggregate)
                r'^convertible\s+debt$',  # "Convertible Debt" (aggregate)
            ]
            
            # Check if it's an industry header (common industry names)
            industry_names = [
                'beverage, food, and tobacco', 'buildings and real estate',
                'diversified/conglomerate manufacturing', 'diversified/conglomerate service',
                'automobile', 'machinery', 'oil and gas', 'pan', 'finance',
                'printing and publishing', 'cargo transportation',
                'healthcare, education, and childcare', 'aerospace and defense',
                'telecommunications', 'personal and non-durable consumer products'
            ]
            
            # Skip if matches skip patterns
            if any(re.search(pattern, company_name_lower, re.IGNORECASE) for pattern in skip_patterns):
                continue
            
            # Skip if it's just an industry name (without company name)
            if company_name_lower in industry_names:
                continue
            
            # Skip if it's an industry percentage row (e.g., "Beverage, Food, and Tobacco –2.2%")
            if re.search(r'^[^–-]+[–-]\s*\d+\.?\d*%', company_name):
                continue
            
            # Skip if it's an investment type description without company name
            # (e.g., "Beverage, Food, and Tobacco – Line of Credit, $...")
            if re.search(r'^[^–-]+[–-]\s*(line\s+of\s+credit|term\s+debt|delayed\s+draw)', company_name_lower):
                # Check if there's a company name before the dash
                parts = re.split(r'[–-]', company_name, 1)
                if len(parts) == 2:
                    first_part = parts[0].strip().lower()
                    # If first part is an industry name, skip
                    if first_part in industry_names:
                        continue
            
            # Skip rows with no meaningful financial data
            principal = html_inv.get('principal_amount')
            cost = html_inv.get('cost')
            fair_value = html_inv.get('fair_value')
            if not principal and not cost and not fair_value:
                # Only skip if investment_type is also Unknown or empty
                inv_type = html_inv.get('investment_type', '').strip().lower()
                if inv_type in ('unknown', '', 'n/a'):
                    continue
            
            # Clean company name (remove extra text)
            cleaned_name = html_inv.get('_cleaned_company_name', company_name)
            
            # The HTML parser may put the full description in investment_type instead of company_name
            # Check investment_type for company name if company_name looks incomplete
            inv_type_raw = html_inv.get('investment_type', '')
            if inv_type_raw and ('–' in inv_type_raw or '-' in inv_type_raw):
                # Pattern: "Company Name – Investment Type Description"
                # Extract company name from investment_type if it's there
                parts = re.split(r'\s*[–-]\s+', inv_type_raw, 1)
                if len(parts) == 2:
                    potential_company = parts[0].strip()
                    second_part = parts[1].strip().lower()
                    
                    # Check if second part looks like investment type description
                    investment_type_indicators = [
                        'line of credit', 'term debt', 'delayed draw', 'preferred equity',
                        'common equity', 'warrants', 'first lien', 'second lien', 'secured',
                        'unsecured', 'convertible', 'due ', 'cash', 'pik', 'available'
                    ]
                    
                    if any(indicator in second_part for indicator in investment_type_indicators):
                        # Use company name from investment_type, and extract clean investment type
                        cleaned_name = potential_company
                        # Extract investment type from second part
                        inv_type_clean = second_part
                        # Normalize investment type
                        if 'line of credit' in inv_type_clean:
                            inv_type_clean = 'Line of Credit'
                        elif 'delayed draw' in inv_type_clean:
                            inv_type_clean = 'Delayed Draw Term Loan'
                        elif 'term debt' in inv_type_clean:
                            inv_type_clean = 'Term Debt'
                        elif 'preferred equity' in inv_type_clean:
                            inv_type_clean = 'Preferred Equity'
                        elif 'common equity' in inv_type_clean:
                            inv_type_clean = 'Common Equity'
                        elif 'warrants' in inv_type_clean:
                            inv_type_clean = 'Warrants'
                        elif 'first lien' in inv_type_clean:
                            inv_type_clean = 'First Lien Debt'
                        elif 'second lien' in inv_type_clean:
                            inv_type_clean = 'Second Lien Debt'
                        else:
                            inv_type_clean = 'Term Debt'  # Default
                        html_inv['investment_type'] = inv_type_clean
            
            # Additional cleaning: remove investment type descriptions from company name
            # Pattern: "Company Name – Investment Type Description"
            if '–' in cleaned_name or '-' in cleaned_name:
                # Try to extract just the company name part
                parts = re.split(r'\s*[–-]\s+', cleaned_name, 1)
                if len(parts) == 2:
                    potential_company = parts[0].strip()
                    second_part = parts[1].strip().lower()
                    
                    # Check if second part looks like investment type description
                    investment_type_indicators = [
                        'line of credit', 'term debt', 'delayed draw', 'preferred equity',
                        'common equity', 'warrants', 'first lien', 'second lien', 'secured',
                        'unsecured', 'convertible', 'due ', 'cash', 'pik', 'available'
                    ]
                    
                    if any(indicator in second_part for indicator in investment_type_indicators):
                        # Second part is investment description, use first part as company name
                        cleaned_name = potential_company
                    # If first part looks like a company name (has LLC, Inc, etc. or is reasonable length)
                    elif any(suffix in potential_company.lower() for suffix in ['llc', 'inc', 'corp', 'ltd', 'holdings', 'group', 'lp', 'l.p.']):
                        cleaned_name = potential_company
            
            # Final cleanup: remove any trailing parentheticals that might be left
            cleaned_name = re.sub(r'\s*\([^)]*\)\s*$', '', cleaned_name).strip()
            
            # Skip if cleaned name is too short or looks invalid
            if len(cleaned_name) < 2:
                continue
            
            # Fix "Pan" -> should be "Pan-Am Dental, LLC" if we can find it
            if cleaned_name.lower() == 'pan' and inv_type_raw:
                # Look for "Pan-Am" in the investment type
                pan_match = re.search(r'(Pan[-–]Am\s+Dental[^–-]*)', inv_type_raw, re.IGNORECASE)
                if pan_match:
                    cleaned_name = pan_match.group(1).strip()
            
            new_inv = GLADInvestment(
                company_name=cleaned_name,
                investment_type=html_inv.get('investment_type', 'Unknown'),
                industry=html_inv.get('industry', 'Unknown'),
                business_description=html_inv.get('business_description'),
                acquisition_date=html_inv.get('acquisition_date'),
                maturity_date=html_inv.get('maturity_date'),
                principal_amount=html_inv.get('principal_amount'),
                cost=html_inv.get('cost'),
                fair_value=html_inv.get('fair_value'),
                interest_rate=html_inv.get('interest_rate'),
                reference_rate=html_inv.get('reference_rate'),
                spread=html_inv.get('spread'),
                floor_rate=html_inv.get('floor_rate'),
                pik_rate=html_inv.get('pik_rate'),
            )
            investments.append(new_inv)
            added_count += 1
        
        if added_count > 0:
            logger.info(f"HTML fallback: Added {added_count} investments from HTML that weren't in XBRL")


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=GLADExtractor()
    try:
        res=ex.extract_from_ticker('GLAD')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





    main()




