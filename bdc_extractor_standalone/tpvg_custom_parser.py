#!/usr/bin/env python3
"""
TPVG (TriplePoint Venture Growth BDC) Custom Investment Extractor
Extracts investment data directly from SEC filings HTML tables.
"""

import logging
import os
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import requests
import csv
from collections import defaultdict
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(__file__))
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class TPVGCustomExtractor:
    """Custom extractor for TPVG that extracts data from SEC filings HTML tables."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "TPVG", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from TPVG's latest 10-Q filing."""
        logger.info(f"Extracting investments for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise RuntimeError("Could not resolve CIK for TPVG")
        
        logger.info(f"Found CIK: {cik}")
        
        index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik, year=year, min_date=min_date)
        if not index_url:
            raise RuntimeError("Could not locate latest 10-Q index for TPVG")
        
        logger.info(f"Filing index: {index_url}")
        
        # Get HTML documents - process all HTML files like the original parser
        documents = self.sec_client.get_documents_from_index(index_url)
        html_docs = [d for d in documents if d.filename.lower().endswith('.htm') and 'index' not in d.filename.lower()]
        
        if not html_docs:
            raise RuntimeError("Could not find HTML document")
        
        logger.info(f"Found {len(html_docs)} HTML documents")
        
        # Extract investments from all HTML documents
        all_investments = []
        for doc in html_docs:
            try:
                logger.info(f"Processing {doc.filename}")
                investments = self._parse_html_table(doc.url)
                all_investments.extend(investments)
                logger.info(f"Extracted {len(investments)} investments from {doc.filename}")
            except Exception as e:
                logger.warning(f"Failed to process {doc.filename}: {e}")
                continue
        
        # Deduplicate across all documents
        investments = self._deduplicate_investments(all_investments)
        logger.info(f"Total unique investments after deduplication: {len(investments)}")
        
        # Recalculate totals
        total_principal = sum(inv.get('principal_amount') or 0 for inv in investments)
        total_cost = sum(inv.get('cost') or 0 for inv in investments)
        total_fair_value = sum(inv.get('fair_value') or 0 for inv in investments)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for inv in investments:
            industry_breakdown[inv.get('industry', 'Unknown')] += 1
            investment_type_breakdown[inv.get('investment_type', 'Unknown')] += 1
        
        # Save to CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, 'TPVG_TriplePoint_Venture_Growth_BDC_investments.csv')
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'company_name', 'industry', 'business_description', 'investment_type',
                'acquisition_date', 'maturity_date', 'principal_amount', 'cost', 'fair_value',
                'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate',
                'shares_units', 'percent_net_assets', 'currency', 'commitment_limit', 'undrawn_commitment'
            ])
            writer.writeheader()
            for inv in investments:
                writer.writerow({
                    'company_name': inv.get('company_name', ''),
                    'industry': inv.get('industry', 'Unknown'),
                    'business_description': inv.get('business_description', ''),
                    'investment_type': inv.get('investment_type', 'Unknown'),
                    'acquisition_date': inv.get('acquisition_date', ''),
                    'maturity_date': inv.get('maturity_date', ''),
                    'principal_amount': inv.get('principal_amount', ''),
                    'cost': inv.get('cost', ''),
                    'fair_value': inv.get('fair_value', ''),
                    'interest_rate': inv.get('interest_rate', ''),
                    'reference_rate': inv.get('reference_rate', ''),
                    'spread': inv.get('spread', ''),
                    'floor_rate': inv.get('floor_rate', ''),
                    'pik_rate': inv.get('pik_rate', ''),
                    'shares_units': inv.get('shares_units', ''),
                    'percent_net_assets': inv.get('percent_net_assets', ''),
                    'currency': inv.get('currency', 'USD'),
                    'commitment_limit': inv.get('commitment_limit', ''),
                    'undrawn_commitment': inv.get('undrawn_commitment', ''),
                })
        
        logger.info(f"Saved {len(investments)} investments to {output_file}")
        
        return {
            'company_name': 'TriplePoint Venture Growth BDC',
            'cik': cik,
            'total_investments': len(investments),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _parse_html_table(self, html_url: str) -> List[Dict]:
        """Parse TPVG's HTML schedule of investments table."""
        
        logger.info(f"Fetching HTML from {html_url}")
        resp = requests.get(html_url, headers=self.headers)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Find schedule tables using the same logic as the original parser
        tables = self._extract_tables_under_heading(soup)
        logger.info(f"Found {len(tables)} schedule tables")
        
        all_investments = []
        
        for table in tables:
            rows = self._table_to_rows(table)
            if not rows:
                continue
            
            # Find header map
            header_map = self._find_header_map(rows)
            
            # Parse investments from this table
            investments = self._parse_section_table(rows, header_map)
            all_investments.extend(investments)
        
        # Post-process: fix continuation rows and carry-forward data
        all_investments = self._post_process_investments(all_investments)
        
        return all_investments
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text by collapsing whitespace."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()
    
    def _normalize_key(self, text: str) -> str:
        """Normalize text for key matching."""
        return self._normalize_text(text).lower()
    
    def _strip_footnote_refs(self, text: Optional[str]) -> str:
        """Remove footnote references from text."""
        if not text:
            return ""
        cleaned = re.sub(r"(?:\s*\(\s*\d+\s*\))+", "", text)
        return self._normalize_text(cleaned)
    
    def _normalize_date(self, date_str: Optional[str]) -> Optional[str]:
        """Convert date from MM/DD/YYYY or MM/DD/YY to ISO format YYYY-MM-DD."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Try MM/DD/YYYY format
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
        if match:
            month, day, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Try MM/DD/YY format (2-digit year)
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2})$", date_str)
        if match:
            month, day, year = match.groups()
            # Assume years 00-30 are 2000-2030, 31-99 are 1931-1999
            year_int = int(year)
            if year_int <= 30:
                year = f"20{year}"
            else:
                year = f"19{year}"
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # If already in ISO format, return as-is
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return date_str
        
        # If we can't parse it, return as-is
        return date_str
    
    def _extract_tables_under_heading(self, soup: BeautifulSoup) -> List:
        """Extract tables that are schedule of investments tables."""
        matches = []
        
        def contains_date_like(blob: str) -> bool:
            return re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", blob, re.IGNORECASE) is not None
        
        required_any = [
            "schedule of investments",
            "continued",
            "unaudited",
            "dollar amounts in thousands",
        ]
        
        def heading_matches(blob: str) -> bool:
            blob_l = blob.lower()
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
                txt = self._normalize_key(prev if isinstance(prev, str) else prev.get_text(" ", strip=True))
                if txt:
                    context_texts.append(txt)
                cur = prev.parent if hasattr(prev, "parent") else None
                if not cur:
                    break
            context_blob = " ".join(context_texts)
            if heading_matches(context_blob):
                matches.append(table)
        
        # Fallback: detect by header row keywords
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
                header_blob = " ".join(self._normalize_key(x.get_text(" ", strip=True)) for x in rows[:3])
                for keys in key_sets:
                    if all(k in header_blob for k in keys):
                        matches.append(table)
                        break
        
        return matches
    
    def _table_to_rows(self, table) -> List[List[str]]:
        """Convert table to list of row cell texts."""
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            vals = []
            for c in cells:
                txt = c.get_text(" ", strip=True)
                txt = txt.replace("\u200b", "").replace("\xa0", " ")
                vals.append(self._normalize_text(txt))
            rows.append(vals)
        return rows
    
    def _compact_row(self, cells: List[str]) -> List[str]:
        """Compact row by merging $ with numbers and numbers with %."""
        filtered = [x for x in cells if x not in ("", "-")]
        merged = []
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
    
    def _find_header_map(self, rows: List[List[str]]) -> Optional[Dict[str, int]]:
        """Find header mapping for table columns."""
        for r in rows[:12]:
            header_cells = self._compact_row(r)
            keys = [self._normalize_key(c) for c in header_cells]
            
            def find_idx(patterns: List[str]) -> Optional[int]:
                for i, k in enumerate(keys):
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
                return {
                    "company": idx_company,
                    "type": idx_type,
                    "floor": -1 if idx_floor is None else idx_floor,
                    "ref": -1 if idx_ref is None else idx_ref,
                    "spread": -1 if idx_spread is None else idx_spread,
                    "rate": -1 if idx_rate is None else idx_rate,
                    "acq": -1 if idx_acq is None else idx_acq,
                    "mat": -1 if idx_mat is None else idx_mat,
                    "prin": idx_prin,
                    "cost": -1 if idx_cost is None else idx_cost,
                    "fv": idx_fv,
                    "pct": -1 if idx_pct is None else idx_pct
                }
        return None
    
    def _parse_section_table(self, rows: List[List[str]], header_map: Optional[Dict]) -> List[Dict]:
        """Parse a section table into investment records."""
        records = []
        
        def has_percent(tokens: List[str]) -> bool:
            return any(re.search(r"\d(\.\d+)?%$", t) or " % " in f" {t} " or "cash /" in t.lower() or "pik" in t.lower() for t in tokens)
        
        def has_spread_token(tokens: List[str]) -> bool:
            return any(t.upper().startswith(("SOFR+","PRIME+","LIBOR+","BASE RATE+","SOFR","PRIME","LIBOR","BASE RATE")) for t in tokens)
        
        def has_date(tokens: List[str]) -> bool:
            return any(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", t) for t in tokens)
        
        def is_section_header(text: str) -> bool:
            t = text.lower()
            return any(k in t for k in ["investments","non-control","non-affiliate"])
        
        last_company = None
        last_industry = None
        
        for r in rows:
            row = self._compact_row(r)
            if not row:
                continue
            
            row_l = " ".join(self._normalize_key(c) for c in row)
            if all(tok in row_l for tok in ["issuer","investment","fair","value"]) and ("acquisition" in row_l or "maturity" in row_l):
                continue
            
            first = row[0]
            if is_section_header(first):
                continue
            
            detail_signals = has_percent(row) or has_spread_token(row) or has_date(row)
            first_l = self._normalize_key(first)
            
            # If the first cell looks like an instrument type, force detail
            if any(k in first_l for k in ["loan","revolver","convertible","warrant","equity","note"]):
                detail_signals = True
            
            # If the first cell looks like a company name and does NOT look like an instrument label, treat as company row
            nameish = ("," in first) or bool(re.search(r"\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|holdings|group|s\.à\s*r\.l\.|limited|plc)\b", first, re.IGNORECASE))
            if nameish and not any(k in first_l for k in ["loan","revolver","convertible","warrant","equity","note"]):
                detail_signals = False
            
            if first and not detail_signals:
                # This is a company/industry header row
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
                        if re.match(r"^\$?\d[\d,]*$", txt):
                            continue
                        if has_percent([txt]) or has_date([txt]) or has_spread_token([txt]):
                            continue
                        if re.search(r"[A-Za-z]", txt):
                            cand_ind = txt
                            break
                    if cand_ind:
                        last_industry = cand_ind
                continue
            
            # This is a detail row - parse it
            record = self._parse_detail_row(row, header_map, last_company, last_industry)
            if record:
                if record.get('company_name'):
                    last_company = record['company_name']
                if record.get('industry') and record['industry'] != "Unknown":
                    last_industry = record['industry']
                records.append(record)
        
        return records
    
    def _parse_detail_row(self, row: List[str], header_map: Optional[Dict], last_company: Optional[str], last_industry: Optional[str]) -> Optional[Dict]:
        """Parse a detail row into an investment record."""
        try:
            inv_type = row[0].strip() if row else ""
            
            # Enhanced percentage extraction - search all cells comprehensively
            row_text = ' '.join(row).upper()
            
            # Extract reference rate and spread from patterns like "PRIME + 2.50%", "SOFR + 6.00%"
            ref_token = None
            spread_val = None
            interest_rate = None
            floor_rate_val = None
            pik_rate_val = None
            
            # Pattern 1: "PRIME + 2.50%" or "SOFR + 6.00%" in a single cell or across cells
            ref_spread_pattern = re.search(
                r'\b(SOFR|LIBOR|PRIME|PRIME\s+RATE|BASE\s+RATE|EURIBOR)(?:\s*\([^)]*\))?\s*\+\s*([\d\.]+)\s*%',
                row_text, re.IGNORECASE
            )
            if ref_spread_pattern:
                ref_base = ref_spread_pattern.group(1).strip().upper()
                # Normalize reference rate names
                ref_map = {'PRIME RATE': 'PRIME', 'BASE RATE': 'BASE RATE', 'BASE': 'BASE RATE'}
                ref_base = ref_map.get(ref_base, ref_base)
                ref_token = ref_base
                spread_val = f"{float(ref_spread_pattern.group(2)):.2f}%"
            
            # Pattern 2: Look for reference rate and spread in separate cells
            if not ref_token or not spread_val:
                for i, c in enumerate(row):
                    cu = c.upper().strip()
                    # Check for reference rate tokens
                    if not ref_token:
                        ref_match = re.match(r'^(SOFR|LIBOR|PRIME|PRIME\s+RATE|BASE\s+RATE|EURIBOR)(?:\s*\([^)]*\))?$', cu, re.IGNORECASE)
                        if ref_match:
                            ref_base = ref_match.group(1).strip().upper()
                            ref_map = {'PRIME RATE': 'PRIME', 'BASE RATE': 'BASE RATE', 'BASE': 'BASE RATE'}
                            ref_token = ref_map.get(ref_base, ref_base)
                    
                    # Check for spread patterns like "SOFR+", "PRIME+"
                    if not spread_val and any(cu.startswith(tok) for tok in ["SOFR+", "PRIME+", "LIBOR+", "BASE RATE+"]):
                        if i+1 < len(row):
                            nxt = row[i+1].strip()
                            if nxt.endswith('%'):
                                spread_val = nxt
                            elif re.match(r'^\d+(\.\d+)?$', nxt):
                                spread_val = f"{nxt}%"
                        # Also check if spread is in the same cell
                        spread_in_cell = re.search(r'\+?\s*([\d\.]+)\s*%', c, re.IGNORECASE)
                        if spread_in_cell:
                            spread_val = f"{float(spread_in_cell.group(1)):.2f}%"
            
            # Extract interest rate - look for percentage values that are reasonable interest rates
            if not interest_rate:
                for c in row:
                    # Look for patterns like "11.75%", "2.50%", etc.
                    rate_match = re.search(r'([\d\.]+)\s*%', c)
                    if rate_match:
                        rate_val = float(rate_match.group(1))
                        # Reasonable interest rate range (0.1% to 30%)
                        if 0.1 <= rate_val <= 30:
                            # Check if this cell doesn't already contain reference rate or spread keywords
                            c_upper = c.upper()
                            if not any(kw in c_upper for kw in ['PIK', 'FLOOR', 'EOT', 'CASH', 'INTEREST']):
                                interest_rate = f"{rate_val:.2f}%"
                                break
            
            # Extract floor rate
            floor_match = re.search(r'floor\s*[:\s]*([\d\.]+)\s*%', row_text, re.IGNORECASE)
            if floor_match:
                floor_rate_val = f"{float(floor_match.group(1)):.2f}%"
            
            # Extract PIK rate
            pik_match = re.search(r'pik\s*(?:interest\s*)?[:\s]*([\d\.]+)\s*%', row_text, re.IGNORECASE)
            if pik_match:
                pik_rate_val = f"{float(pik_match.group(1)):.2f}%"
            
            company_for_row = last_company or ""
            acq = None
            mat = None
            money = []
            
            if header_map:
                def get(idx: int) -> Optional[str]:
                    return row[idx] if 0 <= idx < len(row) else None
                
                company_cell = get(header_map.get('company', -1))
                it_cell = get(header_map.get('type', -1))
                ref_cell = get(header_map.get('ref', -1))
                rate_cell = get(header_map.get('rate', -1))
                spread_cell = get(header_map.get('spread', -1))
                acq_cell = get(header_map.get('acq', -1))
                mat_cell = get(header_map.get('mat', -1))
                prin_cell = get(header_map.get('prin', -1))
                cost_cell = get(header_map.get('cost', -1))
                fv_cell = get(header_map.get('fv', -1))
                
                if company_cell and self._normalize_key(company_cell).startswith('total '):
                    return None
                
                if it_cell and not re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", it_cell):
                    inv_type = it_cell
                
                if rate_cell and re.search(r"%", rate_cell):
                    interest_rate = rate_cell
                
                if spread_cell and re.search(r"%", spread_cell):
                    spread_val = spread_cell
                
                if ref_cell:
                    ref_token = ref_cell
                
                acq_raw = acq_cell if (acq_cell and re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", acq_cell)) else None
                mat_raw = mat_cell if (mat_cell and re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", mat_cell)) else None
                acq = self._normalize_date(acq_raw)
                mat = self._normalize_date(mat_raw)
                
                nameish_cc = bool(company_cell) and ("," in company_cell or re.search(r"\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|holdings|group|s\.à\s*r\.l\.|limited|plc)\b", company_cell, re.IGNORECASE))
                is_instrument_cc = bool(company_cell) and any(k in self._normalize_key(company_cell) for k in ["loan","revolver","convertible","warrant","equity","note"])
                
                if nameish_cc and not is_instrument_cc:
                    company_for_row = company_cell
                else:
                    company_for_row = last_company or ""
                
                money = [prin_cell, cost_cell, fv_cell]
            else:
                company_for_row = last_company or ""
                dates_raw = [c for c in row if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", c)]
                acq = self._normalize_date(dates_raw[0]) if dates_raw else None
                mat = self._normalize_date(dates_raw[1]) if len(dates_raw) > 1 else None
                money = [c for c in row if c.startswith('$') or re.match(r"^\$?\d[\d,]*$", c)]
                
                for tok in row:
                    m = re.match(r"^(SOFR|SONIA|PRIME|LIBOR|BASE RATE|EURIBOR)(?:\s*\([^)]*\))?$", tok, re.IGNORECASE)
                    if m:
                        ref_token = tok
                        break
            
            # Parse terms from investment type
            def parse_terms_from_type(type_text: str) -> Dict[str, Optional[str]]:
                res = {"ref": None, "spread": None, "floor": None, "pik": None, "eot": None, "fixed": None}
                t = type_text or ""
                m = re.search(r"\b(SOFR(?:\s*\([^)]*\))?|PRIME|LIBOR|EURIBOR|BASE\s*RATE)\b", t, re.IGNORECASE)
                if m:
                    res["ref"] = m.group(1)
                m = re.search(r"(?:Prime|SOFR|LIBOR|EURIBOR|Base\s*Rate)\s*\+\s*([\d\.]+)\s*%\s*(?:cash\s+)?interest\s*rate", t, re.IGNORECASE)
                if m:
                    res["spread"] = f"{m.group(1)}%"
                m = re.search(r"([\d\.]+)\s*%\s*interest\s*rate", t, re.IGNORECASE)
                if m:
                    res["fixed"] = f"{m.group(1)}%"
                m = re.search(r"([\d\.]+)\s*%\s*PIK\s*interest", t, re.IGNORECASE)
                if m:
                    res["pik"] = f"{m.group(1)}%"
                m = re.search(r"([\d\.]+)\s*%\s*floor", t, re.IGNORECASE)
                if m:
                    res["floor"] = f"{m.group(1)}%"
                m = re.search(r"([\d\.]+)\s*%\s*EOT\s*payment", t, re.IGNORECASE)
                if m:
                    res["eot"] = f"{m.group(1)}%"
                return res
            
            # Parse terms from investment type text (fallback)
            terms = parse_terms_from_type(inv_type) if inv_type else {}
            if not ref_token and terms.get("ref"):
                ref_token = terms["ref"]
            if not spread_val and terms.get("spread"):
                spread_val = terms["spread"]
            if not interest_rate and terms.get("fixed"):
                interest_rate = terms["fixed"]
            if not floor_rate_val and terms.get("floor"):
                floor_rate_val = terms.get("floor")
            if not pik_rate_val and terms.get("pik"):
                pik_rate_val = terms.get("pik")
            
            # Parse numbers
            def parse_number_local(text: Optional[str]) -> Optional[float]:
                if not text:
                    return None
                t = text.replace("\xa0", " ").replace(",", "").strip().replace('$', '')
                if t in ("—", "—%", "— $"):
                    return None
                if t.endswith('%'):
                    try:
                        return float(t[:-1])
                    except:
                        return None
                try:
                    return float(t)
                except:
                    return None
            
            principal = parse_number_local(money[0]) if len(money) >= 1 else None
            cost = parse_number_local(money[1]) if len(money) >= 2 else None
            fair_value = parse_number_local(money[2]) if len(money) >= 3 else None
            
            # Clean company name
            company_clean = self._strip_footnote_refs(company_for_row or "")
            if (not company_clean) or re.search(r"\b(loan|revolver|convertible|warrant|equity|note)\b", self._normalize_key(company_clean)) or re.match(r"^(\$?\d[\d,]*|\d{1,2}/\d{1,2}/\d{2,4})$", company_clean):
                if last_company:
                    company_clean = last_company
            
            # Normalize investment type
            base_type = self._normalize_key(inv_type or "")
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
                inv_type_norm = (inv_type or '').split('(')[0].strip() or (inv_type or '')
            
            inv_type_clean = self._strip_footnote_refs(inv_type_norm)
            
            # Extract company name and investment type from combined string if needed
            # Handle patterns like "Company Name, Equity Investments" or "Company Name, Warrants"
            if ',' in company_clean:
                # Try to split on comma and extract investment type
                parts = company_clean.split(',')
                base_company = parts[0].strip()
                type_part = ','.join(parts[1:]).strip()
                type_part = self._strip_footnote_refs(type_part)
                
                # Check if the part after comma looks like an investment type
                type_part_lower = type_part.lower()
                if any(keyword in type_part_lower for keyword in [
                    'equity investment', 'equity investments', 'warrant investment', 
                    'warrant investments', 'warrants', 'warrant', 'equity', 'loan',
                    'revolver', 'note', 'convertible', 'preferred', 'common'
                ]):
                    # This is an investment type, extract it
                    company_clean = base_company
                    if not inv_type_clean or inv_type_clean == "Unknown":
                        # Normalize the investment type
                        if 'equity investment' in type_part_lower:
                            inv_type_clean = 'Equity'
                        elif 'warrant investment' in type_part_lower or 'warrants' in type_part_lower:
                            inv_type_clean = 'Warrants'
                        elif 'warrant' in type_part_lower:
                            inv_type_clean = 'Warrants'
                        else:
                            inv_type_clean = type_part
                else:
                    # Might be part of company name (e.g., "Inc., LLC")
                    # Keep the full name but check if it contains investment type keywords
                    pass
            
            # If still no investment type, try to infer from company name
            if not inv_type_clean or inv_type_clean == "Unknown":
                orig_name_lower = (company_clean or last_company or "").lower()
                if 'equity investment' in orig_name_lower or ', equity' in orig_name_lower:
                    inv_type_clean = 'Equity'
                elif 'warrant investment' in orig_name_lower or ', warrant' in orig_name_lower:
                    inv_type_clean = 'Warrants'
                elif 'warrants' in orig_name_lower:
                    inv_type_clean = 'Warrants'
                elif any(kw in orig_name_lower for kw in ['loan', 'revolver', 'note']):
                    inv_type_clean = 'Loan'
                else:
                    inv_type_clean = "Unknown"
            
            industry_clean = self._strip_footnote_refs(last_industry or "")
            if not industry_clean or re.match(r"^\$?\d[\d,]*$", industry_clean):
                industry_clean = "Unknown"
            
            # Must have at least principal or fair value
            has_money = any([principal, cost, fair_value])
            has_dates = bool(acq or mat)
            if not company_clean and not has_money and not has_dates:
                return None
            
            # Standardize
            inv_type_clean = standardize_investment_type(inv_type_clean)
            industry_clean = standardize_industry(industry_clean)
            ref_token = standardize_reference_rate(ref_token) if ref_token else None
            
            # Normalize dates to ISO format
            acq_normalized = self._normalize_date(acq) if acq else None
            mat_normalized = self._normalize_date(mat) if mat else None
            
            return {
                'company_name': company_clean,
                'business_description': "",
                'investment_type': inv_type_clean,
                'industry': industry_clean,
                'acquisition_date': acq_normalized,
                'maturity_date': mat_normalized,
                'interest_rate': interest_rate,
                'reference_rate': ref_token,
                'spread': spread_val,
                'floor_rate': floor_rate_val,
                'pik_rate': pik_rate_val,
                'principal_amount': int(principal) if principal else None,
                'cost': int(cost) if cost else None,
                'fair_value': int(fair_value) if fair_value else None,
            }
        
        except Exception as e:
            logger.warning(f"Failed to parse detail row: {e}")
            return None
    
    def _post_process_investments(self, investments: List[Dict]) -> List[Dict]:
        """Post-process investments to fix continuation rows and carry-forward data."""
        # First pass: extract investment types from company names and clean them
        for inv in investments:
            company_name = (inv.get('company_name') or '').strip()
            inv_type = (inv.get('investment_type') or '').strip()
            
            # If investment type is Unknown but company name has investment type info, extract it
            if (not inv_type or inv_type == "Unknown") and ',' in company_name:
                parts = company_name.split(',')
                base_company = parts[0].strip()
                type_part = ','.join(parts[1:]).strip()
                type_part_lower = type_part.lower()
                
                # Check if the part after comma is an investment type
                if any(keyword in type_part_lower for keyword in [
                    'equity investment', 'equity investments', 'warrant investment', 
                    'warrant investments', 'warrants', 'warrant'
                ]):
                    # Extract investment type
                    if 'equity investment' in type_part_lower:
                        inv['investment_type'] = 'Equity'
                    elif 'warrant investment' in type_part_lower or 'warrants' in type_part_lower:
                        inv['investment_type'] = 'Warrants'
                    elif 'warrant' in type_part_lower:
                        inv['investment_type'] = 'Warrants'
                    else:
                        inv['investment_type'] = type_part
                    
                    # Clean company name
                    inv['company_name'] = base_company
        
        # Fix continuation rows
        last_good_company = None
        for inv in investments:
            name = (inv.get('company_name') or '').strip()
            name_l = self._normalize_key(name)
            is_bad = (
                (not name) or
                bool(re.match(r'^\$?\d[\d,]*$', name)) or
                bool(re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', name)) or
                any(k in name_l for k in ['loan','revolver','convertible','warrant','equity','note'])
            )
            if is_bad and last_good_company:
                inv['company_name'] = last_good_company
            elif not is_bad:
                last_good_company = name
        
        # Carry-forward industry, dates, and percentage values
        last_company = None
        last_industry_by_company = {}
        last_dates_by_company = {}
        last_rates_by_company = {}
        
        for inv in investments:
            cname = inv.get('company_name') or ''
            if cname:
                last_company = cname
            
            if not last_company:
                continue
            
            # Industry carry-forward
            ind = (inv.get('industry') or '').strip()
            if ind and ind != "Unknown":
                last_industry_by_company[last_company] = ind
            elif last_company in last_industry_by_company:
                inv['industry'] = last_industry_by_company[last_company]
            
            # Dates carry-forward
            acq = inv.get('acquisition_date') or ''
            mat = inv.get('maturity_date') or ''
            # Normalize dates if they're not already in ISO format
            if acq and not re.match(r"^\d{4}-\d{2}-\d{2}$", acq):
                acq = self._normalize_date(acq) or ''
            if mat and not re.match(r"^\d{4}-\d{2}-\d{2}$", mat):
                mat = self._normalize_date(mat) or ''
            
            if acq or mat:
                last_dates_by_company[last_company] = {
                    'acq': acq or last_dates_by_company.get(last_company, {}).get('acq'),
                    'mat': mat or last_dates_by_company.get(last_company, {}).get('mat')
                }
            else:
                prev = last_dates_by_company.get(last_company)
                if prev:
                    if not acq and prev.get('acq'):
                        inv['acquisition_date'] = prev.get('acq')
                    if not mat and prev.get('mat'):
                        inv['maturity_date'] = prev.get('mat')
            
            # Percentage values carry-forward (for same company, same investment type)
            # Only carry forward if current values are missing
            if last_company in last_rates_by_company:
                prev_rates = last_rates_by_company[last_company]
                if not inv.get('interest_rate') and prev_rates.get('interest_rate'):
                    inv['interest_rate'] = prev_rates.get('interest_rate')
                if not inv.get('reference_rate') and prev_rates.get('reference_rate'):
                    inv['reference_rate'] = prev_rates.get('reference_rate')
                if not inv.get('spread') and prev_rates.get('spread'):
                    inv['spread'] = prev_rates.get('spread')
                if not inv.get('floor_rate') and prev_rates.get('floor_rate'):
                    inv['floor_rate'] = prev_rates.get('floor_rate')
                if not inv.get('pik_rate') and prev_rates.get('pik_rate'):
                    inv['pik_rate'] = prev_rates.get('pik_rate')
            
            # Update last rates for this company if we have any new values
            if any([inv.get('interest_rate'), inv.get('reference_rate'), inv.get('spread'), 
                   inv.get('floor_rate'), inv.get('pik_rate')]):
                last_rates_by_company[last_company] = {
                    'interest_rate': inv.get('interest_rate') or last_rates_by_company.get(last_company, {}).get('interest_rate'),
                    'reference_rate': inv.get('reference_rate') or last_rates_by_company.get(last_company, {}).get('reference_rate'),
                    'spread': inv.get('spread') or last_rates_by_company.get(last_company, {}).get('spread'),
                    'floor_rate': inv.get('floor_rate') or last_rates_by_company.get(last_company, {}).get('floor_rate'),
                    'pik_rate': inv.get('pik_rate') or last_rates_by_company.get(last_company, {}).get('pik_rate')
                }
        
        # Deduplicate
        seen = set()
        deduped = []
        for inv in investments:
            company = (inv.get('company_name') or '').strip()
            inv_type = (inv.get('investment_type') or '').strip()
            principal = inv.get('principal_amount')
            cost = inv.get('cost')
            fair_value = inv.get('fair_value')
            
            key = (
                company.lower(),
                inv_type.lower(),
                principal if principal is not None else 0,
                cost if cost is not None else 0,
                fair_value if fair_value is not None else 0
            )
            
            if key not in seen:
                seen.add(key)
                deduped.append(inv)
        
        return deduped
    
    def _is_schedule_table(self, rows: List) -> bool:
        """Check if this is a schedule of investments table."""
        if not rows or len(rows) < 3:
            return False
        
        # Check first few rows for schedule indicators
        header_text = " ".join([cell.get_text(" ", strip=True) for row in rows[:10] 
                               for cell in row.find_all(['td', 'th'])]).lower()
        
        schedule_keywords = [
            'issuer', 'investment', 'principal', 'cost', 'fair value',
            'maturity', 'interest rate', 'reference rate', 'spread', 'company name',
            'amortized cost', 'outstanding principal', 'loan', 'debt', 'equity',
            'industry', 'rate', 'floor', 'warrant', 'equity investment'
        ]
        
        matches = sum(1 for keyword in schedule_keywords if keyword in header_text)
        
        # Also check if table has many columns (schedule tables are usually wide)
        if len(rows) > 0:
            first_row_cells = len(rows[0].find_all(['td', 'th']))
            if first_row_cells >= 6 and matches >= 2:
                return True
        
        # Need at least 3 matching keywords OR issuer + financial data
        has_issuer = 'issuer' in header_text
        has_financial_data = any(kw in header_text for kw in ['principal', 'cost', 'fair value', 'amortized'])
        
        if has_issuer and has_financial_data:
            return True
        
        return matches >= 3
    
    def _is_header_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a table header row."""
        if not cell_texts:
            return False
        
        header_keywords = ['Issuer', 'Investment Type', 'Industry', 'Rate', 'Floor', 
                          'Maturity', 'Principal', 'Amortized Cost', 'Fair Value',
                          'Outstanding Principal', 'Acquisition Date', 'Maturity Date']
        
        first_few = ' '.join(cell_texts[:8]).lower()
        return any(keyword.lower() in first_few for keyword in header_keywords)
    
    def _is_total_row(self, cell_texts: List[str]) -> bool:
        """Check if this is a total/summary row."""
        if not cell_texts:
            return False
        
        first_col = cell_texts[0].lower() if len(cell_texts) > 0 else ""
        return "total" in first_col
    
    def _deduplicate_investments(self, investments: List[Dict]) -> List[Dict]:
        """Deduplicate investments across multiple documents."""
        seen = set()
        deduped = []
        
        for inv in investments:
            company = (inv.get('company_name') or '').strip()
            inv_type = (inv.get('investment_type') or '').strip()
            principal = inv.get('principal_amount')
            cost = inv.get('cost')
            fair_value = inv.get('fair_value')
            acq_date = (inv.get('acquisition_date') or '').strip()
            mat_date = (inv.get('maturity_date') or '').strip()
            
            # Create deduplication key: company + type + principal + dates
            key = (
                company.lower(),
                inv_type.lower(),
                principal if principal is not None else 0,
                acq_date.lower(),
                mat_date.lower()
            )
            
            if key not in seen:
                seen.add(key)
                deduped.append(inv)
            else:
                # If we've seen this key, keep the one with more complete data
                existing_idx = next((i for i, rec in enumerate(deduped) if 
                    (rec.get('company_name') or '').strip().lower() == company.lower() and
                    (rec.get('investment_type') or '').strip().lower() == inv_type.lower() and
                    rec.get('principal_amount') == principal and
                    (rec.get('acquisition_date') or '').strip().lower() == acq_date.lower() and
                    (rec.get('maturity_date') or '').strip().lower() == mat_date.lower()), None)
                
                if existing_idx is not None:
                    existing = deduped[existing_idx]
                    # Prefer record with non-null cost or fair_value
                    if (inv.get('cost') is not None or inv.get('fair_value') is not None) and \
                       existing.get('cost') is None and existing.get('fair_value') is None:
                        deduped[existing_idx] = inv
        
        return deduped
    
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    extractor = TPVGCustomExtractor()
    result = extractor.extract_from_ticker("TPVG")
    
    print(f"\n[SUCCESS] Extracted {result['total_investments']} investments for TriplePoint Venture Growth BDC")
    print(f"  Total Principal: ${result['total_principal']:,.0f}")
    print(f"  Total Cost: ${result['total_cost']:,.0f}")
    print(f"  Total Fair Value: ${result['total_fair_value']:,.0f}")


if __name__ == "__main__":
    main()

