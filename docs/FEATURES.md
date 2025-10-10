# Extracted Features Reference

Complete list of features extracted by the preferred stock extraction system.

## XBRL Extraction (10-Q/10-K)

Source: Current financial filings
Method: Regex-based pattern matching
Confidence: High (0.9-0.99)

### Core Identifiers
- **Series Name** - Letter(s) identifying the series (e.g., "A", "RR", "TT")
- **CUSIP** - 9-character security identifier (when available)

### Financial Terms
- **Dividend Rate** - Annual dividend rate (%)
- **Outstanding Shares** - Current shares outstanding
- **Authorized Shares** - Maximum shares authorized
- **Par Value** - Par value per share ($)
- **Liquidation Preference** - Liquidation value per share ($)

### Basic Terms
- **Is Cumulative** - Whether unpaid dividends accumulate (boolean)
- **Is Callable** - Whether issuer can redeem (boolean)
- **Call Date** - Earliest redemption date (when extractable)
- **Has Voting Rights** - Whether shares have voting rights (boolean)
- **Payment Frequency** - Dividend payment frequency (quarterly, monthly, etc.)
- **Ranking** - Priority in capital structure (senior, junior, pari passu)
- **Redemption Type** - Type of redemption provision (optional, mandatory, etc.)

### Extraction Patterns

**Dividend Rate:**
```
Patterns:
- "Series A ... 8.000% ... per annum"
- "8.00% Series B"
- "Series C Preferred Stock, 5.95%"
```

**Shares:**
```
Patterns:
- "22,000 shares outstanding"
- "24,000 shares authorized"
- "Series A, $1.00 par value, 22,000 shares issued"
```

**Cumulative Status:**
```
Patterns:
- "non-cumulative" / "noncumulative"
- "cumulative preferred stock"
```

**Voting Rights:**
```
Patterns:
- "voting rights"
- "no voting rights"
- "entitled to vote"
```

## LLM Extraction (424B Prospectuses)

Source: Offering prospectuses
Method: Google Gemini 2.0 with structured prompts
Confidence: Medium-High (0.7-0.9)

### Dividend Features

**Dividend Stopper Clause**
- Description of dividend restrictions
- Conditions under which common dividends are blocked
- Example: "Cannot pay common dividends if preferred dividends unpaid"

**PIK Toggle**
- Whether dividends can be paid in-kind (additional shares)
- Conditions for PIK payment
- PIK rate vs cash rate

**Dividend Type**
- `fixed` - Fixed rate for life
- `floating` - Variable rate tied to benchmark
- `fixed-to-floating` - Fixed initially, then floats

**Payment Dates**
- Specific quarterly/monthly payment dates
- Ex-dividend date conventions

### Conversion Features

**Conversion Price/Ratio**
- Price at which preferred converts to common
- Number of common shares per preferred share

**Conditional Conversion**
- Triggers for automatic conversion
- Example: "Converts if common stock > $50 for 20 days"

**Conversion Window**
- Earliest conversion date
- Expiration date (if applicable)

**Anti-Dilution Provisions**
- Adjustments for stock splits
- Adjustments for dividends
- Adjustments for offerings below market

### Redemption Features

**Callable Provisions**
- Earliest call date
- Call price (usually par + premium)
- Notice period required

**Make-Whole Provisions**
- Premium paid if called early
- Calculation method (usually NPV of future dividends)

**Sinking Fund**
- Annual mandatory redemptions
- Amount per year
- Schedule of payments

**Special Redemption Events**

*Rating Agency Event:*
- Triggered if security no longer counts as equity capital
- Redemption price (often 102% of par)
- Time window to exercise

*Regulatory Capital Event:*
- Triggered by regulatory changes
- Redemption price (often 100% of par)
- Notice requirements

*Tax Event:*
- Triggered by adverse tax treatment
- Conditions and pricing

### Governance Features

**Voting Rights (Detailed)**
- Conditions for voting (e.g., "6 quarters dividends unpaid")
- Number of directors can elect
- Duration of voting rights
- Matters requiring approval

