# Potential Additional Fields for BDC Investment Extraction

This document identifies additional fields that could be valuable to extract from BDC SEC filings.

## High Value Fields (Commonly Available)

### 1. **Credit Rating** (`credit_rating`)
- **Description**: Credit rating assigned by rating agencies (S&P, Moody's, Fitch)
- **Examples**: "B+", "BB-", "CCC", "NR" (Not Rated)
- **Availability**: Some BDCs include in investment tables or separate rating summary
- **Feasibility**: Medium - appears in some filings, not all
- **Use Case**: Credit quality assessment, risk analysis
- **Extraction**: HTML column or footnote parsing

### 2. **Payment Status** (`payment_status` / `non_accrual`)
- **Description**: Whether investment is performing or on non-accrual
- **Examples**: "Performing", "Non-Accrual", "Default", "Restructured"
- **Availability**: Some BDCs have separate non-performing investment tables
- **Feasibility**: Medium - not consistently reported in main tables
- **Use Case**: Credit quality tracking, early warning indicators
- **Extraction**: Separate table parsing or footnote analysis

### 3. **Geographic Location** (`geographic_location` / `location`)
- **Description**: Geographic location of portfolio company
- **Examples**: "United States", "Europe", "Asia-Pacific", "California"
- **Availability**: Sometimes in business description or separate column
- **Feasibility**: Medium-High - can often be inferred from business description
- **Use Case**: Geographic diversification analysis, regional risk assessment
- **Extraction**: HTML column or parse from business_description

### 4. **Call Provisions** (`call_date`, `call_price`, `callable`)
- **Description**: Callable investment terms (dates, prices)
- **Examples**: "2025-06-15", "Par + 1%", "Yes/No"
- **Availability**: Sometimes in investment tables or footnotes
- **Feasibility**: Low-Medium - often in footnotes, not always in tables
- **Use Case**: Investment duration analysis, prepayment risk
- **Extraction**: HTML column or footnote parsing

### 5. **Conversion Terms** (`conversion_price`, `conversion_ratio`, `conversion_date`)
- **Description**: Terms for convertible investments
- **Examples**: "$10.00", "1:1", "2026-12-31"
- **Availability**: Sometimes in investment tables for convertible investments
- **Feasibility**: Low-Medium - only for convertible investments
- **Use Case**: Equity upside analysis, conversion risk
- **Extraction**: HTML column or footnote parsing

## Medium Value Fields (Less Commonly Available)

### 6. **Warrant Details** (`warrant_strike_price`, `warrant_expiration`, `warrant_shares`)
- **Description**: Warrant terms (strike price, expiration, number of shares)
- **Examples**: "$5.00", "2027-01-01", "100,000"
- **Availability**: Sometimes in investment tables or footnotes
- **Feasibility**: Low - only for investments with warrants
- **Use Case**: Equity upside analysis, warrant valuation
- **Extraction**: HTML column or footnote parsing

### 7. **Dividend Rate** (`dividend_rate`)
- **Description**: Dividend rate for preferred equity investments
- **Examples**: "8%", "Fixed 6%", "Variable"
- **Availability**: Sometimes in investment tables for equity investments
- **Feasibility**: Low-Medium - only for equity investments
- **Use Case**: Yield analysis for equity investments
- **Extraction**: HTML column (might overlap with interest_rate)

### 8. **Collateral Type** (`collateral_type`)
- **Description**: Type of collateral backing the investment
- **Examples**: "First Lien", "Second Lien", "Unsecured", "Real Estate", "Assets"
- **Availability**: Sometimes in investment_type or separate column
- **Feasibility**: Medium - often embedded in investment_type
- **Use Case**: Security analysis, recovery rate estimation
- **Extraction**: Parse from investment_type or HTML column

### 9. **PIK Toggle** (`pik_toggle`, `pik_optional`)
- **Description**: Whether PIK can be toggled on/off
- **Examples**: "Yes", "No", "Optional"
- **Availability**: Rarely in tables, sometimes in footnotes
- **Feasibility**: Low - rarely reported
- **Use Case**: Cash flow analysis, PIK risk assessment
- **Extraction**: Footnote parsing

### 10. **Covenants** (`financial_covenants`, `covenant_compliance`)
- **Description**: Financial covenants and compliance status
- **Examples**: "Leverage < 4.0x", "In Compliance", "Covenant Waiver"
- **Availability**: Rarely in tables, often in footnotes or MD&A
- **Feasibility**: Low - complex to extract, often in narrative text
- **Use Case**: Credit quality assessment, early warning indicators
- **Extraction**: Advanced NLP on footnotes/MD&A

## Lower Priority Fields (Rarely Available)

### 11. **Default Status** (`default_status`, `in_default`)
- **Description**: Whether investment is in default
- **Examples**: "Yes", "No", "Technical Default"
- **Availability**: Usually in separate non-performing table
- **Feasibility**: Medium - if non-performing table exists
- **Use Case**: Credit quality tracking
- **Extraction**: Separate table parsing

### 12. **Restructuring Status** (`restructured`, `restructuring_date`)
- **Description**: Whether investment has been restructured
- **Examples**: "Yes", "No", "2024-03-15"
- **Availability**: Rarely in tables, sometimes in footnotes
- **Feasibility**: Low - rarely reported
- **Use Case**: Historical analysis, credit quality tracking
- **Extraction**: Footnote parsing or separate table

### 13. **Portfolio Company Revenue/EBITDA** (`portfolio_company_revenue`, `portfolio_company_ebitda`)
- **Description**: Financial metrics of portfolio company
- **Examples**: "$50M", "$10M"
- **Availability**: Rarely in investment tables, sometimes in separate tables
- **Feasibility**: Low - rarely in investment schedule
- **Use Case**: Credit analysis, leverage calculations
- **Extraction**: Separate table parsing

### 14. **Leverage Ratio** (`leverage_ratio`, `debt_to_ebitda`)
- **Description**: Portfolio company leverage metrics
- **Examples**: "4.5x", "3.2x EBITDA"
- **Availability**: Rarely in investment tables
- **Feasibility**: Low - rarely reported
- **Use Case**: Credit analysis, risk assessment
- **Extraction**: Separate table or footnote parsing

## Recommended Next Steps

### Phase 1: High Value, High Feasibility
1. **Geographic Location** - Can often be extracted from business_description or added as HTML column
2. **Credit Rating** - Add to FlexibleTableParser column keywords, extract from HTML when available

### Phase 2: High Value, Medium Feasibility
3. **Payment Status** - Parse from separate non-performing investment tables
4. **Call Provisions** - Extract from HTML columns or footnotes when available

### Phase 3: Medium Value
5. **Collateral Type** - Parse from investment_type or extract as separate field
6. **Conversion Terms** - Extract for convertible investments
7. **Warrant Details** - Extract for investments with warrants

## Implementation Notes

- Most of these fields would require:
  - Adding to `FlexibleTableParser.COLUMN_KEYWORDS`
  - Adding to investment dataclasses
  - Adding to CSV output fieldnames
  - HTML fallback extraction (when available)
  - XBRL extraction (if available in XBRL tags)

- Some fields (like covenants, restructuring status) would require more advanced NLP techniques to extract from narrative text in footnotes or MD&A sections.


