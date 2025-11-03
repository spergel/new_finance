# BDC Investment Data Standardization Guide

This document defines standardized names for investment types, industries, and reference rates used across all BDC parsers. The goal is to ensure consistent data output while preserving the original company terminology where useful.

## Overview

Each parser should output **both**:
1. **Standardized fields** - Normalized values for aggregation and analysis
2. **Original fields** - What the company actually calls it (optional, can be in business_description or separate fields)

For the current implementation, we standardize the primary output fields (`investment_type` and `industry`).

---

## Investment Type Standardization

### Standard Investment Types

#### Debt Instruments
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **First Lien Debt** | First Lien Senior Secured Loan, First Lien Term Loan, First Lien Senior Secured Term Loan, Unitranche First Lien Term Loan, First Lien Secured Debt, Senior Secured First Lien Term Loan, Senior Secured First Lien Delayed Draw Term Loan |
| **First Lien Debt - Revolver** | First Lien Senior Secured Loan - Revolver, First Lien Revolver, First Lien Revolving Credit Facility, Senior Secured First Lien Revolver |
| **First Lien Debt - Delayed Draw** | First Lien Senior Secured Loan - Delayed Draw, First Lien Delayed Draw Term Loan, First Lien Senior Secured Loan - Delayed Draw Term Loan, Unitranche First Lien Delayed Draw Term Loan |
| **Second Lien Debt** | Second Lien Senior Secured Loan, Second Lien Term Loan, Second Lien Secured Debt |
| **Unitranche** | Unitranche, Unitranche First Lien Term Loan (if explicitly called "Unitranche" rather than just first lien) |
| **Subordinated Debt** | Subordinated Debt, Subordinated Note, Junior Debt, Mezzanine Debt |
| **Unsecured Debt** | Unsecured Debt, Unsecured Note, Senior Unsecured Debt |

#### Equity Instruments
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Common Equity** | Common Equity, Common Stock, Member Units, Common Shares |
| **Preferred Equity** | Preferred Equity, Preferred Stock, Preferred Shares |
| **Warrants** | Warrants, Warrant, Stock Warrants |

#### Other
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Promissory Note** | Promissory Note, Note Payable |
| **Unknown** | Unknown, Other, Mixed (fallback when type cannot be determined) |

### Implementation Notes
- **Priority order** for matching:
  1. Most specific first (e.g., "First Lien Debt - Revolver" before "First Lien Debt")
  2. Exact matches preferred over partial matches
  3. Case-insensitive matching
- **Unitranche** should only be used when explicitly stated as "Unitranche" - otherwise treat as "First Lien Debt"
- **Delayed Draw** and **Revolver** are variations, not separate investment types - use the main type with suffix
- **Special cases**:
  - "Investment Type Unitranche First Lien Term Loan" → "First Lien Debt" (strip "Investment Type" prefix)
  - "Investment Type Senior Secured..." → map based on lien position
  - "CLO Mezzanine" → "Subordinated Debt"

---

## Industry Standardization

### Standard Industry Names

#### Technology & Software
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Software** | Software, Software & Services, Software Services |
| **Information Technology Services** | Information Technology Services, IT Services, Technology Services |
| **High Tech Industries** | High Tech Industries, Technology, Tech |
| **Telecommunications** | Telecommunications, Telecom |

#### Healthcare & Life Sciences
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Healthcare & Pharmaceuticals** | Healthcare & Pharmaceuticals, Healthcare & Pharma, Health Care Equipment & Services, Healthcare Services, Pharmaceuticals, Biotechnology Life Sciences, Pharmaceuticals Biotechnology Life Sciences, Healthcare Products, Health Products, Health Care |
| **Medical Services** | Medical Services, Healthcare Services (when specifically medical services, not pharma) |

#### Financial Services
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Diversified Financial Services** | Diversified Financial Services, Diversified Financials, Financial Services, Finance |
| **Insurance** | Insurance, FIRE: Insurance (FIRE = Finance, Insurance, Real Estate) |
| **Banking & Finance** | Banking, FIRE: Finance |

#### Business Services
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Business Services** | Business Services, Services: Business, Commercial & Professional Services, Professional Services |
| **Consumer Services** | Consumer Services, Services: Consumer |
| **Environmental Industries** | Environmental Industries, Environmental Services |
| **Utilities: Services** | Utilities: Services, Utilities, Utilities: Water |

