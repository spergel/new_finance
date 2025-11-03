#!/usr/bin/env python3
import os, re, csv
from typing import Optional, List
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(__file__)
TABLE_PATH = os.path.join(BASE_DIR, 'output', 'arcc_tables', 'arcc_table_1.html')
OUT_CSV = os.path.join(BASE_DIR, 'output', 'ARCC_Schedule_single_table.csv')
FILING_YEAR = 2025

def normalize_text(s: str) -> str:
	return re.sub(r"\s+", " ", (s or "")).strip()

def table_to_rows(table) -> List[List[str]]:
	rows = []
	for tr in table.find_all('tr'):
		cells = tr.find_all(['td','th'])
		if not cells: continue
		rows.append([normalize_text(c.get_text(' ', strip=True)) for c in cells])
	return rows

def detect_header_map(header: List[str]):
	keys = [normalize_text(x).lower() for x in header]
	def find(*p):
		for i,k in enumerate(keys):
			if any(pp in k for pp in p):
				return i
		return None
	return {
		"company": find('company'),
		"business": find('business description'),
		"investment": find('investment'),
		"coupon": find('coupon'),
		"reference": find('reference'),
		"spread": find('spread'),
		"acq": find('acquisition date'),
		"mat": find('maturity date'),
		"shares": find('shares/units','shares','units'),
		"principal": find('principal'),
		"cost": find('amortized cost','cost'),
		"fair": find('fair value'),
		"pct_nav": find('% of net assets','percent of net assets'),
	}

def parse_money(cells: List[str], idx: Optional[int]) -> Optional[float]:
	if idx is None or idx >= len(cells):
		return None
	v = cells[idx]
	if v == '$' and idx + 1 < len(cells):
		v = cells[idx+1]
	v = v.replace('\xa0',' ').replace(',','').replace('$','').strip()
	if not v or v == '—': return None
	try:
		return float(v)
	except: return None

def year_from_date(s: str) -> Optional[int]:
	m = re.search(r"(\d{1,2})/(\d{4})$", s)
	if m:
		return int(m.group(2))
	m = re.search(r"\d{1,2}/\d{1,2}/(\d{4})$", s)
	if m:
		return int(m.group(1))
	return None

def main():
	with open(TABLE_PATH, 'r', encoding='utf-8') as fh:
		soup = BeautifulSoup(fh.read(), 'html.parser')
	t = soup.find('table')
	rows = table_to_rows(t)
	if not rows:
		print('No rows found')
		return
	mapping = detect_header_map(rows[0])
	company = None; business = None
	fieldnames = [
		'company_name','business_description','investment_type','coupon_rate','reference_rate','spread',
		'acquisition_date','maturity_date','shares_units','principal_amount','amortized_cost','fair_value','percent_of_net_assets'
	]
	os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
	with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
		w = csv.DictWriter(f, fieldnames=fieldnames)
		w.writeheader()
		last_inv = None; last_coupon = None; last_reference = None; last_spread = None
		for r in rows[1:]:
			if mapping['company'] is not None and r[mapping['company']]:
				# company line
				company = r[mapping['company']]
				if mapping['business'] is not None:
					business = r[mapping['business']] or business
				# reset investment carry when new company encountered
				last_inv = None; last_coupon = None; last_reference = None; last_spread = None
				continue
			inv = r[mapping['investment']] if mapping['investment'] is not None else ''
			coupon = r[mapping['coupon']] if mapping['coupon'] is not None else ''
			reference = r[mapping['reference']] if mapping['reference'] is not None else ''
			spread = r[mapping['spread']] if mapping['spread'] is not None else ''
			acq = r[mapping['acq']] if mapping['acq'] is not None else ''
			mat = r[mapping['mat']] if mapping['mat'] is not None else ''
			shares = r[mapping['shares']] if mapping['shares'] is not None else ''
			principal = parse_money(r, mapping['principal'])
			cost = parse_money(r, mapping['cost'])
			fair = parse_money(r, mapping['fair'])
			pct_nav = r[mapping['pct_nav']] if mapping['pct_nav'] is not None else ''
			# carry forward investment fields on continuation lines with amounts
			if not inv:
				inv = last_inv or ''
			if not coupon:
				coupon = last_coupon or ''
			if not reference:
				reference = last_reference or ''
			if not spread:
				spread = last_spread or ''
			# update carry only when present
			if inv:
				last_inv = inv
			if coupon:
				last_coupon = coupon
			if reference:
				last_reference = reference
			if spread:
				last_spread = spread
			# Year filter
			years = list(filter(None, [year_from_date(acq), year_from_date(mat)]))
			if years and all(y != FILING_YEAR for y in years):
				continue
			# skip subtotal rows
			if not inv and not any([principal, cost, fair]):
				continue
			w.writerow({
				'company_name': company or '',
				'business_description': business or '',
				'investment_type': inv,
				'coupon_rate': coupon or None,
				'reference_rate': reference or None,
				'spread': spread or None,
				'acquisition_date': acq or None,
				'maturity_date': mat or None,
				'shares_units': shares or None,
				'principal_amount': principal,
				'amortized_cost': cost,
				'fair_value': fair,
				'percent_of_net_assets': pct_nav or None,
			})
	print(f'Saved to {OUT_CSV}')

if __name__ == '__main__':
	main()
