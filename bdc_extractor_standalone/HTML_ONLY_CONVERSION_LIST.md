# HTML-Only Conversion List

## Parsers to Convert from XBRL-First to HTML-Only

These parsers have **100% missing maturity dates** for debt investments and need to be converted to pure HTML extraction.

### High Priority (100% Missing Maturity Dates)

1. **GBDC** (Golub Capital BDC Inc) - 1,111/1,111 debt (100%)
   - File: `gbdc_parser.py`
   - Current: XBRL-first with HTML fallback
   - Action: Convert to HTML-only using FlexibleTableParser

2. **MSDL** (Morgan Stanley Direct Lending Fund) - 1,567/1,567 debt (100%)
   - File: `msdl_parser.py`
   - Current: XBRL-first with HTML fallback
   - Action: Convert to HTML-only using FlexibleTableParser

3. **NMFC** (New Mountain Finance Corp) - 1,343/1,343 debt (100%)
   - File: `nmfc_parser.py`
   - Current: XBRL-first with HTML fallback
   - Action: Convert to HTML-only using FlexibleTableParser

4. **OCSL** (Oaktree Specialty Lending Corp) - 970/970 debt (100%)
   - File: `ocsl_parser.py`
   - Current: XBRL-first with HTML fallback
   - Action: Convert to HTML-only using FlexibleTableParser

5. **OBDC** (Blue Owl Capital Corp) - 816/816 debt (100%)
   - File: `obdc_parser.py`
   - Current: XBRL-first with HTML fallback
   - Action: Convert to HTML-only using FlexibleTableParser

6. **CSWC** (Capital Southwest Corp) - ✅ **FIXED** - 50/53 debt (94.3%)
   - File: `cswc_custom_parser.py` (already has custom HTML parser)
   - Status: Maturity date extraction working - 94.3% coverage
   - Remaining: 3 debt investments missing maturity dates (likely not in HTML)

7. **CGBD** (TCG BDC Inc) - 664/664 debt (100%)
   - File: `cgbd_custom_parser.py` (already has custom HTML parser)
   - Current: Custom HTML parser exists
   - Action: Ensure it's being used (may need to update historical extractor)

8. **MAIN** (Main Street Capital Corp) - 493/493 debt (100%)
   - File: `main_custom_parser.py` (already has custom HTML parser)
   - Current: Custom HTML parser exists
   - Action: Ensure it's being used (may need to update historical extractor)

9. **PFLT** (PennantPark Floating Rate Capital Ltd) - 435/435 debt (100%)
   - File: `pflt_parser.py`
   - Current: XBRL-first with HTML fallback
   - Action: Convert to HTML-only using FlexibleTableParser

10. **PSEC** (Prospect Capital Corp) - 304/304 debt (100%)
    - File: `psec_parser.py`
    - Current: XBRL-first with HTML fallback
    - Action: Convert to HTML-only using FlexibleTableParser

11. **TRIN** (Trinity Capital Inc) - 47/47 debt (100%)
    - File: `trin_parser.py`
    - Current: XBRL-first (needs check)
    - Action: Convert to HTML-only using FlexibleTableParser

12. **FSK** (FS KKR Capital Corp) - 14/14 debt (100%)
    - File: `fsk_parser.py`
    - Current: XBRL-first with HTML fallback
    - Action: Convert to HTML-only using FlexibleTableParser

13. **NCDL** (Nuveen Churchill Direct Lending Corp) - 9/9 debt (100%)
    - File: `ncdl_parser.py`
    - Current: XBRL-first with HTML fallback
    - Action: Convert to HTML-only using FlexibleTableParser

## Conversion Strategy

For each parser:
1. Remove XBRL extraction logic (`_extract_typed_contexts`, `_extract_facts`, `_build_investment` from XBRL)
2. Replace `extract_from_url` to use HTML-only extraction via FlexibleTableParser
3. Keep company name normalization and matching logic
4. Ensure maturity dates are extracted from HTML tables
5. Test with recent filings to verify maturity date extraction

## Already HTML-First (No Conversion Needed)

- **MAIN**: `main_custom_parser.py` - Already HTML-first
- **CSWC**: `cswc_custom_parser.py` - Already HTML-first  
- **CGBD**: `cgbd_custom_parser.py` - Already HTML-first

## Status

### Custom Parsers (Auto-Prioritized by Historical Extractor)
- [x] **CSWC** - Uses `cswc_custom_parser.py` (CSWCCustomExtractor) - HTML-first
  - ✅ **Maturity Date Coverage: 94.3%** (50/53 debt investments)
  - Status: Working - 3 investments missing (likely not in HTML)
- [x] **CGBD** - Uses `cgbd_custom_parser.py` (CGBDCustomExtractor) - HTML-first
  - ✅ **Maturity Date Coverage: 100%** (387/387 debt investments)
  - Status: Fixed - Improved column mapping, XBRL tag extraction, and investment type inference
- [x] **MAIN** - Uses `main_custom_parser.py` (MAINCustomExtractor) - HTML-first
  - ✅ **Maturity Date Coverage: 100%** (160/160 debt investments)
  - Status: Fixed - Corrected investment type column (3 instead of 2) and improved date extraction
- [x] **GBDC** - Has `gbdc_custom_parser.py` (auto-prioritized) - Also converted `gbdc_parser.py` to HTML-only
  - ✅ **Maturity Date Coverage: 100%** (38/38 debt investments)
  - Status: Working perfectly
