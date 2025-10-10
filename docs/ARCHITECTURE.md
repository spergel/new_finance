# System Architecture

## Overview

The preferred stock extraction system uses a **hybrid approach** combining:
1. **XBRL Extraction** - Regex-based extraction from 10-Q filings (current financial data)
2. **Filing Matcher** - Intelligent matching of 424B prospectuses to securities
3. **LLM Extraction** - AI-powered extraction from 424B filings (detailed terms)
4. **Data Fusion** - Combines XBRL and LLM data into complete datasets

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        INPUT: Ticker Symbol                      │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
        ┌────────────────────────────────────────┐
        │    1. XBRL Extraction (10-Q/10-K)      │
        │    core/xbrl_preferred_shares_extractor│
        └────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
        [Current Financial Data]   [Known Series Names]
        - Dividend rate                      │
        - Outstanding shares                 │
        - Par value                          │
        - Authorized shares                  │
        - Cumulative status                  │
                    │                         │
                    │                         ▼
                    │         ┌───────────────────────────┐
                    │         │   2. Filing Matcher       │
                    │         │   core/filing_matcher     │
                    │         └───────────────────────────┘
                    │                         │
                    │                         ▼
                    │         [Matched 424B Filings]
                    │         - Series-specific prospectuses
                    │         - Confidence scores
                    │                         │
                    │                         ▼
                    │         ┌───────────────────────────┐
                    │         │   3. LLM Extraction       │
                    │         │   core/securities_features│
                    │         └───────────────────────────┘
                    │                         │
                    │                         ▼
                    │         [Detailed Terms]
                    │         - Conversion terms
                    │         - Redemption provisions
                    │         - Governance features
                    │         - Special provisions
                    │                         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   4. Data Fusion       │
                    │   core/data_fusion     │
                    └────────────────────────┘
                                 │
                                 ▼
                    [Complete Dataset]
                    output/fused/{TICKER}_fused_preferred_shares.json
