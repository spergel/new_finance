# 424B Filing Strategy - Critical Findings

## Problem Identified ⚠️

**Our current implementation only fetches THE MOST RECENT 424B filing**, which is problematic because:

1. **Companies file THOUSANDS of 424B2s for debt instruments**
   - Citigroup: 9,456 total 424B filings
   - BAC: 8,556 total 424B filings
   - Most recent ones are structured notes, NOT preferred shares

2. **Preferred share 424B filings may be years old**
   - Once issued, preferred shares don't get new 424Bs unless there's a new series
   - Current preferred shares may have 424Bs from 2015-2023

3. **Multiple 424Bs for multiple series**
   - JXN has 2 separate 424B filings (both March 2023)
   - We're only getting 1 of them

## Test Results

### JXN (Jackson Financial)
- **Total 424B filings**: 5
- **Preferred share 424Bs**: 2 ✓
  - 424B5 from 2023-03-07 (Score: 32)
  - 424B5 from 2023-03-06 (Score: 32)
- **Currently fetching**: Only 1 (the most recent)
- **Missing**: 1 preferred share filing

### Citigroup (C)
- **Total 424B filings**: 9,456 (!!)
- **Most recent 30**: All 424B2 debt instruments
- **Preferred share 424Bs**: Need to search further back (probably 2010-2020)
- **Currently fetching**: Wrong filing type (debt, not preferred)

### Bank of America (BAC)
- **Total 424B filings**: 8,556
- **Most recent 30**: All 424B2 debt instruments  
- **Preferred share 424Bs**: Need to search further back
- **Currently fetching**: Wrong filing type (debt, not preferred)

## Solution Strategy

### Immediate Fix (Recommended)

**Option 1: Cross-Reference with 10-Q Data**
1. Extract series names from 10-Q (we already do this via regex)
2. Search 424B filings for each series name
3. Match "Series A", "Series RR", etc. to specific 424B filings
4. Only process 424Bs that match known series

**Benefits:**
- Guaranteed to get the right filings
- No wasted LLM calls on irrelevant debt instruments
- Can find old filings (5-10 years back)

**Implementation:**
```python
# 1. Get series from XBRL/regex
xbrl_data = extract_xbrl_preferred_shares("JXN")
series_list = [sec["series_name"] for sec in xbrl_data["securities"]]
# Result: ["A"]

# 2. Search 424B filings for each series
for series in series_list:
    filing_424b = find_424b_for_series(ticker, series)
    # Search filing content for "Series A Preferred Stock"
    if filing_424b:
        extract_llm_features(filing_424b, series)
```

**Option 2: Content-Based Filtering**
1. Fetch last 50-100 424B filings
2. Quick scan each for "preferred stock" keywords
3. Score each filing (as we did in `find_preferred_424b.py`)
4. Process only high-scoring filings (score > 15)

**Benefits:**
- Works even if 10-Q data is unavailable
- Can discover preferred shares we didn't know about
- More robust

**Drawbacks:**
- More API calls to SEC
- Slower (need to download and scan multiple filings)

### Long-Term Strategy

**Option 3: SEC Filing Search API**
Use the SEC's EDGAR full-text search to find preferred share prospectuses:
```
https://www.sec.gov/cgi-bin/srch-edgar?text=preferred+stock+series
```

**Option 4: Manual Mapping Table**
For major financial institutions, maintain a mapping:
```json
{
  "C": {
    "Series A": {"424B_accession": "0001193125-14-123456", "date": "2014-03-15"},
    "Series J": {"424B_accession": "0001193125-15-234567", "date": "2015-06-20"}
  }
}
```

## Recommended Implementation

### Phase 1: Cross-Reference Approach (Best ROI)

```python
def get_preferred_424b_filings(ticker: str) -> List[Dict]:
    """Get 424B filings that match preferred shares from 10-Q."""
    
    # Step 1: Get series names from 10-Q
    xbrl_data = extract_xbrl_preferred_shares(ticker)
    series_names = [sec.get("series_name") for sec in xbrl_data.get("securities", [])]
    
    if not series_names:
        return []
    
    # Step 2: Search 424B filings for each series
    matched_filings = []
    all_424b = get_all_424b_filings(ticker, max_filings=100)
    
    for filing in all_424b:
        # Quick content check
        content = fetch_filing_content(filing)
        if not content:
            continue
        
        # Check if this filing mentions any of our series
        content_lower = content[:50000].lower()
        for series in series_names:
            search_terms = [
                f'series {series} preferred',
                f'series {series} non-cumulative',
                f'series {series} fixed rate',
                f'{series} preferred stock'
            ]
            
            if any(term in content_lower for term in search_terms):
                filing['matched_series'] = series
                filing['confidence'] = 'high'
                matched_filings.append(filing)
                break  # Don't double-count this filing
    
    return matched_filings
```

### Phase 2: Implement in Extract Pipeline

Update `core/securities_features_extractor.py`:
```python
def _get_relevant_filings(self, ticker: str) -> List[Dict]:
    """Get 424B filings that are actually for preferred shares."""
    
    # First, get XBRL data to know what series exist
    from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares
    xbrl_result = extract_xbrl_preferred_shares(ticker)
    
    if not xbrl_result.get("securities"):
        # No preferred shares found in 10-Q, skip 424B search
        return []
    
    # Cross-reference with 424B filings
    matched_424b = get_preferred_424b_filings(ticker)
    
    return matched_424b
```

## Impact

### Current State
- ❌ Fetching wrong 424B filings for C and BAC (debt instruments)
- ⚠️ Missing 50% of JXN's preferred share 424Bs
- ❌ No validation that 424B matches 10-Q data

### After Implementation
- ✅ Only fetch 424Bs that match known preferred share series
- ✅ Get ALL 424Bs for each series (not just most recent)
- ✅ Validation: 424B data matches 10-Q series names
- ✅ Avoid wasting LLM calls on irrelevant debt filings

## Testing Plan

1. **JXN**: Should find 2 424B5 filings for Series A
2. **Citigroup**: Should find 424B filings for Series A, C, D, E, J, etc. (21 total)
3. **BAC**: Should find 424Bs for Series RR, TT, OO, UU

## Priority: HIGH

This is a **critical fix** that affects the core value proposition:
- Without correct 424B filings, LLM extraction is useless
- We're currently extracting data from the wrong documents
- This explains why we might not be getting complete preferred share features

## Next Steps

1. ✅ **Understand the problem** (Done - this document)
2. ⏳ **Implement `get_preferred_424b_filings()` function**
3. ⏳ **Update `SecuritiesFeaturesExtractor._get_relevant_filings()`**
4. ⏳ **Test with JXN, C, BAC**
5. ⏳ **Validate LLM extractions match XBRL data**


