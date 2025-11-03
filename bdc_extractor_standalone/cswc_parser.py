#!/usr/bin/env python3
"""
CSWC (Capital Southwest Corp) Investment Extractor
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

from sec_api_client import SECAPIClient
from standardization import standardize_investment_type, standardize_industry, standardize_reference_rate

logger = logging.getLogger(__name__)

@dataclass
class CSWCInvestment:
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


class CSWCExtractor:
	def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
		self.headers = {'User-Agent': user_agent}
		self.sec_client = SECAPIClient(user_agent=user_agent)

	def _normalize_company_name(self, raw: str) -> str:
		name = raw or ''
		name = re.sub(r'\s*\*\*\*\s*$', '', name)
		name = re.sub(r'\s+', ' ', name).strip()
		# Remove embedded instrument suffixes
		name = re.sub(r',\s*Revolving Loan.*$', '', name, flags=re.IGNORECASE)
		name = re.sub(r',\s*First Lien\b.*$', '', name, flags=re.IGNORECASE)
		name = re.sub(r',\s*Second Lien\b.*$', '', name, flags=re.IGNORECASE)
		name = re.sub(r',\s*Secured Debt\b.*$', '', name, flags=re.IGNORECASE)
		name = re.sub(r',\s*Senior Secured\b.*$', '', name, flags=re.IGNORECASE)
		name = re.sub(r',\s*Term Loan\b.*$', '', name, flags=re.IGNORECASE)
		# Normalize commas before entity suffixes
		name = re.sub(r',\s+(Inc|LLC|Ltd|Corp|Co|LP)\.?' , r' \1', name, flags=re.IGNORECASE)
		# Normalize punctuation in suffixes
		name = re.sub(r'\bInc\.\b', 'Inc', name, flags=re.IGNORECASE)
		name = re.sub(r'\bLLC\.?\b', 'LLC', name, flags=re.IGNORECASE)
		name = re.sub(r'\bLtd\.\b', 'Ltd', name, flags=re.IGNORECASE)
		name = re.sub(r'\bCorp\.\b', 'Corp', name, flags=re.IGNORECASE)
		name = re.sub(r'\bCo\.\b', 'Co', name, flags=re.IGNORECASE)
		# Remove token noise
		name = re.sub(r'\b(SOFR|LIBOR|PRIME|EURIBOR|BASE\s+RATE)\s*\+\s*[\d\.]+%?', '', name, flags=re.IGNORECASE)
		name = re.sub(r'\b(?:[\d\.]+\s*%\s*Floor|Floor\s*[\d\.]+\s*%)\b', '', name, flags=re.IGNORECASE)
		name = re.sub(r'\b(?:PIK\b[^\d%]{0,20}[\d\.]+\s*%|[\d\.]+\s*%\s*PIK)\b', '', name, flags=re.IGNORECASE)
		name = re.sub(r'\bMaturity\s*Date\s*\d{1,2}/\d{1,2}/\d{2,4}\b', '', name, flags=re.IGNORECASE)
		name = re.sub(r'\s+[\-\u2013]\s+.*$', '', name).strip()
		return name.rstrip('., ').strip()

	def _normalize_cswc_row(self, inv: CSWCInvestment) -> Dict:
		# Base dict
		row = {
			'company_name': inv.company_name or '',
			'industry': inv.industry or '',
			'business_description': inv.business_description or '',
			'investment_type': inv.investment_type or 'Unknown',
			'acquisition_date': inv.acquisition_date or '',
			'maturity_date': inv.maturity_date or '',
			'principal_amount': inv.principal_amount if inv.principal_amount is not None else '',
			'cost': inv.cost if inv.cost is not None else '',
			'fair_value': inv.fair_value if inv.fair_value is not None else '',
			'interest_rate': inv.interest_rate or '',
			'reference_rate': inv.reference_rate or '',
			'spread': inv.spread or '',
			'commitment_limit': '',
			'undrawn_commitment': ''
		}

		# Clean company name
		row['company_name'] = self._normalize_company_name(row['company_name'])

		# Normalize investment type
		it = (row['investment_type'] or '').lower()
		cname_l = row['company_name'].lower()
		if 'revolving' in it:
			row['investment_type'] = 'First lien senior secured revolving loan'
		elif 'first lien' in it or 'senior secured' in it or 'secured debt' in it:
			row['investment_type'] = 'First lien senior secured loan'
		elif 'second lien' in it:
			row['investment_type'] = 'Second lien senior secured loan'
		elif 'unitranche' in it:
			row['investment_type'] = 'Unitranche loan'
		elif 'unsecured' in it:
			row['investment_type'] = 'Unsecured debt'
		elif 'preferred' in it or 'preferred' in cname_l:
			row['investment_type'] = 'Preferred equity'
		elif 'warrant' in it or 'warrants' in cname_l:
			row['investment_type'] = 'Warrants'
		elif 'common stock' in it or 'member units' in it or 'equity' in it:
			row['investment_type'] = 'Equity'

		# Format numeric fields to floats if strings
		for field in ['principal_amount', 'cost', 'fair_value']:
			val = row[field]
			if isinstance(val, str):
				try:
					cleaned = val.replace(',', '').strip()
					row[field] = float(cleaned) if cleaned else ''
				except Exception:
					row[field] = ''

		return row

	def _extract_revolver_commitments_from_investments(self, rows: List[Dict]) -> Dict[str, Dict[str, float]]:
		commits: Dict[str, Dict[str, float]] = {}
		for r in rows:
			it = (r.get('investment_type') or '').lower()
			if 'revolving' not in it:
				continue
			company = r.get('company_name', '')
			if not company:
				continue
			principal = r.get('principal_amount')
			fair_val = r.get('fair_value')
			# Heuristic: if principal is missing/zero but fair_value present, treat fair_value as commitment
			try:
				p = float(principal) if principal not in (None, '') else 0.0
			except Exception:
				p = 0.0
			try:
				fv = float(fair_val) if fair_val not in (None, '') else 0.0
			except Exception:
				fv = 0.0
			if company not in commits:
				commits[company] = {'commitment_limit': 0.0, 'undrawn_commitment': 0.0}
			if p <= 0 and fv > 0:
				commits[company]['commitment_limit'] = max(commits[company]['commitment_limit'], fv)
				commits[company]['undrawn_commitment'] = max(commits[company]['undrawn_commitment'], fv)
		return commits

	def extract_from_ticker(self, ticker: str = "CSWC") -> Dict:
		logger.info(f"Extracting investments for {ticker}")
		cik = self.sec_client.get_cik(ticker)
		if not cik:
			raise ValueError(f"Could not find CIK for ticker {ticker}")
		index_url = self.sec_client.get_filing_index_url(ticker, "10-Q", cik=cik)
		if not index_url:
			raise ValueError(f"Could not find 10-Q filing for {ticker}")
		acc = re.search(r'/(\d{10}-\d{2}-\d{6})-index\.html', index_url)
		if not acc:
			raise ValueError("Could not parse accession number")
		accession = acc.group(1)
		accession_no_hyphens = accession.replace('-', '')
		txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
		return self.extract_from_url(txt_url, "Capital_Southwest_Corp", cik)

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
		investments: List[CSWCInvestment] = []
		for ctx in contexts:
			inv = self._build_investment(ctx, facts_by_context.get(ctx['id'], []))
			if inv:
				investments.append(inv)

		# Normalize and de-duplicate by (company_name, investment_type)
		normalized_rows: List[Dict] = []
		seen_keys = set()
		for inv in investments:
			row = self._normalize_cswc_row(inv)
			# Filter out rows without financials
			has_fin = any(bool(row.get(f)) for f in ['principal_amount','cost','fair_value'])
			if not has_fin:
				continue
			key = (row['company_name'].lower(), row['investment_type'].lower())
			if key in seen_keys:
				continue
			seen_keys.add(key)
			normalized_rows.append(row)

		# Enrich revolvers with commitment heuristics
		commitments = self._extract_revolver_commitments_from_investments(normalized_rows)
		for r in normalized_rows:
			if 'revolving' in (r.get('investment_type') or '').lower():
				cm = commitments.get(r.get('company_name',''))
				if cm:
					r['commitment_limit'] = cm.get('commitment_limit') or ''
					r['undrawn_commitment'] = cm.get('undrawn_commitment') or ''

		total_principal = sum(float(r['principal_amount']) for r in normalized_rows if isinstance(r.get('principal_amount'), (int,float)))
		total_cost = sum(float(r['cost']) for r in normalized_rows if isinstance(r.get('cost'), (int,float)))
		total_fair_value = sum(float(r['fair_value']) for r in normalized_rows if isinstance(r.get('fair_value'), (int,float)))
		ind_br = defaultdict(int)
		type_br = defaultdict(int)
		for r in normalized_rows:
			ind_br[r['industry']] += 1
			type_br[r['investment_type']] += 1

		out_dir = 'output'
		os.makedirs(out_dir, exist_ok=True)
		out_file = os.path.join(out_dir, 'CSWC_Capital_Southwest_Corp_investments.csv')
		with open(out_file, 'w', newline='', encoding='utf-8') as f:
			fieldnames = [
				'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
				'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','commitment_limit','undrawn_commitment'
			]
			writer = csv.DictWriter(f, fieldnames=fieldnames)
			writer.writeheader()
			for r in normalized_rows:
				# Apply standardization before writing
				if 'investment_type' in r:
					r['investment_type'] = standardize_investment_type(r.get('investment_type'))
				if 'industry' in r:
					r['industry'] = standardize_industry(r.get('industry'))
				if 'reference_rate' in r:
					r['reference_rate'] = standardize_reference_rate(r.get('reference_rate')) or ''
				
				writer.writerow({k: (r.get(k) if r.get(k) is not None else '') for k in fieldnames})

		logger.info(f"Saved to {out_file}")
		return {
			'company_name': company_name,
			'cik': cik,
			'total_investments': len(normalized_rows),
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
		res = {'company_name':'Unknown','industry':'Unknown','investment_type':'Unknown'}
		if ',' in identifier:
			last = identifier.rfind(',')
			company = identifier[:last].strip()
			tail = identifier[last+1:].strip()
		else:
			company = identifier.strip()
			tail = ''
		res['company_name'] = re.sub(r'\s+',' ', company).rstrip(',')
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
		sp = re.compile(r'<([^>\s:]+:[^>\s]+)[^>]*contextRef="([^"]*)"[^>]*>([^<]*)</\1>', re.DOTALL)
		for concept, cref, val in sp.findall(content):
			if val and cref:
				facts[cref].append({'concept': concept, 'value': val.strip()})
		ixp = re.compile(r'<ix:nonFraction[^>]*?name="([^"]+)"[^>]*?contextRef="([^"]+)"[^>]*?(?:id="([^"]+)")?[^>]*>(.*?)</ix:nonFraction>', re.DOTALL|re.IGNORECASE)
		for m in ixp.finditer(content):
			name = m.group(1); cref = m.group(2); html = m.group(4)
			if not cref: continue
			txt = re.sub(r'<[^>]+>', '', html).strip()
			if txt:
				facts[cref].append({'concept': name, 'value': txt})
			start = max(0, m.start()-3000); end = min(len(content), m.end()+3000)
			window = content[start:end]
			# Reference rate with optional frequency like SOFR (Q/M/S)
			ref_freq = re.search(r'\b(SOFR|SONIA|PRIME|LIBOR|BASE RATE|EURIBOR)\b\s*(?:\((Q|M|S)\))?', window, re.IGNORECASE)
			if ref_freq:
				token = ref_freq.group(1).upper()
				freq = ref_freq.group(2).upper() if ref_freq.group(2) else None
				facts[cref].append({'concept':'derived:ReferenceRateToken','value': f"{token} ({freq})" if freq else token})
			floor = re.search(r'\bfloor\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
			if floor:
				facts[cref].append({'concept':'derived:FloorRate','value': floor.group(1)})
			pik = re.search(r'\bPIK\b[^\d%]{0,20}([\d\.]+)\s*%?', window, re.IGNORECASE)
			if pik:
				facts[cref].append({'concept':'derived:PIKRate','value': pik.group(1)})
			dates = re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', window)
			if dates:
				if len(dates)>=2:
					facts[cref].append({'concept':'derived:AcquisitionDate','value': dates[0]})
					facts[cref].append({'concept':'derived:MaturityDate','value': dates[-1]})
				else:
					facts[cref].append({'concept':'derived:MaturityDate','value': dates[0]})
		return facts

	def _build_investment(self, context: Dict, facts: List[Dict]) -> Optional[CSWCInvestment]:
		if context['company_name']=='Unknown':
			return None
		inv = CSWCInvestment(
			company_name=context['company_name'],
			investment_type=context['investment_type'],
			industry=context['industry'],
			context_ref=context['id']
		)
		# Extract tokens from raw identifier to populate fields and aid cleanup
		raw_text = context.get('raw_identifier') or inv.company_name
		tokens = self._extract_tokens_from_text(raw_text)
		cleaned_name = self._normalize_company_name(raw_text)
		if len(cleaned_name) <= len(inv.company_name) or inv.company_name.lower() in raw_text.lower():
			inv.company_name = cleaned_name
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
		# Fill missing fields from identifier tokens
		if not inv.reference_rate and tokens.get('reference_rate'):
			inv.reference_rate = tokens['reference_rate']
		if not inv.spread and tokens.get('spread'):
			inv.spread = tokens['spread']
		if not inv.floor_rate and tokens.get('floor_rate'):
			inv.floor_rate = tokens['floor_rate']
		if not inv.pik_rate and tokens.get('pik_rate'):
			inv.pik_rate = tokens['pik_rate']
		if not inv.maturity_date and tokens.get('maturity_date'):
			inv.maturity_date = tokens['maturity_date']
		if not inv.acquisition_date and context.get('start_date'):
			inv.acquisition_date = context['start_date'][:10]
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

	def _extract_tokens_from_text(self, text: str) -> Dict[str, Optional[str]]:
		tokens: Dict[str, Optional[str]] = {'reference_rate': None, 'spread': None, 'floor_rate': None, 'pik_rate': None, 'maturity_date': None}
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
		return tokens

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


def main():
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
	ex=CSWCExtractor()
	try:
		res=ex.extract_from_ticker('CSWC')
		print(f"Extracted {res['total_investments']} investments")
	except Exception as e:
		print(f"[ERROR] {e}")

if __name__=='__main__':
	main()





		print(f"[ERROR] {e}")

if __name__=='__main__':
	main()