**Protective Provisions**
- Changes requiring 2/3 vote
- Restrictions on senior securities
- Restrictions on amendments

**Board Appointment Rights**
- Number of directors can appoint
- Trigger conditions
- Term limits

### Rate Reset Features

**Reset Mechanism**
- Reset frequency (e.g., every 5 years)
- Reset benchmark (e.g., 5-year Treasury)
- Spread over benchmark
- Floor/cap on rate

**Reset Dates**
- Specific reset dates
- Initial fixed period end date

### Depositary Shares

**Structure**
- Ratio (e.g., 1/1,000th of preferred share)
- Depositary shares issued
- Underlying preferred shares

**Trading**
- Trading symbol
- Exchange listed on
- Depositary institution

**Pricing**
- Price per depositary share
- Relationship to preferred share value

### Special Provisions

**Change of Control**
- Definition of change of control
- Put right (holder can force redemption)
- Call right (issuer must redeem)
- Premium paid

**VWAP Pricing**
- Volume-weighted average price provisions
- Conditions for use

**Tax Treatment**
- Qualified dividend income status
- DRD (Dividends Received Deduction) eligibility
- Special tax considerations

### Ranking and Priority

**Capital Structure Position**
- Senior to common stock (always)
- Junior to debt (usually)
- Pari passu with other preferred series
- Specific subordination terms

## Fused Output

The final fused output combines all fields:

```json
{
  // Identifiers
  "series_name": "A",
  "ticker": "JXN",
  "cusip": "47215P508",
  "security_id": "Series A",
  "description": "Full description...",
  
  // Financial (from XBRL - current)
  "dividend_rate": 8.0,
  "outstanding_shares": 22000,
  "authorized_shares": 24000,
  "par_value": 25000.0,
  "liquidation_preference": 25000.0,
  "is_cumulative": false,
  "payment_frequency": "quarterly",
  "ranking": "senior to common",
  
  // Basic terms (from XBRL)
  "has_voting_rights": false,
  "call_date": "2028-03-30",
  
  // Detailed terms (from LLM)
  "conversion_terms": {
    "conversion_price": null,
    "conversion_ratio": null,
    "is_conditional": false,
    "conversion_triggers": [],
    "earliest_conversion_date": null
  },
  
  "redemption_terms": {
    "is_callable": true,
    "call_price": 25000.0,
    "earliest_call_date": "2028-03-30",
    "notice_period_days": 30,
    "has_make_whole": false,
    "has_sinking_fund": false
  },
  
  "special_features": {
    "has_change_of_control": false,
    "has_anti_dilution": false,
    "has_vwap_pricing": false
  },
  
  // Metadata
  "has_llm_data": true,
  "xbrl_confidence": 0.99,
  "llm_confidence": 0.8,
  "filing_date_10q": "2025-08-01",
  "filing_date_424b": "2023-03-07",
  "source_filing": "424B5"
}
```

## Coverage by Company Type

**Large Banks (C, BAC, JPM, WFC)**
- Many series (10-30+)
- Mostly old issuances (pre-2020)
- XBRL data available
- Limited 424B matches (old prospectuses)

**Insurance Companies (JXN, MET, PRU, AIG)**
- Fewer series (1-5)
- Mix of old and new
- Good XBRL and LLM coverage

**REITs (PSA, SPG)**
- Multiple series (5-15)
- Ongoing issuances
- Excellent coverage

**Others**
- Varies by company
- System adapts to available data

## Data Quality Notes

**High Confidence (>0.9):**
- Dividend rate from XBRL
- Outstanding shares from XBRL
- Par value from XBRL

**Medium Confidence (0.7-0.9):**
- LLM-extracted terms from recent 424Bs
- Complex provisions requiring interpretation

**Low Confidence (<0.7):**
- Very old prospectuses
- Ambiguous language
- Missing sections

**Always Verify:**
- Redemption dates (can change)
- Conversion terms (often complex)
- Special provisions (require legal review)

