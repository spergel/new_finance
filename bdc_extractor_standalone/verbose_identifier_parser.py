#!/usr/bin/env python3
"""
Verbose Identifier Parser (Shared)

Parses verbose inline strings found in many BDC filings into structured fields:
- company_name
- investment_type
- industry
- acquisition_date
- maturity_date
- interest_rate (coupon)
- reference_rate
- spread
- floor_rate
- pik_rate

Supports common patterns across TRIN, TCPC, SLRC, SAR, RWAY, PSBD, PFLT, MFIC, LRFC, LIEN, ICMB, GSBD, FDUS, CCAP, BCSF.
"""

import re
from typing import Dict, Optional


REF_ALIASES = {
    'S': 'SOFR',
    'SOFR': 'SOFR',
    'C': 'CME',
    'CSA': 'CSA',
    'PRIME': 'Prime',
    'E': 'EURIBOR',
    'EURIBOR': 'EURIBOR',
    'Base Rate': 'Base Rate',
    'P': 'Prime',
    'F': 'Fixed',
}


def _percent(value: str) -> str:
    try:
        v = float(value)
    except Exception:
        return value if value.endswith('%') else f"{value}%"
    if 0 < abs(v) <= 1.0:
        v *= 100.0
    s = f"{v:.4f}".rstrip('0').rstrip('.')
    return f"{s}%"


