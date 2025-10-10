# Usage Guide

How to use the preferred stock extraction system.

## Quick Start

### Extract Complete Data (Recommended)

```python
from scripts.run_fusion import main

# Extract and fuse data for a ticker
result = main('JXN')

# Output saved to: output/fused/JXN_fused_preferred_shares.json
```

This runs the complete pipeline:
1. XBRL extraction from 10-Q
2. Filing matching for 424Bs
3. LLM extraction from matched 424Bs
4. Data fusion

### Extract XBRL Only

```python
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares

result = extract_xbrl_preferred_shares('JXN')

# Returns:
# {
#   "ticker": "JXN",
#   "securities": [{
#     "series_name": "A",
#     "dividend_rate": 8.0,
#     "outstanding_shares": 22000,
#     "par_value": 25000.0,
#     ...
#   }]
# }
```

### Extract LLM Only

```python
from core.securities_features_extractor import SecuritiesFeaturesExtractor

extractor = SecuritiesFeaturesExtractor()
result = extractor.extract_securities_features('JXN')

# Returns detailed terms from 424B prospectuses
```

### Manual Fusion

```python
from core.data_fusion import fuse_data
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares
from core.securities_features_extractor import SecuritiesFeaturesExtractor

# Get XBRL data
xbrl_result = extract_xbrl_preferred_shares('JXN')

# Get LLM data
extractor = SecuritiesFeaturesExtractor()
llm_result = extractor.extract_securities_features('JXN')
llm_dict = {
    'ticker': llm_result.ticker,
    'securities': [sec.dict() for sec in llm_result.securities]
}

# Fuse
fused = fuse_data('JXN', xbrl_result, llm_dict)
```

## Command Line Usage

### Run Full Extraction

```bash
# Single ticker
python scripts/run_fusion.py JXN

# Output: output/fused/JXN_fused_preferred_shares.json
```

### Test Multiple Tickers

```bash
python scripts/test_fusion_diverse.py

# Tests: JXN, C, BAC, PSA
# Outputs to: output/fused/{TICKER}_fused_preferred_shares.json
```

### Use Main Script

```bash
# Extract securities features (LLM only)
python main.py JXN

# Output: output/enhanced/JXN_enhanced_securities_features.json
```

## Output Locations

All outputs are in `output/` directory:

```
output/
├── fused/          # ⭐ Use this - Complete XBRL + LLM data
├── xbrl/           # XBRL extractions only
├── enhanced/       # LLM extractions only
├── summaries/      # XBRL summaries
└── llm/            # Raw LLM responses
```

## Working with Output

### Load Fused Data

```python
import json

with open('output/fused/JXN_fused_preferred_shares.json') as f:
    data = json.load(f)

# Access securities
for security in data['securities']:
    print(f"Series {security['series_name']}")
    print(f"  Dividend Rate: {security['dividend_rate']}%")
    print(f"  Outstanding: {security['outstanding_shares']:,}")
    print(f"  Callable: {security['redemption_terms']['is_callable']}")
```

### Filter by Criteria

```python
import json

with open('output/fused/C_fused_preferred_shares.json') as f:
    data = json.load(f)

# Find high-yield preferreds (>6%)
high_yield = [
    s for s in data['securities']
    if s.get('dividend_rate') and s['dividend_rate'] > 6.0
]

print(f"Found {len(high_yield)} high-yield preferreds")
```

### Check Data Quality

```python
import json

with open('output/fused/JXN_fused_preferred_shares.json') as f:
    data = json.load(f)

for security in data['securities']:
    series = security['series_name']
    has_llm = security.get('has_llm_data', False)
    xbrl_conf = security.get('xbrl_confidence', 0)
    llm_conf = security.get('llm_confidence', 0)
    
    print(f"Series {series}:")
    print(f"  XBRL Confidence: {xbrl_conf:.2f}")
    if has_llm:
        print(f"  LLM Confidence: {llm_conf:.2f}")
        print(f"  ✓ Complete data")
    else:
        print(f"  ⚠ XBRL only (no 424B match)")
```

## Advanced Usage

### Custom Filing Selection

```python
from core.filing_matcher import match_all_filings_to_securities
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares

# Get known securities
xbrl_result = extract_xbrl_preferred_shares('JXN')
securities = xbrl_result['securities']

# Match filings with custom parameters
matched = match_all_filings_to_securities(
    ticker='JXN',
    known_securities=securities,
    max_filings=100  # Check more filings
)

print(f"Matched {len(matched)} filings")
for filing in matched:
    print(f"  {filing['form']} {filing['date']}: Series {filing['matched_series']}")
```

