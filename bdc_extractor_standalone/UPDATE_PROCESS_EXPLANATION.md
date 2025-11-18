# Daily Update Process Explanation

## Current Approach

The daily update script (`daily_update.py`) works as follows:

### 1. **Finding Parsers**
- Scans `bdc_extractor_standalone/` for `*_parser.py` and `*_custom_parser.py` files
- Extracts ticker symbols from filenames (e.g., `arcc_custom_parser.py` → `ARCC`)
- Skips utility parsers like `flexible_table_parser.py`

### 2. **Checking for Updates**
For each ticker, the script:
- Checks if a CSV file exists in `output/` directory
- If CSV exists, checks its last modification date
- If CSV is older than `days_back` (default: 7 days), checks SEC for new filings
- Compares the latest filing date with the CSV's last update date

### 3. **Filing Detection**
- Uses `SECAPIClient.get_filing_index_url()` to get the latest 10-Q or 10-K filing
- **ISSUE**: Currently doesn't properly compare filing dates - just checks if a filing exists
- **FIX NEEDED**: Compare actual filing dates to determine if there's a newer filing

### 4. **Running Parsers**
- Only runs parsers for tickers with:
  - No existing CSV file, OR
  - CSV file older than cutoff date AND new filing found
- Each parser extracts investments and saves to CSV

### 5. **Logging**
- Logs all operations to `daily_update.log`
- Provides summary of successful/failed updates

## Issues to Fix

1. **Date Comparison**: Need to properly extract and compare filing dates
2. **Parser Errors**: Several parsers have syntax/logic errors:
   - BCSF: Indentation error
   - BXSL: Missing module `flexible_table_parser`
   - CSWC: Variable scope issue
   - GBDC, OFS, PSEC: Missing CSV fields (currency, commitment_limit, etc.)
   - SSSS: Undefined variable

## Proposed Fix

1. Add `get_latest_filing_date()` method to `SECAPIClient` to extract filing dates
2. Update `check_for_new_filing()` to compare dates properly
3. Fix all parser errors
4. Ensure all parsers include required CSV fields

