#!/usr/bin/env python3
import re, os, csv, logging, requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class LIENInvestment:
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


class LIENExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "LIEN") -> Dict:
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
        return self.extract_from_url(txt_url, "Chicago_Atlantic_BDC_Inc", cik)

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
        invs: List[LIENInvestment] = []
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
        out_file = os.path.join(out_dir, 'LIEN_Chicago_Atlantic_BDC_Inc_investments.csv')
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
        
        # LIEN format patterns:
        # 1. "US Corporate Debt [Investment Type] U.S. Debt [Industry] [Company Name] Facility Type [Type] All in Rate X.XX% Benchmark [Letter] Spread X.XX% PIK X.XX% Floor X.XX% Initial Acquisition Date X/X/XXXX Maturity X/X/XXXX"
        # 2. "U.S. Warrants [Industry] [Company Name] Warrants Initial Acquisition Date X/X/XXXX"
        
        # Extract dates first (they're at the end)
        acq_match = re.search(r'Initial\s+Acquisition\s+Date\s+(\d{1,2}/\d{1,2}/\d{4})', ident_clean, re.IGNORECASE)
        if acq_match:
            res['acquisition_date'] = acq_match.group(1)
        
        maturity_match = re.search(r'Maturity\s+(\d{1,2}/\d{1,2}/\d{4})', ident_clean, re.IGNORECASE)
        if maturity_match:
            res['maturity_date'] = maturity_match.group(1)
        
        # Extract investment type
        inv_type_match = re.search(r'US\s+Corporate\s+Debt\s+(First\s+Lien\s+Senior\s+Secured|Second\s+Lien\s+Senior\s+Secured|Senior\s+Secured)\s+U\.S\.\s+(Debt|Notes)', ident_clean, re.IGNORECASE)
        if inv_type_match:
            it_part1 = inv_type_match.group(1)
            it_part2 = inv_type_match.group(2)
            res['investment_type'] = f"{it_part1} {it_part2}"
        elif re.search(r'U\.S\.\s+Warrants', ident_clean, re.IGNORECASE):
            res['investment_type'] = "Warrants"
        
        # Extract industry - comes after "U.S. Debt" or "U.S. Notes" or "U.S. Warrants"
        # Industry is typically a single word or short phrase like "Cannabis", "Information", "Retail Trade", "Finance and Insurance"
        # Common industries in LIEN: Cannabis, Information, Retail Trade, Finance and Insurance, Real Estate and Rental
        common_industries = [
            'Cannabis', 'Information', 'Retail Trade', 'Finance and Insurance', 
            'Real Estate and Rental', 'Finance', 'Insurance', 'Real Estate'
        ]
        
        # First try to match known industry names
        industry_match = None
        industry_name = None
        for ind in common_industries:
            pattern = rf'U\.S\.\s+(?:Debt|Notes|Warrants)\s+{re.escape(ind)}(?:\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|Labs|Facility|Warrants))'
            match = re.search(pattern, ident_clean, re.IGNORECASE)
            if match:
                industry_match = match
                industry_name = ind
                break
        
        # If no exact match, try pattern matching
        if not industry_match:
            industry_match = re.search(r'U\.S\.\s+(?:Debt|Notes|Warrants)\s+([A-Z][A-Za-z]+(?:\s+and\s+[A-Z][A-Za-z]+)?|\w+(?:\s+\w+)?)(?:\s+(?:LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|Labs|Facility|Warrants))', ident_clean, re.IGNORECASE)
            if industry_match:
                potential_industry = industry_match.group(1).strip()
                # Check if it matches a known industry pattern
                if 'and' in potential_industry.lower():
                    # Could be "Finance and Insurance" or "Real Estate and Rental"
                    parts = potential_industry.lower().split(' and ')
                    if len(parts) == 2:
                        first = parts[0].strip().title()
                        second = parts[1].strip().title()
                        combined = f"{first} and {second}"
                        if combined in ['Finance and Insurance', 'Real Estate and Rental']:
                            industry_name = combined
                elif potential_industry.lower() in [i.lower() for i in common_industries]:
                    industry_name = potential_industry
                else:
                    # Single word industries
                    industry_name = potential_industry.split()[0] if potential_industry.split() else potential_industry
        
        if industry_name:
            res['industry'] = industry_name
        
        # Extract company name - find entity name (LLC, Inc., Corp, etc.)
        # Company name is between industry and "Facility Type" or "Warrants Initial" or other stop words
        if 'Facility Type' in ident_clean:
            facility_pos = ident_clean.find('Facility Type')
            before_facility = ident_clean[:facility_pos]
            
            # Find where industry ends
            industry_start = 0
            if res['industry'] != 'Unknown':
                industry_pos = before_facility.upper().find(res['industry'].upper())
                if industry_pos >= 0:
                    industry_start = industry_pos + len(res['industry'])
            
            # Text between industry and Facility Type
            company_text = before_facility[industry_start:].strip()
            
            # Remove common prefixes that might have leaked in - more aggressive
            company_text = re.sub(r'^US\s+Corporate\s+Debt\s+', '', company_text, flags=re.IGNORECASE)
            company_text = re.sub(r'^First\s+Lien\s+Senior\s+Secured\s+', '', company_text, flags=re.IGNORECASE)
            company_text = re.sub(r'^Senior\s+Secured\s+', '', company_text, flags=re.IGNORECASE)
            company_text = re.sub(r'^Second\s+Lien\s+Senior\s+Secured\s+', '', company_text, flags=re.IGNORECASE)
            company_text = re.sub(r'^U\.S\.\s+Debt\s+', '', company_text, flags=re.IGNORECASE)
            company_text = re.sub(r'^U\.S\.\s+Notes\s+', '', company_text, flags=re.IGNORECASE)
            # Remove industry name if it appears again (sometimes it's duplicated)
            if res['industry'] != 'Unknown':
                company_text = re.sub(r'^' + re.escape(res['industry']) + r'\s+', '', company_text, flags=re.IGNORECASE)
            company_text = company_text.strip()
            
            # Find entity pattern in this text
            entity_pattern = r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|Labs)(?:\s|$|,)'
            entity_match = re.search(entity_pattern, company_text, re.IGNORECASE)
            if entity_match:
                entity_name = entity_match.group(1).strip()
                entity_type = entity_match.group(2)
                # Clean entity name - remove trailing commas and industry prefixes
                entity_name = entity_name.rstrip(',').strip()
                # Remove industry prefix if it appears at the start
                if res['industry'] != 'Unknown':
                    # Remove industry from start of entity name
                    industry_prefix = res['industry'] + ' '
                    if entity_name.lower().startswith(industry_prefix.lower()):
                        entity_name = entity_name[len(industry_prefix):].strip()
                    # Also remove if industry is embedded (like "Cannabis Elevation Cannabis")
                    words = entity_name.split()
                    if len(words) > 1 and words[0].lower() == res['industry'].lower().split()[0].lower():
                        # Remove first word if it's the industry
                        entity_name = ' '.join(words[1:]).strip()
                # Remove other common prefixes
                entity_name = re.sub(r'^(Debt|Notes|U\.S\.\s+(?:Debt|Notes|Warrants))\s+', '', entity_name, flags=re.IGNORECASE)
                entity_name = entity_name.strip()
                # Handle d/b/a (doing business as) - include it in the name
                if entity_match.end() < len(company_text):
                    after_entity = company_text[entity_match.end():].strip()
                    dba_match = re.search(r'\(d/b/a\s+([^)]+)\)', after_entity, re.IGNORECASE)
                    if dba_match:
                        res['company_name'] = self._strip_footnote_refs(f"{entity_name} {entity_type} (d/b/a {dba_match.group(1)})")
                    else:
                        # Check for dba (without slash)
                        dba_match2 = re.search(r'\(dba\s+([^)]+)\)', after_entity, re.IGNORECASE)
                        if dba_match2:
                            res['company_name'] = self._strip_footnote_refs(f"{entity_name} {entity_type} (dba {dba_match2.group(1)})")
                        else:
                            res['company_name'] = self._strip_footnote_refs(f"{entity_name} {entity_type}")
            else:
                # Fallback: take text up to comma or first meaningful stop word
                comma_pos = company_text.find(',')
                if comma_pos > 0:
                    company_candidate = company_text[:comma_pos].strip()
                    if company_candidate and len(company_candidate) > 3:
                        res['company_name'] = self._strip_footnote_refs(company_candidate)
        else:
            # For warrants: "U.S. Warrants [Industry] [Company Name] Warrants Initial..."
            if re.search(r'U\.S\.\s+Warrants', ident_clean, re.IGNORECASE):
                # Find industry position
                industry_start = 0
                if res['industry'] != 'Unknown':
                    industry_pos = ident_clean.upper().find(res['industry'].upper())
                    if industry_pos >= 0:
                        industry_start = industry_pos + len(res['industry'])
                
                # Text between industry and "Warrants Initial"
                after_industry = ident_clean[industry_start:].strip()
                warrants_match = re.search(r'Warrants\s+Initial', after_industry, re.IGNORECASE)
                if warrants_match:
                    company_text = after_industry[:warrants_match.start()].strip()
                    entity_pattern = r'([A-Z][A-Za-z0-9\s&,\-\.\(\)/]+?)\s+(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co|Labs)(?:\s|$|,)'
                    entity_match = re.search(entity_pattern, company_text, re.IGNORECASE)
                    if entity_match:
                        entity_name = entity_match.group(1).strip()
                        entity_type = entity_match.group(2)
                        after_entity = company_text[entity_match.end():].strip()
                        dba_match = re.search(r'\(dba\s+([^)]+)\)', after_entity, re.IGNORECASE)
                        if dba_match:
                            res['company_name'] = self._strip_footnote_refs(f"{entity_name} {entity_type} (dba {dba_match.group(1)})")
                        else:
                            res['company_name'] = self._strip_footnote_refs(f"{entity_name} {entity_type}")
        
        # Extract rates and spreads from identifier
        spread_match = re.search(r'Spread\s+([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if spread_match:
            res['spread'] = self._percent(spread_match.group(1))
        
        pik_match = re.search(r'PIK\s+([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if pik_match:
            pik_val = pik_match.group(1)
            try:
                if float(pik_val) > 0:
                    res['pik_rate'] = self._percent(pik_val)
            except:
                pass
        
        floor_match = re.search(r'Floor\s+([\d\.]+)\s*%', ident_clean, re.IGNORECASE)
        if floor_match:
            floor_val = floor_match.group(1)
            try:
                fv = float(floor_val)
                if 0.5 <= fv <= 100:
                    res['floor_rate'] = f"{fv:.2f}".rstrip('0').rstrip('.') + "%"
                else:
                    res['floor_rate'] = self._percent(floor_val)
            except:
                res['floor_rate'] = f"{floor_val}%"
        
        # Reference rate from Benchmark letter: "Benchmark [P/F/S]"
        benchmark_match = re.search(r'Benchmark\s+([PFS])', ident_clean, re.IGNORECASE)
        if benchmark_match:
            letter = benchmark_match.group(1).upper()
            if letter == 'P':
                res['reference_rate'] = 'PRIME'
            elif letter == 'F':
                res['reference_rate'] = 'FED FUNDS'
            elif letter == 'S':
                res['reference_rate'] = 'SOFR'
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[LIENInvestment]:
        # Don't filter out Unknown company names if we have financial data - we can still extract useful info
        # But prefer to have a company name
        if context['company_name']=='Unknown':
            # Try to extract from raw identifier as fallback
            raw = context.get('raw_identifier', '')
            if raw:
                # Last resort: try simple extraction
                if 'Facility Type' in raw:
                    parts = raw.split('Facility Type')[0].strip()
                    # Take last meaningful part before Facility Type
                    parts_list = parts.split()
                    if len(parts_list) > 3:
                        # Try to find company name in the last few words
                        potential_name = ' '.join(parts_list[-4:])
                        if len(potential_name) > 5:
                            context['company_name'] = potential_name
        if context['company_name']=='Unknown': return None
        inv=LIENInvestment(
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
                # Floor rates might need different handling
                try:
                    fv = float(v)
                    if 0 < abs(fv) <= 1.0:
                        inv.floor_rate = self._percent(v)
                    elif 0.5 <= abs(fv) <= 100:
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
    ex=LIENExtractor()
    try:
        res=ex.extract_from_ticker('LIEN')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

    def _extract_html_fallback(self, filing_url: str) -> Optional[List[Dict]]:
        """Extract investments from HTML tables as fallback."""
