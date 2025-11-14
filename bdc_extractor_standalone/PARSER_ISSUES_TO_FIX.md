# Parser Issues to Fix

## GLAD (Gladstone Capital Corp) & LIEN (Chicago Atlantic BDC Inc)
**Issue**: Parsers likely only extracting from one table when there are probably multiple investment tables in the filing.
**Status**: Needs investigation - may be missing investments
**Priority**: Medium

**Current Output Issues**:
- Data looks reasonable but may be incomplete
- Need to verify all tables are being parsed
- Both GLAD and LIEN may have the same issue

---

## MRCC (Monroe Capital Corp)
**Issue**: Should at least partially redo the parser
**Status**: Needs improvement
**Priority**: High

**Current Output Issues**:
- All investments show "Telecommunications" as industry (clearly wrong - should vary by company)
- Investment type shows "Non-Affiliated" (generic, should be more specific like "First Lien Debt", "Term Debt", etc.)
- Company names include investment details (e.g., "BTR Opco LLC (Delayed Draw), Senior Secured Loans")
- Need to extract proper industry and investment type from the data

**Example from output**:
```
"BTR Opco LLC (Delayed Draw), Senior Secured Loans",Telecommunications,,Non-Affiliated
```

---

## MSIF (MSC Income Fund Inc)
**Issue**: Should partially redo the parser
**Status**: Needs improvement
**Priority**: Medium

**Current Output Issues**:
- Many investments show "Unknown" for industry
- Investment types look reasonable (Secured Debt, Preferred Equity, Common Equity, etc.)
- Need to improve industry extraction

**Example from output**:
```
"BDB Holdings, LLC",Unknown,,Secured Debt
GRT Rubber Technologies LLC,Unknown,,Secured Debt 1
```

---

## OXSQ (Oxford Square Capital Corp)
**Issue**: Should partially redo the parser
**Status**: Needs improvement
**Priority**: Medium

**Current Output Issues**:
- Company names are embedded with investment type and industry information
- Example: "Senior Secured Notes - Business Services - Access CIG" should be split into:
  - Company name: "Access CIG"
  - Industry: "Business Services"
  - Investment type: "first lien senior secured notes"
- Many show "Unknown" for industry even though it's embedded in the company name
- Need to parse the identifier string to extract company name, industry, and investment type separately

**Example from output**:
```
Senior Secured Notes - Business Services - Access CIG,Unknown,,first lien senior secured notes
```

Should be:
```
Access CIG,Business Services,,First Lien Senior Secured Notes
```

---

## Summary

| Parser | Issue | Priority | Action Needed |
|--------|-------|----------|---------------|
| GLAD | May be missing tables | Medium | Verify all tables are parsed |
| LIEN | May be missing tables | Medium | Verify all tables are parsed |
| MRCC | Wrong industry, generic investment types | High | Fix industry extraction, improve investment type parsing |
| MSIF | Missing industries | Medium | Improve industry extraction |
| OXSQ | Company name contains industry/type info | Medium | Parse identifier to extract company name, industry, and type separately |

