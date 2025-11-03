# BDC Investment Schedule Extraction - Tracker

## Overview
Tracking progress of investment data extraction across all major BDCs.

---

## BDC Universe (47 Companies)

| # | Ticker | Company Name | Status | Data Quality | Notes | Output File |
|---|--------|--------------|--------|--------------|-------|-------------|
| 1 | **ARCC** | Ares Capital Corp | ✅ **COMPLETE** | 896 investments<br>95-100% coverage | Multi-table format<br>Financial col offsets | `Ares_Capital_Corporation_html_investments.csv` |
| 2 | **OBDC** | Blue Owl Capital Corp | ✅ **COMPLETE** | 420 investments<br>Types 98.3% • FV 99.5% | Redo percentages | `OBDC_Blue_Owl_Capital_Corp_investments.csv` |
| 3 | **MAIN** | Main Street Capital Corp | ✅ **COMPLETE** | 633 investments | Redo | `MAIN_Main_Street_Capital_investments.csv` |
| 4 | **GBDC** | Golub Capital BDC Inc | ✅ **COMPLETE** | 1,649 investments | Redo | `GBDC_Golub_Capital_BDC_Inc_investments.csv` |
| 5 | **BXSL** | Blackstone Secured Lending Fund | ✅ **COMPLETE** | - | Redo | `BXSL_Blackstone_Secured_Lending_Fund_investments.csv` |
| 6 | **HTGC** | Hercules Capital Inc | ✅ **COMPLETE** | 304 investments | Needs reparse | `HTGC_Hercules_Capital_investments.csv` |
| 7 | **FSK** | FS KKR Capital Corp | ✅ **COMPLETE** | 639 investments | - | `FSK_FS_KKR_Capital_Corp_investments.csv` |
| 8 | **TSLX** | Sixth Street Specialty Lending Inc | ✅ **COMPLETE** | 188 investments | - | `TSLX_Sixth_Street_Specialty_Lending_Inc_investments.csv` |
| 9 | **MSDL** | Morgan Stanley Direct Lending Fund | ✅ **COMPLETE** | 685 investments | Missing dates | `MSDL_Morgan_Stanley_Direct_Lending_Fund_investments.csv` |
| 10 | **CSWC** | Capital Southwest Corp | ✅ **COMPLETE** | 412 investments | Redo | `CSWC_Capital_Southwest_Corp_investments.csv` |
| 11 | **MFIC** | Midcap Financial Investment Corp | ✅ **COMPLETE** | 640 investments | Needs reparse; dates low | `MFIC_Midcap_Financial_Investment_Corp_investments.csv` |
| 12 | **OCSL** | Oaktree Specialty Lending Corp | ✅ **COMPLETE** | 452 investments | - | `OCSL_Oaktree_Specialty_Lending_investments.csv` |
| 13 | **GSBD** | Goldman Sachs BDC Inc | ✅ **COMPLETE** | - | Needs reparse; dates low | `GSBD_Goldman_Sachs_BDC_Inc_investments.csv` |
| 14 | **TRIN** | Trinity Capital Inc | ✅ **COMPLETE** | - | Needs reparse; missing dates | `TRIN_Trinity_Capital_Inc_investments.csv` |
| 15 | **PSEC** | Prospect Capital Corp | ✅ **COMPLETE** | 229 investments | Needs reparse | `PSEC_Prospect_Capital_Corp_investments.csv` |
| 16 | **NMFC** | New Mountain Finance Corp | ✅ **COMPLETE** | 611 investments | Missing dates | `NMFC_New_Mountain_Finance_Corp_investments.csv` |
| 17 | **PFLT** | PennantPark Floating Rate Capital Ltd | ✅ **COMPLETE** | 605 investments | Needs reparse; dates low | `PFLT_PennantPark_Floating_Rate_Capital_Ltd_investments.csv` |
| 18 | **CGBD** | TCG BDC Inc | ✅ **COMPLETE** | 368 investments | Redo | `CGBD_TCG_BDC_Inc_investments.csv` |
| 19 | **BBDC** | Barings BDC Inc | ✅ **COMPLETE** | 652 investments | Redo | `BBDC_Barings_BDC_Inc_investments.csv` |
| 20 | **FDUS** | Fidus Investment Corp | ✅ **COMPLETE** | 214 investments | Needs reparse; dates low | `FDUS_Fidus_Investment_Corp_investments.csv` |
| 21 | **SLRC** | SLR Investment Corp | ✅ **COMPLETE** | 151 investments | Needs reparse; missing dates | `SLRC_SLR_Investment_Corp_investments.csv` |
| 22 | **BCSF** | Bain Capital Specialty Finance Inc | ✅ **COMPLETE** | 673 investments | Needs reparse; ref rate missing; dates ~60% | `BCSF_Bain_Capital_Specialty_Finance_Inc_investments.csv` |
| 23 | **GAIN** | Gladstone Investment Corp | ✅ **COMPLETE** | 62 investments | Redo | `GAIN_Gladstone_Investment_Corp_investments.csv` |
| 24 | **TCPC** | Blackrock TCP Capital Corp | ✅ **COMPLETE** | 357 investments | Needs reparse; dates low | `TCPC_Blackrock_TCP_Capital_Corp_investments.csv` |
| 25 | **CION** | CION Investment Corp | ✅ **COMPLETE** | - | Redo percentages | `CION_CION_Investment_Corp_investments.csv` |
| 26 | **NCDL** | Nuveen Churchill Direct Lending Corp | ✅ **COMPLETE** | - | Redo | `NCDL_Nuveen_Churchill_Direct_Lending_Corp_investments.csv` |
| 27 | **CCAP** | Crescent Capital BDC Inc | ✅ **COMPLETE** | 595 investments | Needs reparse; missing dates | `CCAP_Crescent_Capital_BDC_Inc_investments.csv` |
| 28 | **GECC** | Great Elm Capital Corp | ✅ **COMPLETE** | 76 investments | - | `GECC_Great_Elm_Capital_Corp_investments.csv` |
| 29 | **GLAD** | Gladstone Capital Corp | ✅ **COMPLETE** | 98 investments | Redo | `GLAD_Gladstone_Capital_Corp_investments.csv` |
| 30 | **HRZN** | Horizon Technology Finance Corp | ✅ **COMPLETE** | 153 investments | Redo | `HRZN_Horizon_Technology_Finance_Corp_investments.csv` |
| 31 | **ICMB** | Investcorp Credit Management BDC Inc | ✅ **COMPLETE** | 65 investments | Needs reparse; missing dates | `ICMB_Investcorp_Credit_Management_BDC_Inc_investments.csv` |
| 32 | **LIEN** | Chicago Atlantic BDC Inc | ✅ **COMPLETE** | 42 investments | Needs reparse; ref rate missing | `LIEN_Chicago_Atlantic_BDC_Inc_investments.csv` |
| 33 | **LRFC** | Logan Ridge Finance Corp | ✅ **COMPLETE** | 640 investments | Needs reparse; missing dates | `LRFC_Logan_Ridge_Finance_Corp_investments.csv` |
| 34 | **MRCC** | Monroe Capital Corp | ✅ **COMPLETE** | 333 investments | Missing dates | `MRCC_Monroe_Capital_Corp_investments.csv` |
| 35 | **MSIF** | MSC Income Fund Inc | ✅ **COMPLETE** | 489 investments | Missing dates | `MSIF_MSC_Income_Fund_Inc_investments.csv` |
| 36 | **OFS** | OFS Capital Corp | ✅ **COMPLETE** | 99 investments | - | `OFS_OFS_Capital_Corp_investments.csv` |
| 37 | **OXSQ** | Oxford Square Capital Corp | ✅ **COMPLETE** | 73 investments | - | `OXSQ_Oxford_Square_Capital_Corp_investments.csv` |
| 38 | **PFX** | Phenixfin Corp | ✅ **COMPLETE** | 94 investments | Redo | `PFX_Phenixfin_Corp_investments.csv` |
| 39 | **PNNT** | PennantPark Investment Corp | ✅ **COMPLETE** | 552 investments | Redo | `PNNT_PennantPark_Investment_Corp_investments.csv` |
| 40 | **PSBD** | Palmer Square Capital BDC Inc | ✅ **COMPLETE** | 263 investments | Needs reparse; dates ~46% | `PSBD_Palmer_Square_Capital_BDC_Inc_investments.csv` |
| 41 | **RAND** | Rand Capital Corp | ✅ **COMPLETE** | 66 investments | Redo | `RAND_Rand_Capital_Corp_investments.csv` |
| 42 | **RWAY** | Runway Growth Finance Corp | ✅ **COMPLETE** | 108 investments | Needs reparse; dates low | `RWAY_Runway_Growth_Finance_Corp_investments.csv` |
| 43 | **SAR** | Saratoga Investment Corp | ✅ **COMPLETE** | 456 investments | Needs reparse | `SAR_Saratoga_Investment_Corp_investments.csv` |
| 44 | **SCM** | Stellus Capital Investment Corp | ✅ **COMPLETE** | 347 investments | Redo | `SCM_Stellus_Capital_Investment_Corp_investments.csv` |
| 45 | **SSSS** | SuRo Capital Corp | ✅ **COMPLETE** | 75 investments | Redo | `SSSS_SuRo_Capital_Corp_investments.csv` |
| 46 | **TPVG** | TriplePoint Venture Growth BDC Corp | ✅ **COMPLETE** | 306 investments | Redo | `TPVG_TriplePoint_Venture_Growth_BDC_investments.csv` |
| 47 | **WHF** | WhiteHorse Finance Inc | ✅ **COMPLETE** | 243 investments | Redo | `WHF_WhiteHorse_Finance_Inc_investments.csv` |

