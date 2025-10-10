# Answers to Your Questions

## Question 1: Why did we fail to get JXN preferred stock info?

### Root Cause
Your extraction **was getting the data from the LLM**, but **throwing it away** due to a model mismatch:

1. **LLM Prompt** asked for 20+ preferred stock fields (dividend_rate, is_cumulative, voting_rights, etc.)
2. **LLM Response** returned all that data
3. **Parser** (`_parse_security_data`) only mapped to basic fields in `SecurityFeatures`
4. **Result** All the rich preferred stock data was discarded

### What Was Wrong with Your Output
```json
{
  "par_value": 1000.0,  // Should be liquidation_preference: 25000.0
  "redemption_terms": {
    "is_callable": false  // Should be true
  }
  // Missing: dividend_rate, is_cumulative, rate_reset, depositary_shares, voting_rights, etc.
}
```

### What It Should Have Been
```json
{
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
  },
  "redemption_terms": {
    "is_callable": true,
    "earliest_call_date": "2028-03-30"
  }
  // ... and 10+ more critical fields
}
```

## Question 2: What else should be in models.py and securities_features_extractor.py that's material?

### What I Added (These Were Missing and Material)

#### In `models.py`:

1. **`RateResetTerms`** - CRITICAL for fixed-to-floating preferreds
   - Most bank preferreds and many corporate preferreds have rate resets
   - Affects valuation significantly
   - JXN resets from 8% to Treasury + 3.728% in 2028

2. **`DepositarySharesInfo`** - CRITICAL for trading
   - Most preferreds trade as depositary shares, not the underlying shares
   - Need to know the ratio (e.g., 1/1000th for JXN)
   - Trading symbol different from underlying
   - Affects pricing and liquidity

3. **`SpecialRedemptionEvents`** - IMPORTANT for risk assessment
   - Rating agency events (downgrades triggering redemption)
   - Regulatory capital events (Basel III, etc.)
   - Tax events
   - Different redemption prices for different triggers

4. **Enhanced `SecurityFeatures` with preferred-specific fields**:
   - `dividend_rate`, `dividend_type`, `is_cumulative`
   - `liquidation_preference` (different from par_value!)
   - `is_perpetual`
   - `voting_rights_description`, `can_elect_directors`
   - `protective_provisions` (veto rights)
   - `payment_frequency`

### What's Still NOT in the Models (Consider Adding)

#### Potentially Material Fields:

1. **Dividend Payment Dates**
   - Specific calendar dates (Mar 30, Jun 30, Sep 30, Dec 30 for JXN)
   - Record dates
   - Ex-dividend dates
   - `List[str]` of payment dates

2. **Offering Economics** (if you care about issuance data)
   - `offering_amount`: Total $ raised
   - `offering_price`: Price per share/depositary share
   - `underwriting_discount`: Fees paid
   - `use_of_proceeds`: What the money is for
   - `over_allotment_option`: Green shoe size

3. **Ranking Detail** (currently just a string)
   - `ranks_senior_to`: List of security types
   - `ranks_pari_passu_with`: List of security types  
   - `ranks_junior_to`: List of security types
   - More structured than free text

4. **Dividend Stopper Clauses** (currently missing)
   - Restrictions on common dividends if preferred not paid
   - Very material for downside protection
   - Example: "Cannot pay common if preferred not paid for 6 quarters"

5. **Mandatory Redemption** (partially covered)
   - `mandatory_redemption_date`: Date if exists
   - `sinking_fund_schedule`: If sinking fund exists
   - `sinking_fund_amount_per_year`: Annual redemption amount

6. **Change of Control Provisions** (in SpecialFeatures but basic)
   - `change_of_control_put_right`: Can holders force redemption?
   - `change_of_control_put_price`: At what price?
   - `change_of_control_definition`: What triggers it?

7. **Tax Treatment Details**
   - `qualified_dividend_eligible`: For individual investors
   - `dividends_received_deduction_eligible`: For corporate investors
   - `tax_rate_notes`: Expected tax treatment

8. **Liquidity Features**
   - `exchange_listed`: NYSE, Nasdaq, etc.
   - `exchange_symbol`: Trading symbol
   - `minimum_denomination`: Minimum trading unit
   - `global_note`: Held by DTC/Euroclear?

### What I WOULD Add Next (Priority Order)

#### High Priority (Material for Analysis):
1. ✅ **Dividend Stopper Clause** - Add to `SecurityFeatures`
   ```python
   dividend_stopper_clause: Optional[str] = None
   ```

2. ✅ **Change of Control Details** - Enhance `SpecialFeatures`
   ```python
   change_of_control_put_right: Optional[bool] = False
   change_of_control_put_price: Optional[float] = None
   ```

3. ✅ **Sinking Fund Schedule** - Add to `RedemptionTerms`
   ```python
   has_sinking_fund: Optional[bool] = False
   sinking_fund_schedule: Optional[str] = None
   ```

#### Medium Priority (Nice to Have):
4. **Dividend Payment Dates** - Add to `SecurityFeatures`
5. **Exchange Listing** - Add to `SecurityFeatures`
6. **Tax Treatment** - New `TaxTreatment` class

#### Low Priority (Offering Data, Not Security Features):
7. Offering economics (amount, price, use of proceeds)

## Question 3: Anything else about @core/ ?

Your question was cut off, but here's what I notice about the `core/` folder:

### What's Good:
- ✅ Modular architecture (separate extractors)
- ✅ Good separation of concerns
- ✅ Comprehensive models
- ✅ LLM + XBRL dual approach

### What Could Be Enhanced:

1. **Error Handling**
   - Add retry logic for API failures
   - Better error messages
   - Fallback strategies

2. **Validation**
   - Add Pydantic validators for fields
   - Check that dividend_rate makes sense (0-100%)
   - Validate dates are in correct order

3. **Confidence Scoring**
   - Currently hardcoded at 0.8
   - Should vary based on extraction quality
   - Lower if fields missing or uncertain

4. **Caching**
   - Cache SEC filings (you may be re-fetching)
   - Cache LLM responses
   - Save $ on API calls

## Summary of Changes Made

### Files Modified:
1. ✅ `core/models.py` - Added 3 new classes, enhanced `SecurityFeatures`
2. ✅ `core/securities_features_extractor.py` - Updated parser to use new fields

### New Classes Added:
1. ✅ `RateResetTerms` - For floating rate preferreds
2. ✅ `DepositarySharesInfo` - For depositary shares
3. ✅ `SpecialRedemptionEvents` - For special redemption triggers

### Fields Added to `SecurityFeatures`:
- Preferred stock: liquidation_preference, dividend_rate, is_cumulative, etc.
- Voting: voting_rights_description, can_elect_directors, etc.
- New nested objects: rate_reset_terms, depositary_shares_info, special_redemption_events

## Testing

Run the test to verify:
```bash
python test_jxn_preferred_extraction.py
```

This will check all 10 material fields are captured.

## What You Should Add Next

Based on materiality for financial analysis:

1. **Dividend Stopper Clause** (add to models.py)
2. **Enhanced Change of Control** (expand SpecialFeatures)
3. **Sinking Fund Details** (add to RedemptionTerms)
4. **Specific Dividend Payment Dates** (add to SecurityFeatures)

These are in order of importance for investment analysis.



