# Quick Start Guide

## 🚀 Getting Started

### 1. Initial Backfill (One-Time Setup)

Backfill historical data for all BDCs:

```bash
cd bdc_extractor_standalone

# Backfill 5 years of data for all BDCs
python scripts/backfill_all_data.py --years-back 5

# Or start with just a few tickers to test
python scripts/backfill_all_data.py --ticker ARCC --ticker HTGC --years-back 5
```

This will:
- Extract historical investments from SEC 10-Q filings (HTML parsing)
- Extract financials data (edgartools)
- Process multiple BDCs in parallel (default: 5 workers)
- Generate JSON files in `frontend/public/data/`
- Create ZIP files for downloads
- **Time**: ~30-60 minutes for all BDCs with 5 workers, ~15-30 minutes with 10 workers (5 years of data)

**Data Extraction Methods:**
- **Investments**: HTML parsing of Schedule of Investments tables
- **Financials**: edgartools XBRL extraction

### 2. Enable Automated Updates

#### GitHub Actions (Recommended)

1. **Push to GitHub**: The workflows are already configured
2. **Daily Updates**: Will run automatically at 6 AM EST
3. **Manual Backfill**: Go to GitHub Actions → "Backfill Historical Data" → "Run workflow"

#### Manual Daily Check (Alternative)

```bash
# Check for new filings
python scripts/check_new_filings.py --days-back 7

# Update data for new filings
python scripts/update_new_data.py --days-back 7
```

### 3. Deploy Frontend

#### Vercel (Recommended)

1. Connect your GitHub repo to Vercel
2. Set build directory to `bdc_extractor_standalone/frontend`
3. Vercel will auto-deploy when data changes (via GitHub Actions commits)

#### Manual Build

```bash
cd frontend
npm install
npm run build
# Deploy dist/ folder to your hosting
```

## 📁 Data Structure

After running scripts:

```
frontend/public/data/
├── index.json                    # All BDCs list
└── {TICKER}/
    ├── periods.json              # Available periods
    ├── latest.json               # Latest period
    ├── profile.json              # Company profile
    ├── investments_{YYYY-MM-DD}.json  # Investment holdings
    ├── financials_{YYYY-MM-DD}.json   # Financial statements
    └── {TICKER}_all_periods.zip       # ZIP archive
```

## 🔄 Workflow

### Daily (Automated)
1. GitHub Actions checks for new SEC filings (edgartools)
2. Extracts data for tickers with new filings:
   - Investments: HTML parsing
   - Financials: edgartools
3. Commits changes to repo
4. Vercel rebuilds frontend automatically

### Weekly/Monthly (Manual)
- Run backfill for specific tickers if needed
- Check for any missed filings
- Update parsers if filing formats change

## 🛠️ Troubleshooting

### Script fails with "No parser found"
- Check `bdc_config.py` for ticker mappings
- Some BDCs may need parser development
- HTML parsers should have `extract_from_html_url()` method

### Rate limit errors
- SEC limits requests per IP
- Wait 5-10 minutes and retry
- GitHub Actions runs once daily to avoid limits

### Missing data for a ticker
- Check if parser exists in `*_parser.py` files
- Verify ticker is in `BDC_UNIVERSE` in `bdc_config.py`
- Run with `--ticker` flag to debug specific ticker
- Check parser logs for extraction errors

### Financials extraction fails
- Ensure `edgartools` is installed: `pip install edgartools`
- Check if filing has XBRL data
- Verify edgartools identity is set

## 📊 Monitoring

### Check GitHub Actions
- Go to repository → Actions tab
- View "Daily Data Update" workflow runs
- Check logs for errors

### Check Data Files
```bash
# List all tickers with data
ls frontend/public/data/

# Check latest period for a ticker
cat frontend/public/data/ARCC/latest.json

# Check available periods
cat frontend/public/data/ARCC/periods.json
```

## 🎯 Next Steps

1. ✅ Run initial backfill
2. ✅ Enable GitHub Actions (already configured)
3. ✅ Connect to Vercel for frontend hosting
4. ✅ Monitor daily updates
5. ⏳ Add more BDCs as needed
6. ⏳ Improve parsers for better extraction

## 📝 Scripts Reference

- `backfill_all_data.py` - Initial historical data extraction
- `check_new_filings.py` - Check for new SEC filings (edgartools)
- `update_new_data.py` - Update data for new filings
- `generate_static_data.py` - Generate frontend JSON files

See `scripts/AUTOMATION_README.md` for detailed documentation.

## 🔧 Dependencies

### Python
- `edgartools` - SEC EDGAR API client
- `beautifulsoup4` - HTML parsing
- `requests` - HTTP client

### Installation
```bash
pip install -r requirements.txt
```
