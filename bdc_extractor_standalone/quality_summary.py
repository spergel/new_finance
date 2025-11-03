#!/usr/bin/env python3
import csv
import os
import sys


FIELDS = [
    'acquisition_date', 'maturity_date',
    'interest_rate', 'reference_rate', 'spread', 'floor_rate', 'pik_rate'
]


def summarize_csv(path: str) -> dict:
    total = 0
    counts = {k: 0 for k in FIELDS}
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            total += 1
            for k in FIELDS:
                v = (row.get(k) or '').strip()
                if v:
                    counts[k] += 1
    pct = {k: (counts[k]/total*100 if total else 0.0) for k in FIELDS}
    return {'file': os.path.basename(path), 'total': total, 'counts': counts, 'pct': pct}


def main():
    if len(sys.argv) < 2:
        print('Usage: python quality_summary.py <csv1> [<csv2> ...]')
        sys.exit(1)
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print(f'Skip missing: {p}')
            continue
        s = summarize_csv(p)
        print(f"\n{s['file']}  (rows={s['total']})")
        for k in FIELDS:
            print(f"  {k}: {s['counts'][k]}/{s['total']} ({s['pct'][k]:.1f}%)")


if __name__ == '__main__':
    main()