#### Manufacturing & Industrial
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Aerospace & Defense** | Aerospace & Defense, Aerospace, Defense Manufacturing |
| **Capital Equipment** | Capital Equipment, Equipment Manufacturing |
| **Component Manufacturing** | Component Manufacturing, Components |
| **Automotive** | Automotive, Automobiles & Components |
| **Construction & Building** | Construction & Building, Construction |

#### Consumer Goods
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Consumer Goods: Durable** | Consumer Goods: Durable, Durable Goods, Durables & Apparel |
| **Consumer Goods: Non-Durable** | Consumer Goods: Non-Durable, Non-Durable Goods |
| **Consumer Products** | Consumer Products, Consumer |
| **Retail** | Retail, Retailing |
| **Consumer Services** | Consumer Services (duplicate, but for service companies) |

#### Materials & Chemicals
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Chemicals, Plastics & Rubber** | Chemicals, Plastics & Rubber, Chemicals & Materials |
| **Containers, Packaging & Glass** | Containers, Packaging & Glass, Packaging |
| **Metals & Mining** | Metals, Mining, Metals & Mining |

#### Energy & Utilities
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Energy** | Energy, Energy Electicity (typo - fix to Energy), Oil & Gas, Electicity (standalone typo) |
| **Utilities: Water** | Utilities: Water, Water Utilities |

#### Transportation & Logistics
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Transportation: Cargo** | Transportation: Cargo, Transportation services, Transportation & Logistics, Logistics |
| **Transportation: Passenger** | Transportation: Passenger (if applicable) |

#### Media & Entertainment
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Media: Diversified & Production** | Media: Diversified & Production, Media & Entertainment, Entertainment |
| **Leisure Products & Services** | Leisure Products & Services, Leisure, Hotel, Gaming & Leisure, Hospitality |

#### Food & Beverage
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Food & Beverage** | Beverage, Food & Tobacco, Food & Beverage, Beverages |
| **Restaurant & Food Services** | Restaurant Services, Food Services |

#### Real Estate
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Real Estate** | Real Estate, REIT, Real Estate Services |

#### Investment Vehicles
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Investment Vehicles** | Investment Vehicles, CLO (Collateralized Loan Obligation), BDC Funds |

#### Wholesale & Distribution
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Wholesale** | Wholesale, Wholesale Distribution |
| **Distribution** | Distribution, Distribution Services |

### Implementation Notes
- **Mapping priority**: Match longest/most specific industry name first
- **Case-insensitive**: All matching should be case-insensitive
- **Partial matching**: For industries with colons or commas (e.g., "Consumer Goods: Durable"), match the full string first, then fall back to partial matching
- **"FIRE" prefix**: FIRE = Finance, Insurance, Real Estate - map to appropriate standard:
  - "FIRE: Finance" → "Diversified Financial Services"
  - "FIRE: Insurance" → "Insurance"
  - "FIRE: Real Estate" → "Real Estate"
- **Clean up typos**: 
  - "Energy Electicity" → "Energy"
  - "Electicity" (standalone) → "Energy"
- **Keep as-is if no match**: If an industry doesn't match any standard, keep the original value (don't force to "Unknown")
- **Industry suffixes**: Some parsers add numbers (e.g., "Leisure Products & Services 1") - strip trailing numbers/space before matching

---

## Reference Rate Standardization

### Standard Reference Rate Names

| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **SOFR** | SOFR, Secured Overnight Financing Rate, S (in formulas like "S + 5%") |
| **LIBOR** | LIBOR, London Interbank Offered Rate, L (in formulas) |
| **PRIME** | PRIME, Prime Rate, P (in formulas) |
| **EURIBOR** | EURIBOR, Euro Interbank Offered Rate, E (in formulas), SN (sometimes used for EURIBOR) |
| **FED FUNDS** | FED FUNDS, Federal Funds Rate, Federal Funds, F (in formulas) |
| **CDOR** | CDOR, Canadian Dollar Offered Rate, C (in formulas) |
| **BASE RATE** | BASE RATE, Base Rate, Benchmark Rate |

