#!/usr/bin/env python3
import re, os, csv, logging, requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class LRFCInvestment:
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


class LRFCExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "LRFC", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            # Known override mapping
            overrides = {
                'LRFC': '0001278752',  # Logan Ridge Finance Corp (formerly OHA Investment Corp)
            }
            if ticker.upper() in overrides:
                cik = overrides[ticker.upper()]
            else:
                raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        return self.extract_from_url(txt_url, "Logan_Ridge_Finance_Corp", cik)

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
        invs: List[LRFCInvestment] = []
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
        out_file = os.path.join(out_dir, 'LRFC_Logan_Ridge_Finance_Corp_investments.csv')
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
        # Convert invs to dict format
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
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same if same else 'Unknown')
            res.append({
                'id':cid,
                'investment_identifier':ident,
                'raw_identifier':ident,
                'company_name':parsed['company_name'],
                'industry':final_industry,
                'business_description':parsed.get('business_description'),
                'investment_type':parsed['investment_type'],
                'maturity_date':parsed.get('maturity_date'),
                'acquisition_date':parsed.get('acquisition_date'),
                'pik_rate':parsed.get('pik_rate'),
                'reference_rate':parsed.get('reference_rate'),
                'spread':parsed.get('spread'),
                'floor_rate':parsed.get('floor_rate'),
                'instant':inst.group(1) if inst else None,
                'start_date':sd.group(1) if sd else None,
                'end_date':ed.group(1) if ed else None
            })
        return res

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_identifier(self, identifier: str) -> Dict[str,str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # Extract dates from identifier (can be 2-digit or 4-digit years)
        # Pattern: "Maturity Date MM/DD/YY" or "Maturity Date MM/DD/YYYY"
        maturity_match = re.search(r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            date_str = maturity_match.group(1)
            # Normalize 2-digit year to 4-digit (assume 2000s if year < 50, else 1900s)
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        # Extract PIK rate
        pik_match = re.search(r'(?:Cash\s+plus\s+)?([\d\.]+)\s*%\s*PIK', ident_clean, re.IGNORECASE)
        if pik_match:
            res['pik_rate'] = self._percent(pik_match.group(1))
        
        # Extract reference rate and spread (e.g., "SOFR+275" or "SOFR+2.75%")
        ref_spread_match = re.search(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            ref_rate = ref_spread_match.group(1).upper().replace('BASE RATE', 'BASE RATE')
            spread_val = ref_spread_match.group(2)
            try:
                sv = float(spread_val)
                # If looks like bps (e.g., 275), convert to percent; if already percent like 2.75, keep
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_val
            res['reference_rate'] = ref_rate
            res['spread'] = self._percent(str(sv))
        
        # Extract floor rate (e.g., "1.00% Floor")
        # Floor rates are already percentages, so don't scale them
        floor_match = re.search(r'([\d\.]+)\s*%\s*Floor', ident_clean, re.IGNORECASE)
        if floor_match:
            floor_val = floor_match.group(1)
            # If it's already a percentage (1.00, 0.75, etc.), keep as-is
            try:
                fv = float(floor_val)
                # If value is already in percentage range (0.5-100), use as-is
                if 0.5 <= fv <= 100:
                    res['floor_rate'] = f"{fv:.2f}".rstrip('0').rstrip('.') + "%"
                else:
                    res['floor_rate'] = self._percent(floor_val)
            except:
                res['floor_rate'] = f"{floor_val}%"
        
        # LRFC format (same as MFIC): "Industry Company Name [Business Name] Investment Type [Rate Info]"
        # Extract investment type first
        inv_type_patterns = [
            r'\s+First\s+Lien\s+Secured\s+Debt(?:\s*[\-\u2013]\s*(Revolver|Term\s+Loan|Delayed\s+Draw))?',
            r'\s+Second\s+Lien\s+.*?(?:Debt|Loan)',
            r'\s+Common\s+Equity(?:\s*[\-\u2013]\s*(?:Equity|Common\s+Stock))?',
            r'\s+Preferred\s+Equity',
            r'\s+Preferred\s+Stock',
            r'\s+Common\s+Stock',
            r'\s+Warrants?',
            r'\s+Unitranche',
            r'\s+Subordinated\s+Debt'
        ]
        
        it_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, ident_clean, re.IGNORECASE)
            if match:
                it_match = match
                it_text = match.group(0).strip()
                it_text = re.sub(r'\s+[\-\u2013]\s+', ' - ', it_text)
                res['investment_type'] = it_text
                break
        
        if it_match:
            before_inv = ident_clean[:it_match.start()].strip()
        else:
            before_inv = ident_clean
        
        # Extract industry
        industry_patterns = [
            r'^(Leisure\s+Products|Financial\s+Services|Containers\s+&\s*Packaging|Ground\s+Transportation|'
            r'Diversified\s+Consumer\s+Services|Health\s+Care\s+Providers\s*&\s*Services|'
            r'Trading\s+Companies\s*&\s*Distributors|Commercial\s+Services\s*&\s*Supplies|'
            r'Professional\s+Services|Software|Automobile\s+Components|Personal\s+Care\s+Products|'
            r'Food\s+Products|Energy\s+Equipment\s*&\s*Services|Electronic\s+Equipment|Instruments\s+and\s+Components)\s+',
        ]
        
        industry_match = None
        for pattern in industry_patterns:
            match = re.match(pattern, before_inv, re.IGNORECASE)
            if match:
                industry_match = match
                res['industry'] = match.group(1).strip()
                break
        
        if industry_match:
            company_part = before_inv[industry_match.end():].strip()
            remaining_industry_match = re.match(r'^(Health\s+Care\s+Providers|Trading\s+Companies|Commercial\s+Services|Energy\s+Equipment)\s+&\s+Services\s+', company_part, re.IGNORECASE)
            if remaining_industry_match:
                company_part = company_part[remaining_industry_match.end():].strip()
        else:
            company_part = before_inv
        
        # Extract company name
        entity_pattern = r'([A-Z][A-Za-z0-9\s&,\-\.]{2,}?)\s+(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co)(?:\s|$)'
        entities = []
        for match in re.finditer(entity_pattern, company_part, re.IGNORECASE):
            entity_name = match.group(1).strip()
            entity_type = match.group(2)
            full_entity = f"{entity_name} {entity_type}"
            entities.append((full_entity, match.start(), match.end(), entity_name, entity_type))
        
        if entities:
            last_entity_full, start_pos, end_pos, last_entity_name, last_entity_type = entities[-1]
            
            if 'f/k/a' in last_entity_name or 'fka' in last_entity_name:
                fka_match = re.search(r'([^(]+?)\s*(?:\(|f/k/a|fka)', last_entity_name, re.IGNORECASE)
                if fka_match:
                    last_entity_name = fka_match.group(1).strip()
                    last_entity_full = f"{last_entity_name} {last_entity_type}"
            
            company_part_lower = company_part.lower()
            entity_name_lower = last_entity_name.lower()
            entity_words = entity_name_lower.split()
            company_name_clean = last_entity_full
            
            if len(entity_words) > 0:
                pattern = r'\b' + re.escape(entity_name_lower) + r'\b'
                matches = list(re.finditer(pattern, company_part_lower))
                
                if len(matches) > 1:
                    company_name_clean = f"{last_entity_name} {last_entity_type}"
                elif len(matches) == 1:
                    match_start = matches[0].start()
                    if match_start > 0:
                        prefix_before = company_part_lower[:match_start].strip()
                        common_prefix_words = ['services', 'distributors', 'packaging', 'supplies', 'solutions', 'banner', 'health', 'care', 'providers']
                        prefix_words = prefix_before.split()
                        if len(prefix_words) >= 2 or any(word in prefix_words for word in common_prefix_words):
                            if prefix_words and prefix_words[-1] in entity_words:
                                company_name_clean = f"{last_entity_name} {last_entity_type}"
            
            unwanted_prefixes = ['Services', 'Distributors', 'Packaging', 'Supplies']
            for prefix in unwanted_prefixes:
                if company_name_clean.lower().startswith(prefix.lower() + ' '):
                    remainder = company_name_clean[len(prefix):].strip()
                    if remainder and len(remainder) > 5:
                        company_name_clean = remainder
            
            industry_prefixes_in_name = [
                r'^Health\s+Care\s+Providers\s*&\s*Services\s+',
                r'^Trading\s+Companies\s*&\s*Distributors\s+',
                r'^Commercial\s+Services\s*&\s*Supplies\s+',
                r'^Energy\s+Equipment\s*&\s*Services\s+'
            ]
            for ip_pattern in industry_prefixes_in_name:
                match = re.match(ip_pattern, company_name_clean, re.IGNORECASE)
                if match:
                    company_name_clean = re.sub(ip_pattern, '', company_name_clean, flags=re.IGNORECASE).strip()
                    entity_match_after = re.search(entity_pattern, company_name_clean, re.IGNORECASE)
                    if entity_match_after:
                        company_name_clean = f"{entity_match_after.group(1).strip()} {entity_match_after.group(2)}"
                    break
            
            res['company_name'] = self._strip_footnote_refs(company_name_clean)
            
            business_part_raw = company_part[:start_pos].strip()
            for entity_full, _, _, _, _ in entities[:-1]:
                if entity_full in business_part_raw:
                    business_part_raw = business_part_raw.replace(entity_full, '').strip()
            if business_part_raw and len(business_part_raw) > 3:
                res['business_description'] = self._strip_footnote_refs(business_part_raw)
        else:
            fallback_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.]+(?:Holdco|Holdings|Buyer|Acquisition|Parent|Opco|OpCo|Sub))', company_part, re.IGNORECASE)
            if fallback_match:
                res['company_name'] = self._strip_footnote_refs(fallback_match.group(1).strip())
            else:
                res['company_name'] = self._strip_footnote_refs(company_part)
        
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
            # Handle both 2-digit and 4-digit years
            # Try multiple date patterns
            dates=[]
            dates.extend(re.findall(r'\b\d{1,2}/\d{1,2}/(?:\d{2}|\d{4})\b', window))
            dates.extend(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', window))
            dates.extend(re.findall(r'\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{1,2}/\d{4}\b', window))
            if dates:
                # Normalize dates to 4-digit years and remove duplicates
                normalized_dates = []
                seen = set()
                for d in dates:
                    parts = d.split('/')
                    if len(parts) == 3:
                        year_str = parts[2]
                        if len(year_str) == 2:
                            try:
                                year = int(year_str)
                                if year < 50:
                                    year_str = f"20{year:02d}"
                                else:
                                    year_str = f"19{year:02d}"
                            except:
                                pass
                        normalized_d = f"{parts[0]}/{parts[1]}/{year_str}"
                    else:
                        normalized_d = d
                    if normalized_d not in seen:
                        seen.add(normalized_d)
                        normalized_dates.append(normalized_d)
                
                if len(normalized_dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value':normalized_dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value':normalized_dates[-1]})
                elif len(normalized_dates)==1:
                    date_idx=window.find(normalized_dates[0])
                    date_context=window[max(0,date_idx-50):min(len(window),date_idx+50)]
                    if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', date_context, re.IGNORECASE):
                        facts[cref].append({'concept':'derived:AcquisitionDate','value':normalized_dates[0]})
                    else:
                        facts[cref].append({'concept':'derived:MaturityDate','value':normalized_dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[LRFCInvestment]:
        if context['company_name']=='Unknown': return None
        inv=LRFCInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
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
            if cl=='derived:floorrate':
                # Floor rates from XBRL might need different handling
                try:
                    fv = float(v)
                    if 0 < abs(fv) <= 1.0:
                        # Likely a decimal, convert to percentage
                        inv.floor_rate = self._percent(v)
                    elif 0.5 <= abs(fv) <= 100:
                        # Already a percentage
                        inv.floor_rate = f"{fv:.2f}".rstrip('0').rstrip('.') + "%"
                    else:
                        inv.floor_rate = self._percent(v)
                except:
                    inv.floor_rate = self._percent(v)
                continue
            if cl=='derived:pikrate': inv.pik_rate=self._percent(v); continue
            if cl=='derived:acquisitiondate': inv.acquisition_date=v; continue
            if cl=='derived:maturitydate': inv.maturity_date=v; continue
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
        # Fill missing fields from parsed identifier tokens
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
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
    ex=LRFCExtractor()
    try:
        res=ex.extract_from_ticker('LRFC')
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
class LRFCInvestment:
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


class LRFCExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "LRFC", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            # Known override mapping
            overrides = {
                'LRFC': '0001278752',  # Logan Ridge Finance Corp (formerly OHA Investment Corp)
            }
            if ticker.upper() in overrides:
                cik = overrides[ticker.upper()]
            else:
                raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        accession = m.group(1)
        folder = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{accession}.txt"
        return self.extract_from_url(txt_url, "Logan_Ridge_Finance_Corp", cik)

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
        invs: List[LRFCInvestment] = []
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
        out_file = os.path.join(out_dir, 'LRFC_Logan_Ridge_Finance_Corp_investments.csv')
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
        # Convert invs to dict format
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
            # Prefer industry from identifier parsing over XBRL axis if identifier has it
            final_industry = parsed['industry'] if parsed['industry'] != 'Unknown' else (same if same else 'Unknown')
            res.append({
                'id':cid,
                'investment_identifier':ident,
                'raw_identifier':ident,
                'company_name':parsed['company_name'],
                'industry':final_industry,
                'business_description':parsed.get('business_description'),
                'investment_type':parsed['investment_type'],
                'maturity_date':parsed.get('maturity_date'),
                'acquisition_date':parsed.get('acquisition_date'),
                'pik_rate':parsed.get('pik_rate'),
                'reference_rate':parsed.get('reference_rate'),
                'spread':parsed.get('spread'),
                'floor_rate':parsed.get('floor_rate'),
                'instant':inst.group(1) if inst else None,
                'start_date':sd.group(1) if sd else None,
                'end_date':ed.group(1) if ed else None
            })
        return res

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _parse_identifier(self, identifier: str) -> Dict[str,str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'maturity_date': None, 'acquisition_date': None,
               'pik_rate': None, 'reference_rate': None, 'spread': None, 'floor_rate': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # Extract dates from identifier (can be 2-digit or 4-digit years)
        # Pattern: "Maturity Date MM/DD/YY" or "Maturity Date MM/DD/YYYY"
        maturity_match = re.search(r'Maturity\s+Date\s+(\d{1,2}/\d{1,2}/\d{2,4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            date_str = maturity_match.group(1)
            # Normalize 2-digit year to 4-digit (assume 2000s if year < 50, else 1900s)
            if len(date_str.split('/')[-1]) == 2:
                year = int(date_str.split('/')[-1])
                if year < 50:
                    date_str = date_str[:-2] + f"20{year:02d}"
                else:
                    date_str = date_str[:-2] + f"19{year:02d}"
            res['maturity_date'] = date_str
        
        # Extract PIK rate
        pik_match = re.search(r'(?:Cash\s+plus\s+)?([\d\.]+)\s*%\s*PIK', ident_clean, re.IGNORECASE)
        if pik_match:
            res['pik_rate'] = self._percent(pik_match.group(1))
        
        # Extract reference rate and spread (e.g., "SOFR+275" or "SOFR+2.75%")
        ref_spread_match = re.search(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)', ident_clean, re.IGNORECASE)
        if ref_spread_match:
            ref_rate = ref_spread_match.group(1).upper().replace('BASE RATE', 'BASE RATE')
            spread_val = ref_spread_match.group(2)
            try:
                sv = float(spread_val)
                # If looks like bps (e.g., 275), convert to percent; if already percent like 2.75, keep
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_val
            res['reference_rate'] = ref_rate
            res['spread'] = self._percent(str(sv))
        
        # Extract floor rate (e.g., "1.00% Floor")
        # Floor rates are already percentages, so don't scale them
        floor_match = re.search(r'([\d\.]+)\s*%\s*Floor', ident_clean, re.IGNORECASE)
        if floor_match:
            floor_val = floor_match.group(1)
            # If it's already a percentage (1.00, 0.75, etc.), keep as-is
            try:
                fv = float(floor_val)
                # If value is already in percentage range (0.5-100), use as-is
                if 0.5 <= fv <= 100:
                    res['floor_rate'] = f"{fv:.2f}".rstrip('0').rstrip('.') + "%"
                else:
                    res['floor_rate'] = self._percent(floor_val)
            except:
                res['floor_rate'] = f"{floor_val}%"
        
        # LRFC format (same as MFIC): "Industry Company Name [Business Name] Investment Type [Rate Info]"
        # Extract investment type first
        inv_type_patterns = [
            r'\s+First\s+Lien\s+Secured\s+Debt(?:\s*[\-\u2013]\s*(Revolver|Term\s+Loan|Delayed\s+Draw))?',
            r'\s+Second\s+Lien\s+.*?(?:Debt|Loan)',
            r'\s+Common\s+Equity(?:\s*[\-\u2013]\s*(?:Equity|Common\s+Stock))?',
            r'\s+Preferred\s+Equity',
            r'\s+Preferred\s+Stock',
            r'\s+Common\s+Stock',
            r'\s+Warrants?',
            r'\s+Unitranche',
            r'\s+Subordinated\s+Debt'
        ]
        
        it_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, ident_clean, re.IGNORECASE)
            if match:
                it_match = match
                it_text = match.group(0).strip()
                it_text = re.sub(r'\s+[\-\u2013]\s+', ' - ', it_text)
                res['investment_type'] = it_text
                break
        
        if it_match:
            before_inv = ident_clean[:it_match.start()].strip()
        else:
            before_inv = ident_clean
        
        # Extract industry
        industry_patterns = [
            r'^(Leisure\s+Products|Financial\s+Services|Containers\s+&\s*Packaging|Ground\s+Transportation|'
            r'Diversified\s+Consumer\s+Services|Health\s+Care\s+Providers\s*&\s*Services|'
            r'Trading\s+Companies\s*&\s*Distributors|Commercial\s+Services\s*&\s*Supplies|'
            r'Professional\s+Services|Software|Automobile\s+Components|Personal\s+Care\s+Products|'
            r'Food\s+Products|Energy\s+Equipment\s*&\s*Services|Electronic\s+Equipment|Instruments\s+and\s+Components)\s+',
        ]
        
        industry_match = None
        for pattern in industry_patterns:
            match = re.match(pattern, before_inv, re.IGNORECASE)
            if match:
                industry_match = match
                res['industry'] = match.group(1).strip()
                break
        
        if industry_match:
            company_part = before_inv[industry_match.end():].strip()
            remaining_industry_match = re.match(r'^(Health\s+Care\s+Providers|Trading\s+Companies|Commercial\s+Services|Energy\s+Equipment)\s+&\s+Services\s+', company_part, re.IGNORECASE)
            if remaining_industry_match:
                company_part = company_part[remaining_industry_match.end():].strip()
        else:
            company_part = before_inv
        
        # Extract company name
        entity_pattern = r'([A-Z][A-Za-z0-9\s&,\-\.]{2,}?)\s+(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co)(?:\s|$)'
        entities = []
        for match in re.finditer(entity_pattern, company_part, re.IGNORECASE):
            entity_name = match.group(1).strip()
            entity_type = match.group(2)
            full_entity = f"{entity_name} {entity_type}"
            entities.append((full_entity, match.start(), match.end(), entity_name, entity_type))
        
        if entities:
            last_entity_full, start_pos, end_pos, last_entity_name, last_entity_type = entities[-1]
            
            if 'f/k/a' in last_entity_name or 'fka' in last_entity_name:
                fka_match = re.search(r'([^(]+?)\s*(?:\(|f/k/a|fka)', last_entity_name, re.IGNORECASE)
                if fka_match:
                    last_entity_name = fka_match.group(1).strip()
                    last_entity_full = f"{last_entity_name} {last_entity_type}"
            
            company_part_lower = company_part.lower()
            entity_name_lower = last_entity_name.lower()
            entity_words = entity_name_lower.split()
            company_name_clean = last_entity_full
            
            if len(entity_words) > 0:
                pattern = r'\b' + re.escape(entity_name_lower) + r'\b'
                matches = list(re.finditer(pattern, company_part_lower))
                
                if len(matches) > 1:
                    company_name_clean = f"{last_entity_name} {last_entity_type}"
                elif len(matches) == 1:
                    match_start = matches[0].start()
                    if match_start > 0:
                        prefix_before = company_part_lower[:match_start].strip()
                        common_prefix_words = ['services', 'distributors', 'packaging', 'supplies', 'solutions', 'banner', 'health', 'care', 'providers']
                        prefix_words = prefix_before.split()
                        if len(prefix_words) >= 2 or any(word in prefix_words for word in common_prefix_words):
                            if prefix_words and prefix_words[-1] in entity_words:
                                company_name_clean = f"{last_entity_name} {last_entity_type}"
            
            unwanted_prefixes = ['Services', 'Distributors', 'Packaging', 'Supplies']
            for prefix in unwanted_prefixes:
                if company_name_clean.lower().startswith(prefix.lower() + ' '):
                    remainder = company_name_clean[len(prefix):].strip()
                    if remainder and len(remainder) > 5:
                        company_name_clean = remainder
            
            industry_prefixes_in_name = [
                r'^Health\s+Care\s+Providers\s*&\s*Services\s+',
                r'^Trading\s+Companies\s*&\s*Distributors\s+',
                r'^Commercial\s+Services\s*&\s*Supplies\s+',
                r'^Energy\s+Equipment\s*&\s*Services\s+'
            ]
            for ip_pattern in industry_prefixes_in_name:
                match = re.match(ip_pattern, company_name_clean, re.IGNORECASE)
                if match:
                    company_name_clean = re.sub(ip_pattern, '', company_name_clean, flags=re.IGNORECASE).strip()
                    entity_match_after = re.search(entity_pattern, company_name_clean, re.IGNORECASE)
                    if entity_match_after:
                        company_name_clean = f"{entity_match_after.group(1).strip()} {entity_match_after.group(2)}"
                    break
            
            res['company_name'] = self._strip_footnote_refs(company_name_clean)
            
            business_part_raw = company_part[:start_pos].strip()
            for entity_full, _, _, _, _ in entities[:-1]:
                if entity_full in business_part_raw:
                    business_part_raw = business_part_raw.replace(entity_full, '').strip()
            if business_part_raw and len(business_part_raw) > 3:
                res['business_description'] = self._strip_footnote_refs(business_part_raw)
        else:
            fallback_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.]+(?:Holdco|Holdings|Buyer|Acquisition|Parent|Opco|OpCo|Sub))', company_part, re.IGNORECASE)
            if fallback_match:
                res['company_name'] = self._strip_footnote_refs(fallback_match.group(1).strip())
            else:
                res['company_name'] = self._strip_footnote_refs(company_part)
        
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
            # Handle both 2-digit and 4-digit years
            # Try multiple date patterns
            dates=[]
            dates.extend(re.findall(r'\b\d{1,2}/\d{1,2}/(?:\d{2}|\d{4})\b', window))
            dates.extend(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', window))
            dates.extend(re.findall(r'\b[A-Za-z]+\s+\d{1,2},\s*\d{4}\b', window))
            dates.extend(re.findall(r'\b\d{1,2}/\d{4}\b', window))
            if dates:
                # Normalize dates to 4-digit years and remove duplicates
                normalized_dates = []
                seen = set()
                for d in dates:
                    parts = d.split('/')
                    if len(parts) == 3:
                        year_str = parts[2]
                        if len(year_str) == 2:
                            try:
                                year = int(year_str)
                                if year < 50:
                                    year_str = f"20{year:02d}"
                                else:
                                    year_str = f"19{year:02d}"
                            except:
                                pass
                        normalized_d = f"{parts[0]}/{parts[1]}/{year_str}"
                    else:
                        normalized_d = d
                    if normalized_d not in seen:
                        seen.add(normalized_d)
                        normalized_dates.append(normalized_d)
                
                if len(normalized_dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value':normalized_dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value':normalized_dates[-1]})
                elif len(normalized_dates)==1:
                    date_idx=window.find(normalized_dates[0])
                    date_context=window[max(0,date_idx-50):min(len(window),date_idx+50)]
                    if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', date_context, re.IGNORECASE):
                        facts[cref].append({'concept':'derived:AcquisitionDate','value':normalized_dates[0]})
                    else:
                        facts[cref].append({'concept':'derived:MaturityDate','value':normalized_dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[LRFCInvestment]:
        if context['company_name']=='Unknown': return None
        inv=LRFCInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
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
            if cl=='derived:floorrate':
                # Floor rates from XBRL might need different handling
                try:
                    fv = float(v)
                    if 0 < abs(fv) <= 1.0:
                        # Likely a decimal, convert to percentage
                        inv.floor_rate = self._percent(v)
                    elif 0.5 <= abs(fv) <= 100:
                        # Already a percentage
                        inv.floor_rate = f"{fv:.2f}".rstrip('0').rstrip('.') + "%"
                    else:
                        inv.floor_rate = self._percent(v)
                except:
                    inv.floor_rate = self._percent(v)
                continue
            if cl=='derived:pikrate': inv.pik_rate=self._percent(v); continue
            if cl=='derived:acquisitiondate': inv.acquisition_date=v; continue
            if cl=='derived:maturitydate': inv.maturity_date=v; continue
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
        # Fill missing fields from parsed identifier tokens
        if not inv.maturity_date and context.get('maturity_date'):
            inv.maturity_date = context['maturity_date']
        if not inv.acquisition_date:
            if context.get('acquisition_date'):
                inv.acquisition_date = context['acquisition_date']
            elif context.get('start_date'):
                inv.acquisition_date = context['start_date'][:10]
        if not inv.pik_rate and context.get('pik_rate'):
            inv.pik_rate = context['pik_rate']
        if not inv.reference_rate and context.get('reference_rate'):
            inv.reference_rate = context['reference_rate']
        if not inv.spread and context.get('spread'):
            inv.spread = context['spread']
        if not inv.floor_rate and context.get('floor_rate'):
            inv.floor_rate = context['floor_rate']
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
    ex=LRFCExtractor()
    try:
        res=ex.extract_from_ticker('LRFC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()






