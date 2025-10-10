# XBRL/Regex Extraction Features

## Overview
This document describes the enhanced regex-based extraction from 10-Q/10-K filings for preferred shares data.

## Extraction Strategy
We use **regex patterns on plain text/HTML** rather than true XBRL tag parsing, as most preferred share details appear in narrative text and HTML tables rather than structured XBRL elements.

## Features Extracted

### Core Financial Data (High Confidence)
1. **Dividend Rate** ✓
   - Pattern: `"Series A ... dividend rate ... 5.25% per annum"`
   - Also handles reverse pattern: `"5.25% ... Preferred Stock, Series A"`
   - Coverage: ~95-100% across tested companies
   - Confidence: 0.95-0.98

2. **Outstanding Shares** ✓
   - Pattern: `"Series A ... 22,000 shares issued and outstanding"`
   - Coverage: Variable (depends on filing structure)
   - Confidence: 0.9

3. **Authorized Shares** ✓
   - Pattern: `"24,000 shares authorized"`
   - Extracted from balance sheet lines
   - Confidence: 0.99

4. **Liquidation Preference** ✓
   - Pattern: `"liquidation preference $25,000 per share"`
   - Coverage: ~95% across tested companies
   - Confidence: 0.99

### Investment-Relevant Features (Medium Confidence)

5. **Cumulative vs Non-Cumulative** ✓ NEW
   - Pattern: `"Series A Non-Cumulative Preferred Stock"`
   - Determines if dividends accumulate if not paid
   - Coverage: ~95-100% (very common in filings)
   - Confidence: 0.95
   - Examples:
     - JXN Series A: Non-cumulative
     - Citigroup: All cumulative
     - BAC: All non-cumulative

6. **Payment Frequency** ✓ NEW
   - Pattern: `"Series A ... dividends payable quarterly"`
   - Frequencies: quarterly, monthly, annually, semi-annually
   - Coverage: ~15-100% (varies by company detail level)
   - Confidence: 0.85-0.9
   - Examples:
     - BAC: All quarterly
     - Citigroup: Some quarterly (14% coverage)

7. **Voting Rights** ✓ NEW
   - Patterns:
     - `"Series A ... non-voting"` → False
     - `"Series A ... entitled to vote"` → True
   - Coverage: ~95-100% for companies that disclose
   - Confidence: 0.8-0.9
   - Examples:
     - Citigroup: 20/21 have voting rights
     - BAC: 4/4 have voting rights

8. **Ranking/Priority** ✓ NEW
   - Pattern: `"Series A ... ranks senior to"` or `"ranks pari passu with"`
   - Types: senior, junior, pari_passu, subordinated
   - Coverage: ~95% for companies that disclose
   - Confidence: 0.85-0.9
   - Examples:
     - Citigroup: Mix of senior and pari_passu
     - BAC: All senior

### Redemption/Call Features (Lower Confidence)

9. **Callable Status** ✓ NEW
   - Patterns:
     - `"Series A ... redeemable on or after March 30, 2028"`
     - `"Series A ... optional redemption"`
     - `"Series A ... not redeemable"`
   - Types: optional, mandatory, not_redeemable
   - Coverage: Variable (depends on filing detail)
   - Confidence: 0.85-0.9

10. **Call Date** ✓ NEW
    - Pattern: `"redeemable on or after March 30, 2028"`
    - Extracts earliest call date when company can redeem
    - Coverage: Low (not always disclosed in 10-Q)
    - Confidence: 0.9 when found

11. **Redemption Type** ✓ NEW
    - Values: optional, mandatory, not_redeemable
    - Indicates if redemption is at company's discretion
    - Confidence: 0.85

## Test Results

### JXN (Jackson Financial Inc.)
- **Securities Found**: 1 (Series A)
- **Dividend Rate**: 8.0% ✓
- **Cumulative**: No ✓
- **Outstanding**: 22,000 shares ✓
- **Liq Pref**: $25,000 ✓

### Citigroup (C)
- **Securities Found**: 21 (Series A-Z)
- **Dividend Rate**: 20/21 (95%) - Range: 3.88% to 8.40%
- **Cumulative**: 20/21 (95%) - All cumulative
- **Payment Frequency**: 3/21 (14%) - All quarterly
- **Voting Rights**: 20/21 (95%) - All have voting rights
- **Ranking**: 20/21 (95%) - Mix of senior and pari_passu

### Bank of America (BAC)
- **Securities Found**: 4 (Series RR, TT, OO, UU)
- **Dividend Rate**: 4/4 (100%) - Range: 4.375% to 6.625%
- **Cumulative**: 4/4 (100%) - All non-cumulative
- **Payment Frequency**: 4/4 (100%) - All quarterly
- **Voting Rights**: 4/4 (100%) - All have voting rights
- **Ranking**: 4/4 (100%) - All senior

## Pattern Design Principles

1. **Context-Aware Extraction**: Always link data to series name
   - `Series\s+([A-Z]+)[^.]{0,300}?<feature>`
   - Prevents mismatching features to wrong securities

2. **Flexible Spacing**: Use `.{0,N}` instead of `[^0-9]{0,N}`
   - Allows numbers like "$533 million" between keywords
   - Handles inconsistent spacing in filings

3. **Bidirectional Patterns**: Check both orderings
   - Forward: "Series A ... 5.25% dividend"
   - Reverse: "5.25% ... Series A Preferred Stock"

4. **Confidence Scoring**: Based on pattern specificity
   - 0.95-0.99: Series-linked with exact matches
   - 0.85-0.9: Series-linked with fuzzy matches
   - 0.6-0.8: Generic patterns without series context

5. **Multi-Letter Series Names**: Support A-ZZZ
   - Updated filter: `len(series_name) <= 3`
   - Handles BAC (RR, TT, OO, UU) and others

## Next Steps (LLM Extraction)

The following features are **rare or absent** in 10-Q filings and should be extracted via LLM from 424B prospectuses:

1. **Conversion Terms** - Details of preferred-to-common conversion
2. **Dividend Stopper** - Restrictions on common dividends if preferred not paid
3. **PIK Toggle** - Payment-in-kind option
4. **Mandatory Conversion Triggers** - Events forcing conversion
5. **Change of Control Provisions** - Special rights on acquisition
6. **Rate Reset Terms** - Dividend rate adjustment mechanisms
7. **Protective Provisions** - Veto rights on major decisions
8. **Board Appointment Rights** - Right to elect directors
9. **Tax Treatment** - Qualified dividend status, etc.
10. **Seniority Details** - Exact ranking relative to other securities

## Output Format

```json
{
  "ticker": "JXN",
  "filing_type": "10-Q",
  "filing_date": "2025-10-03",
  "preferred_shares": [
    {
      "series": "A",
      "description": "Series A Preferred Stock",
      "outstanding_shares": 22000,
      "authorized_shares": 24000,
      "liquidation_preference_per_share": 25000.0,
      "dividend_rate": 8.0,
      "is_cumulative": false,
      "payment_frequency": "quarterly",
      "par_value": 1.0,
      "is_callable": true,
      "call_date": "March 30, 2028",
      "redemption_type": "optional",
      "has_voting_rights": false,
      "ranking": "senior",
      "confidence": 0.99
    }
  ]
}
```

## Files Modified
- `core/xbrl_preferred_shares_extractor.py`: Added 7 new extraction patterns and enhanced grouping logic