### Implementation Notes
- Standardize all variations to uppercase acronym
- In formulas like "S + 5.25%", "S" means SOFR
- If reference rate cannot be determined, leave blank (don't use "Unknown")

---

## Spread, Floor, and PIK Rate Formatting

### Standard Format
- **All rates should be formatted as percentages with "%" suffix**
- **Examples**: "5.25%", "6.5%", "10%"
- **Decimal precision**: 
  - If original has 2+ decimals, preserve: "5.25%" 
  - If original is whole number, show as: "10%"
  - Remove trailing zeros after 2 decimals: "5.20%" → "5.2%"

### Spread
- Extracted from formulas like "SOFR + 5.25%" → spread: "5.25%"
- If spread is in basis points (e.g., 525 bps), convert to percentage: "525" → "5.25%"

### Floor Rate
- Minimum interest rate floor
- Format: "2%" not "200 basis points"
- If already percentage, use as-is

### PIK Rate
- Payment-in-kind interest rate
- Format: "4.5%" or "0%" if none
- If not present, leave blank (not "0%")

---

## Date Formatting

### Standard Format
- **Acquisition Date**: MM/DD/YYYY (e.g., "04/15/2025")
- **Maturity Date**: MM/DD/YYYY (e.g., "12/31/2030")
- **Normalization**: 
  - Convert 2-digit years to 4-digit: "25" → "2025" (if >= 50, use 19xx)
  - Handle MM/YYYY format: add "/01" for day: "03/2028" → "03/01/2028"

---

## Implementation Strategy

### Phase 1: Create Standardization Module
Create `standardization.py` with:
```python
STANDARD_INVESTMENT_TYPES = {...}  # mapping dict
STANDARD_INDUSTRIES = {...}  # mapping dict
STANDARD_REFERENCE_RATES = {...}  # mapping dict

def standardize_investment_type(raw_type: str) -> str:
    """Map raw investment type to standard name"""
    
def standardize_industry(raw_industry: str) -> str:
    """Map raw industry to standard name"""
    
def standardize_reference_rate(raw_rate: str) -> str:
    """Map raw reference rate to standard name"""
```

### Phase 2: Apply to Parsers
- Import standardization module in each parser
- Apply standardization before writing to CSV
- Preserve original values if needed for debugging

### Phase 3: Validation
- Run all parsers
- Check output CSVs for consistent naming
- Update mappings as new variations are found

---

## Examples

### Investment Type Standardization
```
"First Lien Senior Secured Loan" → "First Lien Debt"
"Unitranche First Lien Term Loan" → "First Lien Debt" (unless explicitly called "Unitranche")
"First Lien Senior Secured Loan - Revolver" → "First Lien Debt - Revolver"
"Common Stock" → "Common Equity"
"Preferred Stock" → "Preferred Equity"
"Subordinated Note" → "Subordinated Debt"
```

### Industry Standardization
```
"Healthcare & Pharmaceuticals" → "Healthcare & Pharmaceuticals" (already standard)
"Health Care Equipment & Services" → "Healthcare & Pharmaceuticals"
"Pharmaceuticals Biotechnology Life Sciences" → "Healthcare & Pharmaceuticals"
"Software & Services" → "Software"
"Services: Business" → "Business Services"
"Consumer Goods: Durable" → "Consumer Goods: Durable" (already standard)
"Energy Electicity" → "Energy" (fix typo)
"FIRE: Finance" → "Diversified Financial Services"
```

### Reference Rate Standardization
```
"S + 5.25%" → reference_rate: "SOFR", spread: "5.25%"
"EURIBOR + 4.5%" → reference_rate: "EURIBOR", spread: "4.5%"
"Prime + 3%" → reference_rate: "PRIME", spread: "3%"
```

---

## Notes for Future Enhancements

1. **Dual Output**: Consider adding `investment_type_original` and `industry_original` columns
2. **Confidence Scores**: Could add confidence scores for standardization (1.0 = exact match, 0.5 = partial match)
3. **Custom Mappings**: Allow company-specific mappings if needed
4. **Validation**: Add validation to catch unmapped values and suggest additions

---

## Maintenance

This document should be updated as:
- New investment types are discovered
- New industry variations are found
- Standard industry classifications change
- New reference rates emerge

Last Updated: [Current Date]

This document defines standardized names for investment types, industries, and reference rates used across all BDC parsers. The goal is to ensure consistent data output while preserving the original company terminology where useful.

## Overview

Each parser should output **both**:
1. **Standardized fields** - Normalized values for aggregation and analysis
2. **Original fields** - What the company actually calls it (optional, can be in business_description or separate fields)

For the current implementation, we standardize the primary output fields (`investment_type` and `industry`).

---

## Investment Type Standardization

### Standard Investment Types

#### Debt Instruments
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **First Lien Debt** | First Lien Senior Secured Loan, First Lien Term Loan, First Lien Senior Secured Term Loan, Unitranche First Lien Term Loan, First Lien Secured Debt, Senior Secured First Lien Term Loan, Senior Secured First Lien Delayed Draw Term Loan |
| **First Lien Debt - Revolver** | First Lien Senior Secured Loan - Revolver, First Lien Revolver, First Lien Revolving Credit Facility, Senior Secured First Lien Revolver |
| **First Lien Debt - Delayed Draw** | First Lien Senior Secured Loan - Delayed Draw, First Lien Delayed Draw Term Loan, First Lien Senior Secured Loan - Delayed Draw Term Loan, Unitranche First Lien Delayed Draw Term Loan |
| **Second Lien Debt** | Second Lien Senior Secured Loan, Second Lien Term Loan, Second Lien Secured Debt |
| **Unitranche** | Unitranche, Unitranche First Lien Term Loan (if explicitly called "Unitranche" rather than just first lien) |
| **Subordinated Debt** | Subordinated Debt, Subordinated Note, Junior Debt, Mezzanine Debt |
| **Unsecured Debt** | Unsecured Debt, Unsecured Note, Senior Unsecured Debt |

#### Equity Instruments
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Common Equity** | Common Equity, Common Stock, Member Units, Common Shares |
| **Preferred Equity** | Preferred Equity, Preferred Stock, Preferred Shares |
| **Warrants** | Warrants, Warrant, Stock Warrants |

#### Other
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Promissory Note** | Promissory Note, Note Payable |
| **Unknown** | Unknown, Other, Mixed (fallback when type cannot be determined) |

### Implementation Notes
- **Priority order** for matching:
  1. Most specific first (e.g., "First Lien Debt - Revolver" before "First Lien Debt")
  2. Exact matches preferred over partial matches
  3. Case-insensitive matching
- **Unitranche** should only be used when explicitly stated as "Unitranche" - otherwise treat as "First Lien Debt"
- **Delayed Draw** and **Revolver** are variations, not separate investment types - use the main type with suffix
- **Special cases**:
  - "Investment Type Unitranche First Lien Term Loan" → "First Lien Debt" (strip "Investment Type" prefix)
  - "Investment Type Senior Secured..." → map based on lien position
  - "CLO Mezzanine" → "Subordinated Debt"

---

## Industry Standardization

### Standard Industry Names

#### Technology & Software
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Software** | Software, Software & Services, Software Services |
| **Information Technology Services** | Information Technology Services, IT Services, Technology Services |
| **High Tech Industries** | High Tech Industries, Technology, Tech |
| **Telecommunications** | Telecommunications, Telecom |

#### Healthcare & Life Sciences
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Healthcare & Pharmaceuticals** | Healthcare & Pharmaceuticals, Healthcare & Pharma, Health Care Equipment & Services, Healthcare Services, Pharmaceuticals, Biotechnology Life Sciences, Pharmaceuticals Biotechnology Life Sciences, Healthcare Products, Health Products, Health Care |
| **Medical Services** | Medical Services, Healthcare Services (when specifically medical services, not pharma) |

#### Financial Services
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Diversified Financial Services** | Diversified Financial Services, Diversified Financials, Financial Services, Finance |
| **Insurance** | Insurance, FIRE: Insurance (FIRE = Finance, Insurance, Real Estate) |
| **Banking & Finance** | Banking, FIRE: Finance |

#### Business Services
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Business Services** | Business Services, Services: Business, Commercial & Professional Services, Professional Services |
| **Consumer Services** | Consumer Services, Services: Consumer |
| **Environmental Industries** | Environmental Industries, Environmental Services |
| **Utilities: Services** | Utilities: Services, Utilities, Utilities: Water |

#### Manufacturing & Industrial
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Aerospace & Defense** | Aerospace & Defense, Aerospace, Defense Manufacturing |
| **Capital Equipment** | Capital Equipment, Equipment Manufacturing |
| **Component Manufacturing** | Component Manufacturing, Components |
| **Automotive** | Automotive, Automobiles & Components |
| **Construction & Building** | Construction & Building, Construction |

#### Consumer Goods
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Consumer Goods: Durable** | Consumer Goods: Durable, Durable Goods, Durables & Apparel |
| **Consumer Goods: Non-Durable** | Consumer Goods: Non-Durable, Non-Durable Goods |
| **Consumer Products** | Consumer Products, Consumer |
| **Retail** | Retail, Retailing |
| **Consumer Services** | Consumer Services (duplicate, but for service companies) |

#### Materials & Chemicals
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Chemicals, Plastics & Rubber** | Chemicals, Plastics & Rubber, Chemicals & Materials |
| **Containers, Packaging & Glass** | Containers, Packaging & Glass, Packaging |
| **Metals & Mining** | Metals, Mining, Metals & Mining |

#### Energy & Utilities
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Energy** | Energy, Energy Electicity (typo - fix to Energy), Oil & Gas, Electicity (standalone typo) |
| **Utilities: Water** | Utilities: Water, Water Utilities |

#### Transportation & Logistics
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Transportation: Cargo** | Transportation: Cargo, Transportation services, Transportation & Logistics, Logistics |
| **Transportation: Passenger** | Transportation: Passenger (if applicable) |

#### Media & Entertainment
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Media: Diversified & Production** | Media: Diversified & Production, Media & Entertainment, Entertainment |
| **Leisure Products & Services** | Leisure Products & Services, Leisure, Hotel, Gaming & Leisure, Hospitality |

#### Food & Beverage
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Food & Beverage** | Beverage, Food & Tobacco, Food & Beverage, Beverages |
| **Restaurant & Food Services** | Restaurant Services, Food Services |

#### Real Estate
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Real Estate** | Real Estate, REIT, Real Estate Services |

#### Investment Vehicles
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Investment Vehicles** | Investment Vehicles, CLO (Collateralized Loan Obligation), BDC Funds |

#### Wholesale & Distribution
| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **Wholesale** | Wholesale, Wholesale Distribution |
| **Distribution** | Distribution, Distribution Services |

### Implementation Notes
- **Mapping priority**: Match longest/most specific industry name first
- **Case-insensitive**: All matching should be case-insensitive
- **Partial matching**: For industries with colons or commas (e.g., "Consumer Goods: Durable"), match the full string first, then fall back to partial matching
- **"FIRE" prefix**: FIRE = Finance, Insurance, Real Estate - map to appropriate standard:
  - "FIRE: Finance" → "Diversified Financial Services"
  - "FIRE: Insurance" → "Insurance"
  - "FIRE: Real Estate" → "Real Estate"
- **Clean up typos**: 
  - "Energy Electicity" → "Energy"
  - "Electicity" (standalone) → "Energy"
- **Keep as-is if no match**: If an industry doesn't match any standard, keep the original value (don't force to "Unknown")
- **Industry suffixes**: Some parsers add numbers (e.g., "Leisure Products & Services 1") - strip trailing numbers/space before matching

