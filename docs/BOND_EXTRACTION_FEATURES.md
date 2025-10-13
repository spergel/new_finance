# Bond Extraction Features

Extending the preferred stock extraction system to handle corporate bonds and other debt instruments.

## Overview

While preferred stocks are equity-like instruments with perpetual dividends, **bonds are debt instruments with fixed maturities**. This requires different extraction focus areas:

| Aspect | Preferred Stocks | Bonds |
|--------|------------------|--------|
| **Duration** | Perpetual (no maturity) | Fixed maturity date |
| **Cash Flows** | Dividends (discretionary) | Interest payments (contractual) |
| **Seniority** | Below all debt | Senior/subordinated to other debt |
| **Risk** | Dividend suspension | Default risk |
| **Analysis** | Yield vs par value | YTM, duration, credit spreads |

## Core Bond Information to Extract

### 1. **Basic Bond Terms**

#### From 424B/S-1 Filings:
- **Coupon Rate** - Fixed or floating interest rate (e.g., "5.375%")
- **Maturity Date** - When bond matures (e.g., "June 15, 2030")
- **Face Value/Par Value** - Usually $1,000 or $100
- **Issue Date** - When bonds were originally issued
- **Issuer** - Company/entity issuing the bonds
- **Currency** - USD, EUR, etc. (important for international bonds)

#### Example Extraction:
```json
{
  "coupon_rate": 5.375,
  "maturity_date": "2030-06-15",
  "face_value": 1000.0,
  "issue_date": "2020-06-15",
  "currency": "USD"
}
```

### 2. **Pricing and Yield Information**

#### Key Metrics:
- **Current Price** - Trading price as % of par
- **Yield to Maturity (YTM)** - Total return if held to maturity
- **Current Yield** - Annual interest divided by current price
- **Duration** - Price sensitivity to interest rate changes
- **Modified Duration** - Duration adjusted for yield changes

#### Example:
```json
{
  "current_price_percent": 98.5,
  "yield_to_maturity": 5.75,
  "current_yield": 5.44,
  "duration_years": 7.2,
  "modified_duration": 6.8
}
```

### 3. **Credit and Rating Information**

#### Critical for Bond Analysis:
- **Credit Ratings** - S&P, Moody's, Fitch ratings
- **Rating Outlook** - Stable, Positive, Negative, Developing
- **Rating Watch** - On watch for upgrade/downgrade
- **Seniority Level** - Senior secured, senior unsecured, subordinated, junior subordinated
- **Security Type** - Secured (backed by assets), unsecured, guaranteed

#### Example:
```json
{
  "credit_ratings": {
    "sp": "BBB-",
    "moodys": "Baa3",
    "fitch": "BBB-"
  },
  "rating_outlook": "Stable",
  "seniority": "Senior Unsecured",
  "security_type": "Unsecured"
}
```

### 4. **Call and Put Features**

#### Redemption Provisions:
- **Callable** - Can issuer redeem early?
- **Call Schedule** - Dates and prices for early redemption
- **Call Protection** - Period when bonds cannot be called
- **Make-Whole Calls** - Redemption at NPV of remaining payments
- **putable** - Can holder require early redemption?
- **Put Schedule** - Dates and prices for holder puts

#### Example:
```json
{
  "is_callable": true,
  "call_schedule": [
    {"date": "2025-06-15", "price": 102.5},
    {"date": "2026-06-15", "price": 101.25}
  ],
  "make_whole_call": true,
  "is_putable": false,
  "call_protection_years": 5
}
```

### 5. **Special Bond Features**

#### Structured Features:
- **Convertible** - Can convert to common stock
- **Exchangeable** - Can exchange for other securities
- **Floating Rate** - Rate adjusts periodically (e.g., LIBOR + 2.5%)
- **Step-Up Coupon** - Rate increases over time
- **Zero Coupon** - No periodic interest, discount to par
- **PIK (Payment-in-Kind)** - Interest paid in additional bonds
- **Contingent Convertible (CoCo)** - Converts to equity under stress
- **Perpetual Bonds** - No maturity date (like preferreds)

#### Example:
```json
{
  "is_convertible": false,
  "is_floating_rate": true,
  "floating_rate_formula": "3-month LIBOR + 2.75%",
  "rate_reset_frequency": "Quarterly",
  "is_zero_coupon": false,
  "is_pik": false,
  "is_perpetual": false
}
```

### 6. **Regulatory and Offering Structure**

#### SEC Filings Specific:
- **Rule 144A** - Private placement to QIBs
- **Regulation S** - Offshore offering
- **144A/Reg S** - Global offering structure
- **Minimum Denomination** - Usually $100,000 or $1,000
- **Registration Rights** - Can be registered for public trading
- **Shelf Registration** - Filed under shelf registration statement

