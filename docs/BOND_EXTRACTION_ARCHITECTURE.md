# Bond & Preferred Stock Extraction Architecture

## Overview

Extending the preferred stock extraction system to handle corporate bonds and other debt instruments with proper architectural separation.

## Current Issues

### Preferred Stock Extraction Problems
- **Dividend rates sometimes null** despite being in 424B text
- **Incomplete covenant extraction** - only basic dividend stopper clauses
- **Missing original offering information** - no issuance price, date, size
- **Tax treatment not captured** - regulatory capital status missing
- **Depositary share structures not identified** - B. Riley's complex structure missed

### Architectural Issues
- **Monolithic models.py** - 430 lines, hard to maintain
- **No inheritance hierarchy** - preferred stocks and bonds mixed together
- **No separation of concerns** - one file for all security types
- **Hard to extend** - adding bonds requires touching everything

## Proposed Architecture

### Directory Structure
```
models/
├── __init__.py          # Import all models
├── base.py             # Common security fields + base classes
├── preferred.py        # Preferred stock specific models
└── bonds.py            # Bond specific models

extraction/
├── __init__.py
├── preferred/
│   ├── xbrl_extractor.py    # 10-Q extraction for preferreds
│   ├── filing_matcher.py    # 424B matching for preferreds
│   └── llm_extractor.py     # LLM extraction for preferreds
└── bonds/
    ├── xbrl_extractor.py    # 10-Q extraction for bonds
    ├── filing_matcher.py    # 424B matching for bonds
    └── llm_extractor.py     # LLM extraction for bonds

core/
├── data_fusion.py      # Combine XBRL + LLM data
├── sec_api_client.py   # SEC API interactions
└── utils.py           # Common utilities
```

## Base Security Model

### `models/base.py`
```python
class BaseSecurity(BaseModelWithConfig):
    """Common fields for all security types"""
    security_id: str
    company: str
    filing_date: date
    description: Optional[str] = None

    # Source information
    source_filing: str  # "10-Q", "424B5", "S-1"
    extraction_confidence: float = 1.0

    # Metadata
    matched_filing_date: Optional[date] = None
    matched_filing_accession: Optional[str] = None
    filing_url: Optional[str] = None
    match_confidence: Optional[str] = None

    # Common financial fields
    outstanding_amount: Optional[float] = None  # Principal/shares outstanding
    par_value: Optional[float] = None          # Face/par value per unit
    currency: str = "USD"
```

## Preferred Stock Model

### `models/preferred.py`
```python
class PreferredStock(BaseSecurity):
    """Preferred stock specific fields"""
    # Core terms
    dividend_rate: Optional[float] = None
    dividend_type: Optional[str] = None  # "fixed", "floating", "fixed-to-floating"
    liquidation_preference: Optional[float] = None
    is_cumulative: Optional[bool] = None

    # Dividend details
    payment_frequency: Optional[str] = None
    dividend_calculation_method: Optional[str] = None  # "360-day year"
    dividend_stopper_clause: Optional[str] = None

    # Offering information
    original_offering_size: Optional[int] = None
    original_offering_date: Optional[date] = None
    original_offering_price: Optional[float] = None
    is_new_issuance: Optional[bool] = None

    # Voting & governance
    voting_rights_description: Optional[str] = None
    can_elect_directors: Optional[bool] = None
    protective_provisions: List[str] = []

    # Features
    conversion_terms: Optional[ConversionTerms] = None
    redemption_terms: Optional[RedemptionTerms] = None
    rate_reset_terms: Optional[RateResetTerms] = None
    depositary_shares_info: Optional[DepositarySharesInfo] = None

    # Enhanced features
    covenants: Optional[Covenants] = None
    tax_treatment_notes: Optional[str] = None
```

## Bond Model

### `models/bonds.py`
```python
class Bond(BaseSecurity):
    """Corporate bond specific fields"""
    # Core terms
    coupon_rate: Optional[float] = None
    coupon_type: Optional[str] = None  # "fixed", "floating", "zero-coupon"
    maturity_date: Optional[date] = None
    face_value: Optional[float] = None

    # Pricing & analytics
    current_price_percent: Optional[float] = None
    yield_to_maturity: Optional[float] = None
    current_yield: Optional[float] = None
    duration_years: Optional[float] = None
    modified_duration: Optional[float] = None

    # Credit information
    credit_ratings: Dict[str, str] = {}  # {"sp": "BBB-", "moodys": "Baa3"}
    rating_outlook: Optional[str] = None
    seniority: Optional[str] = None  # "Senior Secured", "Senior Unsecured", "Subordinated"
    security_type: Optional[str] = None  # "Secured", "Unsecured", "Guaranteed"

    # Call/Put features
    is_callable: Optional[bool] = None
    call_schedule: List[Dict] = []
    is_putable: Optional[bool] = None
    put_schedule: List[Dict] = []

    # Bond features
    is_convertible: Optional[bool] = None
    is_exchangeable: Optional[bool] = None
    is_floating_rate: Optional[bool] = None
    is_zero_coupon: Optional[bool] = None

    # Offering structure
    offering_structure: Optional[str] = None  # "144A/Reg S", "Registered"
    minimum_denomination: Optional[int] = None
    registration_rights: Optional[bool] = None

    # Enhanced features
    covenants: Optional[Covenants] = None
    credit_spreads: Optional[Dict] = None
    issuer_financials: Optional[Dict] = None
```

