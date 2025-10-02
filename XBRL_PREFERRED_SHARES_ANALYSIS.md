# 📊 XBRL Data Analysis for Preferred Shares in Employee Benefit Plans

## 🎯 **Overview**

This document analyzes the XBRL (eXtensible Business Reporting Language) schema for Employee Benefit Plans (EBP) to identify what structured data we can extract about preferred shares from recent 10-Q/10-K filings.

## 🏗️ **XBRL Schema Source**
- **Schema**: `us-gaap-ebp-2025.xsd`
- **Namespace**: `http://fasb.org/us-gaap-ebp/2025`
- **Focus**: Employee Benefit Plan disclosures (Form 5500 related)

## 📋 **Preferred Stock XBRL Elements**

### **1. Preferred Stock Classifications**
```xml
<!-- General Preferred Stock Categories -->
us-gaap_PreferredStockMember                     <!-- General preferred stock -->
us-gaap_PreferredNonConvertibleStockMember       <!-- Non-convertible preferred -->
us-gaap_ConvertiblePreferredStockMember          <!-- Convertible preferred -->
us-gaap_ContingentConvertiblePreferredStockMember <!-- Contingent convertible -->
us-gaap_NonredeemablePreferredStockMember        <!-- Non-redeemable preferred -->
us-gaap_RedeemablePreferredStockMember           <!-- Redeemable preferred -->
```

### **2. Employee Benefit Plan Specific Preferred Stock**
```xml
<!-- EBP-Specific Preferred Stock -->
us-gaap-ebp_EmployeeBenefitPlanEmployerPreferredStockMember    <!-- Employer preferred stock -->
us-gaap-ebp_EbpNonemployerPreferredStockMember               <!-- Non-employer preferred stock -->
```

## 💰 **Investment Value Elements**

### **Current/Fair Value Data**
```xml
EmployeeBenefitPlanInvestmentFairValue                    <!-- Fair value of investments -->
EmployeeBenefitPlanInvestmentExcludingPlanInterestInMasterTrustFairValue
EmployeeBenefitPlanInvestmentPlanInterestInMasterTrustFairValue
EmployeeBenefitPlanAssetHeldForInvestmentPlanInterestInMasterTrustCurrentValue
EmployeeBenefitPlanAssetHeldForInvestmentInvestmentExcludingPlanInterestInMasterTrustCurrentValue
```

### **Cost Basis Data**
```xml
EmployeeBenefitPlanInvestmentExcludingPlanInterestInMasterTrustCost
EmployeeBenefitPlanInvestmentAcquiredExcludingPlanInterestInMasterTrustCost
EmployeeBenefitPlanInvestmentSoldExcludingPlanInterestInMasterTrustCost
```

### **Contract Values (for Insurance Contracts)**
```xml
EmployeeBenefitPlanInvestmentPlanInterestInMasterTrustContractValue
EmployeeBenefitPlanInvestmentExcludingPlanInterestInMasterTrustContractValue
EmployeeBenefitPlanInvestmentFairAndContractValue
```

## 📊 **Investment Performance Data**

### **Income and Gains/Losses**
```xml
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitIncreaseForDividendIncomeOnInvestment
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitIncreaseForInterestIncomeOnInvestment
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitIncreaseForInterestAndDividendIncomeOnInvestment
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitIncreaseDecreaseForGainLossOnInvestment
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitIncreaseDecreaseForRealizedGainLossOnInvestment
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitIncreaseDecreaseForUnrealizedGainLossOnInvestment
```

### **Investment Activity**
```xml
EmployeeBenefitPlanInvestmentAcquiredNumber                    <!-- Number of investments acquired -->
EmployeeBenefitPlanInvestmentSoldNumber                       <!-- Number of investments sold -->
EmployeeBenefitPlanInvestmentAcquiredExcludingPlanInterestInMasterTrustPurchasePrice
EmployeeBenefitPlanInvestmentSoldExcludingPlanInterestInMasterTrustSellingPrice
```

## 🎛️ **Investment Characteristics**

### **Investment Details**
```xml
EmployeeBenefitPlanInvestmentNumberOfShares                    <!-- Number of shares held -->
EmployeeBenefitPlanInvestmentParOrMaturityValue               <!-- Par or maturity value -->
EmployeeBenefitPlanInvestmentInterestRate                     <!-- Interest/dividend rate -->
EmployeeBenefitPlanInvestmentMaturityDate                     <!-- Maturity date -->
EmployeeBenefitPlanInvestmentLevel3ReconciliationIncreaseDecreaseForUnrealizedGainLoss
```

### **Investment Classification**
```xml
<!-- Investment Type Categorization -->
us-gaap_InvestmentTypeCategorizationMember
us-gaap_EquitySecuritiesMember
us-gaap_PreferredStockMember
us-gaap_CommonStockMember

<!-- Cost Methods -->
us-gaap_CostMethodDomain
us-gaap_CostMethodAverageCostMember
us-gaap_CostMethodFifoMember
us-gaap_CostMethodLifoMember
```

