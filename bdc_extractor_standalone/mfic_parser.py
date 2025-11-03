#!/usr/bin/env python3
"""
MFIC (Midcap Financial Investment Corp) Investment Extractor
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
class MFICInvestment:
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


class MFICExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "MFIC") -> Dict:
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
        return self.extract_from_url(txt_url, "Midcap_Financial_Investment_Corp", cik)

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
        investments: List[MFICInvestment] = []
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
        out_file = os.path.join(out_dir, 'MFIC_Midcap_Financial_Investment_Corp_investments.csv')
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
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        # Remove numeric-only parenthetical footnote markers
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        # Also handle cases where footnotes might have trailing spaces before them
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        # Clean up any double spaces and normalize
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None,
               'maturity_date': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # MFIC format: "Industry Company Name [Business Name] Investment Type [Rate Info]"
        # Examples:
        # "Leisure Products LashCo Lash OpCo, LLC First Lien Secured Debt"
        # "Financial Services Definiti LLC RHI Acquisition LLC First Lien Secured Debt"
        # "Health Care Providers & Services Thomas Scientific Thomas Scientific, LLC First Lien Secured Debt"
        
        # Extract investment type first (remove it to get company name)
        inv_type_patterns = [
            r'\s+First\s+Lien\s+Secured\s+Debt(?:\s*[\-\u2013]\s*(Revolver|Term\s+Loan|Delayed\s+Draw))?',
            r'\s+Second\s+Lien\s+.*?(?:Debt|Loan)',
            r'\s+Common\s+Equity',
            r'\s+Preferred\s+Equity',
            r'\s+Preferred\s+Stock',
            r'\s+Common\s+Stock',
            r'\s+Warrants?',
            r'\s+Unitranche',
            r'\s+Subordinated\s+Debt',
            r'\s+Senior\s+Subordinated\s+Term\s+Loan'
        ]
        
        it_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, ident_clean, re.IGNORECASE)
            if match:
                it_match = match
                it_text = match.group(0).strip()
                # Normalize
                it_text = re.sub(r'\s+[\-\u2013]\s+', ' - ', it_text)
                res['investment_type'] = it_text
                break
        
        # Remove investment type from identifier
        if it_match:
            before_inv = ident_clean[:it_match.start()].strip()
        else:
            before_inv = ident_clean
        
        # Extract industry - common industry names that appear at the start
        # Look for industry patterns at the beginning
        industry_patterns = [
            r'^(Leisure\s+Products|Financial\s+Services|Containers\s+&\s*Packaging|Ground\s+Transportation|'
            r'Diversified\s+Consumer\s+Services|Health\s+Care\s+Providers\s*&\s*Services|'
            r'Trading\s+Companies\s*&\s*Distributors|Commercial\s+Services\s*&\s*Supplies|'
            r'Professional\s+Services|Software|Automobile\s+Components|Personal\s+Care\s+Products|'
            r'Food\s+Products|Energy\s+Equipment\s*&\s*Services|Aerospace\s+&\s*Defense|'
            r'Electronic\s+Equipment|Instruments\s+and\s+Components)\s+',
        ]
        
        industry_match = None
        for pattern in industry_patterns:
            match = re.match(pattern, before_inv, re.IGNORECASE)
            if match:
                industry_match = match
                res['industry'] = match.group(1).strip()
                break
        
        # Remove industry from before_inv
        if industry_match:
            company_part = before_inv[industry_match.end():].strip()
            # Also handle cases where industry might still be present (like "Health Care Providers & Services")
            # Remove it again if it appears
            remaining_industry_match = re.match(r'^(Health\s+Care\s+Providers|Trading\s+Companies|Commercial\s+Services|Energy\s+Equipment)\s+&\s+Services\s+', company_part, re.IGNORECASE)
            if remaining_industry_match:
                company_part = company_part[remaining_industry_match.end():].strip()
        else:
            company_part = before_inv
        
        # Extract company name - usually ends with LLC, Inc., Corp, LP, etc.
        # Company name is typically the last entity name (LLC/Inc/Corp)
        # Handle cases like "Definiti LLC RHI Acquisition LLC" -> take "RHI Acquisition LLC"
        # Or "Thomas Scientific Thomas Scientific, LLC" -> take "Thomas Scientific, LLC"
        
        # Find all entities with their full names including entity type
        # Use a more specific pattern to match entity names
        entity_pattern = r'([A-Z][A-Za-z0-9\s&,\-\.]{2,}?)\s+(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co)(?:\s|$)'
        entities = []
        for match in re.finditer(entity_pattern, company_part, re.IGNORECASE):
            entity_name = match.group(1).strip()
            entity_type = match.group(2)
            full_entity = f"{entity_name} {entity_type}"
            entities.append((full_entity, match.start(), match.end(), entity_name, entity_type))
        
        if entities:
            # Take the last entity (most likely the actual company)
            last_entity_full, start_pos, end_pos, last_entity_name, last_entity_type = entities[-1]
            
            # Handle f/k/a cases in the entity name itself
            if 'f/k/a' in last_entity_name or 'fka' in last_entity_name:
                # Extract just the main company name before f/k/a
                fka_match = re.search(r'([^(]+?)\s*(?:\(|f/k/a|fka)', last_entity_name, re.IGNORECASE)
                if fka_match:
                    last_entity_name = fka_match.group(1).strip()
                    last_entity_full = f"{last_entity_name} {last_entity_type}"
            
            # Clean up company name - handle duplicates and unwanted prefixes
            # Check the ORIGINAL company_part text for duplicates, not the extracted entity
            company_part_lower = company_part.lower()
            entity_name_lower = last_entity_name.lower()
            
            # Count how many times the entity name appears in the original text (as whole words)
            entity_words = entity_name_lower.split()
            company_name_clean = last_entity_full
            
            if len(entity_words) > 0:
                # Try to find entity name as a phrase in the original company_part
                pattern = r'\b' + re.escape(entity_name_lower) + r'\b'
                matches = list(re.finditer(pattern, company_part_lower))
                
                if len(matches) > 1:
                    # Entity name appears more than once in original - take just the entity name + type
                    company_name_clean = f"{last_entity_name} {last_entity_type}"
                elif len(matches) == 1:
                    # Entity name appears once - check if there's unwanted prefix before it
                    match_start = matches[0].start()
                    if match_start > 0:
                        prefix_before = company_part_lower[:match_start].strip()
                        # Check if prefix contains common descriptors or duplicate-like patterns
                        common_prefix_words = ['services', 'distributors', 'packaging', 'supplies', 'solutions', 'banner', 'health', 'care', 'providers']
                        prefix_words = prefix_before.split()
                        # If prefix has 2+ words or contains common descriptors, it's likely unwanted
                        if len(prefix_words) >= 2 or any(word in prefix_words for word in common_prefix_words):
                            # Also check if prefix ends with same word(s) as entity name (partial duplicate)
                            if prefix_words and prefix_words[-1] in entity_words:
                                company_name_clean = f"{last_entity_name} {last_entity_type}"
            
            # Remove unwanted prefixes that are clearly business descriptors
            unwanted_prefixes = ['Services', 'Distributors', 'Packaging', 'Supplies']
            for prefix in unwanted_prefixes:
                if company_name_clean.lower().startswith(prefix.lower() + ' '):
                    # Check if there's actual company content after
                    remainder = company_name_clean[len(prefix):].strip()
                    if remainder and len(remainder) > 5:
                        company_name_clean = remainder
            
            # Also handle cases where industry prefix leaked in (like "Health Care Providers & Services")
            # Check if company name starts with an industry name
            industry_prefixes_in_name = [
                r'^Health\s+Care\s+Providers\s*&\s*Services\s+',
                r'^Trading\s+Companies\s*&\s*Distributors\s+',
                r'^Commercial\s+Services\s*&\s*Supplies\s+',
                r'^Energy\s+Equipment\s*&\s*Services\s+'
            ]
            for ip_pattern in industry_prefixes_in_name:
                match = re.match(ip_pattern, company_name_clean, re.IGNORECASE)
                if match:
                    # Remove industry prefix
                    company_name_clean = re.sub(ip_pattern, '', company_name_clean, flags=re.IGNORECASE).strip()
                    # If after removing, we still have an entity name, use it
                    # Otherwise, we might have lost the company name entirely
                    entity_match_after = re.search(entity_pattern, company_name_clean, re.IGNORECASE)
                    if entity_match_after:
                        company_name_clean = f"{entity_match_after.group(1).strip()} {entity_match_after.group(2)}"
                    break
            
            res['company_name'] = self._strip_footnote_refs(company_name_clean)
            
            # Extract business description if it exists (the part before the company name)
            business_part_raw = company_part[:start_pos].strip()
            # Remove any duplicate entity names from business description
            for entity_full, _, _, _, _ in entities[:-1]:  # All except the last one
                if entity_full in business_part_raw:
                    business_part_raw = business_part_raw.replace(entity_full, '').strip()
            # Also remove the entity name itself if it appears earlier (for duplicates)
            if last_entity_name in business_part_raw and len(entities) == 1:
                business_part_raw = business_part_raw.replace(last_entity_name, '').strip()
            # Clean up business description - remove common prefixes
            business_part_raw = re.sub(r'^(Services|Distributors|Packaging)\s+', '', business_part_raw, flags=re.IGNORECASE)
            if business_part_raw and len(business_part_raw) > 3:
                res['business_description'] = self._strip_footnote_refs(business_part_raw)
        else:
            # Fallback: look for any recognizable company pattern
            # Try to find just a company name pattern even without clear entity type
            fallback_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.]+(?:Holdco|Holdings|Buyer|Acquisition|Parent|Opco|OpCo|Sub))', company_part, re.IGNORECASE)
            if fallback_match:
                res['company_name'] = self._strip_footnote_refs(fallback_match.group(1).strip())
            else:
                # Last resort: use the company_part as company name
                res['company_name'] = self._strip_footnote_refs(company_part)
        
        if ',' in identifier:
            last = identifier.rfind(',')
            company = identifier[:last].strip()
            tail = identifier[last+1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        # Extract embedded tokens (SOFR/LIBOR + bps, Floor %, PIK %, Maturity Date)
        tokens_text = identifier
        # Reference rate + spread (allow formats like SOFR+475 or SOFR + 4.75%)
        rr = re.search(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', tokens_text, re.IGNORECASE)
        if rr:
            rate = rr.group(1).upper().replace('  ', ' ').replace('BASE RATE', 'BASE RATE')
            spread_raw = rr.group(2)
            try:
                sv = float(spread_raw)
                # If looks like bps (e.g., 575), convert to percent; if already percent like 5.75, keep
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            res['reference_rate'] = rate
            res['spread'] = self._percent(str(sv))
        # Floor: allow both "1.00% Floor" and "Floor 1.00%"
        fl = re.search(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', tokens_text, re.IGNORECASE)
        if fl:
            floor_val = fl.group(1) or fl.group(2)
            res['floor_rate'] = self._percent(floor_val)
        # PIK: "Cash plus 5.10% PIK" or just "PIK 5.10%"
        pk = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', tokens_text, re.IGNORECASE)
        if pk:
            pik_val = pk.group(1) or pk.group(2)
            res['pik_rate'] = self._percent(pik_val)
        # Maturity Date mm/dd/yy or yyyy
        md = re.search(r'Maturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})', tokens_text, re.IGNORECASE)
        if md:
            res['maturity_date'] = md.group(1)

        # If we didn't find investment type above, try from tail
        if res['investment_type'] == 'Unknown' and tail:
            patterns = [
                r'First\s+Lien\s+Secured\s+Debt\s*(?:\-\s*(Revolver|Term\s+Loan|Delayed\s+Draw))?',
                r'First\s+Lien\s+Senior\s+Secured\s+(?:Term\s+Loan|Loan|Revolver)',
                r'Second\s+Lien\s+.*?(?:Debt|Loan)',
                r'Unitranche\s*(?:Loan)?',
                r'Subordinated\s+Debt',
                r'Senior\s+Subordinated\s+Term\s+Loan',
                r'Preferred\s+Equity', r'Preferred\s+Stock',
                r'Common\s+Equity', r'Common\s+Stock',
                r'Warrants?'
            ]
            for p in patterns:
                mm = re.search(p, tail, re.IGNORECASE)
                if mm:
                    it = mm.group(0)
                    res['investment_type'] = re.sub(r'\s+', ' ', it).strip()
                    break
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[MFICInvestment]:
        if context['company_name']=='Unknown':
            return None
        # Initial investment object
        inv = MFICInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        # Secondary pass: extract tokens from the raw identifier (contains all tokens)
        # Only extract tokens, don't overwrite the carefully parsed company name
        raw_text = context.get('raw_identifier') or inv.company_name
        _, tkns = self._extract_tokens_from_text(raw_text)
        # Don't overwrite parsed company name - trust _parse_identifier
        # The parsed name should already be clean
        # Only set from tokens if not already present from facts later
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
        # Fill missing fields from parsed tokens
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
        # Normalize a numeric or string to a percent string without scaling assumptions
        # Accept '1.5', '1', '1.50', or already percent-like strings
        raw = str(s).strip()
        if raw.endswith('%'):
            raw = raw[:-1].strip()
        try:
            v = float(raw)
        except:
            return f"{s}%"
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

    def _extract_tokens_from_text(self, text: str) -> (str, Dict[str, Optional[str]]):
        """Extract tokens like SOFR/LIBOR + spread, Floor %, PIK %, and Maturity Date
        from a free-form text and return a cleaned name and token dict.
        """
        tokens: Dict[str, Optional[str]] = {'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None, 'maturity_date': None}
        original = text
        # Reference rate + spread
        def rr_repl(m):
            rate = m.group(1).upper().replace('  ', ' ').replace('BASE RATE', 'BASE RATE')
            spread_raw = m.group(2)
            try:
                sv = float(spread_raw)
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            tokens['reference_rate'] = rate
            tokens['spread'] = self._percent(str(sv))
            return ''
        text = re.sub(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', rr_repl, text, flags=re.IGNORECASE)
        # Floor
        def floor_repl(m):
            v = m.group(1) or m.group(2)
            tokens['floor_rate'] = self._percent(v)
            return ''
        text = re.sub(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', floor_repl, text, flags=re.IGNORECASE)
        # PIK
        def pik_repl(m):
            v = m.group(1) or m.group(2)
            tokens['pik_rate'] = self._percent(v)
            return ''
        text = re.sub(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', pik_repl, text, flags=re.IGNORECASE)
        # Maturity Date
        def md_repl(m):
            tokens['maturity_date'] = m.group(1)
            return ''
        text = re.sub(r'\bMaturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})\b', md_repl, text, flags=re.IGNORECASE)
        # Remove trailing loan descriptors after dash
        text = re.sub(r'\s+[\-\u2013]\s+.*$', '', text).strip()
        # Normalize whitespace and stray punctuation
        text = re.sub(r'\s+', ' ', text).strip().rstrip(',')
        cleaned = text if text else original
        return cleaned, tokens

    def _format_spread(self, s: str) -> str:
        raw = str(s).strip().rstrip('%')
        try:
            v = float(raw)
        except:
            return self._percent(s)
        # If looks like a fraction (0.0275), scale to 2.75
        if v < 1:
            v *= 100.0
        # If looks like bps (275), scale to 2.75
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


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=MFICExtractor()
    try:
        res=ex.extract_from_ticker('MFIC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





MFIC (Midcap Financial Investment Corp) Investment Extractor
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
class MFICInvestment:
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


class MFICExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "MFIC") -> Dict:
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
        return self.extract_from_url(txt_url, "Midcap_Financial_Investment_Corp", cik)

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
        investments: List[MFICInvestment] = []
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
        out_file = os.path.join(out_dir, 'MFIC_Midcap_Financial_Investment_Corp_investments.csv')
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
                'instant': inst.group(1) if inst else None,
                'start_date': sd.group(1) if sd else None,
                'end_date': ed.group(1) if ed else None,
            })
        return contexts

    def _strip_footnote_refs(self, text: str) -> str:
        """Remove numeric-only parenthetical footnote markers like (5) (10)"""
        if not text:
            return ""
        # Remove numeric-only parenthetical footnote markers
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        # Also handle cases where footnotes might have trailing spaces before them
        cleaned = re.sub(r"\s+\(\s*\d+\s*\)", "", cleaned)
        # Clean up any double spaces and normalize
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    def _parse_identifier(self, identifier: str) -> Dict[str, str]:
        res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown',
               'business_description': None,
               'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None,
               'maturity_date': None}
        
        ident_clean = self._strip_footnote_refs(identifier)
        
        # MFIC format: "Industry Company Name [Business Name] Investment Type [Rate Info]"
        # Examples:
        # "Leisure Products LashCo Lash OpCo, LLC First Lien Secured Debt"
        # "Financial Services Definiti LLC RHI Acquisition LLC First Lien Secured Debt"
        # "Health Care Providers & Services Thomas Scientific Thomas Scientific, LLC First Lien Secured Debt"
        
        # Extract investment type first (remove it to get company name)
        inv_type_patterns = [
            r'\s+First\s+Lien\s+Secured\s+Debt(?:\s*[\-\u2013]\s*(Revolver|Term\s+Loan|Delayed\s+Draw))?',
            r'\s+Second\s+Lien\s+.*?(?:Debt|Loan)',
            r'\s+Common\s+Equity',
            r'\s+Preferred\s+Equity',
            r'\s+Preferred\s+Stock',
            r'\s+Common\s+Stock',
            r'\s+Warrants?',
            r'\s+Unitranche',
            r'\s+Subordinated\s+Debt',
            r'\s+Senior\s+Subordinated\s+Term\s+Loan'
        ]
        
        it_match = None
        for pattern in inv_type_patterns:
            match = re.search(pattern, ident_clean, re.IGNORECASE)
            if match:
                it_match = match
                it_text = match.group(0).strip()
                # Normalize
                it_text = re.sub(r'\s+[\-\u2013]\s+', ' - ', it_text)
                res['investment_type'] = it_text
                break
        
        # Remove investment type from identifier
        if it_match:
            before_inv = ident_clean[:it_match.start()].strip()
        else:
            before_inv = ident_clean
        
        # Extract industry - common industry names that appear at the start
        # Look for industry patterns at the beginning
        industry_patterns = [
            r'^(Leisure\s+Products|Financial\s+Services|Containers\s+&\s*Packaging|Ground\s+Transportation|'
            r'Diversified\s+Consumer\s+Services|Health\s+Care\s+Providers\s*&\s*Services|'
            r'Trading\s+Companies\s*&\s*Distributors|Commercial\s+Services\s*&\s*Supplies|'
            r'Professional\s+Services|Software|Automobile\s+Components|Personal\s+Care\s+Products|'
            r'Food\s+Products|Energy\s+Equipment\s*&\s*Services|Aerospace\s+&\s*Defense|'
            r'Electronic\s+Equipment|Instruments\s+and\s+Components)\s+',
        ]
        
        industry_match = None
        for pattern in industry_patterns:
            match = re.match(pattern, before_inv, re.IGNORECASE)
            if match:
                industry_match = match
                res['industry'] = match.group(1).strip()
                break
        
        # Remove industry from before_inv
        if industry_match:
            company_part = before_inv[industry_match.end():].strip()
            # Also handle cases where industry might still be present (like "Health Care Providers & Services")
            # Remove it again if it appears
            remaining_industry_match = re.match(r'^(Health\s+Care\s+Providers|Trading\s+Companies|Commercial\s+Services|Energy\s+Equipment)\s+&\s+Services\s+', company_part, re.IGNORECASE)
            if remaining_industry_match:
                company_part = company_part[remaining_industry_match.end():].strip()
        else:
            company_part = before_inv
        
        # Extract company name - usually ends with LLC, Inc., Corp, LP, etc.
        # Company name is typically the last entity name (LLC/Inc/Corp)
        # Handle cases like "Definiti LLC RHI Acquisition LLC" -> take "RHI Acquisition LLC"
        # Or "Thomas Scientific Thomas Scientific, LLC" -> take "Thomas Scientific, LLC"
        
        # Find all entities with their full names including entity type
        # Use a more specific pattern to match entity names
        entity_pattern = r'([A-Z][A-Za-z0-9\s&,\-\.]{2,}?)\s+(LLC|Inc\.|Inc|Corp\.|Corp|LP|L\.P\.|LLP|Ltd\.|Limited|Holdings|Holdco|Holdco\.|Company|Co\.|Co)(?:\s|$)'
        entities = []
        for match in re.finditer(entity_pattern, company_part, re.IGNORECASE):
            entity_name = match.group(1).strip()
            entity_type = match.group(2)
            full_entity = f"{entity_name} {entity_type}"
            entities.append((full_entity, match.start(), match.end(), entity_name, entity_type))
        
        if entities:
            # Take the last entity (most likely the actual company)
            last_entity_full, start_pos, end_pos, last_entity_name, last_entity_type = entities[-1]
            
            # Handle f/k/a cases in the entity name itself
            if 'f/k/a' in last_entity_name or 'fka' in last_entity_name:
                # Extract just the main company name before f/k/a
                fka_match = re.search(r'([^(]+?)\s*(?:\(|f/k/a|fka)', last_entity_name, re.IGNORECASE)
                if fka_match:
                    last_entity_name = fka_match.group(1).strip()
                    last_entity_full = f"{last_entity_name} {last_entity_type}"
            
            # Clean up company name - handle duplicates and unwanted prefixes
            # Check the ORIGINAL company_part text for duplicates, not the extracted entity
            company_part_lower = company_part.lower()
            entity_name_lower = last_entity_name.lower()
            
            # Count how many times the entity name appears in the original text (as whole words)
            entity_words = entity_name_lower.split()
            company_name_clean = last_entity_full
            
            if len(entity_words) > 0:
                # Try to find entity name as a phrase in the original company_part
                pattern = r'\b' + re.escape(entity_name_lower) + r'\b'
                matches = list(re.finditer(pattern, company_part_lower))
                
                if len(matches) > 1:
                    # Entity name appears more than once in original - take just the entity name + type
                    company_name_clean = f"{last_entity_name} {last_entity_type}"
                elif len(matches) == 1:
                    # Entity name appears once - check if there's unwanted prefix before it
                    match_start = matches[0].start()
                    if match_start > 0:
                        prefix_before = company_part_lower[:match_start].strip()
                        # Check if prefix contains common descriptors or duplicate-like patterns
                        common_prefix_words = ['services', 'distributors', 'packaging', 'supplies', 'solutions', 'banner', 'health', 'care', 'providers']
                        prefix_words = prefix_before.split()
                        # If prefix has 2+ words or contains common descriptors, it's likely unwanted
                        if len(prefix_words) >= 2 or any(word in prefix_words for word in common_prefix_words):
                            # Also check if prefix ends with same word(s) as entity name (partial duplicate)
                            if prefix_words and prefix_words[-1] in entity_words:
                                company_name_clean = f"{last_entity_name} {last_entity_type}"
            
            # Remove unwanted prefixes that are clearly business descriptors
            unwanted_prefixes = ['Services', 'Distributors', 'Packaging', 'Supplies']
            for prefix in unwanted_prefixes:
                if company_name_clean.lower().startswith(prefix.lower() + ' '):
                    # Check if there's actual company content after
                    remainder = company_name_clean[len(prefix):].strip()
                    if remainder and len(remainder) > 5:
                        company_name_clean = remainder
            
            # Also handle cases where industry prefix leaked in (like "Health Care Providers & Services")
            # Check if company name starts with an industry name
            industry_prefixes_in_name = [
                r'^Health\s+Care\s+Providers\s*&\s*Services\s+',
                r'^Trading\s+Companies\s*&\s*Distributors\s+',
                r'^Commercial\s+Services\s*&\s*Supplies\s+',
                r'^Energy\s+Equipment\s*&\s*Services\s+'
            ]
            for ip_pattern in industry_prefixes_in_name:
                match = re.match(ip_pattern, company_name_clean, re.IGNORECASE)
                if match:
                    # Remove industry prefix
                    company_name_clean = re.sub(ip_pattern, '', company_name_clean, flags=re.IGNORECASE).strip()
                    # If after removing, we still have an entity name, use it
                    # Otherwise, we might have lost the company name entirely
                    entity_match_after = re.search(entity_pattern, company_name_clean, re.IGNORECASE)
                    if entity_match_after:
                        company_name_clean = f"{entity_match_after.group(1).strip()} {entity_match_after.group(2)}"
                    break
            
            res['company_name'] = self._strip_footnote_refs(company_name_clean)
            
            # Extract business description if it exists (the part before the company name)
            business_part_raw = company_part[:start_pos].strip()
            # Remove any duplicate entity names from business description
            for entity_full, _, _, _, _ in entities[:-1]:  # All except the last one
                if entity_full in business_part_raw:
                    business_part_raw = business_part_raw.replace(entity_full, '').strip()
            # Also remove the entity name itself if it appears earlier (for duplicates)
            if last_entity_name in business_part_raw and len(entities) == 1:
                business_part_raw = business_part_raw.replace(last_entity_name, '').strip()
            # Clean up business description - remove common prefixes
            business_part_raw = re.sub(r'^(Services|Distributors|Packaging)\s+', '', business_part_raw, flags=re.IGNORECASE)
            if business_part_raw and len(business_part_raw) > 3:
                res['business_description'] = self._strip_footnote_refs(business_part_raw)
        else:
            # Fallback: look for any recognizable company pattern
            # Try to find just a company name pattern even without clear entity type
            fallback_match = re.search(r'([A-Z][A-Za-z0-9\s&,\-\.]+(?:Holdco|Holdings|Buyer|Acquisition|Parent|Opco|OpCo|Sub))', company_part, re.IGNORECASE)
            if fallback_match:
                res['company_name'] = self._strip_footnote_refs(fallback_match.group(1).strip())
            else:
                # Last resort: use the company_part as company name
                res['company_name'] = self._strip_footnote_refs(company_part)
        
        if ',' in identifier:
            last = identifier.rfind(',')
            company = identifier[:last].strip()
            tail = identifier[last+1:].strip()
        else:
            company = identifier.strip()
            tail = ''
        # Extract embedded tokens (SOFR/LIBOR + bps, Floor %, PIK %, Maturity Date)
        tokens_text = identifier
        # Reference rate + spread (allow formats like SOFR+475 or SOFR + 4.75%)
        rr = re.search(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', tokens_text, re.IGNORECASE)
        if rr:
            rate = rr.group(1).upper().replace('  ', ' ').replace('BASE RATE', 'BASE RATE')
            spread_raw = rr.group(2)
            try:
                sv = float(spread_raw)
                # If looks like bps (e.g., 575), convert to percent; if already percent like 5.75, keep
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            res['reference_rate'] = rate
            res['spread'] = self._percent(str(sv))
        # Floor: allow both "1.00% Floor" and "Floor 1.00%"
        fl = re.search(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', tokens_text, re.IGNORECASE)
        if fl:
            floor_val = fl.group(1) or fl.group(2)
            res['floor_rate'] = self._percent(floor_val)
        # PIK: "Cash plus 5.10% PIK" or just "PIK 5.10%"
        pk = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', tokens_text, re.IGNORECASE)
        if pk:
            pik_val = pk.group(1) or pk.group(2)
            res['pik_rate'] = self._percent(pik_val)
        # Maturity Date mm/dd/yy or yyyy
        md = re.search(r'Maturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})', tokens_text, re.IGNORECASE)
        if md:
            res['maturity_date'] = md.group(1)

        # If we didn't find investment type above, try from tail
        if res['investment_type'] == 'Unknown' and tail:
            patterns = [
                r'First\s+Lien\s+Secured\s+Debt\s*(?:\-\s*(Revolver|Term\s+Loan|Delayed\s+Draw))?',
                r'First\s+Lien\s+Senior\s+Secured\s+(?:Term\s+Loan|Loan|Revolver)',
                r'Second\s+Lien\s+.*?(?:Debt|Loan)',
                r'Unitranche\s*(?:Loan)?',
                r'Subordinated\s+Debt',
                r'Senior\s+Subordinated\s+Term\s+Loan',
                r'Preferred\s+Equity', r'Preferred\s+Stock',
                r'Common\s+Equity', r'Common\s+Stock',
                r'Warrants?'
            ]
            for p in patterns:
                mm = re.search(p, tail, re.IGNORECASE)
                if mm:
                    it = mm.group(0)
                    res['investment_type'] = re.sub(r'\s+', ' ', it).strip()
                    break
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[MFICInvestment]:
        if context['company_name']=='Unknown':
            return None
        # Initial investment object
        inv = MFICInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            business_description=context.get('business_description'),
            context_ref=context['id']
        )
        # Secondary pass: extract tokens from the raw identifier (contains all tokens)
        # Only extract tokens, don't overwrite the carefully parsed company name
        raw_text = context.get('raw_identifier') or inv.company_name
        _, tkns = self._extract_tokens_from_text(raw_text)
        # Don't overwrite parsed company name - trust _parse_identifier
        # The parsed name should already be clean
        # Only set from tokens if not already present from facts later
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
        # Fill missing fields from parsed tokens
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
        # Normalize a numeric or string to a percent string without scaling assumptions
        # Accept '1.5', '1', '1.50', or already percent-like strings
        raw = str(s).strip()
        if raw.endswith('%'):
            raw = raw[:-1].strip()
        try:
            v = float(raw)
        except:
            return f"{s}%"
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

    def _extract_tokens_from_text(self, text: str) -> (str, Dict[str, Optional[str]]):
        """Extract tokens like SOFR/LIBOR + spread, Floor %, PIK %, and Maturity Date
        from a free-form text and return a cleaned name and token dict.
        """
        tokens: Dict[str, Optional[str]] = {'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None, 'maturity_date': None}
        original = text
        # Reference rate + spread
        def rr_repl(m):
            rate = m.group(1).upper().replace('  ', ' ').replace('BASE RATE', 'BASE RATE')
            spread_raw = m.group(2)
            try:
                sv = float(spread_raw)
                if sv > 20:
                    sv = sv / 100.0
            except:
                sv = spread_raw
            tokens['reference_rate'] = rate
            tokens['spread'] = self._percent(str(sv))
            return ''
        text = re.sub(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*([\d\.]+)%?', rr_repl, text, flags=re.IGNORECASE)
        # Floor
        def floor_repl(m):
            v = m.group(1) or m.group(2)
            tokens['floor_rate'] = self._percent(v)
            return ''
        text = re.sub(r'(?:\b([\d\.]+)\s*%\s*Floor\b|\bFloor\b[^\d%]{0,20}([\d\.]+)\s*%)', floor_repl, text, flags=re.IGNORECASE)
        # PIK
        def pik_repl(m):
            v = m.group(1) or m.group(2)
            tokens['pik_rate'] = self._percent(v)
            return ''
        text = re.sub(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%|([\d\.]+)\s*%\s*PIK', pik_repl, text, flags=re.IGNORECASE)
        # Maturity Date
        def md_repl(m):
            tokens['maturity_date'] = m.group(1)
            return ''
        text = re.sub(r'\bMaturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})\b', md_repl, text, flags=re.IGNORECASE)
        # Remove trailing loan descriptors after dash
        text = re.sub(r'\s+[\-\u2013]\s+.*$', '', text).strip()
        # Normalize whitespace and stray punctuation
        text = re.sub(r'\s+', ' ', text).strip().rstrip(',')
        cleaned = text if text else original
        return cleaned, tokens

    def _format_spread(self, s: str) -> str:
        raw = str(s).strip().rstrip('%')
        try:
            v = float(raw)
        except:
            return self._percent(s)
        # If looks like a fraction (0.0275), scale to 2.75
        if v < 1:
            v *= 100.0
        # If looks like bps (275), scale to 2.75
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


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex=MFICExtractor()
    try:
        res=ex.extract_from_ticker('MFIC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()




