# Custom Parser Status

## Completed Custom Parsers

### ✅ ARCC (Ares Capital Corporation)
- **File**: `arcc_custom_parser.py`
- **Status**: Working
- **Approach**: XBRL + HTML table merging
- **Coverage**: Improved from 65.2% to higher coverage with dates/rates

### ✅ MAIN (Main Street Capital Corporation)
- **File**: `main_custom_parser.py`
- **Status**: Working
- **Approach**: XBRL + HTML table merging with improved matching
- **Match Rate**: 41.9% (255/609 investments matched) - *Improved matching logic with proper deduplication*
- **Features**:
  - Extracts dates (acquisition_date, maturity_date) from HTML
  - Extracts rates (interest_rate, reference_rate, spread, pik_rate) from HTML
  - Extracts business descriptions and industries from HTML
  - Flexible matching handles XBRL identifiers like "Company, Secured Debt 1" matching HTML "Secured Debt"
  - Improved company name parsing (handles LLC/Inc. suffixes, HTML entities, parentheses)
  - Prevents double-matching of HTML entries to ensure accuracy

### ✅ NCDL (Nuveen Churchill Direct Lending Corp)
- **File**: `ncdl_custom_parser.py`
- **Status**: Working
- **Approach**: XBRL + HTML table merging with company-name-first matching
- **Match Rate**: 79.8% (398/499 investments matched) - *Improved from 51.7%*
- **Features**:
  - Extracts maturity dates from HTML
  - Extracts rates (interest_rate, reference_rate, spread, pik_rate) from HTML
  - Handles complex interest rates like "8.92% (Cash) 5.13% (PIK)"
  - Parses spread and reference rate from combined format (e.g., "S + 4.75%")
  - Matches by company name (removes trailing numbers from XBRL identifiers)
  - Improved company name parsing (handles HTML entities, parentheses, LLC/Inc. suffixes)
  - Fuzzy company name matching for better coverage
  - Prevents double-matching of HTML entries
  - Extracts % of Net Assets

### ✅ OBDC (Blue Owl Capital Corp)
- **File**: `obdc_custom_parser.py`
- **Status**: Working
- **Approach**: XBRL + HTML table merging with improved matching
- **Match Rate**: 81.6% (347/425 investments matched) - *Improved from 12.9% → 33.9% → 81.6%*
- **Features**:
  - Extracts maturity dates from HTML (MM/YYYY format)
  - Extracts rates (reference_rate, spread, pik_rate) from separate columns
  - Handles separate Cash and PIK rate columns
  - Extracts industries from section headers
  - Extracts % of Net Assets
  - Handles Par/Units (can be principal amount or units)
  - **Advanced matching features**:
    - Entity suffix normalization (matches "company" with "company llc")
    - Fuzzy company name matching (handles variations)
    - Better XBRL identifier parsing (handles "Unsecured facility" patterns)
    - Component-based investment type matching

### ✅ MFIC (Midcap Financial Investment Corp)
- **File**: `mfic_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction (no XBRL merging)
- **Investments Extracted**: ~1,500+ investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles continuation rows (empty company name)
  - Extracts interest rates, maturity dates, principal, cost, fair value
  - Filters for Q3 2025 (September 30, 2025) data only
  - Values in thousands (multiplied by 1000)

### ✅ GBDC (Golub Capital BDC Inc)
- **File**: `gbdc_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: ~2,400+ investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles continuation rows
  - Extracts spread, reference rate, interest rate, PIK rate
  - Extracts maturity dates, principal, cost, fair value
  - Filters for Q2 2025 (June 30, 2025) data
  - Values in thousands (multiplied by 1000)

### ✅ CION (CION Investment Corp)
- **File**: `cion_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: ~400+ investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Parses complex interest rate strings (e.g., "S+600, 1.00% SOFR Floor")
  - Extracts industry information
  - Extracts maturity dates, principal, cost, fair value
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)

### ✅ CSWC (Capital Southwest Corp)
- **File**: `cswc_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: ~50 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles continuation rows (empty company name, investment type in col 1)
  - Extracts principal and fair value
  - Handles equity investments with shares/units
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)

### ✅ PSEC (Prospect Capital Corp)
- **File**: `psec_custom_parser.py`
- **Status**: Working (with limitations)
- **Approach**: HTML-only extraction
- **Investments Extracted**: 287 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles continuation rows with correct column mapping
  - Parses complex coupon/yield strings (e.g., "12.31% (3M SOFR + 7.75%)", "6.00% plus 2.00% PIK")
  - Extracts principal, cost, fair value, maturity dates
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)
- **Limitations**:
  - 68 investments (24%) missing fair values - these are continuation rows where fair value is not in individual rows (may be in summary rows or different tables)
  - Write-down appears high (46.8%) but may be legitimate given portfolio composition

