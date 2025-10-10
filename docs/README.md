# Documentation

## Core Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and data flow
- **[FEATURES.md](FEATURES.md)** - Complete list of extracted features
- **[USAGE.md](USAGE.md)** - How to use the system
- **[TODO.md](TODO.md)** - Development roadmap

## Quick Links

### For Users
- **Quick Start:** See [USAGE.md](USAGE.md#quick-start)
- **Feature List:** See [FEATURES.md](FEATURES.md)
- **Output Format:** See [FEATURES.md](FEATURES.md#fused-output)

### For Developers
- **System Design:** See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Data Flow:** See [ARCHITECTURE.md](ARCHITECTURE.md#data-flow)
- **Core Modules:** See [ARCHITECTURE.md](ARCHITECTURE.md#core-modules)

## Overview

This system extracts comprehensive preferred stock data from SEC filings using:

1. **XBRL Extraction** - Current financial data from 10-Q filings
2. **Filing Matcher** - Intelligent 424B prospectus matching  
3. **LLM Extraction** - Detailed terms from prospectuses
4. **Data Fusion** - Combined complete datasets

## What's Extracted

### From 10-Q (XBRL)
- Dividend rate
- Outstanding/authorized shares
- Par value
- Cumulative status
- Basic voting rights

### From 424B (LLM)
- Conversion terms
- Redemption provisions
- Governance features
- Rate reset terms
- Special provisions

### Fused Output
Complete dataset combining current financials with detailed terms.

**Location:** `output/fused/{TICKER}_fused_preferred_shares.json`

## Quick Start

```bash
# Extract complete data for a ticker
python scripts/run_fusion.py JXN

# Output: output/fused/JXN_fused_preferred_shares.json
```

```python
from scripts.run_fusion import main

result = main('JXN')
# Returns fused data with XBRL + LLM
```

## Example Output

```json
{
  "ticker": "JXN",
  "series_name": "A",
  "dividend_rate": 8.0,
  "outstanding_shares": 22000,
  "par_value": 25000.0,
  "is_cumulative": false,
  "redemption_terms": {
    "is_callable": true,
    "earliest_call_date": "2028-03-30"
  },
  "has_llm_data": true
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
