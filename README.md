# Preferred Stock Data Extraction System

A streamlined system for extracting comprehensive preferred stock data from SEC filings using regex and LLM extraction.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Extract data for a ticker
python scripts/extract_preferred_stocks.py JXN
```

## Core Features

- **Simple regex extraction** from 10-Q filings to identify preferred stock series
- **Smart filing matching** to find relevant 424B prospectuses
- **LLM-powered extraction** for complex terms and conditions
- **Clean, focused results** with proper deduplication

## Project Structure

```
new_finance/
├── core/                          # Core extraction modules
│   ├── securities_features_extractor.py  # LLM extraction
│   ├── filing_matcher.py                 # 424B filing matching
│   ├── xbrl_preferred_shares_extractor.py # Series identification
│   ├── sec_api_client.py                 # SEC API client
│   └── models.py                         # Data models
├── docs/                          # Documentation
├── output/                        # All extraction results
├── data/                          # Sample filing data (gitignored)
└── scripts/                       # Utility scripts (gitignored)
```

## Documentation

See [docs/README.md](docs/README.md) for complete documentation, including:
- Detailed usage instructions
- API reference
- Architecture overview
- Testing results

## Example Output

```json
{
  "ticker": "JXN",
  "securities": [
    {
      "security_id": "Series A Preferred Stock",
      "dividend_rate": 8.0,
      "liquidation_preference": 25000.0,
      "par_value": 0.01,
      "is_cumulative": false,
      "redemption_terms": {
        "earliest_call_date": "2028-03-30"
      }
    }
  ]
}
```

## Requirements

- Python 3.8+
- Google Gemini API key (optional, for LLM features)
- See `requirements.txt` for full dependencies

## License

MIT
