# Data Automation Scripts

This directory contains scripts for automating data extraction, backfilling historical data, and monitoring for new SEC filings.

## Overview

The system uses a dual-approach for data extraction:
- **HTML Parsing** for investment holdings (Schedule of Investments)
- **edgartools** for financial statements (Income Statement, Balance Sheet, Cash Flow)

## Scripts Overview

### 1. `backfill_all_data.py`
**Purpose**: Backfill historical investment and financial data for all BDCs.

**Usage**:
```bash
# Backfill 5 years of data for all BDCs (5 parallel workers)
python scripts/backfill_all_data.py --years-back 5

# Backfill with more workers for faster processing (watch SEC rate limits!)
python scripts/backfill_all_data.py --years-back 5 --max-workers 10

# Backfill specific tickers
python scripts/backfill_all_data.py --ticker ARCC --ticker HTGC --years-back 5

# Skip tickers that already have data
python scripts/backfill_all_data.py --years-back 5 --skip-existing

# Limit to first 5 tickers (for testing)
python scripts/backfill_all_data.py --max-tickers 5
```

**What it does**:
1. **Investments**: Extracts from HTML tables in 10-Q filings
   - Uses HTML parsers (`extract_from_html_url()` method)
   - Parses Schedule of Investments tables
   - Normalizes to standardized schema
2. **Financials**: Extracts using edgartools
   - Uses `edgartools.Company.get_filings()` to fetch filings
   - Extracts XBRL data for financial statements
   - Normalizes to standardized concepts
3. **Parallel Processing**: Processes multiple BDCs simultaneously
   - Default: 5 parallel workers (respects SEC rate limits)
   - Can be increased with `--max-workers` flag
   - Significantly faster than sequential processing
4. Generates JSON files in `frontend/public/data/`
5. Creates ZIP files for download
6. Updates `index.json` with all BDCs

**Output**:
- `frontend/public/data/{TICKER}/investments_{YYYY-MM-DD}.json`
- `frontend/public/data/{TICKER}/financials_{YYYY-MM-DD}.json`
- `frontend/public/data/{TICKER}/periods.json`
- `frontend/public/data/{TICKER}/{TICKER}_all_periods.zip`

### 2. `check_new_filings.py`
**Purpose**: Check SEC EDGAR for new 10-Q filings using edgartools.

**Usage**:
```bash
# Check all BDCs for new filings in last 30 days
python scripts/check_new_filings.py

# Check specific tickers
python scripts/check_new_filings.py --ticker ARCC --ticker HTGC

# Check last 7 days only
python scripts/check_new_filings.py --days-back 7

# Only show tickers with new filings
python scripts/check_new_filings.py --only-new

# Save results to JSON
python scripts/check_new_filings.py --output results.json
```

**What it does**:
- Uses `edgartools.Company.get_filings()` to fetch latest filings
- Compares filing dates with existing data in `periods.json`
- Identifies tickers with new filings
- Outputs report of new filings

**Output**:
- Lists which tickers have new filings
- Shows latest filing date vs. existing data date
- Can output JSON for programmatic use

### 3. `update_new_data.py`
**Purpose**: Check for new filings and automatically extract data for updated tickers.

**Usage**:
```bash
# Check and update all BDCs with new filings
python scripts/update_new_data.py

# Update specific tickers
python scripts/update_new_data.py --ticker ARCC

# Force update even if no new filings (re-extract)
python scripts/update_new_data.py --force

# Extract more years of history when updating
python scripts/update_new_data.py --years-back 3
```

**What it does**:
1. Checks each ticker for new filings (uses `check_new_filings.py`)
2. Extracts data only for tickers with new filings:
   - Investments: HTML parsing
   - Financials: edgartools
3. Updates JSON files in `frontend/public/data/`

## GitHub Actions Workflows

### Daily Data Update (`daily_data_update.yml`)
**Runs**: Daily at 6 AM EST (11 AM UTC)

**What it does**:
1. Checks for new SEC filings in the last 7 days (edgartools)
2. Extracts data for tickers with new filings:
   - Investments: HTML parsing
   - Financials: edgartools
3. Commits and pushes changes to repository
4. Vercel automatically rebuilds with new data

**Manual trigger**: Available in GitHub Actions UI

### Backfill Historical Data (`backfill_data.yml`)
**Runs**: Manual trigger only

**What it does**:
1. Backfills historical data for all BDCs (or specified tickers)
2. Extracts both investments and financials
3. Skips tickers that already have data
4. Commits and pushes changes

**Usage**:
- Go to GitHub Actions → "Backfill Historical Data" → "Run workflow"
- Optionally specify years back and specific tickers

## Local Development

### Initial Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Backfill data for all BDCs (this will take a while)
python scripts/backfill_all_data.py --years-back 5

# Or start with just a few tickers
python scripts/backfill_all_data.py --ticker ARCC --ticker HTGC --years-back 5
```

### Daily Updates (Local)
```bash
# Check for new filings
python scripts/check_new_filings.py --days-back 7

# Update data for new filings
python scripts/update_new_data.py --days-back 7
```

## Data Structure

After running scripts, data is organized as:

```
frontend/public/data/
├── index.json                    # List of all BDCs
└── {TICKER}/
    ├── periods.json              # List of available periods
    ├── latest.json               # Latest period info
    ├── profile.json              # Yahoo Finance profile data
    ├── investments_{YYYY-MM-DD}.json  # Investment data per period
    ├── financials_{YYYY-MM-DD}.json   # Financials data per period
    ├── {TICKER}_all_periods.zip       # ZIP of all JSON files
    └── {TICKER}_all_periods_csv.zip   # ZIP of all CSV files
```

## Extraction Methods

### Investments: HTML Parsing
- **Method**: Parse HTML tables from 10-Q filings
- **Parser**: BDC-specific parsers with `extract_from_html_url()` method
- **Advantages**:
  - Faster than XBRL parsing
  - Direct access to table structures
  - Better handling of multi-table formats

### Financials: edgartools
- **Method**: Extract XBRL data using edgartools
- **Library**: `edgartools` (Python package)
- **Advantages**:
  - Reliable XBRL extraction
  - Standardized financial concepts
  - Better for time-series data

## Environment Variables

Optional environment variables:
- `USER_AGENT`: Custom user agent for SEC API requests (required by SEC)
- `EDGARTOOLS_IDENTITY`: Email for edgartools identity (default: contact@example.com)

## Rate Limiting

SEC EDGAR has rate limits:
- Scripts include delays between requests
- If you hit rate limits, wait a few minutes and retry
- GitHub Actions runs once daily to avoid rate limits

## Troubleshooting

### "No parser found for ticker"
- Some BDCs may not have parsers yet
- Check `bdc_config.py` for parser mappings
- Add parser to `TICKER_TO_PARSER` in `batch_historical_extractor.py`

### "Failed to extract investments"
- Parser may need updates for new filing format
- Check parser logs for specific errors
- Some filings may have different table structures
- Try using `FlexibleTableParser` for complex formats

### "Failed to extract financials"
- Check if edgartools is installed: `pip install edgartools`
- Verify filing has XBRL data
- Check edgartools logs for errors

### "Rate limit exceeded"
- SEC limits requests per IP
- Wait 5-10 minutes and retry
- Consider running scripts less frequently

## Next Steps

1. **Initial Backfill**: Run `backfill_all_data.py` to populate historical data
2. **Enable GitHub Actions**: Workflows will run automatically
3. **Monitor**: Check GitHub Actions logs for daily updates
4. **Vercel**: Frontend will auto-rebuild when data changes
