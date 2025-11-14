#!/usr/bin/env python3
"""
Financial Statements Extractor for BDCs

Extracts key financial metrics from SEC XBRL filings using edgartools:
- Net Asset Value (NAV) per share
- Total Investment Income (TII)
- Net Investment Income (NII) and per share
- Total Expenses
- Net Realized/Unrealized Gains
- Shares Outstanding
- Leverage metrics (debt-to-equity, asset coverage)
- Cash flow metrics
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime, timezone

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

try:
    from edgar import Company, Filing, set_identity
    EDGARTOOLS_AVAILABLE = True
except ImportError:
    EDGARTOOLS_AVAILABLE = False
    Company = None
    Filing = None
    set_identity = None

logger = logging.getLogger(__name__)


class FinancialsExtractor:
    """Extracts financial statement data from XBRL filings using edgartools."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        if not EDGARTOOLS_AVAILABLE:
            raise ImportError("edgartools is required. Install with: pip install edgartools")
        # Set identity from user agent email if present, otherwise use default
        email = user_agent.split()[-1] if "@" in user_agent else "bdc-extractor@example.com"
        try:
            set_identity(email)
        except Exception:
            pass  # Identity may already be set
        self.headers = {'User-Agent': user_agent}
    
    def extract_from_url(self, filing_url: str, ticker: str, company_name: str, 
                        reporting_period: Optional[str] = None) -> Dict:
        """
        Extract financial metrics from XBRL filing using edgartools.
        
        Args:
            filing_url: URL to SEC filing XBRL (.txt file)
            ticker: Stock ticker
            company_name: Company name
            reporting_period: Expected reporting period (YYYY-MM-DD) for validation
        
        Returns:
            Dictionary with financial metrics
        """
        logger.info(f"Extracting financials for {ticker} from {filing_url} (period: {reporting_period})")
        
        try:
            # NEW APPROACH: Use edgartools Filing.xbrl() to get structured XBRL data
            # This is much faster and more reliable than manual regex parsing
            
            # Extract accession number from URL
            import re
            # Try multiple patterns for accession number
            accession = None
            patterns = [
                r'/(\d{10}-\d{2}-\d{6})\.txt',  # Standard format
                r'/(\d{10}-\d{2}-\d{6})',       # Without .txt
                r'(\d{10}-\d{2}-\d{6})',        # Anywhere in URL
            ]
            for pattern in patterns:
                accession_match = re.search(pattern, filing_url)
                if accession_match:
                    accession = accession_match.group(1)
                    break
            
            if accession:
                logger.info(f"Found accession number: {accession}")
                
                # Try to get filing using edgartools
                try:
                    # Get company and find the specific filing
                    logger.info(f"Getting filings for {ticker} using edgartools...")
                    company = Company(ticker)
                    filings = company.get_filings(form=["10-Q", "10-K"])
                    logger.info(f"Found {len(filings)} filings (10-Q/10-K)")
                    
                    # Find filing matching accession number
                    target_filing = None
                    for filing in filings:
                        if hasattr(filing, 'accession_number') and filing.accession_number == accession:
                            target_filing = filing
                            break
                        # Also try matching by URL
                        if hasattr(filing, 'url') and accession in filing.url:
                            target_filing = filing
                            break
                    
                    if target_filing:
                        logger.info(f"Found filing: {target_filing.form} from {target_filing.filing_date}")
                        # Get XBRL data
                        logger.info("Loading XBRL data...")
                        xbrl = target_filing.xbrl()
                        if xbrl:
                            logger.info("✅ Successfully loaded XBRL data using edgartools")
                            result = self._extract_from_xbrl_data(xbrl, ticker, company_name, reporting_period)
                            if result:
                                logger.info("✅ Successfully extracted financials from XBRL data")
                                return result
                            else:
                                logger.warning("XBRL data loaded but extraction returned None")
                        else:
                            logger.warning("Filing.xbrl() returned None")
                    else:
                        logger.warning(f"Could not find filing with accession {accession} in {len(filings)} filings")
                except Exception as e:
                    logger.warning(f"Could not use edgartools Filing.xbrl(): {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    logger.info("Falling back to manual XBRL parsing")
            else:
                logger.warning(f"Could not extract accession number from URL: {filing_url}")
            
            # FALLBACK: Manual XBRL parsing (slower but more compatible)
            import requests
            response = requests.get(filing_url, headers=self.headers)
            response.raise_for_status()
            xbrl_content = response.text
            
            logger.info(f"Downloaded {len(xbrl_content)} characters from {filing_url}")
            
            # Parse XBRL directly from the filing content to get quarterly financials
            result = self._parse_xbrl_financials(xbrl_content, ticker, company_name, reporting_period)
            
            if result:
                return result
            
            # Last fallback: Try edgartools Company.get_financials() - but this gives annual data
            logger.warning(f"Direct XBRL parsing returned no data, falling back to Company.get_financials() (annual data)")
            company = Company(ticker)
            financials = company.get_financials()
            
            if financials:
                income_stmt = financials.income_statement()
                balance_sheet_data = financials.balance_sheet()
                
                result = self._build_financials_from_edgartools(
                    income_stmt, balance_sheet_data, financials, ticker, company_name, reporting_period
                )
                
                # Log that we're using annual data, not quarterly
                if income_stmt and hasattr(income_stmt, 'to_dataframe'):
                    df = income_stmt.to_dataframe()
                    date_cols = [c for c in df.columns if c not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                    if reporting_period and reporting_period not in date_cols:
                        logger.warning(f"Period {reporting_period} not found in annual financials. Available periods: {date_cols}")
                        logger.warning(f"Note: Using annual data because quarterly parsing failed.")
                
                return result
            
            return self._empty_financials(ticker, company_name, reporting_period)
            
        except Exception as e:
            logger.error(f"Error extracting financials for {ticker}: {e}")
            import traceback
            traceback.print_exc()
            # Return empty structure on error
            return self._empty_financials(ticker, company_name, reporting_period)
    
    def _extract_from_xbrl_data(self, xbrl, ticker: str, company_name: str, 
                                reporting_period: Optional[str]) -> Optional[Dict]:
        """
        Extract financials from edgartools XBRLData object.
        This is faster and more reliable than manual regex parsing.
        """
        try:
            # Debug: Check what's available in XBRL object
            logger.debug(f"XBRL object type: {type(xbrl)}")
            logger.debug(f"XBRL object attributes: {dir(xbrl)[:20]}")
            
            # Get financial statements using edgartools' built-in methods
            # Try to get full statements using Company API (better for multi-period data)
            income_stmt_obj = None
            cash_flow_stmt_obj = None
            balance_sheet_obj = None
            
            try:
                # Get Company object for full statement access
                company = Company(ticker)
                if company.facts:
                    # Get quarterly income statement (most recent period)
                    try:
                        income_stmt_obj = company.income_statement(periods=1, annual=False)
                        logger.info("Got full Income Statement from Company API (quarterly)")
                    except Exception as e:
                        logger.debug(f"Could not get quarterly income statement: {e}")
                        try:
                            income_stmt_obj = company.income_statement(periods=1, annual=True)
                            logger.info("Got full Income Statement from Company API (annual)")
                        except:
                            pass
                    
                    # Get quarterly cash flow statement
                    try:
                        cash_flow_stmt_obj = company.cash_flow(periods=1, annual=False)
                        logger.info("Got full Cash Flow Statement from Company API (quarterly)")
                    except Exception as e:
                        logger.debug(f"Could not get quarterly cash flow: {e}")
                        try:
                            cash_flow_stmt_obj = company.cash_flow(periods=1, annual=True)
                            logger.info("Got full Cash Flow Statement from Company API (annual)")
                        except:
                            pass
                    
                    # Get balance sheet
                    try:
                        balance_sheet_obj = company.balance_sheet(periods=1, annual=False)
                        logger.info("Got full Balance Sheet from Company API (quarterly)")
                    except Exception as e:
                        logger.debug(f"Could not get quarterly balance sheet: {e}")
                        try:
                            balance_sheet_obj = company.balance_sheet(periods=1, annual=True)
                            logger.info("Got full Balance Sheet from Company API (annual)")
                        except:
                            pass
            except Exception as e:
                logger.debug(f"Could not get full statements from Company API: {e}")
            
            # BEST APPROACH: Use Company API for quarterly data (this works!)
            # The Company API gives us quarterly statements directly
            logger.info("Trying Company API for quarterly financial statements...")
            company = Company(ticker)
            
            # Get quarterly income statement
            try:
                income_stmt_obj = company.income_statement(periods=1, annual=False)
                logger.info(f"✅ Got quarterly Income Statement: {type(income_stmt_obj)}")
                if hasattr(income_stmt_obj, 'to_dataframe'):
                    df = income_stmt_obj.to_dataframe()
                    logger.info(f"Income statement DataFrame shape: {df.shape}, columns: {list(df.columns)}")
            except Exception as e:
                logger.debug(f"Could not get quarterly income statement: {e}")
                income_stmt_obj = None
            
            # Get quarterly balance sheet
            try:
                balance_sheet_obj = company.balance_sheet(periods=1, annual=False)
                logger.info(f"✅ Got quarterly Balance Sheet: {type(balance_sheet_obj)}")
                if hasattr(balance_sheet_obj, 'to_dataframe'):
                    df = balance_sheet_obj.to_dataframe()
                    logger.info(f"Balance sheet DataFrame shape: {df.shape}, columns: {list(df.columns)}")
            except Exception as e:
                logger.debug(f"Could not get quarterly balance sheet: {e}")
                balance_sheet_obj = None
            
            # Get quarterly cash flow
            try:
                cash_flow_stmt_obj = company.cash_flow(periods=1, annual=False)
                logger.info(f"✅ Got quarterly Cash Flow Statement: {type(cash_flow_stmt_obj)}")
            except Exception as e:
                logger.debug(f"Could not get quarterly cash flow: {e}")
                cash_flow_stmt_obj = None
            
            # Also try to get statements from XBRL object directly (fallback)
            income_stmt_raw = None
            try:
                income_stmt_raw = xbrl.get_statement("Income Statement")
                logger.info("Got Income Statement from XBRL using get_statement()")
            except Exception as e:
                logger.debug(f"Could not get Income Statement: {e}")
                # Try alternative names
                for alt_name in ["Statement of Operations", "Statement of Income", "Operations"]:
                    try:
                        income_stmt_raw = xbrl.get_statement(alt_name)
                        logger.info(f"Got Income Statement using '{alt_name}'")
                        break
                    except:
                        continue
            
            balance_sheet_raw = None
            # Try multiple names for balance sheet
            balance_sheet_names = [
                "Balance Sheet",
                "Statement of Financial Position", 
                "CONSOLIDATEDSTATEMENTSOFASSETSANDLIABILITIES",
                "Consolidated Statements of Assets and Liabilities",
                "Assets and Liabilities"
            ]
            for bs_name in balance_sheet_names:
                try:
                    balance_sheet_raw = xbrl.get_statement(bs_name)
                    logger.info(f"Got Balance Sheet using '{bs_name}'")
                    break
                except Exception as e:
                    logger.debug(f"Could not get Balance Sheet with '{bs_name}': {e}")
                    continue
            
            # Try to get cash flow statement from XBRL
            cash_flow_stmt_raw = None
            cash_flow_names = [
                "Cash Flow Statement",
                "Statement of Cash Flows",
                "CONSOLIDATEDSTATEMENTSOFCASHFLOWS",
                "Consolidated Statements of Cash Flows",
                "Cash Flows"
            ]
            for cf_name in cash_flow_names:
                try:
                    cash_flow_stmt_raw = xbrl.get_statement(cf_name)
                    logger.info(f"Got Cash Flow Statement using '{cf_name}'")
                    break
                except Exception as e:
                    logger.debug(f"Could not get Cash Flow with '{cf_name}': {e}")
                    continue
            
            # Convert statement lists to dict format for easier access
            income_dict = None
            balance_dict = None
            cash_flow_dict = None
            
            if income_stmt_raw:
                logger.info(f"Income statement type: {type(income_stmt_raw)}")
                # Statement can be a list of dicts, a DataFrame, or a Statement object
                income_dict = {}
                
                # Try to convert to DataFrame if it's a Statement object
                if hasattr(income_stmt_raw, 'to_dataframe'):
                    try:
                        df = income_stmt_raw.to_dataframe()
                        logger.info(f"Income statement DataFrame shape: {df.shape}")
                        # Convert DataFrame to dict format
                        for idx, row in df.iterrows():
                            concept = row.get('concept', '') or row.get('name', '')
                            if not concept:
                                continue
                            # Get values from all date columns
                            values = {}
                            for col in df.columns:
                                if col not in ['concept', 'name', 'label', 'level', 'abstract', 'dimension']:
                                    val = row.get(col)
                                    if val is not None and val != '':
                                        values[col] = val
                            if values:
                                income_dict[concept] = values
                        logger.info(f"Converted income statement DataFrame to dict with {len(income_dict)} concepts")
                    except Exception as e:
                        logger.debug(f"Could not convert income statement to DataFrame: {e}")
                
                # Also try list format
                if isinstance(income_stmt_raw, list) and not income_dict:
                    for item in income_stmt_raw:
                        if isinstance(item, dict) and 'concept' in item and 'values' in item:
                            concept = item.get('concept') or item.get('name', '')
                            values = item.get('values', {})
                            # Only include items with actual values
                            if concept and values and isinstance(values, dict) and len(values) > 0:
                                income_dict[concept] = values
                    logger.info(f"Converted income statement list to dict with {len(income_dict)} concepts with values")
                
                if income_dict:
                    # Debug: show sample concepts
                    sample_concepts = list(income_dict.keys())[:10]
                    logger.info(f"Sample income concepts: {sample_concepts}")
            
            if balance_sheet_raw:
                logger.info(f"Balance sheet type: {type(balance_sheet_raw)}")
                balance_dict = {}
                
                # Try to convert to DataFrame if it's a Statement object
                if hasattr(balance_sheet_raw, 'to_dataframe'):
                    try:
                        df = balance_sheet_raw.to_dataframe()
                        logger.info(f"Balance sheet DataFrame shape: {df.shape}")
                        # Convert DataFrame to dict format
                        for idx, row in df.iterrows():
                            concept = row.get('concept', '') or row.get('name', '')
                            if not concept:
                                continue
                            # Get values from all date columns
                            values = {}
                            for col in df.columns:
                                if col not in ['concept', 'name', 'label', 'level', 'abstract', 'dimension']:
                                    val = row.get(col)
                                    if val is not None and val != '':
                                        values[col] = val
                            if values:
                                balance_dict[concept] = values
                        logger.info(f"Converted balance sheet DataFrame to dict with {len(balance_dict)} concepts")
                    except Exception as e:
                        logger.debug(f"Could not convert balance sheet to DataFrame: {e}")
                
                # Also try list format
                if isinstance(balance_sheet_raw, list) and not balance_dict:
                    for item in balance_sheet_raw:
                        if isinstance(item, dict) and 'concept' in item and 'values' in item:
                            concept = item.get('concept') or item.get('name', '')
                            values = item.get('values', {})
                            # Only include items with actual values
                            if concept and values and isinstance(values, dict) and len(values) > 0:
                                balance_dict[concept] = values
                    logger.info(f"Converted balance sheet list to dict with {len(balance_dict)} concepts with values")
                
                if balance_dict:
                    # Debug: show sample concepts
                    sample_concepts = list(balance_dict.keys())[:10]
                    logger.info(f"Sample balance concepts: {sample_concepts}")
            
            if cash_flow_stmt_raw:
                logger.info(f"Cash flow statement type: {type(cash_flow_stmt_raw)}")
                # Statement is a list of dicts with 'concept' and 'values'
                if isinstance(cash_flow_stmt_raw, list):
                    cash_flow_dict = {}
                    for item in cash_flow_stmt_raw:
                        if isinstance(item, dict) and 'concept' in item and 'values' in item:
                            concept = item.get('concept') or item.get('name', '')
                            values = item.get('values', {})
                            # Only include items with actual values
                            if concept and values and isinstance(values, dict) and len(values) > 0:
                                cash_flow_dict[concept] = values
                    logger.info(f"Converted cash flow statement to dict with {len(cash_flow_dict)} concepts with values")
                    # Debug: show sample concepts
                    sample_concepts = list(cash_flow_dict.keys())[:10]
                    logger.info(f"Sample cash flow concepts: {sample_concepts}")
            
            # Also try to get full statements from Company API (for better structure)
            # This is a fallback if XBRL statements don't work well
            if not income_stmt_obj or not cash_flow_stmt_obj:
                try:
                    company = Company(ticker)
                    if company.facts:
                        if not income_stmt_obj:
                            try:
                                income_stmt_obj = company.income_statement(periods=1, annual=False)
                                logger.info("Got full Income Statement from Company API (quarterly)")
                            except:
                                try:
                                    income_stmt_obj = company.income_statement(periods=1, annual=True)
                                    logger.info("Got full Income Statement from Company API (annual)")
                                except:
                                    pass
                        
                        if not cash_flow_stmt_obj:
                            try:
                                cash_flow_stmt_obj = company.cash_flow(periods=1, annual=False)
                                logger.info("Got full Cash Flow Statement from Company API (quarterly)")
                            except:
                                try:
                                    cash_flow_stmt_obj = company.cash_flow(periods=1, annual=True)
                                    logger.info("Got full Cash Flow Statement from Company API (annual)")
                                except:
                                    pass
                except Exception as e:
                    logger.debug(f"Could not get full statements from Company API: {e}")
            
            # Build financials from statement dicts
            if income_dict is not None or balance_dict is not None or cash_flow_dict is not None:
                result = self._build_financials_from_statement_dicts(
                    income_dict, balance_dict, ticker, company_name, reporting_period,
                    income_stmt_obj=income_stmt_obj, cash_flow_stmt_obj=cash_flow_stmt_obj, balance_sheet_obj=balance_sheet_obj,
                    cash_flow_dict=cash_flow_dict
                )
                if result:
                    return result
            
            # Extract facts directly from XBRL if statements not available
            logger.info("Trying to extract facts directly from XBRL")
            # Try to get facts by concept
            try:
                if hasattr(xbrl, 'facts'):
                    facts = xbrl.facts
                    logger.info(f"Got facts from XBRL: {type(facts)}, length: {len(facts) if hasattr(facts, '__len__') else 'N/A'}")
                    if facts:
                        return self._build_financials_from_facts_dict(facts, ticker, company_name, reporting_period)
                elif hasattr(xbrl, 'get_facts'):
                    facts = xbrl.get_facts()
                    logger.info(f"Got facts via get_facts(): {type(facts)}")
                    if facts:
                        return self._build_financials_from_facts_dict(facts, ticker, company_name, reporting_period)
            except Exception as e:
                logger.debug(f"Could not get facts: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting from XBRLData: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _build_financials_from_statement_dicts(self, income_dict, balance_dict, ticker: str,
                                         company_name: str, reporting_period: Optional[str],
                                         income_stmt_obj=None, cash_flow_stmt_obj=None, balance_sheet_obj=None,
                                         cash_flow_dict=None) -> Dict:
        """Build financials from edgartools statement dicts (list of concept dicts) and full statement objects."""
        
        def get_value(stmt_dict, concept_patterns: List[str], preferred_period: Optional[str] = None):
            """Extract value from statement dict matching concept patterns."""
            if not stmt_dict:
                return None
            
            # Try to find concept matching patterns
            for pattern in concept_patterns:
                for concept, values in stmt_dict.items():
                    # Concepts are like 'us-gaap_NetInvestmentIncome' - match after underscore or anywhere
                    concept_lower = concept.lower()
                    pattern_lower = pattern.lower()
                    
                    # Match if pattern is in concept (after removing namespace prefix)
                    if pattern_lower in concept_lower or concept_lower.endswith('_' + pattern_lower):
                        # values is a dict with date keys like 'duration_2025-07-01_2025-09-30' or instant dates
                        if not values:
                            continue
                        
                        # Try to find value matching preferred period
                        # Dates can be:
                        # - 'duration_YYYY-MM-DD_YYYY-MM-DD' (period ending on second date)
                        # - 'instant_YYYY-MM-DD' or just 'YYYY-MM-DD'
                        best_val = None
                        best_date = None
                        
                        if preferred_period:
                            # Extract year-month-day from preferred period
                            try:
                                from datetime import datetime
                                target_date = datetime.strptime(preferred_period, '%Y-%m-%d').date()
                                
                                for date_key, val in values.items():
                                    if val is None:
                                        continue
                                    
                                    # Check if this date key matches our period
                                    # For duration periods: 'duration_2025-07-01_2025-09-30' - check if ends on target date
                                    if date_key.startswith('duration_'):
                                        # Extract end date
                                        parts = date_key.split('_')
                                        if len(parts) >= 3:
                                            end_date_str = parts[-1]
                                            try:
                                                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                                                if end_date == target_date:
                                                    best_val = val
                                                    best_date = date_key
                                                    break  # Exact match found
                                                # Also check if within 7 days
                                                elif abs((end_date - target_date).days) <= 7:
                                                    if best_date is None or abs((end_date - target_date).days) < abs((datetime.strptime(best_date.split('_')[-1], '%Y-%m-%d').date() - target_date).days):
                                                        best_val = val
                                                        best_date = date_key
                                            except:
                                                pass
                                    elif date_key.startswith('instant_') or len(date_key) == 10:
                                        # Instant date
                                        date_str = date_key.replace('instant_', '')[:10]
                                        try:
                                            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                                            if date_obj == target_date:
                                                best_val = val
                                                best_date = date_key
                                                break
                                        except:
                                            pass
                            except:
                                pass
                        
                        # If no match found, get most recent value
                        if best_val is None and values:
                            try:
                                from datetime import datetime
                                date_vals = []
                                for date_key, val in values.items():
                                    if val is None:
                                        continue
                                    try:
                                        # Extract date from key
                                        if date_key.startswith('duration_'):
                                            end_date_str = date_key.split('_')[-1]
                                            date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                                        elif date_key.startswith('instant_'):
                                            date_str = date_key.replace('instant_', '')[:10]
                                            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                                        else:
                                            # Try to parse as date directly
                                            date_obj = datetime.strptime(date_key[:10], '%Y-%m-%d').date()
                                        date_vals.append((date_obj, val))
                                    except:
                                        pass
                                
                                if date_vals:
                                    date_vals.sort(key=lambda x: x[0], reverse=True)
                                    best_val = date_vals[0][1]
                            except:
                                # Last resort: just get first non-null value
                                for val in values.values():
                                    if val is not None:
                                        best_val = val
                                        break
                        
                        if best_val is not None:
                            try:
                                return float(best_val)
                            except:
                                pass
            
            return None
        
        # Extract income statement data
        # First try to get from statement objects (Company API - quarterly data)
        income_data = {}
        
        if income_stmt_obj and hasattr(income_stmt_obj, 'to_dataframe'):
            try:
                df = income_stmt_obj.to_dataframe()
                # Get the most recent quarter column
                quarter_cols = [c for c in df.columns if c not in ['concept', 'name', 'label', 'level', 'abstract', 'dimension', 'depth', 'is_abstract', 'is_total', 'section', 'confidence']]
                if quarter_cols:
                    latest_quarter = quarter_cols[-1]  # Most recent quarter
                    logger.info(f"Using quarterly column for income statement: {latest_quarter}")
                    
                    # Extract values by concept name
                    # Concept is in the DataFrame index
                    for idx, row in df.iterrows():
                        # Get concept from index (it's the index value itself)
                        concept = str(idx).lower()
                        value = row.get(latest_quarter)
                        
                        if pd.notna(value) and value != '' and value != 0:
                            try:
                                value_float = float(value)
                                # Match concepts
                                if 'netinvestmentincome' in concept or 'netinvestmentincomeloss' in concept:
                                    if 'pershare' not in concept and 'per share' not in concept:
                                        if 'net_investment_income' not in income_data or abs(value_float) > abs(income_data.get('net_investment_income', 0)):
                                            income_data['net_investment_income'] = value_float
                                            logger.info(f"Found net_investment_income: {value_float} from concept: {concept}")
                                elif 'interestanddividendincome' in concept or 'grossinvestmentincome' in concept or 'investmentincome' in concept:
                                    if 'total_investment_income' not in income_data or abs(value_float) > abs(income_data.get('total_investment_income', 0)):
                                        income_data['total_investment_income'] = value_float
                                        logger.info(f"Found total_investment_income: {value_float} from concept: {concept}")
                                elif 'operatingexpenses' in concept or 'totalexpenses' in concept:
                                    if 'total_expenses' not in income_data or abs(value_float) > abs(income_data.get('total_expenses', 0)):
                                        income_data['total_expenses'] = abs(value_float)
                                        logger.info(f"Found total_expenses: {abs(value_float)} from concept: {concept}")
                                elif 'managementfee' in concept:
                                    income_data['management_fees'] = value_float
                                    logger.info(f"Found management_fees: {value_float} from concept: {concept}")
                                elif 'incentivefee' in concept:
                                    income_data['incentive_fees'] = value_float
                                    logger.info(f"Found incentive_fees: {value_float} from concept: {concept}")
                                elif 'interestexpense' in concept:
                                    income_data['interest_expense'] = value_float
                                    logger.info(f"Found interest_expense: {value_float} from concept: {concept}")
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                logger.debug(f"Could not extract from income statement DataFrame: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
        # Fallback to dict-based extraction
        if not income_data:
            income_data = {
            'total_investment_income': get_value(income_dict, ['InterestAndDividendIncomeOperating', 'GrossInvestmentIncomeOperating'], reporting_period) or get_value(income_dict, ['InterestAndDividendIncomeOperating', 'GrossInvestmentIncomeOperating'], None),
            'net_investment_income': get_value(income_dict, ['NetInvestmentIncome'], reporting_period) or get_value(income_dict, ['NetInvestmentIncome'], None),
            'net_investment_income_per_share': get_value(income_dict, ['InvestmentCompanyInvestmentIncomeLossPerShare', 'NetInvestmentIncomePerShare'], reporting_period),
            'total_expenses': abs(get_value(income_dict, ['OperatingExpenses'], reporting_period) or 0),
            'management_fees': get_value(income_dict, ['ManagementFeeRevenue', 'ManagementFees'], reporting_period),
            'incentive_fees': get_value(income_dict, ['IncentiveFeeRevenue', 'IncentiveFees'], reporting_period),
            'interest_expense': get_value(income_dict, ['InterestExpense', 'InterestExpenseDebt'], reporting_period),
        }
        
        if income_data.get('total_expenses') == 0:
            income_data['total_expenses'] = None
        
        # Extract gains/losses
        gains_losses = {
            'net_realized_gains': get_value(income_dict, ['NetRealizedGainLossOnInvestments', 'RealizedInvestmentGainsLosses'], reporting_period),
            'net_unrealized_gains': get_value(income_dict, ['NetUnrealizedGainLossOnInvestments', 'UnrealizedGainLossOnInvestments'], reporting_period),
        }
        
        # Extract balance sheet data
        # First try to get from statement objects (Company API - quarterly data)
        balance_data = {}
        
        if balance_sheet_obj and hasattr(balance_sheet_obj, 'to_dataframe'):
            try:
                df = balance_sheet_obj.to_dataframe()
                # Get the most recent quarter column
                quarter_cols = [c for c in df.columns if c not in ['concept', 'name', 'label', 'level', 'abstract', 'dimension', 'depth', 'is_abstract', 'is_total', 'section', 'confidence']]
                if quarter_cols:
                    latest_quarter = quarter_cols[-1]  # Most recent quarter
                    logger.info(f"Using quarterly column for balance sheet: {latest_quarter}")
                    
                    # Extract values by concept name
                    # Concept is in the DataFrame index
                    for idx, row in df.iterrows():
                        # Get concept from index (it's the index value itself)
                        concept = str(idx).lower()
                        
                        value = row.get(latest_quarter)
                        
                        if pd.notna(value) and value != '' and value != 0:
                            try:
                                value_float = float(value)
                                # Match concepts
                                if 'netassetvaluepershare' in concept or 'navpershare' in concept:
                                    balance_data['nav_per_share'] = value_float
                                    logger.info(f"Found nav_per_share: {value_float} from concept: {concept}")
                                elif 'assets' in concept and ('total' in concept or 'liabilitiesandstockholdersequity' in concept):
                                    if 'total_assets' not in balance_data or abs(value_float) > abs(balance_data.get('total_assets', 0)):
                                        balance_data['total_assets'] = value_float
                                        logger.info(f"Found total_assets: {value_float} from concept: {concept}")
                                elif 'liabilities' in concept and 'total' in concept:
                                    balance_data['total_liabilities'] = value_float
                                    logger.info(f"Found total_liabilities: {value_float} from concept: {concept}")
                                elif 'stockholdersequity' in concept or ('equity' in concept and 'stockholders' in concept):
                                    balance_data['total_equity'] = value_float
                                    logger.info(f"Found total_equity: {value_float} from concept: {concept}")
                                elif 'investment' in concept and 'fairvalue' in concept:
                                    balance_data['total_investments'] = value_float
                                    logger.info(f"Found total_investments: {value_float} from concept: {concept}")
                                elif 'cashandcashequivalents' in concept or 'cashandcash' in concept:
                                    balance_data['cash_and_cash_equivalents'] = value_float
                                    logger.info(f"Found cash_and_cash_equivalents: {value_float} from concept: {concept}")
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                logger.debug(f"Could not extract from balance sheet DataFrame: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
        # Fallback to dict-based extraction
        if not balance_data:
            balance_data = {
            'nav_per_share': get_value(balance_dict, ['NetAssetValuePerShare'], reporting_period),
            'total_assets': get_value(balance_dict, ['LiabilitiesAndStockholdersEquity', 'Assets'], reporting_period),
            'total_liabilities': get_value(balance_dict, ['Liabilities'], reporting_period),
            'total_equity': get_value(balance_dict, ['StockholdersEquity', 'Equity'], reporting_period),
            'total_investments': get_value(balance_dict, ['InvestmentOwnedAtFairValue', 'Investments'], reporting_period),
            'cash_and_cash_equivalents': get_value(balance_dict, ['CashAndCashEquivalentsAtCarryingValue'], reporting_period),
        }
        
        # Extract shares
        shares_data = {
            'shares_outstanding': get_value(balance_dict, ['CommonStockSharesOutstanding', 'SharesOutstanding'], reporting_period),
            'weighted_avg_shares': get_value(income_dict, ['WeightedAverageNumberOfSharesOutstandingBasic'], reporting_period),
        }
        
        # Extract leverage
        leverage_data = {
            'total_debt': get_value(balance_dict, ['LongTermDebt', 'Debt', 'NotesPayable'], reporting_period),
            'revolving_credit_facility': get_value(balance_dict, ['RevolvingCreditFacility'], reporting_period),
        }
        
        # Extract full statements if available
        full_income_statement = None
        full_cash_flow_statement = None
        full_balance_sheet = None
        
        # Try to extract from statement objects first (better structure)
        if income_stmt_obj:
            full_income_statement = self._extract_full_statement(income_stmt_obj, reporting_period)
            logger.info(f"Extracted full income statement with {len(full_income_statement) if full_income_statement else 0} line items")
        # Merge with XBRL-derived dict to increase coverage
        if income_dict:
            xbrl_income_full = self._convert_dict_to_full_statement(income_dict, reporting_period)
            if xbrl_income_full:
                full_income_statement = {**(full_income_statement or {}), **xbrl_income_full}
                logger.info(f"Merged XBRL income items; total now {len(full_income_statement)}")
        
        if cash_flow_stmt_obj:
            full_cash_flow_statement = self._extract_full_statement(cash_flow_stmt_obj, reporting_period)
            logger.info(f"Extracted full cash flow statement with {len(full_cash_flow_statement) if full_cash_flow_statement else 0} line items")
        # Merge with XBRL-derived dict to increase coverage
        if cash_flow_dict:
            xbrl_cf_full = self._convert_dict_to_full_statement(cash_flow_dict, reporting_period)
            if xbrl_cf_full:
                full_cash_flow_statement = {**(full_cash_flow_statement or {}), **xbrl_cf_full}
                logger.info(f"Merged XBRL cash flow items; total now {len(full_cash_flow_statement)}")
        
        if balance_sheet_obj:
            full_balance_sheet = self._extract_full_statement(balance_sheet_obj, reporting_period)
            logger.info(f"Extracted full balance sheet with {len(full_balance_sheet) if full_balance_sheet else 0} line items")
        # Merge with XBRL-derived dict to increase coverage
        if balance_dict:
            xbrl_bs_full = self._convert_dict_to_full_statement(balance_dict, reporting_period)
            if xbrl_bs_full:
                full_balance_sheet = {**(full_balance_sheet or {}), **xbrl_bs_full}
                logger.info(f"Merged XBRL balance sheet items; total now {len(full_balance_sheet)}")
        
        # Build result
        result = {
            'ticker': ticker.upper(),
            'name': company_name,
            'period': reporting_period,
            'period_start': None,
            'period_end': None,
            'filing_date': None,
            'accession_number': None,
            'income_statement': income_data,
            'gains_losses': gains_losses,
            'balance_sheet': balance_data,
            'shares': shares_data,
            'leverage': leverage_data,
            'derived': self._calculate_derived_metrics({
                'income_statement': income_data,
                'balance_sheet': balance_data,
                'leverage': leverage_data,
                'shares': shares_data,
            }),
            # Full statements (if available)
            'full_income_statement': full_income_statement,
            'full_cash_flow_statement': full_cash_flow_statement,
            'full_balance_sheet': full_balance_sheet,
            'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
        }
        
        return result
    
    def _extract_full_statement(self, statement_obj, reporting_period: Optional[str]) -> Optional[Dict]:
        """Extract full statement data from edgartools statement object."""
        try:
            if not statement_obj:
                return None
            
            # Get periods from statement
            periods = []
            if hasattr(statement_obj, 'periods'):
                periods = statement_obj.periods
            elif hasattr(statement_obj, 'get_periods'):
                periods = statement_obj.get_periods()
            
            # Find the period that matches our reporting period
            target_period = None
            if reporting_period and periods:
                # Try to find exact match or closest match
                for period in periods:
                    if reporting_period in str(period) or str(period) in reporting_period:
                        target_period = period
                        break
                # If no match, use most recent period
                if not target_period and periods:
                    target_period = periods[0]
            
            # Extract all line items
            statement_data = {}
            
            # Try different methods to iterate through statement items
            if hasattr(statement_obj, 'iter_with_values'):
                # Standard edgartools method
                for item in statement_obj.iter_with_values():
                    concept = getattr(item, 'concept', None) or getattr(item, 'name', None)
                    label = getattr(item, 'label', None) or str(concept)
                    
                    if concept:
                        # Get value for target period
                        value = None
                        if target_period:
                            if hasattr(item, 'values') and isinstance(item.values, dict):
                                value = item.values.get(target_period)
                            elif hasattr(item, 'get_value'):
                                value = item.get_value(target_period)
                        
                        # If no value for target period, try to get latest available
                        if value is None and hasattr(item, 'values') and isinstance(item.values, dict):
                            for period in periods:
                                if period in item.values:
                                    value = item.values[period]
                                    break
                        
                        if value is not None or concept:  # Include even if value is None to show structure
                            statement_data[concept] = {
                                'label': label,
                                'concept': concept,
                                'value': float(value) if value is not None else None,
                                'period': str(target_period) if target_period else None,
                                'depth': getattr(item, 'depth', 0),
                                'is_total': getattr(item, 'is_total', False),
                            }
            
            elif hasattr(statement_obj, '__iter__'):
                # Fallback: iterate directly
                for item in statement_obj:
                    if isinstance(item, dict):
                        concept = item.get('concept') or item.get('name')
                        label = item.get('label') or str(concept)
                        values = item.get('values', {})
                        
                        if concept:
                            value = None
                            if target_period and target_period in values:
                                value = values[target_period]
                            elif values:
                                # Get first available value
                                value = list(values.values())[0] if values else None
                            
                            statement_data[concept] = {
                                'label': label,
                                'concept': concept,
                                'value': float(value) if value is not None else None,
                                'period': str(target_period) if target_period else None,
                            }
            
            return statement_data if statement_data else None
            
        except Exception as e:
            logger.error(f"Error extracting full statement: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _convert_dict_to_full_statement(self, stmt_dict: Dict, reporting_period: Optional[str]) -> Optional[Dict]:
        """Convert statement dict (concept -> values) to full statement format."""
        if not stmt_dict:
            return None
        
        statement_data = {}
        
        for concept, values in stmt_dict.items():
            if not isinstance(values, dict):
                continue
            
            # Get value for reporting period
            value = None
            if reporting_period:
                # Try to match by date
                for date_key, val in values.items():
                    if reporting_period in str(date_key) or str(date_key) in reporting_period:
                        value = val
                        break
                    # For duration periods, check if reporting period is within range
                    if date_key.startswith('duration_'):
                        parts = date_key.split('_')
                        if len(parts) >= 3:
                            start_date = parts[1]
                            end_date = parts[2]
                            if start_date <= reporting_period <= end_date:
                                value = val
                                break
            
            # If no match, get most recent value
            if value is None and values:
                try:
                    from datetime import datetime
                    date_vals = []
                    for date_key, val in values.items():
                        if val is None:
                            continue
                        try:
                            if date_key.startswith('duration_'):
                                end_date_str = date_key.split('_')[-1]
                                date_obj = datetime.strptime(end_date_str, '%Y-%m-%d')
                            elif date_key.startswith('instant_'):
                                date_str = date_key.replace('instant_', '')[:10]
                                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                            else:
                                date_obj = datetime.strptime(date_key[:10], '%Y-%m-%d')
                            date_vals.append((date_obj, val))
                        except:
                            pass
                    
                    if date_vals:
                        date_vals.sort(key=lambda x: x[0], reverse=True)
                        value = date_vals[0][1]
                except:
                    # Last resort: get first value
                    value = list(values.values())[0] if values else None
            
            # Clean concept name (remove namespace prefix)
            clean_concept = concept.replace('us-gaap_', '').replace('dei_', '')
            
            # Convert value to float, handling None and empty strings
            float_value = None
            if value is not None and value != '':
                try:
                    float_value = float(value)
                except (ValueError, TypeError):
                    float_value = None
            
            statement_data[clean_concept] = {
                'label': clean_concept.replace('_', ' ').title(),
                'concept': concept,
                'value': float_value,
                'period': reporting_period,
            }
        
        return statement_data if statement_data else None
    
    def _build_financials_from_dataframes(self, income_df, balance_df, ticker: str, 
                                         company_name: str, reporting_period: Optional[str]) -> Dict:
        """Build financials dictionary from pandas DataFrames."""
        
        def get_value(df, concept_patterns: List[str], preferred_period: Optional[str] = None):
            """Extract value from dataframe matching concept patterns."""
            if df is None or (hasattr(df, 'empty') and df.empty):
                return None
            
            if not PANDAS_AVAILABLE:
                return None
            
            # Find date columns
            date_cols = [c for c in df.columns if c not in ['concept', 'label', 'level', 'abstract', 'dimension']]
            if not date_cols:
                return None
            
            # Select period column
            date_col = preferred_period if preferred_period and preferred_period in date_cols else date_cols[-1]
            
            # Try to find concept
            for pattern in concept_patterns:
                matches = df[df['concept'].str.contains(pattern, case=False, na=False)]
                if not matches.empty:
                    val = matches.iloc[0][date_col]
                    if pd.notna(val) and val != 0:
                        return float(val)
            return None
        
        # Extract income statement data
        income_data = {
            'total_investment_income': get_value(income_df, ['InterestAndDividendIncomeOperating', 'GrossInvestmentIncomeOperating'], reporting_period),
            'net_investment_income': get_value(income_df, ['NetInvestmentIncome'], reporting_period),
            'net_investment_income_per_share': get_value(income_df, ['InvestmentCompanyInvestmentIncomeLossPerShare', 'NetInvestmentIncomePerShare'], reporting_period),
            'total_expenses': abs(get_value(income_df, ['OperatingExpenses'], reporting_period) or 0),
            'management_fees': get_value(income_df, ['ManagementFeeRevenue', 'ManagementFees'], reporting_period),
            'incentive_fees': get_value(income_df, ['IncentiveFeeRevenue', 'IncentiveFees'], reporting_period),
            'interest_expense': get_value(income_df, ['InterestExpense', 'InterestExpenseDebt'], reporting_period),
        }
        
        if income_data['total_expenses'] == 0:
            income_data['total_expenses'] = None
        
        # Extract gains/losses
        gains_losses = {
            'net_realized_gains': get_value(income_df, ['NetRealizedGainLossOnInvestments', 'RealizedInvestmentGainsLosses'], reporting_period),
            'net_unrealized_gains': get_value(income_df, ['NetUnrealizedGainLossOnInvestments', 'UnrealizedGainLossOnInvestments'], reporting_period),
        }
        
        # Extract balance sheet data
        balance_data = {
            'nav_per_share': get_value(balance_df, ['NetAssetValuePerShare'], reporting_period),
            'total_assets': get_value(balance_df, ['LiabilitiesAndStockholdersEquity', 'Assets'], reporting_period),
            'total_liabilities': get_value(balance_df, ['Liabilities'], reporting_period),
            'total_equity': get_value(balance_df, ['StockholdersEquity', 'Equity'], reporting_period),
            'total_investments': get_value(balance_df, ['InvestmentOwnedAtFairValue', 'Investments'], reporting_period),
            'cash_and_cash_equivalents': get_value(balance_df, ['CashAndCashEquivalentsAtCarryingValue'], reporting_period),
        }
        
        # Extract shares
        shares_data = {
            'shares_outstanding': get_value(balance_df, ['CommonStockSharesOutstanding', 'SharesOutstanding'], reporting_period),
            'weighted_avg_shares': get_value(income_df, ['WeightedAverageNumberOfSharesOutstandingBasic'], reporting_period),
        }
        
        # Extract leverage
        leverage_data = {
            'total_debt': get_value(balance_df, ['LongTermDebt', 'Debt', 'NotesPayable'], reporting_period),
            'revolving_credit_facility': get_value(balance_df, ['RevolvingCreditFacility'], reporting_period),
        }
        
        # Build result
        result = {
            'ticker': ticker.upper(),
            'name': company_name,
            'period': reporting_period,
            'period_start': None,
            'period_end': None,
            'filing_date': None,
            'accession_number': None,
            'income_statement': income_data,
            'gains_losses': gains_losses,
            'balance_sheet': balance_data,
            'shares': shares_data,
            'leverage': leverage_data,
            'derived': self._calculate_derived_metrics({
                'income_statement': income_data,
                'balance_sheet': balance_data,
                'leverage': leverage_data,
                'shares': shares_data,
            }),
            'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
        }
        
        return result
    
    def _build_financials_from_facts_dict(self, facts, ticker: str, company_name: str, 
                                          reporting_period: Optional[str]) -> Optional[Dict]:
        """Build financials from edgartools FactsView object."""
        try:
            # FactsView is iterable and has concept/value pairs
            # Convert to a dict for easier lookup
            facts_dict = {}
            
            # Extract period from reporting_period if provided
            target_date = None
            if reporting_period:
                try:
                    from datetime import datetime
                    target_date = datetime.strptime(reporting_period, '%Y-%m-%d').date()
                except:
                    pass
            
            # FactsView might need to be converted or accessed differently
            # Try different ways to access facts
            facts_list = None
            try:
                if hasattr(facts, 'to_list'):
                    facts_list = facts.to_list()
                elif hasattr(facts, 'to_dict'):
                    facts_dict_raw = facts.to_dict()
                    # Convert dict format to our format
                    for key, value in facts_dict_raw.items():
                        if isinstance(value, (int, float)):
                            facts_dict[key] = value
                        elif hasattr(value, 'value'):
                            facts_dict[key] = value.value
                    logger.info(f"Converted {len(facts_dict)} facts from dict")
                    facts_list = []  # Already processed
                elif hasattr(facts, 'data'):
                    facts_list = facts.data
                elif hasattr(facts, '__iter__'):
                    # Try to convert to list
                    try:
                        facts_list = list(facts)
                    except:
                        # Try accessing as dict
                        if hasattr(facts, 'get'):
                            # It's dict-like
                            for key in dir(facts):
                                if not key.startswith('_'):
                                    try:
                                        val = getattr(facts, key)
                                        if isinstance(val, (int, float)):
                                            facts_dict[key] = val
                                    except:
                                        pass
                            facts_list = []
            except Exception as e:
                logger.debug(f"Error accessing facts: {e}")
            
            # Iterate through facts and extract relevant ones
            if facts_list:
                for fact in facts_list:
                    try:
                        concept = fact.concept if hasattr(fact, 'concept') else None
                        value = fact.value if hasattr(fact, 'value') else None
                        end_date = fact.end_date if hasattr(fact, 'end_date') else None
                        
                        if concept and value is not None:
                            # Filter by period if we have a target date
                            if target_date and end_date:
                                try:
                                    if isinstance(end_date, str):
                                        fact_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                                    else:
                                        fact_date = end_date
                                    # Allow 45 day window
                                    if abs((fact_date - target_date).days) > 45:
                                        continue
                                except:
                                    pass
                            
                            # Store fact by concept name
                            concept_name = concept.name if hasattr(concept, 'name') else str(concept)
                            facts_dict[concept_name] = value
                    except Exception as e:
                        logger.debug(f"Error processing fact: {e}")
                        continue
            elif not facts_dict:
                # Last resort: try to access facts by concept name directly
                logger.info("Trying to access facts by concept name directly")
                concept_names = [
                    'NetInvestmentIncome', 'TotalInvestmentIncome', 'Assets', 
                    'LiabilitiesAndStockholdersEquity', 'NetAssetValuePerShare'
                ]
                for concept_name in concept_names:
                    try:
                        if hasattr(facts, concept_name):
                            val = getattr(facts, concept_name)
                            if val is not None:
                                facts_dict[concept_name] = val
                    except:
                        pass
            
            logger.info(f"Extracted {len(facts_dict)} facts from FactsView")
            
            # Now extract specific financial metrics
            def find_fact(patterns: List[str]) -> Optional[float]:
                for pattern in patterns:
                    # Try exact match first
                    for key, value in facts_dict.items():
                        if pattern.lower() in key.lower():
                            try:
                                return float(value)
                            except:
                                pass
                return None
            
            # Build income statement
            income_data = {
                'total_investment_income': find_fact(['InterestAndDividendIncomeOperating', 'GrossInvestmentIncomeOperating']),
                'net_investment_income': find_fact(['NetInvestmentIncome']),
                'net_investment_income_per_share': find_fact(['InvestmentCompanyInvestmentIncomeLossPerShare', 'NetInvestmentIncomePerShare']),
                'total_expenses': abs(find_fact(['OperatingExpenses']) or 0),
                'management_fees': find_fact(['ManagementFeeRevenue', 'ManagementFees']),
                'incentive_fees': find_fact(['IncentiveFeeRevenue', 'IncentiveFees']),
                'interest_expense': find_fact(['InterestExpense', 'InterestExpenseDebt']),
            }
            
            if income_data['total_expenses'] == 0:
                income_data['total_expenses'] = None
            
            # Gains/Losses
            gains_losses = {
                'net_realized_gains': find_fact(['NetRealizedGainLossOnInvestments', 'RealizedInvestmentGainsLosses']),
                'net_unrealized_gains': find_fact(['NetUnrealizedGainLossOnInvestments', 'UnrealizedGainLossOnInvestments']),
            }
            
            # Balance sheet
            balance_data = {
                'nav_per_share': find_fact(['NetAssetValuePerShare']),
                'total_assets': find_fact(['LiabilitiesAndStockholdersEquity', 'Assets']),
                'total_liabilities': find_fact(['Liabilities']),
                'total_equity': find_fact(['StockholdersEquity', 'Equity']),
                'total_investments': find_fact(['InvestmentOwnedAtFairValue', 'Investments']),
                'cash_and_cash_equivalents': find_fact(['CashAndCashEquivalentsAtCarryingValue']),
            }
            
            # Shares
            shares_data = {
                'shares_outstanding': find_fact(['CommonStockSharesOutstanding', 'SharesOutstanding']),
                'weighted_avg_shares': find_fact(['WeightedAverageNumberOfSharesOutstandingBasic']),
            }
            
            # Leverage
            leverage_data = {
                'total_debt': find_fact(['LongTermDebt', 'Debt', 'NotesPayable']),
                'revolving_credit_facility': find_fact(['RevolvingCreditFacility']),
            }
            
            # Check if we got any meaningful data
            has_data = any([
                income_data.get('net_investment_income'),
                balance_data.get('total_assets'),
                balance_data.get('nav_per_share'),
            ])
            
            if not has_data:
                logger.warning("No meaningful financial data found in facts")
                return None
            
            # Build result
            result = {
                'ticker': ticker.upper(),
                'name': company_name,
                'period': reporting_period,
                'period_start': None,
                'period_end': None,
                'filing_date': None,
                'accession_number': None,
                'income_statement': income_data,
                'gains_losses': gains_losses,
                'balance_sheet': balance_data,
                'shares': shares_data,
                'leverage': leverage_data,
                'derived': self._calculate_derived_metrics({
                    'income_statement': income_data,
                    'balance_sheet': balance_data,
                    'leverage': leverage_data,
                    'shares': shares_data,
                }),
                'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
            }
            
            logger.info(f"✅ Successfully built financials from {len(facts_dict)} facts")
            return result
            
        except Exception as e:
            logger.error(f"Error building financials from facts: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _parse_xbrl_financials(self, xbrl_content: str, ticker: str, company_name: str, 
                               reporting_period: Optional[str]) -> Optional[Dict]:
        """
        Parse XBRL content directly to extract quarterly financials.
        This is needed because edgartools' Company.get_financials() only returns annual data.
        """
        try:
            # Parse the XBRL manually to find the reporting period's instant context
            # and extract financial facts for that context
            import re
            
            # Extract contexts from XBRL
            contexts = []
            context_pattern = re.compile(r'<context id="([^"]+)">(.*?)</context>', re.DOTALL)
            for match in context_pattern.finditer(xbrl_content):
                ctx_id = match.group(1)
                ctx_content = match.group(2)
                
                # Extract period information
                instant = re.search(r'<instant>([^<]+)</instant>', ctx_content)
                start_date = re.search(r'<startDate>([^<]+)</startDate>', ctx_content)
                end_date = re.search(r'<endDate>([^<]+)</endDate>', ctx_content)
                
                contexts.append({
                    'id': ctx_id,
                    'instant': instant.group(1) if instant else None,
                    'start_date': start_date.group(1) if start_date else None,
                    'end_date': end_date.group(1) if end_date else None,
                })
            
            logger.info(f"Found {len(contexts)} total contexts in XBRL")
            # Log instant contexts
            instant_contexts = [c for c in contexts if c.get('instant')]
            logger.info(f"Found {len(instant_contexts)} instant contexts")
            if instant_contexts:
                logger.debug(f"Sample instant dates: {[c['instant'] for c in instant_contexts[:5]]}")
            if reporting_period:
                logger.info(f"Looking for period: {reporting_period}")
            
            # Find the context matching our reporting period
            target_context = None
            if reporting_period:
                # Try exact match first
                for ctx in contexts:
                    if ctx.get('instant') == reporting_period:
                        target_context = ctx
                        break
                
                # If no exact match, try to find the closest instant
                if not target_context:
                    from datetime import datetime
                    try:
                        period_dt = datetime.strptime(reporting_period, '%Y-%m-%d')
                        best_match = None
                        best_diff = None
                        for ctx in contexts:
                            if ctx.get('instant'):
                                try:
                                    ctx_dt = datetime.strptime(ctx['instant'], '%Y-%m-%d')
                                    diff = abs((period_dt - ctx_dt).days)
                                    if best_diff is None or diff < best_diff:
                                        best_diff = diff
                                        best_match = ctx
                                except:
                                    pass
                        if best_match and best_diff and best_diff <= 45:  # Within 45 days
                            target_context = best_match
                            logger.info(f"Using closest context: {best_match['instant']} (diff: {best_diff} days)")
                    except:
                        pass
            
            if not target_context:
                # Use the latest instant context
                instant_contexts = [c for c in contexts if c.get('instant')]
                if instant_contexts:
                    instant_contexts.sort(key=lambda x: x['instant'] or '', reverse=True)
                    target_context = instant_contexts[0]
                    logger.info(f"Using latest context: {target_context['instant']}")
            
            if not target_context:
                logger.warning("No suitable context found in XBRL")
                logger.debug(f"Available contexts: {[c.get('id') for c in contexts[:10]]}")
                return None
            
            logger.info(f"Selected context: {target_context['id']} with instant: {target_context.get('instant')}")
            
            # Extract facts for this context
            facts = self._extract_facts_for_context(xbrl_content, target_context['id'])
            
            # Log sample facts for debugging
            if facts:
                sample_facts = list(facts.items())[:10]
                logger.debug(f"Sample facts extracted: {sample_facts}")
            else:
                logger.warning(f"No facts extracted for context {target_context['id']}")
                # Try to find why - check if context appears in file
                context_mentions = xbrl_content.count(target_context['id'])
                logger.debug(f"Context ID '{target_context['id']}' appears {context_mentions} times in XBRL")
            
            # Build financials from facts
            result = self._build_financials_from_facts(
                facts, target_context, ticker, company_name, reporting_period
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing XBRL directly: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_facts_for_context(self, xbrl_content: str, context_id: str) -> Dict[str, float]:
        """Extract XBRL facts for a specific context ID."""
        facts = {}
        
        import re
        
        # OPTIMIZATION: For large files, first find all positions where context_id appears
        # This avoids scanning the entire file multiple times
        context_positions = []
        search_pos = 0
        while True:
            pos = xbrl_content.find(f'contextRef="{context_id}"', search_pos)
            if pos == -1:
                pos = xbrl_content.find(f"contextRef='{context_id}'", search_pos)
                if pos == -1:
                    break
            context_positions.append(pos)
            search_pos = pos + 1
        
        if not context_positions:
            logger.debug(f"Context {context_id} not found in file")
            return facts
        
        logger.debug(f"Found {len(context_positions)} occurrences of context {context_id}")
        
        # Extract a window around each occurrence to avoid processing the entire file
        # This is much faster for large files
        processed_chunks = set()  # Track which chunks we've processed to avoid duplicates
        
        # Pattern for standard XBRL: <us-gaap:Concept contextRef="ctx-id">value</us-gaap:Concept>
        # Also try with company-specific namespaces (e.g., htgc:)
        std_pattern = re.compile(
            r'<(?:us-gaap|rily|dei|htgc|arcc|obdc|ocsl|gbdc|bxsl|fsk|tslx|msdl|cswc|mfic|gsbd|trin|psec|nmfc|pflt|cgbd|bbdc|fdus|slrc|bcsf|gain|tcpc|cion|ncdl|ccap|gecc|glad|hrzn|icmb|lien|lrfc|mrcc|msif|ofs|oxsq|pfx|pnnt|psbd|rand|rway|sar|scm|ssss|tpvg|whf):([^:>\s]+)[^>]*contextRef="' + re.escape(context_id) + r'"[^>]*>'
            r'([^<]+)</(?:us-gaap|rily|dei|htgc|arcc|obdc|ocsl|gbdc|bxsl|fsk|tslx|msdl|cswc|mfic|gsbd|trin|psec|nmfc|pflt|cgbd|bbdc|fdus|slrc|bcsf|gain|tcpc|cion|ncdl|ccap|gecc|glad|hrzn|icmb|lien|lrfc|mrcc|msif|ofs|oxsq|pfx|pnnt|psbd|rand|rway|sar|scm|ssss|tpvg|whf):[^>]*>',
            re.DOTALL
        )
        
        # Pattern for inline XBRL: <ix:nonFraction ... name="..." contextRef="..." ...>value</ix:nonFraction>
        # Attributes can be in any order, so match them separately
        # Pattern 1: name before contextRef
        inline_pattern1 = re.compile(
            r'<ix:nonFraction[^>]*name\s*=\s*["\'](?:us-gaap|rily|dei|htgc|arcc|obdc|ocsl|gbdc|bxsl|fsk|tslx|msdl|cswc|mfic|gsbd|trin|psec|nmfc|pflt|cgbd|bbdc|fdus|slrc|bcsf|gain|tcpc|cion|ncdl|ccap|gecc|glad|hrzn|icmb|lien|lrfc|mrcc|msif|ofs|oxsq|pfx|pnnt|psbd|rand|rway|sar|scm|ssss|tpvg|whf):([^"\']+)"[^>]*contextRef\s*=\s*["\']' + re.escape(context_id) + r'["\'][^>]*>'
            r'([^<]+)</ix:nonFraction>',
            re.DOTALL | re.IGNORECASE
        )
        # Pattern 2: contextRef before name
        inline_pattern2 = re.compile(
            r'<ix:nonFraction[^>]*contextRef\s*=\s*["\']' + re.escape(context_id) + r'["\'][^>]*name\s*=\s*["\'](?:us-gaap|rily|dei|htgc|arcc|obdc|ocsl|gbdc|bxsl|fsk|tslx|msdl|cswc|mfic|gsbd|trin|psec|nmfc|pflt|cgbd|bbdc|fdus|slrc|bcsf|gain|tcpc|cion|ncdl|ccap|gecc|glad|hrzn|icmb|lien|lrfc|mrcc|msif|ofs|oxsq|pfx|pnnt|psbd|rand|rway|sar|scm|ssss|tpvg|whf):([^"\']+)"[^>]*>'
            r'([^<]+)</ix:nonFraction>',
            re.DOTALL | re.IGNORECASE
        )
        # Pattern 3: Simplified - just find ix:nonFraction with contextRef and extract name/value
        # This is faster than lookaheads and should catch most cases
        inline_pattern3 = re.compile(
            r'<ix:nonFraction[^>]*contextRef\s*=\s*["\']' + re.escape(context_id) + r'["\'][^>]*>'
            r'([^<]+)</ix:nonFraction>',
            re.DOTALL | re.IGNORECASE
        )
        # Separate pattern to extract name from the same tag
        inline_pattern3_name = re.compile(
            r'<ix:nonFraction[^>]*contextRef\s*=\s*["\']' + re.escape(context_id) + r'["\'][^>]*name\s*=\s*["\']([^"\']+):([^"\']+)["\']',
            re.IGNORECASE
        )
        
        # Also try a more flexible pattern that matches any namespace
        flexible_pattern = re.compile(
            r'<([^:>\s]+):([^:>\s]+)[^>]*contextRef="' + re.escape(context_id) + r'"[^>]*>'
            r'([^<]+)</\1:\2>',
            re.DOTALL
        )
        
        # OPTIMIZATION: Process chunks around context positions instead of entire file
        # Process first 10 occurrences to avoid processing too many (financials are typically in the first few)
        max_positions = min(10, len(context_positions))
        
        std_count = 0
        for pos_idx, pos in enumerate(context_positions[:max_positions]):
            # Extract a larger window around this position (5000 chars before, 10000 chars after)
            # Financial statements are often in larger blocks
            chunk_start = max(0, pos - 5000)
            chunk_end = min(len(xbrl_content), pos + 10000)
            chunk = xbrl_content[chunk_start:chunk_end]
            
            # Only process if we haven't seen this exact chunk
            chunk_hash = hash(chunk[:500])  # Use first 500 chars as hash
            if chunk_hash in processed_chunks:
                continue
            processed_chunks.add(chunk_hash)
            
            for match in std_pattern.finditer(chunk):
                std_count += 1
                concept_base = match.group(1)
                value_str = match.group(2).strip()
                
                # Determine namespace from the full match
                full_match = match.group(0)
                namespace = None
                for ns in ['rily', 'dei', 'htgc', 'arcc', 'obdc', 'ocsl', 'gbdc', 'bxsl', 'fsk', 'tslx', 'msdl', 'cswc', 'mfic', 'gsbd', 'trin', 'psec', 'nmfc', 'pflt', 'cgbd', 'bbdc', 'fdus', 'slrc', 'bcsf', 'gain', 'tcpc', 'cion', 'ncdl', 'ccap', 'gecc', 'glad', 'hrzn', 'icmb', 'lien', 'lrfc', 'mrcc', 'msif', 'ofs', 'oxsq', 'pfx', 'pnnt', 'psbd', 'rand', 'rway', 'sar', 'scm', 'ssss', 'tpvg', 'whf', 'us-gaap']:
                    if f'{ns}:' in full_match:
                        namespace = ns
                        break
                if not namespace:
                    namespace = 'us-gaap'  # default
                
                concept = f'{namespace}:{concept_base}'
                
                # Parse value
                try:
                    cleaned = value_str.replace(',', '').replace('(', '-').replace(')', '')
                    if cleaned:
                        value = float(cleaned)
                        facts[concept] = value
                except (ValueError, TypeError):
                    pass
        
        inline_count = 0
        # Reset processed chunks for inline patterns
        processed_chunks_inline = set()
        
        # Try pattern 1 (name before contextRef)
        for pos_idx, pos in enumerate(context_positions[:max_positions]):
            chunk_start = max(0, pos - 5000)
            chunk_end = min(len(xbrl_content), pos + 10000)
            chunk = xbrl_content[chunk_start:chunk_end]
            
            chunk_hash = hash(chunk[:500])
            if chunk_hash in processed_chunks_inline:
                continue
            processed_chunks_inline.add(chunk_hash)
            
            for match in inline_pattern1.finditer(chunk):
                inline_count += 1
                concept_base = match.group(1)
                value_str = match.group(2).strip()
                
                # Determine namespace from the name attribute
                full_match = match.group(0)
                namespace = None
                for ns in ['rily', 'dei', 'htgc', 'arcc', 'obdc', 'ocsl', 'gbdc', 'bxsl', 'fsk', 'tslx', 'msdl', 'cswc', 'mfic', 'gsbd', 'trin', 'psec', 'nmfc', 'pflt', 'cgbd', 'bbdc', 'fdus', 'slrc', 'bcsf', 'gain', 'tcpc', 'cion', 'ncdl', 'ccap', 'gecc', 'glad', 'hrzn', 'icmb', 'lien', 'lrfc', 'mrcc', 'msif', 'ofs', 'oxsq', 'pfx', 'pnnt', 'psbd', 'rand', 'rway', 'sar', 'scm', 'ssss', 'tpvg', 'whf', 'us-gaap']:
                    if f'{ns}:' in full_match:
                        namespace = ns
                        break
                if not namespace:
                    namespace = 'us-gaap'  # default
                
                concept = f'{namespace}:{concept_base}'
                
                # Parse value
                try:
                    cleaned = value_str.replace(',', '').replace('(', '-').replace(')', '').strip()
                    if cleaned and cleaned not in ['—', '-', 'N/A', '']:
                        value = float(cleaned)
                        facts[concept] = value
                except (ValueError, TypeError):
                    pass
        
        # Try pattern 2 (contextRef before name)
        for pos_idx, pos in enumerate(context_positions[:max_positions]):
            chunk_start = max(0, pos - 5000)
            chunk_end = min(len(xbrl_content), pos + 10000)
            chunk = xbrl_content[chunk_start:chunk_end]
            
            chunk_hash = hash(chunk[:500])
            if chunk_hash in processed_chunks_inline:
                continue
            processed_chunks_inline.add(chunk_hash)
            
            for match in inline_pattern2.finditer(chunk):
                inline_count += 1
                concept_base = match.group(1)
                value_str = match.group(2).strip()
                
                # Determine namespace from the name attribute
                full_match = match.group(0)
                namespace = None
                for ns in ['rily', 'dei', 'htgc', 'arcc', 'obdc', 'ocsl', 'gbdc', 'bxsl', 'fsk', 'tslx', 'msdl', 'cswc', 'mfic', 'gsbd', 'trin', 'psec', 'nmfc', 'pflt', 'cgbd', 'bbdc', 'fdus', 'slrc', 'bcsf', 'gain', 'tcpc', 'cion', 'ncdl', 'ccap', 'gecc', 'glad', 'hrzn', 'icmb', 'lien', 'lrfc', 'mrcc', 'msif', 'ofs', 'oxsq', 'pfx', 'pnnt', 'psbd', 'rand', 'rway', 'sar', 'scm', 'ssss', 'tpvg', 'whf', 'us-gaap']:
                    if f'{ns}:' in full_match:
                        namespace = ns
                        break
                if not namespace:
                    namespace = 'us-gaap'  # default
                
                concept = f'{namespace}:{concept_base}'
                
                # Skip if already found
                if concept in facts:
                    continue
                
                # Parse value
                try:
                    cleaned = value_str.replace(',', '').replace('(', '-').replace(')', '').strip()
                    if cleaned and cleaned not in ['—', '-', 'N/A', '']:
                        value = float(cleaned)
                        facts[concept] = value
                except (ValueError, TypeError):
                    pass
        
        # Try pattern 3 (catch-all for contextRef)
        # Process chunks around context positions
        for pos_idx, pos in enumerate(context_positions[:max_positions]):
            chunk_start = max(0, pos - 5000)
            chunk_end = min(len(xbrl_content), pos + 10000)
            chunk = xbrl_content[chunk_start:chunk_end]
            
            chunk_hash = hash(chunk[:500])
            if chunk_hash in processed_chunks_inline:
                continue
            processed_chunks_inline.add(chunk_hash)
            
            for match in inline_pattern3.finditer(chunk):
                inline_count += 1
                value_str = match.group(1).strip()
                
                # Adjust match positions to account for chunk offset
                tag_start_in_chunk = match.start()
                tag_end_in_chunk = match.end()
                tag_text = chunk[tag_start_in_chunk:tag_end_in_chunk]
                
                # Extract name attribute
                name_match = re.search(r'name\s*=\s*["\']([^"\']+):([^"\']+)["\']', tag_text, re.IGNORECASE)
                if name_match:
                    namespace = name_match.group(1)
                    concept_base = name_match.group(2)
                    concept = f'{namespace}:{concept_base}'
                    
                    # Skip if already found
                    if concept in facts:
                        continue
                    
                    # Parse value
                    try:
                        cleaned = value_str.replace(',', '').replace('(', '-').replace(')', '').strip()
                        if cleaned and cleaned not in ['—', '-', 'N/A', '']:
                            value = float(cleaned)
                            facts[concept] = value
                    except (ValueError, TypeError):
                        pass
        
        # Try flexible pattern as fallback (only on chunks, not full file)
        flexible_count = 0
        processed_chunks_flex = set()
        
        for pos_idx, pos in enumerate(context_positions[:max_positions]):
            chunk_start = max(0, pos - 5000)
            chunk_end = min(len(xbrl_content), pos + 10000)
            chunk = xbrl_content[chunk_start:chunk_end]
            
            chunk_hash = hash(chunk[:500])
            if chunk_hash in processed_chunks_flex:
                continue
            processed_chunks_flex.add(chunk_hash)
            
            for match in flexible_pattern.finditer(chunk):
                flexible_count += 1
                namespace = match.group(1)
                concept_base = match.group(2)
                value_str = match.group(3).strip()
                
                concept = f'{namespace}:{concept_base}'
                
                # Skip if already found
                if concept in facts:
                    continue
                
                # Parse value
                try:
                    cleaned = value_str.replace(',', '').replace('(', '-').replace(')', '')
                    if cleaned:
                        value = float(cleaned)
                        facts[concept] = value
                except (ValueError, TypeError):
                    pass
        
        logger.info(f"Extracted {len(facts)} facts for context {context_id} (std: {std_count}, inline: {inline_count}, flexible: {flexible_count})")
        
        if len(facts) == 0 or len(facts) < 10:
            # Debug: try to find any mention of this context
            context_mentions = xbrl_content.count(context_id)
            if len(facts) == 0:
                logger.warning(f"No facts found for context {context_id} (appears {context_mentions} times in file)")
            else:
                logger.warning(f"Only {len(facts)} facts found for context {context_id} (appears {context_mentions} times in file)")
            
            # Find a sample of where this context is used
            idx = xbrl_content.find(f'contextRef="{context_id}"')
            if idx == -1:
                idx = xbrl_content.find(f"contextRef='{context_id}'")
            if idx != -1:
                sample_start = max(0, idx - 200)
                sample_end = min(len(xbrl_content), idx + 800)
                sample = xbrl_content[sample_start:sample_end]
                logger.debug(f"Sample XBRL around context {context_id}:\n{sample[:1000]}")
                
                # Try to find facts with alternative patterns
                # Look for any numeric values near this context
                # Pattern for inline XBRL with different structures
                alt_patterns = [
                    # Pattern 1: contextRef="..." ...>value<
                    re.compile(
                        r'contextRef\s*=\s*["\']' + re.escape(context_id) + r'["\'][^>]*>([^<]+)<',
                        re.DOTALL | re.IGNORECASE
                    ),
                    # Pattern 2: name="..." contextRef="..."
                    re.compile(
                        r'name\s*=\s*["\']([^"]+)["\'][^>]*contextRef\s*=\s*["\']' + re.escape(context_id) + r'["\'][^>]*>([^<]+)<',
                        re.DOTALL | re.IGNORECASE
                    ),
                ]
                
                for i, alt_pattern in enumerate(alt_patterns):
                    alt_matches = list(alt_pattern.finditer(xbrl_content))
                    logger.debug(f"Alternative pattern {i+1} found {len(alt_matches)} potential matches")
                    if alt_matches and len(alt_matches) > len(facts):
                        logger.debug(f"Sample values from pattern {i+1}: {[m.group(1).strip()[:50] if len(m.groups()) > 0 else 'N/A' for m in alt_matches[:10]]}")
        
        return facts
    
    def _build_financials_from_facts(self, facts: Dict[str, float], context: Dict, 
                                    ticker: str, company_name: str, 
                                    reporting_period: Optional[str]) -> Dict:
        """Build financials dictionary from parsed XBRL facts."""
        
        def find_fact(patterns: List[str]) -> Optional[float]:
            for pattern in patterns:
                # Try exact match
                if pattern in facts:
                    return facts[pattern]
                # Try case-insensitive base match
                pattern_base = pattern.split(':')[-1].lower()
                for key, value in facts.items():
                    key_base = key.split(':')[-1].lower() if ':' in key else key.lower()
                    if key_base == pattern_base:
                        return value
            return None
        
        # Build income statement
        income_data = {
            'total_investment_income': find_fact([
                'us-gaap:InterestAndDividendIncomeOperating',
                'us-gaap:GrossInvestmentIncomeOperating',
                'rily:InvestmentIncome',
            ]),
            'net_investment_income': find_fact([
                'us-gaap:NetInvestmentIncome',
                'rily:NetInvestmentIncome',
            ]),
            'net_investment_income_per_share': find_fact([
                'us-gaap:InvestmentCompanyInvestmentIncomeLossPerShare',
                'us-gaap:NetInvestmentIncomePerShare',
                'rily:NetInvestmentIncomePerShare',
            ]),
            'total_expenses': abs(find_fact([
                'us-gaap:OperatingExpenses',
                'rily:OperatingExpenses',
            ]) or 0),
            'management_fees': find_fact([
                'us-gaap:ManagementFeeRevenue',
                'rily:ManagementFees',
            ]),
            'incentive_fees': find_fact([
                'us-gaap:IncentiveFeeRevenue',
                'rily:IncentiveFees',
            ]),
            'interest_expense': find_fact([
                'us-gaap:InterestExpense',
                'us-gaap:InterestExpenseDebt',
                'rily:InterestExpense',
            ]),
        }
        
        if income_data['total_expenses'] == 0:
            income_data['total_expenses'] = None
        
        # Gains/Losses
        gains_losses = {
            'net_realized_gains': find_fact([
                'us-gaap:NetRealizedGainLossOnInvestments',
                'us-gaap:RealizedInvestmentGainsLosses',
            ]),
            'net_unrealized_gains': find_fact([
                'us-gaap:NetUnrealizedGainLossOnInvestments',
                'us-gaap:UnrealizedGainLossOnInvestments',
            ]),
        }
        
        # Balance sheet
        balance_data = {
            'nav_per_share': find_fact([
                'us-gaap:NetAssetValuePerShare',
                'rily:NetAssetValuePerShare',
            ]),
            'total_assets': find_fact([
                'us-gaap:LiabilitiesAndStockholdersEquity',
                'us-gaap:Assets',
                'rily:TotalAssets',
            ]),
            'total_liabilities': find_fact([
                'us-gaap:Liabilities',
                'rily:TotalLiabilities',
            ]),
            'total_equity': find_fact([
                'us-gaap:StockholdersEquity',
                'us-gaap:Equity',
                'rily:StockholdersEquity',
            ]),
            'total_investments': find_fact([
                'us-gaap:InvestmentOwnedAtFairValue',
                'us-gaap:Investments',
                'rily:InvestmentsAtFairValue',
            ]),
            'cash_and_cash_equivalents': find_fact([
                'us-gaap:CashAndCashEquivalentsAtCarryingValue',
                'rily:CashAndCashEquivalents',
            ]),
        }
        
        # Shares
        shares_data = {
            'shares_outstanding': find_fact([
                'us-gaap:CommonStockSharesOutstanding',
                'us-gaap:SharesOutstanding',
                'rily:SharesOutstanding',
            ]),
            'weighted_avg_shares': find_fact([
                'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic',
                'rily:WeightedAverageSharesOutstanding',
            ]),
        }
        
        # Leverage
        leverage_data = {
            'total_debt': find_fact([
                'us-gaap:LongTermDebt',
                'us-gaap:Debt',
                'us-gaap:NotesPayable',
                'rily:TotalDebt',
            ]),
            'revolving_credit_facility': find_fact([
                'us-gaap:RevolvingCreditFacility',
                'rily:RevolvingCreditFacility',
            ]),
        }
        
        # Build result
        period = context.get('instant') or reporting_period
        result = {
            'ticker': ticker.upper(),
            'name': company_name,
            'period': period,
            'period_start': context.get('start_date'),
            'period_end': context.get('end_date'),
            'filing_date': None,  # Will be set by caller
            'accession_number': None,  # Will be set by caller
            'income_statement': income_data,
            'gains_losses': gains_losses,
            'balance_sheet': balance_data,
            'shares': shares_data,
            'leverage': leverage_data,
            'derived': self._calculate_derived_metrics({
                'income_statement': income_data,
                'balance_sheet': balance_data,
                'leverage': leverage_data,
                'shares': shares_data,
            }),
            'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
        }
        
        return result
    
    def _build_financials_from_edgartools(self, income_stmt, balance_sheet, financials, 
                                         ticker: str, company_name: str, 
                                         reporting_period: Optional[str]) -> Dict:
        """Build financials dictionary from edgartools objects."""
        
        # Helper to safely get value from edgartools Statement
        def get_value(stmt, concept_name: str, default=None, ticker_prefix: str = None, preferred_period: Optional[str] = None):
            if stmt is None:
                return default
            
            try:
                # edgartools Statement objects have a to_dataframe() method
                if hasattr(stmt, 'to_dataframe'):
                    df = stmt.to_dataframe()
                elif hasattr(stmt, 'dataframe'):
                    df = stmt.dataframe
                elif hasattr(stmt, 'empty'):
                    df = stmt  # It's already a DataFrame
                else:
                    return default
                
                if df is None or (hasattr(df, 'empty') and df.empty):
                    return default
                
                # edgartools dataframes have 'concept' column and date columns
                if 'concept' not in df.columns:
                    return default
                
                # Find date columns (excluding 'concept', 'label', 'level', 'abstract', 'dimension')
                date_cols = [c for c in df.columns if c not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                if not date_cols:
                    return default
                
                # If we have a preferred period, try to use it
                preferred_col = None
                period_to_match = preferred_period or reporting_period
                if period_to_match:
                    # Try exact match first
                    if period_to_match in date_cols:
                        preferred_col = period_to_match
                    else:
                        # Try partial match (e.g., "2025-10-23" might be "2025-10-23" or "2025-10-23 00:00:00")
                        for col in date_cols:
                            if str(col).startswith(period_to_match):
                                preferred_col = col
                                break
                
                # Use preferred period if found, otherwise use most recent
                if preferred_col:
                    date_col = preferred_col
                else:
                    # Sort date columns to get most recent first
                    date_cols.sort(reverse=True)
                    date_col = date_cols[0]
                
                # Search for concept in the 'concept' column
                # Try exact match first (with and without namespace)
                search_patterns = [
                    f'us-gaap_{concept_name}',  # Prefer us-gaap prefix first
                    concept_name,  # Exact without prefix
                    f'rily_{concept_name}',  # With rily prefix
                    concept_name.replace(':', '_'),  # Replace : with _
                ]
                
                # Also try company-specific prefixes (e.g., htgc_)
                if ticker_prefix:
                    search_patterns.append(f'{ticker_prefix.lower()}_{concept_name}')
                
                for pattern in search_patterns:
                    # Try exact match first
                    exact_matches = df[df['concept'] == pattern]
                    if not exact_matches.empty:
                        val = exact_matches.iloc[0][date_col]
                        if val is not None and not (isinstance(val, float) and val != val):
                            return float(val)
                    
                    # Try contains match, but exclude Abstract concepts and prefer main concepts over sub-items
                    # For Assets, prefer exact "Assets" or "LiabilitiesAndStockholdersEquity" over "OtherAssets" etc.
                    matches = df[
                        df['concept'].str.contains(pattern, case=False, na=False, regex=False) &
                        ~df['concept'].str.contains('Abstract', case=False, na=False) &
                        ~df['concept'].str.contains('Other', case=False, na=False)  # Exclude OtherAssets, OtherLiabilities, etc.
                    ]
                    if not matches.empty:
                        # Filter out rows where the value is None or NaN
                        matches = matches[matches[date_col].notna()]
                        if not matches.empty:
                            # Prefer exact concept name matches over partial matches
                            exact_concept_match = matches[matches['concept'] == pattern]
                            if not exact_concept_match.empty:
                                val = exact_concept_match.iloc[0][date_col]
                            else:
                                val = matches.iloc[0][date_col]
                            if val is not None and not (isinstance(val, float) and val != val):  # Check for NaN
                                return float(val)
                
                # Try partial match (case-insensitive)
                if PANDAS_AVAILABLE:
                    for _, row in df.iterrows():
                        concept = str(row['concept']) if pd.notna(row['concept']) else ''
                        if concept_name.lower() in concept.lower():
                            val = row[date_col]
                            if val is not None and not (isinstance(val, float) and val != val):
                                return float(val)
                else:
                    # Fallback without pandas
                    for idx in range(len(df)):
                        concept = str(df.iloc[idx]['concept']) if 'concept' in df.columns else ''
                        if concept_name.lower() in concept.lower():
                            val = df.iloc[idx][date_col]
                            if val is not None and not (isinstance(val, float) and val != val):
                                return float(val)
                            
            except (KeyError, IndexError, AttributeError, ValueError, TypeError, ImportError) as e:
                logger.debug(f"Error getting {concept_name}: {e}")
                pass
            return default
        
        # Extract period from financials
        period = None
        if hasattr(financials, 'period') and financials.period:
            period = str(financials.period)
        elif reporting_period:
            period = reporting_period
        
        # Build income statement - pass reporting_period to get_value to extract the correct period's data
        income_data = {
            'total_investment_income': get_value(income_stmt, 'InterestAndDividendIncomeOperating', ticker_prefix=ticker, preferred_period=reporting_period) or 
                                      get_value(income_stmt, 'GrossInvestmentIncomeOperating', ticker_prefix=ticker, preferred_period=reporting_period),
            'net_investment_income': get_value(income_stmt, 'NetInvestmentIncome', ticker_prefix=ticker, preferred_period=reporting_period),
            'net_investment_income_per_share': get_value(income_stmt, 'InvestmentCompanyInvestmentIncomeLossPerShare', ticker_prefix=ticker, preferred_period=reporting_period) or
                                              get_value(income_stmt, 'NetInvestmentIncomePerShare', ticker_prefix=ticker, preferred_period=reporting_period),
            'total_expenses': abs(get_value(income_stmt, 'OperatingExpenses', ticker_prefix=ticker, preferred_period=reporting_period) or 
                            get_value(income_stmt, 'OperatingExpensesNet', ticker_prefix=ticker, preferred_period=reporting_period) or 0),  # Take absolute value for expenses
            'management_fees': get_value(income_stmt, 'ManagementFeeRevenue', ticker_prefix=ticker, preferred_period=reporting_period) or
                             get_value(income_stmt, 'ManagementFees', ticker_prefix=ticker, preferred_period=reporting_period),
            'incentive_fees': get_value(income_stmt, 'IncentiveFeeRevenue', ticker_prefix=ticker, preferred_period=reporting_period) or
                            get_value(income_stmt, 'IncentiveFees', ticker_prefix=ticker, preferred_period=reporting_period),
            'interest_expense': get_value(income_stmt, 'InterestExpense', ticker_prefix=ticker, preferred_period=reporting_period) or
                              get_value(income_stmt, 'InterestExpenseDebt', ticker_prefix=ticker, preferred_period=reporting_period),
        }
        
        # Fix: if total_expenses is 0, set to None
        if income_data['total_expenses'] == 0:
            income_data['total_expenses'] = None
        
        # Gains/Losses
        gains_losses = {
            'net_realized_gains': get_value(income_stmt, 'NetRealizedGainLossOnInvestments', ticker_prefix=ticker, preferred_period=reporting_period) or
                                 get_value(income_stmt, 'RealizedInvestmentGainsLosses', ticker_prefix=ticker, preferred_period=reporting_period),
            'net_unrealized_gains': get_value(income_stmt, 'NetUnrealizedGainLossOnInvestments', ticker_prefix=ticker, preferred_period=reporting_period) or
                                   get_value(income_stmt, 'UnrealizedGainLossOnInvestments', ticker_prefix=ticker, preferred_period=reporting_period),
        }
        
        # Balance sheet
        # For Assets, prioritize LiabilitiesAndStockholdersEquity (which equals total assets) over individual Assets lines
        total_assets_val = get_value(balance_sheet, 'LiabilitiesAndStockholdersEquity', ticker_prefix=ticker, preferred_period=reporting_period) or \
                          get_value(balance_sheet, 'Assets', ticker_prefix=ticker, preferred_period=reporting_period)
        
        balance_data = {
            'nav_per_share': get_value(balance_sheet, 'NetAssetValuePerShare', ticker_prefix=ticker, preferred_period=reporting_period),
            'total_assets': total_assets_val,
            'total_liabilities': get_value(balance_sheet, 'Liabilities', ticker_prefix=ticker, preferred_period=reporting_period),
            'total_equity': get_value(balance_sheet, 'StockholdersEquity', ticker_prefix=ticker, preferred_period=reporting_period),
            'total_investments': get_value(balance_sheet, 'InvestmentOwnedAtFairValue', ticker_prefix=ticker, preferred_period=reporting_period) or
                               get_value(balance_sheet, 'Investments', ticker_prefix=ticker, preferred_period=reporting_period),
            'cash_and_cash_equivalents': get_value(balance_sheet, 'CashAndCashEquivalentsAtCarryingValue', ticker_prefix=ticker, preferred_period=reporting_period),
        }
        
        # Shares - try to get from balance sheet or financials
        shares_outstanding = get_value(balance_sheet, 'CommonStockSharesOutstanding', ticker_prefix=ticker, preferred_period=reporting_period) or \
                           get_value(balance_sheet, 'SharesOutstanding', ticker_prefix=ticker, preferred_period=reporting_period)
        
        shares_data = {
            'shares_outstanding': shares_outstanding,
            'weighted_avg_shares': get_value(income_stmt, 'WeightedAverageNumberOfSharesOutstandingBasic', ticker_prefix=ticker, preferred_period=reporting_period),
        }
        
        # Leverage
        leverage_data = {
            'total_debt': get_value(balance_sheet, 'LongTermDebt', ticker_prefix=ticker, preferred_period=reporting_period) or 
                         get_value(balance_sheet, 'Debt', ticker_prefix=ticker, preferred_period=reporting_period) or 
                         get_value(balance_sheet, 'NotesPayable', ticker_prefix=ticker, preferred_period=reporting_period),
            'revolving_credit_facility': get_value(balance_sheet, 'RevolvingCreditFacility', ticker_prefix=ticker, preferred_period=reporting_period),
        }
        
        # Build result
        result = {
            'ticker': ticker.upper(),
            'name': company_name,
            'period': period,
            'period_start': None,
            'period_end': None,
            'filing_date': None,  # Will be set by caller
            'accession_number': None,  # Will be set by caller
            'income_statement': income_data,
            'gains_losses': gains_losses,
            'balance_sheet': balance_data,
            'shares': shares_data,
            'leverage': leverage_data,
            'derived': self._calculate_derived_metrics({
                'income_statement': income_data,
                'balance_sheet': balance_data,
                'leverage': leverage_data,
                'shares': shares_data,
            }),
            'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
        }
        
        return result
    
    def _empty_financials(self, ticker: str, company_name: str, period: Optional[str]) -> Dict:
        """Return empty financials structure."""
        return {
            'ticker': ticker.upper(),
            'name': company_name,
            'period': period,
            'period_start': None,
            'period_end': None,
            'filing_date': None,
            'accession_number': None,
            'income_statement': {
                'total_investment_income': None,
                'net_investment_income': None,
                'net_investment_income_per_share': None,
                'total_expenses': None,
                'management_fees': None,
                'incentive_fees': None,
                'interest_expense': None,
            },
            'gains_losses': {
                'net_realized_gains': None,
                'net_unrealized_gains': None,
            },
            'balance_sheet': {
                'nav_per_share': None,
                'total_assets': None,
                'total_liabilities': None,
                'total_equity': None,
                'total_investments': None,
                'cash_and_cash_equivalents': None,
            },
            'shares': {
                'shares_outstanding': None,
                'weighted_avg_shares': None,
            },
            'leverage': {
                'total_debt': None,
                'revolving_credit_facility': None,
            },
            'derived': {},
            'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
        }
    
    def _calculate_derived_metrics(self, financials: Dict) -> Dict:
        """Calculate derived metrics like ratios, per-share values, etc."""
        derived = {}
        
        inc = financials.get('income_statement', {})
        bal = financials.get('balance_sheet', {})
        lev = financials.get('leverage', {})
        shares_data = financials.get('shares', {})
        
        nav_ps = bal.get('nav_per_share')
        nii = inc.get('net_investment_income')
        nii_ps = inc.get('net_investment_income_per_share')
        shares = shares_data.get('shares_outstanding') or shares_data.get('weighted_avg_shares')
        total_assets = bal.get('total_assets')
        total_liabilities = bal.get('total_liabilities')
        total_debt = lev.get('total_debt')
        
        # NII per share (if not provided, calculate)
        if not nii_ps and nii is not None and shares is not None and shares > 0:
            derived['net_investment_income_per_share'] = nii / shares
        
        # NAV total (if per share provided)
        if nav_ps is not None and shares is not None:
            derived['nav_total'] = nav_ps * shares
        
        # Leverage ratios
        if total_debt is not None and bal.get('total_equity') is not None:
            equity = bal['total_equity']
            if equity and equity != 0:
                derived['debt_to_equity'] = total_debt / equity
        
        if total_assets is not None and total_liabilities is not None:
            if total_assets and total_assets != 0:
                derived['asset_coverage'] = total_assets / (total_assets - total_liabilities) if (total_assets - total_liabilities) > 0 else None
        
        # Payout ratio (if dividends available)
        # Note: dividends would need to be extracted separately
        
        return derived

