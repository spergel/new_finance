# Project Structure

## Overview
This project extracts comprehensive preferred stock data from SEC filings using a hybrid approach:
- **XBRL extraction** from 10-Q filings (current financial data)
- **LLM extraction** from 424B prospectuses (detailed terms)
- **Data fusion** to combine both sources

## Directory Structure

```
new_finance/
├── core/                           # Core extraction modules
│   ├── xbrl_preferred_shares_extractor.py   # Regex-based 10-Q extraction
│   ├── filing_matcher.py                    # Intelligent 424B matching
│   ├── data_fusion.py                       # Combines XBRL + LLM data
│   ├── securities_features_extractor.py     # LLM-based 424B extraction
│   ├── sec_api_client.py                    # SEC EDGAR API client
│   ├── models.py                            # Pydantic data models
│   └── corporate_actions_extractor.py       # Corporate actions extraction
│
├── output/                         # All extraction outputs
│   ├── fused/                      # ✨ Combined XBRL + LLM data (USE THIS!)
│   ├── xbrl/                       # Raw XBRL extractions
│   ├── summaries/                  # XBRL summaries
│   ├── enhanced/                   # LLM-only extractions
│   ├── llm/                        # Raw LLM responses
│   └── legacy/                     # Old format outputs
│
├── scripts/                        # Utility scripts
│   ├── run_fusion.py               # Run data fusion for a ticker
│   ├── test_fusion_diverse.py      # Test across multiple companies
│   ├── extract.py                  # Extraction utilities
│   └── retest_banks.py             # Bank-specific testing
│
├── docs/                           # Documentation
│   ├── README.md                   # Documentation overview
│   ├── XBRL_EXTRACTION_FEATURES.md # XBRL extraction capabilities
│   ├── LLM_EXTRACTION_COMPLETE.md  # LLM extraction features
│   ├── FILING_STRATEGY_FINAL.md    # 424B matching strategy
│   ├── 424B_MATCHING_TESTS.md      # Matching test results
│   └── TESTING_SUMMARY.md          # Complete testing summary
│
├── data/                           # Sample filing data
│
├── main.py                         # Main entry point
├── requirements.txt                # Python dependencies
└── README.md                       # Project README

```

## Key Files

### Core Modules

- **`core/xbrl_preferred_shares_extractor.py`**
  - Extracts from 10-Q filings using regex
  - Features: dividend rate, shares, par value, cumulative status, voting rights
  - Handles multi-letter series (e.g., RR, TT)

- **`core/filing_matcher.py`**
  - Matches 424B filings to known securities
  - Cross-references series names from 10-Q
  - Confidence scoring based on content analysis

- **`core/data_fusion.py`**
  - Combines XBRL and LLM extractions
  - XBRL = source of truth for current financials
  - LLM = detailed narrative features

- **`core/securities_features_extractor.py`**
  - LLM-based extraction from 424B prospectuses
  - Features: conversion terms, redemption, governance, special provisions

### Output Files

**🎯 Primary Output: `output/fused/`**
- Combined XBRL + LLM data
- Most complete and accurate
- Use this for investment analysis

**Other Outputs:**
- `output/xbrl/` - Raw XBRL extractions (10-Q only)
- `output/enhanced/` - LLM extractions (424B only)
- `output/summaries/` - XBRL summaries
- `output/legacy/` - Old format outputs

## Usage

### Extract Complete Data for a Ticker

```python
from scripts.run_fusion import main

# Extract and fuse data for JXN
result = main('JXN')

# Output saved to: output/fused/JXN_fused_preferred_shares.json
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

