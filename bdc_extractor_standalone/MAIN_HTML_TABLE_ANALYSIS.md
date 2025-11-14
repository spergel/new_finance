# MAIN HTML Table Structure Analysis

## Table Structure (from actual HTML inspection)

Based on `output/main_tables/main_table_10.html`, the MAIN schedule of investments table has the following structure:

### Header Row (Row 2):
- **Column 0**: "Portfolio Company (1) (20)"
- **Column 1**: Empty (or footnote column)
- **Column 2**: "Investment Date (24)"
- **Column 3**: "Business Description"
- **Column 4**: "Type of Investment (2) (3) (15)"
- **Column 5**: "Shares/Units"
- **Column 6**: "Rate"
- **Column 7**: "Maturity Date"
- **Column 8**: "Principal (4)" (but $ sign is in a separate cell)
- **Column 9**: "Cost (4)"
- **Column 10**: "Fair Value (18)"

### Data Rows:

#### Company Header Row (first row for each company):
- **Column 0**: Company name (e.g., "Jensen Jewelers of Idaho, LLC")
- **Column 1**: Empty or footnotes
- **Column 2**: Investment Date (e.g., "November 14, 2006")
- **Column 3**: Business Description (e.g., "Retail Jewelry Store")
- **Column 4**: Empty (investment type comes in next row)
- **Column 5-10**: Empty

#### Investment Detail Rows (subsequent rows with empty Column 0):
- **Column 0**: Empty (company name inherited from previous row)
- **Column 1**: Empty or footnotes
- **Column 2**: Empty (investment date inherited)
- **Column 3**: Empty (business description inherited)
- **Column 4**: Investment Type (e.g., "Secured Debt", "Member Units")
- **Column 5**: Shares/Units (e.g., "627", "743,921")
- **Column 6**: Rate (e.g., "10.00% (Prime+6.75%, Floor 2.00%)", "11.50%", "12.00% (L+11.00%, Floor 1.00%)")
- **Column 7**: Maturity Date (e.g., "11/14/2023", "10/31/2024")
- **Column 8**: Empty or "$" (dollar sign in separate cell)
- **Column 9**: Principal amount (e.g., "3,250", "12,800") - value after $ sign
- **Column 10**: Cost (e.g., "3,227", "12,702")
- **Column 11**: Fair Value (e.g., "3,250", "12,800")

### Key Observations:

1. **Company name** appears only in the first row for each company (Column 0)
2. **Investment Date** and **Business Description** also appear only in the first row (Columns 2 and 3)
3. **Investment Type** appears in Column 4 of detail rows
4. **Rate** column (Column 6) contains complex strings that need parsing:
   - Simple: "11.50%"
   - With reference rate: "10.00% (Prime+6.75%, Floor 2.00%)"
   - With LIBOR: "12.00% (L+11.00%, Floor 1.00%)"
   - PIK rates: "12.00% PIK", "13.00% (10.00% Cash, 3.00% PIK)"
5. **Maturity Date** is in Column 7 (not Column 11 as some parsers assume)
6. **Principal** value is in Column 9 (after $ sign in Column 8)
7. **Cost** is in Column 10
8. **Fair Value** is in Column 11
9. Values are in **thousands** (need to multiply by 1000)
10. There are **subtotal rows** that sum investments for each company (these should be skipped)

### Rate Parsing Examples:

- `"10.00% (Prime+6.75%, Floor 2.00%)"` → interest_rate: "10.00%", reference_rate: "PRIME", spread: "6.75%", floor_rate: "2.00%"
- `"12.00% (L+11.00%, Floor 1.00%)"` → interest_rate: "12.00%", reference_rate: "LIBOR", spread: "11.00%", floor_rate: "1.00%"
- `"11.50%"` → interest_rate: "11.50%"
- `"12.00% PIK"` → interest_rate: "12.00%", pik_rate: "12.00%"
- `"13.00% (10.00% Cash, 3.00% PIK)"` → interest_rate: "13.00%", pik_rate: "3.00%"

### Issues with Current `main_parser.py`:

1. Column detection logic may not correctly identify the MAIN-specific column structure
2. Rate parsing needs to handle the complex format in Column 6
3. Need to properly handle continuation rows (empty Column 0)
4. Need to skip subtotal rows
5. Values need to be multiplied by 1000 (they're in thousands)