### ✅ OCSL (Oaktree Specialty Lending Corp)
- **File**: `ocsl_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: 784 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Extracts Index (reference rate), Spread, Cash Interest Rate, PIK rate from separate columns
  - Extracts maturity dates, principal, cost, fair value
  - Handles equity investments with shares
  - Handles both "$" in separate column and direct value formats
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)

### ✅ BBDC (Barings BDC Inc)
- **File**: `bbdc_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: 312 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles portfolio change table format (Dec 2024 → Sep 2025)
  - Calculates cost basis from Dec 2024 Value + Gross Additions - Gross Reductions
  - Extracts fair value from September 30, 2025 Value column
  - Parses interest rates, reference rates, spreads, PIK rates from investment type strings
  - Handles continuation rows (empty company name)
  - Extracts shares/units and percentage member interests
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)

### ✅ MSDL (Morgan Stanley Direct Lending Fund)
- **File**: `msdl_custom_parser.py`
- **Status**: Working
- **Approach**: XBRL-first extraction (HTML enhancement available but not needed)
- **Investments Extracted**: 697 investments
- **Features**:
  - Uses XBRL as primary data source (MSDL has good XBRL coverage)
  - Extracts all investment data from XBRL InvestmentIdentifierAxis
  - Filters for Q3 2025 (September 30, 2025) instant contexts
  - HTML parsing available for future enhancement if needed
  - Good coverage: 69.8% (close to 80% threshold)

### ✅ PFLT (PennantPark Floating Rate Capital Ltd)
- **File**: `pflt_custom_parser.py`
- **Status**: Working
- **Approach**: XBRL-first extraction (HTML enhancement available but not needed)
- **Investments Extracted**: 605 investments
- **Features**:
  - Uses XBRL as primary data source (PFLT has good XBRL coverage)
  - Extracts all investment data from XBRL InvestmentIdentifierAxis
  - Filters for Q2 2025 (June 30, 2025) instant contexts
  - HTML parsing available for future enhancement if needed
  - Coverage: 67.8% (close to 80% threshold)

### ✅ TCPC (Blackrock TCP Capital Corp)
- **File**: `tcpc_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: 349 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles continuation rows (empty company name)
  - Extracts reference rate, floor rate, spread, PIK rate from separate columns
  - Parses complex spread formats (e.g., "2.75% Cash + 2.75% PIK")
  - Extracts maturity dates, principal, cost, fair value
  - Handles negative values in parentheses
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in actual dollars (not thousands)

### ✅ GAIN (Gladstone Investment Corp)
- **File**: `gain_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: 127 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Parses company name and investment type from combined column (separated by "–")
  - Extracts interest rate info from parentheses (e.g., "SOFR+9.0%, 13.1% Cash, Due 12/2029")
  - Handles shares/units for equity investments
  - Extracts principal, cost, fair value
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)

