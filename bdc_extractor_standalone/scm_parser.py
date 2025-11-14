#!/usr/bin/env python3
"""
SCM (Stellus Capital Investment Corp) Investment Extractor
HTML-based extraction following HTML_SCHEDULE_WORKFLOW.md
"""

import re
import os
import csv
import logging
import requests
from typing import List, Dict, Optional
from collections import defaultdict
from bs4 import BeautifulSoup
from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)


class SCMExtractor:
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)

    def extract_from_ticker(self, ticker: str = "SCM") -> Dict:
        """Extract investments from SCM's latest 10-Q filing using HTML tables."""
        logger.info(f"Extracting investments for {ticker}")
        
        # Get CIK
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for ticker {ticker}")
        
        logger.info(f"Found CIK: {cik}")
        
        # Get latest 10-Q filing URL
        filing_index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
        if not filing_index_url:
            # Try 10-K as fallback
            filing_index_url = self.sec_client.get_filing_index_url(ticker, "10-K", cik=cik)
            if not filing_index_url:
                raise ValueError(f"Could not find 10-Q or 10-K filing for {ticker}")
        
        logger.info(f"Found filing index: {filing_index_url}")
        
        # Get documents from index
        documents = self.sec_client.get_documents_from_index(filing_index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith(".htm")), None)
        if not main_html:
            raise ValueError(f"No main HTML document found for {ticker}")
        
        logger.info(f"Found main HTML: {main_html.url}")
        
        # Extract investments from HTML
        return self.extract_from_html_url(main_html.url, "Stellus_Capital_Investment_Corp", cik)
    
    def extract_from_html_url(self, html_url: str, company_name: str, cik: str) -> Dict:
        """Extract investments from SCM HTML filing URL."""
        
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
            return self._fallback_to_xbrl(html_url, company_name, cik)
        
        # Save simplified tables for QA
        self._save_simplified_tables(tables, cik)
        
        # Parse tables to extract investments
        records = self._parse_html_tables(tables)
        
        logger.info(f"Built {len(records)} investment records from HTML")
        
        # Enrich missing industries from XBRL
        industry_map = self._extract_industries_from_xbrl(html_url, cik)
        if industry_map:
            logger.info(f"Found {len(industry_map)} industry mappings from XBRL")
            enriched_count = 0
            for rec in records:
                if not rec.get('industry') and rec.get('company_name'):
                    # Try to match company name (normalize for matching)
                    company_key = self._normalize_company_name(rec['company_name'])
                    if company_key in industry_map:
                        rec['industry'] = industry_map[company_key]
                        enriched_count += 1
            logger.info(f"Enriched {enriched_count} records with industry from XBRL")
        
        # Calculate totals
        total_principal = sum(r.get('principal_amount') or 0 for r in records)
        total_cost = sum(r.get('amortized_cost') or 0 for r in records)
        total_fair_value = sum(r.get('fair_value') or 0 for r in records)
        
        # Create breakdowns
        industry_breakdown = defaultdict(int)
        investment_type_breakdown = defaultdict(int)
        
        for rec in records:
            if rec.get('industry'):
                industry_breakdown[rec['industry']] += 1
            if rec.get('investment_type'):
                investment_type_breakdown[rec['investment_type']] += 1
        
        # Save to CSV with WHF format
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, 'SCM_Stellus_Capital_Investment_Corp_investments.csv')
        
        fieldnames = [
            'company_name',
            'investment_type',
            'industry',
            'interest_rate',
            'reference_rate',
            'spread',
            'acquisition_date',
            'maturity_date',
            'principal_amount',
            'amortized_cost',
            'fair_value',
            'percent_of_net_assets',
        ]
        
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in records:
                # Apply standardization
                if 'investment_type' in rec and rec['investment_type']:
                    rec['investment_type'] = standardize_investment_type(rec['investment_type'])
                if 'industry' in rec and rec['industry']:
                    rec['industry'] = standardize_industry(rec['industry'])
                if 'reference_rate' in rec and rec['reference_rate']:
                    rec['reference_rate'] = standardize_reference_rate(rec['reference_rate']) or ''
                
                # Write row with only the fields we want
                writer.writerow({
                    'company_name': rec.get('company_name', ''),
                    'investment_type': rec.get('investment_type', ''),
                    'industry': rec.get('industry', ''),
                    'interest_rate': rec.get('interest_rate', ''),
                    'reference_rate': rec.get('reference_rate', ''),
                    'spread': rec.get('spread', ''),
                    'acquisition_date': rec.get('acquisition_date', ''),
                    'maturity_date': rec.get('maturity_date', ''),
                    'principal_amount': rec.get('principal_amount', ''),
                    'amortized_cost': rec.get('amortized_cost', ''),
                    'fair_value': rec.get('fair_value', ''),
                    'percent_of_net_assets': rec.get('percent_of_net_assets', ''),
                })
        
        logger.info(f"Saved to {out_file}")
        
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': len(records),
            'total_principal': total_principal,
            'total_cost': total_cost,
            'total_fair_value': total_fair_value,
            'industry_breakdown': dict(industry_breakdown),
            'investment_type_breakdown': dict(investment_type_breakdown)
        }
    
    def _find_schedule_tables(self, soup: BeautifulSoup) -> List[BeautifulSoup]:
        """Find tables under Consolidated Schedule of Investments heading."""
        matches: List[BeautifulSoup] = []
        
        def normalize_text(text: str) -> str:
            if not text:
                return ""
            return re.sub(r"\s+", " ", text).strip()
        
        def normalize_key(text: str) -> str:
            return normalize_text(text).lower()
        
        def contains_date_like(blob: str) -> bool:
            return re.search(
                r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
                blob, re.IGNORECASE
            ) is not None
        
        required_any = [
            "consolidated schedule of investments",
            "continued",
            "unaudited",
            "dollar amounts in thousands",
        ]
        
        def heading_matches(blob: str) -> bool:
            blob_l = blob.lower()
            if "consolidated schedule of investments" not in blob_l:
                return False
            if not contains_date_like(blob_l):
                count = sum(1 for t in required_any if t in blob_l)
                if count < 3:
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
        
        return matches
    
    def _save_simplified_tables(self, tables: List[BeautifulSoup], cik: str):
        """Save simplified HTML tables for QA."""
        tables_dir = os.path.join('output', 'scm_tables')
        os.makedirs(tables_dir, exist_ok=True)
        
        for i, table in enumerate(tables, 1):
            simple = BeautifulSoup(str(table), "html.parser").find("table")
            if simple:
                # Replace XBRL tags with their text
                for ix in simple.find_all(lambda el: isinstance(el.name, str) and el.name.lower().startswith("ix:")):
                    ix.replace_with(ix.get_text(" ", strip=True))
                
                # Strip attributes
                def strip_attrs(el):
                    if hasattr(el, "attrs"):
                        el.attrs = {}
                    for child in getattr(el, "children", []):
                        if hasattr(child, "name"):
                            strip_attrs(child)
                
                strip_attrs(simple)
                
                with open(os.path.join(tables_dir, f"scm_table_{i}.html"), "w", encoding="utf-8") as fh:
                    fh.write(str(simple))
        
        logger.info(f"Saved {len(tables)} simplified tables to {tables_dir}")
    
    def _parse_html_tables(self, tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
        """Parse HTML tables into investment records."""
        records: List[Dict[str, Optional[str]]] = []
        
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
            """Remove spacer/blank cells and merge tokens like "$" + number, number + "%"."""
            filtered = [x for x in cells if x not in ("", "-", "—")]
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
        
        def find_header_map(rows: List[List[str]]) -> Optional[Dict[str, int]]:
            """Find column indices for key fields."""
            for r in rows[:12]:
                header_cells = compact_row(r)
                keys = [normalize_key(c) for c in header_cells]
                
                def find_idx(patterns: List[str]) -> Optional[int]:
                    for i, k in enumerate(keys):
                        if any(p in k for p in patterns):
                            return i
                    return None
                
                idx_company = find_idx(["issuer", "company", "portfolio company"])
                idx_type = find_idx(["investment type", "security type", "class"])
                idx_floor = find_idx(["floor"])
                idx_ref = find_idx(["reference rate"])
                idx_spread = find_idx(["spread above index", "spread"])
                idx_rate = find_idx(["interest rate"])
                idx_industry = find_idx(["industry", "sector"])  # rare, but use if present
                idx_acq = find_idx(["acquisition date"])
                idx_mat = find_idx(["maturity date"])
                idx_prin = find_idx(["principal", "share amount", "principal/share amount"])
                idx_cost = find_idx(["amortized cost", "cost"])
                idx_fv = find_idx(["fair value"])
                idx_pct = find_idx(["percentage of net assets", "% of net assets", "as a percentage of net assets"])
                
                if idx_company is not None and idx_type is not None and idx_prin is not None and idx_fv is not None:
                    return {
                        "company": idx_company,
                        "type": idx_type,
                        "floor": -1 if idx_floor is None else idx_floor,
                        "ref": -1 if idx_ref is None else idx_ref,
                        "spread": -1 if idx_spread is None else idx_spread,
                        "rate": -1 if idx_rate is None else idx_rate,
                        "industry": -1 if idx_industry is None else idx_industry,
                        "acq": -1 if idx_acq is None else idx_acq,
                        "mat": -1 if idx_mat is None else idx_mat,
                        "prin": idx_prin,
                        "cost": -1 if idx_cost is None else idx_cost,
                        "fv": idx_fv,
                        "pct": -1 if idx_pct is None else idx_pct,
                    }
            return None
        
        def has_percent(tokens: List[str]) -> bool:
            return any(
                re.search(r"\d(\.\d+)?%$", t) or " % " in f" {t} " or "cash /" in t.lower() or "pik" in t.lower()
                for t in tokens
            )
        
        def has_spread_token(tokens: List[str]) -> bool:
            return any(
                t.upper().startswith(("SOFR+", "PRIME+", "LIBOR+", "BASE RATE+", "SOFR", "PRIME", "LIBOR", "BASE RATE", "CORRA"))
                for t in tokens
            )
        
        def has_date(tokens: List[str]) -> bool:
            return any(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", t) for t in tokens)
        
        def is_section_header(text: str) -> bool:
            t = text.lower()
            return any(k in t for k in ["investments", "debt and equity", "non-control", "non-affiliate", "total"])

        us_state_codes = set([
            "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"
        ])

        def looks_like_location(text: str) -> bool:
            # e.g., "Skokie, IL" or "Atlanta, GA"
            m = re.match(r"^[A-Za-z .'-]+,\s*([A-Z]{2})$", text.strip())
            return bool(m and m.group(1) in us_state_codes)

        def looks_like_entity_name(text: str) -> bool:
            return any(suf in text for suf in [" Inc", " Inc.", " LLC", " L.L.C", " L.P", " L.P.", " Corp", " Corporation", " Holdings", " Company", " Limited", " Ltd", " S.A."]) or \
                   bool(re.search(r"\b(f/k/a|d/b/a)\b", text, re.IGNORECASE))

        def is_industry_like(text: str) -> bool:
            if not text:
                return False
            t = text.strip()
            if looks_like_location(t):
                return False
            if looks_like_entity_name(t):
                return False
            if any(ch.isdigit() for ch in t):
                return False
            # Common industry cue words
            cues = [
                "services","software","technology","industrial","industries","health care","healthcare","biotech","pharma","finance","financial",
                "consumer","media","retail","manufacturing","communications","energy","utilities","transportation","logistics","real estate",
                "packaging","equipment","chemicals","aerospace","defense","mining","metals","education","food","beverage","medical"
            ]
            lt = t.lower()
            return any(w in lt for w in cues) and len(t.split()) <= 6
        
        for table in tables:
            rows = table_to_rows(table)
            if not rows:
                continue
            
            header_map = find_header_map(rows) or {}
            last_company: Optional[str] = None
            last_industry: Optional[str] = None
            
            for r in rows:
                row = compact_row(r)
                if not row:
                    continue
                
                first = row[0]
                if is_section_header(first):
                    continue
                
                detail_signals = has_percent(row) or has_spread_token(row) or has_date(row)
                
                if first and not detail_signals:
                    # If the row looks like an industry header (only first cell meaningful), set industry
                    non_empty_others = [c for c in row[1:] if c and c not in ("$", "%")]
                    if not non_empty_others:
                        cand = first.strip()
                        last_industry = cand if is_industry_like(cand) else last_industry
                    else:
                        last_company = first.strip()
                        cand_ind = None
                        for cell in row[1:]:
                            if cell and not has_percent([cell]) and not has_date([cell]) and not has_spread_token([cell]):
                                cand_ind = cell.strip()
                                break
                        if cand_ind and is_industry_like(cand_ind):
                            last_industry = cand_ind
                    continue
                
                # Map columns if header detected; otherwise fallback heuristics
                inv_type = first.strip()
                # For equity-like rows, do not treat bare % as interest rate
                equity_like = bool(re.search(r"(common|preferred|equity|units|stock)", inv_type, re.IGNORECASE))
                interest_rate = None if equity_like else next((c for c in row if re.search(r"\d(\.\d+)?%", c)), None)
                spread_val = None
                
                for i, c in enumerate(row):
                    cu = c.upper()
                    if any(cu.startswith(tok) for tok in ["SOFR+", "PRIME+", "LIBOR+", "BASE RATE+", "CORRA+"]):
                        if i + 1 < len(row):
                            nxt = row[i + 1]
                            spread_val = nxt if nxt.endswith("%") else (nxt + "%" if re.match(r"^\d+(\.\d+)?$", nxt) else nxt)
                            break
                
                # Reference rate token present as e.g., "SOFR (3M)"
                ref_token = None
                
                if header_map:
                    def get(idx: int) -> Optional[str]:
                        return row[idx] if 0 <= idx < len(row) else None
                    
                    company_cell = get(header_map.get("company", -1))
                    it_cell = get(header_map.get("type", -1))
                    ref_cell = get(header_map.get("ref", -1))
                    rate_cell = get(header_map.get("rate", -1))
                    spread_cell = get(header_map.get("spread", -1))
                    industry_cell = get(header_map.get("industry", -1))
                    acq_cell = get(header_map.get("acq", -1))
                    mat_cell = get(header_map.get("mat", -1))
                    prin_cell = get(header_map.get("prin", -1))
                    cost_cell = get(header_map.get("cost", -1))
                    fv_cell = get(header_map.get("fv", -1))
                    pct_cell = get(header_map.get("pct", -1))
                    
                    # Prefer mapped values
                    inv_type = it_cell or inv_type
                    # Only set interest rate from mapped cell for non-equity rows
                    interest_rate = (rate_cell or interest_rate) if not equity_like else None
                    spread_val = spread_cell or spread_val
                    ref_token = ref_cell
                    acq = acq_cell
                    mat = mat_cell
                    company_for_row = company_cell or last_company or ""
                    # Industry mapping if provided and sensible
                    mapped_industry = industry_cell if industry_cell and is_industry_like(industry_cell) else None
                    if mapped_industry:
                        last_industry = mapped_industry
                    money = [prin_cell, cost_cell, fv_cell]
                else:
                    company_for_row = last_company or ""
                    dates = [c for c in row if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", c)]
                    acq = dates[0] if dates else None
                    mat = dates[1] if len(dates) > 1 else None
                    money = [c for c in row if c.startswith("$") or re.match(r"^\$?\d[\d,]*$", c)]
                    pct_cell = None
                    
                    # Scan for reference rate token
                    for tok in row:
                        m = re.match(r"^(SOFR|SONIA|PRIME|LIBOR|BASE RATE|EURIBOR|CORRA)(?:\s*\([^)]*\))?$", tok, re.IGNORECASE)
                        if m:
                            ref_token = tok
                            break
                
                principal = money[0] if len(money) >= 1 else None
                cost = money[1] if len(money) >= 2 else None
                fair_value = money[2] if len(money) >= 3 else None
                
                pct_nav = None
                if 'pct_cell' in locals() and pct_cell:
                    pct_nav = pct_cell
                else:
                    percent_tokens = [c for c in row if c.endswith("%")]
                    if percent_tokens:
                        pct_nav = percent_tokens[-1]
                
                def parse_number_local(text: Optional[str]) -> Optional[float]:
                    if not text:
                        return None
                    t = text.replace("\xa0", " ").replace(",", "").strip()
                    t = t.replace("$", "")
                    if t in ("—", "—%", "— $", "-"):
                        return None
                    if t.endswith("%"):
                        try:
                            return float(t[:-1])
                        except:
                            return None
                    try:
                        return float(t)
                    except:
                        return None
                
                company_clean = strip_footnote_refs(company_for_row or last_company or "")
                inv_type_clean = strip_footnote_refs(inv_type)
                ind_candidate = strip_footnote_refs(last_industry or "")
                industry_clean = ind_candidate if is_industry_like(ind_candidate) else ""
                
                # Only add if we have meaningful data
                if company_clean or (principal or cost or fair_value):
                    records.append({
                        "company_name": company_clean,
                        "investment_type": inv_type_clean,
                        "industry": industry_clean,
                        "interest_rate": interest_rate,
                        "reference_rate": ref_token,
                        "spread": spread_val,
                        "acquisition_date": acq,
                        "maturity_date": mat,
                        "principal_amount": parse_number_local(principal),
                        "amortized_cost": parse_number_local(cost),
                        "fair_value": parse_number_local(fair_value),
                        "percent_of_net_assets": parse_number_local(pct_nav),
                    })
        
        return records
    
    def _extract_industries_from_xbrl(self, html_url: str, cik: str) -> Dict[str, str]:
        """Extract industry mappings from XBRL by company name."""
        logger.info(f"Starting XBRL industry extraction from {html_url}")
        industry_map = {}
        
        try:
            # Extract accession number from HTML URL - try multiple patterns
            accession_match = re.search(r'/(\d{10}-\d{2}-\d{6})', html_url)
            if not accession_match:
                # Try pattern from directory structure: /000155837025010509/
                accession_match = re.search(r'/(\d{10}\d{2}\d{6})', html_url)
                if accession_match:
                    # Format it properly
                    acc_str = accession_match.group(1)
                    accession = f"{acc_str[:10]}-{acc_str[10:12]}-{acc_str[12:]}"
                else:
                    logger.warning(f"Could not extract accession number from {html_url}")
                    return industry_map
            else:
                accession = accession_match.group(1)
            
            accession_no_hyphens = accession.replace('-', '')
            
            # Strip leading zeros from CIK for URL
            cik_numeric = str(int(cik)) if cik.isdigit() else cik.lstrip('0')
            
            # Build .txt URL
            txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik_numeric}/{accession_no_hyphens}/{accession}.txt"
            logger.info(f"Downloading XBRL for industry enrichment: {txt_url}")
            
            response = requests.get(txt_url, headers=self.headers)
            response.raise_for_status()
            content = response.text
            
            # Extract contexts with InvestmentIdentifierAxis and industry
            cp = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
            tp = re.compile(
                r'<xbrldi:typedMember[^>]*dimension="us-gaap:InvestmentIdentifierAxis"[^>]*>'
                r'\s*<us-gaap:InvestmentIdentifierAxis\.domain>([^<]+)</us-gaap:InvestmentIdentifierAxis\.domain>'
                r'\s*</xbrldi:typedMember>', re.DOTALL
            )
            ep = re.compile(
                r'<xbrldi:explicitMember[^>]*dimension="us-gaap:EquitySecuritiesByIndustryAxis"[^>]*>([^<]+)</xbrldi:explicitMember>',
                re.DOTALL | re.IGNORECASE
            )
            
            context_count = 0
            typed_member_count = 0
            industry_member_count = 0
            
            for m in cp.finditer(content):
                context_count += 1
                cid = m.group(1)
                chtml = m.group(2)
                
                # Find investment identifier
                tm = tp.search(chtml)
                if not tm:
                    continue
                
                typed_member_count += 1
                ident = tm.group(1).strip()
                parsed = self._parse_identifier_xbrl(ident)
                company_name = parsed.get('company_name', '').strip()
                industry_from_ident = parsed.get('industry', '').strip()
                
                if not company_name or company_name == 'Unknown':
                    continue
                
                # Try to find industry from explicitMember first
                em = ep.search(chtml)
                industry = None
                if em:
                    industry_member_count += 1
                    industry_qname = em.group(1).strip()
                    industry = self._industry_member_to_name(industry_qname)
                
                # Fallback: use industry from identifier if available
                if not industry and industry_from_ident and industry_from_ident != 'Unknown':
                    industry = industry_from_ident
                
                if industry:
                    # Normalize company name for mapping
                    company_key = self._normalize_company_name(company_name)
                    if company_key:
                        industry_map[company_key] = industry
                        logger.debug(f"Mapped {company_name} -> {industry}")
            
            logger.info(f"XBRL parsing: {context_count} contexts, {typed_member_count} typed members, {industry_member_count} industry members")
            
            logger.info(f"Extracted {len(industry_map)} industry mappings from XBRL")
            
        except Exception as e:
            logger.warning(f"Failed to extract industries from XBRL: {e}", exc_info=True)
        
        return industry_map
    
    def _parse_identifier_xbrl(self, identifier: str) -> Dict[str, str]:
        """Parse XBRL InvestmentIdentifierAxis identifier.
        
        Formats can be:
        - "Company Name, Investment Type"
        - "Company Name, Industry, Investment Type"
        """
        res = {'company_name': 'Unknown', 'industry': 'Unknown', 'investment_type': 'Unknown'}
        
        if not identifier or not identifier.strip():
            return res
        
        # Split by commas
        parts = [p.strip() for p in identifier.split(',')]
        
        if len(parts) == 0:
            return res
        elif len(parts) == 1:
            # Just company name
            res['company_name'] = re.sub(r'\s+', ' ', parts[0]).rstrip(',')
        elif len(parts) == 2:
            # "Company, Investment Type"
            res['company_name'] = re.sub(r'\s+', ' ', parts[0]).rstrip(',')
            res['investment_type'] = parts[1]
        else:
            # 3+ parts: likely "Company, Industry, Investment Type" or more
            res['company_name'] = re.sub(r'\s+', ' ', parts[0]).rstrip(',')
            
            # Check if middle part looks like industry (not investment type or entity suffix)
            middle = parts[1]
            investment_type_patterns = [
                r'First\s+lien', r'Second\s+lien', r'Unitranche', r'Senior\s+secured',
                r'Secured\s+Debt', r'Unsecured\s+Debt', r'Preferred\s+Equity',
                r'Preferred\s+Stock', r'Common\s+Stock', r'Member\s+Units', r'Warrants?',
                r'Term\s+Loan', r'Revolver', r'Delayed\s+Draw'
            ]
            
            # Entity suffixes that shouldn't be treated as industry
            entity_suffixes = [r'^LLC$', r'^L\.L\.C\.?$', r'^L\.P\.?$', r'^Inc\.?$', r'^Corp\.?$', 
                              r'^Corporation$', r'^Company$', r'^Co\.?$', r'^Limited$', r'^Ltd\.?$']
            
            is_investment_type = any(re.search(p, middle, re.IGNORECASE) for p in investment_type_patterns)
            is_entity_suffix = any(re.match(p, middle, re.IGNORECASE) for p in entity_suffixes)
            
            # Only treat as industry if it's not an investment type, not an entity suffix, 
            # and looks like it could be an industry (has industry-like words)
            industry_keywords = ['services', 'technology', 'health', 'care', 'software', 'industrial', 
                                'consumer', 'media', 'retail', 'manufacturing', 'communications', 
                                'energy', 'utilities', 'transportation', 'logistics', 'real estate',
                                'packaging', 'equipment', 'chemicals', 'aerospace', 'defense',
                                'mining', 'metals', 'education', 'food', 'beverage', 'medical']
            
            looks_like_industry = any(kw in middle.lower() for kw in industry_keywords) and len(middle.split()) <= 6
            
            if not is_investment_type and not is_entity_suffix and looks_like_industry:
                # Middle part is likely industry
                res['industry'] = middle
                res['investment_type'] = ', '.join(parts[2:])
            else:
                # Middle part is investment type or entity suffix, no industry
                res['investment_type'] = ', '.join(parts[1:])
        
        # Clean up company name
        res['company_name'] = re.sub(r'\s+', ' ', res['company_name']).strip()
        
        return res
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for matching (remove common suffixes, punctuation, etc.)."""
        if not name:
            return ""
        
        # Remove common legal suffixes and normalize
        normalized = re.sub(r'\s*(Inc\.?|LLC|L\.L\.C\.?|L\.P\.?|Corp\.?|Corporation|Company|Co\.?|Limited|Ltd\.?)\s*$', '', name, flags=re.IGNORECASE)
        normalized = re.sub(r'\s*\([^)]*\)\s*', '', normalized)  # Remove parentheticals like (d/b/a ...)
        normalized = re.sub(r'\s*(d/b/a|f/k/a|fka|dba)\s+.*$', '', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove punctuation
        normalized = re.sub(r'\s+', ' ', normalized).strip().upper()
        
        return normalized
    
    def _industry_member_to_name(self, qname: str) -> Optional[str]:
        """Convert XBRL industry member QName to readable industry name."""
        local = qname.split(':', 1)[-1] if ':' in qname else qname
        local = re.sub(r'Member$', '', local)
        if local.endswith('Sector'):
            local = local[:-6]
        
        # Convert CamelCase to words
        words = re.sub(r'(?<!^)([A-Z])', r' \1', local).strip()
        words = re.sub(r'\bAnd\b', 'and', words)
        words = re.sub(r'\s+', ' ', words).strip()
        
        return words if words else None
    
    def _fallback_to_xbrl(self, html_url: str, company_name: str, cik: str) -> Dict:
        """Fallback to XBRL extraction if HTML tables not found."""
        # Extract accession number from HTML URL
        accession_match = re.search(r'/(\d{10}-\d{2}-\d{6})', html_url)
        if not accession_match:
            raise ValueError(f"Could not parse accession number from {html_url}")
        
        accession = accession_match.group(1)
        accession_no_hyphens = accession.replace('-', '')
        
        # Build .txt URL
        txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
        logger.info(f"Fallback: Using XBRL URL: {txt_url}")
        
        # Use existing XBRL extraction logic (simplified version)
        response = requests.get(txt_url, headers=self.headers)
        response.raise_for_status()
        content = response.text
        
        # For now, just return empty result - XBRL extraction can be added later if needed
        logger.warning("XBRL fallback not fully implemented, returning empty result")
        return {
            'company_name': company_name,
            'cik': cik,
            'total_investments': 0,
            'total_principal': 0,
            'total_cost': 0,
            'total_fair_value': 0,
            'industry_breakdown': {},
            'investment_type_breakdown': {}
        }


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    ex = SCMExtractor()
    try:
        res = ex.extract_from_ticker('SCM')
        print(f"Extracted {res['total_investments']} investments")
        print(f"Total principal: ${res['total_principal']:,.0f}")
        print(f"Total fair value: ${res['total_fair_value']:,.0f}")
    except Exception as e:
        logger.exception(f"[ERROR] {e}")
        print(f"[ERROR] {e}")


if __name__ == '__main__':
    main()



