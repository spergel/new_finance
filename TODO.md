# 🚀 Preferred Shares Data Extraction Project - TODO

## 🎯 **Current Status: Implementing XBRL + LLM Hybrid Approach**

### **Phase 1: ✅ Repository Setup & Core Functionality** *(COMPLETED)*
- [x] **Repository Cleanup** - Removed 20+ unnecessary files, organized structure
- [x] **Models Simplified** - Reduced models.py from 1,012 to 147 lines (85% reduction)
- [x] **Core Extractors** - Clean securities_features_extractor.py and corporate_actions_extractor.py
- [x] **FastAPI Backend** - REST API endpoints for both extractors
- [x] **Duplicate Prevention** - Smart deduplication logic implemented
- [x] **Real API Testing** - Working with Google Gemini API for LLM analysis
- [x] **File Cleanup** - Removed redundant test and analysis files (8 files removed)

### **Phase 2: 🔄 XBRL + LLM Hybrid Implementation** *(IN PROGRESS)*

#### **Current Task: XBRL Analysis & Series Identification**
- [x] **XBRL Schema Analysis** - Documented available XBRL elements for preferred shares
- [x] **XBRL Parser Created** - `xbrl_preferred_shares_extractor.py` for extracting from 10-Q filings
- [ ] **Series Identification** - Extract specific preferred share series from XBRL data
- [ ] **Filing Mapping** - Map series to their corresponding 424B/424B5 filings
- [ ] **Enhanced LLM Prompts** - Target specific series found in XBRL
- [ ] **Data Fusion Logic** - Combine XBRL structured data with LLM contextual analysis

#### **🎯 XBRL Data Analysis Results**
**From 10-Q Filings:**
- **✅ BAC**: 191 PreferredStock occurrences, multiple XBRL tags found
- **✅ JPM**: 703 PreferredStock occurrences, series-specific data available
- **✅ JXN**: 125 PreferredStock occurrences in balance sheet

**Available XBRL Elements:**
- `PreferredStock` (general)
- `ConvertiblePreferredStock`, `NonredeemablePreferredStock`, `RedeemablePreferredStock`
- `EmployeeBenefitPlanEmployerPreferredStock` (institutional holdings)
- Balance sheet classifications and monetary values

### **Phase 3: 🏗️ Enhanced Data Pipeline** *(PLANNED)*

#### **Data Fusion Architecture**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   XBRL Parser   │───▶│  Series Mapper  │───▶│   LLM Extractor │
│                 │    │                 │    │                 │
│ • Extract       │    │ • Map series to │    │ • Analyze       │
│   outstanding   │    │   424B filings  │    │   specific      │
│   amounts       │    │                 │    │   series        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │  Data Fusion    │
                    │                 │
                    │ • Combine       │
                    │   sources       │
                    │ • Validate      │
                    │   consistency   │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Final        │
                    │   Database     │
                    └─────────────────┘
```

#### **Implementation Steps**
- [ ] **XBRL Parser Enhancement** - Improve extraction of specific series data
- [ ] **Filing Discovery** - Automated mapping of series to 424B filings
- [ ] **LLM Prompt Engineering** - Target specific series for detailed analysis
- [ ] **Cross-Validation** - Ensure XBRL and LLM data consistency
- [ ] **Performance Optimization** - Batch processing and caching

### **Phase 4: 🚀 Production Features** *(FUTURE)*

#### **Advanced Capabilities**
- [ ] **Historical Data** - Backfill XBRL data for trend analysis
- [ ] **Real-time Updates** - Monitor new filings automatically
- [ ] **API Rate Limiting** - Production-ready API management
- [ ] **Database Integration** - PostgreSQL for data persistence
- [ ] **User Interface** - Web dashboard for data exploration

#### **Data Quality Enhancements**
- [ ] **Confidence Scoring** - Combined confidence from XBRL + LLM sources
- [ ] **Data Validation** - Cross-reference between multiple sources
- [ ] **Error Handling** - Graceful degradation when data is incomplete
- [ ] **Audit Trail** - Track data sources and extraction methods

---

## 🎯 **Next Immediate Actions**

1. **Enhance XBRL Series Identification** - Extract specific preferred share series names, CUSIPs, and identifiers from XBRL data
2. **Improve Filing Mapping** - Create intelligent logic to map XBRL series to their corresponding 424B/424B5 filings
3. **Implement Data Fusion** - Combine XBRL structured data with LLM contextual analysis for comprehensive results
4. **Add XBRL API Endpoint** - Expose XBRL extraction capabilities through the FastAPI backend
5. **Optimize Core Modules** - Enhance error handling, logging, and performance across all extractors

## 📊 **Current Data Sources**

### **XBRL Data (Structured)**
- **Source**: 10-Q/10-K filings
- **Data**: Outstanding shares, balance sheet positions, institutional holdings
- **Format**: Standardized XBRL tags
- **Reliability**: High (exact numbers)

### **LLM Data (Contextual)**
- **Source**: 424B/424B5 filings
- **Data**: Conversion terms, redemption provisions, special features
- **Format**: Natural language processing
- **Reliability**: High (understands context)

### **Combined Approach Benefits**
- **✅ Precision**: XBRL provides exact financial data
- **✅ Context**: LLM understands legal terms and conditions
- **✅ Completeness**: Both sources provide complementary information
- **✅ Validation**: Cross-reference between sources for accuracy

---

*This TODO tracks our progress toward a comprehensive preferred shares analysis system that leverages both XBRL structured data and LLM contextual understanding.*