```

## Core Modules

### 1. XBRL Preferred Shares Extractor
**File:** `core/xbrl_preferred_shares_extractor.py`

**Purpose:** Extract current financial data from 10-Q/10-K filings

**Method:** Regex-based pattern matching on filing text

**Extracted Features:**
- Series name (e.g., "A", "RR", "TT")
- Dividend rate (%)
- Outstanding shares
- Authorized shares
- Par value / Liquidation preference
- Cumulative vs non-cumulative
- Voting rights (basic)
- Redemption type
- Ranking/priority
- Payment frequency

**Key Design Decisions:**
- Uses regex instead of XML parsing for flexibility
- Handles multi-letter series (e.g., BAC Series RR, TT)
- Groups data points by series for accuracy
- Confidence scoring based on pattern specificity

### 2. Filing Matcher
**File:** `core/filing_matcher.py`

**Purpose:** Identify which 424B filings correspond to which preferred shares

**Strategy:**
1. Fetch all 424B filings for the ticker
2. Extract first 10,000 characters to identify security type
3. Count mentions of each series name
4. Match filings to securities based on:
   - Security type (preferred_stock vs senior_notes vs common_stock)
   - Series mention frequency
   - Confidence thresholds

**Confidence Levels:**
- `high` - 20+ mentions, clearly matches
- `medium` - 10-19 mentions, likely matches
- `low` - 5-9 mentions, possible match

**Handles:**
- Old preferred shares (>5 years) - May have no recent 424Bs
- New issuances - Multiple 424B filings (uses most recent)
- Debt instruments - Filters out based on security type

### 3. LLM Extraction
**File:** `core/securities_features_extractor.py`

**Purpose:** Extract complex narrative features from 424B prospectuses

**Method:** Google Gemini 2.0 Flash with structured output

**Extracted Features:**

**Dividend Features:**
- Dividend stopper clause
- PIK (Payment-in-Kind) toggle
- Dividend payment dates
- Dividend type (fixed, floating, fixed-to-floating)

**Conversion Features:**
- Conversion price/ratio
- Conditional conversion triggers
- Anti-dilution provisions
- Earliest conversion date

**Redemption Features:**
- Call dates and prices
- Make-whole provisions
- Sinking fund schedules
- Special redemption events (rating agency, regulatory capital, tax)

**Governance Features:**
- Voting rights (detailed conditions)
- Director election rights
- Protective provisions
- Board appointment rights

**Rate Reset:**
- Reset frequency and dates
- Reset benchmark (e.g., 5-year Treasury)
- Spread/floor/cap

**Depositary Shares:**
- Depositary ratio
- Trading symbol
- Shares issued vs underlying

**Special Provisions:**
- Change of control protections
- Put/call rights on change of control
- Tax treatment notes

### 4. Data Fusion
**File:** `core/data_fusion.py`

**Purpose:** Combine XBRL and LLM data into complete datasets

**Strategy:**
- **Financial Terms:** XBRL is source of truth (most current)
- **Narrative Terms:** LLM provides detail (from prospectus)
- **Matching:** By series name (e.g., "A" matches "Series A Preferred")

**Conflict Resolution:**
- Current data (shares, dividend rate) → XBRL wins
- Detailed terms (conversion, redemption) → LLM wins
- Description → Prefer longer/more detailed version

**Output Format:**
```json
{
  "series_name": "A",
  "ticker": "JXN",
  "description": "Fixed-Rate Reset Noncumulative...",
  
  // From XBRL (current, authoritative)
  "dividend_rate": 8.0,
  "outstanding_shares": 22000,
  "authorized_shares": 24000,
  "par_value": 25000.0,
  "is_cumulative": false,
  
  // From LLM (detailed, from prospectus)
  "redemption_terms": { ... },
  "conversion_terms": { ... },
  "special_features": { ... },
  
  // Metadata
  "has_llm_data": true,
  "xbrl_confidence": 0.99,
  "llm_confidence": 0.8
}
```

## Design Principles

### 1. Dual-Source Strategy
**Why:** Neither XBRL nor LLM alone provides complete data
- XBRL: Current financials but limited detail
- LLM: Rich detail but may be from old prospectus

**Solution:** Use both and fuse intelligently

### 2. Confidence Scoring
Every extraction includes confidence metrics:
- XBRL confidence: Based on pattern match quality
- LLM confidence: Based on extraction completeness
- Filing match confidence: Based on series mention frequency

### 3. Error Tolerance
System handles:
- Missing 424B filings (old preferreds)
- Malformed HTML/XBRL
- API timeouts
- Empty/null values

### 4. Extensibility
Easy to add new features:
- XBRL: Add regex patterns to extractor
- LLM: Update prompt and models
- Fusion: Add merge logic

## Data Models

**Key Pydantic Models** (in `core/models.py`):

- `SecurityFeatures` - Complete security data
- `EnhancedPreferredShareFeatures` - Full preferred share detail
- `ConversionTerms` - Conversion provisions
- `RedemptionTerms` - Redemption/call provisions
- `RateResetTerms` - Rate reset mechanisms
- `DepositarySharesInfo` - Depositary share details
- `SpecialRedemptionEvents` - Special redemption triggers
- `PreferredShareGovernance` - Voting and governance

## Performance

**Typical Extraction Times:**
- XBRL extraction: 10-30 seconds
- Filing matching: 5-15 seconds
- LLM extraction: 10-20 seconds per filing
- Total (with 1-2 424B filings): 30-80 seconds

**Rate Limits:**
- SEC API: 10 requests/second (enforced by API)
- Google Gemini: Generous free tier

## Error Handling

**Network Errors:**
- Retry with exponential backoff
- Fall back to cached data if available

**Parsing Errors:**
- Log and continue (graceful degradation)
- Return partial results with confidence scores

**Missing Data:**
- Clearly mark as `null` vs empty vs not extracted
- Include metadata about extraction success

## Testing Strategy

1. **Unit Tests:** Individual regex patterns
2. **Integration Tests:** Full extraction pipeline
3. **Accuracy Tests:** Ground truth validation
4. **Error Tests:** Edge cases and failures

See `docs/TESTING.md` for details.

## Future Enhancements

**Potential Improvements:**
1. Caching layer for SEC filings
2. Batch processing for multiple tickers
3. Real-time monitoring for new filings
4. Historical tracking of term changes
5. Support for other security types (bonds, warrants)
6. Web UI for extraction and visualization

