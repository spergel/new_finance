#!/usr/bin/env python3
import re, os, csv, logging, requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import defaultdict
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class PFXInvestment:
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


class PFXExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "PFX") -> Dict:
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
        return self.extract_from_url(txt_url, "Phenixfin_Corp", cik)

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
        invs: List[PFXInvestment] = []
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
        out_file = os.path.join(out_dir, 'PFX_Phenixfin_Corp_investments.csv')
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
            # Prefer industry from identifier parsing over XBRL explicit member
            industry = parsed.get('industry') or same
            if industry == 'Unknown':
                industry = same
            res.append({'id':cid,'investment_identifier':ident,'company_name':parsed['company_name'],'industry':industry,'investment_type':parsed['investment_type'],'instant':inst.group(1) if inst else None,'start_date':sd.group(1) if sd else None,'end_date':ed.group(1) if ed else None})
        return res

    def _parse_identifier(self, identifier: str) -> Dict[str,str]:
        res={'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        if not identifier or identifier.strip() == '':
            return res
        
        identifier = identifier.strip()
        
        # Extract industry if present (usually at the end after a dash, like " - Real Estate" or " - Business")
        # Match industry patterns that come after the company name and investment type
        industry_patterns = [
            r'\s*-\s*(Real\s+Estate|Business|Consumer|Banking\s+&\s+Finance|Automotive|Construction\s+&\s+Building|Metals\s+&\s+Mining|Consumer\s+Discretionary|Aerospace\s+&\s+Defense|Broadcasting\s+&\s+Subscription)$',
        ]
        for pattern in industry_patterns:
            match = re.search(pattern, identifier, re.IGNORECASE)
            if match:
                industry = match.group(1).strip()
                res['industry'] = industry
                identifier = identifier[:match.start()].strip()  # Remove industry from identifier
                break
        
        # PFX format: "Company Name - Investment Type" or "Company Name, Investment Type"
        # Also handles: "Affiliated Investments-Company Name-Investment Type"
        
        # Remove common prefixes like "Non-Controlled/Non-Affiliated Investments -" or "Controlled Investments -"
        prefix_patterns = [
            r'^Non-Controlled/Non-Affiliated\s+Investments\s*-\s*',
            r'^Controlled\s+Investments\s*-\s*',
            r'^Affiliated\s+Investments\s*-\s*',
        ]
        for pattern in prefix_patterns:
            identifier = re.sub(pattern, '', identifier, flags=re.IGNORECASE).strip()
        
        # First, try to split on common separators
        # Check for patterns like "Company - Investment Type" or "Company, Investment Type"
        # Also handle "Affiliated Investments-Company Name-Investment Type" or "Controlled Investments-Company Name-Investment Type"
        if ' - ' in identifier:
            parts = identifier.split(' - ')
            if len(parts) >= 2:
                # Check if first part is a prefix like "Affiliated Investments" or "Controlled Investments"
                first_part = parts[0].strip()
                is_prefix = first_part.lower() in ['affiliated investments', 'controlled investments']
                
                if is_prefix and len(parts) >= 3:
                    # Format: "Affiliated Investments - Company Name - Investment Type"
                    company = parts[1].strip()  # Middle part is the actual company
                    inv_type = parts[-1].strip()
                else:
                    # Format: "Company Name - Investment Type"
                    # Check if last part is an investment type
                    last_part = parts[-1].strip()
                    if self._looks_like_investment_type(last_part):
                        company = ' - '.join(parts[:-1]).strip()
                        inv_type = last_part
                    else:
                        # Last part might be part of company name
                        company = ' - '.join(parts).strip()
                        inv_type = 'Unknown'
                
                res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
                res['investment_type'] = self._extract_investment_type_from_string(inv_type)
                return res
        elif '-' in identifier and ' - ' not in identifier:
            # Handle single dashes (no spaces): "Company-Investment Type"
            parts = identifier.split('-')
            if len(parts) >= 2:
                # Check if first part is a prefix
                first_part = parts[0].strip()
                is_prefix = first_part.lower() in ['affiliated investments', 'controlled investments']
                
                if is_prefix and len(parts) >= 3:
                    # Format: "Affiliated Investments-Company Name-Investment Type"
                    company = parts[1].strip()
                    inv_type = '-'.join(parts[2:]).strip()  # Join remaining parts as investment type
                else:
                    # Format: "Company-Investment Type"
                    # Try to find where investment type starts by matching patterns
                    inv_type_match = None
                    for i in range(1, len(parts)):
                        candidate = '-'.join(parts[i:])
                        if any(re.search(p, candidate, re.IGNORECASE) for p in [
                            r'First\s+Lien', r'Senior\s+Secured', r'Equity', r'Term\s+Loan', r'Revolving'
                        ]):
                            company = '-'.join(parts[:i]).strip()
                            inv_type = candidate
                            inv_type_match = True
                            break
                    
                    if not inv_type_match:
                        # Default: last part is investment type
                        company = '-'.join(parts[:-1]).strip()
                        inv_type = parts[-1].strip()
                
                res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
                res['investment_type'] = self._extract_investment_type_from_string(inv_type)
                return res
        elif ',' in identifier:
            # Try splitting on comma
            last_comma = identifier.rfind(',')
            company = identifier[:last_comma].strip()
            tail = identifier[last_comma+1:].strip()
            res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
            res['investment_type'] = self._extract_investment_type_from_string(tail)
            return res
        
        # If no clear separator, try to extract investment type from the end
        # Common patterns in PFX identifiers
        inv_type_patterns = [
            r'First\s+Lien\s+(?:Delayed\s+Draw\s+)?(?:Term\s+Loan\s*[A-Z]?|Super\s+Priority\s+(?:Delayed\s+Draw\s+)?Term\s+Loan)',
            r'Second\s+Lien\s+.*$',
            r'Unitranche\s*\d*$',
            r'Senior\s+Secured\s+(?:Revolving\s+Note|Term\s+Loan\s*[A-Z]?|Promissory\s+Note)',
            r'Secured\s+Debt\s*\d*$',
            r'Unsecured\s+Debt\s*\d*$',
            r'Preferred\s+Equity$',
            r'Preferred\s+Stock$',
            r'Common\s+Equity$',
            r'Common\s+Stock\s*\d*$',
            r'Member\s+Units\s*\d*$',
            r'Equity\s+Interest$',
            r'Equity$',
            r'Warrants?$',
            r'Revolving\s+Note',
            r'Term\s+Loan\s*[A-Z]?',
        ]
        
        for pattern in inv_type_patterns:
            match = re.search(pattern, identifier, re.IGNORECASE)
            if match:
                inv_type = match.group(0).strip()
                company = identifier[:match.start()].strip()
                # Clean up company name - remove trailing dashes, commas, etc.
                company = re.sub(r'[-\s,]+$', '', company).strip()
                res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
                res['investment_type'] = self._extract_investment_type_from_string(inv_type)
                return res
        
        # If no investment type found, use the whole identifier as company name
        res['company_name'] = re.sub(r'\s+',' ', identifier).rstrip(',')
        return res
    
    def _looks_like_investment_type(self, s: str) -> bool:
        """Check if a string looks like an investment type."""
        if not s:
            return False
        s_lower = s.lower()
        investment_type_keywords = [
            'equity', 'term loan', 'first lien', 'senior secured', 'revolving',
            'warrant', 'preferred', 'common', 'note', 'debt', 'secured', 'unsecured'
        ]
        return any(keyword in s_lower for keyword in investment_type_keywords)
    
    def _extract_investment_type_from_string(self, s: str) -> str:
        """Extract and standardize investment type from a string."""
        if not s:
            return "Unknown"
        
        s = s.strip()
        
        # Map common variations to standard types
        s_lower = s.lower()
        
        # Term Loans
        if 'term loan' in s_lower:
            if 'term loan a' in s_lower or 'term a loan' in s_lower:
                return "Term Loan A"
            elif 'term loan b' in s_lower or 'term b loan' in s_lower:
                return "Term Loan B"
            elif 'term loan c' in s_lower or 'term c loan' in s_lower:
                return "Term Loan C"
            elif 'delayed draw' in s_lower:
                return "Term Loan"
            elif 'super priority' in s_lower:
                return "Term Loan"
            else:
                return "Term Loan"
        
        # First Lien
        if 'first lien' in s_lower:
            if 'term loan' in s_lower:
                if 'delayed draw' in s_lower:
                    return "First Lien Term Loan"
                elif 'super priority' in s_lower:
                    return "First Lien Term Loan"
                else:
                    return "First Lien Term Loan"
            else:
                return "First Lien"
        
        # Senior Secured
        if 'senior secured' in s_lower:
            if 'revolving' in s_lower or 'revolver' in s_lower:
                return "Revolver"
            elif 'term loan' in s_lower:
                return "Term Loan"
            elif 'promissory note' in s_lower:
                return "Senior Secured Note"
            else:
                return "Senior Secured"
        
        # Equity types
        if 'preferred equity' in s_lower or 'preferred stock' in s_lower:
            return "Preferred Equity"
        if 'common equity' in s_lower or 'common stock' in s_lower:
            return "Common Equity"
        if 'equity interest' in s_lower or (s_lower == 'equity' and 'preferred' not in s_lower):
            return "Common Equity"
        
        # Revolving
        if 'revolving' in s_lower or 'revolver' in s_lower:
            return "Revolver"
        
        # Warrants
        if 'warrant' in s_lower:
            return "Warrants"
        
        # Return cleaned version
        return re.sub(r'\s+', ' ', s).strip()

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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[PFXInvestment]:
        if context['company_name']=='Unknown': return None
        
        # Clean company name - remove investment type suffixes if they're still embedded
        company_name = context['company_name']
        inv_type = context['investment_type']
        
        # If investment type is still in company name, try to remove it
        if inv_type != 'Unknown' and inv_type.lower() in company_name.lower():
            # Try to remove the investment type from the end of company name
            pattern = r'\s*[-,\s]+\s*' + re.escape(inv_type) + r'\s*$'
            company_name = re.sub(pattern, '', company_name, flags=re.IGNORECASE).strip()
        
        # Also clean common patterns like "- Equity", "- Senior Secured", etc.
        company_name = re.sub(r'\s*[-,\s]+\s*(Equity|Senior\s+Secured|First\s+Lien|Term\s+Loan.*?|Revolving\s+Note.*?)$', '', company_name, flags=re.IGNORECASE).strip()
        
        # Remove industry suffixes that might still be in company name
        # Match with or without HTML entities like &amp;
        industry_suffixes = [
            r'\s*-\s*Real\s+Estate',
            r'\s*-\s*Business',
            r'\s*-\s*Consumer(?:\s+Discretionary)?',
            r'\s*-\s*Banking(?:\s*&\s*Finance)?',
            r'\s*-\s*Automotive',
            r'\s*-\s*Construction\s*&\s*Building',
            r'\s*-\s*Metals\s*&\s*Mining',
            r'\s*-\s*Consumer\s+Discretionary',
            r'\s*-\s*Aerospace\s*&\s*Defense',
            r'\s*-\s*Broadcasting\s*&\s*Subscription',
        ]
        for pattern in industry_suffixes:
            company_name = re.sub(pattern + r'$', '', company_name, flags=re.IGNORECASE).strip()
            # Also handle HTML entities
            company_name = re.sub(pattern.replace('&', r'&amp;') + r'$', '', company_name, flags=re.IGNORECASE).strip()
        
        # Remove any remaining " - Banking" or " - Business" patterns (more general)
        # This catches patterns like " - Banking - Fund Investment" or " - High Tech Industries"
        company_name = re.sub(r'\s*-\s*(Banking|Business|Consumer|Real\s+Estate|Automotive|Construction|Metals|Aerospace|Broadcasting|High\s+Tech\s+Industries)(?:\s*-\s*.*)?$', '', company_name, flags=re.IGNORECASE).strip()
        
        # Remove any remaining " - [Industry-like text]" patterns
        # Common industry-like suffixes that might appear
        industry_like_patterns = [
            r'\s*-\s*High\s+Tech\s+Industries$',
            r'\s*-\s*Fund\s+Investment$',
            r'\s*-\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*-\s*Fund\s+Investment$',  # " - Industry - Fund Investment"
        ]
        for pattern in industry_like_patterns:
            company_name = re.sub(pattern, '', company_name, flags=re.IGNORECASE).strip()
        
        # Remove trailing dashes and commas
        company_name = re.sub(r'[-\s,]+$', '', company_name).strip()
        
        # Clean up any remaining HTML entities in company name
        company_name = company_name.replace('&amp;', '&')
        
        # Fix cases where company name got split incorrectly (e.g., "Advocates for Disabled Vets" with "LLC (dba Reps for Vets)" as investment type)
        if inv_type and inv_type != 'Unknown':
            # If investment type looks like part of a company name (contains "LLC", "Inc", etc.), merge it back
            if re.search(r'\b(LLC|Inc\.?|Corp\.?|L\.P\.?|LP)\b', inv_type, re.IGNORECASE):
                company_name = f"{company_name} {inv_type}".strip()
                inv_type = 'Unknown'  # Will be inferred later
        
        # Infer investment type if still Unknown
        if inv_type == 'Unknown':
            inv_type = self._infer_investment_type(company_name, facts)
        
        inv=PFXInvestment(company_name=company_name,investment_type=inv_type,industry=context['industry'],context_ref=context['id'])
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
    
    def _infer_investment_type(self, company_name: str, facts: List[Dict]) -> str:
        """Infer investment type from facts when it's Unknown."""
        # Check for shares/units - indicates equity
        for f in facts:
            c = f.get('concept', '').lower()
            if any(k in c for k in ['numberofshares', 'sharesoutstanding', 'unitsoutstanding', 'sharesheld', 'unitsheld']):
                # Check if there's an interest rate - if yes, might be preferred equity
                has_interest = any('interestrate' in fact.get('concept', '').lower() for fact in facts)
                if has_interest:
                    return "Preferred Equity"
                return "Common Equity"
        
        # Check if there's principal amount but no interest rate - might be equity
        has_principal = any('principalamount' in f.get('concept', '').lower() or 'outstandingprincipal' in f.get('concept', '').lower() for f in facts)
        has_interest = any('interestrate' in f.get('concept', '').lower() for f in facts)
        
        if has_principal and not has_interest:
            # Has principal but no interest - likely equity
            return "Common Equity"
        
        # Check company name for hints
        company_lower = company_name.lower()
        if 'equity' in company_lower:
            if 'preferred' in company_lower:
                return "Preferred Equity"
            return "Common Equity"
        
        # Default to Unknown if we can't infer
        return "Unknown"

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
    ex=PFXExtractor()
    try:
        res=ex.extract_from_ticker('PFX')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





    main()




