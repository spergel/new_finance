#!/usr/bin/env python3
"""
Custom ARCC (Ares Capital Corporation) Investment Extractor

Finds latest 10-Q filing, extracts XBRL + HTML, merges, and saves to
`bdc_extractor_standalone/output/Ares_Capital_Corporation_html_investments.csv`.
"""

import logging
import os
import re
from typing import Optional

from complete_extractor import CompleteBDCExtractor
from sec_api_client import SECAPIClient


logger = logging.getLogger(__name__)


def _build_filing_urls(cik: str, index_url: str) -> Optional[tuple[str, str]]:
	m = re.search(r"/(\d{10}-\d{2}-\d{6})-index\.html", index_url)
	if not m:
		return None
	accession = m.group(1)
	accession_no_hyphens = accession.replace('-', '')
	# .txt contains inline XBRL; .htm is the main HTML filing
	txt_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/{accession}.txt"
	# Common filename pattern: arcc-YYYYMMDD.htm; fall back to index replacement if needed
	htm_url_guess = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_hyphens}/arcc-{accession[5:13].replace('-', '')}.htm"
	# If guess is risky, still return; Complete extractor will request it. Many ARCC filings use predictable names.
	return txt_url, htm_url_guess


def main():
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

	client = SECAPIClient(user_agent="BDC-Extractor/1.0 contact@example.com")
	ticker = "ARCC"
	company_name = "Ares Capital Corporation"
	logger.info(f"Extracting investments for {ticker}")
	cik = client.get_cik(ticker)
	if not cik:
		raise RuntimeError("Could not resolve CIK for ARCC")
	logger.info(f"Found CIK: {cik}")

	index_url = client.get_filing_index_url(ticker, "10-Q", cik=cik)
	if not index_url:
		raise RuntimeError("Could not locate latest 10-Q index for ARCC")
	logger.info(f"Filing index: {index_url}")

	urls = _build_filing_urls(cik, index_url)
	if not urls:
		raise RuntimeError("Could not parse accession/URLs for ARCC")
	txt_url, htm_url = urls
	logger.info(f"XBRL URL: {txt_url}")
	logger.info(f"HTML URL: {htm_url}")

	extractor = CompleteBDCExtractor()
	result = extractor.extract_from_filing(txt_url=txt_url, htm_url=htm_url, company_name=company_name, cik=cik)

	# Save to local output directory
	out_dir = os.path.join(os.path.dirname(__file__), 'output')
	os.makedirs(out_dir, exist_ok=True)
	extractor.save_results(result, output_dir=out_dir)
	logger.info(f"Saved results to {out_dir}")

	print(f"\n[SUCCESS] Extracted {result.total_investments} investments for {company_name}")
	print(f"  Total Cost: ${result.total_cost:,.0f}")
	print(f"  Total Fair Value: ${result.total_fair_value:,.0f}")


if __name__ == "__main__":
	main()
