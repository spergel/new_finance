## BDC Scraper Spec (LLM-ready)

This single file defines the minimal, standard way to build a BDC scraper that:
- Uses the existing `sec_api_client.py` to fetch the latest filing
- Extracts investments into a consistent, flat CSV schema
- Saves output to `output/[TICKER]_[Company_Name]_investments.csv`

### Output Schema (CSV)
Columns (header exactly):
```
company_name,industry,business_description,investment_type,acquisition_date,maturity_date,principal_amount,cost,fair_value,interest_rate,reference_rate,spread,floor_rate,pik_rate
```
Notes:
- Dates: use as-is when captured; normalize to YYYY-MM-DD when clear
- Numbers: store as plain numbers without commas
- Empty/missing fields: leave blank

### How to Fetch Filings
Use `sec_api_client.SECAPIClient`:
```python
from sec_api_client import SECAPIClient

client = SECAPIClient(user_agent="BDC-Extractor/1.0 email@example.com")
cik = client.get_cik("OBDC")  # or any BDC ticker
index_url = client.get_filing_index_url("OBDC", "10-Q", cik=cik)
result = client.fetch_filing_by_index_url(index_url, ticker="OBDC", filing_type="10-Q", save_to_file=False)
text = result.text  # inline XBRL/text bundle
```

### Parsing Strategy (Standard)
1) Identify investments using the XBRL Investment Identifier Axis (typed member):
- Look for contexts with:
  - `xbrldi:typedMember dimension="us-gaap:InvestmentIdentifierAxis"`
  - The domain text is the “identifier” string to parse for `company_name` and `investment_type`

2) Enrich industries using the industry axis (explicit member):
- Look for contexts with:
  - `xbrldi:explicitMember dimension="us-gaap:EquitySecuritiesByIndustryAxis"`
  - Map QNames like `obdc:AdvertisingAndMediaMember` to readable names (e.g., `Advertising and Media`)
- Join to investment contexts by the same `<instant>` date

3) Facts / amounts / rates:
- Group facts by `contextRef`
- Extract numeric amounts using common concept names (case-insensitive substring match):
  - principal: `principalamount`, `ownedbalanceprincipalamount`, `outstandingprincipal`
  - cost: `amortized` or `basis`, or `ownedatcost`
  - fair value: `fairvalue` or `ownedatfairvalue`
- Rates: capture as strings (append `%` where appropriate)
  - interest rate: `investmentinterestrate`
  - spread: `investmentbasisspreadvariablerate`
  - derived tokens from nearby inline XBRL: `SOFR+`, `PRIME+`, `LIBOR+`, `Base Rate+`, `EURIBOR+`
  - floor/PIK: look for `floor` / `PIK` near inline facts
- Dates: infer `acquisition_date`/`maturity_date` from nearby mm/dd/yyyy patterns; fallback to context period

### Minimal Extractor Skeleton
```python
import re, csv, os
from collections import defaultdict
from sec_api_client import SECAPIClient

def extract_bdc(ticker: str, company_name: str):
    client = SECAPIClient(user_agent="BDC-Extractor/1.0 email@example.com")
    cik = client.get_cik(ticker)
    index_url = client.get_filing_index_url(ticker, "10-Q", cik=cik)
    filing = client.fetch_filing_by_index_url(index_url, ticker=ticker, filing_type="10-Q", save_to_file=False)
    content = filing.text

    # 1) contexts with InvestmentIdentifierAxis → parse company, type
    contexts = []  # [{ id, company_name, investment_type, instant, start_date, end_date, industry? }]
    # 2) build industry_by_instant from EquitySecuritiesByIndustryAxis explicit members
    industry_by_instant = {}
    # 3) facts_by_context from standard and inline XBRL; derive rates/dates nearby
    facts_by_context = defaultdict(list)

    # ...implementation mirrors `obdc_parser.py`/`ocsl_parser.py`...

    # Build investments and write CSV
    os.makedirs("output", exist_ok=True)
    outfile = os.path.join("output", f"{ticker}_{company_name.replace(' ', '_')}_investments.csv")
    with open(outfile, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'company_name','industry','business_description','investment_type','acquisition_date','maturity_date',
            'principal_amount','cost','fair_value','interest_rate','reference_rate','spread','floor_rate','pik_rate'
        ])
        writer.writeheader()
        # writer.writerow({...}) for each investment
    return outfile
```

### Naming Convention
CSV filename: `output/[TICKER]_[Company_Name]_investments.csv`

### Respectful Access
- Always pass a real `User-Agent`
- Add small delays if scraping multiple filings

This spec is sufficient for an LLM to implement a new BDC scraper using the existing client and produce standardized CSV output.


