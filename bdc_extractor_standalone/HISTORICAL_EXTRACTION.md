# Historical Investment Data Extraction

This module adds the ability to extract historical investment data from previous 10-Q filings for all BDCs, creating time-series datasets perfect for frontend visualization.

## Features

- Extract investments from multiple historical 10-Q filings
- Track reporting periods for each investment
- Batch processing for all BDCs
- CSV output with `reporting_period`, `filing_date`, and `accession_number` fields

## Usage

### Extract Historical Data for a Single BDC

```python
from historical_investment_extractor import extract_historical_for_ticker

# Extract last 3 years of data for GLAD
csv_path = extract_historical_for_ticker(
    ticker="GLAD",
    parser_module_name="glad_parser",
    years_back=3
)

print(f"Historical data saved to: {csv_path}")
```

### Extract Historical Data for All BDCs

```bash
# Extract last 5 years for all BDCs
python batch_historical_extractor.py --years-back 5

# Extract for specific BDCs only
python batch_historical_extractor.py --ticker GLAD --ticker GAIN --years-back 3

# Skip BDCs that already have historical CSV files
python batch_historical_extractor.py --years-back 5 --skip-processed

# Save summary report
python batch_historical_extractor.py --years-back 5 --report-file summary.txt
```

### Programmatic Usage

```python
from batch_historical_extractor import BatchHistoricalExtractor

# Create batch extractor
batch = BatchHistoricalExtractor(
    years_back=5,
    output_dir="output"
)

# Process all BDCs
results = batch.process_all_bdcs()

# Generate summary report
batch.generate_summary_report(output_file="summary.txt")
```

## Output Format

The historical investment CSV files include all standard investment fields plus:

- `reporting_period`: Period end date (YYYY-MM-DD) - the date the investment snapshot was taken
- `filing_date`: Date the 10-Q was filed with the SEC
- `accession_number`: SEC accession number for the filing

This allows you to:
- Track how investments change over time
- Identify when investments were added or removed
- Analyze portfolio composition changes
- Build time-series visualizations

## CSV Structure

```csv
reporting_period,filing_date,accession_number,company_name,industry,...,principal_amount,cost,fair_value
2024-09-30,2024-11-08,0001104659-24-123456,Company A,Software,...,1000000,950000,980000
2024-06-30,2024-08-07,0001104659-24-098765,Company A,Software,...,1000000,940000,970000
...
```

## Performance Considerations

- Processing all BDCs with 5 years of history can take 30-60 minutes
- Each BDC requires fetching multiple 10-Q filings from the SEC
- Use `--skip-processed` to avoid re-processing existing data
- Rate limiting is handled automatically by the SEC API client

## Notes

- Historical data extraction relies on the existing parser modules
- If a parser doesn't exist for a BDC, it will be skipped
- Some BDCs may have limited historical filings available
- Period end dates are extracted from XBRL content when available



