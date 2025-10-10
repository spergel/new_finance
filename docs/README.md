# SEC Securities Analysis Tool

A focused tool for extracting two types of information from SEC filings:

## 🎯 **Two Simple Paths**

### **Path 1: Securities Features Extractor**
- **Purpose**: Extract detailed features of bonds and preferred shares
- **Sources**: 424B filings and S-1 shelf registrations
- **Target Features**:
  - Conversion terms (price, ratio, conditions)
  - Redemption terms (call provisions, prices, notice periods)
  - Special features (change of control, make-whole, anti-dilution)
  - Interest rates, maturity dates, principal amounts
  - VWAP pricing mechanisms
  - Hedging arrangements

### **Path 2: Corporate Actions Extractor**
- **Purpose**: Extract recent corporate actions affecting securities
- **Sources**: 8-K, 10-K, and 10-Q filings
- **Target Actions**:
  - Tender offers
  - Redemptions and calls
  - Conversions and exchanges
  - Spin-offs and distributions
  - Mergers and acquisitions
  - Debt refinancing
  - Change of control events

## 🏗️ **Architecture**

```
SEC Filings
    ├── 424B + S-1 → Securities Features → JSON output
    └── 8-K + 10-K/Q → Corporate Actions → JSON output
```

## 📁 **Output Structure**

### Securities Features Output
```json
{
  "ticker": "BW",
  "extraction_date": "2025-01-19",
  "securities": [
    {
      "id": "bw_8125_notes_2026",
      "type": "senior_notes",
      "principal_amount": 151200000,
      "interest_rate": 8.125,
      "maturity_date": "2026-02-28",
      "conversion_terms": null,
      "redemption_terms": {
        "callable": true,
        "call_price": 100.0,
        "notice_days": 30
      },
      "special_features": {
        "change_of_control": true,
        "make_whole": false,
        "anti_dilution": false
      },
      "source_filing": "S-3"
    }
  ]
}
```

### Corporate Actions Output
```json
{
  "ticker": "BW", 
  "extraction_date": "2025-01-19",
  "actions": [
    {
      "id": "bw_tender_2024_q3",
      "action_type": "tender_offer",
      "announcement_date": "2024-09-15",
      "target_security": "8.125% Senior Notes",
      "offer_price": 102.5,
      "expiration_date": "2024-10-15",
      "source_filing": "8-K"
    }
  ]
}
```

## 🎯 **Key Principles**

1. **Simple & Focused**: Two extractors, two purposes, clean separation
2. **LLM-Powered**: Use Gemini to intelligently extract structured data
3. **Standards-Based**: Use existing models.py SecurityData structure
4. **No Noise**: Focus on actual securities features and corporate actions, not random text matching
5. **Reliable Sources**: 424B/S-1 for original terms, 8-K/10-K/Q for recent events

## 🚀 **Usage**

```bash
# Extract securities features
python3 securities_features_extractor.py BW

# Extract corporate actions  
python3 corporate_actions_extractor.py BW

# Results saved to output/
```

## 📊 **Example Use Cases**

- **Investment Analysis**: Understand conversion optionality and call risk
- **Risk Management**: Track change of control provisions and redemption terms
- **Event Monitoring**: Stay updated on tender offers and refinancing activities
- **Portfolio Management**: Monitor corporate actions affecting held securities 