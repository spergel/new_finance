#!/usr/bin/env python3
"""
Extract CSWC Schedule of Investments tables from latest 10-Q HTML and save:
- Normalized CSV in bdc_extractor_standalone/output
- Simplified HTML tables for visual inspection in bdc_extractor_standalone/output/cswc_tables

Usage:
  python cswc_html_tables_to_csv.py
"""

import csv
import os
import re
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

from sec_api_client import SECAPIClient


def normalize_text(text: str) -> str:
	if not text:
		return ""
	return re.sub(r"\s+", " ", text).strip()


def normalize_key(text: str) -> str:
	return normalize_text(text).lower()


def extract_tables_under_heading(soup: BeautifulSoup) -> List[BeautifulSoup]:
    """Find CSWC schedule tables by either heading proximity or header keywords."""
    matches: List[BeautifulSoup] = []

    def heading_matches(blob: str) -> bool:
        b = blob
        if "consolidated schedule of investments" not in b:
            return False
        return True

    def has_schedule_headers(table: BeautifulSoup) -> bool:
        header_text = normalize_key(table.get_text(" ", strip=True))
        return (
            "portfolio company" in header_text and
            "type of investment" in header_text and
            ("principal" in header_text or "fair value" in header_text or "cost" in header_text)
        )

    for table in soup.find_all("table"):
        if has_schedule_headers(table):
            matches.append(table)
            continue
        # Otherwise check heading proximity
        context_texts = []
        cur = table
        for _ in range(15):
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
	rows = []
	for tr in table.find_all("tr"):
		cells = tr.find_all(["td", "th"])
		if not cells:
			continue
		vals = [normalize_text(c.get_text(" ", strip=True)) for c in cells]
		rows.append(vals)
	return rows


def simplify_table(table: BeautifulSoup) -> str:
	simple = BeautifulSoup(str(table), "html.parser").find("table")
	if not simple:
		return "<table></table>"
	for ix in simple.find_all(lambda t: isinstance(t.name, str) and t.name.lower().startswith("ix:")):
		ix.replace_with(ix.get_text(" ", strip=True))
	def strip_attrs(el):
		if hasattr(el, "attrs"):
			el.attrs = {}
		for child in getattr(el, "children", []):
			strip_attrs(child)
	strip_attrs(simple)
	for tag_name in ["span", "div", "b", "strong", "i", "em", "u"]:
		for t in simple.find_all(tag_name):
			t.unwrap()
	for tr in simple.find_all("tr"):
		cells = tr.find_all(["td", "th"])
		if not cells or not any(c.get_text(strip=True) for c in cells):
			tr.decompose()
	allowed = {"table", "thead", "tbody", "tr", "th", "td"}
	for tag in list(simple.find_all(True)):
		if tag.name not in allowed:
			tag.unwrap()
	return str(simple)


def parse_section_tables(tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
	records: List[Dict[str, Optional[str]]] = []

	def is_date(t: str) -> bool:
		return bool(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", t))

	def looks_percent(t: str) -> bool:
		return t.endswith("%") or "cash /" in t.lower() or "pik" in t.lower()

	for table in tables:
		rows = table_to_rows(table)
		if not rows:
			continue
		last_company = None
		last_industry = None
		for r in rows:
			row = [x for x in r if x != ""]
			if not row:
				continue
			first = row[0]
			# Company/industry line if no dates or percents present
			if not any(is_date(x) or looks_percent(x) for x in row):
				last_company = first
				cand_ind = next((x for x in row[1:] if x and not is_date(x) and not looks_percent(x)), None)
				if cand_ind:
					last_industry = cand_ind
				continue
			# Detail line
			inv_type = first
			interest = next((x for x in row if looks_percent(x)), None)
			spread = None
			for i, x in enumerate(row):
				xu = x.upper()
				if xu.startswith(("SOFR+", "PRIME+", "LIBOR+", "BASE RATE+")):
					if i+1 < len(row):
						spread = row[i+1] if row[i+1].endswith('%') else (row[i+1] + '%' if re.match(r"^\d+(\.\d+)?$", row[i+1]) else row[i+1])
					break
			dates = [x for x in row if is_date(x)]
			acq = dates[0] if dates else None
			mat = dates[1] if len(dates) > 1 else None
			mon = [x for x in row if x.startswith("$") or re.match(r"^\$?\d[\d,]*$", x)]
			principal = mon[0] if len(mon) >= 1 else None
			cost = mon[1] if len(mon) >= 2 else None
			fv = mon[2] if len(mon) >= 3 else None
			def to_num(t: Optional[str]) -> Optional[float]:
				if not t:
					return None
				s = t.replace("$", "").replace(",", "").strip()
				if s in ("—", "—%", "— $"):
					return None
				try:
					return float(s)
				except:
					return None
			records.append({
				"company_name": last_company or "",
				"investment_type": inv_type,
				"industry": last_industry or "",
				"interest_rate": interest,
				"spread": spread,
				"acquisition_date": acq,
				"maturity_date": mat,
				"principal_amount": to_num(principal),
				"amortized_cost": to_num(cost),
				"fair_value": to_num(fv),
			})
	return records


def main():
	client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
	index_url = client.get_filing_index_url("CSWC", "10-Q")
	if not index_url:
		raise SystemExit("Could not find latest 10-Q for CSWC")
	docs = client.get_documents_from_index(index_url)
	main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
	if not main_html:
		raise SystemExit("No main HTML document found for CSWC")
	resp = requests.get(main_html.url, headers=client.headers)
	resp.raise_for_status()
	soup = BeautifulSoup(resp.text, "html.parser")

	tables = extract_tables_under_heading(soup)
	records = parse_section_tables(tables)

	out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
	os.makedirs(out_dir, exist_ok=True)
	out_csv = os.path.join(out_dir, "CSWC_Schedule_from_html.csv")
	fields = [
		"company_name","investment_type","industry","interest_rate","spread","acquisition_date","maturity_date","principal_amount","amortized_cost","fair_value"
	]
	with open(out_csv, "w", newline="", encoding="utf-8") as f:
		w = csv.DictWriter(f, fieldnames=fields)
		w.writeheader()
		for r in records:
			w.writerow({k: r.get(k, "") for k in fields})
	print(f"Saved {len(records)} rows to {out_csv}")

	tables_dir = os.path.join(out_dir, "cswc_tables")
	os.makedirs(tables_dir, exist_ok=True)
	for i, t in enumerate(tables, 1):
		with open(os.path.join(tables_dir, f"cswc_table_{i}.html"), "w", encoding="utf-8") as fh:
			fh.write(simplify_table(t))
	print(f"Saved {len(tables)} simplified tables to {tables_dir}")

	# If none matched, dump a sample of all tables for manual inspection
	if not tables:
		all_dir = os.path.join(out_dir, "cswc_tables_all")
		os.makedirs(all_dir, exist_ok=True)
		for i, t in enumerate(soup.find_all("table")[:80], 1):
			with open(os.path.join(all_dir, f"cswc_all_{i}.html"), "w", encoding="utf-8") as fh:
				fh.write(simplify_table(t))
		print(f"Saved {min(80, len(soup.find_all('table')))} fallback tables to {all_dir}")


if __name__ == "__main__":
	main()


