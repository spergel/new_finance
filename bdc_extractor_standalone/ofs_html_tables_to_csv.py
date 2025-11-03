#!/usr/bin/env python3
"""
Extract OFS Schedule of Investments (Continued) tables from latest 10-Q HTML
and save as a normalized CSV in bdc_extractor_standalone/output.

Heading targeted (normalized):
  "ofs capital corporation and subsidiaries consolidated schedule of investments - continued (unaudited) september 30, 2025 (dollar amounts in thousands)"

Usage:
  python ofs_html_tables_to_csv.py
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


def is_dash(text: str) -> bool:
	return normalize_key(text) in {"—", "-", "n/m", "n/a", "—%", "-%", "— $", "$ —"}


def parse_number(text: str) -> Optional[float]:
	if not text:
		return None
	t = normalize_text(text)
	if is_dash(t):
		return None
	# remove $ and commas and NBSP
	t = t.replace("$", "").replace(",", "").replace("\xa0", " ")
	# strip trailing percent sign for numerics we still keep as float
	t = t.replace("%", "").strip()
	try:
		return float(t)
	except ValueError:
		return None


def detect_header_map(header_cells: List[str]) -> Dict[str, int]:
	"""Map canonical fields to column indexes based on header text tokens."""
	joined = " ".join(header_cells)
	keys = [normalize_key(c) for c in header_cells]

	def find_index(patterns: List[str]) -> Optional[int]:
		for i, k in enumerate(keys):
			if any(p in k for p in patterns):
				return i
		return None

	return {
		"company": find_index(["portfolio company", "company", "issuer"]),
		"investment_type": find_index(["investment type", "class", "security type", "debt", "equity"]),
		"industry": find_index(["industry"]),
		"interest_rate": find_index(["interest rate", "cash / pik", "coupon"]),
		"spread_token": find_index(["spread above index", "sofr+", "libor+", "spread"]),
		"acq_date": find_index(["initial acquisition date", "acquisition date"]),
		"maturity": find_index(["maturity"]),
		"principal": find_index(["principal amount", "par", "face amount"]),
		"cost": find_index(["amortized cost", "cost"]),
		"fair_value": find_index(["fair value"]),
		"percent_nav": find_index(["percent of net assets", "% of net assets"]) ,
	}


def extract_tables_under_heading(soup: BeautifulSoup, heading_norm: str) -> List[BeautifulSoup]:
	matches = []
	# Token-based relaxed matching
	required_any = [
		"ofs capital corporation",  # allow "and subsidiaries" to vary
		"consolidated schedule of investments",
		"continued",
		"unaudited",
		"september 30, 2025",
		"dollar amounts in thousands",
	]
	def heading_matches(blob: str) -> bool:
		blob_l = blob
		# must contain schedule phrase and date at minimum
		must = ["consolidated schedule of investments", "september 30, 2025"]
		if not all(m in blob_l for m in must):
			return False
		# also require at least one of company/continued/unaudited/dollars
		count = sum(1 for t in required_any if t in blob_l)
		return count >= 3

	for table in soup.find_all("table"):
		context_texts = []
		cur = table
		for _ in range(12):  # look a bit further back
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
		vals = []
		for c in cells:
			# prefer textual content without child tags like ix:nonFraction; use their text
			vals.append(normalize_text(c.get_text(" ", strip=True)))
		rows.append(vals)
	return rows


def simplify_table(table: BeautifulSoup) -> str:
	"""Return a simplified HTML string for a table (remove styles/classes/formatting)."""
	# Work on a copy
	simple = BeautifulSoup(str(table), "html.parser").find("table")
	if not simple:
		return "<table></table>"
	# Replace ix:* with text
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


def coerce_interest_and_spread(raw_interest: str, raw_spread: str) -> (Optional[str], Optional[str]):
	interest = normalize_text(raw_interest) if raw_interest else ""
	spread = normalize_text(raw_spread) if raw_spread else ""
	interest_out = interest or None
	spread_out = spread or None
	return interest_out, spread_out


def parse_section_tables(tables: List[BeautifulSoup]) -> List[Dict[str, Optional[str]]]:
	records: List[Dict[str, Optional[str]]] = []

	def has_percent(tokens: List[str]) -> bool:
		return any(re.search(r"\d(\.\d+)?%$", t) or " % " in f" {t} " or "cash /" in t.lower() or "pik" in t.lower() for t in tokens)

	def has_spread_token(tokens: List[str]) -> bool:
		return any(t.upper().startswith(("SOFR+", "PRIME+", "LIBOR+", "BASE RATE+", "SOFR", "PRIME", "LIBOR", "BASE RATE")) for t in tokens)

	def has_date(tokens: List[str]) -> bool:
		return any(re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", t) for t in tokens)

	def is_section_header(text: str) -> bool:
		t = text.lower()
		return any(k in t for k in ["investments", "debt and equity", "non-control", "non-affiliate"])

	for table in tables:
		rows = table_to_rows(table)
		if not rows:
			continue

		last_company: Optional[str] = None
		last_industry: Optional[str] = None

		for r in rows:
			# Clean and drop spacer-only cells
			row = [x for x in r if x != ""]
			if not row:
				continue

			first = row[0]
			if is_section_header(first):
				continue

			# Decide if company row vs detail row
			detail_signals = has_percent(row) or has_spread_token(row) or has_date(row)

			if first and not detail_signals:
				# Likely a company/industry label row
				last_company = first.strip()
				# Try to capture industry from the next non-empty cell
				cand_ind = None
				for cell in row[1:]:
					if cell and not has_percent([cell]) and not has_date([cell]) and not has_spread_token([cell]):
						cand_ind = cell.strip()
						break
				if cand_ind:
					last_industry = cand_ind
				continue

			# Detail row
			inv_type = first.strip()

			# Interest rate (accept e.g., "10.40%" or "5.94% cash / 6.50% PIK")
			interest_rate = next((c for c in row if re.search(r"\d(\.\d+)?%", c)), None)

			# Spread token/value
			spread_val = None
			for i, c in enumerate(row):
				cu = c.upper()
				if any(cu.startswith(tok) for tok in ["SOFR+", "PRIME+", "LIBOR+", "BASE RATE+"]):
					if i + 1 < len(row):
						nxt = row[i + 1]
						spread_val = nxt if nxt.endswith("%") else (nxt + "%" if re.match(r"^\d+(\.\d+)?$", nxt) else nxt)
						break

			# Dates
			dates = [c for c in row if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", c)]
			acq = dates[0] if dates else None
			mat = dates[1] if len(dates) > 1 else None

			# Monetary amounts: scan $ or numeric blocks
			money = [c for c in row if c.startswith("$") or re.match(r"^\$?\d[\d,]*$", c)]
			principal = money[0] if len(money) >= 1 else None
			cost = money[1] if len(money) >= 2 else None
			fair_value = money[2] if len(money) >= 3 else None

			# Percent of NAV: choose last percentage-like that is not the same as interest/spread
			pct_nav = None
			percent_tokens = [c for c in row if c.endswith("%")]
			if percent_tokens:
				pct_nav = percent_tokens[-1]

			def parse_number(text: Optional[str]) -> Optional[float]:
				if not text:
					return None
				t = text.replace("\xa0", " ").replace(",", "").strip()
				t = t.replace("$", "")
				if t in ("—", "—%", "— $"):
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

			records.append({
				"company_name": last_company or "",
				"investment_type": inv_type,
				"industry": last_industry or "",
				"interest_rate": interest_rate,
				"spread": spread_val,
				"acquisition_date": acq,
				"maturity_date": mat,
				"principal_amount": parse_number(principal),
				"amortized_cost": parse_number(cost),
				"fair_value": parse_number(fair_value),
				"percent_of_net_assets": parse_number(pct_nav),
			})
	return records


def main():
	client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
	index_url = client.get_filing_index_url("OFS", "10-Q")
	if not index_url:
		raise SystemExit("Could not find latest 10-Q for OFS")
	docs = client.get_documents_from_index(index_url)
	main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
	if not main_html:
		raise SystemExit("No main HTML document found for OFS")
	resp = requests.get(main_html.url, headers=client.headers)
	resp.raise_for_status()
	soup = BeautifulSoup(resp.text, "html.parser")

	heading_norm = (
		"ofs capital corporation and subsidiaries"
		" consolidated schedule of investments - continued (unaudited)"
		" september 30, 2025"
		" (dollar amounts in thousands)"
	)
	tables = extract_tables_under_heading(soup, normalize_key(heading_norm))
	records = parse_section_tables(tables)

	out_dir = os.path.join(os.path.dirname(__file__), "output")
	os.makedirs(out_dir, exist_ok=True)
	out_csv = os.path.join(out_dir, "OFS_Schedule_Continued_2025Q3.csv")
	fieldnames = [
		"company_name",
		"investment_type",
		"industry",
		"interest_rate",
		"spread",
		"acquisition_date",
		"maturity_date",
		"principal_amount",
		"amortized_cost",
		"fair_value",
		"percent_of_net_assets",
	]
	with open(out_csv, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=fieldnames)
		writer.writeheader()
		for rec in records:
			writer.writerow(rec)
	print(f"Saved {len(records)} rows to {out_csv}")

	# Also save each matched table as simplified HTML
	tables_dir = os.path.join(out_dir, "ofs_tables")
	os.makedirs(tables_dir, exist_ok=True)
	for i, t in enumerate(tables, 1):
		simple_html = simplify_table(t)
		with open(os.path.join(tables_dir, f"ofs_table_{i}.html"), "w", encoding="utf-8") as fh:
			fh.write(simple_html)
	print(f"Saved {len(tables)} simplified tables to {tables_dir}")


if __name__ == "__main__":
	main()
