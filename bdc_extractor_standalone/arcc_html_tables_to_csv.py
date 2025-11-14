#!/usr/bin/env python3
"""
Extract ARCC Consolidated Schedule of Investments tables from latest 10-Q HTML
and save: simplified HTML tables + normalized CSV in bdc_extractor_standalone/output.
"""

import os
import re
import csv
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


def extract_tables_with_schedule(soup: BeautifulSoup) -> List[BeautifulSoup]:
	matches = []
	# Relaxed tokens for ARCC: handle variants, continued sections, unaudited, etc.
	required_phrase = "schedule of investments"
	def context_matches(blob: str) -> bool:
		b = blob
		return required_phrase in b

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
		if context_matches(context_blob):
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
	# Replace ix tags
	for ix in simple.find_all(lambda t: isinstance(t.name, str) and t.name.lower().startswith("ix:")):
		ix.replace_with(ix.get_text(" ", strip=True))
	# Strip attrs
	def strip_attrs(el):
		if hasattr(el, "attrs"):
			el.attrs = {}
		for child in getattr(el, "children", []):
			strip_attrs(child)
	strip_attrs(simple)
	# Unwrap
	for tag_name in ["span", "div", "b", "strong", "i", "em", "u"]:
		for t in simple.find_all(tag_name):
			t.unwrap()
	# Remove empty rows
	for tr in simple.find_all("tr"):
		cells = tr.find_all(["td", "th"])
		if not cells or not any(c.get_text(strip=True) for c in cells):
			tr.decompose()
	# Keep basic tags
	allowed = {"table", "thead", "tbody", "tr", "th", "td"}
	for tag in list(simple.find_all(True)):
		if tag.name not in allowed:
			tag.unwrap()
	return str(simple)


def parse_money_cell(cells: List[str], idx: int) -> (Optional[float], int):
	"""Parse a monetary field possibly split into ['$', '13.2'] or just '13.2'. Returns (value, next_index)."""
	if idx >= len(cells):
		return None, idx
	val = cells[idx]
	if val == "$" and idx + 1 < len(cells):
		val = cells[idx + 1]
		next_idx = idx + 2
	else:
		next_idx = idx + 1
	val = val.replace("\xa0", " ").replace(",", "").strip().replace("$", "")
	if val in ("", "—"):
		return None, next_idx
	try:
		return float(val), next_idx
	except:
		return None, next_idx


def detect_header_map(header_cells: List[str]) -> Dict[str, int]:
	keys = [normalize_key(c) for c in header_cells]
	def find(*patterns: str) -> Optional[int]:
		for i, k in enumerate(keys):
			if any(p in k for p in patterns):
				return i
		return None
	return {
		"company": find("company"),
		"business": find("business description"),
		"investment": find("investment"),
		"coupon": find("coupon", "%"),
		"reference": find("reference"),
		"spread": find("spread"),
		"acq": find("acquisition date"),
		"mat": find("maturity date"),
		"shares": find("shares/units", "shares", "units"),
		"principal": find("principal"),
		"cost": find("amortized cost", "cost"),
		"fair": find("fair value"),
		"pct_nav": find("% of net assets", "percent of net assets"),
	}


