# BDC Extractor Standalone

A clean, production-ready backend for extracting and standardizing BDC (Business Development Company) investment data from SEC filings.

## Overview

This directory contains:
- **Parsers**: Individual parsers for each BDC ticker that extract investment data from SEC filings
- **Standardization**: Functions to standardize investment types, industries, and reference rates
- **SEC API Client**: Client for fetching SEC filings and data
- **Daily Update Script**: Automated script to check for new filings and update data

## Directory Structure

```
bdc_extractor_standalone/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── daily_update.py              # Daily update script (checks for new filings)
├── run_all_parsers.py          # Run all parsers (full refresh)
├── standardization.py           # Standardization functions (used by frontend)
├── sec_api_client.py           # SEC API client
├── models.py                    # Data models (if needed)
│
├── *_parser.py                  # Individual BDC parsers
├── *_custom_parser.py           # Custom HTML table parsers
│
├── output/                      # Generated CSV files (investment data)
│   └── *_investments.csv       # One CSV per BDC ticker
│
└── frontend/                    # Frontend application
    ├── src/
    ├── public/
    └── ...
```

## Core Files

### Essential Files (DO NOT DELETE)

- **`standardization.py`**: Standardization functions for investment types, industries, and rates. Used by frontend.
- **`sec_api_client.py`**: SEC API client for fetching filings. Used by all parsers.
- **`run_all_parsers.py`**: Main script to run all parsers and generate output files.
- **`daily_update.py`**: Daily update script to check for new filings and update only changed data.
- **`*_parser.py`** and **`*_custom_parser.py`**: Individual BDC parsers (one per ticker).

### Output Files

- **`output/*_investments.csv`**: Generated investment data files (one per BDC ticker).

## Usage

### Daily Updates (Recommended)

Check for new filings and update only changed data:

```bash
python bdc_extractor_standalone/daily_update.py
```

Force update all parsers:

```bash
python bdc_extractor_standalone/daily_update.py --force-all
```

Check for filings from the last 14 days:

```bash
python bdc_extractor_standalone/daily_update.py --days-back 14
```

### Full Refresh

Run all parsers to regenerate all output files:

```bash
python bdc_extractor_standalone/run_all_parsers.py
```

### Individual Parser

Run a specific parser:

```bash
python bdc_extractor_standalone/arcc_custom_parser.py
```

## Standardization

The `standardization.py` module provides functions to standardize:

- **Investment Types**: Maps various investment type descriptions to standard values
- **Industries**: Maps industry descriptions to standard industry categories
- **Reference Rates**: Maps rate descriptions (SOFR, LIBOR, PRIME, etc.) to standard values

These functions are used by:
1. The parsers to standardize extracted data
2. The frontend to display consistent data

## Parser Types

### XBRL Parsers (`*_parser.py`)

Parsers that extract data from XBRL (eXtensible Business Reporting Language) filings. These are typically more reliable and structured.

### Custom HTML Parsers (`*_custom_parser.py`)

Parsers that extract data from HTML tables in SEC filings. These are used when XBRL data is not available or insufficient.

## Output Format

Each parser generates a CSV file in the `output/` directory with the following columns:

- `company_name`: Name of the portfolio company
- `industry`: Industry category
- `business_description`: Business description
- `investment_type`: Type of investment (e.g., "First Lien Debt", "Common Equity")
- `acquisition_date`: Date investment was acquired
- `maturity_date`: Maturity date (for debt investments)
- `principal_amount`: Principal amount
- `cost`: Cost basis
- `fair_value`: Fair value
- `interest_rate`: Interest rate
- `reference_rate`: Reference rate (SOFR, LIBOR, PRIME, etc.)
- `spread`: Spread over reference rate
- `floor_rate`: Floor rate
- `pik_rate`: PIK (Payment-In-Kind) rate
- `shares_units`: Number of shares/units (for equity)
- `percent_net_assets`: Percentage of net assets
- `currency`: Currency (typically USD)
- `commitment_limit`: Commitment limit (for revolving facilities)
- `undrawn_commitment`: Undrawn commitment amount

## Frontend Integration

The frontend application in `frontend/` reads the CSV files from `output/` and uses the standardization functions from `standardization.py` to display consistent, standardized data.

## Automation

### Daily Updates (Recommended)

The `daily_update.py` script intelligently checks for new filings and only updates tickers that have new data:

```bash
python bdc_extractor_standalone/daily_update.py
```

**What it does:**
1. Checks last modification time of each CSV file
2. For files older than 7 days (configurable), checks SEC for new filings
3. Runs parsers only for tickers with new filings
4. Updates the corresponding CSV files
5. Logs results to `daily_update.log`

**Options:**
- `--force-all`: Force update all parsers regardless of last update time
- `--days-back N`: Check for filings from the last N days (default: 7)

**Example:**
```bash
# Check for new filings in last 14 days
python bdc_extractor_standalone/daily_update.py --days-back 14

# Force update everything
python bdc_extractor_standalone/daily_update.py --force-all
```

### Scheduled Daily Updates

**Windows Task Scheduler:**
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger to "Daily" at desired time
4. Action: Start a program
5. Program: `python`
6. Arguments: `bdc_extractor_standalone/daily_update.py`
7. Start in: `C:\Users\jsper\dev\Github\new_finance`

**Linux/Mac Cron:**
```bash
# Edit crontab
crontab -e

# Add line (runs daily at 2 AM)
0 2 * * * cd /path/to/new_finance && python bdc_extractor_standalone/daily_update.py >> bdc_extractor_standalone/daily_update.log 2>&1
```

### Full Refresh (Weekly/Monthly)

Periodically run a full refresh to ensure all data is up to date:

```bash
python bdc_extractor_standalone/run_all_parsers.py
```

This regenerates all CSV files from scratch. Useful for:
- Weekly/monthly maintenance
- After parser updates
- When data inconsistencies are suspected

## Dependencies

Install dependencies:

```bash
pip install -r bdc_extractor_standalone/requirements.txt
```

## Logging

- **Daily updates**: Logged to `daily_update.log`
- **Parser runs**: Logged to console and can be redirected to files

## Parser Organization

Some BDCs have both `*_parser.py` (XBRL-based) and `*_custom_parser.py` (HTML table-based) files. The `run_all_parsers.py` script automatically prefers the regular parser over the custom parser if both exist. Both types of parsers produce the same output format.

## Notes

- The `output/` directory contains generated files and can be regenerated at any time
- The `frontend/` directory is a separate application that reads from `output/`
- All parsers use the `SECAPIClient` to fetch filings, ensuring consistent data access
- Standardization ensures data consistency across all BDCs
- Old testing/analysis scripts have been removed for a clean production codebase
- The `raw_tables/` and `temp_filings/` directories contain temporary files and can be cleaned periodically