- [x] **OCSL** - Has `ocsl_custom_parser.py` (auto-prioritized)
  - ✅ **Maturity Date Coverage: 99.2%** (625/630 debt investments)
  - Status: Working well
- [x] **OBDC** - Has `obdc_custom_parser.py` (auto-prioritized)
  - ✅ **Maturity Date Coverage: 93.0%** (266/286 debt investments)
  - Status: Working well
- [x] **PSEC** - Has `psec_custom_parser.py` (auto-prioritized)
  - ✅ **Maturity Date Coverage: 99.2%** (251/253 debt investments)
  - Status: Working well
- [x] **MSDL** - Has `msdl_custom_parser.py` (auto-prioritized)
  - ✅ **Maturity Date Coverage: 99.5%** (661/664 debt investments)
  - Status: Improved - Extracts commitment expiration dates from company names
- [x] **PFLT** - Has `pflt_custom_parser.py` (auto-prioritized)
  - ✅ **Maturity Date Coverage: 98.7%** (462/468 debt investments)
  - Status: Improved - Extracts investment types and dates from company names
- [x] **NMFC** - Has `nmfc_custom_parser.py` (auto-prioritized)
  - ✅ **Maturity Date Coverage: 100%** (117/117 debt investments)
  - Status: Fixed - Now returns BDCExtractionResult instead of Dict
- [x] **TRIN** - Has `trin_custom_parser.py` (auto-prioritized)
- [x] **FSK** - Has `fsk_custom_parser.py` (auto-prioritized)
- [x] **NCDL** - Has `ncdl_custom_parser.py` (auto-prioritized)

### Regular Parsers Converted to HTML-Only
- [x] **GBDC** - `gbdc_parser.py` converted to HTML-only (uses FlexibleTableParser)
  - Note: Custom parser takes precedence, but regular parser is also HTML-only now

### Implementation Notes

1. **Custom Parser Priority**: The `historical_investment_extractor.py` now automatically checks for `{ticker}_custom_parser.py` first before falling back to `{ticker}_parser.py`. This means custom parsers are always used when they exist.

2. **Old XBRL Code**: ✅ **REMOVED** - All deprecated XBRL methods have been removed from `gbdc_parser.py`:
   - ~~`_extract_typed_contexts()`~~ - Removed
   - ~~`_extract_facts()`~~ - Removed
   - ~~`_build_investment()`~~ - Removed
   - ~~`_extract_html_fallback()`~~ - Removed
   - ~~`_merge_html_data()`~~ - Removed
   - ~~`_build_industry_index()`~~ - Removed
   - ~~`_industry_member_to_name()`~~ - Removed
   - ~~`_parse_gbdc_identifier()`~~ - Removed
   - ~~`_select_reporting_instant()`~~ - Removed
   - ~~Duplicate `_normalize_company_name()` and `_fuzzy_match_company_names()`~~ - Removed

3. **Testing**: ✅ **COMPLETE**
   - ✅ Custom parsers are automatically prioritized (verified)
   - ✅ All test tickers (CSWC, CGBD, MAIN, GBDC) use custom parsers
   - ✅ GBDC parser imports successfully after code removal
   - ✅ Historical extractor correctly loads custom parsers first

4. **Next Steps**: 
   - ✅ Tested CSWC, CGBD, MAIN, GBDC custom parsers
   - ⏳ Fix CGBD and MAIN maturity date extraction (currently 0%)
   - ⏳ Re-run batch extraction for all converted tickers to verify improved maturity date coverage

## Test Results (Latest - 2025-11-13)

### ✅ Working Parsers (≥90% coverage)
- **CGBD**: 100.0% maturity date coverage (387/387 debt investments) ✅ **FIXED**
- **GBDC**: 100.0% maturity date coverage (38/38 debt investments) ✅
- **MAIN**: 100.0% maturity date coverage (160/160 debt investments) ✅ **FIXED**
- **NMFC**: 100.0% maturity date coverage (117/117 debt investments) ✅ **FIXED**
- **MSDL**: 99.5% maturity date coverage (661/664 debt investments) ✅ **IMPROVED**
- **OCSL**: 99.2% maturity date coverage (625/630 debt investments) ✅
- **PSEC**: 99.2% maturity date coverage (251/253 debt investments) ✅
- **PFLT**: 98.7% maturity date coverage (462/468 debt investments) ✅ **IMPROVED**
- **CSWC**: 94.3% maturity date coverage (50/53 debt investments) ✅
- **OBDC**: 93.0% maturity date coverage (266/286 debt investments) ✅

### ⚠️ Needs Improvement (50-90% coverage)
- ~~**MSDL**: 80.7% maturity date coverage~~ ✅ **IMPROVED** - Now 99.5% (661/664 debt investments)
- ~~**PFLT**: 55.6% maturity date coverage~~ ✅ **IMPROVED** - Now 98.7% (462/468 debt investments)

### ❌ Needs Fixing (<50% coverage)
- ~~**CGBD**: 0% maturity date coverage~~ ✅ **FIXED** - Now 100% (387/387 debt investments)
- ~~**MAIN**: 0% maturity date coverage~~ ✅ **FIXED** - Now 100% (160/160 debt investments)

### ❌ Errors
- ~~**NMFC**: Parser error - 'dict' object has no attribute 'investments'~~ ✅ **FIXED** - Now returns BDCExtractionResult

