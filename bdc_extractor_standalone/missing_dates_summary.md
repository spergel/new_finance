# Missing Dates Analysis Summary

## Overall Statistics
- **Total investments analyzed**: 55,652
- **Missing acquisition_date**: 51,680 (92.9%)
- **Missing maturity_date**: 41,099 (73.8%)

### Debt-Specific
- **Total debt investments**: 30,201
- **Debt missing acquisition_date**: 28,602 (94.7%)
- **Debt missing maturity_date**: 18,201 (60.3%)

## Critical Issues by Ticker

### 100% Missing Maturity Date (Debt)
These tickers have **ALL** debt investments missing maturity dates:
- **CGBD** (TCG BDC Inc) - 664/664 debt (100%)
- **CSWC** (Capital Southwest Corp) - 765/765 debt (100%)
- **GAIN** (Gladstone Investment Corp) - 28/28 debt (100%)
- **GBDC** (Golub Capital BDC Inc) - 1,111/1,111 debt (100%)
- **MAIN** (Main Street Capital Corp) - 493/493 debt (100%)
- **MSDL** (Morgan Stanley Direct Lending Fund) - All investments (100%)

### 100% Missing Acquisition Date (Debt)
These tickers have **ALL** debt investments missing acquisition dates:
- **BCSF** (Bain Capital Specialty Finance Inc) - 1,112/1,112 debt (100%)
- **CGBD** (TCG BDC Inc) - 664/664 debt (100%)
- **CION** (CION Investment Corp) - 214/214 debt (100%)
- **CSWC** (Capital Southwest Corp) - 765/765 debt (100%)

### Tickers with Good Date Coverage
- **ARCC** (Ares Capital Corporation) - Only 36.4% missing acquisition_date, 77.8% missing maturity_date
- **FDUS** (Fidus Investment Corp) - Only 11.8% missing acquisition_date, 57.7% missing maturity_date
- **GSBD** (Goldman Sachs BDC Inc) - Only 10.1% missing maturity_date (but 90.2% missing acquisition_date)
- **HTGC** (Hercules Capital Inc) - Only 8.5% missing maturity_date (but 100% missing acquisition_date)

## Patterns Identified

1. **Parser-Specific Issues**: Different parsers extract dates differently
   - ARCC parser extracts dates well (has dates in MM/DD/YYYY format)
   - CGBD, CSWC, MAIN parsers extract NO dates
   - HTGC parser extracts maturity dates but not acquisition dates

2. **Investment Type Patterns**:
   - Equity investments typically don't have maturity dates (expected)
   - Debt investments should have maturity dates but many are missing
   - Acquisition dates are missing across all investment types

3. **Date Format Variations**:
   - ARCC uses: MM/DD/YYYY format (e.g., "04/01/2025")
   - HTGC uses: YYYY-MM-DD format (e.g., "2029-08-01")
   - Many files have empty strings or NaN

## Recommendations

### High Priority Fixes
1. **CGBD parser** - Add date extraction (currently 100% missing both dates)
2. **CSWC parser** - Add date extraction (currently 100% missing both dates)
3. **MAIN parser** - Add date extraction (currently 100% missing both dates)
4. **MSDL parser** - Add date extraction (currently 100% missing both dates)
5. **GBDC parser** - Add maturity date extraction for debt (currently 100% missing)

### Medium Priority Fixes
1. **HTGC parser** - Add acquisition date extraction (currently 100% missing)
2. **BCSF parser** - Add acquisition date extraction (currently 100% missing)
3. **CION parser** - Add acquisition date extraction (currently 100% missing)
4. **GAIN parser** - Add maturity date extraction for debt (currently 100% missing)

### Low Priority (Already Good)
- **ARCC parser** - Working well, could improve maturity date coverage
- **FDUS parser** - Working well, could improve maturity date coverage

## Root Cause Analysis

After reviewing the parser code:

1. **CGBD Parser**: Has date extraction logic in `_parse_identifier()` that looks for dates in the identifier string using regex patterns:
   - `Maturity\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})`
   - `(?:Acquisition|Investment)\s*Date\s*(\d{1,2}/\d{1,2}/\d{2,4})`
   - **Problem**: Dates are likely NOT in the identifier string - they're probably in HTML tables or separate XBRL facts

2. **MAIN Parser**: Has `parse_date()` function that can parse dates from cells, but it's only used when specific column headers are found. The parser may not be finding the date columns.

3. **CSWC Parser**: Similar to CGBD - tries to extract dates from identifier but they're not there.

4. **Pattern**: Most parsers extract dates from the identifier string, but for many BDCs, dates are in:
   - HTML table columns (separate columns for acquisition date, maturity date)
   - Separate XBRL facts (not in the identifier)
   - Context dates (startDate/endDate in XBRL contexts)

## Next Steps

### Immediate Actions
1. **Check HTML tables** for date columns - many BDCs have separate columns for dates
2. **Check XBRL facts** - dates might be in separate fact elements, not in identifier
3. **Check context dates** - XBRL contexts have startDate/endDate that might represent maturity dates

### Parser-Specific Fixes Needed

#### CGBD (100% missing both dates)
- Check HTML fallback extraction (`_extract_html_fallback`) - add date column parsing
- Check if dates are in separate XBRL facts (not just identifier)
- Review actual CGBD filing HTML to see where dates are located

#### CSWC (100% missing both dates)  
- Similar to CGBD - check HTML tables for date columns
- Review CSWC filing structure

#### MAIN (100% missing both dates)
- The parser has date parsing logic but may not be finding date columns
- Check if column headers are being matched correctly
- Review MAIN filing HTML structure

#### MSDL (100% missing both dates)
- Check which parser MSDL uses (may be using FlexibleTableParser)
- Ensure FlexibleTableParser extracts date columns

#### GBDC (100% missing maturity_date for debt)
- Check if maturity dates are in identifier or separate columns
- Review GBDC filing structure

### Testing Strategy
1. Download a sample filing HTML for each problematic ticker
2. Manually inspect where dates appear (identifier, HTML table columns, XBRL facts)
3. Update parser logic to extract dates from the correct location
4. Re-run extraction and verify dates are populated

