#!/usr/bin/env python3
import requests
import re

url = "https://www.sec.gov/Archives/edgar/data/0001280784/000128078425000041/0001280784-25-000041.txt"
r = requests.get(url, headers={'User-Agent': 'test'})
content = r.text

concepts = set()
for m in re.finditer(r'<(?:us-gaap|rily|dei):([^:>\s]+)[^>]*contextRef', content):
    concepts.add(m.group(1))

income = [c for c in concepts if 'income' in c.lower() or 'investment' in c.lower()]
nav = [c for c in concepts if ('nav' in c.lower() or 'asset' in c.lower() or 'net' in c.lower()) and 'share' in c.lower()]
assets = [c for c in concepts if 'asset' in c.lower() and 'total' in c.lower()]
shares = [c for c in concepts if 'share' in c.lower() and 'outstanding' in c.lower()]
expenses = [c for c in concepts if 'expense' in c.lower() or 'cost' in c.lower()]

print('Income/Investment concepts:', sorted(income)[:30])
print('\nNAV/Asset per share concepts:', sorted(nav)[:20])
print('\nTotal Assets concepts:', sorted(assets)[:20])
print('\nShares Outstanding concepts:', sorted(shares)[:20])
print('\nExpenses concepts:', sorted(expenses)[:20])











