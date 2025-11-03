#!/usr/bin/env python3
"""
Find how companies map to industries in XBRL
"""

import requests
import re
from collections import defaultdict

url = "https://www.sec.gov/Archives/edgar/data/1287750/000128775025000046/arcc-20250930_htm.xml"
print(f"Downloading...")
headers = {'User-Agent': 'Research Tool contact@example.com'}
response = requests.get(url, headers=headers)
content = response.text

print(f"Downloaded {len(content)} characters\n")

# Extract all contexts
context_pattern = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
contexts = context_pattern.findall(content)

print(f"Total contexts: {len(contexts)}\n")

# Find contexts with industry dimensions
industry_contexts = []
for ctx_id, ctx_content in contexts:
    dims = re.findall(r'<xbrldi:explicitMember[^>]*dimension="([^"]*)"[^>]*>([^<]+)</xbrldi:explicitMember>', ctx_content)
    dims_dict = dict(dims)
    
    # Check for industry-related dimensions
    has_industry = False
    has_company = False
    industry_member = None
    company_member = None
    
    for dim_axis, dim_member in dims_dict.items():
        if 'Industry' in dim_axis or 'Sector' in dim_axis:
            has_industry = True
            industry_member = dim_member
        if 'InvestmentIssuerName' in dim_axis:
            has_company = True
            company_member = dim_member
    
    if has_industry or has_company:
        industry_contexts.append({
            'id': ctx_id,
            'has_industry': has_industry,
            'has_company': has_company,
            'industry': industry_member,
            'company': company_member,
            'all_dims': dims_dict
        })

print(f"Contexts with industry or company info: {len(industry_contexts)}")

# Find contexts with BOTH company and industry
both = [ctx for ctx in industry_contexts if ctx['has_industry'] and ctx['has_company']]
print(f"Contexts with BOTH company AND industry: {len(both)}")

if both:
    print("\nContexts with both company and industry:")
    for ctx in both[:10]:
        print(f"\n  Context {ctx['id']}:")
        print(f"    Company: {ctx['company']}")
        print(f"    Industry: {ctx['industry']}")
        print(f"    All dimensions: {list(ctx['all_dims'].keys())}")

# Look for industry-only contexts
industry_only = [ctx for ctx in industry_contexts if ctx['has_industry'] and not ctx['has_company']]
print(f"\n\nIndustry-only contexts: {len(industry_only)}")
if industry_only:
    # Get unique industries
    industries = set(ctx['industry'] for ctx in industry_only if ctx['industry'])
    print(f"Unique industries found: {len(industries)}")
    for industry in sorted(industries):
        print(f"  {industry}")

# Look for company-only contexts
company_only = [ctx for ctx in industry_contexts if ctx['has_company'] and not ctx['has_industry']]
print(f"\n\nCompany-only contexts: {len(company_only)}")

# Maybe industry is specified in the COMPANY member name itself?
print("\n\nChecking if industry is embedded in company member names...")
industry_keywords = [
    'Software', 'Healthcare', 'Technology', 'Financial', 'Commercial',
    'Professional', 'Services', 'Media', 'Consumer', 'Industrial',
    'Energy', 'Materials', 'Aerospace', 'Automobiles'
]

companies_with_industry_hint = []
for ctx in company_only[:100]:
    company = ctx['company'] or ''
    for keyword in industry_keywords:
        if keyword in company:
            companies_with_industry_hint.append((company, keyword))
            break

print(f"Companies with industry keywords in name: {len(companies_with_industry_hint)}")
for company, keyword in companies_with_industry_hint[:20]:
    print(f"  {company[:80]}: {keyword}")

# Look at facts to see if industry is tagged differently
print("\n\n" + "=" * 60)
print("CHECKING IF INDUSTRY IS IN SEPARATE FACTS")
print("=" * 60)

# Find a sample company context
sample_company_ctx = company_only[0]
print(f"\nSample company context: {sample_company_ctx['id']}")
print(f"Company: {sample_company_ctx['company']}")

# Look for ALL facts referencing this context
fact_pattern = re.compile(rf'<([^>\s:]+:[^>\s]+)[^>]*contextRef="{sample_company_ctx["id"]}"[^>]*>([^<]*)</\1>')
facts = fact_pattern.findall(content)

print(f"\nFacts for this context: {len(facts)}")
for concept, value in facts[:20]:
    if value:
        print(f"  {concept}: {value[:100]}")

# Search for patterns like "schedule axis" or "table axis"
print("\n\n" + "=" * 60)
print("LOOKING FOR SCHEDULE/TABLE DIMENSIONS")
print("=" * 60)

schedule_axes = set()
for ctx_id, ctx_content in contexts:
    dims = re.findall(r'<xbrldi:explicitMember[^>]*dimension="([^"]*)"', ctx_content)
    for dim in dims:
        if 'Schedule' in dim or 'Table' in dim or 'Statement' in dim:
            schedule_axes.add(dim)

print(f"Schedule/Table axes found: {len(schedule_axes)}")
for axis in schedule_axes:
    print(f"  {axis}")









