#!/usr/bin/env python3
"""
Utility script to infer missing investment_type values in extracted CSV outputs.

Heuristics:
- Look for common security keywords embedded in company_name or business_description
  (e.g., "Preferred Shares, Series B", "Class A Units", "Senior Secured Notes").
- Apply the same standardization mappings used by the main parsers.

Run:
    python scripts/fix_unknown_investment_types.py
"""

import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from standardization import standardize_investment_type


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

TYPE_PATTERN = re.compile(
    r'(?:'
    r'First\s+Lien\s+Senior\s+Secured\s+(?:Notes?|Loans?)|'
    r'Second\s+Lien\s+Senior\s+Secured\s+(?:Notes?|Loans?)|'
    r'Second\s+Lien\s+Notes?|'
    r'(?:First|Second)\s+Lien\s+(?:Term\s+Loan|Secured\s+Debt)|'
    r'Senior\s+Secured\s+(?:Notes?|Loan)|'
    r'Subordinated\s+(?:Debt|Note)|'
    r'Subordinated\s+Revolving\s+Loan|'
    r'Subordinated\s+Certificates?|'
    r'Unitranche(?:\s+Loan)?|'
    r'Junior\s+Preferred\s+Shares?(?:,\s*Series\s+[A-Za-z0-9-]+)?|'
    r'Preferred\s+Shares?(?:,\s*Series\s+[A-Za-z0-9-]+)?|'
    r'Preferred\s+Equity|'
    r'Series\s+[A-Za-z0-9-]+\s+Convertible\s+Shares?|'
    r'Series\s+[A-Za-z0-9-]+\s+Shares?|'
    r'Series\s+[A-Za-z0-9-]+\s+Preferred|'
    r'Common\s+Shares?|'
    r'Common\s+Units?|'
    r'Ordinary\s+Shares?|'
    r'Class\s+[A-Za-z0-9-]+\s+Units?|'
    r'Class\s+[A-Za-z0-9-]+\s+Redeemable\s+Shares?|'
    r'Membership\s+Interest(?:s)?(?:,\s*Class\s+[A-Za-z0-9-]+)?|'
    r'Member\s+Interest(?:s)?|'
    r'Limited\s+Partner\s+Interests?|'
    r'Limited\s+Partnership\s+Interests?|'
    r'Simple\s+Agreement\s+for\s+Future\s+Equity|'
    r'Warrants?(?:\s+to\s+Purchase[^\s,]+(?:\s+[^\s,]+)*)?'
    r')',
    re.IGNORECASE,
)


def infer_type_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    match = TYPE_PATTERN.search(text)
    if match:
        candidate = match.group(0).strip()
        return standardize_investment_type(candidate)
    return None


def normalize_company_name(name: str) -> str:
    if not name:
        return ""
    cleaned = re.sub(r'\([^)]*\)', '', name)
    split_pattern = re.compile(
        r',\s*(?:First|Second|Senior|Junior|Subordinated|Preferred|Common|Series|Class|Membership|Member|Limited|Units?|Unit|Ordinary|Simple|Convertible|Warrants?|Notes?|Loan|Loans?|Debt)\b',
        re.IGNORECASE,
    )
    parts = split_pattern.split(cleaned, maxsplit=1)
    base = parts[0] if parts else cleaned
    return re.sub(r'\s+', ' ', base).strip(' ,')


def process_file(csv_path: Path) -> bool:
    df = pd.read_csv(csv_path)
    if "investment_type" not in df.columns:
        return False

    known_type_map = {}
    for idx, row in df.iterrows():
        raw_type = str(row.get("investment_type", "")).strip()
        if raw_type and raw_type.lower() != "unknown":
            base = normalize_company_name(row.get("company_name", ""))
            if base and base not in known_type_map:
                known_type_map[base] = raw_type

    updated = False
    mask = df["investment_type"].fillna("").str.strip().str.lower().eq("unknown")
    if not mask.any():
        return False

    for idx in df[mask].index:
        name = str(df.at[idx, "company_name"]) if "company_name" in df.columns else ""
        desc = str(df.at[idx, "business_description"]) if "business_description" in df.columns else ""
        combined = f"{name} {desc}".strip()
        inferred = infer_type_from_text(combined)
        if not inferred and "investment_notes" in df.columns:
            inferred = infer_type_from_text(str(df.at[idx, "investment_notes"]))
        if not inferred:
            base = normalize_company_name(name)
            inferred = standardize_investment_type(known_type_map.get(base, "") or "")
            if inferred == "Unknown":
                inferred = None
        if not inferred and "context_ref" in df.columns:
            inferred = infer_type_from_text(str(df.at[idx, "context_ref"]))
        if inferred:
            df.at[idx, "investment_type"] = inferred
            updated = True

    if updated:
        df.to_csv(csv_path, index=False)
    return updated


def main() -> None:
    if not OUTPUT_DIR.exists():
        print(f"Output directory not found: {OUTPUT_DIR}")
        return

    files = sorted(OUTPUT_DIR.glob("*_investments.csv"))
    if not files:
        print("No investment CSVs found.")
        return

    total_updated = 0
    for csv_path in files:
        try:
            if process_file(csv_path):
                total_updated += 1
                print(f"Updated investment types in {csv_path.name}")
        except Exception as exc:
            print(f"[WARN] Failed to process {csv_path.name}: {exc}")

    if total_updated == 0:
        print("No updates were necessary.")
    else:
        print(f"Completed. Updated {total_updated} files.")


if __name__ == "__main__":
    main()

