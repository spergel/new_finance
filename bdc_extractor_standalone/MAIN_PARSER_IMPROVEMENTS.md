# MAIN Parser Improvements

## Summary

I've analyzed MAIN's HTML table structure and improved the `main_parser.py` to correctly extract investment data from their schedule of investments tables.

## Key Improvements

### 1. Added Rate String Parser (`_parse_rate_string`)

MAIN's "Rate" column contains complex strings that need parsing:
- `"10.00% (Prime+6.75%, Floor 2.00%)"` → Extracts interest_rate, reference_rate (PRIME), spread (6.75%), floor_rate (2.00%)
- `"12.00% (L+11.00%, Floor 1.00%)"` → Extracts interest_rate, reference_rate (LIBOR), spread (11.00%), floor_rate (1.00%)
- `"11.50%"` → Simple interest rate
- `"12.00% PIK"` → Extracts interest_rate and pik_rate
- `"13.00% (10.00% Cash, 3.00% PIK)"` → Extracts interest_rate and pik_rate

The new function properly handles all these formats and normalizes reference rate names (L → LIBOR, SF → SOFR, etc.).

### 2. Improved Column Detection

Updated the header detection to specifically look for MAIN's table format:
- Requires: "Portfolio Company", "Investment Date", "Type of Investment", "Rate", "Maturity Date", and financial columns
- Maps columns correctly based on MAIN's actual structure

### 3. Better Handling of Table Structure

MAIN's tables have a specific structure:
- **Company header rows**: Column 0 has company name, Column 2 has investment date, Column 3 has business description
- **Investment detail rows**: Column 0 is empty, Column 4 has investment type, Column 6 has rate, Column 7 has maturity date, etc.

The parser now:
- Correctly identifies company header rows vs. investment detail rows
- Skips company header rows (they don't have investment data)
- Properly handles continuation rows (empty Column 0)
- Skips subtotal rows

### 4. Correct Column Mapping

Based on actual HTML inspection:
- **Column 0**: Portfolio Company (company name)
- **Column 2**: Investment Date (acquisition date)
- **Column 3**: Business Description
- **Column 4**: Type of Investment
- **Column 5**: Shares/Units
- **Column 6**: Rate (complex string to parse)
- **Column 7**: Maturity Date
- **Column 8**: "$" (dollar sign, separate cell)
- **Column 9**: Principal amount (value after $)
- **Column 10**: Cost
- **Column 11**: Fair Value

### 5. Value Extraction Improvements

- Principal: Correctly handles the case where $ is in a separate cell (Column 8), value is in Column 9
- Cost: Directly from Column 10
- Fair Value: Directly from Column 11
- All values are multiplied by 1000 (MAIN reports in thousands)

## Testing Recommendations

1. Test with actual MAIN filings to verify:
   - Rate parsing handles all formats correctly
   - Maturity dates are extracted properly
   - Company names and investment types are correctly identified
   - Financial values are correctly extracted and converted from thousands

2. Compare output with `main_custom_parser.py` to ensure consistency

3. Check that subtotal rows are properly skipped

## Files Modified

- `bdc_extractor_standalone/main_parser.py`:
  - Added `_parse_rate_string()` method
  - Updated `_parse_html_tables()` method with improved MAIN-specific logic

## Documentation Created

- `MAIN_HTML_TABLE_ANALYSIS.md`: Detailed analysis of MAIN's HTML table structure
- `MAIN_PARSER_IMPROVEMENTS.md`: This file

