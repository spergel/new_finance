#!/usr/bin/env python3
"""
Extract BCSF Consolidated Schedule of Investments tables from latest 10-Q HTML
and save as a normalized CSV plus simplified HTML tables.
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


def extract_tables_under_heading(soup: BeautifulSoup) -> List[BeautifulSoup]:
	matches = []
	# Relaxed matching: require schedule phrase; optionally detect date/unaudited
	required_phrase = "consolidated schedule of investments"
	optional_tokens = ["unaudited", "(dollar amounts in", "and subsidiaries"]

	def heading_matches(blob: str) -> bool:
		blob_l = blob
		if required_phrase not in blob_l:
			return False
		# Having any optional tokens increases confidence but isn't required
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
	rows = []
	for tr in table.find_all("tr"):
		cells = tr.find_all(["td", "th"])
		if not cells:
			continue
		vals = []
		for c in cells:
			vals.append(normalize_text(c.get_text(" ", strip=True)))
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

	def has_percent(tokens: List[str]) -> bool:
		return any(re.search(r"\d(\.\d+)?%", t) or "cash /" in t.lower() or "pik" in t.lower() for t in tokens)

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
			row = [x for x in r if x != ""]
			if not row:
				continue
			first = row[0]
			if is_section_header(first):
				continue
			detail_signals = has_percent(row) or has_spread_token(row) or has_date(row)

			if first and not detail_signals:
				last_company = first.strip()
				cand_ind = None
				for cell in row[1:]:
					if cell and not has_percent([cell]) and not has_date([cell]) and not has_spread_token([cell]):
						cand_ind = cell.strip()
						break
				if cand_ind:
					last_industry = cand_ind
				continue

			inv_type = first.strip()
			interest_rate = next((c for c in row if re.search(r"\d(\.\d+)?%", c)), None)
			spread_val = None
			for i, c in enumerate(row):
				cu = c.upper()
				if any(cu.startswith(tok) for tok in ["SOFR+", "PRIME+", "LIBOR+", "BASE RATE+"]):
					if i + 1 < len(row):
						nxt = row[i + 1]
						spread_val = nxt if nxt.endswith("%") else (nxt + "%" if re.match(r"^\d+(\.\d+)?$", nxt) else nxt)
						break
			dates = [c for c in row if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", c)]
			acq = dates[0] if dates else None
			mat = dates[1] if len(dates) > 1 else None
			money = [c for c in row if c.startswith("$") or re.match(r"^\$?\d[\d,]*$", c)]
			principal = money[0] if len(money) >= 1 else None
			cost = money[1] if len(money) >= 2 else None
			fair_value = money[2] if len(money) >= 3 else None
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
	index_url = client.get_filing_index_url("BCSF", "10-Q")
	if not index_url:
		raise SystemExit("Could not find latest 10-Q for BCSF")
	docs = client.get_documents_from_index(index_url)
	main_html = next((d for d in docs if d.filename.lower().endswith(".htm")), None)
	if not main_html:
		raise SystemExit("No main HTML document found for BCSF")
	resp = requests.get(main_html.url, headers=client.headers)
	resp.raise_for_status()
	soup = BeautifulSoup(resp.text, "html.parser")

	tables = extract_tables_under_heading(soup)
	records = parse_section_tables(tables)

	out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
	os.makedirs(out_dir, exist_ok=True)
	out_csv = os.path.join(out_dir, "BCSF_Schedule_latest.csv")
	fieldnames = [
		"company_name","investment_type","industry","interest_rate","spread",
		"acquisition_date","maturity_date","principal_amount","amortized_cost","fair_value","percent_of_net_assets",
	]
	with open(out_csv, "w", newline="", encoding="utf-8") as f:
		w = csv.DictWriter(f, fieldnames=fieldnames)
		w.writeheader()
		for rec in records:
			w.writerow(rec)

	tables_dir = os.path.join(out_dir, "bcsf_tables")
	os.makedirs(tables_dir, exist_ok=True)
	for i, t in enumerate(tables, 1):
		simple_html = simplify_table(t)
		with open(os.path.join(tables_dir, f"bcsf_table_{i}.html"), "w", encoding="utf-8") as fh:
			fh.write(simple_html)

	print(f"Saved {len(records)} rows to {out_csv}")
	print(f"Saved {len(tables)} simplified tables to {tables_dir}")


if __name__ == "__main__":
	main()