---

## Reference Rate Standardization

### Standard Reference Rate Names

| Standard Name | Common Variations to Map |
|--------------|------------------------|
| **SOFR** | SOFR, Secured Overnight Financing Rate, S (in formulas like "S + 5%") |
| **LIBOR** | LIBOR, London Interbank Offered Rate, L (in formulas) |
| **PRIME** | PRIME, Prime Rate, P (in formulas) |
| **EURIBOR** | EURIBOR, Euro Interbank Offered Rate, E (in formulas), SN (sometimes used for EURIBOR) |
| **FED FUNDS** | FED FUNDS, Federal Funds Rate, Federal Funds, F (in formulas) |
| **CDOR** | CDOR, Canadian Dollar Offered Rate, C (in formulas) |
| **BASE RATE** | BASE RATE, Base Rate, Benchmark Rate |

### Implementation Notes
- Standardize all variations to uppercase acronym
- In formulas like "S + 5.25%", "S" means SOFR
- If reference rate cannot be determined, leave blank (don't use "Unknown")

---

## Spread, Floor, and PIK Rate Formatting

### Standard Format
- **All rates should be formatted as percentages with "%" suffix**
- **Examples**: "5.25%", "6.5%", "10%"
- **Decimal precision**: 
  - If original has 2+ decimals, preserve: "5.25%" 
  - If original is whole number, show as: "10%"
  - Remove trailing zeros after 2 decimals: "5.20%" → "5.2%"

### Spread
- Extracted from formulas like "SOFR + 5.25%" → spread: "5.25%"
- If spread is in basis points (e.g., 525 bps), convert to percentage: "525" → "5.25%"

### Floor Rate
- Minimum interest rate floor
- Format: "2%" not "200 basis points"
- If already percentage, use as-is

### PIK Rate
- Payment-in-kind interest rate
- Format: "4.5%" or "0%" if none
- If not present, leave blank (not "0%")

---

## Date Formatting

### Standard Format
- **Acquisition Date**: MM/DD/YYYY (e.g., "04/15/2025")
- **Maturity Date**: MM/DD/YYYY (e.g., "12/31/2030")
- **Normalization**: 
  - Convert 2-digit years to 4-digit: "25" → "2025" (if >= 50, use 19xx)
  - Handle MM/YYYY format: add "/01" for day: "03/2028" → "03/01/2028"

---

## Implementation Strategy

### Phase 1: Create Standardization Module
Create `standardization.py` with:
```python
STANDARD_INVESTMENT_TYPES = {...}  # mapping dict
STANDARD_INDUSTRIES = {...}  # mapping dict
STANDARD_REFERENCE_RATES = {...}  # mapping dict

def standardize_investment_type(raw_type: str) -> str:
    """Map raw investment type to standard name"""
    
def standardize_industry(raw_industry: str) -> str:
    """Map raw industry to standard name"""
    
def standardize_reference_rate(raw_rate: str) -> str:
    """Map raw reference rate to standard name"""
```

### Phase 2: Apply to Parsers
- Import standardization module in each parser
- Apply standardization before writing to CSV
- Preserve original values if needed for debugging

### Phase 3: Validation
- Run all parsers
- Check output CSVs for consistent naming
- Update mappings as new variations are found

---

## Examples

### Investment Type Standardization
```
"First Lien Senior Secured Loan" → "First Lien Debt"
"Unitranche First Lien Term Loan" → "First Lien Debt" (unless explicitly called "Unitranche")
"First Lien Senior Secured Loan - Revolver" → "First Lien Debt - Revolver"
"Common Stock" → "Common Equity"
"Preferred Stock" → "Preferred Equity"
"Subordinated Note" → "Subordinated Debt"
```

### Industry Standardization
```
"Healthcare & Pharmaceuticals" → "Healthcare & Pharmaceuticals" (already standard)
"Health Care Equipment & Services" → "Healthcare & Pharmaceuticals"
"Pharmaceuticals Biotechnology Life Sciences" → "Healthcare & Pharmaceuticals"
"Software & Services" → "Software"
"Services: Business" → "Business Services"
"Consumer Goods: Durable" → "Consumer Goods: Durable" (already standard)
"Energy Electicity" → "Energy" (fix typo)
"FIRE: Finance" → "Diversified Financial Services"
```

### Reference Rate Standardization
```
"S + 5.25%" → reference_rate: "SOFR", spread: "5.25%"
"EURIBOR + 4.5%" → reference_rate: "EURIBOR", spread: "4.5%"
"Prime + 3%" → reference_rate: "PRIME", spread: "3%"
```

---

## Notes for Future Enhancements

1. **Dual Output**: Consider adding `investment_type_original` and `industry_original` columns
2. **Confidence Scores**: Could add confidence scores for standardization (1.0 = exact match, 0.5 = partial match)
3. **Custom Mappings**: Allow company-specific mappings if needed
4. **Validation**: Add validation to catch unmapped values and suggest additions

---

## Maintenance

This document should be updated as:
- New investment types are discovered
- New industry variations are found
- Standard industry classifications change
- New reference rates emerge

Last Updated: [Current Date]
