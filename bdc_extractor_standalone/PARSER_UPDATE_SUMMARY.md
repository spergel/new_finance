# Parser Update Summary

## Completed Updates

### Core Infrastructure
1. **`xbrl_typed_extractor.py`** - Enhanced `_build_investment` method to extract:
   - maturity_date
   - acquisition_date
   - interest_rate
   - reference_rate (SOFR, LIBOR, PRIME, etc.)
   - spread
   - floor_rate
   - pik_rate

### Directly Updated Parsers
1. **BCSF** - Enhanced fact extraction
2. **FDUS** - Enhanced fact extraction
3. **TRIN** - Enhanced fact extraction (fixed URL issue)
4. **ARCC** - Switched from HTML to XBRL extraction
5. **CSWC** - Switched from HTML to XBRL extraction
6. **GLAD** - Enhanced fact extraction
7. **MRCC** - Enhanced fact extraction
8. **MSIF** - Enhanced fact extraction
9. **OXSQ** - Enhanced fact extraction
10. **OFS** - Enhanced fact extraction
11. **PFX** - Enhanced fact extraction
12. **RAND** - Enhanced fact extraction
13. **TPVG** - Enhanced fact extraction
14. **WHF** - Enhanced fact extraction

### Automatically Updated (via `xbrl_typed_extractor`)
- **MAIN** - Uses `TypedMemberExtractor`
- **GBDC** - Uses `TypedMemberExtractor`
- **CGBD** - Uses `TypedMemberExtractor`
- **OBDC** - Uses `TypedMemberExtractor`
- **PSEC** - Uses `TypedMemberExtractor`
- **NCDL** - Uses `TypedMemberExtractor`
- **NMFC** - Uses `TypedMemberExtractor`
- **OCSL** - Uses `TypedMemberExtractor`
- **MSDL** - Uses `TypedMemberExtractor` (already extracts from identifier strings)
- **FSK** - Uses `TypedMemberExtractor`

### Special Cases
- **SCM** - Uses HTML tables with XBRL fallback (may need separate update)

## Key Improvements

1. **Enhanced Fact Extraction**: All parsers now extract maturity dates, interest rates, spreads, reference rates, floor rates, and PIK rates from XBRL facts
2. **URL Filtering**: Fixed issue where interest_rate fields were capturing URLs instead of percentages
3. **Reference Rate Detection**: Automatically detects SOFR, LIBOR, PRIME, SONIA, EURIBOR from XBRL facts
4. **Percentage Formatting**: Properly formats rates (0-1 range converted to percentages, e.g., 0.0929 → 9.29%)

## Testing

Run `test_all_parsers.py` to verify all parsers are working correctly.

