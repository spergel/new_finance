#!/usr/bin/env python3
"""
Download SOHO's 424B filings to the data folder for manual inspection
"""

import sys
import os
import logging
sys.path.append('.')

from core.sec_api_client import SECAPIClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_soho_424b_filings():
    """Download SOHO's 424B filings to data folder"""

    client = SECAPIClient(data_dir="data")

    print("Downloading SOHO 424B filings...")

    # Get all 424B filings for SOHO (like the filing matcher does)
    all_424b = client.get_all_424b_filings(
        "SOHO",
        max_filings=20,
        filing_variants=['424B5', '424B3', '424B7']  # Only actual equity/preferred issuances
    )

    if not all_424b:
        print("No 424B filings found for SOHO")
        return

    print(f"Found {len(all_424b)} 424B filings for SOHO")

    # Download each filing
    downloaded_files = []
    for i, filing in enumerate(all_424b, 1):
        try:
            print(f"[{i}/{len(all_424b)}] Downloading {filing['form']} from {filing['date']}...")

            # Get content and save to file
            content = client.get_filing_by_accession(
                "SOHO",
                filing['accession'],
                filing['form']
            )

            if content:
                # Save to data folder with readable filename
                filename = f"SOHO_{filing['form']}_{filing['date']}_{filing['accession'].replace('-', '')}.txt"
                filepath = os.path.join("data", filename)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)

                downloaded_files.append(filepath)
                print(f"  [OK] Saved: {filepath}")
            else:
                print(f"  [FAIL] Failed to get content for {filing['accession']}")

        except Exception as e:
            print(f"  [ERROR] Error downloading {filing['accession']}: {e}")

    print(f"\nDownloaded {len(downloaded_files)} SOHO 424B filings to data/ folder:")
    for file_path in downloaded_files:
        print(f"  - {file_path}")

    print("\nYou can now examine these filings manually to see what information we might be missing!")

if __name__ == "__main__":
    download_soho_424b_filings()
