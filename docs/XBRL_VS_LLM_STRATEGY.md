# XBRL vs LLM Extraction Strategy for Preferred Shares

## Current Status

### What We're Actually Using
**REGEX on Plain Text/HTML from 10-Q/10-K filings** (NOT true XBRL tags)

The "XBRL extractor" is somewhat misnamed - we're parsing the **text content** of XBRL filings (10-Q/10-K), not extracting from XBRL tags like `<ix:nonFraction name="us-gaap:PreferredStockDividendRate">`.

**Why?** Most preferred share details appear in:
- HTML tables in the equity/mezzanine section
- Text descriptions in footnotes
- Certificates of designation (plain text)
- Balance sheet line items

## What Can We Extract With Each Approach?

### ✅ REGEX on 10-Q/10-K (Current - Works Well)

**Already Extracting:**
- Series names (A, RR, AA, etc.)
- Dividend rates (8.0%, 5.25%, etc.)
- Outstanding shares
- Authorized shares  
- Par value / Liquidation preference

**Can Easily Add:**
- Redemption/Call provisions (basic mentions)
- Cumulative vs Non-cumulative dividends
- Voting rights (yes/no)
- Liquidation preference details
- Dividend payment dates (quarterly, dates)
- Ranking/Priority (senior, junior, pari passu)

**Limitations:**
- Gets only what's explicitly stated in standardized format
- Misses nuanced terms and conditions
- Cannot understand complex formulas or conditional logic

---

### 🤖 LLM on 424B/S-1 (Needed for Complex Terms)

**Best For:**
- **Reset provisions** (benchmarks, floors, caps, triggers)
  - Example: "Rate resets every 5 years to 5-year Treasury + 3.728%"
- **Change of control provisions** (specific actions, prices, rights)
- **Detailed redemption terms** (conditions, schedules, optional vs mandatory)
- **Conversion mechanics** (formulas, adjustments, anti-dilution)
- **Exchange rights** (what can be exchanged, when, how)
- **Protective covenants** (restrictions on company actions)
- **Special features** (participation rights, voting triggers)
- **Tax treatment** (dividend treatment, qualified dividend status)

**Evidence from Testing:**
| Feature | 10-Q Mentions | 424B Mentions | Better Source |
|---------|--------------|---------------|---------------|
| Reset provisions | 10 | 56 | 424B (5.6x more) |
| Change of control | 1 | 12 | 424B (12x more) |
| Exchange rights | 23 | 58 | 424B (2.5x more) |
| Protective covenants | 16 | 80 | 424B (5x more) |

---

## Recommended Hybrid Strategy

### Phase 1: REGEX Extraction from 10-Q ✅ **DONE**
```python
# core/xbrl_preferred_shares_extractor.py
extract_xbrl_preferred_shares('JXN')
```

**Extracts:**
- Series identification
- Dividend rates
- Outstanding/authorized shares
- Par values
- Basic structural info

**Output:** `output/xbrl/JXN_xbrl_data.json`

---

### Phase 2: LLM Extraction from 424B ⚠️ **PARTIALLY DONE**
```python
# core/securities_features_extractor.py
extract_securities('JXN')
```

**Should Extract:**
- Reset provisions and benchmarks
- Detailed call/redemption terms
- Change of control provisions
- Conversion features (if any)
- Voting rights details
- Special features
- Protective covenants

**Output:** `output/llm/JXN_securities_features.json`

**Current Issue:** LLM extractor is generic for all securities, not focused on preferred shares

---

### Phase 3: Data Fusion 🔜 **TODO**
```python
# New: core/data_fusion.py
fuse_xbrl_and_llm_data('JXN')
```

**Combines:**
- XBRL: Current financials (rates, shares, values)
- LLM: Complex terms and conditions
- Validation: Cross-check data between sources
- Confidence scoring: Rate reliability of each field

**Output:** `output/fusion/JXN_complete_data.json`

---

## Example: What We Get From Each Source

### From 10-Q (REGEX):
```json
{
  "series": "A",
  "dividend_rate": 8.0,
  "outstanding_shares": 22000,
  "authorized_shares": 24000,
  "liquidation_preference_per_share": 25000.0,
  "par_value": 1.0
}
```

### From 424B (LLM):
```json
{
  "series": "A",
  "description": "Fixed-Rate Reset Noncumulative Perpetual Preferred Stock",
  "dividend_terms": {
    "initial_rate": 8.0,
    "initial_period": "2023-03-30 to 2028-03-30",
    "reset_mechanism": "5-year U.S. Treasury Rate + 3.728%",
    "reset_frequency": "Every 5 years",
    "cumulative": false
  },
  "redemption_terms": {
    "optional_redemption": {
      "earliest_date": "2028-03-30",
      "price": "$25,000 per share plus accrued dividends"
    }
  },
  "voting_rights": {
    "general_voting": false,
    "special_voting": "Triggers if 6 quarterly dividends unpaid"
  }
}
```

### Fused (Best of Both):
```json
{
  "series": "A",
  "cusip": null,
  "description": "Fixed-Rate Reset Noncumulative Perpetual Preferred Stock",
  
  "current_financials": {
    "dividend_rate": 8.0,
    "outstanding_shares": 22000,
    "authorized_shares": 24000,
    "liquidation_preference": 25000.0,
    "par_value": 1.0,
    "source": "10-Q",
    "as_of_date": "2025-06-30"
  },
  
  "terms_and_conditions": {
    "dividend_terms": {
      "current_rate": 8.0,
      "reset_date": "2028-03-30",
      "reset_formula": "5-year Treasury + 3.728%",
      "cumulative": false
    },
    "redemption_terms": {
      "callable": true,
      "call_date": "2028-03-30",
      "call_price": "$25,000 plus accrued dividends"
    },
    "source": "424B5"
  },
  
  "data_quality": {
    "confidence": 0.95,
    "xbrl_coverage": 0.8,
    "llm_coverage": 0.7,
    "cross_validated": ["dividend_rate", "series_name"]
  }
}
```

---

## Next Steps

1. ✅ **DONE:** REGEX extraction from 10-Q works robustly across companies
2. ✅ **DONE:** Validated with JXN, BAC, Citigroup
3. 🔜 **TODO:** Enhance LLM prompts for preferred share specifics
4. 🔜 **TODO:** Build data fusion layer
5. 🔜 **TODO:** Add confidence scoring and validation

---

## Key Insight

**It's NOT "XBRL tags" vs "Regex"** - it's:
- **Regex on structured text (10-Q)**: Fast, reliable for standard financial metrics
- **LLM on prospectuses (424B)**: Needed for complex terms, conditions, and special features
- **Fusion**: Combines both for complete, investment-grade data

The "XBRL" name is historical - we're really doing "structured text extraction from periodic reports" vs "unstructured text understanding from offering documents".