#### Example:
```json
{
  "offering_structure": "144A/Reg S",
  "minimum_denomination": 100000,
  "registration_rights": true,
  "shelf_registration": false
}
```

### 7. **Trading and Liquidity Information**

#### Market Data:
- **Exchange Listing** - NYSE, NASDAQ, OTC
- **CUSIP/ISIN** - Bond identifiers
- **Trading Volume** - Average daily volume
- **Bid/Ask Spread** - Market liquidity measure
- **Last Trade Price** - Most recent trade
- **Average Volume** - 30-day average

#### Example:
```json
{
  "exchange_listing": "NYSE",
  "cusip": "123456789",
  "isin": "US1234567890",
  "average_daily_volume": 50000,
  "bid_ask_spread": 0.25
}
```

### 8. **Issuer Financial Information**

#### Company Metrics:
- **Industry Sector** - Technology, Healthcare, Financials, etc.
- **Total Debt Outstanding** - Company's total debt load
- **Debt-to-Equity Ratio** - Leverage measure
- **Interest Coverage Ratio** - Ability to pay interest
- **EBITDA** - Operating cash flow measure
- **Free Cash Flow** - Cash available after capex
- **Credit Metrics** - Altman Z-score, etc.

#### Example:
```json
{
  "industry_sector": "Technology",
  "total_debt_outstanding": 2500000000,
  "debt_to_equity_ratio": 0.8,
  "interest_coverage_ratio": 8.5,
  "ebitda_millions": 1200,
  "free_cash_flow_millions": 450
}
```

### 9. **Market and Relative Value Metrics**

#### Comparative Analysis:
- **Benchmark Index** - U.S. Treasury curve, corporate bond indices
- **Spread to Benchmark** - Credit spread over Treasuries
- **Spread to Peers** - Relative to industry peers
- **Z-spread** - Zero-volatility spread
- **OAS (Option-Adjusted Spread)** - Adjusted for embedded options

#### Example:
```json
{
  "benchmark_treasury": "10-year U.S. Treasury",
  "spread_to_benchmark_bps": 250,
  "z_spread_bps": 275,
  "option_adjusted_spread_bps": 260
}
```

## Bond-Specific Data Sources

### Primary Sources:
1. **424B Prospectuses** - Offering details, terms, features
2. **S-1 Registration Statements** - Initial public offerings
3. **8-K Filings** - Rating changes, defaults, redemptions
4. **10-Q/10-K** - Issuer financials, debt covenants
5. **Market Data Feeds** - Bloomberg, TRACE, eMBS for pricing

### XBRL Extensions Needed:
- Debt instrument tagging (different from preferred stock)
- Maturity date extraction
- Coupon rate vs dividend rate
- Seniority classification
- Security type identification

## Bond Analysis Framework

### Credit Analysis:
- **Issuer Credit Quality** - Rating agency assessments
- **Industry Risk** - Cyclical vs defensive sectors
- **Company-Specific Factors** - Management, competitive position
- **Financial Ratios** - Leverage, coverage, cash flow

### Structural Analysis:
- **Call/Put Features** - Impact on duration and yield
- **Sinking Funds** - Principal repayment schedules
- **Covenants** - Restrictive provisions
- **Security** - Asset backing

### Market Analysis:
- **Liquidity** - Trading volume and bid-ask spreads
- **Relative Value** - Spreads vs peers and benchmarks
- **Supply/Demand** - New issuance calendar
- **Macro Factors** - Interest rates, credit spreads

## Implementation Plan

### Phase 1: Core Bond Terms
- Extend models to include bond-specific fields
- Update LLM prompts for bond terminology
- Add bond-specific regex patterns

### Phase 2: Credit and Ratings
- Integrate rating agency data
- Add credit spread calculations
- Implement rating change tracking

### Phase 3: Pricing and Analytics
- Add YTM and duration calculations
- Implement spread analysis
- Create peer comparison tools

### Phase 4: Advanced Features
- Callable bond modeling
- Embedded option valuation
- Default probability modeling

## Sample Bond Extraction Output

```json
{
  "security_id": "ABC Corp 5.375% 2030",
  "security_type": "corporate_bond",
  "issuer": "ABC Corporation",
  "coupon_rate": 5.375,
  "maturity_date": "2030-06-15",
  "face_value": 1000.0,
  "current_price_percent": 98.5,
  "yield_to_maturity": 5.75,
  "credit_ratings": {
    "sp": "BBB-",
    "moodys": "Baa3"
  },
  "is_callable": true,
  "call_schedule": [
    {"date": "2025-06-15", "price": 102.5}
  ],
  "seniority": "Senior Unsecured",
  "offering_structure": "144A/Reg S",
  "industry_sector": "Technology",
  "spread_to_benchmark_bps": 250
}
```

This framework would extend our preferred stock system to handle the full spectrum of fixed income securities, enabling comprehensive bond investment analysis.



