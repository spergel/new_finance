# Preferred Stock Extraction Issues

## Current Problems (as of 2025-10-11)

### 1. **Dividend Rates Still NULL** ❌
**Problem:** Despite being in 424B text, dividend rates return `null`

**Example from RILY:**
- 424B text: `"7.375% Series B Cumulative Perpetual Preferred Stock"`
- Current output: `dividend_rate: null`
- Expected: `dividend_rate: 7.375`

**Root Cause:** LLM not extracting from title/headers despite prompts

### 2. **Covenants Not Extracted** ❌
**Problem:** Covenant information is `null`

**Example from RILY:**
- Should extract: dividend stopper clauses, events of default, etc.
- Current output: `covenants: null`
- Expected: Covenant package details

**Root Cause:** LLM prompts not asking for covenant details

### 3. **Original Offering Information Missing** ❌
**Problem:** No offering price, date, size

**Example from RILY:**
- Should extract: Original offering price $25.00
- Current output: `original_offering_price: null`
- Expected: `original_offering_price: 25.0`

**Root Cause:** LLM prompts not asking for offering details

### 4. **Tax Treatment Notes Missing** ❌
**Problem:** No regulatory capital status

**Example from RILY:**
- Should extract: "Qualifies as Tier 1 capital"
- Current output: No tax treatment field
- Expected: `tax_treatment_notes: "Qualifies as Tier 1 capital"`

**Root Cause:** No field in models + not in LLM prompts

## Current Working Features ✅

### XBRL Extraction (10-Q)
- ✅ Outstanding shares: 1,729
- ✅ Cumulative status: `true`
- ✅ Par value: Not extracted (should be $1.00)

### LLM Extraction (424B)
- ✅ Descriptions: `"7.375% Series B Cumulative Perpetual Preferred Stock"`
- ✅ Call dates: `"2025-09-04"`
- ✅ Change of control features: `true`
- ✅ Filing matching: Correctly finds 424B5 filings

### Data Fusion
- ✅ Merges XBRL + LLM data
- ✅ Handles multiple series (A and B)
- ✅ Confidence scoring

## Immediate Fixes Needed

### 1. **Enhanced LLM Prompts**
Add to prompts:
```python
# For Preferred Stocks
"Extract these PREFERRED STOCK fields:
- Dividend rate from title (e.g., '7.375% Series B')
- Original offering details (size, date, price)
- Tax treatment (Tier 1 capital, REIT status)
- Covenant package (financial, negative, affirmative)
- Depositary share ratio if applicable"
```

### 2. **Add Missing Model Fields**
```python
# Add to SecurityFeatures
original_offering_size: Optional[int] = None
original_offering_date: Optional[date] = None
original_offering_price: Optional[float] = None
is_new_issuance: Optional[bool] = None
dividend_calculation_method: Optional[str] = None

# Add to SpecialRedemptionEvents
tax_treatment_notes: Optional[str] = None
```

### 3. **Improved Regex Extraction**
Add patterns for:
```python
# Dividend rates in titles
r'(\d+\.?\d*)\s*%\s+Series\s+[A-Z]'

# Original offering info
r'We are offering.*?(\d+,?\d*)\s+shares.*?\$?(\d+\.?\d*)'

# Tax treatment
r'Tier\s+\d+\s+capital|qualified dividend|regulatory capital'
```

### 4. **Enhanced Covenant Extraction**
Add to LLM prompts:
```python
"Covenants and Restrictions:
- Financial covenants: interest coverage ratios, debt-to-EBITDA limits, minimum EBITDA
- Negative covenants: restrictions on dividends, new debt, asset sales, mergers
- Affirmative covenants: reporting requirements, maintenance obligations
- Events of default: payment defaults, bankruptcy, covenant breaches
- Cross-default provisions: default on other debt
- Change of control covenants: what triggers on ownership changes"
```

## Test Results Summary

### RILY (B. Riley Financial)
**Status:** ❌ **BROKEN** - Critical fields missing

**Current Issues:**
- Dividend rates: `null` (should be 7.375% and 6.875%)
- Covenants: `null` (should have dividend stopper, events of default)
- Original price: `null` (should be $25.00)
- Tax treatment: `null` (should be "Tier 1 capital")

**Working:**
- Series identification: ✅
- Call dates: ✅
- Descriptions: ✅

### SOHO (Sotherly Hotels)
**Status:** ⚠️ **PARTIAL** - Some issues

**Current Issues:**
- Dividend rates: `null` (should be 8.25% for Series D)
- Covenants: `null`
- Original price: `null`

**Working:**
- Series identification: ✅
- Descriptions: ✅

### JXN (Jackson Financial)
**Status:** ✅ **WORKING** - Good extraction

**Working:**
- Dividend rate: 8.0% ✅
- All fields populated ✅

## Priority Fixes

### Immediate (Next 24 hours)
1. **Fix dividend rate extraction** - Add regex patterns for title extraction
2. **Add covenant extraction** - Update LLM prompts for covenant details
3. **Add original offering info** - Extract from 424B text
4. **Add tax treatment notes** - Extract regulatory status

### Medium Term (Next week)
1. **Enhanced regex patterns** - Better extraction from 424B headers
2. **Improved LLM prompts** - More specific instructions for missing fields
3. **Validation checks** - Flag missing critical data
4. **Error handling** - Better fallback mechanisms

### Long Term (Next month)
1. **Bond extraction** - Extend to corporate bonds
2. **Enhanced analytics** - YTM, duration calculations
3. **Data quality scoring** - Automated validation
4. **API improvements** - Better SEC data access

## Success Criteria

**Fixed State:**
```json
{
  "dividend_rate": 7.375,
  "original_offering_price": 25.0,
  "covenants": {
    "restricted_payments_covenant": "Cannot pay common dividends if preferred dividends in arrears",
    "events_of_default": ["Payment default", "Bankruptcy", "Covenant breach"],
    "tax_treatment_notes": "Qualifies as Tier 1 capital for regulatory purposes"
  }
}
```

**Current State:**
```json
{
  "dividend_rate": null,
  "original_offering_price": null,
  "covenants": null
}
```

This represents a **MAJOR GAP** in our extraction capabilities that needs immediate attention.




