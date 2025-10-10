# Enhanced Regex Extraction - Summary

## ✅ Completed: Additional Regex Features

We've successfully enhanced the XBRL/regex extraction to capture **6 new investment-relevant features** from 10-Q/10-K filings:

### New Features Extracted

1. **Cumulative vs Non-Cumulative Status** ✓
   - Determines if unpaid dividends accumulate
   - Pattern: `"Series A Non-Cumulative Preferred Stock"`
   - Coverage: 95-100% (very reliable)
   - Example: JXN Series A is non-cumulative, Citigroup all cumulative

2. **Payment Frequency** ✓
   - When dividends are paid (quarterly, monthly, annually, semi-annually)
   - Pattern: `"Series A ... dividends payable quarterly"`
   - Coverage: 15-100% (varies by filing detail)
   - Example: BAC all quarterly

3. **Voting Rights** ✓
   - Whether holders can vote on corporate matters
   - Patterns: `"non-voting"`, `"entitled to vote"`, etc.
   - Coverage: 95-100% when disclosed
   - Example: Citigroup 20/21 have voting rights

4. **Ranking/Priority** ✓
   - Seniority in capital structure (senior, junior, pari_passu, subordinated)
   - Pattern: `"Series A ... ranks senior to"` or `"ranks pari passu with"`
   - Coverage: 95% when disclosed
   - Example: BAC all senior, Citigroup mix of senior and pari_passu

5. **Callable Status & Redemption Type** ✓
   - Whether company can redeem shares (optional, mandatory, not_redeemable)
   - Patterns: `"optional redemption"`, `"mandatory redemption"`, `"not redeemable"`
   - Coverage: Variable (depends on filing)

6. **Call Date** ✓
   - Earliest date company can redeem
   - Pattern: `"redeemable on or after March 30, 2028"`
   - Coverage: Low in 10-Q (more common in prospectuses)

## Test Results

### Jackson Financial (JXN)
```
Series A: 8.0% dividend, non-cumulative, 22,000 shares, $25,000 liq pref
Coverage: 100% dividend rate, 100% cumulative status
```

### Citigroup (C)
```
21 securities (Series A-Z)
- Dividend Rates: 20/21 (95%) - Range: 3.88% to 8.40%
- Cumulative Status: 20/21 (95%) - All cumulative
- Payment Frequency: 3/21 (14%) - All quarterly
- Voting Rights: 20/21 (95%) - All have voting
- Ranking: 20/21 (95%) - Mix of senior and pari_passu
```

### Bank of America (BAC)
```
4 securities (Series RR, TT, OO, UU)
- Dividend Rates: 4/4 (100%) - Range: 4.375% to 6.625%
- Cumulative Status: 4/4 (100%) - All non-cumulative
- Payment Frequency: 4/4 (100%) - All quarterly
- Voting Rights: 4/4 (100%) - All have voting
- Ranking: 4/4 (100%) - All senior
```

## Technical Implementation

### Pattern Design Principles
1. **Context-Aware**: Always link features to series name
   - `Series\s+([A-Z]+)[^.]{0,300}?<feature>`
2. **Flexible Spacing**: Use `.{0,N}` to allow numbers between keywords
3. **Bidirectional**: Check both forward and reverse orderings
4. **Confidence Scoring**: 0.95-0.99 for series-linked patterns

### Files Modified
- `core/xbrl_preferred_shares_extractor.py`
  - Added 7 new extraction patterns (lines 192-289)
  - Enhanced `_group_investment_data` to handle new features
  - Updated output format to include all new fields

### Output Format
```json
{
  "series": "A",
  "dividend_rate": 8.0,
  "is_cumulative": false,
  "payment_frequency": "quarterly",
  "has_voting_rights": false,
  "ranking": "senior",
  "is_callable": true,
  "call_date": "March 30, 2028",
  "redemption_type": "optional",
  "outstanding_shares": 22000,
  "liquidation_preference_per_share": 25000.0
}
```

## Next Step: LLM Enhancement

The following features are **rare in 10-Q filings** and should be extracted via LLM from 424B prospectuses:

1. ⏳ Conversion Terms (conversion ratio, triggers, adjustment formulas)
2. ⏳ Dividend Stopper (restrictions on common dividends)
3. ⏳ PIK Toggle (payment-in-kind option)
4. ⏳ Mandatory Conversion Triggers
5. ⏳ Change of Control Provisions
6. ⏳ Rate Reset Terms (floating rate adjustments)
7. ⏳ Protective Provisions (veto rights)
8. ⏳ Board Appointment Rights
9. ⏳ Tax Treatment details
10. ⏳ Detailed Seniority explanations

## Summary Statistics

**Regex Extraction (10-Q/10-K):**
- ✅ Core metrics: 95-100% coverage (dividend rate, liquidation pref)
- ✅ Structural features: 95-100% coverage (cumulative, voting, ranking)
- ✅ Frequency features: 15-100% coverage (payment frequency)
- ⚠️ Redemption features: Variable coverage (better in prospectuses)

**Ready for:** LLM extraction of complex, narrative-based features from 424B filings

---

**Status:** Regex enhancement COMPLETE ✓  
**Next:** Implement LLM extraction for advanced features


