# Changelog

## 2025-10-10 - Major Refactor & Cleanup

### Added
- **XBRL Extraction Module** (`core/xbrl_preferred_shares_extractor.py`)
  - Regex-based extraction from 10-Q filings
  - Extracts: dividend rate, shares, par value, cumulative status, voting rights
  - Handles multi-letter series (e.g., RR, TT)

- **Filing Matcher** (`core/filing_matcher.py`)
  - Intelligent matching of 424B filings to securities
  - Cross-references series names from 10-Q with 424B content
  - Confidence scoring based on mention frequency

- **Data Fusion Module** (`core/data_fusion.py`)
  - Combines XBRL (10-Q) and LLM (424B) extractions
  - XBRL = source of truth for current financial terms
  - LLM = detailed narrative features

- **Enhanced LLM Extraction**
  - Comprehensive preferred share features
  - Rate reset terms, depositary shares, special redemption events
  - Voting rights, protective provisions, dividend stoppers

- **Documentation**
  - `docs/ARCHITECTURE.md` - System design and data flow
  - `docs/FEATURES.md` - Complete feature list
  - `docs/USAGE.md` - User guide with examples
  - `PROJECT_STRUCTURE.md` - Repository structure

### Changed
- **Enhanced SEC API Client** (`core/sec_api_client.py`)
  - Added `get_all_424b_filings()` for fetching all 424B variants
  - Added `get_filing_by_accession()` for historical filing retrieval

- **Updated Models** (`core/models.py`)
  - Added `EnhancedPreferredShareFeatures`
  - Added rate reset terms, governance features, special provisions

- **Reorganized File Structure**
  - Moved all outputs to `output/` subdirectories
  - Created `scripts/` for utility scripts
  - Removed individual ticker directories from root
  - Consolidated documentation from 17 to 5 files

### Removed
- Individual ticker directories (JXN/, BAC/, C/, etc.) - moved to output/
- 15 redundant documentation files - consolidated into 3 comprehensive guides
- Old extraction scripts - moved to scripts/

### Fixed
- XBRL dividend rate extraction (now handles newlines and varied spacing)
- Multi-letter series filtering (now allows series like RR, TT)
- 424B filing matching (now uses accession numbers for historical filings)
- Data fusion series matching (handles both 'series' and 'series_name' keys)
- Unicode encoding issues in terminal output

## Repository Statistics

### Before Cleanup
- 17 markdown documentation files
- Scattered output files in individual ticker directories
- Scripts mixed with core modules

### After Cleanup
- 5 consolidated documentation files
- All outputs organized in `output/` subdirectories
- Clean separation: `core/`, `scripts/`, `docs/`, `output/`

### Current Structure
```
new_finance/
├── core/         # 19 files - Core extraction modules
├── scripts/      # 5 files  - Utility scripts
├── docs/         # 5 files  - Documentation
├── output/       # 38 files - Extraction outputs
├── data/         # 3 files  - Sample data
└── Root files    # 8 files  - Main project files
```

## Testing Performed

### Functionality Tests
- ✅ XBRL extraction across multiple companies (JXN, C, BAC, PSA)
- ✅ Filing matcher with various preferred share types
- ✅ LLM extraction with complex terms
- ✅ Data fusion combining XBRL and LLM sources

### Accuracy Tests
- ✅ JXN Series A data validation
- ✅ Citigroup multi-series extraction
- ✅ Bank of America multi-letter series
- ✅ Dividend rate reasonableness checks

### Error Handling Tests
- ✅ Missing 424B filings (old preferreds)
- ✅ Malformed HTML/XBRL
- ✅ API timeouts
- ✅ Empty/null values

## Performance

**Typical Extraction Times:**
- XBRL extraction: 10-30 seconds
- Filing matching: 5-15 seconds
- LLM extraction: 10-20 seconds per filing
- Total (with 1-2 424B filings): 30-80 seconds

## Breaking Changes

None - This is the first major release.

## Migration Guide

If you were using previous versions:

1. **Output Files:** Now in `output/fused/` instead of `{TICKER}/`
2. **Scripts:** Now in `scripts/` instead of root
3. **Documentation:** Consolidated - see `docs/README.md`
4. **Main Entry Point:** Use `scripts/run_fusion.py` for complete extraction

## Future Plans

See `docs/TODO.md` for development roadmap.

Key priorities:
- Caching layer for SEC filings
- Batch processing improvements
- Web UI for extraction
- Real-time monitoring for new filings
- Support for other security types (bonds, warrants)