def parse_verbose_identifier(text: str, default_industry: Optional[str] = None) -> Dict[str, Optional[str]]:
    t = text.replace('\xa0', ' ').strip()
    result: Dict[str, Optional[str]] = {
        'company_name': None,
        'investment_type': None,
        'industry': default_industry,
        'acquisition_date': None,
        'maturity_date': None,
        'interest_rate': None,
        'reference_rate': None,
        'spread': None,
        'floor_rate': None,
        'pik_rate': None,
    }

    # Special case: pipe-delimited rows (e.g., SLRC). Use relaxed threshold (>=2) because CSV may truncate at commas.
    if '|' in t and t.count('|') >= 2:
        tokens = [tok.strip() for tok in t.split('|')]
        # Attempt mapping based on typical order
        # [0]=category, [1]=subtype, [2]=company, [3]=industry, [4]=spread, [5]=floor, [6]=coupon, [7]=acq, [8]=maturity
        try:
            # Pick company token: ideally tokens[2]; fallback to the last token that looks like a name, not a category
            comp = None
            if len(tokens) > 2:
                comp = tokens[2]
            if not comp:
                for tok in tokens:
                    if any(s in tok for s in ['LLC', 'Inc', 'Holdings', 'Partners', 'Buyer', 'Management', 'Company', 'Parent']):
                        comp = tok
                        break
            if not comp and len(tokens) >= 1:
                comp = tokens[-1]
            # Sometimes company token includes LLC etc.; accept as-is
            # industry
            ind = tokens[3] if len(tokens) > 3 else default_industry
            # spread like 'S+525'
            spr = tokens[4] if len(tokens) > 4 else None
            if spr:
                msp = re.match(r'([A-Za-z]+)\s*\+\s*([\d\.]+)', spr)
                if msp:
                    ref = REF_ALIASES.get(msp.group(1).upper(), msp.group(1))
                    result['reference_rate'] = ref
                    # interpret 525 as 5.25
                    spread_val = float(msp.group(2))
                    if spread_val > 40:  # assume bps
                        result['spread'] = _percent(str(spread_val / 100.0))
                    else:
                        result['spread'] = _percent(msp.group(2))
            # floor
            fl = tokens[5] if len(tokens) > 5 else None
            if fl and re.search(r'\d', fl):
                result['floor_rate'] = _percent(re.sub(r'[^\d\.]', '', fl))
            # coupon
            cp = tokens[6] if len(tokens) > 6 else None
            if cp and re.search(r'\d', cp):
                result['interest_rate'] = _percent(re.sub(r'[^\d\.]', '', cp))
            # dates
            acq = tokens[7] if len(tokens) > 7 else None
            mat = tokens[8] if len(tokens) > 8 else None
            if acq and re.search(r'\d', acq):
                result['acquisition_date'] = acq.strip()
            if mat and re.search(r'\d', mat):
                result['maturity_date'] = mat.strip()
            # type from tokens[1] when available and meaningful
            if len(tokens) > 1:
                subtype = tokens[1]
                # normalize common phrases
                if 'First Lien' in subtype and 'revolving' in subtype:
                    result['investment_type'] = 'First Lien Revolving Loan'
                elif 'First Lien' in subtype:
                    result['investment_type'] = 'First Lien Loan'
                elif 'Second Lien' in subtype:
                    result['investment_type'] = 'Second Lien Loan'
                else:
                    result['investment_type'] = subtype
            result['industry'] = ind or result['industry']
            result['company_name'] = comp
            return result
        except Exception:
            # fall through to generic parsing
            pass

    # 1) Extract obvious tokens first
    # Acquisition
    m = re.search(r'(Initial\s+)?Acquisition Date\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})', t, re.IGNORECASE)
    if m:
        result['acquisition_date'] = m.group(2)

    # Maturity: "Maturity Date X" or "Maturity X" or "due X"
    for pat in [
        r'Maturity\s+Date\s+([A-Za-z]+\s+\d{1,2},?\s*\d{4})',
        r'Maturity\s+Date\s+([0-9/]{4,10})',
        r'\bMaturity\s+([0-9/]{4,10})',
        r'\bdue\s+([0-9/]{4,10})'
    ]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            result['maturity_date'] = m.group(1)
            break
    # Pattern like "MM/DD/YYYY Maturity" (CION)
    if not result['maturity_date']:
        m = re.search(r'([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})\s+Maturity\b', t, re.IGNORECASE)
        if m:
            result['maturity_date'] = m.group(1)

    # Industry
    m = re.search(r'\bIndustry\s+([A-Za-z,& ]+?)(?=\s+(Interest|Maturity|Current|All in Rate|Benchmark|Facility|Investment|Type|$))', t, re.IGNORECASE)
    if m:
        result['industry'] = m.group(1).strip()

    # Interest/coupon
    m = re.search(r'(Interest Rate|Total Coupon|All in Rate)\s+([\d\.]+)\s*%?', t, re.IGNORECASE)
    if m:
        result['interest_rate'] = _percent(m.group(2))

    # PIK within coupon
    m = re.search(r'PIK\s+([\d\.]+)\s*%?', t, re.IGNORECASE)
    if m:
        result['pik_rate'] = _percent(m.group(1))

    # Floor
    m = re.search(r'Floor\s+([\d\.]+)\s*%?', t, re.IGNORECASE)
    if m:
        result['floor_rate'] = _percent(m.group(1))

    # Reference + spread: examples "S + 6.50%", "SOFR+575", "3M SOFR+565", "S + 6.50" without percent
    # Patterns like "(S + CSA + 4.25%)" or "S + 4.25%"
    m = re.search(r'\((?:[^)]*?)\b(SOFR|LIBOR|PRIME|Base Rate|EURIBOR|S|E|C)\b\s*\+\s*(?:CSA\s*\+\s*)?([\d\.]+)\s*%\)', t, re.IGNORECASE)
    if not m:
        m = re.search(r'(?:(\b\d+M)\s+)?\b(SOFR|LIBOR|PRIME|Base Rate|EURIBOR|S|E|C)\b\s*\+\s*([\d\.]+)\s*%?', t, re.IGNORECASE)
    if m:
        ref_raw = m.group(1 if m.lastindex == 2 else 2).strip()
        ref_key = REF_ALIASES.get(ref_raw.upper(), ref_raw)
        result['reference_rate'] = ref_key
        spread_val_str = m.group(2 if m.lastindex == 2 else 3)
        try:
            spread_num = float(spread_val_str)
            # Treat large integers as basis points (e.g., 525 -> 5.25%)
            if spread_num >= 40:
                result['spread'] = _percent(str(spread_num / 100.0))
            else:
                result['spread'] = _percent(spread_val_str)
        except Exception:
            result['spread'] = _percent(spread_val_str)

    # Standalone Spread tokens
    if not result['spread']:
        m = re.search(r'\bSpread\s+([\d\.]+)\s*%?', t, re.IGNORECASE)
        if m:
            result['spread'] = _percent(m.group(1))

    # 2) Investment type heuristics
    type_patterns = [
        r'First\s+Lien\s+Senior\s+Secured\s+Loan', r'Second\s+Lien\s+Senior\s+Secured\s+Loan',
        r'First[-\s]lien\s+revolving\s+loan', r'First[-\s]lien\s+loan', r'Second[-\s]lien\s+loan',
        r'Unitranche\s+loan', r'Senior\s+Secured', r'Secured\s+Loan', r'Secured\s+Debt', r'Unsecured\s+Debt',
        r'Warrants?', r'Preferred\s+(?:Stock|Shares|Equity)', r'Common\s+Stock', r'Notes?', r'Term\s+Loan',
        r'Equipment\s+Financing', r'Delayed\s+Draw\s+Term\s+Loan', r'Revolver', r'Credit\s+Facility', r'Note'
    ]
    it = None
    for p in type_patterns:
        mm = re.search(p, t, re.IGNORECASE)
        if mm:
            it = mm.group(0)
            break
    if it:
        result['investment_type'] = it

    # 3) Company name extraction
    # Try after known headings like "Debt Investments <Industry> <Company> ..."
    # Strip common verbose prefixes
    prefix_patterns = [
        r'^Debt Investments\s+', r'^Equity (?:Securities|Investments)\s+', r'^Portfolio Company (?:Debt|Warrant) Investments[\- ]+[^ ]+\s+',
        r'^Investments United States\s+', r'^Non-control(?:led)?/Non-Affiliate(?:d)? Investments\s+', r'^US Corporate Debt\s+',
        r'^Senior Secured Loans\s+'
    ]
    base = t
    for pp in prefix_patterns:
        base = re.sub(pp, '', base, flags=re.IGNORECASE)

    # If pipe present, choose likely company token heuristically
    if '|' in t and not result['company_name']:
        toks = [x.strip() for x in t.split('|')]
        # Prefer token with LLC/Inc./Holdings/Partners or that doesn't contain 'Secured Loans'
        for tok in toks:
            if any(s in tok for s in ['LLC', 'Inc', 'Holdings', 'Partners', 'Buyer', 'Management', 'Company']):
                result['company_name'] = tok
                break
        if not result['company_name'] and len(toks) > 2:
            result['company_name'] = toks[2]
    m = re.match(r'^([A-Z][^,|\(]+?)(?=\s+(?:Investment|Type|First|Second|Unitranche|Senior|Secured|Warrants?|Preferred|Common|Notes?|Term|Revolver|Credit|due|Maturity|\(|\||,))', base)
    if m:
        comp = m.group(1).strip()
        comp = re.sub(r'\s+', ' ', comp).rstrip(',')
        if not result['company_name']:
            result['company_name'] = comp

    return result


