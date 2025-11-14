# XBRL Data Extraction Summary

## Status

### ✅ Complete XBRL Data (Just Need Reparse)
These tickers have all needed data in XBRL:
- **BCSF**: Has maturity_date, interest_rate in XBRL
- **FDUS**: Has acquisition_date, interest_rate in XBRL  
- **MSDL**: Has maturity_date, interest_rate, reference_rate, spread embedded in identifier
- **TRIN**: Has maturity_date, interest_rate embedded in identifier

### ⚠️ Partial XBRL Data (Need Full Fact Extraction)
These tickers have some data in XBRL but need all facts extracted:
- **ARCC**: 3,626 contexts, 42,897 facts - missing dates/rates in basic extraction
- **CGBD**: 832 contexts, 12,424 facts
- **CSWC**: 1,259 contexts, 15,564 facts
- **FSK**: 2,198 contexts, 20,109 facts
- **GBDC**: 3,348 contexts, 43,541 facts
- **GLAD**: 234 contexts, 5,915 facts
- **MAIN**: 2,777 contexts, 24,837 facts
- **MRCC**: 992 contexts, 13,429 facts
- **MSIF**: 1,645 contexts, 15,781 facts
- **NCDL**: 1,209 contexts, 15,111 facts
- **NMFC**: 1,247 contexts, 18,635 facts
- **OBDC**: 1,292 contexts, 24,495 facts
- **OFS**: 276 contexts, 4,559 facts
- **OXSQ**: 297 contexts, 5,535 facts
- **PFX**: 202 contexts, 3,583 facts
- **PSEC**: 786 contexts, 9,044 facts
- **RAND**: 391 contexts, 5,535 facts
- **SCM**: 1,436 contexts, 16,072 facts
- **TPVG**: 664 contexts, 4,339 facts
- **TRIN**: (needs reparse)
- **WHF**: 981 contexts, 24,495 facts - **HAS maturity_date, interest_rate, spread in facts!**

## Key Finding: WHF Example

For WHF investment "RCKC Acquisitions LLC First Lien Secured Delayed Draw Loan":
- **21 facts** extracted for this investment
- **Available facts include:**
  - `us-gaap:InvestmentMaturityDate`: 2029-01-02
  - `us-gaap:InvestmentInterestRate`: 0.0946
  - `us-gaap:InvestmentBasisSpreadVariableRate`: 0.05
  - `us-gaap:InvestmentInterestRateFloor`: 0.01
  - `us-gaap:InvestmentOwnedBalancePrincipalAmount`: 2923000
  - `us-gaap:InvestmentOwnedAtCost`: 2903000
  - `us-gaap:InvestmentOwnedAtFairValue`: 2923000
  - Plus industry, geographic region, investment type enumerations

## Next Steps

1. **For BCSF, FDUS, MSDL, TRIN**: Reparse XBRL to extract all available fields
2. **For others**: Use the `*_all_facts.csv` files to extract all facts per investment context
3. **Parser approach**: 
   - Extract all facts for each investment context
   - Map common XBRL concepts to our fields
   - Supplement with HTML where XBRL is missing

## Files Created

- `output/xbrl_raw/`: Basic XBRL extraction (24 files)
- `output/xbrl_all_facts/`: All facts per investment (20 files)

