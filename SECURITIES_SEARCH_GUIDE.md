# Securities Filings Search Guide

This guide explains how to use the SEC API client and search tools to find all securities offerings and registrations for any company.

## 🚀 Quick Start

### Simple Search (Recommended)
```bash
python3 search_securities_filings.py <TICKER> [MONTHS_BACK]
```

**Examples:**
```bash
# Search for BW's securities filings over the last 60 months
python3 search_securities_filings.py BW 60

# Search for Apple's securities filings over the last 24 months  
python3 search_securities_filings.py AAPL 24

# Search for Tesla's securities filings over the last 12 months
python3 search_securities_filings.py TSLA 12
```

### Comprehensive Search
```bash
python3 get_all_securities_filings.py
```

## 📋 What Each Tool Does

### 1. `search_securities_filings.py` (Simple & User-Friendly)
- **Purpose**: Quick search for any company's securities filings
- **Features**: 
  - Command-line interface
  - Emoji-based progress indicators
  - Quick analysis of filing contents
  - Summary statistics
- **Searches**: All 424B subtypes + All S-series filings
- **Output**: Clean, readable results with file locations

### 2. `get_all_securities_filings.py` (Comprehensive)
- **Purpose**: Detailed analysis with extensive reporting
- **Features**:
  - Detailed file analysis
  - Content parsing for key information
  - Multiple filing type breakdowns
  - Historical analysis
- **Best for**: Deep research and analysis

### 3. `sec_api_client.py` (Core Library)
- **Purpose**: The underlying SEC API client
- **Features**:
  - Company lookup by ticker
  - Filing downloads with rate limiting
  - Text extraction and cleaning
  - Error handling and retries

## 📊 Filing Types Explained

### 424B Filings (Prospectus Supplements)
- **424B**: Generic prospectus supplements
- **424B1**: Prospectus supplements for certain offerings
- **424B2**: Prospectus supplements for business combinations
- **424B3**: Post-effective amendments to prospectus supplements
- **424B4**: Final terms of the offering
- **424B5**: Prospectus supplements for certain offerings
- **424B7**: Prospectus supplements for business combinations
- **424B8**: Prospectus supplements for certain offerings
- **424B9**: Prospectus supplements for certain offerings

### S-Series Filings (Registration Statements)
- **S-1**: Registration statement for initial public offerings
- **S-3**: Registration statement for seasoned issuers (shelf registration)
- **S-4**: Registration statement for business combinations
- **S-8**: Registration statement for employee benefit plans
- **S-11**: Registration statement for real estate companies
- **S-20**: Registration statement for standardized options

## 🔍 Understanding the Results

### What to Look For:

**424B Filings** = Actual securities offerings
- These show when a company actually sold securities
- Look for dollar amounts, offering types, and dates
- Common types: Common stock, preferred stock, debt, warrants

**S-Series Filings** = Registration statements
- These show what a company is authorized to sell
- S-3 filings are "shelf registrations" that allow future offerings
- Look for registration amounts and authorized security types

### Key Information in Filings:
- **💰 Dollar Amounts**: Total offering size
- **📈 Security Types**: Common stock, preferred stock, debt, warrants
- **📅 Dates**: When offerings occurred
- **🎯 Purpose**: Why the company raised money

## 📁 Output Files

All downloaded filings are saved in organized directories:
- `{ticker}_securities/` - For simple search
- `{ticker}_securities_data/` - For comprehensive search

Each filing includes:
- Complete SEC filing text
- All exhibits and attachments
- Metadata and filing dates

## 🎯 Real-World Examples

### Babcock & Wilcox (BW) Results:
- **15 424B filings** (actual offerings)
- **8 S-series filings** (registrations)
- **Key offerings**: Rights offering ($50M), debt-for-equity exchanges
- **Shelf registration**: $600M authorization for future offerings

### Apple (AAPL) Results:
- **2 424B2 filings** (business combination prospectuses)
- **Key amounts**: $4.5B, $1.5B, $1B offerings
- **No recent S-series filings** (mature company with established registration)

## 🛠️ Advanced Usage

### Custom Time Ranges
```bash
# Search last 5 years
python3 search_securities_filings.py TSLA 60

# Search last 6 months
python3 search_securities_filings.py NVDA 6
```

### Multiple Companies
```bash
# Create a script to search multiple companies
for ticker in AAPL MSFT GOOGL TSLA NVDA; do
    echo "Searching $ticker..."
    python3 search_securities_filings.py $ticker 24
done
```

### Analyzing Specific Filing Types
```bash
# Use the comprehensive tool for detailed analysis
python3 get_all_securities_filings.py
```

## 🔧 Troubleshooting

### Common Issues:
1. **No filings found**: Try increasing the time range
2. **Rate limiting**: The client automatically handles SEC rate limits
3. **File encoding issues**: Some SEC files have encoding problems (handled automatically)
4. **Company not found**: Check the ticker symbol spelling

### Error Messages:
- `Company not found`: Invalid ticker symbol
- `No filings found`: No securities offerings in the time range
- `Error reading file`: File encoding issues (usually still usable)

## 📈 Interpreting Results

### High Activity Companies:
- **Frequent 424B filings**: Regular securities offerings
- **Large S-3 registrations**: Big shelf registrations for future offerings
- **Multiple filing types**: Complex capital structure

### Low Activity Companies:
- **Few 424B filings**: Minimal securities offerings
- **No S-series filings**: No recent registrations
- **Small amounts**: Minor capital raises

### Red Flags:
- **Frequent small offerings**: May indicate financial stress
- **Large debt offerings**: High leverage
- **Rights offerings**: Often dilutive to existing shareholders

## 🎯 Best Practices

1. **Start with simple search**: Use `search_securities_filings.py` first
2. **Check time ranges**: Use longer periods for infrequent filers
3. **Read the filings**: Download and examine the actual documents
4. **Compare companies**: Look at similar companies in the same industry
5. **Track trends**: Monitor filing frequency and amounts over time

## 📚 Additional Resources

- **SEC EDGAR**: https://www.sec.gov/edgar/searchedgar/companysearch
- **Filing Types Guide**: https://www.sec.gov/fast-answers/answersformtypeshtm.html
- **Company Tickers**: https://www.sec.gov/files/company_tickers.json

---

**Happy searching! 🚀** 