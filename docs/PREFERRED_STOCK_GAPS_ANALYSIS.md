# Preferred Stock Extraction Gaps - Critical Analysis

## Problem Summary
The JXN extraction failed to capture detailed preferred stock features because of a **model mismatch**: the LLM prompt requests extensive data, but the parser only maps to basic fields.

## What's Missing from Current Implementation

### 1. **Critical Preferred Stock Fields NOT in SecurityFeatures**

Based on JXN Series A Preferred Stock 424B5 filing analysis:

#### Dividend Features (MISSING)
- `dividend_rate` - e.g., 8.000% initial
- `dividend_type` - "fixed", "floating", "fixed-to-floating", "auction"
- `is_cumulative` - false (noncumulative for JXN)
- `payment_frequency` - "quarterly" (Mar 30, Jun 30, Sep 30, Dec 30)
- `dividend_payment_dates` - specific dates
- `dividend_stopper_clause` - restrictions on common dividends
- `dividend_calculation_method` - "360-day year, twelve 30-day months"

#### Rate Reset Features (MISSING - CRITICAL for JXN!)
- `has_rate_reset` - YES for JXN
- `reset_frequency` - "5 years" for JXN
- `reset_dates` - March 30, 2028, then every 5 years
- `reset_spread` - 3.728% over 5-year Treasury for JXN
- `reset_benchmark` - "Five-year U.S. Treasury Rate"
- `initial_fixed_period_end` - March 30, 2028 for JXN

#### Liquidation Features (PARTIALLY MISSING)
- `liquidation_preference` - $25,000 per share ($25 per depositary share) for JXN
- `liquidation_preference_per_depositary` - $25 for JXN
- `ranking_details` - "senior to common, pari passu with other preferred"

#### Voting Rights (MISSING)
- `voting_rights_description` - "None except if dividends unpaid for 6 quarters"
- `can_elect_directors` - true (2 directors if dividends unpaid)
- `director_election_trigger` - "6 quarterly dividend periods unpaid"
- `protective_provisions` - list of veto rights

#### Redemption Features (PARTIALLY CAPTURED)
Current model has basic redemption, but MISSING:
- `special_redemption_events` - ["rating_agency_event", "regulatory_capital_event"]
- `rating_agency_event_price` - $25,500 for JXN
- `regulatory_capital_event_price` - $25,000 for JXN
- `rating_agency_event_window` - "90 days after occurrence"
- `optional_redemption_date` - "on or after March 30, 2028"
- `partial_redemption_allowed` - true (after 2028) / false (before 2028)

#### Depositary Shares Structure (MISSING)
- `is_depositary_shares` - true for JXN
- `depositary_ratio` - "1/1000th interest per depositary share"
- `depositary_shares_issued` - 22,000,000
- `underlying_preferred_shares` - 22,000
- `depositary_symbol` - "JXN PR A"
- `depositary` - "Equiniti Trust Company"

#### Perpetual/Maturity Features (MISSING)
- `is_perpetual` - true for JXN
- `has_mandatory_redemption` - false
- `has_sinking_fund` - false

#### Tax Features (MISSING)
- `qualified_dividend_eligible` - likely true
- `dividends_received_deduction_eligible` - true for corporate holders
- `tax_treatment_notes` - "Dividends expected to qualify for preferential tax rate"

#### Ranking/Priority (MISSING)
- `ranks_senior_to` - ["common_stock", "junior_stock"]
- `ranks_pari_passu_with` - ["other_preferred_series"]
- `ranks_junior_to` - ["all_debt", "senior_stock"]

### 2. **Existing EnhancedPreferredShareFeatures Model - NOT BEING USED**

You already have `EnhancedPreferredShareFeatures` with:
- `PreferredShareDividendFeatures`
- `PreferredShareGovernance`
- `PreferredShareConversionFeatures`
- `PreferredShareRedemptionFeatures`
- `PreferredShareSpecialProvisions`

**BUT** `securities_features_extractor.py` doesn't use it!

### 3. **What JXN Filing Shows Should Be Captured**

From `JXN_424B5_0001104659-23-029632.txt`:

```
ACTUAL DATA:
- Series A Preferred Stock
- Par value: $1.00 per share
- Liquidation preference: $25,000 per share ($25 per depositary share)
- 22,000,000 depositary shares (representing 22,000 shares)
- Dividend: 8.000% until March 30, 2028
- Then resets to: 5-year Treasury + 3.728%
- Noncumulative dividends
- Quarterly payments: Mar 30, Jun 30, Sep 30, Dec 30
- Callable: March 30, 2028+ at $25,000/share
- Special redemption: Rating agency event ($25,500) or Regulatory capital ($25,000)
- Voting: Can elect 2 directors if 6 quarters of dividends unpaid
- Perpetual (no maturity)
- NYSE symbol: JXN PR A
```

**YOUR CURRENT OUTPUT (JXN_securities_features.json):**
```json
{
  "security_type": "preferred_stock",
  "par_value": 1000.0,  // WRONG - should be 25000 liquidation pref
  "conversion_terms": null,
  "redemption_terms": {
    "is_callable": false,  // WRONG - should be true
    ...
  }
}
```

## Root Causes

1. **Parser Discards LLM Data**: `_parse_security_data()` only maps to `SecurityFeatures` fields, ignoring rich preferred stock data
2. **Wrong Model Used**: Should use `EnhancedPreferredShareFeatures` for preferred stocks
3. **Prompt/Parser Mismatch**: Prompt asks for 20+ features, parser captures ~5

## Recommended Solutions

### Option 1: Dual-Model Approach (RECOMMENDED)
- Use `SecurityFeatures` for debt (notes, bonds)
- Use `EnhancedPreferredShareFeatures` for preferred stocks
- Modify `_parse_security_data()` to detect security type and use appropriate model

### Option 2: Enhance SecurityFeatures
- Add all missing fields to `SecurityFeatures`
- Make most fields Optional
- Single model for all securities

### Option 3: Separate Extractors
- Create `PreferredStockExtractor` using `EnhancedPreferredShareFeatures`
- Keep existing for debt securities
- More modular but more complex

## Material Fields to Add Immediately

**MUST HAVE for Preferred Stock Analysis:**
1. ✅ Liquidation preference (already exists in EnhancedPreferredShareFeatures)
2. ✅ Dividend rate and type (already exists)
3. ✅ Is cumulative/noncumulative (already exists)
4. ❌ Rate reset terms (NOT in any model - ADD THIS)
5. ✅ Voting rights trigger (already exists)
6. ✅ Director election rights (already exists)
7. ❌ Special redemption events (partially exists - enhance)
8. ❌ Depositary shares structure (NOT in any model - ADD THIS)
9. ✅ Perpetual vs finite (can infer from maturity_date)
10. ✅ Payment frequency (already exists)

## Action Items

1. **Add to models.py:**
   - RateResetTerms class
   - DepositarySharesInfo class
   - SpecialRedemptionEvents class

2. **Modify securities_features_extractor.py:**
   - Create `_parse_preferred_stock_data()` method
   - Route preferred stocks to EnhancedPreferredShareFeatures
   - Update prompt to match model fields exactly

3. **Update SecuritiesFeaturesResult:**
   - Support both SecurityFeatures and EnhancedPreferredShareFeatures
   - Or use Union type

4. **Test with JXN:**
   - Re-run extraction
   - Verify all 10 material fields captured
   - Compare output to manual filing review



