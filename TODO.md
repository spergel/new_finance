# TODO: SEC Securities Analysis Tool

## 🎯 **Immediate Goals**

### **Phase 1: Clean Up & Foundation**
- [ ] **Delete unnecessary files** 
  - [ ] Remove all the test files and failed experiments
  - [ ] Keep only: `sec_api_client.py`, `models.py`, core extractors
  - [ ] Clean up output directory of old failed attempts

- [ ] **Simplify models.py**
  - [ ] Review SecurityData model for our specific needs
  - [ ] Ensure it supports both securities features and corporate actions
  - [ ] Add clear fields for change-of-control provisions

### **Phase 2: Securities Features Extractor**
- [ ] **Create `securities_features_extractor.py`**
  - [ ] Search 424B and S-1 filings only
  - [ ] Use LLM to extract bond/preferred features
  - [ ] Focus on: conversion terms, redemption terms, special features
  - [ ] Output clean JSON using SecurityData models

- [ ] **Target Features for BW Example:**
  - [ ] 8.125% Senior Notes due 2026: Extract change-of-control provisions
  - [ ] 6.50% Senior Notes due 2026: Extract change-of-control provisions  
  - [ ] 7.75% Preferred Stock: Extract redemption/conversion terms
  - [ ] Any warrants or convertible features

### **Phase 3: Corporate Actions Extractor**
- [ ] **Create `corporate_actions_extractor.py`**
  - [ ] Search 8-K, 10-K, 10-Q filings only
  - [ ] Use LLM to extract corporate actions
  - [ ] Focus on: tenders, redemptions, conversions, M&A events
  - [ ] Output clean JSON with action timeline

- [ ] **Target Actions for BW Example:**
  - [ ] Recent asset sales (BWRS, SPIG/GMAB)
  - [ ] Credit facility amendments
  - [ ] Any tender offers or redemptions
  - [ ] Spin-off activities

## 🛠️ **Technical Implementation**

### **Extractor Structure**
```python
class SecuritiesFeaturesExtractor:
    def __init__(self):
        self.sec_client = SECAPIClient()
        self.llm = GeminiModel()
    
    def extract_features(self, ticker: str) -> List[SecurityData]:
        # 1. Download 424B and S-1 filings
        # 2. Use LLM to extract features
        # 3. Convert to SecurityData objects
        # 4. Save to JSON
        pass

class CorporateActionsExtractor:
    def __init__(self):
        self.sec_client = SECAPIClient()
        self.llm = GeminiModel()
    
    def extract_actions(self, ticker: str) -> List[CorporateAction]:
        # 1. Download 8-K, 10-K, 10-Q filings
        # 2. Use LLM to extract actions
        # 3. Convert to structured objects
        # 4. Save to JSON
        pass
```

### **LLM Prompts**
- [ ] **Securities Features Prompt**: Focus on bond/preferred terms
- [ ] **Corporate Actions Prompt**: Focus on recent events and transactions

## 📋 **Success Criteria**

### **For BW Test Case:**
- [ ] Successfully extract change-of-control provisions from BW debt
- [ ] Extract preferred stock redemption terms
- [ ] Identify recent corporate actions (asset sales, credit amendments)
- [ ] Generate clean, readable JSON output
- [ ] No random text matching or false positives

### **Output Quality:**
- [ ] Each security has clear, structured features
- [ ] Corporate actions have dates, descriptions, affected securities
- [ ] No duplicates or noise
- [ ] Easy to read and analyze

## 🚫 **What We DON'T Want**
- [ ] ❌ Thousands of test files
- [ ] ❌ Random number pattern matching
- [ ] ❌ Complex nested analysis functions
- [ ] ❌ Multiple output formats
- [ ] ❌ Overly complex class hierarchies

## 🎯 **Keep It Simple**
- [ ] ✅ Two files: `securities_features_extractor.py` + `corporate_actions_extractor.py`
- [ ] ✅ Clean LLM prompts focused on specific goals
- [ ] ✅ Use existing `models.py` SecurityData structure
- [ ] ✅ Clear JSON output in `output/` directory
- [ ] ✅ Focus on BW as test case first

## 📅 **Timeline**
1. **Today**: Clean up files and finalize TODO
2. **Next**: Build securities features extractor
3. **Then**: Build corporate actions extractor  
4. **Finally**: Test with BW and other companies 