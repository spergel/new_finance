#!/usr/bin/env python3
"""
Utility script to compute non-empty field coverage for investment CSV outputs.

Usage:
    python calc_coverage.py path/to/file.csv [more.csv ...]
    python calc_coverage.py path/to/directory

If a directory is provided, every *.csv file within (non-recursive) is processed.
"""

import argparse
import csv
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_FIELDS: tuple[str, ...] = (
    "business_description",
    "acquisition_date",
    "maturity_date",
    "principal_amount",
    "cost",
    "fair_value",
    "interest_rate",
    "reference_rate",
    "spread",
    "floor_rate",
    "pik_rate",
    "geographic_location",
    "credit_rating",
    "payment_status",
)


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def calc_coverage(rows: Sequence[dict], fields: Sequence[str]) -> list[tuple[str, int, int, float]]:
    total = len(rows)
    results: list[tuple[str, int, int, float]] = []

    for field in fields:
        count = sum(1 for row in rows if (row.get(field) or "").strip())
        pct = (count / total * 100) if total else 0.0
        results.append((field, count, total, pct))

    return results


def emit_report(csv_path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    print(f"\n=== {csv_path} ===")
    total = len(rows)
    print(f"Total rows: {total}")

    if total == 0:
        return

    for field, count, _, pct in calc_coverage(rows, fields):
        print(f"{field}: {count}/{total} ({pct:.1f}%)")


def iter_csv_targets(targets: Sequence[Path]) -> Iterable[Path]:
    for target in targets:
        if target.is_dir():
            for csv_path in sorted(target.glob("*.csv")):
                yield csv_path
        elif target.suffix.lower() == ".csv":
            yield target
        else:
            continue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute non-empty field coverage for CSV investment exports.")
    parser.add_argument("paths", nargs="+", type=Path, help="CSV files or directories to analyze.")
    parser.add_argument(
        "--fields",
        nargs="+",
        default=DEFAULT_FIELDS,
        help="Override default field list.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_paths = list(iter_csv_targets(args.paths))

    if not csv_paths:
        print("No CSV files found to process.")
        return 1

    for csv_path in csv_paths:
        if not csv_path.exists():
            print(f"Skipping missing file: {csv_path}")
            continue

        rows = load_rows(csv_path)
        emit_report(csv_path, rows, args.fields)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

