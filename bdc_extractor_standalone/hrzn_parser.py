#!/usr/bin/env python3
"""
HRZN (Horizon Technology Finance Corp) Investment Extractor
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
from bs4 import BeautifulSoup

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class HRZNInvestment:
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


class HRZNExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "HRZN") -> Dict:
        """Extract investments from HRZN's latest 10-Q filing using HTML tables."""
        
        logger.info(f"Extracting investments for {ticker}")
        
        # Get CIK
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        logger.info(f"Found CIK: {cik}")
        
        # Get latest 10-Q filing URL
        filing_index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not filing_index_url:
            raise ValueError(f"Could not find 10-Q filing for {ticker}")
        
        logger.info(f"Found filing index: {filing_index_url}")
        
        # Get documents from index
        documents = self.sec_client.get_documents_from_index(filing_index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith(".htm")), None)
        if not main_html:
            raise ValueError(f"No main HTML document found for {ticker}")
        
        logger.info(f"Found main HTML: {main_html.url}")
        
        # Extract investments from HTML
        return self.extract_from_html_url(main_html.url, "Horizon Technology Finance Corp", cik)

    def extract_from_html_url(self, html_url: str, company_name: str, cik: str) -> Dict:
        """Extract investments from HRZN HTML filing URL."""
        
        logger.info(f"Downloading HTML from: {html_url}")
        
        # Download the HTML content
        response = requests.get(html_url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        logger.info(f"Downloaded and parsed HTML")
        
        # Find Consolidated Schedule of Investments tables
        tables = self._find_schedule_tables(soup)
        logger.info(f"Found {len(tables)} schedule tables")
        
        if not tables:
            logger.warning("No schedule tables found, falling back to XBRL extraction")
            # Fallback to XBRL if HTML tables not found
            return self._fallback_to_xbrl(html_url, company_name, cik)
        
        # Save simplified tables for QA
        self._save_simplified_tables(tables, cik)
        
        # Parse tables to extract investments
        investments = self._parse_html_tables(tables)
        
        logger.info(f"Built {len(investments)} investments from HTML")
        
        # Calculate totals
        total_principal = sum(inv.principal_amount or 0 for inv in investments)
        total_cost = sum(inv.cost or 0 for inv in investments)
        total_fair_value = sum(inv.fair_value or 0 for inv in investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in investments:
            industry_breakdown[inv.industry] += 1
            investment_type_breakdown[inv.investment_type] += 1
        
        # Save to CSV
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'HRZN_Horizon_Technology_Finance_Corp_investments.csv')
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
                    'company_name': inv.company_name or '',
                    'industry': standardized_industry or '',
                    'business_description': inv.business_description or '',
                    'investment_type': standardized_inv_type or '',
                    'acquisition_date': inv.acquisition_date or '',
                    'maturity_date': inv.maturity_date or '',
                    'principal_amount': inv.principal_amount or '',
                    'cost': inv.cost or '',
                    'fair_value': inv.fair_value or '',
                    'interest_rate': inv.interest_rate or '',
                    'reference_rate': standardized_ref_rate or '',
                    'spread': inv.spread or '',
                    'floor_rate': inv.floor_rate or '',
                    'pik_rate': inv.pik_rate or '',
                })
        
        logger.info(f"Saved to {out_file}")
        
        # Convert to dict format
        investment_dicts = []
        for inv in investments:
            investment_dicts.append({
                'company_name': inv.company_name,
                'industry': inv.industry,
                'business_description': inv.business_description,
                'investment_type': inv.investment_type,
                'acquisition_date': inv.acquisition_date,
                'maturity_date': inv.maturity_date,
                'principal_amount': inv.principal_amount,
                'cost': inv.cost,
                'fair_value': inv.fair_value,
                'interest_rate': inv.interest_rate,
                'reference_rate': inv.reference_rate,
                'spread': inv.spread,
                'floor_rate': inv.floor_rate,
                'pik_rate': inv.pik_rate,
                'shares_units': inv.shares_units,
                'percent_net_assets': inv.percent_net_assets,
                'currency': inv.currency,
                'commitment_limit': inv.commitment_limit,
                'undrawn_commitment': inv.undrawn_commitment,
            })
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(investments),
            'investments': investment_dicts,
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _fallback_to_xbrl(self, html_url: str, company_name: str, cik: str) -> Dict:
        """Fallback to XBRL extraction if HTML tables not found."""
        # Extract accession number from HTML URL - try multiple formats
        accession_match = re.search(r'/(\d{10}-\d{2}-\d{6})', html_url)
        if not accession_match:
            # Try alternative format: /000143774925031988/ -> 0001437749-25-031988
            alt_match = re.search(r'/(\d{10})(\d{2})(\d{6})', html_url)
            if alt_match:
                accession = f"{alt_match.group(1)}-{alt_match.group(2)}-{alt_match.group(3)}"
            else:
                raise ValueError(f"Could not parse accession number from {html_url}")
        else:
            accession = accession_match.group(1)
        
        accession_no_hyphens = accession.replace('-', '')
        
        # Build .txt URL
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        logger.info(f"Fallback: Using XBRL URL: {txt_url}")
        
        return self.extract_from_url(txt_url, company_name, cik)
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text by collapsing whitespace."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()
    
    def _find_schedule_tables(self, soup: BeautifulSoup) -> List[BeautifulSoup]:
        """Find tables with Consolidated Schedule of Investments heading."""
        matches = []
        
        # Tokens that should appear in the heading context
        required_any = [
            "horizon technology",
            "consolidated schedule of investments",
            "schedule of investments",
            "unaudited",
            "dollar amounts in thousands",
        ]
        
        def heading_matches(blob: str) -> bool:
            blob_l = blob.lower()
            # Must contain schedule phrase
            must = ["schedule of investments"]
            if not all(m in blob_l for m in must):
                return False
            # Also require at least one of company/unaudited/dollars
            count = sum(1 for t in required_any if t in blob_l)
            return count >= 1
        
        for table in soup.find_all("table"):
            context_texts = []
            cur = table
            for _ in range(12):  # Look back 12 text nodes
                prev = cur.find_previous(string=True)
                if not prev:
                    break
                txt = self._normalize_text(prev if isinstance(prev, str) else prev.get_text(" ", strip=True))
                if txt:
                    context_texts.append(txt)
                cur = prev.parent if hasattr(prev, "parent") else None
                if not cur:
                    break
            context_blob = " ".join(context_texts)
            if heading_matches(context_blob):
                matches.append(table)
        
        # Fallback: if nothing matched, return the first 30 tables for QA
        if not matches:
            all_tables = soup.find_all("table")
            if all_tables:
                logger.info("No schedule-heading matches; returning first 30 tables for QA review")
                matches = all_tables[:30]
        
        return matches
    
    def _table_to_rows(self, table: BeautifulSoup) -> List[List[str]]:
        """Convert table to list of rows (list of cell strings)."""
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            vals = []
            for c in cells:
                # Get text content, handling XBRL tags
                vals.append(self._normalize_text(c.get_text(" ", strip=True)))
            rows.append(vals)
        return rows
    
    def _simplify_table(self, table: BeautifulSoup) -> str:
        """Return simplified HTML string for a table (remove styles/classes)."""
        simple = BeautifulSoup(str(table), "html.parser").find("table")
        if not simple:
            return "<table></table>"
        
        # Replace ix:* tags with their text
        for ix in simple.find_all(lambda t: isinstance(t.name, str) and t.name.lower().startswith("ix:")):
            ix.replace_with(ix.get_text(" ", strip=True))
        
        # Remove attributes
        def strip_attrs(el):
            if hasattr(el, "attrs"):
                el.attrs = {}
            for child in getattr(el, "children", []):
                strip_attrs(child)
        strip_attrs(simple)
        
        # Unwrap format tags
        for tag_name in ["span", "div", "b", "strong", "i", "em", "u"]:
            for t in simple.find_all(tag_name):
                t.unwrap()
        
        # Remove empty rows
        for tr in simple.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells or not any(c.get_text(strip=True) for c in cells):
                tr.decompose()
        
        # Keep only table structure tags
        allowed = {"table", "thead", "tbody", "tr", "th", "td"}
        for tag in list(simple.find_all(True)):
            if tag.name not in allowed:
                tag.unwrap()
        
        return str(simple)
    
    def _save_simplified_tables(self, tables: List[BeautifulSoup], cik: str):
        """Save simplified HTML tables for QA review."""
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", f"hrzn_tables")
        os.makedirs(output_dir, exist_ok=True)
        
        for i, table in enumerate(tables, 1):
            simple_html = self._simplify_table(table)
            output_file = os.path.join(output_dir, f"hrzn_table_{i}.html")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(simple_html)
        
        logger.info(f"Saved {len(tables)} simplified tables to {output_dir}")
    
    def _parse_html_tables(self, tables: List[BeautifulSoup]) -> List[HRZNInvestment]:
        """Parse HTML tables to extract investment data - handles both simple and detailed debt tables."""
        investments: List[HRZNInvestment] = []
        
        def to_float(s: Optional[str]) -> Optional[float]:
            if not s:
                return None
            t = s.replace('\xa0', ' ').replace(',', '').strip()
            if t in ("—", "-", "", "n/a"):
                return None
            if t.startswith('$'):
                t = t[1:].strip()
            try:
                return float(t)
            except:
                return None
        
        def find_value_in_row(row: List[str], header_idx: int, max_search: int = 10) -> Optional[str]:
            """Find first non-empty value starting from header_idx (look further for split cells)."""
            for i in range(header_idx, min(header_idx + max_search, len(row))):
                val = row[i].strip() if i < len(row) else ""
                if val and val not in ("—", "-", ""):
                    return val
            return None
        
        def find_amount_in_row(row: List[str], start_idx: int) -> Optional[float]:
            """Find first numeric amount starting from start_idx (look further for split cells)."""
            for i in range(start_idx, min(start_idx + 10, len(row))):
                val = to_float(row[i]) if i < len(row) else None
                if val is not None and val > 0:
                    # Skip very small values that are likely percentages
                    if val < 100:
                        continue
                    return val
            return None
        
        def parse_date(cell: str) -> Optional[str]:
            """Parse date from cell (e.g., 'March 1, 2029')."""
            if not cell:
                return None
            month_match = re.search(r'([A-Za-z]+)\s+(\d+),\s+(\d{4})', cell)
            if month_match:
                month_name = month_match.group(1)
                day = month_match.group(2)
                year = month_match.group(3)
                months = {
                    'january': '01', 'february': '02', 'march': '03', 'april': '04',
                    'may': '05', 'june': '06', 'july': '07', 'august': '08',
                    'september': '09', 'october': '10', 'november': '11', 'december': '12'
                }
                month_num = months.get(month_name.lower())
                if month_num:
                    return f"{year}-{month_num}-{day.zfill(2)}"
            return None
        
        last_company = None
        last_industry = None
        
        for table in tables:
            rows = self._table_to_rows(table)
            if not rows:
                continue
            
            col_idx = {}
            in_body = False
            
            for r in rows:
                if not in_body:
                    header = ' '.join(r).lower()
                    has_detailed = 'cash rate' in header and 'maturity date' in header and 'principal amount' in header
                    has_simple = 'portfolio company' in header and ('cost' in header or 'value' in header)
                    
                    if has_detailed or has_simple:
                        for i, cell in enumerate(r):
                            c = cell.lower()
                            if 'portfolio company' in c:
                                col_idx['company'] = i
                            elif c.strip() == 'sector' or 'sector' in c:
                                col_idx['sector'] = i
                            elif 'type of investment' in c:
                                col_idx['type'] = i
                            elif 'cash rate' in c:
                                col_idx['cash_rate'] = i
                            elif c.strip() == 'index':
                                col_idx['index'] = i
                            elif c.strip() == 'margin':
                                col_idx['margin'] = i
                            elif c.strip() == 'floor':
                                col_idx['floor'] = i
                            elif 'maturity date' in c:
                                col_idx['maturity'] = i
                            elif 'principal amount' in c:
                                col_idx['principal'] = i
                            elif 'cost of' in c or ('cost' in c and 'investment' in c):
                                col_idx['cost'] = i
                            elif 'fair' in c and 'value' in c:
                                col_idx['value'] = i
                        in_body = True
                        continue
                    continue
                
                # Handle continuation rows
                first_cell = r[0].strip() if r else ""
                first_cell_empty = not first_cell
                
                if first_cell_empty and last_company:
                    company_name = last_company
                    industry = last_industry
                else:
                    company_name = first_cell
                    if not company_name:
                        continue
                    
                    # Remove footnote markers
                    company_name = re.sub(r'\s*\(\d+\)(?:\(\d+\))*\s*', '', company_name).strip()
                    
                    # Skip section headers
                    low = company_name.lower()
                    if any(tok in low for tok in ['non-affiliate', 'affiliate', 'total', 'warrants', 'investments', '—', 'debt investments']):
                        continue
                    
                    last_company = company_name
                    si = col_idx.get('sector')
                    industry = find_value_in_row(r, si) if si is not None else None
                    industry = industry or last_industry or 'Unknown'
                    last_industry = industry
                
                # Extract investment type
                ti = col_idx.get('type')
                inv_type = find_value_in_row(r, ti) if ti is not None else 'Unknown'
                
                # Extract rates from detailed table
                interest_rate = None
                reference_rate = None
                spread = None
                floor_rate = None
                maturity_date = None
                principal_amount = None
                cost = None
                fair_value = None
                
                if 'cash_rate' in col_idx:
                    # Cash rate (interest rate) - value is 1-2 cells after header
                    cash_idx = col_idx['cash_rate']
                    cash_val = find_value_in_row(r, cash_idx + 1)
                    if cash_val:
                        # Check if next cell has %
                        if cash_idx + 2 < len(r) and r[cash_idx + 2].strip() == "%":
                            interest_rate = f"{cash_val}%"
                        elif "%" in cash_val:
                            interest_rate = cash_val
                        else:
                            # Check if next cell has %
                            for i in range(cash_idx + 1, min(cash_idx + 5, len(r))):
                                if r[i].strip() == "%" and i > cash_idx + 1:
                                    interest_rate = f"{cash_val}%"
                                    break
                    
                    # Index (reference rate) - value is 1-2 cells after header
                    idx_idx = col_idx.get('index')
                    if idx_idx is not None:
                        idx_val = find_value_in_row(r, idx_idx + 1)
                        if idx_val:
                            reference_rate = idx_val.upper()
                    
                    # Margin (spread) - value is 1-2 cells after header
                    margin_idx = col_idx.get('margin')
                    if margin_idx is not None:
                        margin_val = find_value_in_row(r, margin_idx + 1)
                        if margin_val:
                            # Check if next cell has %
                            if margin_idx + 2 < len(r) and r[margin_idx + 2].strip() == "%":
                                spread = f"{margin_val}%"
                            elif "%" in margin_val:
                                spread = margin_val
                            else:
                                # Check if next cell has %
                                for i in range(margin_idx + 1, min(margin_idx + 5, len(r))):
                                    if r[i].strip() == "%" and i > margin_idx + 1:
                                        spread = f"{margin_val}%"
                                        break
                    
                    # Floor - value is 1-2 cells after header
                    floor_idx = col_idx.get('floor')
                    if floor_idx is not None:
                        floor_val = find_value_in_row(r, floor_idx + 1)
                        if floor_val:
                            # Check if next cell has %
                            if floor_idx + 2 < len(r) and r[floor_idx + 2].strip() == "%":
                                floor_rate = f"{floor_val}%"
                            elif "%" in floor_val:
                                floor_rate = floor_val
                            else:
                                # Check if next cell has %
                                for i in range(floor_idx + 1, min(floor_idx + 5, len(r))):
                                    if r[i].strip() == "%" and i > floor_idx + 1:
                                        floor_rate = f"{floor_val}%"
                                        break
                    
                    # Maturity date - value is typically 5-7 cells after header (skips empty cells)
                    mat_idx = col_idx.get('maturity')
                    if mat_idx is not None:
                        # Look further for maturity date (it's after ETP percentage)
                        mat_val = find_value_in_row(r, mat_idx + 1)
                        if mat_val and parse_date(mat_val):
                            maturity_date = parse_date(mat_val)
                        else:
                            # Try looking further (5-7 cells after header)
                            for i in range(mat_idx + 1, min(mat_idx + 10, len(r))):
                                val = r[i].strip() if i < len(r) else ""
                                if val:
                                    parsed = parse_date(val)
                                    if parsed:
                                        maturity_date = parsed
                                        break
                    
                    # Principal amount - need to look further and skip percentage values
                    princ_idx = col_idx.get('principal')
                    if princ_idx is not None:
                        # Principal amounts are typically 5-8 cells after the header
                        # Skip small values (< 100) which are likely percentages
                        for i in range(princ_idx + 1, min(princ_idx + 15, len(r))):
                            val_str = r[i].strip() if i < len(r) else ""
                            if not val_str or val_str in ("—", "-", ""):
                                continue
                            # Remove commas and $ for parsing
                            val_clean = val_str.replace(',', '').replace('$', '').strip()
                            try:
                                val = float(val_clean)
                                if val >= 100:  # Skip percentages, only get dollar amounts
                                    principal_amount = val
                                    break
                            except:
                                pass
                    
                    # Cost - look further after principal amount or use column index
                    cost_idx = col_idx.get('cost')
                    if cost_idx is not None:
                        # Cost is typically 3-5 cells after principal amount
                        if principal_amount is not None:
                            # Find where principal amount was and look after it
                            for i in range(len(r)):
                                val_str = r[i].strip() if i < len(r) else ""
                                val_clean = val_str.replace(',', '').replace('$', '').strip()
                                try:
                                    if float(val_clean) == principal_amount:
                                        # Look 3-5 cells after principal
                                        for j in range(i + 3, min(i + 8, len(r))):
                                            cost_val = to_float(r[j])
                                            if cost_val is not None and cost_val >= 100:
                                                cost = cost_val
                                                break
                                        break
                                except:
                                    pass
                        # Fallback to searching from cost column
                        if cost is None:
                            for i in range(cost_idx + 1, min(cost_idx + 15, len(r))):
                                val = to_float(r[i])
                                if val is not None and val >= 100:
                                    cost = val
                                    break
                    
                    # Fair value - look further after cost or use column index
                    val_idx = col_idx.get('value')
                    if val_idx is not None:
                        # Fair value is typically 3-5 cells after cost
                        if cost is not None:
                            # Find where cost was and look after it
                            for i in range(len(r)):
                                val_str = r[i].strip() if i < len(r) else ""
                                val_clean = val_str.replace(',', '').replace('$', '').strip()
                                try:
                                    if abs(float(val_clean) - cost) < 1:  # Allow small rounding differences
                                        # Look 3-5 cells after cost
                                        for j in range(i + 3, min(i + 8, len(r))):
                                            val_val = to_float(r[j])
                                            if val_val is not None and val_val >= 100:
                                                fair_value = val_val
                                                break
                                        break
                                except:
                                    pass
                        # Fallback to searching from value column
                        if fair_value is None:
                            for i in range(val_idx + 1, min(val_idx + 15, len(r))):
                                val = to_float(r[i])
                                if val is not None and val >= 100:
                                    fair_value = val
                                    break
                
                else:
                    # Simple table
                    cost_idx = col_idx.get('cost')
                    val_idx = col_idx.get('value')
                    if cost_idx is not None:
                        cost = to_float(r[cost_idx]) if cost_idx < len(r) else None
                    if val_idx is not None:
                        fair_value = to_float(r[val_idx]) if val_idx < len(r) else None
                
                # Create investment if we have essential data
                if company_name and (principal_amount or cost or fair_value):
                    investments.append(HRZNInvestment(
                        company_name=company_name,
                        industry=industry or 'Unknown',
                        investment_type=inv_type or 'Unknown',
                        maturity_date=maturity_date,
                        principal_amount=principal_amount,
                        cost=cost,
                        fair_value=fair_value,
                        interest_rate=interest_rate,
                        reference_rate=reference_rate,
                        spread=spread,
                        floor_rate=floor_rate
                    ))
        
        return investments
    
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
        investments: List[HRZNInvestment] = []
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

        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'HRZN_Horizon_Technology_Finance_Corp_investments.csv')
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
        # Clean odd concatenations (XBRL member strings) by inserting spaces before capitals
        company = re.sub(r'(?<!\s)([A-Z])', r' \1', company)
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
        # Apply HRZN-specific heuristic cleanup for concatenated XBRL identifiers
        res['company_name'] = self._heuristic_clean_hrzn_name(re.sub(r'\s+',' ', clean_company).rstrip(','))
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
        # Extract standard XBRL facts and capture unitRef for currency
        sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*(?:unitRef="([^"]*)")?[^>]*>([^<]*)</\1>', re.DOTALL)
        for match in sp.finditer(content):
            concept = match.group(1)
            cref = match.group(2)
            unit_ref = match.group(3)
            val = match.group(4)
            if val and cref:
                fact_entry = {'concept': concept, 'value': val.strip()}
                # Extract currency from unitRef if present
                if unit_ref:
                    currency_match = re.search(r'\b([A-Z]{3})\b', unit_ref.upper())
                    if currency_match:
                        fact_entry['currency'] = currency_match.group(1)
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
                    if currency_match:
                        fact_entry['currency'] = currency_match.group(1)
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
                seen = set()
                unique_dates = []
                for d in dates:
                    if d not in seen:
                        seen.add(d)
                        unique_dates.append(d)
                if len(unique_dates)>=2:
                    facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[-1]})
                elif len(unique_dates)==1:
                    date_idx = window.find(unique_dates[0])
                    date_context = window[max(0, date_idx-50):min(len(window), date_idx+50)]
                    if re.search(r'\b(acquisition|origination|investment|purchase|initial)\s+date\b', date_context, re.IGNORECASE):
                        facts[cref].append({'concept':'derived:AcquisitionDate','value': unique_dates[0]})
                    else:
                        facts[cref].append({'concept':'derived:MaturityDate','value': unique_dates[0]})
        return facts

    def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[HRZNInvestment]:
        if context['company_name']=='Unknown':
            return None
        inv = HRZNInvestment(
            company_name=context['company_name'],
            investment_type=context['investment_type'],
            industry=context['industry'],
            context_ref=context['id']
        )
        # Extract tokens from raw identifier and clean name
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
            # Extract shares/units for equity investments
            if any(k in cl for k in ['numberofshares','sharesoutstanding','unitsoutstanding','sharesheld','unitsheld']):
                try: 
                    shares_val = v.strip().replace(',', '')
                    float(shares_val)  # Validate
                    inv.shares_units = shares_val
                except: pass
                continue
            # Extract currency from fact metadata
            if 'currency' in f:
                inv.currency = f.get('currency')
        # Fill missing from tokens
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
        # Heuristic for commitment_limit and undrawn_commitment
        if inv.fair_value and not inv.principal_amount:
            inv.commitment_limit = inv.fair_value
        elif inv.fair_value and inv.principal_amount:
            if inv.fair_value > inv.principal_amount:
                inv.commitment_limit = inv.fair_value
                inv.undrawn_commitment = inv.fair_value - inv.principal_amount
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

    def _heuristic_clean_hrzn_name(self, text: str) -> str:
        t = text
        # Remove generic prefixes
        t = re.sub(r'^Nonaffiliate\s*Debt\s*Investments\s*', '', t, flags=re.IGNORECASE)
        # Common domain markers
        domains = ['Life Science', 'Technology', 'Healthcare', 'Software']
        for d in domains:
            t = re.sub(rf'^{d}\s*', '', t, flags=re.IGNORECASE)
        # Remove trailing instrument descriptors
        t = re.sub(r'(Biotechnology|Pharmaceuticals|Software|Healthcare).*$', '', t, flags=re.IGNORECASE)
        # Remove trailing Member
        t = re.sub(r'Term\s*Loan.*$', '', t, flags=re.IGNORECASE)
        t = re.sub(r'Member$', '', t, flags=re.IGNORECASE)
        # Normalize spaces
        t = re.sub(r'\s+', ' ', t).strip(' ,.-')
        return t if t else text

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
    ex=HRZNExtractor()
    try:
        res=ex.extract_from_ticker('HRZN')
        print(f"Extracted {res['total_investments']} investments")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__=='__main__':
    main()