### Manual Filing Selection

```python
from core.sec_api_client import SECAPIClient
from core.securities_features_extractor import SecuritiesFeaturesExtractor

client = SECAPIClient()
extractor = SecuritiesFeaturesExtractor()

# Get specific filing by accession number
content = client.get_filing_by_accession(
    ticker='JXN',
    accession_number='0001104659-23-029632'
)

print(f"Retrieved {len(content)} characters")
```

### Batch Processing

```python
from scripts.run_fusion import main
import json

tickers = ['JXN', 'C', 'BAC', 'PSA', 'MET']
results = {}

for ticker in tickers:
    try:
        print(f"Processing {ticker}...")
        result = main(ticker)
        results[ticker] = {
            'success': True,
            'securities': result['total_securities'],
            'with_llm': result['securities_with_llm_data']
        }
    except Exception as e:
        print(f"  Error: {e}")
        results[ticker] = {'success': False, 'error': str(e)}

# Summary
for ticker, result in results.items():
    if result['success']:
        print(f"{ticker}: {result['securities']} securities ({result['with_llm']} with LLM)")
    else:
        print(f"{ticker}: FAILED - {result['error']}")
```

## Environment Setup

### Required

Create `.env.local` with your Google API key:

```
GOOGLE_API_KEY=your_api_key_here
```

Get a key at: https://makersuite.google.com/app/apikey

### Optional

```
# Logging level
LOG_LEVEL=INFO

# SEC API rate limiting
SEC_RATE_LIMIT=10  # requests per second
```

## Error Handling

### Common Issues

**No preferred shares found:**
```python
result = extract_xbrl_preferred_shares('AAPL')
# Returns empty securities list (Apple has no preferreds)
```

**No 424B matches:**
```python
# For old preferreds, you'll get XBRL data but no LLM data
result = main('C')  # Citigroup has old preferreds
# Output has has_llm_data=false for most series
```

**API timeout:**
```python
try:
    result = main('JXN')
except Exception as e:
    print(f"Error: {e}")
    # Retry or use cached data
```

### Validation

```python
def validate_security(security):
    """Validate extracted security data."""
    issues = []
    
    # Check required fields
    if not security.get('series_name'):
        issues.append("Missing series name")
    if not security.get('dividend_rate'):
        issues.append("Missing dividend rate")
    if not security.get('outstanding_shares'):
        issues.append("Missing outstanding shares")
    
    # Check reasonableness
    div_rate = security.get('dividend_rate', 0)
    if div_rate < 0 or div_rate > 20:
        issues.append(f"Suspicious dividend rate: {div_rate}%")
    
    # Check confidence
    if security.get('xbrl_confidence', 0) < 0.7:
        issues.append("Low XBRL confidence")
    
    return issues

# Use it
with open('output/fused/JXN_fused_preferred_shares.json') as f:
    data = json.load(f)

for security in data['securities']:
    issues = validate_security(security)
    if issues:
        print(f"Series {security['series_name']}:")
        for issue in issues:
            print(f"  ⚠ {issue}")
```

## Performance Tips

1. **Use fused output** - Don't re-extract if you already have it
2. **Cache SEC filings** - Download once, process many times
3. **Batch process** - Process multiple tickers in one script
4. **Filter early** - Check if company has preferreds before full extraction
5. **Parallel processing** - Process multiple tickers concurrently

## Best Practices

1. **Always check confidence scores** before using data
2. **Verify redemption dates** - They can change via amendments
3. **Review LLM extractions** for complex provisions
4. **Use XBRL for financials** - It's more current
5. **Use LLM for terms** - It captures nuance better
6. **Save intermediate results** for debugging
7. **Log extraction metadata** for audit trail

## Troubleshooting

### No output generated

Check:
1. Ticker is valid
2. Company has preferred shares
3. API credentials are set
4. Output directory exists

### Incorrect data

Check:
1. Confidence scores
2. Filing dates (is it current?)
3. Series name matching
4. Manual verification against SEC filings

### Slow extraction

Normal times:
- XBRL: 10-30 seconds
- LLM: 10-20 seconds per filing
- Total: 30-80 seconds

If slower:
- Check network connection
- Check SEC API rate limits
- Check Google API quotas

### Missing LLM data

Reasons:
- No 424B filings found
- Filings too old (>10 years)
- Filing matching failed
- API quota exceeded

Solution:
- Use XBRL data only
- Manually specify filing
- Increase `max_filings` parameter