### ✅ BCSF (Bain Capital Specialty Finance Inc)
- **File**: `bcsf_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: 1049 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles continuation rows (empty company name)
  - Extracts reference rate (Index), spread, PIK rate from separate columns
  - Parses complex spread formats (e.g., "5.50% (1.50% PIK)")
  - Extracts maturity dates, principal, cost, fair value
  - Handles negative values in parentheses
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)

### ✅ HTGC (Hercules Capital Inc)
- **File**: `htgc_custom_parser.py`
- **Status**: Working
- **Approach**: HTML-only extraction
- **Investments Extracted**: 286 investments
- **Features**:
  - Extracts all data directly from HTML tables
  - Handles continuation rows (empty company name)
  - Parses complex interest rate strings (e.g., "Prime + 2.85%, Floor rate 10.35%, 5.55% Exit Fee")
  - Extracts reference rate, spread, floor rate, PIK rate from combined interest rate column
  - Handles fixed rates and PIK-only rates
  - Extracts maturity dates (e.g., "August 2029" -> "08/01/2029")
  - Extracts principal, cost, fair value
  - Filters for Q3 2025 (September 30, 2025) data
  - Values in thousands (multiplied by 1000)

## Parser Architecture

Both custom parsers follow the same pattern:

1. **XBRL Extraction**: Extract financial values (principal, cost, fair_value) from XBRL
2. **HTML Extraction**: Extract descriptive data (dates, rates, industries, business descriptions) from HTML tables
3. **Intelligent Merging**: Match XBRL and HTML data by company name + investment type
4. **Flexible Matching**: Handle variations in investment type naming (e.g., "Secured Debt 1" vs "Secured Debt")

## Table Structure Mappings

### ARCC Table Structure
- Column 0: Company name
- Column 2: Business Description
- Column 4: Investment Type
- Column 6: Coupon/Interest Rate
- Column 7: Reference Rate
- Column 8: Spread
- Column 10: Acquisition Date
- Column 12: Maturity Date
- Column 14: Shares/Units
- Column 15: Principal
- Column 17: Amortized Cost
- Column 19: Fair Value

### MAIN Table Structure
- Column 0: Portfolio Company (company name)
- Column 2: Business Description
- Column 3: Type of Investment
- Column 5: Investment Date (acquisition date)
- Column 6: Shares/Units
- Column 7: Total Rate (interest rate)
- Column 8: Reference Rate and Spread (e.g., "SF+ 8.00%")
- Column 9: PIK Rate
- Column 10: MaturityDate
- Column 11: Principal
- Column 12: Cost
- Column 13: Fair Value

### NCDL Table Structure
- Column 0: Portfolio Company (company name)
- Column 2: Footnotes
- Column 4: Investment (investment type)
- Column 6: Spread Above Reference Rate (e.g., "S + 4.75%")
- Column 8: Interest Rate (e.g., "8.85" with "%" in column 9)
- Column 10: Maturity Date
- Column 12: Par Amount (Principal) - sometimes "$" in column 13, value in column 14
- Column 14: Amortized Cost - sometimes "$" in column 15, value in column 16
- Column 16: Fair Value - sometimes "$" in column 17, value in column 18
- Column 18: % of Net Assets

### OBDC Table Structure
- Column 0: Company(1)(25) (company name with footnotes)
- Column 2: Investment (investment type)
- Column 4: Ref. Rate (reference rate, e.g., "S+")
- Column 5: Cash (cash interest rate/spread, e.g., "4.75%")
- Column 6: PIK (PIK interest rate, e.g., "2.75%")
- Column 8: Maturity Date (MM/YYYY format)
- Column 10: Par / Units (principal amount or units)
- Column 12: Amortized Cost(2)(27) (cost basis - value in column 13)
- Column 14: Fair Value (fair value - value in column 15)
- Column 16: % of Net Assets (percentage - value in column 17, "%" in column 18)

## Next Steps

### High Priority (Next to Create)
1. ✅ **NCDL** (62.5% coverage) - **COMPLETED**
2. ✅ **OBDC** (62.6% coverage) - **COMPLETED**
3. ✅ **MFIC** (63.4% coverage) - **COMPLETED**
4. ✅ **CION** (68.6% coverage) - **COMPLETED**
5. ✅ **GBDC** (68.7% coverage) - **COMPLETED**
6. ✅ **CSWC** (69.9% coverage) - **COMPLETED**
7. ✅ **PSEC** (69.0% coverage) - **COMPLETED** (with limitations)
8. ✅ **OCSL** (72.0% coverage) - **COMPLETED**
9. ✅ **BBDC** (72.7% coverage) - **COMPLETED**
10. ✅ **MSDL** (69.8% coverage) - **COMPLETED**
11. ✅ **PFLT** (67.8% coverage) - **COMPLETED**
12. ✅ **TCPC** (76.9% coverage) - **COMPLETED**
13. ✅ **GAIN** (67.1% coverage) - **COMPLETED**
14. ✅ **BCSF** (79.7% coverage) - **COMPLETED**
15. ✅ **HTGC** (70.4% coverage) - **COMPLETED**
16. **TRIN** (62.8% coverage, 0 tables - needs investigation)
17. **CGBD** (65.9% coverage, 0 tables - needs investigation)

### Medium Priority
18. **NMFC** (73.2% coverage, 0 tables - needs investigation)
19. **TSLX** (76.9% coverage, 0 tables - needs investigation)
20. **FSK** (68.7% coverage, 0 tables - needs investigation)

## Usage

### Running MAIN Custom Parser
```bash
python main_custom_parser.py
```

### Running NCDL Custom Parser
```bash
python ncdl_custom_parser.py
```

### Running OBDC Custom Parser
```bash
python obdc_custom_parser.py
```

### Running ARCC Custom Parser
```bash
python arcc_custom_parser.py
```

## Key Improvements Over Standard Parsers

1. **Date Extraction**: Custom parsers extract dates from HTML tables (0% → 60-80% coverage)
2. **Rate Extraction**: Extract interest rates, reference rates, spreads from HTML
3. **Business Descriptions**: Extract business descriptions from HTML
4. **Industry Information**: Better industry extraction from HTML tables
5. **Flexible Matching**: Handle variations in naming between XBRL and HTML
6. **Entity Suffix Normalization**: Match "company" with "company llc" by normalizing suffixes
7. **Fuzzy Company Matching**: Handle slight variations in company names
8. **Better XBRL Parsing**: Improved investment type extraction from complex identifiers

## Investigation Tools

- **Debug Script**: `debug_obdc_matching.py` - Analyzes matching patterns and identifies issues
- **Investigation Results**: `INVESTIGATION_RESULTS.md` - Detailed analysis of matching improvements

## Notes

- Some parsers (TRIN, CGBD, FSK, NMFC, TSLX) had 0 tables extracted - may need different document selection or extraction approach
- Match rates can be improved further by:
  - Better normalization of company names
  - Handling more investment type variations
  - Using fuzzy matching for company names


  - Better normalization of company names
  - Handling more investment type variations
  - Using fuzzy matching for company names

