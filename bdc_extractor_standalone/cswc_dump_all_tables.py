#!/usr/bin/env python3
"""
Dump ALL HTML tables from the latest CSWC 10-Q exhibits to simplified HTML files
for manual review. This helps us align our parser to the actual schedule tables.

Usage:
  python cswc_dump_all_tables.py
"""

import os
from bs4 import BeautifulSoup
from sec_api_client import SECAPIClient
import requests


def simplify_table(table_html: str) -> str:
	simple = BeautifulSoup(table_html, 'html.parser').find('table')
	if not simple:
		return '<table></table>'
	for ix in simple.find_all(lambda t: isinstance(t.name, str) and t.name.lower().startswith('ix:')):
		ix.replace_with(ix.get_text(' ', strip=True))
	def strip_attrs(el):
		if hasattr(el, 'attrs'):
			el.attrs = {}
		for child in getattr(el, 'children', []):
			strip_attrs(child)
	strip_attrs(simple)
	for tag_name in ['span', 'div', 'b', 'strong', 'i', 'em', 'u']:
		for t in simple.find_all(tag_name):
			t.unwrap()
	for tr in simple.find_all('tr'):
		cells = tr.find_all(['td','th'])
		if not cells or not any(c.get_text(strip=True) for c in cells):
			tr.decompose()
	allowed = {'table','thead','tbody','tr','th','td'}
	for tag in list(simple.find_all(True)):
		if tag.name not in allowed:
			tag.unwrap()
	return str(simple)


def main():
	client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
	index_url = client.get_filing_index_url('CSWC', '10-Q')
	if not index_url:
		print('No index URL found for CSWC 10-Q')
		return
	# Ensure temp_filings exists for downloads
	os.makedirs('temp_filings', exist_ok=True)
	# Download all non-image exhibits
	paths = client.download_all_exhibits_for_filing('CSWC', index_url)
	if not paths:
		print('No exhibits downloaded')
		return
	# Dump tables from each exhibit
	out_dir = os.path.join(os.path.dirname(__file__), 'output', 'cswc_tables_all')
	os.makedirs(out_dir, exist_ok=True)
	count = 0
	for p in paths:
		try:
			with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
				html = fh.read()
			soup = BeautifulSoup(html, 'html.parser')
			for i, t in enumerate(soup.find_all('table'), 1):
				count += 1
				with open(os.path.join(out_dir, f"{os.path.basename(p)}_{i}.html"), 'w', encoding='utf-8') as out:
					out.write(simplify_table(str(t)))
		except Exception as e:
			print(f"Failed {p}: {e}")
	print(f"Saved {count} tables to {out_dir}")


if __name__ == '__main__':
	main()


