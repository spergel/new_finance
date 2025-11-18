# Insider Trading and Ownership Data Extraction

This module extracts insider trading and ownership data from SEC filings for BDCs.

## Features

### 1. **Insider Transactions (Form 4)**
- Extracts insider buy/sell transactions
- Includes transaction dates, shares, prices, and values
- Tracks insider names and titles

### 2. **Ownership Data (DEF 14A Proxy Statements)**
- Extracts ownership tables from proxy statements
- Includes major shareholders and their holdings
- Shows percentage ownership

### 3. **Beneficial Ownership (13D/G)**
- Extracts 5%+ beneficial ownership reports
- Tracks significant shareholders

## Usage

### Standalone Extraction
```bash
# Extract for a single ticker
python bdc_extractor_standalone/insider_ownership_extractor.py ARCC --days-back 365

# Extract for all BDCs
python bdc_extractor_standalone/extract_insider_ownership.py
```

### Integration with Daily Updates
The extractor can be integrated into `daily_update.py` to automatically update insider/ownership data when new filings are available.

## Output Format

Data is saved to JSON files in the `output/` directory:
- `{TICKER}_insider_ownership.json`

Example structure:
```json
{
  "ticker": "ARCC",
  "cik": "0001288840",
  "insider_transactions": [
    {
      "ticker": "ARCC",
      "insider_name": "John Doe",
      "insider_title": "CEO",
      "transaction_date": "2025-01-15",
      "transaction_type": "Buy",
      "shares": 1000.0,
      "price_per_share": 25.50,
      "value": 25500.0,
      "ownership_type": "Direct",
      "filing_date": "2025-01-16",
      "accession_number": "0001288840-25-000001"
    }
  ],
  "ownership": [
    {
      "ticker": "ARCC",
      "owner_name": "Vanguard Group Inc",
      "owner_type": "Institutional",
      "shares_owned": 5000000.0,
      "percent_owned": 12.5,
      "filing_date": "2025-01-10",
      "source_filing": "DEF 14A"
    }
  ],
  "last_updated": "2025-11-17T19:42:27"
}
```

## Implementation Status

### ✅ Completed
- Basic extractor structure
- DEF 14A proxy statement parsing
- Ownership table extraction
- JSON output format
- Batch extraction script

### 🚧 In Progress
- Form 4 insider transaction parsing (needs XML parsing)
- 13D/G beneficial ownership parsing
- Integration with daily_update.py

### 📋 TODO
- Add Form 4 XML parsing (Form 4 filings are in XML format)
- Improve ownership table detection and parsing
- Add institutional holdings from 13F filings
- Create frontend components to display the data
- Add API hooks in frontend to fetch the data

## Technical Notes

### Form 4 Filings
Form 4 filings are submitted by insiders (not the company) and are in XML format. They contain structured data about:
- Transaction codes (P = Purchase, S = Sale, etc.)
- Security information
- Transaction amounts and prices
- Post-transaction holdings

### DEF 14A Proxy Statements
Proxy statements contain ownership tables that list:
- Principal stockholders
- Directors and officers
- Institutional holders
- Share counts and percentages

### 13D/G Filings
These filings are submitted by 5%+ beneficial owners and contain:
- Owner information
- Purpose of transaction
- Source of funds
- Holdings information

## Future Enhancements

1. **Real-time Updates**: Monitor for new Form 4 filings and update immediately
2. **Historical Analysis**: Track insider trading trends over time
3. **Alerts**: Notify when significant insider transactions occur
4. **Visualizations**: Charts showing insider trading activity
5. **Comparison**: Compare insider activity across BDCs