def parse_section_tables(tables: List[BeautifulSoup], filing_year: Optional[int]) -> List[Dict[str, Optional[str]]]:
	records: List[Dict[str, Optional[str]]] = []

	def looks_like_company_only(row: List[str]) -> bool:
		# company row tends to have text in the first cell and empty investment/coupon/principal fields
		return bool(row and row[0]) and not any(re.search(r"\d(\.\d+)?%", c) for c in row)

	def parse_date_token(s: str) -> Optional[int]:
		# Accept MM/YYYY or MM/DD/YYYY ⇒ return year int
		m = re.search(r"(\d{2})/(\d{4})$", s)
		if m:
			try:
				return int(m.group(2))
			except:
				return None
		m2 = re.search(r"\d{1,2}/\d{1,2}/(\d{4})$", s)
		if m2:
			try:
				return int(m2.group(1))
			except:
				return None
		return None

	for table in tables:
		rows = table_to_rows(table)
		if not rows:
			continue
		header = rows[0]
		mapping = detect_header_map(header)
		current_company = None
		current_business = None

		for r in rows[1:]:
			row = [x for x in r]  # keep positions for monetary parsing
			if not any(c for c in row):
				continue

			# Company-only row update
			if mapping["company"] is not None and row[mapping["company"]]:
				inv_idx = mapping.get("investment")
				biz_idx = mapping.get("business")
				invest_txt = row[inv_idx] if inv_idx is not None and inv_idx < len(row) else ""
				biz_txt = row[biz_idx] if biz_idx is not None and biz_idx < len(row) else ""
				# Treat as industry header if both business and investment are empty
				if not invest_txt and not biz_txt:
					# industry section header; do not change current_company/current_business
					pass
				else:
					current_company = row[mapping["company"]]
					if biz_idx is not None and biz_idx < len(row) and biz_txt:
						current_business = biz_txt
					continue

			# Build record
			investment_type = row[mapping["investment"]] if mapping["investment"] is not None and mapping["investment"] < len(row) else ""
			coupon_rate = row[mapping["coupon"]] if mapping["coupon"] is not None and mapping["coupon"] < len(row) else ""
			reference_rate = row[mapping["reference"]] if mapping["reference"] is not None and mapping["reference"] < len(row) else ""
			spread = row[mapping["spread"]] if mapping["spread"] is not None and mapping["spread"] < len(row) else ""
			acq = row[mapping["acq"]] if mapping["acq"] is not None and mapping["acq"] < len(row) else ""
			mat = row[mapping["mat"]] if mapping["mat"] is not None and mapping["mat"] < len(row) else ""
			shares_units = row[mapping["shares"]] if mapping["shares"] is not None and mapping["shares"] < len(row) else ""

			# Monetary with possible $ separators
			principal = None; cost = None; fair_value = None
			if mapping["principal"] is not None and mapping["principal"] < len(row):
				principal, _ = parse_money_cell(row, mapping["principal"])
			if mapping["cost"] is not None and mapping["cost"] < len(row):
				cost, _ = parse_money_cell(row, mapping["cost"])
			if mapping["fair"] is not None and mapping["fair"] < len(row):
				fair_value, _ = parse_money_cell(row, mapping["fair"])

			pct_nav = row[mapping["pct_nav"]] if mapping["pct_nav"] is not None and mapping["pct_nav"] < len(row) else ""

			# Filter to filing year if provided
			if filing_year is not None:
				years = []
				if acq:
					y = parse_date_token(acq)
					if y: years.append(y)
				if mat:
					y = parse_date_token(mat)
					if y: years.append(y)
				if years and all(y != filing_year for y in years):
					continue

			# Skip subtotal/empty lines without investment and without any monetary values
			has_any_money = any(v is not None for v in [principal, cost, fair_value])
			if not investment_type and not has_any_money:
				continue

			records.append({
				"company_name": current_company or "",
				"business_description": current_business or "",
				"investment_type": investment_type,
				"coupon_rate": coupon_rate or None,
				"reference_rate": reference_rate or None,
				"spread": spread or None,
				"acquisition_date": acq or None,
				"maturity_date": mat or None,
				"shares_units": shares_units or None,
				"principal_amount": principal,
				"amortized_cost": cost,
				"fair_value": fair_value,
				"percent_of_net_assets": pct_nav or None,
			})
	return records


def main():
	client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
	index_url = client.get_filing_index_url("ARCC", "10-Q")
	if not index_url:
		raise SystemExit("Could not find latest 10-Q for ARCC")
	docs = client.get_documents_from_index(index_url)
	main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
	if not main_html:
		raise SystemExit("No main HTML document found for ARCC")
	resp = requests.get(main_html.url, headers=client.headers)
	resp.raise_for_status()
	soup = BeautifulSoup(resp.text, "html.parser")

	# Infer filing year from filename if possible (e.g., arcc-20250930.htm)
	filing_year = None
	m = re.search(r"(20\d{2})\d{4}\.htm$", main_html.filename or main_html.url)
	if m:
		try:
			filing_year = int(m.group(1))
		except:
			filing_year = None

	tables = extract_tables_with_schedule(soup)

	# Save simplified tables
	out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
	os.makedirs(out_dir, exist_ok=True)
	tables_dir = os.path.join(out_dir, "arcc_tables")
	os.makedirs(tables_dir, exist_ok=True)
	for i, t in enumerate(tables, 1):
		simple_html = simplify_table(t)
		with open(os.path.join(tables_dir, f"arcc_table_{i}.html"), "w", encoding="utf-8") as fh:
			fh.write(simple_html)

	# Parse to CSV
	records = parse_section_tables(tables, filing_year)
	out_csv = os.path.join(out_dir, "ARCC_Schedule_latest.csv")
	fieldnames = [
		"company_name","business_description","investment_type","coupon_rate","reference_rate","spread",
		"acquisition_date","maturity_date","shares_units","principal_amount","amortized_cost","fair_value","percent_of_net_assets",
	]
	with open(out_csv, "w", newline="", encoding="utf-8") as f:
		w = csv.DictWriter(f, fieldnames=fieldnames)
		w.writeheader()
		for rec in records:
			w.writerow(rec)
	print(f"Saved {len(records)} rows to {out_csv}")
	print(f"Saved {len(tables)} simplified tables to {tables_dir}")


if __name__ == "__main__":
	main()
