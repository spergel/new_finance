### HTML Consolidated Schedule of Investments → CSV Workflow

This doc standardizes how we extract the Consolidated Schedule of Investments from 10‑Q/10‑K HTML and convert the tables into clean CSVs.

---

#### 1) Discover the latest filing (per ticker)
- Use `SECAPIClient.get_filing_index_url(ticker, "10-Q")` (fallback to 10-K if needed).
- Example: resolve to `.../{accession_no}-index.html`.

Outputs:
- Filing index URL

#### 2) Identify the main HTML document
- Call `SECAPIClient.get_documents_from_index(index_url)` and choose the primary `.htm` document.
- Avoid XBRL viewer links (client normalizes).

Outputs:
- Main HTML URL (e.g., `.../ofs-20250930.htm`)

#### 3) Download and parse HTML
- `requests.get(main_html, headers)` → `BeautifulSoup(html, "html.parser")`.
- Keep raw HTML for debugging if needed.

Outputs:
- `soup` parsed HTML

#### 4) Locate Consolidated Schedule of Investments section
- We use a tolerant heading match (variant-safe): find tables with nearby prior text containing at least:
  - "Consolidated Schedule of Investments"
  - Filing date line (e.g., "September 30, 2025")
  - Optionally include: company name text ("… and Subsidiaries"), "(unaudited)", "(Dollar amounts in thousands)".
- Implementation: scan prior text nodes (8–12) before each `<table>`; select tables whose context blob satisfies the match.

Outputs:
- List of matched `<table>` elements (usually 3–10 for large BDCs)

#### 5) Save simplified HTML tables (optional but recommended)
- Strip styles and classes; keep only `<table>/<tr>/<th>/<td>`.
- Replace inline XBRL tags (e.g., `ix:nonFraction`) with their text.
- Save as `output/{TICKER}_tables/{TICKER}_table_{i}.html` for QA.

Outputs:
- Clean, reviewable HTML tables

#### 6) Normalize to CSV rows (schema)
Target columns:
- company_name, investment_type, industry, interest_rate, spread, acquisition_date, maturity_date, principal_amount, amortized_cost, fair_value, percent_of_net_assets

Row parsing rules:
- Row types:
  - Company rows: first non-empty cell is company; another cell nearby is industry. No rate/spread/date signals.
  - Detail rows: contain interest rate (e.g., `10.40%` or `5.94% cash / 6.50% PIK`), spread token (`SOFR+`, `PRIME+`, etc.), and often dates. Carry-forward `company_name` and `industry` from the last company row.
- Symbols merging:
  - Merge standalone `$` and `%` cells with adjacent numerics (e.g., `$` + `8,931` → `$8,931`).
- Field extraction:
  - interest_rate: first percentage-like or "cash / PIK" composite.
  - spread: token + the next numeric percentage cell.
  - dates: regex `\bMM/DD/YYYY\b` → first is acquisition, second is maturity.
  - monetary fields (principal, cost, fair_value): first three currency-like tokens (allow `$` prefix or comma numerics). Convert to float; `—` → null.
  - percent_of_net_assets: last percentage-like token not used as interest/spread.
- Skip section headers (e.g., "Debt and Equity Investments", "Non-control/Non-affiliate Investments").

Outputs:
- `{TICKER}_{Company}_Schedule_{PERIOD}.csv` (or consolidated single CSV per ticker)

#### 7) File outputs
- CSV: `output/{TICKER}_Schedule_{PERIOD}.csv`
- Simplified tables (QA): `output/{TICKER}_tables/{TICKER}_table_{i}.html`
- Logs: `output/logs_{TICKER}.log`

#### 8) Quality checks
- Spot-check 5–10 random investments vs filing.
- Totals sanity: sum of `fair_value` across rows vs reported totals (when available).
- Fields completeness rates (interest, dates) ≥ target.

#### 9) Edge cases & heuristics
- Multi-line interest formats (cash / PIK): retain the composite string in `interest_rate`.
- Negative or em-dash values (`—`): convert to null; keep negatives `(<value>)` as negative floats when appropriate.
- Section subtotals/rollups: ignore rows that lack company and monetary fields.
- Multi-table schedules: append in order; carry `company_name/industry` only within the table where they appear.

#### 10) Batch across all tickers
- Loop `BDC_UNIVERSE`:
  1) Resolve index URL
  2) Find main HTML
  3) Match schedule tables
  4) Save simplified tables
  5) Parse to CSV (shared parser with company/industry carry-forward)
  6) Save outputs under `output/`
- Add `Start-Sleep 2` seconds between requests; respect SEC rate limits and set a proper User-Agent.

#### 11) Retries & fallbacks
- If no tables matched: widen heading search window; allow minor punctuation variants; consider 10-K if 10-Q absent.
- If columns differ materially: override mapping per BDC (e.g., custom industry cell index).

#### 12) Implementation pointers (repo)
- Reference implementation (OFS): `ofs_html_tables_to_csv.py`
- Delegated entry for OFS: `ofs_parser.py`
- SEC utility: `sec_api_client.py`

---

#### Done checklist (for each ticker)
- [ ] Main HTML identified and archived (optional)
- [ ] Tables saved in `output/{TICKER}_tables/`
- [ ] CSV created with target schema
- [ ] QA spot-check completed
- [ ] Logged counts and basic stats
