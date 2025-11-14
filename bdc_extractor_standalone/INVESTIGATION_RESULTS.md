# OBDC Matching Investigation Results

## Summary

Investigated OBDC matching issues and improved match rate from **33.9% to 81.6%** (347/425 investments).

## Key Findings

### 1. Company Name Variations
**Problem**: XBRL and HTML had different company name formats
- XBRL: "accelerate topco holdings"
- HTML: "accelerate topco holdings llc"

**Solution**: Normalize entity suffixes (LLC, Inc, Corp, Ltd, LP, Limited, Corporation, Company) for matching

### 2. Investment Type Parsing Issues
**Problem**: 42 investments had "Unknown" investment type
- XBRL identifiers like "Hg Genesis 8 Sumoco Limited, Unsecured facility" weren't being parsed correctly
- Investment type was being treated as part of company name

**Solution**: Improved XBRL identifier parsing to detect investment type patterns:
- "Unsecured facility"
- "Unsecured notes"
- "First lien senior secured loan"
- "Second lien senior secured loan"
- "Subordinated debt/notes"

### 3. Company Name Matching
**Problem**: Exact matching failed when company names had slight variations
- 93.2% of unmatched had commas
- 47.7% had parentheses (footnotes, dba, f/k/a)
- 41.3% had dba patterns

**Solution**: Implemented fuzzy company name matching:
- Checks if one normalized name contains the other
- Handles length differences (within 5 characters)
- Matches "company" with "company llc"

## Match Rate Progression

1. **Initial**: 12.9% (55/425) - Basic matching
2. **After first improvement**: 33.9% (144/425) - Better investment type matching
3. **After investigation**: 81.6% (347/425) - Entity suffix normalization + fuzzy matching

## Remaining Unmatched (18.4%)

### Analysis of 78 Unmatched Investments

**Patterns**:
- Some companies exist only in XBRL (not in HTML tables)
- Some companies exist only in HTML (not in XBRL)
- Complex nested company names with multiple f/k/a patterns
- Investment types that don't appear in HTML (e.g., equity investments)

**Examples of Unmatched**:
- "IRI Group Holdings, Inc. (f/k/a Circana Group, L.P. (f/k/a The NPD Group, L.P.))" - Complex nested f/k/a
- "Hg Genesis 8 Sumoco Limited, Unsecured facility" - May not be in HTML table
- Equity investments (Class A Units, Common Units) - May be in different tables

## Improvements Made

### 1. Entity Suffix Normalization
```python
# Removes LLC, Inc, Corp, etc. for matching
entity_suffixes = [' llc', ' inc', ' corp', ' ltd', ' lp', ' limited', ' corporation', ' company']
```

### 2. Better XBRL Identifier Parsing
```python
# Detects investment type patterns in identifiers
investment_type_patterns = [
    r',\s*Unsecured\s+(facility|notes?)$',
    r',\s*First\s+lien\s+senior\s+secured\s+(loan|revolving\s+loan)',
    ...
]
```

### 3. Fuzzy Company Name Matching
```python
# Checks if one name contains the other (handles "company" vs "company llc")
if company_key in html_company or html_company in company_key:
    if abs(len(company_key) - len(html_company)) <= 5:
        candidates.extend(html_entries)
```

## Recommendations for Further Improvement

1. **Handle nested f/k/a patterns**: Better parsing of complex company name structures
2. **Check multiple HTML tables**: Some investments might be in different table sections
3. **Equity investment handling**: May need separate extraction logic for equity investments
4. **Fuzzy string matching**: Use Levenshtein distance for better company name matching

## Debug Script

Created `debug_obdc_matching.py` to analyze matching issues:
- Shows matched vs unmatched patterns
- Analyzes company name variations
- Compares HTML vs XBRL company names
- Identifies overlap and differences

## Usage

```bash
# Run OBDC custom parser
python obdc_custom_parser.py

# Debug matching issues
python debug_obdc_matching.py
```

