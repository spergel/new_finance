# Problematic Parsers Analysis

This document identifies BDC parsers with the most extraction issues and prioritizes them for custom parser development.

## Priority Ranking (by Coverage %)

### Tier 1: Critical Issues (< 65% coverage)

| Ticker | Company Name | Coverage | Key Missing Fields | Priority |
|--------|--------------|----------|-------------------|----------|
| **MAIN** | Main Street Capital Corp | 51.7% | industry (11.8%), principal_amount (33.0%), interest_rate (37.8%), acquisition_date (0%), maturity_date (0%) | 🔴 HIGHEST |
| **NCDL** | Nuveen Churchill Direct Lending Corp | 62.5% | investment_type (74.6%), interest_rate (0%), acquisition_date (0%), maturity_date (0%) | 🔴 HIGH |
| **OBDC** | Blue Owl Capital Corp | 62.6% | investment_type (97.8%), interest_rate (13.8%), acquisition_date (0%), maturity_date (0%) | 🔴 HIGH |
| **TRIN** | Trinity Capital Inc | 62.8% | principal_amount (42.6%), interest_rate (38.3%), acquisition_date (0%), maturity_date (0%) | 🔴 HIGH |
| **MFIC** | Midcap Financial Investment Corp | 63.4% | investment_type (65.0%), principal_amount (38.0%), interest_rate (45.6%), acquisition_date (0%) | 🔴 HIGH |
| **CGBD** | TCG BDC Inc | 65.9% | cost (71.1%), principal_amount (60.6%), interest_rate (62.2%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM-HIGH |

### Tier 2: Significant Issues (65-70% coverage)

| Ticker | Company Name | Coverage | Key Missing Fields | Priority |
|--------|--------------|----------|-------------------|----------|
| **CION** | CION Investment Corp | 68.6% | cost (76.4%), principal_amount (60.9%), interest_rate (57.4%), acquisition_date (0%) | 🟡 MEDIUM |
| **GBDC** | Golub Capital BDC Inc | 68.7% | principal_amount (59.8%), interest_rate (62.2%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM |
| **FSK** | FS KKR Capital Corp | 68.7% | cost (85.1%), principal_amount (72.9%), interest_rate (67.0%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM |
| **CSWC** | Capital Southwest Corp | 69.9% | principal_amount (69.5%), interest_rate (63.1%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM |
| **MSDL** | Morgan Stanley Direct Lending Fund | 69.8% | investment_type (94.8%), cost (81.1%), principal_amount (76.1%), interest_rate (76.3%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM |
| **PSEC** | Prospect Capital Corp | 69.0% | investment_type (95.5%), cost (86.8%), principal_amount (66.7%), interest_rate (72.2%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM |
| **PFLT** | PennantPark Floating Rate Capital Ltd | 67.8% | investment_type (93.4%), principal_amount (73.6%), interest_rate (61.6%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM |
| **GAIN** | Gladstone Investment Corp | 67.1% | investment_type (91.1%), principal_amount (56.8%), interest_rate (56.8%), acquisition_date (0%), maturity_date (0%) | 🟡 MEDIUM |

### Tier 3: Moderate Issues (70-80% coverage)

| Ticker | Company Name | Coverage | Key Missing Fields | Priority |
|--------|--------------|----------|-------------------|----------|
| **HTGC** | Hercules Capital Inc | 70.4% | fair_value (48.7%), interest_rate (2.9%), acquisition_date (0%) | 🟢 LOW-MEDIUM |
| **OCSL** | Oaktree Specialty Lending Corp | 72.0% | industry (92.1%), principal_amount (86.6%), interest_rate (69.5%), acquisition_date (0%), maturity_date (0%) | 🟢 LOW-MEDIUM |
| **BBDC** | Barings BDC Inc | 72.7% | principal_amount (77.2%), interest_rate (78.9%), acquisition_date (0%), maturity_date (0%) | 🟢 LOW-MEDIUM |
| **NMFC** | New Mountain Finance Corp | 73.2% | interest_rate (69.2%), acquisition_date (0%), maturity_date (0%) | 🟢 LOW-MEDIUM |
| **FDUS** | Fidus Investment Corp | 76.0% | investment_type (83.5%), principal_amount (39.7%), interest_rate (41.7%), maturity_date (42.3%) | 🟢 LOW-MEDIUM |
| **TSLX** | Sixth Street Specialty Lending Inc | 76.9% | investment_type (62.7%), principal_amount (0%), interest_rate (70.3%), maturity_date (68.6%) | 🟢 LOW-MEDIUM |
| **TCPC** | Blackrock TCP Capital Corp | 76.9% | investment_type (52.5%), maturity_date (80.1%) | 🟢 LOW-MEDIUM |
| **BCSF** | Bain Capital Specialty Finance Inc | 79.7% | investment_type (98.9%), interest_rate (66.4%), acquisition_date (0%) | 🟢 LOW |

## Common Issues Across All Parsers

### 1. Missing Dates (Most Critical)
- **acquisition_date**: Missing for 20+ parsers (0% coverage)
- **maturity_date**: Missing for 15+ parsers (0% coverage)
- **Solution**: Extract from HTML tables (like ARCC custom parser)

### 2. Missing Interest Rates
- Many parsers have 0-60% coverage for interest_rate
- **Solution**: Extract from HTML tables, often in "Coupon/Interest Rate" column

### 3. Missing Investment Types
- Some parsers (MAIN, MFIC, TSLX, TCPC) have low investment_type coverage
- **Solution**: Better HTML table parsing or XBRL concept matching

### 4. Missing Principal Amounts
- Several parsers have 30-60% coverage for principal_amount
- **Solution**: Better monetary value extraction from HTML tables

## Recommended Approach

Based on the ARCC custom parser success, we should:

1. **Extract HTML Tables**: Use `extract_problematic_parser_tables.py` to get all tables
2. **Analyze Structure**: Review table structures to understand column mappings
3. **Create Custom Parsers**: Build parsers that:
   - Extract from XBRL for financial values (principal, cost, fair_value)
   - Extract from HTML tables for dates, rates, industries, business descriptions
   - Merge data intelligently (like ARCC custom parser)

## Next Steps

1. ✅ Created `extract_problematic_parser_tables.py` to extract all tables
2. ⏳ Run extraction script to get tables for analysis
3. ⏳ Analyze table structures for top 5-10 parsers
4. ⏳ Create custom parsers starting with Tier 1 (highest priority)

## Reference

- ARCC Custom Parser: `arcc_custom_parser.py` (successful example)
- Test Results: `PARSER_TEST_RESULTS.md`
- Field Status: `FIELD_EXTRACTION_STATUS.md`