## Data Extraction Pipeline

### 1. XBRL Extraction (10-Q/10-K)
**Source:** Current financial statements
**Method:** Structured data extraction

**Preferred Stocks:**
- Outstanding shares
- Par value
- Cumulative status
- Basic voting rights

**Bonds:**
- Outstanding principal
- Carrying value
- Issuer financial metrics
- Debt covenant compliance

### 2. Filing Matching
**Source:** Match 424B/S-1 to securities from XBRL
**Method:** Series name/CUSIP matching

**Preferred Stocks:**
- Match by series name (Series A, Series B)
- Match by dividend rate and liquidation preference

**Bonds:**
- Match by CUSIP/ISIN
- Match by maturity date and coupon rate
- Match by issuer and issue size

### 3. LLM Extraction (424B/S-1)
**Source:** Offering prospectuses
**Method:** AI-powered text analysis

**Preferred Stocks:**
- Complete dividend terms
- Voting rights details
- Protective provisions
- Tax treatment notes

**Bonds:**
- Complete coupon and maturity terms
- Credit ratings and rankings
- Call/put schedules
- Covenant packages

### 4. Data Fusion
**Strategy:**
- XBRL = source of truth for current financial state
- LLM = source of truth for original offering terms
- Merge by security_id with conflict resolution

## Implementation Phases

### Phase 1: Models Restructure (Week 1)
- Create models folder structure
- Split models.py into base/preferred/bonds
- Update all import statements
- Test that preferred stock extraction still works

### Phase 2: Bond XBRL Extraction (Week 2)
- Create bond-specific XBRL patterns
- Extract debt instruments from 10-Q balance sheets
- Identify CUSIP, maturity, coupon from structured data

### Phase 3: Bond Filing Matching (Week 3)
- Match 424B/S-1 to bonds from XBRL
- Handle different bond identifiers (CUSIP vs maturity date)
- Implement confidence scoring for bond matches

### Phase 4: Bond LLM Extraction (Week 4)
- Create bond-specific LLM prompts
- Extract coupon rates, maturity, covenants, credit terms
- Parse call schedules, sinking funds, special features

### Phase 5: Enhanced Features (Week 5)
- Add covenant extraction and parsing
- Implement credit spread calculations
- Add issuer financial analysis
- Create bond-specific analytics

## Priority Fixes for Preferred Stocks

### Immediate Issues to Fix:
1. **Dividend rate extraction** - Sometimes null despite being in 424B
2. **Covenant extraction** - Currently only basic dividend stopper
3. **Original offering information** - Missing issuance details
4. **Tax treatment notes** - Regulatory capital status
5. **Depositary share identification** - Complex structures like B. Riley

### Enhanced LLM Prompts Needed:
```python
# For Preferred Stocks
"Extract these PREFERRED STOCK fields:
- Dividend rate from title (e.g., '7.375% Series B')
- Original offering details (size, date, price)
- Tax treatment (Tier 1 capital, REIT status)
- Covenant package (financial, negative, affirmative)
- Depositary share ratio if applicable"
```

## Quality Assurance

### Testing Strategy:
1. **Unit Tests:** Individual extraction functions
2. **Integration Tests:** End-to-end pipeline
3. **Accuracy Tests:** Compare extracted data vs known values
4. **Regression Tests:** Ensure preferred stocks still work

### Validation Checks:
- Dividend rates not null when expected
- Covenant extraction finds actual restrictions
- Filing matching accuracy > 90%
- Data fusion preserves XBRL truth

## Sample Outputs

### Preferred Stock Output:
```json
{
  "security_id": "RILY Series B Preferred",
  "company": "B. Riley Financial Inc",
  "dividend_rate": 7.375,
  "original_offering_price": 25.0,
  "covenants": {
    "restricted_payments_covenant": "Cannot pay common dividends if preferred dividends in arrears",
    "events_of_default": ["Payment default", "Bankruptcy", "Covenant breach"]
  },
  "tax_treatment_notes": "Qualifies as Tier 1 capital for regulatory purposes"
}
```

### Bond Output:
```json
{
  "security_id": "AAPL 4.375% 2045",
  "company": "Apple Inc",
  "coupon_rate": 4.375,
  "maturity_date": "2045-05-15",
  "yield_to_maturity": 4.75,
  "credit_ratings": {"sp": "AA+", "moodys": "Aa1"},
  "is_callable": true,
  "call_schedule": [{"date": "2025-05-15", "price": 100.0}],
  "covenants": {
    "has_financial_covenants": false,
    "restricted_payments_covenant": "Standard dividend restrictions"
  }
}
```

## Success Metrics

- **Preferred Stock Extraction:** 95%+ dividend rate capture rate
- **Bond Extraction:** Successful extraction of top 50 corporate bonds
- **Filing Matching:** 90%+ accuracy for both preferreds and bonds
- **Data Completeness:** 80%+ of key fields populated
- **Processing Speed:** < 2 minutes per security

This architecture provides a solid foundation for comprehensive fixed income security analysis while maintaining the quality of our preferred stock system.




