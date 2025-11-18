#!/usr/bin/env python3
"""
SAR (Saratoga Investment Corp) Investment Extractor
HTML-first table parsing with rate extraction from embedded text.
"""

import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
import os
import csv
import requests
from bs4 import BeautifulSoup

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class SARInvestment:
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


def extract_tables_under_heading(soup: BeautifulSoup) -> List[BeautifulSoup]:
    matches: List[BeautifulSoup] = []
    def contains_date_like(blob: str) -> bool:
        return re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", blob, re.IGNORECASE) is not None
    required_any = ["schedule of investments", "consolidated", "unaudited", "dollar amounts in"]
    def heading_matches(blob: str) -> bool:
        blob_l = blob
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
    filtered = [x for x in cells if x not in ("", "-")]
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


def find_header_map(rows: List[List[str]]) -> Optional[Dict[str,int]]:
    for r in rows[:12]:
        header_cells = compact_row(r)
        keys = [normalize_key(c) for c in header_cells]
        def find_idx(patterns: List[str]) -> Optional[int]:
            for i,k in enumerate(keys):
                if any(p in k for p in patterns):
                    return i
            return None
        fv_latest_idx = None
        best_year = -1
        for i,k in enumerate(keys):
            if k.startswith('fair value at'):
                m = re.search(r'(19|20)\d{2}', k)
                yr = int(m.group(0)) if m else -1
                if yr > best_year or (yr == -1 and fv_latest_idx is None):
                    best_year = yr
                    fv_latest_idx = i
        return {
            "company": find_idx(["issuer","company","portfolio company"]) or -1,
            "type": find_idx(["investment type","security type","class","interest rate","maturity","investment interest rate"]) or -1,
            "acq": find_idx(["acquisition date","investment date","initial investment date","original acquisition"]) or -1,
            "mat": find_idx(["maturity date","expiration date"]) or -1,
            "prin": find_idx(["principal","share amount","principal/ quantity","principal/quantity","shares/principal/ quantity","number of shares"]) or -1,
            "cost": find_idx(["amortized cost","cost"]) or -1,
            "fv": (fv_latest_idx if fv_latest_idx is not None else (find_idx(["fair value"]) or -1)),
            "pct": find_idx(["percentage of net assets","% of net assets"]) or -1,
        }
    return None