## 🔍 **Investment Measurement and Valuation**

### **Fair Value Measurement**
```xml
EmployeeBenefitPlanInvestmentMeasurementInput                  <!-- Valuation inputs -->
EmployeeBenefitPlanInvestmentLevel3ReconciliationIncreaseDecreaseForPurchase
EmployeeBenefitPlanInvestmentLevel3ReconciliationIncreaseDecreaseForSale
EmployeeBenefitPlanInvestmentLevel3ReconciliationIncreaseDecreaseForTransferToLevel3
EmployeeBenefitPlanInvestmentLevel3ReconciliationDecreaseForTransferFromLevel3
EmployeeBenefitPlanInvestmentLevel3ReconciliationReasonForTransferIntoOutOfLevel3Description
```

### **NAV and Redemption Information**
```xml
EmployeeBenefitPlanInvestmentFairValueAndNavTableTextBlock
EmployeeBenefitPlanInvestmentFairValueAndNavTextBlock
EmployeeBenefitPlanInvestmentNetAssetValuePerShareOrUnit
EmployeeBenefitPlanInvestmentEmployerCommonStockToTotalAssetPercentage
```

## 📈 **Plan-Level Financial Data**

### **Plan Assets and Performance**
```xml
EmployeeBenefitPlanNetAssetAvailableForBenefit                 <!-- Total plan assets -->
EmployeeBenefitPlanAssetHeldForInvestment                     <!-- Total investments -->
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitIncrease <!-- Total contributions -->
EmployeeBenefitPlanChangeInNetAssetAvailableForBenefitDecrease <!-- Total distributions -->
EmployeeBenefitPlanForm5500CaptionTotalIncome                <!-- Total income -->
EmployeeBenefitPlanForm5500CaptionNetIncomeLoss              <!-- Net income/loss -->
```

## 🎯 **Data Extraction Strategy**

### **For Preferred Shares Analysis**

1. **📊 Investment Holdings**:
   - Filter by `us-gaap_PreferredStockMember` and related categories
   - Extract current/fair values, cost basis, and quantities
   - Get maturity dates and interest rates

2. **💰 Income Generation**:
   - Extract dividend/interest income from preferred shares
   - Track realized/unrealized gains/losses
   - Monitor investment activity (purchases/sales)

3. **📈 Performance Metrics**:
   - Calculate preferred stock allocation percentages
   - Track concentration limits and diversification
   - Monitor valuation changes over time

### **XBRL vs. LLM Comparison**

| Aspect | XBRL Data | LLM Extraction |
|--------|-----------|----------------|
| **Precision** | ✅ Exact numbers | ⚠️ May interpret incorrectly |
| **Structure** | ✅ Standardized tags | ⚠️ Text parsing |
| **Consistency** | ✅ Same across filers | ⚠️ Varies by format |
| **Context** | ❌ Limited context | ✅ Understands relationships |
| **Nuance** | ❌ Standardized only | ✅ Captures special terms |

## 🚀 **Implementation Plan**

### **Phase 1: XBRL Parser Integration**
```python
# Add XBRL parsing capability
def extract_xbrl_preferred_shares(filing_url: str) -> Dict:
    # Parse XBRL instance document
    # Extract preferred stock holdings by category
    # Return structured data
    pass
```

### **Phase 2: Data Fusion**
```python
# Combine XBRL + LLM data
def combine_data_sources(llm_data: Dict, xbrl_data: Dict) -> Dict:
    # Use XBRL for precise numbers
    # Use LLM for context and special terms
    # Return enriched dataset
    pass
```

### **Phase 3: Enhanced Validation**
```python
# Cross-validate between sources
def validate_data_consistency(llm_result: Dict, xbrl_result: Dict) -> Dict:
    # Compare totals, identify discrepancies
    # Generate confidence scores
    pass
```

## 📋 **Key Insights**

1. **✅ Rich Data Available**: XBRL provides precise investment values, income data, and performance metrics for preferred shares in employee benefit plans

2. **🎯 Employee Benefit Focus**: This schema is specifically for Form 5500 disclosures, making it highly relevant for institutional preferred stock holdings

3. **📊 Investment-Centric**: Strong focus on investment values, performance, and plan-level financials

4. **🔗 Standardization**: Consistent taxonomy across filers for reliable data extraction

5. **🚀 Complementary**: XBRL provides the "what" (numbers), LLM provides the "why" (context and special terms)

## 🎯 **Next Steps**

1. **Implement XBRL parser** for the identified elements
2. **Test with real 10-Q/10-K filings** containing employee benefit plan data
3. **Develop data fusion logic** to combine XBRL precision with LLM context
4. **Create validation framework** to ensure data quality

---

*This analysis is based on the `us-gaap-ebp-2025.xsd` schema for Employee Benefit Plan disclosures. The XBRL data provides structured, standardized information that complements our current LLM-based extraction approach.*
