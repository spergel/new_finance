# Preferred Share Data Extraction System

A comprehensive system for extracting and analyzing preferred share data from SEC filings using a hybrid regex + LLM approach.

## Overview

This system extracts detailed information about preferred shares from SEC filings by:
1. **Regex extraction** from 10-Q filings for structured financial data
2. **Intelligent 424B matching** to identify correct historical prospectuses
3. **LLM extraction** from 424B filings for complex narrative features
4. **Data fusion** to combine both sources into unified output

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up Google API key (optional, for LLM extraction)
export GOOGLE_API_KEY="your-api-key-here"

# Extract data for a ticker
python -c "from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares; \
           result = extract_xbrl_preferred_shares('JXN'); \
           print(f'Found {len(result[\"preferred_shares\"])} preferred shares')"
```

## System Architecture

```
User Input (Ticker)
    │
    ├─► 10-Q Extraction (Regex)
    │   └─► Financial terms (dividend, shares, liquidation)
    │
    ├─► 424B Filing Matcher
    │   └─► Identifies correct historical prospectuses by series
    │
    ├─► LLM Extraction (Optional)
    │   └─► Narrative features (conversion, redemption, governance)
    │
    └─► Data Fusion
        └─► Unified JSON output
```

## Features Extracted

### From 10-Q (Always Available)
- ✓ Dividend rate (fixed/floating)
- ✓ Outstanding & authorized shares
- ✓ Liquidation preference
- ✓ Cumulative vs non-cumulative
- ✓ Par value
- ✓ Voting rights
- ✓ Ranking/priority
- ✓ Payment frequency
- ✓ Basic call dates

### From 424B (When Available)
- ✓ Detailed conversion terms
- ✓ Redemption provisions
- ✓ Dividend stopper clauses
- ✓ PIK toggle options
- ✓ Governance rights
- ✓ Protective provisions
- ✓ Change of control terms
- ✓ Rate reset mechanisms

## Core Modules

### `core/xbrl_preferred_shares_extractor.py`
Extracts structured financial data from 10-Q filings using regex patterns.

```python
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares

result = extract_xbrl_preferred_shares('JXN')
print(result)
# {
#   'ticker': 'JXN',
#   'preferred_shares': [
#     {
#       'series': 'A',
#       'dividend_rate': 8.0,
#       'outstanding_shares': 22000,
#       'is_cumulative': False,
#       ...
#     }
#   ]
# }
```

### `core/filing_matcher.py`
Intelligently matches 424B filings to specific preferred share series.

```python
from core.filing_matcher import match_all_filings_to_securities

known_securities = [{'series_name': 'Series A'}]
matched = match_all_filings_to_securities('JXN', known_securities, max_filings=50)
print(f"Found {len(matched)} matched filings")
```

### `core/securities_features_extractor.py`
Extracts complex narrative features from 424B using LLMs.

```python
from core.securities_features_extractor import SecuritiesFeaturesExtractor

extractor = SecuritiesFeaturesExtractor()
result = extractor.extract_securities_features('JXN')
print(f"Extracted {result.total_securities} securities")
```

### `core/data_fusion.py`
Merges 10-Q and 424B data into unified output.

```python
from core.data_fusion import fuse_data

fused = fuse_data('JXN', xbrl_result, llm_result)
print(f"Fused {fused['total_securities']} securities")
```

## Testing

### Run All Tests
```bash
# System validation
python test_system_final.py

# 424B matching tests (17 tests)
python test_424b_matching_comprehensive.py

# Full LLM extraction pipeline
python test_llm_extraction_full.py