def parse_section_tables(tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
    recs: List[Dict[str, Optional[str]]] = []
    def parse_money_cell(x: Optional[str]) -> Optional[float]:
        if not x:
            return None
        t = str(x).strip()
        t = t.replace(',)', ')')
        t = t.replace(' )', ')')
        t = t.replace('$', '').replace(',', '')
        if t in ('—','-','–',''):
            return None
        neg = False
        if t.startswith('(') and t.endswith(')'):
            neg = True
            t = t[1:-1]
        try:
            v = float(t)
            return -v if neg else v
        except:
            return None
    
    for table in tables:
        rows = table_to_rows(table)
        if not rows:
            continue
        hdr = find_header_map(rows) or {}
        last_company: Optional[str] = None
        last_industry: Optional[str] = None
        
        for r in rows:
            row = compact_row(r)
            if not row:
                continue
            first = row[0]
            
            # Skip obvious section headers
            if normalize_key(first) in ("investments","debt investments","equity investments"):
                continue
            
            # Skip header rows
            row_l = " ".join(normalize_key(c) for c in row)
            if "issuer" in row_l and "investment" in row_l and "fair value" in row_l:
                continue
            
            # Identify company/industry lines (no dates/rates/money)
            if not any(re.search(r"\d{1,2}/\d{1,2}/\d{4}", c) for c in row) and not any('%' in c for c in row) and not any(re.search(r'\$[\d,]', c) for c in row):
                if len(row) == 1:
                    last_industry = first
                else:
                    last_company = first
                continue
            
            # Skip totals/subtotals
            first_l = normalize_key(first)
            if first_l.startswith('total ') or first_l.startswith('portfolio investments') or first_l.startswith('non-controlled'):
                continue
            
            def get(idx: int) -> Optional[str]:
                return row[idx] if 0 <= idx < len(row) else None
            
            raw_company = get(hdr.get("company", -1)) or first
            raw_inv_type = get(hdr.get("type", -1)) or ""
            acq = get(hdr.get("acq", -1))
            mat = get(hdr.get("mat", -1))
            prin = get(hdr.get("prin", -1))
            cost = get(hdr.get("cost", -1))
            fv = get(hdr.get("fv", -1))
            pct = get(hdr.get("pct", -1))
            
            # The investment type column contains rate info: "First Lien Term Loan (6M USD TERM SOFR+8.08%), 12.46% Cash, 7/18/2027"
            # Extract rates from the investment type column
            ref_rate = None
            spread = None
            interest_rate = None
            if raw_inv_type:
                # Extract reference rate and spread: "6M USD TERM SOFR+8.08%" or "3M USD TERM SOFR+5.50%"
                ref_map = {'E': 'EURIBOR', 'BASE RATE': 'BASE RATE', 'BASE': 'BASE RATE'}
                ref_match = re.search(r'(\d+[M]?)\s*USD\s*(TERM\s+)?(SOFR|LIBOR|PRIME|Prime|Base Rate|EURIBOR|E)\s*\+\s*([\d\.]+)\s*%?', raw_inv_type, re.IGNORECASE)
                if ref_match:
                    term_type = ref_match.group(1).strip() if ref_match.group(1) else None
                    base = ref_match.group(3).upper()
                    base = ref_map.get(base, base)
                    if term_type and 'SOFR' in base:
                        # Clean up term type: "6M USD" -> "6M"
                        term_clean = term_type.replace('USD', '').strip()
                        ref_rate = f"SOFR ({term_clean})"
                    else:
                        ref_rate = base
                    spread = f"{float(ref_match.group(4)):.2f}%"
                
                # Extract interest rate: "12.46% Cash" or "9.67% Cash"
                rate_match = re.search(r'([\d\.]+)\s*%\s*Cash', raw_inv_type, re.IGNORECASE)
                if rate_match:
                    interest_rate = f"{float(rate_match.group(1)):.2f}%"
                
                # Extract maturity date from investment type column if not in separate column
                if not mat:
                    date_match = re.search(r'\b(\d{1,2}/\d{1,2}/\d{4})\b', raw_inv_type)
                    if date_match:
                        mat = date_match.group(1)
                
                # Extract investment type (remove rate info)
                inv_type_clean = raw_inv_type
                inv_type_clean = re.sub(r'\([^)]*\)', '', inv_type_clean).strip()  # Remove (6M USD TERM SOFR+8.08%)
                inv_type_clean = re.sub(r',\s*[\d\.]+\s*%?\s*Cash', '', inv_type_clean, flags=re.IGNORECASE).strip()  # Remove , 12.46% Cash
                inv_type_clean = re.sub(r',\s*\d{1,2}/\d{1,2}/\d{4}', '', inv_type_clean).strip()  # Remove , 7/18/2027
                inv_type = inv_type_clean or inv_type or ""
            else:
                inv_type = inv_type or ""
            
            # Clean company name (remove footnote markers)
            company = strip_footnote_refs(raw_company)
            industry = last_industry or ""
            
            # Heuristic date extraction
            row_blob = " ".join(row)
            if (not acq or acq == '') or (not mat or mat == ''):
                date_matches = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", row_blob)
                if date_matches:
                    if len(date_matches) >= 2:
                        acq = acq or date_matches[0]
                        mat = mat or date_matches[-1]
                    else:
                        if re.search(r"expiration|maturity", row_blob, re.IGNORECASE):
                            mat = mat or date_matches[0]
                        else:
                            acq = acq or date_matches[0]
            
            # Extract floor/PIK if present
            floor = None
            floor_match = re.search(r"floor\s*(?:rate)?\s*([\d\.]+)\s*%", row_blob, re.IGNORECASE)
            if floor_match:
                floor = f"{float(floor_match.group(1)):.2f}%"
            
            pik_rate = None
            pik_match = re.search(r"PIK\s*(?:interest)?\s*([\d\.]+)\s*%", row_blob, re.IGNORECASE)
            if pik_match:
                pik_rate = f"{float(pik_match.group(1)):.2f}%"
            
            prin_v = parse_money_cell(prin)
            cost_v = parse_money_cell(cost)
            fv_v = parse_money_cell(fv)
            pct_v = None
            if pct:
                pp = str(pct).strip().rstrip('%')
                try:
                    pct_v = float(pp)
                except:
                    pct_v = parse_money_cell(pct)
            
            recs.append({
                "company_name": strip_footnote_refs(company),
                "investment_type": strip_footnote_refs(inv_type),
                "industry": strip_footnote_refs(industry),
                "interest_rate": interest_rate,
                "reference_rate": ref_rate,
                "spread": spread,
                "floor_rate": floor,
                "pik_rate": pik_rate,
                "acquisition_date": acq,
                "maturity_date": mat,
                "principal_amount": prin_v,
                "amortized_cost": cost_v,
                "fair_value": fv_v,
                "percent_of_net_assets": pct_v,
            })
    
    return recs


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
    index_url = client.get_filing_index_url("SAR", "10-Q")
    if not index_url:
        print("Could not find latest 10-Q for SAR")
        return
    docs = client.get_documents_from_index(index_url)
    main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
    if not main_html:
        print("No main HTML document found for SAR")
        return
    resp = requests.get(main_html.url, headers=client.headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    
    tables = extract_tables_under_heading(soup)
    if not tables:
        # Fallback: choose the largest tables
        all_tables = soup.find_all("table")
        scored = []
        for t in all_tables:
            rows = t.find_all("tr")
            rcount = len(rows)
            ccount = max((len(r.find_all(["td","th"])) for r in rows), default=0)
            scored.append((rcount*ccount, t))
        scored.sort(reverse=True, key=lambda x: x[0])
        tables = [t for _, t in scored[:10]]
    
    records = parse_section_tables(tables)
    
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, "SAR_Schedule_Continued_latest.csv")
    fieldnames = [
        "company_name","investment_type","industry","interest_rate","reference_rate","spread","floor_rate","pik_rate","acquisition_date","maturity_date","principal_amount","amortized_cost","fair_value","percent_of_net_assets",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            if 'investment_type' in rec:
                rec['investment_type'] = standardize_investment_type(rec.get('investment_type'))
            if 'industry' in rec:
                rec['industry'] = standardize_industry(rec.get('industry'))
            if 'reference_rate' in rec:
                rec['reference_rate'] = standardize_reference_rate(rec.get('reference_rate')) or ''
            writer.writerow(rec)
    print(f"Saved {len(records)} rows to {out_csv}")
    
    # Build normalized investments CSV
    def parse_float_maybe(s: Optional[str]) -> Optional[float]:
        if s is None:
            return None
        t = str(s).replace(",", "").replace("$", "").strip()
        if t in ("—","-","–",""):
            return None
        neg = False
        if t.startswith("(") and t.endswith(")"):
            neg = True
            t = t[1:-1]
        try:
            v = float(t)
            return -v if neg else v
        except:
            return None
    
    inv_rows: List[Dict[str, Optional[str]]] = []
    for rec in records:
        name = (rec.get("company_name") or "").strip()
        if not name or name.lower().startswith("total "):
            continue
        pa = parse_float_maybe(rec.get("principal_amount"))
        cost = parse_float_maybe(rec.get("amortized_cost"))
        fv = parse_float_maybe(rec.get("fair_value"))
        if pa is None and cost is None and fv is None:
            continue
        inv_rows.append({
            'company_name': name,
            'industry': rec.get('industry') or '',
            'business_description': '',
            'investment_type': rec.get('investment_type') or '',
            'acquisition_date': rec.get('acquisition_date') or '',
            'maturity_date': rec.get('maturity_date') or '',
            'principal_amount': pa if pa is not None else '',
            'cost': cost if cost is not None else '',
            'fair_value': fv if fv is not None else '',
            'interest_rate': rec.get('interest_rate') or '',
            'reference_rate': rec.get('reference_rate') or '',
            'spread': rec.get('spread') or '',
            'floor_rate': rec.get('floor_rate') or '',
            'pik_rate': rec.get('pik_rate') or '',
        })
    
    inv_out = os.path.join(out_dir, 'SAR_Saratoga_Investment_Corp_investments.csv')
    with open(inv_out, 'w', newline='', encoding='utf-8') as f:
        inv_fields = ['company_name','industry','business_description','investment_type','acquisition_date','maturity_date','principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate']
        w = csv.DictWriter(f, fieldnames=inv_fields)
        w.writeheader()
        for r in inv_rows:
            if 'investment_type' in r:
                r['investment_type'] = standardize_investment_type(r.get('investment_type'))
            if 'industry' in r:
                r['industry'] = standardize_industry(r.get('industry'))
            if 'reference_rate' in r:
                r['reference_rate'] = standardize_reference_rate(r.get('reference_rate')) or ''
            w.writerow(r)
    print(f"Saved {len(inv_rows)} rows to {inv_out}")
    
    # Save simplified tables
    tables_dir = os.path.join(out_dir, "sar_tables")
    os.makedirs(tables_dir, exist_ok=True)
    for i, t in enumerate(tables, 1):
        simple = BeautifulSoup(str(t), "html.parser").find("table")
        if simple:
            for ix in simple.find_all(lambda el: isinstance(el.name, str) and el.name.lower().startswith("ix:")):
                ix.replace_with(ix.get_text(" ", strip=True))
            def strip_attrs(el):
                if hasattr(el, "attrs"):
                    el.attrs = {}
                for child in getattr(el, "children", []):
                    strip_attrs(child)
            strip_attrs(simple)
            with open(os.path.join(tables_dir, f"sar_table_{i}.html"), "w", encoding="utf-8") as fh:
                fh.write(str(simple))
    print(f"Saved {len(tables)} simplified tables to {tables_dir}")


class SARExtractor:
    """Extractor class for SAR to match standard extractor interface."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.headers = {'User-Agent': user_agent}
        self.sec_client = SECAPIClient(user_agent=user_agent)
    
    def extract_from_ticker(self, ticker: str = "SAR", year: Optional[int] = 2025, min_date: Optional[str] = None) -> Dict:
        """Extract investments from ticker symbol."""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        client = self.sec_client
        
        # Build normalized investments CSV
        def parse_float_maybe(s: Optional[str]) -> Optional[float]:
            if s is None:
                return None
            t = str(s).replace(",", "").replace("$", "").strip()
            if t in ("—","-","–",""):
                return None
            neg = False
            if t.startswith("(") and t.endswith(")"):
                neg = True
                t = t[1:-1]
            try:
                v = float(t)
                return -v if neg else v
            except ValueError:
                return None
        
        index_url = client.get_filing_index_url(ticker, "10-Q")
        if not index_url:
            raise ValueError("Could not find latest 10-Q for SAR")
        docs = client.get_documents_from_index(index_url)
        main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
        if not main_html:
            raise ValueError("No main HTML document found for SAR")
        resp = requests.get(main_html.url, headers=client.headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        tables = extract_tables_under_heading(soup)
        if not tables:
            all_tables = soup.find_all("table")
            scored = []
            for t in all_tables:
                rows = t.find_all("tr")
                rcount = len(rows)
                ccount = max((len(r.find_all(["td","th"])) for r in rows), default=0)
                scored.append((rcount*ccount, t))
            scored.sort(reverse=True, key=lambda x: x[0])
            tables = [t for _, t in scored[:10]]
        
        # Use parse_section_tables which has the proper parsing logic
        records = parse_section_tables(tables)
        
        inv_rows = []
        for rec in records:
            name = (rec.get("company_name") or "").strip()
            if not name or name.lower().startswith("total "):
                continue
            pa = parse_float_maybe(rec.get("principal_amount"))
            cost = parse_float_maybe(rec.get("amortized_cost"))
            fv = parse_float_maybe(rec.get("fair_value"))
            if pa is None and cost is None and fv is None:
                continue
            inv_rows.append({
                'company_name': name,
                'industry': rec.get('industry') or '',
                'business_description': '',
                'investment_type': rec.get('investment_type') or '',
                'acquisition_date': rec.get('acquisition_date') or '',
                'maturity_date': rec.get('maturity_date') or '',
                'principal_amount': pa if pa is not None else '',
                'cost': cost if cost is not None else '',
                'fair_value': fv if fv is not None else '',
                'interest_rate': rec.get('interest_rate') or '',
                'reference_rate': rec.get('reference_rate') or '',
                'spread': rec.get('spread') or '',
                'floor_rate': rec.get('floor_rate') or '',
                'pik_rate': rec.get('pik_rate') or '',
            })
        
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        inv_out = os.path.join(out_dir, 'SAR_Saratoga_Investment_Corp_investments.csv')
        with open(inv_out, 'w', newline='', encoding='utf-8') as f:
            inv_fields = ['company_name','industry','business_description','investment_type','acquisition_date','maturity_date','principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate']
            w = csv.DictWriter(f, fieldnames=inv_fields)
            w.writeheader()
            for r in inv_rows:
                if 'investment_type' in r:
                    r['investment_type'] = standardize_investment_type(r.get('investment_type'))
                if 'industry' in r:
                    r['industry'] = standardize_industry(r.get('industry'))
                if 'reference_rate' in r:
                    r['reference_rate'] = standardize_reference_rate(r.get('reference_rate')) or ''
                w.writerow(r)
        
        logger.info(f"Saved {len(inv_rows)} rows to {inv_out}")
        
        return {
            'company_name': 'Saratoga Investment Corp',
            'cik': client.get_cik(ticker),
            'total_investments': len(inv_rows),
            'investments': inv_rows,
        }


if __name__=='__main__':
    main()


