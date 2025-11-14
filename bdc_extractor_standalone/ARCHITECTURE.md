# BDC Extractor Architecture

## Overview

This system extracts and maintains historical investment and financial data for Business Development Companies (BDCs) from SEC EDGAR filings. The architecture uses a dual-approach:

1. **HTML Parsing** for investment holdings (Schedule of Investments)
2. **edgartools** for financial statements (Income Statement, Balance Sheet, Cash Flow)

## Data Extraction Strategy

### Investments: HTML Parsing

**Why HTML?**
- Schedule of Investments tables are consistently formatted in HTML
- Faster and more reliable than parsing XBRL for investment data
- Direct access to table structures
- Better handling of multi-table formats

**Process:**
1. Fetch 10-Q filing index from SEC EDGAR
2. Identify main HTML document (not XBRL viewer)
3. Parse HTML tables using BeautifulSoup
4. Extract Schedule of Investments tables
5. Normalize to standardized schema (company_name, investment_type, industry, etc.)
6. Store as JSON per period

**Parser Types:**
- **HTML-based parsers**: Most BDCs use `extract_from_html_url()` method
- **Flexible Table Parser**: For BDCs with complex multi-table formats (e.g., ARCC)
- **Custom parsers**: BDC-specific parsers in `*_parser.py` files

### Financial Statements: edgartools

**Why edgartools?**
- Reliable XBRL extraction for financial statements
- Handles complex XBRL structures automatically
- Provides standardized financial concepts
- Better for time-series financial data

**Process:**
1. Fetch 10-Q filing using edgartools `Company.get_filings()`
2. Load XBRL data using `Filing.get_xbrl()`
3. Extract financial statements:
   - Income Statement
   - Balance Sheet
   - Cash Flow Statement
4. Normalize to standardized concepts
5. Store as JSON per period

**Data Sources:**
- Primary: XBRL data from filing
- Fallback: Company Facts API for historical data

## Historical Data System

### Data Storage

**File Structure:**
```
frontend/public/data/
├── index.json                    # All BDCs list
└── {TICKER}/
    ├── periods.json              # Available periods
    ├── latest.json               # Latest period info
    ├── profile.json              # Company profile (Yahoo Finance)
    ├── investments_{YYYY-MM-DD}.json  # Investment holdings per period
    ├── financials_{YYYY-MM-DD}.json  # Financial statements per period
    └── {TICKER}_all_periods.zip       # ZIP of all JSON files
```

**Data Retention:**
- Default: 5 years of historical data
- Configurable via `--years-back` parameter
- Each period stored as separate JSON file
- ZIP archives for bulk download

### Historical Index

```json
{
  "historical_index": {
    "ARCC": {
      "periods": [
        {
          "period": "2024-09-30",
          "filing_date": "2024-11-08",
          "accession": "0001287750-24-123456",
          "investments_file": "investments_2024-09-30.json",
          "financials_file": "financials_2024-09-30.json"
        }
      ]
    }
  }
}
```

## Automated Update System

### Architecture

```
┌─────────────────┐
│  SEC EDGAR API  │
│  (edgartools)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Filing Monitor │  ← Checks for new 10-Q filings
│  (Daily Cron)   │     - Uses edgartools Company.get_filings()
└────────┬────────┘     - Compares with existing periods.json
         │
         ▼
┌─────────────────┐
│  Data Extractor │  ← Extracts investments + financials
│  (HTML + XBRL)  │     - HTML parsing for investments
└────────┬────────┘     - edgartools for financials
         │
         ▼
┌─────────────────┐
│  Data Processor │  ← Validates and normalizes
│  (Validator)    │     - Standardizes investment types
└────────┬────────┘     - Validates financial totals
         │
         ▼
┌─────────────────┐
│  File System    │  ← Saves JSON files
│  (GitHub Repo)  │     - Updates index.json
└─────────────────┘     - Commits to repository
```

### Components