---

## Progress Summary

- ✅ **Complete**: 12 / 26 (46.2%)
- 📋 **Documented**: 1 / 26 (3.8%)
- ⏳ **Pending**: 13 / 26 (50.0%)

**Total Investments Extracted**: 7,195

---

## Extraction Approach

### Phase 1: Base Parser (✅ DONE)
- `flexible_table_parser.py` - Adaptive HTML parser
- Handles multi-table formats
- Column header detection
- Carry-forward logic
- Industry detection
- Financial value extraction

### Phase 2: BDC-Specific Customization (🔄 IN PROGRESS)
Each BDC may require:
1. **Custom column offsets** (like ARCC's Principal+3/+6 pattern)
2. **Industry header detection rules**
3. **Table identification criteria**
4. **Date format parsing**
5. **Special footnote handling**

### Phase 3: Automation
- Batch processing script
- Configuration per BDC
- Automated data quality checks
- Standardized output format

---

## Next Steps

### Immediate (Top 5 by AUM)
1. ✅ **OBDC** - Blue Owl Capital ($12.2B) - DONE
2. ⏳ **MAIN** - Main Street Capital ($2.1B)
3. ⏳ **GBDC** - Golub Capital BDC ($3.9B)
4. 📋 **BXSL** - Blackstone Secured Lending ($2.0B) - Format known
5. ⏳ **FSK** - FS KKR Capital ($3.2B)

### Strategy
For each BDC:
1. Find latest 10-Q filing URL
2. Run `flexible_table_parser.py` with URL
3. Analyze extraction results
4. Document any unique format requirements
5. Create custom parser if needed
6. Validate data quality
7. Save to standardized CSV

---

## Common Issues & Solutions

### Issue 1: Financial Column Offsets
**Problem**: $ sign and value in separate cells  
**Solution**: Check next cell when `$` found (already implemented)

**Problem**: Columns offset from headers (ARCC: Principal+3 for Cost)  
**Solution**: Detect principal column, calculate offsets (already implemented)

### Issue 2: Multi-Table Formats
**Problem**: Schedule split across 50-100+ tables  
**Solution**: Sequential parsing with state persistence (already implemented)

### Issue 3: Industry Headers
**Problem**: Different styling (bold, font-weight, section dividers)  
**Solution**: Check for bold tags and industry keywords (already implemented)

### Issue 4: Company Name Carry-Forward
**Problem**: Company name appears once for multiple investments  
**Solution**: Instance-level state tracking (already implemented)

---

## Data Quality Targets

For each BDC, aim for:
- ✅ **Company Names**: 100%
- ✅ **Investment Types**: 100%
- ✅ **Industries**: 95%+
- ✅ **Financial Values**: 90%+
  - Principal Amount
  - Cost (Amortized Cost)
  - Fair Value
- ✅ **Dates**: 90%+
  - Acquisition Date
  - Maturity Date
- ✅ **Rate Information**: 85%+
  - Interest Rate
  - Reference Rate (SOFR/LIBOR)
  - Spread

---

## Filing Information

### Where to Find Filings

**SEC EDGAR Search**: https://www.sec.gov/edgar/searchedgar/companysearch

**Direct URL Pattern**:
```
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=[TICKER]&type=10-Q&dateb=&owner=exclude&count=40
```

**HTML Filing Pattern**:
```
https://www.sec.gov/Archives/edgar/data/[CIK]/[ACCESSION]/[FILENAME].htm
```

### Latest Filing Dates (as of project start)
- Most BDCs file quarterly (10-Q)
- Look for Q3 2024 or Q4 2024 filings
- Some may have Q1 2025 available

---

## Configuration Template

For each BDC, we'll create a config:

```python
{
    "ticker": "ARCC",
    "name": "Ares Capital Corporation",
    "cik": "1287750",
    "latest_filing": {
        "accession": "000128775025000046",
        "filename": "arcc-20250930.htm",
        "period": "Q3 2025"
    },
    "parser_config": {
        "min_table_rows": 10,
        "header_threshold": 4,
        "industry_detection": "bold",
        "financial_col_offset": {
            "cost": 3,  # Principal + 3
            "fair_value": 6  # Principal + 6
        }
    }
}
```

---

## Validation Checklist

For each completed extraction:
- [ ] Sample 10 random investments manually
- [ ] Verify company names match filing
- [ ] Check financial totals against filing summary
- [ ] Confirm industry classifications
- [ ] Validate date formats
- [ ] Check for duplicate entries
- [ ] Verify investment type variety

---

*Last Updated: October 29, 2025*
*Status: 3/26 complete (ARCC, HTGC, OCSL)*



