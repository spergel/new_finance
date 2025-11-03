#!/usr/bin/env python3
"""
BDC Configuration for Batch Processing

This file contains metadata and filing information for all major BDCs.
Update the 'latest_filing' information as new quarters are filed.
"""

BDC_UNIVERSE = [
    {
        "ticker": "ARCC",
        "name": "Ares Capital Corporation",
        "cik": "1287750",
        "status": "complete",
        "latest_filing": {
            "accession": "000128775025000046",
            "filename": "arcc-20250930.htm",
            "period": "Q3 2025",
            "filing_date": "2025-01-23"
        },
        "parser_config": {
            "min_table_rows": 10,
            "header_threshold": 4,
            "industry_detection": "bold",
            "financial_col_offset": {
                "enabled": True,
                "cost": 3,  # Principal + 3
                "fair_value": 6  # Principal + 6
            }
        },
        "output_file": "Ares_Capital_Corporation_html_investments.csv",
        "stats": {
            "investments": 896,
            "industries_pct": 100.0,
            "types_pct": 100.0,
            "dates_pct": 95.8,
            "principal_pct": 99.8,
            "cost_pct": 95.2,
            "fair_value_pct": 94.9
        }
    },
    {
        "ticker": "OBDC",
        "name": "Blue Owl Capital Corp",
        "cik": "1823833",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "MAIN",
        "name": "Main Street Capital Corp",
        "cik": "1396440",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "GBDC",
        "name": "Golub Capital BDC Inc",
        "cik": "1494188",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "BXSL",
        "name": "Blackstone Secured Lending Fund",
        "cik": "1789559",
        "status": "documented",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": "Q2 2025",
            "filing_date": None
        },
        "parser_config": {
            "notes": "Format documented in BDC_TABLE_FORMATS.md"
        },
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "HTGC",
        "name": "Hercules Capital Inc",
        "cik": "1348055",
        "status": "complete",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": "HTGC_Hercules_Capital_investments.csv",
        "stats": {
            "investments": 353,
            "notes": "Successfully extracted"
        }
    },
    {
        "ticker": "FSK",
        "name": "FS KKR Capital Corp",
        "cik": "1422183",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "TSLX",
        "name": "Sixth Street Specialty Lending Inc",
        "cik": "1517389",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "MSDL",
        "name": "Morgan Stanley Direct Lending Fund",
        "cik": "1838426",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "CSWC",
        "name": "Capital Southwest Corp",
        "cik": "1589526",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "MFIC",
        "name": "Midcap Financial Investment Corp",
        "cik": "1534675",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "OCSL",
        "name": "Oaktree Specialty Lending Corp",
        "cik": "1414932",
        "status": "complete",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": "OCSL_Oaktree_Specialty_Lending_investments.csv",
        "stats": {
            "investments": 691,
            "notes": "Successfully extracted"
        }
    },
    {
        "ticker": "GSBD",
        "name": "Goldman Sachs BDC Inc",
        "cik": "1576940",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "TRIN",
        "name": "Trinity Capital Inc",
        "cik": "1525877",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "PSEC",
        "name": "Prospect Capital Corp",
        "cik": "1368874",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "NMFC",
        "name": "New Mountain Finance Corp",
        "cik": "1424838",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "PFLT",
        "name": "PennantPark Floating Rate Capital Ltd",
        "cik": "1403521",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "CGBD",
        "name": "TCG BDC Inc",
        "cik": "1631282",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "BBDC",
        "name": "Barings BDC Inc",
        "cik": "1379785",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "FDUS",
        "name": "Fidus Investment Corp",
        "cik": "1487918",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "SLRC",
        "name": "SLR Investment Corp",
        "cik": "1380438",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "BCSF",
        "name": "Bain Capital Specialty Finance Inc",
        "cik": "1650729",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "GAIN",
        "name": "Gladstone Investment Corp",
        "cik": "1280784",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "TCPC",
        "name": "Blackrock TCP Capital Corp",
        "cik": "1379438",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "CION",
        "name": "CION Investment Corp",
        "cik": "1556593",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    },
    {
        "ticker": "NCDL",
        "name": "Nuveen Churchill Direct Lending Corp",
        "cik": "1822523",
        "status": "pending",
        "latest_filing": {
            "accession": None,
            "filename": None,
            "period": None,
            "filing_date": None
        },
        "parser_config": None,
        "output_file": None,
        "stats": None
    }
]


def get_bdc_by_ticker(ticker: str):
    """Get BDC configuration by ticker symbol."""
    for bdc in BDC_UNIVERSE:
        if bdc['ticker'].upper() == ticker.upper():
            return bdc
    return None


def get_pending_bdcs():
    """Get list of BDCs that haven't been processed yet."""
    return [bdc for bdc in BDC_UNIVERSE if bdc['status'] == 'pending']


def get_completed_bdcs():
    """Get list of BDCs that have been successfully processed."""
    return [bdc for bdc in BDC_UNIVERSE if bdc['status'] == 'complete']


def get_filing_url(bdc: dict) -> str:
    """Generate SEC filing URL for a BDC."""
    if not bdc['latest_filing']['accession'] or not bdc['latest_filing']['filename']:
        return None
    
    return f"https://www.sec.gov/Archives/edgar/data/{bdc['cik']}/{bdc['latest_filing']['accession']}/{bdc['latest_filing']['filename']}"


def print_summary():
    """Print summary of BDC extraction status."""
    total = len(BDC_UNIVERSE)
    complete = len([b for b in BDC_UNIVERSE if b['status'] == 'complete'])
    documented = len([b for b in BDC_UNIVERSE if b['status'] == 'documented'])
    pending = len([b for b in BDC_UNIVERSE if b['status'] == 'pending'])
    
    print(f"\n{'='*60}")
    print(f"BDC EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total BDCs: {total}")
    print(f"  ✅ Complete: {complete} ({100*complete/total:.1f}%)")
    print(f"  📋 Documented: {documented} ({100*documented/total:.1f}%)")
    print(f"  ⏳ Pending: {pending} ({100*pending/total:.1f}%)")
    print(f"{'='*60}\n")
    
    # Show completed
    if complete > 0:
        print("✅ COMPLETED:")
        for bdc in get_completed_bdcs():
            stats = bdc.get('stats', {})
            inv_count = stats.get('investments', 'N/A')
            print(f"  {bdc['ticker']:6s} - {bdc['name']:40s} ({inv_count} investments)")
        print()
    
    # Show next 5 to process
    pending_list = get_pending_bdcs()
    if pending_list:
        print("⏳ NEXT TO PROCESS (Top 5):")
        for i, bdc in enumerate(pending_list[:5], 1):
            print(f"  {i}. {bdc['ticker']:6s} - {bdc['name']}")
        print()


if __name__ == "__main__":
    print_summary()
    
    # Show example usage
    print("\nEXAMPLE USAGE:")
    print("-" * 60)
    arcc = get_bdc_by_ticker("ARCC")
    if arcc:
        print(f"Ticker: {arcc['ticker']}")
        print(f"Name: {arcc['name']}")
        print(f"CIK: {arcc['cik']}")
        print(f"Filing URL: {get_filing_url(arcc)}")
        print(f"Status: {arcc['status']}")









