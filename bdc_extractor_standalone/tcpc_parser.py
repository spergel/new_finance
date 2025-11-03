#!/usr/bin/env python3
"""
TCPC (Blackrock TCP Capital Corp) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filtering; de-dup; industry enrichment.
"""

import re
import html
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
class TCPCInvestment:
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


class TCPCExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "TCPC") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Blackrock_TCP_Capital_Corp", cik)

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
        investments: List[TCPCInvestment] = []
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
        out_file = os.path.join(out_dir, 'TCPC_Blackrock_TCP_Capital_Corp_investments.csv')
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
        """TCPC identifiers like:
        "Debt Investments IT Services Serrano Parent,Chemicals,,First Lien Term Loan Ref SOFR(S) Floor 1.00% Spread 6.50% Total Coupon 10.71% Maturity 5/13/2030"
        Format: [Prefix] [Industry] [Company Name],[XBRL Industry],,[Investment Type] Ref [Rate] ...
        Parse to extract company, industry, investment type.
        """
        res: Dict[str, Optional[str]] = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        
        # Split on comma - parts are: [main], [industry axis], [], [tail with inv type]
        parts = [p.strip() for p in identifier.split(',')]
        main_part = parts[0] if parts else identifier.strip()
        tail_part = parts[-1] if len(parts) > 1 else ''
        
        # Check for prefix: "Debt Investments" or "Equity Securities"
        prefix_match = re.match(r'^(Debt\s+Investments|Equity\s+Securities)\s+(.+)$', main_part, re.IGNORECASE)
        if prefix_match:
            rest = prefix_match.group(2)
            words = rest.split()
            if words:
                # Industry is typically 1-3 words, company name is the rest
                # Common industry patterns: single words or "X and Y" or "X, Y and Z"
                # Try to find where company name starts by looking for:
                # 1. Entity suffixes (LLC, Inc, Corp, etc.) - company includes this
                # 2. Company name patterns (capitalized words that aren't common industry words)
                
                # List of common industry words (used to identify industry vs company)
                common_industry_indicators = {
                    'services', 'service', 'capital', 'markets', 'consumer', 'finance',
                    'financial', 'software', 'media', 'diversified', 'professional',
                    'building', 'products', 'construction', 'engineering', 'internet'
                }
                
                # Find entity suffix positions
                entity_positions = []
                for i, word in enumerate(words):
                    if re.search(r'\b(LLC|Inc\.?|Corp\.?|LP|Holdings?|Companies?|B\.V\.?|Ltd\.?|Corporation)\b', word, re.IGNORECASE):
                        entity_positions.append(i)
                
                # If we find an entity suffix, company name likely starts before it
                if entity_positions:
                    # Company includes entity suffix, so start a bit before
                    entity_pos = entity_positions[0]
                    # Look backwards for company name start (usually 1-3 words before entity)
                    company_start = max(0, entity_pos - 2)
                    # But don't split too early - ensure at least 1 word for industry
                    if company_start == 0 and len(words) > 1:
                        company_start = 1
                else:
                    # No entity suffix found, use heuristics
                    # Industry is usually 1-3 words, rest is company
                    # Look for transition from common industry words to company name
                    company_start = len(words)
                    for i in range(min(4, len(words)-1)):  # Check first few words
                        word_lower = words[i].lower().rstrip(',')
                        # If word is not a common industry indicator and previous words might be industry
                        if word_lower not in common_industry_indicators and i > 0:
                            # Potential company start - but be conservative
                            # Only split if we have at least 1 word for industry
                            if i >= 1:
                                # Check if this looks like a proper noun (capitalized) or company name part
                                if words[i][0].isupper() or i >= 2:  # Multiple capitalized words suggests company
                                    company_start = i
                                    break
                    
                    # Fallback: if no clear split, assume industry is first 1-2 words
                    if company_start == len(words) and len(words) >= 2:
                        company_start = min(2, len(words) - 1)
                
                if company_start > 0 and company_start < len(words):
                    industry_words = words[:company_start]
                    company_words = words[company_start:]
                elif len(words) >= 2:
                    # Fallback: first 1-2 words are industry
                    industry_words = words[:min(2, len(words)-1)]
                    company_words = words[min(2, len(words)-1):]
                else:
                    industry_words = []
                    company_words = words
                
                if industry_words:
                    res['industry'] = ' '.join(industry_words)
                if company_words:
                    res['company_name'] = ' '.join(company_words)
        
        # Extract investment type from tail part (after last comma) or main_part if no comma
        search_text = tail_part if tail_part else main_part
        # Investment type is before "Ref"
        inv_type_match = re.search(r'(.+?)\s+Ref\s+(?:SOFR|LIBOR|PRIME)', search_text, re.IGNORECASE)
        if inv_type_match:
            inv_part = inv_type_match.group(1).strip()
            # Extract common investment type patterns
            patterns = [
                r'First\s+Lien(?:\s+.*?)?(?:\s+Term\s+Loan\s*(?:[A-Z])?)?',
                r'Second\s+.*?Term\s+Loan',
                r'Delayed\s+Draw.*?Term\s+Loan',
                r'Incremental\s+Term\s+Loan',
                r'Preferred\s+Units?',
                r'Common\s+Units?',
                r'Warrants?',
                r'Term\s+Loan\s*[A-Z]?',
            ]
            for p in patterns:
                m = re.search(p, inv_part, re.IGNORECASE)
                if m:
                    res['investment_type'] = m.group(0).strip()
                    break
        
        # Clean up company name - remove trailing tokens that look like investment types
        if res['company_name'] != 'Unknown':
            cleaned = res['company_name']
            # Remove common trailing investment type patterns
            cleaned = re.sub(r'\s+(First\s+Lien|Second\s+Lien|Term\s+Loan|Ref\s+SOFR|Ref\s+LIBOR).*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Ref\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Floor\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Spread\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Total\s+Coupon\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Maturity\s+.*$', '', cleaned, flags=re.IGNORECASE)
            res['company_name'] = re.sub(r'\s+', ' ', cleaned).strip().rstrip(',')
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[TCPCInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = TCPCInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        # Extract tokens from raw identifier for TCPC-specific format
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
        # Fill missing fields from identifier tokens
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
        if not inv.maturity_date and toks.get('maturity_date'):
            inv.maturity_date = toks['maturity_date']
        # Final company name cleanup
        inv.company_name = self._clean_company_name(inv.company_name)

        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _clean_company_name(self, name: str) -> str:
        if not name:
            return name
        s = html.unescape(name)
        s = re.sub(r"\s+" , " ", s).strip().strip(',')
        # Drop leading connectors/industry fragments like "&", "and", "Services", "Systems", "Application", "Commercial", "Professional", "& Supplies"
        leading_noise = {
            'and', '&', 'services', 'service', 'systems', 'application', 'applications',
            'commercial', 'professional', 'supplies', 'equipment', 'products', '& supplies', '& equipment'
        }
        parts = s.split()
        # Remove leading noise tokens while next token is capitalized
        while parts and parts[0].lower() in leading_noise and (len(parts) == 1 or parts[1][0].isupper()):
            parts.pop(0)
        s = ' '.join(parts).strip()
        # Remove trailing security descriptors accidentally in name
        s = re.sub(r"\b(Common|Preferred)\s+Units?\b$", "", s, flags=re.IGNORECASE).strip().strip(',')
        return s

    def _extract_tokens_from_identifier(self, text: str) -> Dict[str, Optional[str]]:
        """Extract tokens from TCPC identifier format:
        "Debt Investments IT Services Serrano Parent,Chemicals,,First Lien Term Loan Ref SOFR(S) Floor 1.00% Spread 6.50% Total Coupon 10.71% Maturity 5/13/2030"
        Format: [Prefix] [Industry] [Company Name],[XBRL Industry],,[Investment Type] Ref [Rate] ...
        """
        out: Dict[str, Optional[str]] = {
            'company_name': None, 'industry': None, 'investment_type': None,
            'reference_rate': None, 'spread': None, 'floor_rate': None,
            'interest_rate': None, 'pik_rate': None, 'maturity_date': None
        }
        if not text:
            return out
        
        # Split on comma - parts are: [main], [industry axis], [], [tail with inv type]
        parts = [p.strip() for p in text.split(',')]
        main_part = parts[0] if parts else text.strip()
        tail_part = parts[-1] if len(parts) > 1 else ''
        
        # Parse company name and industry from main_part (same logic as _parse_identifier)
        prefix_match = re.match(r'^(Debt\s+Investments|Equity\s+Securities)\s+(.+)$', main_part, re.IGNORECASE)
        if prefix_match:
            rest = prefix_match.group(2)
            words = rest.split()
            if words:
                # Use same logic as _parse_identifier
                common_industry_indicators = {
                    'services', 'service', 'capital', 'markets', 'consumer', 'finance',
                    'financial', 'software', 'media', 'diversified', 'professional',
                    'building', 'products', 'construction', 'engineering', 'internet'
                }
                
                entity_positions = []
                for i, word in enumerate(words):
                    if re.search(r'\b(LLC|Inc\.?|Corp\.?|LP|Holdings?|Companies?|B\.V\.?|Ltd\.?|Corporation)\b', word, re.IGNORECASE):
                        entity_positions.append(i)
                
                if entity_positions:
                    entity_pos = entity_positions[0]
                    company_start = max(0, entity_pos - 2)
                    if company_start == 0 and len(words) > 1:
                        company_start = 1
                else:
                    company_start = len(words)
                    for i in range(min(4, len(words)-1)):
                        word_lower = words[i].lower().rstrip(',')
                        if word_lower not in common_industry_indicators and i > 0:
                            if i >= 1:
                                if words[i][0].isupper() or i >= 2:
                                    company_start = i
                                    break
                    if company_start == len(words) and len(words) >= 2:
                        company_start = min(2, len(words) - 1)
                
                if company_start > 0 and company_start < len(words):
                    industry_words = words[:company_start]
                    company_words = words[company_start:]
                elif len(words) >= 2:
                    industry_words = words[:min(2, len(words)-1)]
                    company_words = words[min(2, len(words)-1):]
                else:
                    industry_words = []
                    company_words = words
                
                if industry_words:
                    out['industry'] = ' '.join(industry_words)
                if company_words:
                    out['company_name'] = ' '.join(company_words)
        
        # Search for tokens in tail_part (after last comma) or main_part if no comma
        search_text = tail_part if tail_part else main_part
        
        # Investment type (before "Ref")
        inv_type_match = re.search(r'(.+?)\s+Ref\s+(?:SOFR|LIBOR|PRIME)', search_text, re.IGNORECASE)
        if inv_type_match:
            inv_part = inv_type_match.group(1).strip()
            patterns = [
                r'First\s+Lien(?:\s+.*?)?(?:\s+Term\s+Loan\s*(?:[A-Z])?)?',
                r'Second\s+.*?Term\s+Loan',
                r'Delayed\s+Draw.*?Term\s+Loan',
                r'Incremental\s+Term\s+Loan',
                r'Preferred\s+Units?',
                r'Common\s+Units?',
                r'Warrants?',
                r'Term\s+Loan\s*[A-Z]?',
            ]
            for p in patterns:
                m = re.search(p, inv_part, re.IGNORECASE)
                if m:
                    out['investment_type'] = m.group(0).strip()
                    break
        
        # Reference rate: "Ref SOFR(S)" or "Ref LIBOR(M)" etc.
        ref_match = re.search(r'Ref\s+(SOFR|LIBOR|PRIME)\s*\([SMQ]\)?', search_text, re.IGNORECASE)
        if ref_match:
            out['reference_rate'] = ref_match.group(1).upper()
        
        # Floor: "Floor 1.00%"
        floor_match = re.search(r'Floor\s+([\d\.]+)%', search_text, re.IGNORECASE)
        if floor_match:
            out['floor_rate'] = self._percent(floor_match.group(1))
        
        # Spread: "Spread 6.50%" or "Spread 10.11% PIK"
        spread_match = re.search(r'Spread\s+([\d\.]+)%(?:\s+PIK)?', search_text, re.IGNORECASE)
        if spread_match:
            out['spread'] = self._percent(spread_match.group(1))
            # Check if PIK mentioned near spread
            if 'PIK' in search_text[max(0, spread_match.start()-20):spread_match.end()+20]:
                out['pik_rate'] = self._percent(spread_match.group(1))
        
        # Total Coupon: "Total Coupon 10.71%"
        coupon_match = re.search(r'Total\s+Coupon\s+([\d\.]+)%', search_text, re.IGNORECASE)
        if coupon_match:
            out['interest_rate'] = self._percent(coupon_match.group(1))
        
        # Maturity: "Maturity 5/13/2030"
        mat_match = re.search(r'Maturity\s+(\d{1,2}/\d{1,2}/\d{4})', search_text, re.IGNORECASE)
        if mat_match:
            out['maturity_date'] = mat_match.group(1)
        
        return out

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
    ex=TCPCExtractor()
    try:
        res=ex.extract_from_ticker('TCPC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()





TCPC (Blackrock TCP Capital Corp) Investment Extractor
XBRL-first using InvestmentIdentifierAxis; latest-instant filtering; de-dup; industry enrichment.
"""

import re
import html
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
class TCPCInvestment:
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


class TCPCExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "TCPC") -> Dict:
        logger.info(f"Extracting investments for {ticker}")
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        m = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
        if not m:
            raise ValueError("Could not parse accession number")
        accession = m.group(1)
        accession_no_hyphens = accession.replace('-', '')
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        return self.extract_from_url(txt_url, "Blackrock_TCP_Capital_Corp", cik)

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
        investments: List[TCPCInvestment] = []
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
        out_file = os.path.join(out_dir, 'TCPC_Blackrock_TCP_Capital_Corp_investments.csv')
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
        """TCPC identifiers like:
        "Debt Investments IT Services Serrano Parent,Chemicals,,First Lien Term Loan Ref SOFR(S) Floor 1.00% Spread 6.50% Total Coupon 10.71% Maturity 5/13/2030"
        Format: [Prefix] [Industry] [Company Name],[XBRL Industry],,[Investment Type] Ref [Rate] ...
        Parse to extract company, industry, investment type.
        """
        res: Dict[str, Optional[str]] = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
        
        # Split on comma - parts are: [main], [industry axis], [], [tail with inv type]
        parts = [p.strip() for p in identifier.split(',')]
        main_part = parts[0] if parts else identifier.strip()
        tail_part = parts[-1] if len(parts) > 1 else ''
        
        # Check for prefix: "Debt Investments" or "Equity Securities"
        prefix_match = re.match(r'^(Debt\s+Investments|Equity\s+Securities)\s+(.+)$', main_part, re.IGNORECASE)
        if prefix_match:
            rest = prefix_match.group(2)
            words = rest.split()
            if words:
                # Industry is typically 1-3 words, company name is the rest
                # Common industry patterns: single words or "X and Y" or "X, Y and Z"
                # Try to find where company name starts by looking for:
                # 1. Entity suffixes (LLC, Inc, Corp, etc.) - company includes this
                # 2. Company name patterns (capitalized words that aren't common industry words)
                
                # List of common industry words (used to identify industry vs company)
                common_industry_indicators = {
                    'services', 'service', 'capital', 'markets', 'consumer', 'finance',
                    'financial', 'software', 'media', 'diversified', 'professional',
                    'building', 'products', 'construction', 'engineering', 'internet'
                }
                
                # Find entity suffix positions
                entity_positions = []
                for i, word in enumerate(words):
                    if re.search(r'\b(LLC|Inc\.?|Corp\.?|LP|Holdings?|Companies?|B\.V\.?|Ltd\.?|Corporation)\b', word, re.IGNORECASE):
                        entity_positions.append(i)
                
                # If we find an entity suffix, company name likely starts before it
                if entity_positions:
                    # Company includes entity suffix, so start a bit before
                    entity_pos = entity_positions[0]
                    # Look backwards for company name start (usually 1-3 words before entity)
                    company_start = max(0, entity_pos - 2)
                    # But don't split too early - ensure at least 1 word for industry
                    if company_start == 0 and len(words) > 1:
                        company_start = 1
                else:
                    # No entity suffix found, use heuristics
                    # Industry is usually 1-3 words, rest is company
                    # Look for transition from common industry words to company name
                    company_start = len(words)
                    for i in range(min(4, len(words)-1)):  # Check first few words
                        word_lower = words[i].lower().rstrip(',')
                        # If word is not a common industry indicator and previous words might be industry
                        if word_lower not in common_industry_indicators and i > 0:
                            # Potential company start - but be conservative
                            # Only split if we have at least 1 word for industry
                            if i >= 1:
                                # Check if this looks like a proper noun (capitalized) or company name part
                                if words[i][0].isupper() or i >= 2:  # Multiple capitalized words suggests company
                                    company_start = i
                                    break
                    
                    # Fallback: if no clear split, assume industry is first 1-2 words
                    if company_start == len(words) and len(words) >= 2:
                        company_start = min(2, len(words) - 1)
                
                if company_start > 0 and company_start < len(words):
                    industry_words = words[:company_start]
                    company_words = words[company_start:]
                elif len(words) >= 2:
                    # Fallback: first 1-2 words are industry
                    industry_words = words[:min(2, len(words)-1)]
                    company_words = words[min(2, len(words)-1):]
                else:
                    industry_words = []
                    company_words = words
                
                if industry_words:
                    res['industry'] = ' '.join(industry_words)
                if company_words:
                    res['company_name'] = ' '.join(company_words)
        
        # Extract investment type from tail part (after last comma) or main_part if no comma
        search_text = tail_part if tail_part else main_part
        # Investment type is before "Ref"
        inv_type_match = re.search(r'(.+?)\s+Ref\s+(?:SOFR|LIBOR|PRIME)', search_text, re.IGNORECASE)
        if inv_type_match:
            inv_part = inv_type_match.group(1).strip()
            # Extract common investment type patterns
            patterns = [
                r'First\s+Lien(?:\s+.*?)?(?:\s+Term\s+Loan\s*(?:[A-Z])?)?',
                r'Second\s+.*?Term\s+Loan',
                r'Delayed\s+Draw.*?Term\s+Loan',
                r'Incremental\s+Term\s+Loan',
                r'Preferred\s+Units?',
                r'Common\s+Units?',
                r'Warrants?',
                r'Term\s+Loan\s*[A-Z]?',
            ]
            for p in patterns:
                m = re.search(p, inv_part, re.IGNORECASE)
                if m:
                    res['investment_type'] = m.group(0).strip()
                    break
        
        # Clean up company name - remove trailing tokens that look like investment types
        if res['company_name'] != 'Unknown':
            cleaned = res['company_name']
            # Remove common trailing investment type patterns
            cleaned = re.sub(r'\s+(First\s+Lien|Second\s+Lien|Term\s+Loan|Ref\s+SOFR|Ref\s+LIBOR).*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Ref\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Floor\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Spread\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Total\s+Coupon\s+.*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s+Maturity\s+.*$', '', cleaned, flags=re.IGNORECASE)
            res['company_name'] = re.sub(r'\s+', ' ', cleaned).strip().rstrip(',')
        
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

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[TCPCInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = TCPCInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        # Extract tokens from raw identifier for TCPC-specific format
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
        # Fill missing fields from identifier tokens
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
        if not inv.maturity_date and toks.get('maturity_date'):
            inv.maturity_date = toks['maturity_date']
        # Final company name cleanup
        inv.company_name = self._clean_company_name(inv.company_name)

        if not inv.acquisition_date and context.get('start_date'):
            inv.acquisition_date = context['start_date'][:10]
        if inv.company_name and (inv.principal_amount or inv.cost or inv.fair_value):
            return inv
        return None

    def _clean_company_name(self, name: str) -> str:
        if not name:
            return name
        s = html.unescape(name)
        s = re.sub(r"\s+" , " ", s).strip().strip(',')
        # Drop leading connectors/industry fragments like "&", "and", "Services", "Systems", "Application", "Commercial", "Professional", "& Supplies"
        leading_noise = {
            'and', '&', 'services', 'service', 'systems', 'application', 'applications',
            'commercial', 'professional', 'supplies', 'equipment', 'products', '& supplies', '& equipment'
        }
        parts = s.split()
        # Remove leading noise tokens while next token is capitalized
        while parts and parts[0].lower() in leading_noise and (len(parts) == 1 or parts[1][0].isupper()):
            parts.pop(0)
        s = ' '.join(parts).strip()
        # Remove trailing security descriptors accidentally in name
        s = re.sub(r"\b(Common|Preferred)\s+Units?\b$", "", s, flags=re.IGNORECASE).strip().strip(',')
        return s

    def _extract_tokens_from_identifier(self, text: str) -> Dict[str, Optional[str]]:
        """Extract tokens from TCPC identifier format:
        "Debt Investments IT Services Serrano Parent,Chemicals,,First Lien Term Loan Ref SOFR(S) Floor 1.00% Spread 6.50% Total Coupon 10.71% Maturity 5/13/2030"
        Format: [Prefix] [Industry] [Company Name],[XBRL Industry],,[Investment Type] Ref [Rate] ...
        """
        out: Dict[str, Optional[str]] = {
            'company_name': None, 'industry': None, 'investment_type': None,
            'reference_rate': None, 'spread': None, 'floor_rate': None,
            'interest_rate': None, 'pik_rate': None, 'maturity_date': None
        }
        if not text:
            return out
        
        # Split on comma - parts are: [main], [industry axis], [], [tail with inv type]
        parts = [p.strip() for p in text.split(',')]
        main_part = parts[0] if parts else text.strip()
        tail_part = parts[-1] if len(parts) > 1 else ''
        
        # Parse company name and industry from main_part (same logic as _parse_identifier)
        prefix_match = re.match(r'^(Debt\s+Investments|Equity\s+Securities)\s+(.+)$', main_part, re.IGNORECASE)
        if prefix_match:
            rest = prefix_match.group(2)
            words = rest.split()
            if words:
                # Use same logic as _parse_identifier
                common_industry_indicators = {
                    'services', 'service', 'capital', 'markets', 'consumer', 'finance',
                    'financial', 'software', 'media', 'diversified', 'professional',
                    'building', 'products', 'construction', 'engineering', 'internet'
                }
                
                entity_positions = []
                for i, word in enumerate(words):
                    if re.search(r'\b(LLC|Inc\.?|Corp\.?|LP|Holdings?|Companies?|B\.V\.?|Ltd\.?|Corporation)\b', word, re.IGNORECASE):
                        entity_positions.append(i)
                
                if entity_positions:
                    entity_pos = entity_positions[0]
                    company_start = max(0, entity_pos - 2)
                    if company_start == 0 and len(words) > 1:
                        company_start = 1
                else:
                    company_start = len(words)
                    for i in range(min(4, len(words)-1)):
                        word_lower = words[i].lower().rstrip(',')
                        if word_lower not in common_industry_indicators and i > 0:
                            if i >= 1:
                                if words[i][0].isupper() or i >= 2:
                                    company_start = i
                                    break
                    if company_start == len(words) and len(words) >= 2:
                        company_start = min(2, len(words) - 1)
                
                if company_start > 0 and company_start < len(words):
                    industry_words = words[:company_start]
                    company_words = words[company_start:]
                elif len(words) >= 2:
                    industry_words = words[:min(2, len(words)-1)]
                    company_words = words[min(2, len(words)-1):]
                else:
                    industry_words = []
                    company_words = words
                
                if industry_words:
                    out['industry'] = ' '.join(industry_words)
                if company_words:
                    out['company_name'] = ' '.join(company_words)
        
        # Search for tokens in tail_part (after last comma) or main_part if no comma
        search_text = tail_part if tail_part else main_part
        
        # Investment type (before "Ref")
        inv_type_match = re.search(r'(.+?)\s+Ref\s+(?:SOFR|LIBOR|PRIME)', search_text, re.IGNORECASE)
        if inv_type_match:
            inv_part = inv_type_match.group(1).strip()
            patterns = [
                r'First\s+Lien(?:\s+.*?)?(?:\s+Term\s+Loan\s*(?:[A-Z])?)?',
                r'Second\s+.*?Term\s+Loan',
                r'Delayed\s+Draw.*?Term\s+Loan',
                r'Incremental\s+Term\s+Loan',
                r'Preferred\s+Units?',
                r'Common\s+Units?',
                r'Warrants?',
                r'Term\s+Loan\s*[A-Z]?',
            ]
            for p in patterns:
                m = re.search(p, inv_part, re.IGNORECASE)
                if m:
                    out['investment_type'] = m.group(0).strip()
                    break
        
        # Reference rate: "Ref SOFR(S)" or "Ref LIBOR(M)" etc.
        ref_match = re.search(r'Ref\s+(SOFR|LIBOR|PRIME)\s*\([SMQ]\)?', search_text, re.IGNORECASE)
        if ref_match:
            out['reference_rate'] = ref_match.group(1).upper()
        
        # Floor: "Floor 1.00%"
        floor_match = re.search(r'Floor\s+([\d\.]+)%', search_text, re.IGNORECASE)
        if floor_match:
            out['floor_rate'] = self._percent(floor_match.group(1))
        
        # Spread: "Spread 6.50%" or "Spread 10.11% PIK"
        spread_match = re.search(r'Spread\s+([\d\.]+)%(?:\s+PIK)?', search_text, re.IGNORECASE)
        if spread_match:
            out['spread'] = self._percent(spread_match.group(1))
            # Check if PIK mentioned near spread
            if 'PIK' in search_text[max(0, spread_match.start()-20):spread_match.end()+20]:
                out['pik_rate'] = self._percent(spread_match.group(1))
        
        # Total Coupon: "Total Coupon 10.71%"
        coupon_match = re.search(r'Total\s+Coupon\s+([\d\.]+)%', search_text, re.IGNORECASE)
        if coupon_match:
            out['interest_rate'] = self._percent(coupon_match.group(1))
        
        # Maturity: "Maturity 5/13/2030"
        mat_match = re.search(r'Maturity\s+(\d{1,2}/\d{1,2}/\d{4})', search_text, re.IGNORECASE)
        if mat_match:
            out['maturity_date'] = mat_match.group(1)
        
        return out

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
    ex=TCPCExtractor()
    try:
        res=ex.extract_from_ticker('TCPC')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()




