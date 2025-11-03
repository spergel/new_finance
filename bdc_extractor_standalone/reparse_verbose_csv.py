#!/usr/bin/env python3
import csv
import os
import sys
import re
from verbose_identifier_parser import parse_verbose_identifier


def needs_verbose_parse(company_name: str) -> bool:
    tokens = [
        'Debt Investments', 'Equity Securities', 'Portfolio Company', 'Non-control', 'Non-Control',
        'US Corporate Debt', 'Senior Secured Loans', 'Investments United States', 'First Lien', 'Second Lien',
        'Facility Type', 'All in Rate', 'Benchmark', 'Interest Rate', 'Maturity', 'Issuer Name'
    ]
    company_name = company_name or ''
    return any(tok in company_name for tok in tokens)


def reparse_file(path: str) -> str:
    out_path = path
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames or []
        for row in r:
            cn = row.get('company_name', '')
            if cn and needs_verbose_parse(cn):
                # SLRC-specific pipe correction: force company from 3rd pipe token
                if 'Senior Secured Loans' in cn and '|' in cn:
                    parts = [p.strip() for p in cn.split('|')]
                    if len(parts) >= 3:
                        comp = parts[2].strip().rstrip(',')
                        # Avoid generic tokens
                        if comp.lower().startswith('senior') or comp.lower().startswith('first lien'):
                            comp = parts[-1].strip().rstrip(',')
                        if comp:
                            row['company_name'] = comp

                parsed = parse_verbose_identifier(cn, default_industry=row.get('industry') or None)
                # Update fields
                for k in ['company_name','investment_type','industry','acquisition_date','maturity_date','interest_rate','reference_rate','spread','floor_rate','pik_rate']:
                    if parsed.get(k):
                        row[k] = parsed[k]

                # Normalize spread percents accidentally in bps (e.g., 525%)
                sp = (row.get('spread') or '').strip()
                if sp.endswith('%'):
                    try:
                        v = float(sp[:-1])
                        if v >= 40.0:
                            row['spread'] = f"{v/100:.2f}%".rstrip('0').rstrip('.') + '%'.replace('%%','%')
                    except Exception:
                        pass
            rows.append(row)

    # Write back
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main():
    if len(sys.argv) < 2:
        print('Usage: python reparse_verbose_csv.py <csv1> [<csv2> ...]')
        sys.exit(1)
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print(f'Skip missing: {p}')
            continue
        out = reparse_file(p)
        print(f'Updated: {out}')


if __name__ == '__main__':
    main()


