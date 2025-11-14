# Field Extraction Status

This document tracks the status of additional field extraction for BDC investments.

## ✅ Fully Implemented Fields

### 1. `shares_units` - Shares/Units for Equity Investments
- **Status**: ✅ Fully Implemented
- **Extraction Method**: 
  - HTML tables: `FlexibleTableParser` extracts from columns with keywords: 'shares/units', 'shares', 'units', 'quantity'
  - XBRL: Extracts from facts with concepts containing: 'numberofshares', 'sharesoutstanding', 'unitsoutstanding', 'sharesheld', 'unitsheld'
- **CSV Output**: ✅ Added to fieldnames
- **Parsers Updated**: BCSF, TCPC, FDUS, FlexibleTableParser
- **Use Case**: Useful for equity investments (common stock, preferred equity, warrants) to track number of shares/units owned

### 2. `percent_net_assets` - Portfolio Weight
- **Status**: ✅ HTML Implemented, XBRL Calculation Pending
- **Extraction Method**:
  - HTML tables: `FlexibleTableParser` extracts from columns with keywords: '% of net assets', 'percent of net assets', '%', 'net assets'
  - XBRL: Not yet implemented (would need to calculate from fair_value / total_net_assets per period)
- **CSV Output**: ✅ Added to fieldnames
- **Parsers Updated**: BCSF, TCPC, FDUS, FlexibleTableParser
- **Use Case**: Shows what percentage of the BDC's portfolio each investment represents

### 3. `currency` - Investment Currency
- **Status**: ✅ Fully Implemented
- **Extraction Method**:
  - HTML tables: `FlexibleTableParser` extracts from columns with keywords: 'currency', 'curr', 'ccy'
  - XBRL: Extracts from `unitRef` attribute on facts (e.g., `unitRef="USD"` or `unitRef="U-S-D"`)
- **CSV Output**: ✅ Added to fieldnames
- **Parsers Updated**: BCSF, TCPC, FDUS, FlexibleTableParser
- **Use Case**: Important for foreign investments to track currency exposure

### 4. `commitment_limit` and `undrawn_commitment` - Revolving Credit Commitments
- **Status**: ✅ Partially Implemented
- **Extraction Method**:
  - HTML tables: `FlexibleTableParser` extracts from columns with keywords: 'commitment', 'commitment limit', 'undrawn', 'unfunded'
  - XBRL: Heuristic extraction for revolvers:
    - If `fair_value` exists but no `principal_amount`: `commitment_limit = fair_value`, `undrawn_commitment = fair_value`
    - If both exist: `commitment_limit = fair_value`, `undrawn_commitment = fair_value - principal_amount`
  - Some parsers (BXSL, CSWC, OBDC, GBDC, CION, MAIN) have custom extraction logic
- **CSV Output**: ✅ Already in fieldnames
- **Parsers Updated**: BCSF, TCPC, FDUS, FlexibleTableParser
- **Coverage**: Extracted by ~9 parsers, needs to be added to remaining parsers
- **Use Case**: For revolving credit facilities, shows total commitment and available undrawn amount

## 🔄 Fields to Investigate

### 5. `credit_rating` - Credit Rating
- **Status**: ⚠️ Not Implemented
- **Feasibility**: Low-Medium
- **Potential Sources**:
  - HTML tables: Separate rating column (rare)
  - Footnotes: May be mentioned in investment footnotes
  - Separate tables: Some BDCs have rating summary tables
- **Use Case**: Credit quality indicator for debt investments
- **Next Steps**: Sample a few filings to see if ratings are consistently reported

### 6. `payment_status` - Performing vs Non-Performing
- **Status**: ⚠️ Not Implemented
- **Feasibility**: Low
- **Potential Sources**:
  - HTML tables: Status column (rare)
  - Footnotes: May mention if investment is on non-accrual
  - Separate tables: Some BDCs have non-performing investment tables
- **Use Case**: Track credit quality and potential defaults
- **Next Steps**: Check if BDCs consistently report this information

## Implementation Details

### FlexibleTableParser Updates
- Added `shares_units`, `percent_net_assets`, `currency`, `commitment_limit`, `undrawn_commitment` to `COLUMN_KEYWORDS`
- Added extraction logic in `_parse_data_row()` method
- Fields are cleaned and validated before being added to investment dictionary

### XBRL Parser Updates (BCSF, TCPC, FDUS)
- Updated `_extract_facts()` to capture `unitRef` attribute for currency extraction
- Updated `_build_investment()` to extract:
  - `shares_units` from share-related XBRL concepts
  - `currency` from fact metadata (set by `_extract_facts`)
  - `commitment_limit` and `undrawn_commitment` using heuristics for revolvers
- Updated investment dataclasses to include new fields
- Updated return dictionaries to include new fields

### CSV Output Updates
- `historical_investment_extractor.py`: Added fields to CSV fieldnames
- `scripts/generate_static_data.py`: Added fields to CSV fieldnames and `_to_plain()` fallback

### Next Steps
1. **Apply to More Parsers**: Add same extraction logic to remaining XBRL parsers (CSWC, CGBD, OBDC, GBDC, PSEC, CION, OCSL, etc.)
2. **Percent of Net Assets Calculation**: Add XBRL calculation (fair_value / total_net_assets per period)
3. **Credit Rating**: Sample filings to assess feasibility
4. **Payment Status**: Sample filings to assess feasibility
5. **Testing**: Run full parser test to verify new fields are being extracted
