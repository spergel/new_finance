# Data Generation Scripts

## generate_all_data.py

Generates all JSON data files for the frontend from existing CSV files.

### Usage

```bash
# Generate data for all BDCs
python scripts/generate_all_data.py

# Generate data for specific ticker(s)
python scripts/generate_all_data.py --ticker HTGC --ticker OCSL

# Also extract financials (requires SEC API access)
python scripts/generate_all_data.py --financials
```

### What it does

1. **Scans `output/` directory** for CSV files matching pattern `{TICKER}_*_investments.csv`
2. **Generates `investments_{period}.json`** files in `frontend/public/data/{TICKER}/`
3. **Generates `periods.json`** listing all available periods
4. **Generates `latest.json`** with latest period info
5. **Updates `index.json`** with all BDCs and their periods

### Output Structure

```
frontend/public/data/
├── index.json
└── {TICKER}/
    ├── periods.json
    ├── latest.json
    ├── investments_{YYYY-MM-DD}.json
    └── financials_{YYYY-MM-DD}.json (if --financials flag used)
```

### Notes

- Periods are extracted from CSV filenames (date patterns) or file modification dates
- The script will skip tickers that have no CSV files
- Financials extraction requires SEC API access and is slower

## generate_static_data.py

Full historical extraction from SEC filings (uses HistoricalInvestmentExtractor).

### Usage

```bash
# Extract last 5 years for all BDCs
python scripts/generate_static_data.py

# Extract for specific tickers
python scripts/generate_static_data.py --ticker HTGC --ticker OCSL

# Extract more years back
python scripts/generate_static_data.py --years-back 10
```

This script:
- Downloads historical 10-Q filings from SEC
- Extracts investments using ticker-specific parsers
- Generates all JSON files including financials
- More comprehensive but slower than `generate_all_data.py`

## populate_financials.py

Extracts financials for existing investment periods.

### Usage

```bash
# Extract financials for all tickers
python scripts/populate_financials.py --all

# Extract financials for specific ticker
python scripts/populate_financials.py --ticker HTGC
```









