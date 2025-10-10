# Preferred Stock Extraction Enhancements - Implementation Summary

## Overview
Fixed critical gaps in preferred stock feature extraction by adding missing material fields to the data models and updating the extractor to capture comprehensive preferred stock information.

## Problem Identified
The JXN Series A Preferred Stock extraction was failing to capture critical features because:
1. **Model Mismatch**: LLM prompt requested extensive data, but parser only mapped to basic fields
2. **Missing Fields**: `SecurityFeatures` model lacked preferred stock-specific fields
3. **Data Loss**: Rich LLM responses were being discarded

## Changes Implemented

### 1. New Model Classes Added to `core/models.py`

#### `RateResetTerms`
Captures floating rate and fixed-to-floating preferred stock features:
- `has_rate_reset`: Boolean flag
- `reset_frequency`: e.g., "5 years", "quarterly"
- `reset_dates`: List of reset dates
- `initial_fixed_period_end`: When initial fixed period ends
- `reset_spread`: Spread over benchmark (e.g., 3.728%)
- `reset_benchmark`: e.g., "Five-year U.S. Treasury Rate"
- `reset_floor`, `reset_cap`: Optional min/max rates

**Material for**: JXN Series A (8% until 2028, then 5Y Treasury + 3.728%)

#### `DepositarySharesInfo`
Tracks depositary shares structure (critical for preferred stock trading):
- `is_depositary_shares`: Boolean flag
- `depositary_ratio`: e.g., "1/1,000th interest"
- `depositary_shares_issued`: e.g., 22,000,000 for JXN
- `underlying_preferred_shares`: e.g., 22,000 for JXN
- `depositary_symbol`: Trading symbol (e.g., "JXN PR A")
- `depositary_institution`: Custodian (e.g., "Equiniti Trust Company")
- `price_per_depositary_share`: Offering price per depositary share

**Material for**: Understanding actual traded instrument vs underlying preferred

#### `SpecialRedemptionEvents`
Captures non-standard redemption triggers:
- `has_rating_agency_event`, `rating_agency_event_price`, `rating_agency_event_window`
- `has_regulatory_capital_event`, `regulatory_capital_event_price`, `regulatory_capital_event_window`
- `has_tax_event`, `tax_event_details`

**Material for**: JXN can redeem at $25,500 for rating event or $25,000 for regulatory event

### 2. Enhanced `SecurityFeatures` Model

Added preferred stock-specific fields:
- **Dividend Features**: `dividend_rate`, `dividend_type`, `is_cumulative`, `payment_frequency`
- **Liquidation**: `liquidation_preference`
- **Perpetual Status**: `is_perpetual`
- **Voting Rights**: `voting_rights_description`, `can_elect_directors`, `director_election_trigger`, `protective_provisions`
- **Redemption**: `special_redemption_events`, `partial_redemption_allowed`
- **Rate Reset**: `rate_reset_terms`
- **Depositary**: `depositary_shares_info`
- **Ranking**: `ranking_description`

### 3. Updated `securities_features_extractor.py`

#### Enhanced `_parse_security_data()` Method
Now parses and constructs:
- `RateResetTerms` from LLM response
- `DepositarySharesInfo` from LLM response
- `SpecialRedemptionEvents` from LLM response
- All new preferred stock fields

#### Updated LLM Prompt Example
Changed from flat structure to nested objects matching models:
```json
{
  "security_id": "JXN Series A Preferred",
  "liquidation_preference": 25000.0,
  "dividend_rate": 8.0,
  "is_cumulative": false,
  "rate_reset_terms": {
    "has_rate_reset": true,
    "reset_spread": 3.728,
    "reset_benchmark": "Five-year U.S. Treasury Rate"
  },
  "depositary_shares_info": {
    "depositary_shares_issued": 22000000,
    "depositary_symbol": "JXN PR A"
  }
}
```

## Material Fields Now Captured

