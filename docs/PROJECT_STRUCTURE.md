# Project Structure

## Overview
This project extracts comprehensive preferred stock data from SEC filings using a streamlined regex + LLM approach:
- **Regex series identification** from 10-Q filings
- **Smart filing matching** to find relevant 424B prospectuses
- **LLM feature extraction** for detailed terms and conditions
- **Clean output** with proper deduplication

## Directory Structure

```
new_finance/
├── core/                           # Core extraction modules
│   ├── securities_features_extractor.py     # Main LLM extraction engine
│   ├── filing_matcher.py                    # 424B filing matching
│   ├── xbrl_preferred_shares_extractor.py   # Simple series identification
│   ├── sec_api_client.py                    # SEC EDGAR API client
│   └── models.py                            # Pydantic data models
│
├── docs/                           # Documentation
│   ├── README.md                   # Main documentation
│   ├── ARCHITECTURE.md             # System design
│   ├── FEATURES.md                 # Feature list
│   ├── USAGE.md                    # Usage guide
│   ├── PROJECT_STRUCTURE.md        # This file
│   └── TODO.md                     # Development roadmap
│
├── output/                         # All extraction outputs
│   ├── llm/                        # ✨ Main output (USE THIS!)
│   ├── enhanced/                   # Legacy LLM outputs
│   ├── fused/                      # Legacy fused outputs
│   └── xbrl/                       # XBRL data (if available)
│
├── data/                           # Sample filing data (gitignored)
├── scripts/                        # Utility scripts (gitignored)
├── .gitignore                      # Git ignore rules
├── requirements.txt                # Python dependencies
└── README.md                       # Project overview
```

## Key Files

### Core Modules

- **`core/securities_features_extractor.py`**
  - Main extraction engine with regex + LLM
  - Handles the complete pipeline from 10-Q to final output
  - Features: dividend terms, redemption, conversion, governance

- **`core/filing_matcher.py`**
  - Matches each preferred series to its specific 424B filing
  - Finds the best historical prospectus for each series
  - Eliminates cross-contamination between different series

- **`core/xbrl_preferred_shares_extractor.py`**
  - Simple regex extraction from 10-Q filings
  - Identifies preferred stock series names
  - Basic financial data extraction

- **`core/sec_api_client.py`**
  - SEC EDGAR API client
  - Downloads filings and handles rate limiting

- **`core/models.py`**
  - Pydantic data models for type safety
  - Defines the structure of extracted data

### Output Files

**🎯 Primary Output: `output/llm/`**
- Complete preferred stock data in JSON format
- Most accurate and up-to-date extraction results
- Use this for investment analysis

**Other Outputs:**
- `output/enhanced/` - Legacy LLM outputs
- `output/fused/` - Legacy fused outputs
- `output/xbrl/` - Raw XBRL data (if available)

## Usage

### Extract Complete Data for a Ticker

```bash
# Simple command-line extraction
python scripts/extract_preferred_stocks.py JXN

# Output: output/llm/JXN_securities_features.json
```

```python
from core.securities_features_extractor import extract_preferred_stocks_simple

# Programmatic extraction
result = extract_preferred_stocks_simple('JXN')
print(f"Found {len(result.securities)} preferred securities")
```

### Test Multiple Companies

```bash
python scripts/test_fusion_diverse.py
```

### Extract XBRL Only

```python
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares

result = extract_xbrl_preferred_shares('JXN')
# Returns: dividend rate, shares, par value, etc.
```

### Extract LLM Only

```python
from core.securities_features_extractor import SecuritiesFeaturesExtractor

extractor = SecuritiesFeaturesExtractor()
result = extractor.extract_securities_features('JXN')
# Returns: conversion terms, redemption, governance, etc.
```

## Data Flow

```
1. XBRL Extraction (10-Q)
   ↓
   [Current Financial Data]
   - Dividend rate
   - Outstanding shares
   - Par value
   - Cumulative status
   
2. Filing Matcher
   ↓
   [Identifies relevant 424B filings]
   - Matches series names
   - Confidence scoring
   
3. LLM Extraction (424B)
   ↓
   [Detailed Terms]
   - Conversion terms
   - Redemption provisions
   - Governance features
   - Special provisions
   
4. Data Fusion
   ↓
   [Complete Dataset]
   output/fused/{TICKER}_fused_preferred_shares.json
```

## Example Output

```json
{
  "ticker": "JXN",
  "series_name": "A",
  "description": "Fixed-Rate Reset Noncumulative Perpetual Preferred Stock, Series A",
  "dividend_rate": 8.0,
  "outstanding_shares": 22000,
  "authorized_shares": 24000,
  "par_value": 25000.0,
  "is_cumulative": false,
  "redemption_terms": {
    "is_callable": true,
    "call_price": 25000.0,
    "earliest_call_date": "2028-03-30",
    "notice_period_days": 30
  },
  "has_llm_data": true,
  "xbrl_confidence": 0.99,
  "llm_confidence": 0.8
}
```

## Testing

All test results documented in:
- `docs/TESTING_SUMMARY.md` - Complete testing overview
- `docs/424B_MATCHING_TESTS.md` - Filing matcher tests
- `docs/ERROR_TESTING_RESULTS.md` - Error case handling

## Dependencies

See `requirements.txt` for full list. Key dependencies:
- `google-generativeai` - LLM extraction
- `pydantic` - Data validation
- `requests` - SEC API access
- `beautifulsoup4` - HTML parsing

## Environment Setup

Create `.env.local` with:
```
GOOGLE_API_KEY=your_api_key_here
```

## Contributing

1. Core extraction logic in `core/`
2. Utility scripts in `scripts/`
3. Documentation in `docs/`
4. All outputs to `output/`
5. Test before committing!

