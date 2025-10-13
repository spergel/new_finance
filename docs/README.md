# Preferred Stock Data Extraction System

## Overview

This system extracts comprehensive preferred stock data from SEC filings using a streamlined approach:

1. **Regex Series Identification** - Simple pattern matching to find preferred stock series in 10-Q filings
2. **Smart Filing Matching** - Match each series to its specific 424B prospectus
3. **LLM Feature Extraction** - Extract detailed terms and conditions from matched filings
4. **Clean Output** - Unified JSON results with proper deduplication

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Extract data for a ticker
python scripts/extract_preferred_stocks.py JXN
```

## Architecture

```
User Input (Ticker)
    │
    ├─► 10-Q Analysis (Regex)
    │   └─► Identify preferred stock series
    │
    ├─► Filing Matcher
    │   └─► Find best 424B for each series
    │
    └─► LLM Extractor
        └─► Extract from matched filings
            └─► output/llm/{TICKER}_securities_features.json
```

## Core Documentation

- **[USAGE.md](USAGE.md)** - How to use the system
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and data flow
- **[FEATURES.md](FEATURES.md)** - Complete list of extracted features
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - Project organization
- **[TODO.md](TODO.md)** - Development roadmap

## What's Extracted

### Core Features
- **Dividend Information**: Rate, type, payment frequency, cumulative status
- **Capital Structure**: Liquidation preference, par value, outstanding shares
- **Redemption Terms**: Call dates, prices, notice periods
- **Conversion Features**: Ratios, triggers, price adjustments
- **Governance**: Voting rights, director election, protective provisions
- **Special Terms**: Tax treatment, anti-dilution, rate resets

### Output Format
Clean JSON with complete preferred stock data.

**Location:** `output/llm/{TICKER}_securities_features.json`

## Usage Examples

### Command Line
```bash
# Extract preferred stock data for a company
python scripts/extract_preferred_stocks.py JXN

# Output: output/llm/JXN_securities_features.json
```

### Python API
```python
from core.securities_features_extractor import extract_preferred_stocks_simple

result = extract_preferred_stocks_simple('JXN')
# Returns complete preferred stock data
```

## Example Output

```json
{
  "ticker": "JXN",
  "extraction_date": "2025-10-13",
  "securities": [
    {
      "security_id": "Series A Preferred Stock",
      "security_type": "preferred_stock",
      "description": "8.0% Series A Cumulative Perpetual Preferred Stock",
      "dividend_rate": 8.0,
      "liquidation_preference": 25000.0,
      "par_value": 0.01,
      "is_cumulative": true,
      "redemption_terms": {
        "earliest_call_date": "2028-03-30"
      }
    }
  ]
}
```

## Documentation Structure

```
docs/
├── README.md           # This file - documentation index
├── ARCHITECTURE.md     # System design and data flow
├── FEATURES.md         # Complete feature list
├── USAGE.md            # Usage guide
└── TODO.md             # Development roadmap
```

## Need Help?

1. **Getting Started:** [USAGE.md](USAGE.md)
2. **Understanding Output:** [FEATURES.md](FEATURES.md)
3. **System Design:** [ARCHITECTURE.md](ARCHITECTURE.md)
4. **Issues/Questions:** Create an issue on GitHub