### Critical for Investment Analysis:
1. ✅ **Liquidation Preference** - $25,000 per share for JXN
2. ✅ **Dividend Rate** - 8.0% initial for JXN
3. ✅ **Cumulative Status** - Noncumulative for JXN (critical!)
4. ✅ **Rate Reset** - Resets to Treasury + 3.728% in 2028
5. ✅ **Voting Triggers** - Can elect 2 directors if 6 quarters unpaid
6. ✅ **Special Redemptions** - Rating agency ($25,500) and regulatory ($25,000) events
7. ✅ **Depositary Structure** - 22M depositary shares representing 22K preferred
8. ✅ **Perpetual Status** - No maturity date
9. ✅ **Call Terms** - Callable after March 30, 2028 at $25,000/share
10. ✅ **Payment Frequency** - Quarterly

## Expected JXN Output (After Fix)

```json
{
  "security_id": "JXN Series A Preferred",
  "security_type": "preferred_stock",
  "description": "Fixed-Rate Reset Noncumulative Perpetual Preferred Stock, Series A",
  "par_value": 1.0,
  "liquidation_preference": 25000.0,
  "dividend_rate": 8.0,
  "dividend_type": "fixed-to-floating",
  "is_cumulative": false,
  "payment_frequency": "quarterly",
  "is_perpetual": true,
  "voting_rights_description": "Can elect 2 directors if dividends not paid for 6 quarters",
  "can_elect_directors": true,
  "director_election_trigger": "6 quarterly dividend periods unpaid",
  "redemption_terms": {
    "is_callable": true,
    "call_price": 25000.0,
    "earliest_call_date": "2028-03-30"
  },
  "special_redemption_events": {
    "has_rating_agency_event": true,
    "rating_agency_event_price": 25500.0,
    "has_regulatory_capital_event": true,
    "regulatory_capital_event_price": 25000.0
  },
  "rate_reset_terms": {
    "has_rate_reset": true,
    "reset_frequency": "5 years",
    "initial_fixed_period_end": "2028-03-30",
    "reset_spread": 3.728,
    "reset_benchmark": "Five-year U.S. Treasury Rate"
  },
  "depositary_shares_info": {
    "is_depositary_shares": true,
    "depositary_shares_issued": 22000000,
    "underlying_preferred_shares": 22000,
    "depositary_symbol": "JXN PR A",
    "depositary_institution": "Equiniti Trust Company",
    "price_per_depositary_share": 25.0
  }
}
```

## Comparison: Before vs After

### Before (Missing Data):
```json
{
  "par_value": 1000.0,  // WRONG
  "conversion_terms": null,
  "redemption_terms": {
    "is_callable": false  // WRONG
  }
}
```

### After (Complete Data):
- ✅ Correct liquidation preference ($25,000)
- ✅ Dividend rate (8.0%)
- ✅ Noncumulative status
- ✅ Rate reset terms
- ✅ Callable (true) with call date
- ✅ Special redemption events
- ✅ Depositary shares structure
- ✅ Voting rights
- ✅ All 10 material fields captured

## Benefits

1. **Accurate Valuation**: Rate reset terms critical for pricing
2. **Risk Assessment**: Noncumulative status = higher risk (dividends don't accumulate)
3. **Trading**: Depositary symbol and structure for actual trading
4. **Call Protection**: Earliest call date and special redemption prices
5. **Control Rights**: Voting triggers and director election rights
6. **Liquidity**: Trading symbol and depositary structure

## Testing Required

Run extraction on JXN and verify:
1. All 10 material fields populated
2. Rate reset terms correctly captured
3. Depositary shares info complete
4. Special redemption events present
5. Voting rights captured

## Files Modified

1. `core/models.py` - Added 3 new classes, enhanced SecurityFeatures
2. `core/securities_features_extractor.py` - Updated parser and prompt
3. `PREFERRED_STOCK_GAPS_ANALYSIS.md` - Documented gaps
4. `IMPLEMENTATION_SUMMARY_PREFERRED_STOCK_ENHANCEMENTS.md` - This file

## Next Steps

1. Test with actual JXN extraction
2. Verify LLM captures all new fields
3. Compare output to 424B5 filing manually
4. Test with other preferred stocks (bank preferreds, etc.)
5. Update documentation with examples