# Data fusion
python test_data_fusion.py
```

### Test Results
- ✓ **10-Q Extraction:** 95-99% confidence on financial terms
- ✓ **424B Matching:** 17/17 tests passing (100% accuracy)
- ✓ **LLM Extraction:** 80% confidence (tunable)
- ✓ **Multi-company:** Tested with JXN, Citigroup, Bank of America

## Example Output

### JXN - Series A Preferred Stock

**From 10-Q (Regex):**
```json
{
  "series": "A",
  "dividend_rate": 8.0,
  "outstanding_shares": 22000,
  "authorized_shares": 24000,
  "liquidation_preference_per_share": 25000.0,
  "is_cumulative": false,
  "par_value": 1.0,
  "confidence": 0.99
}
```

**From 424B (LLM):**
```json
{
  "description": "Fixed-Rate Reset Noncumulative Perpetual Preferred Stock, Series A",
  "redemption_terms": {
    "is_callable": false,
    "call_price": 25000.0,
    "earliest_call_date": "2028-03-30"
  }
}
```

**Fused Output:**
```json
{
  "series_name": "A",
  "dividend_rate": 8.0,
  "outstanding_shares": 22000,
  "liquidation_preference": 25000.0,
  "is_cumulative": false,
  "redemption_terms": {
    "earliest_call_date": "2028-03-30",
    "call_price": 25000.0
  },
  "has_llm_data": true,
  "xbrl_confidence": 0.99,
  "llm_confidence": 0.8
}
```

## Adaptive Strategy

### For Recent Issuances (e.g., JXN 2023)
- ✓ Extract from 10-Q (current financial terms)
- ✓ Match and extract from 424B (detailed provisions)
- ✓ Fuse data for complete picture

### For Old Issuances (e.g., Citigroup pre-2024)
- ✓ Extract from 10-Q (sufficient for decisions)
- ✓ Skip 424B search (too old, in historical archives)
- ✓ Log info message (not error)

## Requirements

```
beautifulsoup4>=4.12.0
requests>=2.31.0
python-dotenv>=1.0.0
google-generativeai>=0.3.0  # Optional, for LLM extraction
pydantic>=2.0.0
```

## Configuration

### Environment Variables
```bash
# Optional: For LLM extraction
GOOGLE_API_KEY=your-api-key-here

# Optional: Custom user agent for SEC requests
SEC_API_USER_AGENT="YourApp/1.0 (your@email.com)"
```

## Output Files

```
output/
├── xbrl/
│   ├── {TICKER}_xbrl_data.json      # Raw 10-Q extraction
│   └── ...
├── summaries/
│   ├── {TICKER}_xbrl_summary.json   # Human-readable summaries
│   └── ...
├── {TICKER}_llm_features.json       # 424B LLM extraction
└── {TICKER}_fused_data.json         # Final merged output
```

## Key Achievements

1. **Solved "Wrong 424B" Problem**
   - Was fetching recent debt filings instead of historical preferred prospectuses
   - Now correctly identifies and fetches specific historical 424Bs by accession number

2. **Multi-Company Robustness**
   - JXN: 1 series (new issuance)
   - Citigroup: 21 series (old issuances)
   - Bank of America: 4 series with multi-letter names (RR, TT, OO, UU)

3. **Production-Ready Code**
   - Comprehensive error handling
   - Confidence scoring
   - Data validation
   - Extensive testing

## Limitations

- 10-Q data only includes currently outstanding preferred shares
- LLM extraction requires Google API key and credits
- SEC API has rate limiting (~10 requests/second)
- Very old preferred shares (>1-2 years) may not have recent 424B filings

## Contributing

This is a research/investment tool. Use at your own risk. Always verify extracted data against original SEC filings.

## License

MIT

## Support

For issues or questions, please check the documentation in `/docs`:
- `IMPLEMENTATION_COMPLETE.md` - Full system documentation
- `FILING_STRATEGY_FINAL.md` - Filing matching strategy
- `424B_MATCHING_TESTS.md` - Test results and coverage
- `XBRL_EXTRACTION_FEATURES.md` - Regex extraction details
- `LLM_EXTRACTION_COMPLETE.md` - LLM extraction features



