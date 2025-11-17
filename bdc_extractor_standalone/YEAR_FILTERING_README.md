# Year Filtering for BDC Extractors

All parsers now support year filtering to ensure we get 2025 data by default, while still allowing historical data extraction.

## Default Behavior

By default, all parsers will extract data from **2025 filings only**. This ensures consistency and prevents accidentally extracting older data.

## Usage

### Default (2025 data)
```python
from psec_custom_parser import PSECCustomExtractor

extractor = PSECCustomExtractor()
result = extractor.extract_from_ticker("PSEC")  # Gets 2025 data
```

### Specific Year
```python
# Get 2024 data
result = extractor.extract_from_ticker("PSEC", year=2024)

# Get 2023 data
result = extractor.extract_from_ticker("PSEC", year=2023)
```

### Latest Filing (Any Year)
```python
# Get the most recent filing regardless of year
result = extractor.extract_from_ticker("PSEC", year=None)
```

### Minimum Date Filter
```python
# Get filings after a specific date
result = extractor.extract_from_ticker("PSEC", min_date="2025-01-01")
```

## Implementation Details

- The `get_filing_index_url()` method in `SECAPIClient` now filters filings by report date
- Default year is 2025 if no year or min_date is specified
- All parsers have been updated to support `year` and `min_date` parameters
- Historical extraction is fully supported - just pass the desired year

## Updated Parsers

All parsers in the `bdc_extractor_standalone` directory have been updated:
- All `*_custom_parser.py` files
- All `*_parser.py` files (except utility parsers)

## Notes

- The year filter is based on the filing's report date, not the filing date
- If no filing exists for the specified year, the parser will raise an error
- Use `year=None` to get the latest filing regardless of year (useful for historical analysis)

