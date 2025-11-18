#!/usr/bin/env python3
"""
Simple financials extraction using edgartools directly.
Much simpler than the full FinancialsExtractor.
"""

import os
import json
import sys
from datetime import datetime, timezone, timedelta
import datetime as dt_module
from typing import Dict, Optional

# Add parent directory to path
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas required. Install with: pip install pandas")
    sys.exit(1)

try:
    from edgar import Company, set_identity
    EDGARTOOLS_AVAILABLE = True
except ImportError:
    EDGARTOOLS_AVAILABLE = False
    print("ERROR: edgartools not installed. Install with: pip install edgartools")
    sys.exit(1)

PUBLIC_DATA_DIR = os.path.join(ROOT, 'frontend', 'public', 'data')


def extract_financials_simple(ticker: str, period: str, accession_number: str = None, form_type: str = None) -> Optional[Dict]:
    """Extract financials using edgartools - get quarterly data from specific 10-Q or 10-K filing."""
    try:
        set_identity("bdc-extractor@example.com")
        company = Company(ticker)
        
        # Parse period to get year and quarter
        period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
        year = period_date.year
        month = period_date.month
        
        # Determine if this should be a 10-K (annual) or 10-Q (quarterly)
        # 10-K filings are typically for year-end (Dec 31) and filed in Feb-Apr
        # If form_type is provided, use it; otherwise infer from period date
        if not form_type:
            # Check if period is near year-end (Dec) or early in year (Jan-Mar) - likely annual
            if month == 12 or (month >= 1 and month <= 3):
                # Could be annual - check if we have investment data that indicates form type
                investment_file = os.path.join(PUBLIC_DATA_DIR, ticker.upper(), f"investments_{period}.json")
                if os.path.exists(investment_file):
                    try:
                        with open(investment_file, 'r', encoding='utf-8') as f:
                            inv_data = json.load(f)
                            form_type = inv_data.get('form_type', '10-Q')  # Default to 10-Q if not specified
                    except:
                        form_type = '10-Q'  # Default to quarterly
                else:
                    form_type = '10-Q'  # Default to quarterly
            else:
                form_type = '10-Q'  # Definitely quarterly
        
        target_form = form_type  # '10-Q' or '10-K'
        
        # Determine quarter from month (for 10-Q)
        if month in [1, 2, 3]:
            quarter = 1
        elif month in [4, 5, 6]:
            quarter = 2
        elif month in [7, 8, 9]:
            quarter = 3
        else:
            quarter = 4
        
        if target_form == '10-K':
            print(f"  Looking for 10-K {year} filing for period {period}")
        else:
            print(f"  Looking for 10-Q Q{quarter} {year} filing for period {period}")
        
        # Try to load investment JSON to get accession number
        investment_file = os.path.join(PUBLIC_DATA_DIR, ticker.upper(), f"investments_{period}.json")
        if os.path.exists(investment_file):
            try:
                with open(investment_file, 'r', encoding='utf-8') as f:
                    inv_data = json.load(f)
                    accession_number = inv_data.get('accession_number') or accession_number
                    if accession_number:
                        print(f"  Found accession from investment file: {accession_number}")
            except:
                pass
        
        target_filing = None
        
        # Try using get_filings with year and quarter to get the specific filing
        try:
            from edgar import get_filings
            # Get filings for the specific year and quarter, then filter by ticker
            all_filings = get_filings(year=year, quarter=quarter, form=target_form)
            if all_filings:
                # Filter by ticker/company
                filings = [f for f in all_filings if hasattr(f, 'ticker') and f.ticker == ticker.upper()]
                if not filings:
                    # Try by company name
                    company_name = company.name if hasattr(company, 'name') else None
                    filings = [f for f in all_filings if hasattr(f, 'company') and company_name and company_name.lower() in str(f.company).lower()]
                
                if filings:
                    # Find the filing that matches our period (within 30 days for 10-Q, 90 days for 10-K)
                    max_days = 90 if target_form == '10-K' else 30
                    for filing in filings:
                        try:
                            filing_date = filing.filing_date if hasattr(filing, 'filing_date') else None
                            if filing_date:
                                if isinstance(filing_date, str):
                                    filing_date = dt_module.datetime.strptime(filing_date, '%Y-%m-%d')
                                # Check if filing date is close to period
                                if abs((period_date - filing_date).days) < max_days:
                                    target_filing = filing
                                    if target_form == '10-K':
                                        print(f"  Found annual filing: {filing_date} ({year})")
                                    else:
                                        print(f"  Found quarterly filing: {filing_date} (Q{quarter} {year})")
                                    break
                        except:
                            continue
                    
                    # If no exact match, use the first filing from that quarter/year
                    if not target_filing and len(filings) > 0:
                        target_filing = filings[0]
                        if target_form == '10-K':
                            print(f"  Using first filing from {year}")
                        else:
                            print(f"  Using first filing from Q{quarter} {year}")
        except Exception as e:
            print(f"  Could not use get_filings(year, quarter): {e}")
        
        # Fallback: If we have an accession number, try to find that specific filing
        if not target_filing and accession_number:
            try:
                # Get all filings and find the one with matching accession
                filings_all = company.get_filings(form=target_form)
                for filing in filings_all:
                    filing_acc = getattr(filing, 'accession_number', None) or getattr(filing, 'accession', None)
                    if filing_acc and accession_number in str(filing_acc):
                        target_filing = filing
                        print(f"  Found filing by accession: {accession_number}")
                        break
            except Exception as e:
                print(f"  Could not find filing by accession: {e}")
        
        # Final fallback: find by date
        if not target_filing:
            # Get recent filings of the target form type
            filings = company.get_filings(form=target_form)
            if not filings:
                print(f"  Warning: No {target_form} filings found for {ticker}")
                return None
            
            # Find filing closest to the period date (within 3 months)
            min_diff = float('inf')
            for filing in filings:
                try:
                    filing_date = filing.filing_date if hasattr(filing, 'filing_date') else None
                    if not filing_date:
                        continue
                    if isinstance(filing_date, str):
                        filing_date = dt_module.datetime.strptime(filing_date, '%Y-%m-%d')
                    
                    diff = abs((period_date - filing_date).days)
                    if diff < min_diff and diff < 120:  # Within 4 months
                        min_diff = diff
                        target_filing = filing
                except:
                    continue
            
            if not target_filing:
                print(f"  Warning: No 10-Q filing found near period {period}, using most recent")
                target_filing = filings[0]
        
        filing_date_str = target_filing.filing_date if hasattr(target_filing, 'filing_date') else 'unknown'
        print(f"  Using filing: {filing_date_str}")
        
        # Try to get period end date from filing
        period_end_date = None
        if hasattr(target_filing, 'period_end_date'):
            period_end_date = target_filing.period_end_date
        elif hasattr(target_filing, 'period_end'):
            period_end_date = target_filing.period_end
        elif hasattr(target_filing, 'period'):
            period_end_date = target_filing.period
        
        if period_end_date:
            print(f"  Filing period end: {period_end_date}")
        
        # Get financials from the specific filing - try to access quarterly data
        financials = None
        income_stmt = None
        balance_sheet = None
        cash_flow = None
        
        # Try to get XBRL from filing and extract quarterly facts directly
        xbrl_obj = None
        try:
            xbrl_obj = target_filing.xbrl() if hasattr(target_filing, 'xbrl') else None
            if xbrl_obj:
                print(f"  Got XBRL from filing, trying to extract quarterly facts...")
                # Try to get statements from XBRL
                if hasattr(xbrl_obj, 'income_statement'):
                    income_stmt = xbrl_obj.income_statement()
                elif hasattr(xbrl_obj, 'get_statement'):
                    # Try to get income statement by name
                    try:
                        income_stmt = xbrl_obj.get_statement("Income Statement")
                    except:
                        pass
                if hasattr(xbrl_obj, 'balance_sheet'):
                    balance_sheet = xbrl_obj.balance_sheet()
                if hasattr(xbrl_obj, 'cashflow_statement'):
                    cash_flow = xbrl_obj.cashflow_statement()
        except Exception as e:
            print(f"  Could not get XBRL from filing: {e}")
        
        # Fallback: try financials object
        if not income_stmt:
            try:
                if hasattr(target_filing, 'financials'):
                    financials = target_filing.financials
                elif hasattr(target_filing, 'get_financials'):
                    financials = target_filing.get_financials()
            except Exception as e:
                print(f"  Warning: Could not get financials from filing: {e}")
            
            if financials:
                # Get statements from filing's financials
                if hasattr(financials, 'income_statement'):
                    income_stmt = financials.income_statement()
                if hasattr(financials, 'balance_sheet'):
                    balance_sheet = financials.balance_sheet()
                if hasattr(financials, 'cashflow_statement'):
                    cash_flow = financials.cashflow_statement()
        
        # Final fallback: try company.get_financials()
        if not income_stmt and not balance_sheet:
            financials = company.get_financials()
            if financials:
                if hasattr(financials, 'income_statement'):
                    income_stmt = financials.income_statement()
                if hasattr(financials, 'balance_sheet'):
                    balance_sheet = financials.balance_sheet()
                if hasattr(financials, 'cashflow_statement'):
                    cash_flow = financials.cashflow_statement()
        
        if not income_stmt and not balance_sheet:
            print(f"  Warning: No statement data found for {ticker}")
            return None
        
        if not income_stmt and not balance_sheet:
            print(f"  Warning: No statement data found for {ticker}")
            return None
        
        # Determine form type from filing
        form_type = '10-Q'  # Default to quarterly
        if target_filing:
            filing_form = getattr(target_filing, 'form', None) or (target_filing.__dict__.get('form') if hasattr(target_filing, '__dict__') else None)
            if filing_form:
                form_type = filing_form
            # Also check if it's an annual filing by checking the period
            # Annual filings typically cover full year (Dec 31)
            try:
                period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                # If period is near year-end (Dec) and filing is 10-K, it's annual
                if period_date.month == 12 or (period_date.month == 1 and period_date.day <= 15):
                    # Could be annual - check if we're looking for 10-K
                    if '10-K' in str(filing_form) if filing_form else False:
                        form_type = '10-K'
            except:
                pass
        
        # Build result
        result = {
            'ticker': ticker.upper(),
            'name': company.name if hasattr(company, 'name') else ticker,
            'period': period,
            'period_start': None,
            'period_end': None,
            'filing_date': None,
            'accession_number': None,
            'form_type': form_type,
            'income_statement': {},
            'gains_losses': {},
            'balance_sheet': {},
            'cash_flow_statement': {},
            'shares': {},
            'leverage': {},
            'derived': {},
            'full_income_statement': {},
            'full_cash_flow_statement': {},
            'full_balance_sheet': {},
            'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        
        # Extract income statement
        if income_stmt:
            # Try different methods to get data from Statement object
            df = None
            if hasattr(income_stmt, 'dataframe'):
                df = income_stmt.dataframe()
            elif hasattr(income_stmt, 'df'):
                df = income_stmt.df()
            elif hasattr(income_stmt, 'to_dataframe'):
                df = income_stmt.to_dataframe()
            elif hasattr(income_stmt, 'facts'):
                # If it has facts, convert to dataframe
                facts = income_stmt.facts
                if facts:
                    df = pd.DataFrame(facts)
            
            print(f"  Income statement: {type(income_stmt)}, df type: {type(df)}, df shape: {df.shape if df is not None else 'None'}")
            if df is not None and not df.empty:
                print(f"  Income statement columns: {list(df.columns)}")
                print(f"  Income statement rows: {len(df)}")
                # Check ALL columns - look for quarterly dates
                print(f"  All columns: {df.columns.tolist()}")
                date_cols = [c for c in df.columns if c not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                print(f"  Date columns found: {date_cols}")
                
                # Check if there are any columns with 2025 dates (quarterly)
                quarterly_cols = []
                for col in df.columns:
                    col_str = str(col)
                    if '2025' in col_str or '2024' in col_str:
                        try:
                            # Try to parse as date
                            col_date = dt_module.datetime.strptime(col_str, '%Y-%m-%d')
                            # Check if it's a quarter-end date (Mar 31, Jun 30, Sep 30, Dec 31)
                            if (col_date.month, col_date.day) in [(3, 31), (6, 30), (9, 30), (12, 31)]:
                                quarterly_cols.append(col)
                                print(f"  Found potential quarterly column: {col} ({col_date.date()})")
                        except:
                            pass
                
                if quarterly_cols:
                    print(f"  Quarterly columns identified: {quarterly_cols}")
                
                # Initialize quarterly period column variable
                quarterly_period_col = None
                
                # Calculate expected quarterly period end date
                # For a 10-Q filing, the period end is typically the end of the quarter
                # Q1: Mar 31, Q2: Jun 30, Q3: Sep 30, Q4: Dec 31
                quarter_end_months = {1: 3, 2: 6, 3: 9, 4: 12}
                quarter_end_days = {1: 31, 2: 30, 3: 30, 4: 31}
                expected_q_end = dt_module.datetime(year, quarter_end_months[quarter], quarter_end_days[quarter]).date()
                expected_q_str = str(expected_q_end)
                print(f"  Expected quarterly period end: {expected_q_str} (Q{quarter} {year})")
                
                # Check if this date exists in columns
                if expected_q_str in df.columns:
                    quarterly_period_col = expected_q_str
                    print(f"  Found expected quarterly column: {quarterly_period_col}")
                else:
                    # Try to find any date column that's close to our expected quarter end
                    for col in date_cols:
                        try:
                            col_date = dt_module.datetime.strptime(str(col), '%Y-%m-%d')
                            # Check if within 30 days of expected quarter end
                            if abs((col_date.date() - expected_q_end).days) < 30:
                                quarterly_period_col = col
                                print(f"  Found quarterly column (close match): {quarterly_period_col}")
                                break
                        except:
                            continue
                
                # Continue checking Statement object for periods (don't reset quarterly_period_col if we already found it)
                period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                
                # First, try to get periods from the Statement object
                if hasattr(income_stmt, 'periods'):
                    periods = income_stmt.periods
                    print(f"  Statement.periods: {periods}")
                    if periods:
                        print(f"  Period details: {[str(p) for p in periods[:5]]}")
                        
                        # Find the period that matches our quarterly period
                        for period_obj in periods:
                            try:
                                # Try to get period end date from period object
                                period_end = None
                                if hasattr(period_obj, 'end_date'):
                                    period_end = period_obj.end_date
                                elif hasattr(period_obj, 'endDate'):
                                    period_end = period_obj.endDate
                                elif hasattr(period_obj, 'period_end'):
                                    period_end = period_obj.period_end
                                elif isinstance(period_obj, str):
                                    # Try to parse as date
                                    try:
                                        period_end = dt_module.datetime.strptime(period_obj[:10], '%Y-%m-%d')
                                    except:
                                        pass
                                
                                if period_end:
                                    if isinstance(period_end, str):
                                        period_end = dt_module.datetime.strptime(period_end[:10], '%Y-%m-%d')
                                    
                                    # Check if this period matches our quarterly period (within 30 days)
                                    if abs((period_date - period_end).days) < 30:
                                        # Try to find this period in the dataframe columns
                                        period_str = str(period_end.date())
                                        if period_str in df.columns:
                                            quarterly_period_col = period_str
                                            print(f"  Found quarterly period column: {quarterly_period_col}")
                                            break
                                        # Also try different formats
                                        for col in df.columns:
                                            if col not in ['concept', 'label', 'level', 'abstract', 'dimension']:
                                                if period_str in str(col) or str(col) in period_str:
                                                    quarterly_period_col = col
                                                    print(f"  Found quarterly period column (match): {quarterly_period_col}")
                                                    break
                                        if quarterly_period_col:
                                            break
                            except Exception as e:
                                print(f"  Error checking period: {e}")
                                continue
                
                # If we have XBRL object, try to get facts directly and filter by period
                if not quarterly_period_col and xbrl_obj:
                    try:
                        # Get all facts from XBRL
                        all_facts = xbrl_obj.facts if hasattr(xbrl_obj, 'facts') else None
                        if all_facts:
                            print(f"  Checking XBRL facts for quarterly data...")
                            # Try to find facts with quarterly period
                            # Facts might be a dict or list
                            if isinstance(all_facts, dict):
                                facts_items = all_facts.items()
                            else:
                                facts_items = enumerate(all_facts) if isinstance(all_facts, list) else []
                            
                            # Look for a quarterly date column in the dataframe by checking facts
                            quarterly_dates = set()
                            for fact_key, fact in list(facts_items)[:100]:  # Sample first 100
                                if isinstance(fact, dict):
                                    # Check for period information
                                    fact_period = fact.get('period_end') or fact.get('end_date') or fact.get('endDate')
                                    if fact_period:
                                        try:
                                            if isinstance(fact_period, str):
                                                fact_date = dt_module.datetime.strptime(fact_period[:10], '%Y-%m-%d')
                                            else:
                                                fact_date = fact_period
                                            # If within 30 days of our period, it's quarterly
                                            if abs((period_date - fact_date).days) < 30:
                                                quarterly_dates.add(fact_date.date())
                                        except:
                                            pass
                            
                            # Check if any quarterly dates match dataframe columns
                            for q_date in quarterly_dates:
                                q_str = str(q_date)
                                if q_str in df.columns:
                                    quarterly_period_col = q_str
                                    print(f"  Found quarterly column from XBRL facts: {quarterly_period_col}")
                                    break
                    except Exception as e:
                        print(f"  Error checking XBRL facts: {e}")
                
                # Try to get quarterly data directly from Statement methods
                # Check if Statement has methods to filter by period
                stmt_attrs = [attr for attr in dir(income_stmt) if not attr.startswith('_')]
                print(f"  Statement object attributes: {stmt_attrs}")
                
                # Try get_raw_data() - this might have quarterly data!
                if hasattr(income_stmt, 'get_raw_data'):
                    try:
                        raw_data = income_stmt.get_raw_data()
                        print(f"  get_raw_data() type: {type(raw_data)}, length: {len(raw_data) if hasattr(raw_data, '__len__') else 'N/A'}")
                        if raw_data:
                            if isinstance(raw_data, list) and len(raw_data) > 0:
                                print(f"  Raw data list - checking first item: {type(raw_data[0])}")
                                if isinstance(raw_data[0], dict):
                                    print(f"  First raw data item keys: {list(raw_data[0].keys())}")
                                    # Check the 'values' key - this might contain period-specific data!
                                    sample = raw_data[0]
                                    if 'values' in sample:
                                        values = sample['values']
                                        print(f"  Values type: {type(values)}")
                                        if isinstance(values, dict):
                                            print(f"  Values keys (periods): {list(values.keys())[:10]}")
                                            if not values:
                                                # Values dict is empty - check other items in raw_data
                                                print(f"  First item values dict is empty, checking other items...")
                                                for i, item in enumerate(raw_data[:5]):
                                                    if isinstance(item, dict) and 'values' in item:
                                                        item_values = item['values']
                                                        if isinstance(item_values, dict) and item_values:
                                                            print(f"  Item {i} has values: {list(item_values.keys())[:5]}")
                                                            break
                                            # Check if any of these keys match our quarterly period
                                            period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                                            # Check all items, not just the first one
                                            all_periods = set()
                                            for item in raw_data:
                                                if isinstance(item, dict) and 'values' in item and isinstance(item['values'], dict):
                                                    all_periods.update(item['values'].keys())
                                            all_periods_list = sorted([str(p) for p in all_periods])
                                            print(f"  All periods found in raw_data values ({len(all_periods_list)} total)")
                                            print(f"  Most recent periods: {all_periods_list[-15:]}")  # Show last 15
                                            # Also check for 2025 periods specifically
                                            periods_2025 = [p for p in all_periods_list if '2025' in str(p)]
                                            if periods_2025:
                                                print(f"  2025 periods found: {periods_2025}")
                                            else:
                                                print(f"  No 2025 periods found - checking if period should be 2024")
                                            
                                            for period_key in all_periods:
                                                try:
                                                    period_str = str(period_key)
                                                    # Check if it's a duration string (e.g., "duration_2022-04-01_2022-06-30")
                                                    if 'duration_' in period_str:
                                                        # Extract end date from duration string
                                                        parts = period_str.split('_')
                                                        if len(parts) >= 3:
                                                            end_date_str = parts[-1]  # Last part is end date
                                                            period_key_date = dt_module.datetime.strptime(end_date_str, '%Y-%m-%d')
                                                        else:
                                                            continue
                                                    else:
                                                        # Try to parse period key as date directly
                                                        period_key_date = dt_module.datetime.strptime(period_str[:10], '%Y-%m-%d')
                                                    
                                                    # For Q3 2025, look for Q3 2024 if 2025 not available, or check if period date is actually 2024
                                                    # Check if within 90 days of our period (for quarterly matching)
                                                    # Also check if it's the same quarter in previous year if 2025 not available
                                                    days_diff = abs((period_date - period_key_date).days)
                                                    is_same_quarter = False
                                                    if days_diff > 90:
                                                        # Check if same quarter but different year (e.g., Q3 2024 vs Q3 2025)
                                                        if period_key_date.month in [3, 6, 9, 12] and period_date.month in [3, 6, 9, 12]:
                                                            period_q = (period_key_date.month - 1) // 3 + 1
                                                            target_q = (period_date.month - 1) // 3 + 1
                                                            if period_q == target_q:
                                                                is_same_quarter = True
                                                    
                                                    if days_diff < 90 or is_same_quarter:
                                                        print(f"  Found quarterly period in values: {period_key} (end date: {period_key_date.date()}, days diff: {days_diff})")
                                                        # Extract quarterly data from raw_data - get ALL items with this period
                                                        quarterly_rows = []
                                                        items_checked = 0
                                                        items_with_period = 0
                                                        
                                                        def extract_item_data(item, period_key_str):
                                                            """Recursively extract data from item and its children"""
                                                            rows = []
                                                            if not isinstance(item, dict):
                                                                return rows
                                                            
                                                            # Check if this item has the period
                                                            if 'values' in item and isinstance(item['values'], dict):
                                                                if period_key in item['values']:
                                                                    value = item['values'][period_key]
                                                                    # Include if has a value (even if abstract, as it might have children with actual values)
                                                                    if value is not None:
                                                                        if not (isinstance(value, float) and pd.isna(value)):
                                                                            # Only skip if it's abstract AND has no children (then it's just a header)
                                                                            if not item.get('is_abstract', False) or (item.get('children') and len(item.get('children', [])) == 0):
                                                                                rows.append({
                                                                                    'concept': item.get('concept') or item.get('name'),
                                                                                    'label': item.get('label') or item.get('preferred_label'),
                                                                                    period_key_str: value
                                                                                })
                                                            
                                                            # Also check children recursively
                                                            if 'children' in item and isinstance(item['children'], list):
                                                                for child in item['children']:
                                                                    rows.extend(extract_item_data(child, period_key_str))
                                                            
                                                            return rows
                                                        
                                                        period_key_str = str(period_key)
                                                        for item in raw_data:
                                                            items_checked += 1
                                                            rows = extract_item_data(item, period_key_str)
                                                            if rows:
                                                                items_with_period += len(rows)
                                                                quarterly_rows.extend(rows)
                                                        
                                                        print(f"  Checked {items_checked} items, found {items_with_period} with period {period_key}, {len(quarterly_rows)} rows created")
                                                        if quarterly_rows:
                                                            df = pd.DataFrame(quarterly_rows)
                                                            # Filter out rows with null/NaN values
                                                            period_col = str(period_key)
                                                            if period_col in df.columns:
                                                                df_filtered = df[df[period_col].notna()]
                                                                print(f"  After filtering nulls: {len(df_filtered)} rows")
                                                                if len(df_filtered) > 0:
                                                                    df = df_filtered
                                                            quarterly_period_col = period_col
                                                            print(f"  Rebuilt dataframe with quarterly column: {list(df.columns)}")
                                                            print(f"  Dataframe shape: {df.shape}")
                                                            print(f"  Using quarterly period column: {quarterly_period_col}")
                                                            break
                                                        else:
                                                            print(f"  No data found for period {period_key}, continuing search...")
                                                except:
                                                    continue
                                            
                                            # Fallback: try original logic with first item's values
                                            for period_key, period_value in values.items():
                                                try:
                                                    # Try to parse period key as date
                                                    period_key_date = dt_module.datetime.strptime(str(period_key)[:10], '%Y-%m-%d')
                                                    # Check if within 30 days
                                                    if abs((period_date - period_key_date).days) < 30:
                                                        print(f"  Found quarterly period in values: {period_key} -> {period_value}")
                                                        # Extract quarterly data from raw_data
                                                        quarterly_items = []
                                                        for item in raw_data:
                                                            if isinstance(item, dict) and 'values' in item and isinstance(item['values'], dict):
                                                                if period_key in item['values']:
                                                                    quarterly_items.append({
                                                                        'concept': item.get('concept'),
                                                                        'label': item.get('label'),
                                                                        'value': item['values'][period_key],
                                                                        'period': period_key
                                                                    })
                                                        if quarterly_items:
                                                            print(f"  Extracted {len(quarterly_items)} quarterly items")
                                                            q_df = pd.DataFrame(quarterly_items)
                                                            print(f"  Quarterly dataframe columns: {list(q_df.columns)}")
                                                            # Build a new dataframe with concept/label/value structure
                                                            quarterly_df_dict = {}
                                                            for item in quarterly_items:
                                                                concept = item['concept']
                                                                if concept:
                                                                    quarterly_df_dict[concept] = {
                                                                        'label': item['label'],
                                                                        'concept': concept,
                                                                        'value': item['value'],
                                                                        'period': period_key
                                                                    }
                                                            # Update df to use quarterly period column
                                                            quarterly_period_col = period_key
                                                            print(f"  Found quarterly period column in values: {quarterly_period_col}")
                                                            # Rebuild df with quarterly data
                                                            quarterly_rows = []
                                                            for item in raw_data:
                                                                if isinstance(item, dict) and 'values' in item and isinstance(item['values'], dict):
                                                                    if period_key in item['values']:
                                                                        quarterly_rows.append({
                                                                            'concept': item.get('concept'),
                                                                            'label': item.get('label'),
                                                                            period_key: item['values'][period_key]
                                                                        })
                                                            if quarterly_rows:
                                                                df = pd.DataFrame(quarterly_rows)
                                                                print(f"  Rebuilt dataframe with quarterly column: {list(df.columns)}")
                                                                break
                                                except:
                                                    continue
                                        elif isinstance(values, list):
                                            print(f"  Values is a list with {len(values)} items")
                                            print(f"  First value: {values[0] if values else 'empty'}")
                            elif isinstance(raw_data, pd.DataFrame):
                                print(f"  Raw data columns: {list(raw_data.columns)}")
                                # Check if raw data has quarterly columns
                                raw_date_cols = [c for c in raw_data.columns if '2025' in str(c) or '2024' in str(c)]
                                print(f"  Raw data date columns: {raw_date_cols}")
                                if raw_date_cols:
                                    # Use raw data if it has quarterly columns
                                    df = raw_data
                                    print(f"  Using raw data with quarterly columns")
                            elif isinstance(raw_data, dict):
                                print(f"  Raw data keys: {list(raw_data.keys())[:10]}")
                    except Exception as e:
                        print(f"  Error getting raw data: {e}")
                
                # Try to_dataframe() with different parameters
                if hasattr(income_stmt, 'to_dataframe'):
                    try:
                        # Try to_dataframe with period parameter if it exists
                        q_df = income_stmt.to_dataframe(period=period)
                        if q_df is not None and not q_df.empty:
                            print(f"  to_dataframe(period) columns: {list(q_df.columns)}")
                            if len(q_df.columns) > len(df.columns):
                                df = q_df
                    except TypeError:
                        # to_dataframe doesn't accept period parameter
                        pass
                    except Exception as e:
                        print(f"  Error with to_dataframe(period): {e}")
                
                # Check facts directly - they might have quarterly data with period info
                if hasattr(income_stmt, 'facts'):
                    facts = income_stmt.facts
                    print(f"  Facts type: {type(facts)}")
                    if facts:
                        if isinstance(facts, dict):
                            facts_list = list(facts.values())[:10]  # Sample first 10
                            print(f"  Sample fact keys: {list(facts.keys())[:5]}")
                        elif isinstance(facts, list):
                            facts_list = facts[:10]
                        else:
                            facts_list = []
                        
                        if facts_list:
                            sample_fact = facts_list[0]
                            print(f"  Sample fact type: {type(sample_fact)}")
                            if isinstance(sample_fact, dict):
                                print(f"  Sample fact keys: {list(sample_fact.keys())}")
                                # Look for period-related keys
                                period_keys = [k for k in sample_fact.keys() if 'period' in str(k).lower() or 'date' in str(k).lower()]
                                print(f"  Period-related keys: {period_keys}")
                                if period_keys:
                                    for pk in period_keys:
                                        print(f"    {pk}: {sample_fact.get(pk)}")
                            
                            # Try to extract quarterly facts (those with period_end dates matching our period)
                            period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                            quarterly_facts = []
                            quarterly_dates_found = set()
                            for fact in facts_list:
                                if isinstance(fact, dict):
                                    # Check various period keys
                                    fact_period = (fact.get('period_end') or fact.get('end_date') or 
                                                  fact.get('endDate') or fact.get('period') or
                                                  fact.get('period_end_date'))
                                    if fact_period:
                                        try:
                                            if isinstance(fact_period, str):
                                                fact_date = dt_module.datetime.strptime(fact_period[:10], '%Y-%m-%d')
                                            else:
                                                fact_date = fact_period
                                            quarterly_dates_found.add(fact_date.date())
                                            # Check if within 3 months of our period
                                            if abs((period_date - fact_date).days) < 100:
                                                quarterly_facts.append(fact)
                                        except:
                                            pass
                            
                            print(f"  Unique quarterly dates found in facts: {sorted(quarterly_dates_found)}")
                            
                            if quarterly_facts:
                                print(f"  Found {len(quarterly_facts)} quarterly facts matching period {period}")
                                # Try to create dataframe from quarterly facts
                                try:
                                    q_df = pd.DataFrame(quarterly_facts)
                                    print(f"  Quarterly facts dataframe columns: {list(q_df.columns)}")
                                    # If this has a value column, we might be able to use it
                                    if 'value' in q_df.columns or 'val' in q_df.columns:
                                        print(f"  Quarterly facts dataframe has value column - might be usable")
                                except:
                                    pass
                # Convert dataframe to dict format
                # First determine which column to use for values
                period_col = None
                period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                
                # Priority: 1) quarterly_period_col, 2) period_end_date, 3) closest date column
                if quarterly_period_col:
                    period_col = quarterly_period_col
                    print(f"  Using quarterly period column: {period_col}")
                elif period_end_date:
                    period_end_str = str(period_end_date)
                    if period_end_str in df.columns:
                        period_col = period_end_str
                        print(f"  Matched to filing period_end_date column: {period_col}")
                
                # If not found, try matching to period date or use most recent annual column
                if not period_col:
                    for col in df.columns:
                            if col in ['concept', 'label', 'level', 'abstract', 'dimension']:
                                continue
                            col_str = str(col)
                            # Try exact match or closest date
                            if period in col_str or col_str in period:
                                period_col = col
                                break
                            # Try to match year and quarter - find closest date
                            try:
                                col_date = dt_module.datetime.strptime(col_str, '%Y-%m-%d')
                                # If within 6 months, consider it a match (for quarterly vs annual)
                                days_diff = abs((period_date - col_date).days)
                                if days_diff < 180:
                                    period_col = col
                                    break
                            except:
                                pass
                    
                    # If no period match, try to find quarterly date closest to period
                    if period_col is None:
                        date_cols = []
                        for col in df.columns:
                            if col in ['concept', 'label', 'level', 'abstract', 'dimension']:
                                continue
                            try:
                                col_date = dt_module.datetime.strptime(str(col), '%Y-%m-%d')
                                date_cols.append((col, col_date))
                            except:
                                pass
                        if date_cols:
                            # Find date closest to period (prefer dates before period, i.e., quarterly end dates)
                            period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                            # Sort by proximity to period date
                            date_cols.sort(key=lambda x: abs((period_date - x[1]).days))
                            # Prefer quarterly dates (end of quarter: 3/31, 6/30, 9/30, 12/31)
                            # that are close to but before the period
                            for col, col_date in date_cols:
                                # Check if it's a quarter-end date
                                month_day = (col_date.month, col_date.day)
                                if month_day in [(3, 31), (6, 30), (9, 30), (12, 31)]:
                                    # If it's before or close to period, use it
                                    if col_date <= period_date or abs((period_date - col_date).days) < 100:
                                        period_col = col
                                        break
                            # If no quarter-end found, use closest date
                            if period_col is None:
                                period_col = date_cols[0][0]
                
                # Now loop through dataframe rows to extract values
                for idx, row in df.iterrows():
                    # Try to get concept/label - check different possible column names
                    concept = str(row.get('concept', row.get('tag', row.get('name', idx))))
                    value = row.get('value', row.get('val'))
                    label = str(row.get('label', row.get('description', row.get('concept', concept))))
                    
                    # Get value from the period column we determined
                    if period_col:
                        val = row[period_col] if period_col in row else value
                    else:
                        val = value
                    
                    # Skip if no valid value (handle empty strings, None, NaN)
                    if val is None or val == '' or (isinstance(val, (int, float)) and pd.isna(val)):
                        continue
                    
                    # Convert to float, handling strings
                    try:
                        float_val = float(val) if not pd.isna(val) else None
                    except (ValueError, TypeError):
                        continue
                    
                    # Store in both formats
                    result['income_statement'][concept] = float_val
                    result['full_income_statement'][concept] = {
                        'label': label,
                        'concept': concept,
                        'value': float_val,
                        'period': period
                    }
        
        # Extract balance sheet - use same quarterly extraction logic as income statement
        if balance_sheet:
            df = None
            quarterly_period_col = None
            
            # Try to get dataframe
            if hasattr(balance_sheet, 'dataframe'):
                df = balance_sheet.dataframe()
            elif hasattr(balance_sheet, 'df'):
                df = balance_sheet.df()
            elif hasattr(balance_sheet, 'to_dataframe'):
                df = balance_sheet.to_dataframe()
            elif hasattr(balance_sheet, 'facts'):
                facts = balance_sheet.facts
                if facts:
                    df = pd.DataFrame(facts)
            
            if df is not None and not df.empty:
                # Try to get quarterly data from raw_data (same approach as income statement)
                if hasattr(balance_sheet, 'get_raw_data'):
                    try:
                        raw_data = balance_sheet.get_raw_data()
                        if isinstance(raw_data, list) and len(raw_data) > 0:
                            # Find quarterly period in raw_data values
                            period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                            for item in raw_data:
                                if isinstance(item, dict) and 'values' in item and isinstance(item['values'], dict):
                                    for period_key, period_value in item['values'].items():
                                        if 'duration_' in str(period_key):
                                            try:
                                                # Parse duration string (e.g., "duration_2024-10-01_2024-12-31")
                                                end_date_str = str(period_key).split('_')[-1]
                                                period_key_date = dt_module.datetime.strptime(end_date_str, '%Y-%m-%d')
                                                days_diff = abs((period_date - period_key_date).days)
                                                
                                                # Check if within 90 days (quarterly match)
                                                if days_diff < 90:
                                                    quarterly_period_col = str(period_key)
                                                    print(f"  Found quarterly period for balance sheet: {quarterly_period_col}")
                                                    break
                                            except:
                                                continue
                                    if quarterly_period_col:
                                        break
                        
                        # If we found a quarterly period, extract all items with that period
                        if quarterly_period_col:
                            quarterly_rows = []
                            for item in raw_data:
                                if isinstance(item, dict) and 'values' in item and isinstance(item['values'], dict):
                                    if quarterly_period_col in item['values']:
                                        value = item['values'][quarterly_period_col]
                                        if value is not None and not (isinstance(value, float) and pd.isna(value)):
                                            if not item.get('is_abstract', False):
                                                quarterly_rows.append({
                                                    'concept': item.get('concept') or item.get('name'),
                                                    'label': item.get('label') or item.get('preferred_label'),
                                                    quarterly_period_col: value
                                                })
                            
                            if quarterly_rows:
                                df = pd.DataFrame(quarterly_rows)
                                quarterly_period_col = str(quarterly_period_col)
                                print(f"  Extracted {len(quarterly_rows)} balance sheet items from quarterly period")
                    except Exception as e:
                        print(f"  Error extracting quarterly balance sheet data: {e}")
                
                # Extract from dataframe
                for idx, row in df.iterrows():
                    concept = str(row.get('concept', row.get('name', idx)))
                    label = str(row.get('label', row.get('preferred_label', concept)))
                    
                    # Get value from quarterly period column if found, otherwise try other columns
                    val = None
                    if quarterly_period_col and quarterly_period_col in row:
                        val = row[quarterly_period_col]
                    else:
                        # Try to find period column
                        period_col = None
                        for col in df.columns:
                            if col not in ['concept', 'label', 'level', 'abstract', 'dimension', 'name', 'preferred_label']:
                                if period in str(col) or str(col) in period:
                                    period_col = col
                                    break
                        
                        if period_col:
                            val = row[period_col] if period_col in row else None
                        elif len(df.columns) > 2:
                            # Try first non-metadata column
                            for col in df.columns:
                                if col not in ['concept', 'label', 'level', 'abstract', 'dimension']:
                                    val = row[col] if col in row else None
                                    break
                    
                    if val is None or val == '' or (isinstance(val, (int, float)) and pd.isna(val)):
                        continue
                    
                    try:
                        float_val = float(val) if not pd.isna(val) else None
                    except (ValueError, TypeError):
                        continue
                    
                    result['balance_sheet'][concept] = float_val
                    result['full_balance_sheet'][concept] = {
                        'label': label,
                        'concept': concept,
                        'value': float_val,
                        'period': period
                    }
        
        # Extract cash flow - use same quarterly extraction logic
        if cash_flow:
            df = None
            quarterly_period_col = None
            
            # Try to get dataframe
            if hasattr(cash_flow, 'dataframe'):
                df = cash_flow.dataframe()
            elif hasattr(cash_flow, 'df'):
                df = cash_flow.df()
            elif hasattr(cash_flow, 'to_dataframe'):
                df = cash_flow.to_dataframe()
            elif hasattr(cash_flow, 'facts'):
                facts = cash_flow.facts
                if facts:
                    df = pd.DataFrame(facts)
            
            if df is not None and not df.empty:
                # Try to get quarterly data from raw_data (same approach as income statement)
                if hasattr(cash_flow, 'get_raw_data'):
                    try:
                        raw_data = cash_flow.get_raw_data()
                        if isinstance(raw_data, list) and len(raw_data) > 0:
                            # Find quarterly period in raw_data values
                            period_date = dt_module.datetime.strptime(period, '%Y-%m-%d')
                            for item in raw_data:
                                if isinstance(item, dict) and 'values' in item and isinstance(item['values'], dict):
                                    for period_key, period_value in item['values'].items():
                                        if 'duration_' in str(period_key):
                                            try:
                                                # Parse duration string (e.g., "duration_2024-10-01_2024-12-31")
                                                end_date_str = str(period_key).split('_')[-1]
                                                period_key_date = dt_module.datetime.strptime(end_date_str, '%Y-%m-%d')
                                                days_diff = abs((period_date - period_key_date).days)
                                                
                                                # Check if within 90 days (quarterly match)
                                                if days_diff < 90:
                                                    quarterly_period_col = str(period_key)
                                                    print(f"  Found quarterly period for cash flow: {quarterly_period_col}")
                                                    break
                                            except:
                                                continue
                                    if quarterly_period_col:
                                        break
                        
                        # If we found a quarterly period, extract all items with that period
                        if quarterly_period_col:
                            quarterly_rows = []
                            for item in raw_data:
                                if isinstance(item, dict) and 'values' in item and isinstance(item['values'], dict):
                                    if quarterly_period_col in item['values']:
                                        value = item['values'][quarterly_period_col]
                                        if value is not None and not (isinstance(value, float) and pd.isna(value)):
                                            if not item.get('is_abstract', False):
                                                quarterly_rows.append({
                                                    'concept': item.get('concept') or item.get('name'),
                                                    'label': item.get('label') or item.get('preferred_label'),
                                                    quarterly_period_col: value
                                                })
                            
                            if quarterly_rows:
                                df = pd.DataFrame(quarterly_rows)
                                quarterly_period_col = str(quarterly_period_col)
                                print(f"  Extracted {len(quarterly_rows)} cash flow items from quarterly period")
                    except Exception as e:
                        print(f"  Error extracting quarterly cash flow data: {e}")
                
                # Extract from dataframe
                for idx, row in df.iterrows():
                    concept = str(row.get('concept', row.get('name', idx)))
                    label = str(row.get('label', row.get('preferred_label', concept)))
                    
                    # Get value from quarterly period column if found, otherwise try other columns
                    val = None
                    if quarterly_period_col and quarterly_period_col in row:
                        val = row[quarterly_period_col]
                    else:
                        # Try to find period column
                        period_col = None
                        for col in df.columns:
                            if col not in ['concept', 'label', 'level', 'abstract', 'dimension', 'name', 'preferred_label']:
                                if period in str(col) or str(col) in period:
                                    period_col = col
                                    break
                        
                        if period_col:
                            val = row[period_col] if period_col in row else None
                        elif len(df.columns) > 2:
                            # Try first non-metadata column
                            for col in df.columns:
                                if col not in ['concept', 'label', 'level', 'abstract', 'dimension']:
                                    val = row[col] if col in row else None
                                    break
                    
                    if val is None or val == '' or (isinstance(val, (int, float)) and pd.isna(val)):
                        continue
                    
                    try:
                        float_val = float(val) if not pd.isna(val) else None
                    except (ValueError, TypeError):
                        continue
                    
                    result['cash_flow_statement'] = result.get('cash_flow_statement', {})
                    result['cash_flow_statement'][concept] = float_val
                    result['full_cash_flow_statement'][concept] = {
                        'label': label,
                        'concept': concept,
                        'value': float_val,
                        'period': period
                    }
        
        return result
        
    except Exception as e:
        print(f"  Error extracting financials for {ticker} period {period}: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Extract financials using edgartools directly')
    parser.add_argument('--ticker', required=True, help='Ticker symbol')
    parser.add_argument('--period', required=True, help='Period (YYYY-MM-DD)')
    parser.add_argument('--accession', help='Accession number (optional, will try to find from investment file)')
    args = parser.parse_args()
    
    ticker_dir = os.path.join(PUBLIC_DATA_DIR, args.ticker.upper())
    os.makedirs(ticker_dir, exist_ok=True)
    
    print(f"Extracting financials for {args.ticker} period {args.period}...")
    financials = extract_financials_simple(args.ticker, args.period, args.accession)
    
    if financials:
        output_path = os.path.join(ticker_dir, f"financials_{args.period}.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(financials, f, ensure_ascii=False, indent=2)
        print(f"Saved to {output_path}")

        # Also export CSVs for income, balance, cash flow
        import csv
        def write_stmt_csv(stmt_key: str, filename_prefix: str):
            stmt = financials.get(stmt_key) or {}
            if not isinstance(stmt, dict) or not stmt:
                return None
            csv_path = os.path.join(ticker_dir, f"{filename_prefix}_{args.period}.csv")
            with open(csv_path, 'w', newline='', encoding='utf-8') as cf:
                writer = csv.writer(cf)
                writer.writerow(["key", "label", "concept", "value", "period"])  # header
                for k, v in stmt.items():
                    # v expected: { label, concept, value, period? }
                    label = (v or {}).get('label') if isinstance(v, dict) else ''
                    concept = (v or {}).get('concept') if isinstance(v, dict) else k
                    value = (v or {}).get('value') if isinstance(v, dict) else v
                    per = (v or {}).get('period') if isinstance(v, dict) else financials.get('period')
                    writer.writerow([k, label, concept, value, per])
            print(f"Saved CSV to {csv_path}")
            return csv_path

        write_stmt_csv('full_income_statement', 'income')
        write_stmt_csv('full_balance_sheet', 'balance')
        write_stmt_csv('full_cash_flow_statement', 'cashflow')
    else:
        print(f"Failed to extract financials")
        sys.exit(1)


if __name__ == '__main__':
    main()

