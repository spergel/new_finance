# Table Extraction Results

## Summary

Successfully extracted **517 tables** from **22 problematic BDC parsers**.

## Extraction Results by Ticker

### ✅ Successfully Extracted (17 parsers)

| Ticker | Coverage | Tables | Status | Priority |
|--------|----------|--------|--------|----------|
| **MAIN** | 51.7% | **92** | ✅ Extracted | 🔴 HIGHEST |
| **GBDC** | 68.7% | **94** | ✅ Extracted | 🟡 MEDIUM |
| **OBDC** | 62.6% | **61** | ✅ Extracted | 🔴 HIGH |
| **BBDC** | 72.7% | **54** | ✅ Extracted | 🟢 LOW-MEDIUM |
| **NCDL** | 62.5% | **51** | ✅ Extracted | 🔴 HIGH |
| **PSEC** | 69.0% | **39** | ✅ Extracted | 🟡 MEDIUM |
| **HTGC** | 70.4% | **33** | ✅ Extracted | 🟢 LOW-MEDIUM |
| **OCSL** | 72.0% | **27** | ✅ Extracted | 🟢 LOW-MEDIUM |
| **CION** | 68.6% | **25** | ✅ Extracted | 🟡 MEDIUM |
| **CSWC** | 69.9% | **7** | ✅ Extracted | 🟡 MEDIUM |
| **BCSF** | 79.7% | **6** | ✅ Extracted | 🟢 LOW |
| **MFIC** | 63.4% | **5** | ✅ Extracted | 🔴 HIGH |
| **TCPC** | 76.9% | **5** | ✅ Extracted | 🟢 LOW-MEDIUM |
| **PFLT** | 67.8% | **4** | ✅ Extracted | 🟡 MEDIUM |
| **GAIN** | 67.1% | **8** | ✅ Extracted | 🟡 MEDIUM |
| **MSDL** | 69.8% | **3** | ✅ Extracted | 🟡 MEDIUM |
| **FDUS** | 76.0% | **3** | ✅ Extracted | 🟢 LOW-MEDIUM |

### ⚠️ No Tables Found (5 parsers)

These parsers may need different extraction approaches:

| Ticker | Coverage | Tables | Issue | Next Steps |
|--------|----------|--------|-------|------------|
| **TRIN** | 62.8% | 0 | Wrong HTML document selected | Check for alternative documents |
| **CGBD** | 65.9% | 0 | Wrong HTML document selected | Check for alternative documents |
| **FSK** | 68.7% | 0 | Wrong HTML document selected | Check for alternative documents |
| **NMFC** | 73.2% | 0 | Wrong HTML document selected | Check for alternative documents |
| **TSLX** | 76.9% | 0 | Wrong HTML document selected | Check for alternative documents |

## Recommended Next Steps

### Phase 1: High Priority Parsers (Start Here)

1. **MAIN** (51.7% coverage, 92 tables) - **HIGHEST PRIORITY**
   - Worst coverage overall
   - Most tables extracted
   - Missing: industry (11.8%), dates (0%), interest rates (37.8%)

2. **NCDL** (62.5% coverage, 51 tables) - **HIGH PRIORITY**
   - Missing: investment_type (74.6%), dates (0%), interest_rate (0%)

3. **OBDC** (62.6% coverage, 61 tables) - **HIGH PRIORITY**
   - Missing: interest_rate (13.8%), dates (0%)

4. **MFIC** (63.4% coverage, 5 tables) - **HIGH PRIORITY**
   - Missing: investment_type (65.0%), dates (0%), principal_amount (38.0%)

5. **TRIN** (62.8% coverage, 0 tables) - **NEEDS INVESTIGATION**
   - No tables found - may need to check alternative documents

### Phase 2: Medium Priority Parsers

6. **CGBD** (65.9% coverage, 0 tables) - **NEEDS INVESTIGATION**
7. **CION** (68.6% coverage, 25 tables)
8. **GBDC** (68.7% coverage, 94 tables)
9. **CSWC** (69.9% coverage, 7 tables)
10. **MSDL** (69.8% coverage, 3 tables)

## Table Locations

All extracted tables are saved in:
```
bdc_extractor_standalone/output/{ticker}_tables/
```

Each directory contains:
- `{ticker}_table_1.html` through `{ticker}_table_N.html`
- Simplified HTML format (attributes removed, IX tags unwrapped)

## Analysis Workflow

For each parser, follow this process:

1. **Review Tables**: Open a few tables in a browser to understand structure
2. **Identify Columns**: Map HTML columns to data fields:
   - Company name
   - Business description
   - Investment type
   - Interest rate / Coupon
   - Reference rate
   - Spread
   - Acquisition date
   - Maturity date
   - Principal amount
   - Cost basis
   - Fair value
3. **Create Custom Parser**: Similar to `arcc_custom_parser.py`:
   - Extract from XBRL for financial values
   - Extract from HTML tables for dates, rates, descriptions
   - Merge intelligently
4. **Test**: Run parser and verify coverage improvement

## Reference

- ARCC Custom Parser: `arcc_custom_parser.py` (working example)
- Extraction Script: `extract_problematic_parser_tables.py`
- Analysis Doc: `PROBLEMATIC_PARSERS_ANALYSIS.md`

