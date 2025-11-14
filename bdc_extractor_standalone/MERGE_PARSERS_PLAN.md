# Parser Merge Plan

## Current Situation

- **23 tickers** have both custom and regular parsers
- **Custom parsers are auto-prioritized** by `historical_investment_extractor.py`
- **Regular parsers are effectively unused** but may have improvements
- Recent improvements (PFLT, TRIN identifier parsing) are in regular parsers but custom parsers are what's used

## Strategy

### Option 1: Enhance Custom Parsers (Recommended)
1. Port identifier parsing improvements from regular parsers to custom parsers
2. For PFLT/TRIN: Add the `_parse_identifier` improvements to custom parsers
3. Test custom parsers have all functionality
4. Delete regular parsers once complete

### Option 2: Make Regular Parsers the Custom Parsers
1. Rename regular parsers to `*_custom_parser.py`
2. Update them to return `BDCExtractionResult` instead of `Dict`
3. Delete old custom parsers

### Option 3: Hybrid Approach
1. Keep custom parsers for tickers that use `TypedMemberExtractor` well
2. For tickers where regular parser is better (like PFLT/TRIN with recent improvements), make regular parser the custom one
3. Standardize all to return `BDCExtractionResult`

## Immediate Actions Needed

### High Priority (Recent Improvements)
1. **PFLT**: Port identifier parsing from `pflt_parser.py` to `pflt_custom_parser.py`
   - Extract interest_rate, reference_rate, spread, maturity_date from identifiers
   - Clean company names properly
   
2. **TRIN**: Port identifier parsing from `trin_parser.py` to `trin_custom_parser.py`
   - Extract maturity_date, interest_rate, PIK rate, reference_rate, spread
   - Debt detection logic
   - Note: TRIN custom parser appears incomplete (no class found)

### Medium Priority
3. Review other tickers with identifier parsing in regular parsers:
   - BBDC, BCSF, CGBD, CION, CSWC, FDUS, FSK, GAIN, MFIC, MSDL, NMFC, PSEC, TCPC, TSLX
   - Port improvements to custom parsers

### Low Priority
4. For tickers with only regular parsers, consider:
   - Creating custom parsers using `TypedMemberExtractor`
   - Or keeping as-is if they work well

## Implementation Steps

### For PFLT/TRIN (Immediate)
```python
# 1. Copy _parse_identifier method from regular parser to custom parser
# 2. Update custom parser to use identifier parsing results
# 3. Test extraction
# 4. Delete regular parser once verified
```

### For Other Tickers
1. Run `analyze_parser_duplicates.py` to identify differences
2. Compare identifier parsing logic
3. Port improvements to custom parsers
4. Test
5. Delete regular parsers

## Testing Checklist

For each merged parser:
- [ ] Extracts same number of investments
- [ ] All fields populated correctly (especially rates, dates)
- [ ] Company names are clean
- [ ] Investment types are correct
- [ ] Historical extractor works with custom parser

## Files to Update

1. `pflt_custom_parser.py` - Add identifier parsing from `pflt_parser.py`
2. `trin_custom_parser.py` - Add identifier parsing from `trin_parser.py` (may need to create class)
3. Other custom parsers as needed
4. `historical_investment_extractor.py` - Already prioritizes custom parsers (no change needed)

## Files to Delete (After Merging)

Once custom parsers are complete and tested:
- `pflt_parser.py` (after merging improvements)
- `trin_parser.py` (after merging improvements)
- Other regular parsers as they're merged