#### 1. Filing Monitor (`check_new_filings.py`)
- Uses `edgartools` to fetch latest filings
- Compares filing dates with existing data
- Identifies tickers with new filings
- Outputs JSON report of new filings

#### 2. Data Extractor (`backfill_all_data.py`)
- Orchestrates extraction for multiple tickers
- Calls HTML parsers for investments
- Calls edgartools for financials
- Generates static JSON files

#### 3. Update Script (`update_new_data.py`)
- Checks for new filings
- Extracts data only for updated tickers
- Updates JSON files in place

### GitHub Actions Workflows

#### Daily Data Update (`daily_data_update.yml`)
- **Schedule**: Daily at 6 AM EST (11 AM UTC)
- **Steps**:
  1. Check for new filings (last 7 days)
  2. Extract data for tickers with new filings
  3. Commit and push changes
  4. Vercel auto-rebuilds frontend

#### Backfill Historical Data (`backfill_data.yml`)
- **Trigger**: Manual only
- **Steps**:
  1. Backfill historical data (configurable years)
  2. Optionally filter by specific tickers
  3. Commit and push changes

## Comparison Functionality

### Current Features
- Side-by-side comparison of multiple BDCs
- Holdings comparison
- Financials comparison
- Analytics comparison

### Planned Improvements
- Side-by-side tables (all BDCs in one view)
- Portfolio overlap metrics
- Industry concentration comparison
- Visual charts (Windows 95 style)

## News Feed Integration

### Current State
- NewsFeed component created (placeholder)
- Needs API integration

### Implementation Options
1. **NewsAPI** - Free tier available
2. **RSS Feeds** - Aggregate financial news
3. **Custom Backend** - Scrape financial sites

### Recommended: NewsAPI + RSS Hybrid
- Primary: NewsAPI for general financial news
- Fallback: RSS feeds for additional sources
- Cache: 1 hour to reduce API calls

## Technical Stack

### Backend
- **Language**: Python 3.8+
- **Libraries**:
  - `edgartools` - SEC EDGAR API client
  - `beautifulsoup4` - HTML parsing
  - `requests` - HTTP client
  - `pandas` - Data processing (optional)

### Frontend
- **Framework**: React + TypeScript
- **Styling**: Tailwind CSS (Windows 95 theme)
- **State**: Zustand
- **Data Fetching**: React Query
- **Build**: Vite

### Deployment
- **Frontend**: Vercel (auto-deploy on GitHub push)
- **Data**: GitHub repository (static JSON files)
- **Automation**: GitHub Actions

## Data Flow

### Initial Backfill
```
1. Run backfill_all_data.py --years-back 5
2. For each ticker:
   a. Fetch historical 10-Q filings (edgartools)
   b. Extract investments (HTML parsing)
   c. Extract financials (edgartools)
   d. Generate JSON files
3. Commit to GitHub
4. Vercel rebuilds frontend
```

### Daily Updates
```
1. GitHub Actions runs daily
2. Check for new filings (edgartools)
3. Extract data for updated tickers
4. Update JSON files
5. Commit to GitHub
6. Vercel rebuilds frontend
```

## Performance Considerations

### Rate Limiting
- SEC EDGAR: 10 requests/second per IP
- Scripts include delays between requests
- GitHub Actions runs once daily to avoid limits

### Optimization
- HTML parsing: ~15-20 seconds per filing
- XBRL extraction: ~5-10 seconds per filing
- Total per ticker: ~20-30 seconds per period

### Caching
- Frontend: React Query caches for 24 hours
- Static JSON: Served via CDN (Vercel)

## Future Enhancements

### Phase 1 (Immediate)
- ✅ HTML parsing for investments
- ✅ edgartools for financials
- ⏳ News feed API integration
- ⏳ Comparison improvements

### Phase 2 (Short-term)
- Historical trends visualization
- Advanced comparison metrics
- Export functionality

### Phase 3 (Long-term)
- SQLite database migration
- Real-time updates
- User preferences/settings
