#!/usr/bin/env python3
"""
XBRL Preferred Shares Extractor

Extracts preferred share series information from XBRL data in 10-Q/10-K filings.
This provides structured data about outstanding shares, classifications, and institutional holdings.
"""

import re
import json
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import date
from core.sec_api_client import SECAPIClient
from core.models import XBRLSeriesIdentifier, XBRLPreferredSharesData, XBRLSummary, DataFusionSource, FusedSecurityData, DataFusionResult

logger = logging.getLogger(__name__)


class XBRLPreferredSharesExtractor:
    """Extracts ONLY investment-relevant preferred shares data from XBRL filings."""

    def __init__(self):
        self.sec_client = SECAPIClient()

    def _extract_investment_relevant_data(self, filing_content: str) -> List[Dict[str, Any]]:
        """Extract ACTUAL investment-relevant financial data from XBRL content."""

        investment_data = []

        # 0. XBRL TAG PARSING: Extract series from XBRL XML tags (catches securities not in readable text)
        # Look for patterns like "us-gaap:SeriesAPreferredStockMember" or "bw:SeriesAPreferredStockMember"
        xbrl_series_pattern = r'(?:us-gaap:|[a-z]+:)Series([A-Z]+)PreferredStockMember'
        xbrl_matches = re.findall(xbrl_series_pattern, filing_content)
        for series_letter in set(xbrl_matches):  # Use set to deduplicate
            investment_data.append({
                "type": "series_name",
                "name": series_letter,
                "confidence": 0.99,  # High confidence - from actual XBRL tags
                "source": "xbrl_tags"
            })
            logger.info(f"Found Series {series_letter} Preferred from XBRL tags")

        # 1. SPECIAL PATTERN: Extract complete balance sheet line for preferred stock
        # Example: "Series A non-cumulative preferred stock...: 24,000 shares authorized; 22,000 shares issued and outstanding...; liquidation preference $25,000 per share"
        balance_sheet_pattern = (
            r'Series\s+([A-Z])\s+'  # "Series A"
            r'[^:]{0,200}:\s*'  # "... :"
            r'(.{0,500})'  # Capture everything after the colon
        )
        
        balance_sheet_matches = re.findall(balance_sheet_pattern, filing_content, re.IGNORECASE)
        for series_letter, content_after_colon in balance_sheet_matches:
            # Now extract specific data from the content after the colon
            authorized_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s+shares\s+authorized', content_after_colon, re.IGNORECASE)
            outstanding_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s+shares\s+issued\s+and\s+outstanding', content_after_colon, re.IGNORECASE)
            liq_pref_match = re.search(r'liquidation\s+preference\s+\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', content_after_colon, re.IGNORECASE)
            
            # Create a comprehensive data point if we found financial data
            if outstanding_match or liq_pref_match:
                data_point = {
                    "type": "complete_series",
                    "series_name": series_letter,
                    "confidence": 0.99
                }
                
                if outstanding_match:
                    data_point["outstanding_shares"] = int(outstanding_match.group(1).replace(',', ''))
                if liq_pref_match:
                    data_point["par_value"] = float(liq_pref_match.group(1).replace(',', ''))
                if authorized_match:
                    data_point["authorized_shares"] = int(authorized_match.group(1).replace(',', ''))
                
                investment_data.append(data_point)

        # 2. Extract dividend/interest rates WITH SERIES CONTEXT
        # Pattern A: "Series A ... dividend rate ... 5.25% per annum" (rate after series)
        # Note: Use .{0,1000} not [^0-9]{0,1000} because there may be numbers like "$533 million" between Series and rate
        rate_with_series_pattern = r'Series\s+([A-Z]+).{0,1000}?(?:dividend|interest)\s+rate.{0,200}?(\d+\.\d+)%\s*per\s+annum'
        context_matches = re.findall(rate_with_series_pattern, filing_content, re.IGNORECASE | re.DOTALL)
        for series_letter, rate_str in context_matches:
            try:
                numeric_rate = float(rate_str)
                if 0 < numeric_rate < 100:
                    investment_data.append({
                        "type": "dividend_rate",
                        "rate": numeric_rate,
                        "series_name": series_letter,  # Link to series!
                        "confidence": 0.98
                    })
            except ValueError:
                pass
        
        # Pattern B: "5.25% ... Preferred Stock, Series A" (rate before series)
        # Common in certificates of designation like Citigroup's filings
        reverse_rate_pattern = r'(\d+\.\d+)%\s+(?:Fixed Rate|Floating Rate|Non-Cumulative|Noncumulative|Cumulative)[^,]{0,100}?(?:Preferred Stock|preferred stock),?\s+Series\s+([A-Z]+)'
        reverse_matches = re.findall(reverse_rate_pattern, filing_content, re.IGNORECASE | re.DOTALL)
        for rate_str, series_letter in reverse_matches:
            try:
                numeric_rate = float(rate_str)
                if 0 < numeric_rate < 100:
                    investment_data.append({
                        "type": "dividend_rate",
                        "rate": numeric_rate,
                        "series_name": series_letter,  # Link to series!
                        "confidence": 0.95
                    })
            except ValueError:
                pass

        # Fallback: rates without clear series context
        rate_patterns = [
            r'dividend\s+rate[^0-9]{0,50}?(\d+\.\d+)%\s*per\s+annum',
            r'dividend\s+rate[^0-9]{0,20}?(\d+\.\d+)%',
        ]
        for pattern in rate_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for match in matches[:5]:  # Limit to avoid noise
                try:
                    numeric_rate = float(match)
                    if 0 < numeric_rate < 100:
                        investment_data.append({
                            "type": "dividend_rate",
                            "rate": numeric_rate,
                            "confidence": 0.7  # Lower confidence without context
                        })
                except ValueError:
                    pass

        # 3. Extract outstanding share amounts WITH CONTEXT
        # Look for "Series A ... 22,000 shares issued and outstanding"
        shares_with_context_pattern = r'Series\s+([A-Z])[^0-9]{0,500}?(\d{1,3}(?:,\d{3})*)\s+shares\s+issued\s+and\s+outstanding'
        context_matches = re.findall(shares_with_context_pattern, filing_content, re.IGNORECASE)
        for series_letter, shares_str in context_matches:
            clean_amount = shares_str.replace(',', '')
            try:
                numeric_amount = int(clean_amount)
                if 1000 < numeric_amount < 100_000_000:
                    investment_data.append({
                        "type": "outstanding_shares",
                        "amount": numeric_amount,
                        "series_name": series_letter,  # Link to series!
                        "confidence": 0.98
                    })
            except ValueError:
                pass

        # Fallback: shares without clear series context
        outstanding_patterns = [
            r'(\d{1,3}(?:,\d{3})*)\s+shares\s+issued\s+and\s+outstanding',
        ]
        for pattern in outstanding_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for match in matches[:5]:  # Limit to avoid noise
                clean_amount = match.replace(',', '')
                try:
                    numeric_amount = int(clean_amount)
                    if 1000 < numeric_amount < 100_000_000:
                        investment_data.append({
                            "type": "outstanding_shares",
                            "amount": numeric_amount,
                            "confidence": 0.7  # Lower confidence without context
                        })
                except ValueError:
                    pass

        # 4. Extract liquidation preference/par values WITH CONTEXT
        # "Series A ... liquidation preference $25,000 per share"
        liq_with_context_pattern = r'Series\s+([A-Z])[^$]{0,500}?liquidation\s+preference\s+\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)'
        context_matches = re.findall(liq_with_context_pattern, filing_content, re.IGNORECASE)
        for series_letter, value_str in context_matches:
            clean_value = value_str.replace(',', '')
            try:
                numeric_value = float(clean_value)
                if numeric_value > 0:
                    investment_data.append({
                        "type": "par_value",
                        "value": numeric_value,
                        "series_name": series_letter,  # Link to series!
                        "confidence": 0.98
                    })
            except ValueError:
                pass

        # Fallback: liquidation preference without series context
        par_patterns = [
            r'liquidation\s+preference\s+\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
        ]
        for pattern in par_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for match in matches[:5]:  # Limit to avoid noise
                clean_value = match.replace(',', '')
                try:
                    numeric_value = float(clean_value)
                    if numeric_value > 0:
                        investment_data.append({
                            "type": "par_value",
                            "value": numeric_value,
                            "confidence": 0.7  # Lower confidence without context
                        })
                except ValueError:
                    pass

        # 5. Extract cumulative vs non-cumulative WITH SERIES CONTEXT
        # "Series A Non-Cumulative Preferred Stock"
        cumulative_with_series = r'Series\s+([A-Z]+)[^.]{0,200}?(non-cumulative|noncumulative|cumulative)'
        cum_matches = re.findall(cumulative_with_series, filing_content, re.IGNORECASE)
        for series_letter, cum_type in cum_matches:
            is_cumulative = 'non' not in cum_type.lower()
            investment_data.append({
                "type": "cumulative_status",
                "is_cumulative": is_cumulative,
                "series_name": series_letter,
                "confidence": 0.95
            })

        # 6. Extract voting rights WITH SERIES CONTEXT
        # "Series A ... voting rights" or "Series A ... non-voting"
        voting_patterns = [
            (r'Series\s+([A-Z]+)[^.]{0,300}?non-voting', False, 0.9),
            (r'Series\s+([A-Z]+)[^.]{0,300}?no\s+voting\s+rights', False, 0.9),
            (r'Series\s+([A-Z]+)[^.]{0,300}?entitled\s+to\s+vote', True, 0.85),
            (r'Series\s+([A-Z]+)[^.]{0,300}?voting\s+rights', True, 0.8),
        ]
        for pattern, has_voting, conf in voting_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for series_letter in matches:
                investment_data.append({
                    "type": "voting_rights",
                    "has_voting_rights": has_voting,
                    "series_name": series_letter,
                    "confidence": conf
                })

        # 7. Extract redemption/call information WITH SERIES CONTEXT
        # "Series A ... redeemable on or after March 30, 2028"
        redemption_patterns = [
            # Callable/redeemable with date
            (r'Series\s+([A-Z]+)[^.]{0,500}?(?:callable|redeemable)[^.]{0,200}?(?:on or after|after|on)\s+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})', 'date'),
            # Optional redemption
            (r'Series\s+([A-Z]+)[^.]{0,300}?optional\s+redemption', 'optional'),
            # Mandatory redemption
            (r'Series\s+([A-Z]+)[^.]{0,300}?mandatory\s+redemption', 'mandatory'),
            # Not redeemable
            (r'Series\s+([A-Z]+)[^.]{0,300}?(?:not|non)\s+redeemable', 'not_redeemable'),
        ]
        for pattern, redemption_type in redemption_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for match in matches:
                if redemption_type == 'date':
                    series_letter, date_str = match
                    investment_data.append({
                        "type": "redemption_info",
                        "is_callable": True,
                        "redemption_type": "optional",
                        "earliest_call_date": date_str,
                        "series_name": series_letter,
                        "confidence": 0.9
                    })
                else:
                    investment_data.append({
                        "type": "redemption_info",
                        "is_callable": redemption_type not in ['not_redeemable'],
                        "redemption_type": redemption_type,
                        "series_name": match if isinstance(match, str) else match[0],
                        "confidence": 0.85
                    })

        # 8. Extract ranking/priority WITH SERIES CONTEXT
        # "Series A ... ranks senior to" or "ranks pari passu with"
        ranking_patterns = [
            (r'Series\s+([A-Z]+)[^.]{0,300}?rank(?:s|ing)?\s+(?:senior|prior)', 'senior', 0.9),
            (r'Series\s+([A-Z]+)[^.]{0,300}?rank(?:s|ing)?\s+junior', 'junior', 0.9),
            (r'Series\s+([A-Z]+)[^.]{0,300}?rank(?:s|ing)?\s+(?:pari\s+passu|equal|equally)', 'pari_passu', 0.9),
            (r'Series\s+([A-Z]+)[^.]{0,300}?subordinated', 'subordinated', 0.85),
        ]
        for pattern, rank_type, conf in ranking_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for series_letter in matches:
                investment_data.append({
                    "type": "ranking",
                    "ranking": rank_type,
                    "series_name": series_letter,
                    "confidence": conf
                })

        # 9. Extract payment frequency WITH SERIES CONTEXT
        # "Series A ... dividends payable quarterly"
        frequency_patterns = [
            (r'Series\s+([A-Z]+)[^.]{0,300}?(?:dividends?\s+)?payable\s+(quarterly|monthly|annually|semi-annually)', 0.9),
            (r'Series\s+([A-Z]+)[^.]{0,300}?paid\s+(quarterly|monthly|annually|semi-annually)', 0.85),
        ]
        for pattern, conf in frequency_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for series_letter, frequency in matches:
                investment_data.append({
                    "type": "payment_frequency",
                    "frequency": frequency.lower(),
                    "series_name": series_letter,
                    "confidence": conf
                })

        # 10. Extract maturity/call dates (generic fallback - lower confidence)
        date_patterns = [
            r'(?:matur|call|redemp).*?([0-9]{4}-[0-9]{2}-[0-9]{2})',
            r'([0-9]{4}-[0-9]{2}-[0-9]{2}).*?(?:matur|call|redemp)',
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for match in matches[:5]:  # Limit to avoid noise
                investment_data.append({
                    "type": "maturity_or_call_date",
                    "date": match,
                    "confidence": 0.6
                })

        # 11. Extract CUSIPs and series names (identifiers)
        identifier_patterns = [
            r'Series\s+([A-Z]+)',
            r'([A-Z]{2}[0-9]{4}[A-Z0-9]{3})',  # CUSIP
        ]

        for pattern in identifier_patterns:
            matches = re.findall(pattern, filing_content, re.IGNORECASE)
            for match in matches:
                if re.match(r'[A-Z]{2}[0-9]{4}[A-Z0-9]{3}', str(match)):
                    # This is a CUSIP
                    investment_data.append({
                        "type": "cusip",
                        "identifier": match,
                        "confidence": 0.9
                    })
                else:
                    # This is a series name
                    investment_data.append({
                        "type": "series_name",
                        "name": match,
                        "confidence": 0.8
                    })

        return investment_data

    def extract_preferred_shares_from_10q(self, ticker: str) -> Dict[str, Any]:
        """
        Extract ONLY investment-relevant preferred shares information from 10-Q filing.

        Focuses on data that matters for investment decisions:
        - Series identification and CUSIPs
        - Interest rates and yields
        - Outstanding amounts
        - Maturity and call dates
        """
        logger.info(f"Extracting investment-relevant preferred shares data for {ticker}")

        try:
            filing_content = self.sec_client.get_filing_text(ticker, '10-Q')
            if not filing_content:
                return {"error": "No 10-Q filing found", "ticker": ticker}

            # Extract only investment-relevant data
            investment_data = self._extract_investment_relevant_data(filing_content)

            # Group by security (series/CUSIP combination)
            securities = self._group_investment_data(investment_data)

            return {
                "ticker": ticker,
                "filing_type": "10-Q",
                "extraction_date": date.today().isoformat(),
                "securities_found": len(securities),
                "securities": securities,
                "total_data_points": len(investment_data)
            }

        except Exception as e:
            logger.error(f"Error extracting investment data for {ticker}: {e}")
            return {"error": str(e), "ticker": ticker}

    def _group_investment_data(self, investment_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group investment data points by security."""
        securities = {}

        for data_point in investment_data:
            # Handle complete_series type specially - it has everything in one data point
            if data_point["type"] == "complete_series":
                series_name = data_point.get("series_name")
                if series_name:
                    securities[series_name] = {
                        "security_id": f"Series {series_name}",
                        "series_name": series_name,
                        "cusip": None,
                        "dividend_rate": data_point.get("dividend_rate"),
                        "outstanding_shares": data_point.get("outstanding_shares"),
                        "par_value": data_point.get("par_value"),
                        "authorized_shares": data_point.get("authorized_shares"),
                        "is_callable": None,
                        "call_date": None,
                        "is_cumulative": None,
                        "has_voting_rights": None,
                        "redemption_type": None,
                        "ranking": None,
                        "payment_frequency": None,
                        "confidence": data_point.get("confidence", 0.99)
                    }
                continue

            # Create a key based on the most identifying information
            if data_point["type"] == "cusip" and data_point.get("identifier"):
                key = data_point["identifier"]
            elif data_point.get("name"):  # series_name is stored as "name"
                key = data_point["name"]
            elif data_point.get("series_name"):
                key = data_point["series_name"]
            else:
                continue  # Skip data points without clear identifiers

            if key not in securities:
                securities[key] = {
                    "security_id": key,
                    "series_name": data_point.get("name") or data_point.get("series_name"),
                    "cusip": data_point.get("identifier") if data_point["type"] == "cusip" else None,
                    "dividend_rate": None,
                    "outstanding_shares": None,
                    "par_value": None,
                    "authorized_shares": None,
                    "is_callable": None,
                    "call_date": None,
                    "is_cumulative": None,
                    "has_voting_rights": None,
                    "redemption_type": None,
                    "ranking": None,
                    "payment_frequency": None,
                    "confidence": data_point.get("confidence", 0.5)
                }

            # Add the specific data point - handle all the new data types
            if data_point["type"] == "dividend_rate" and securities[key]["dividend_rate"] is None:
                securities[key]["dividend_rate"] = data_point["rate"]
            elif data_point["type"] == "outstanding_shares" and securities[key]["outstanding_shares"] is None:
                securities[key]["outstanding_shares"] = data_point["amount"]
            elif data_point["type"] == "par_value" and securities[key]["par_value"] is None:
                securities[key]["par_value"] = data_point["value"]
            elif data_point["type"] == "authorized_shares" and securities[key]["authorized_shares"] is None:
                securities[key]["authorized_shares"] = data_point["amount"]
            elif data_point["type"] == "call_date":
                securities[key]["call_date"] = data_point.get("date")
                securities[key]["is_callable"] = True
            elif data_point["type"] == "cusip" and securities[key]["cusip"] is None:
                securities[key]["cusip"] = data_point.get("identifier")
            elif data_point["type"] == "cumulative_status" and securities[key]["is_cumulative"] is None:
                securities[key]["is_cumulative"] = data_point.get("is_cumulative")
            elif data_point["type"] == "voting_rights" and securities[key]["has_voting_rights"] is None:
                securities[key]["has_voting_rights"] = data_point.get("has_voting_rights")
            elif data_point["type"] == "redemption_info":
                if securities[key]["is_callable"] is None:
                    securities[key]["is_callable"] = data_point.get("is_callable")
                if securities[key]["redemption_type"] is None:
                    securities[key]["redemption_type"] = data_point.get("redemption_type")
                if data_point.get("earliest_call_date") and securities[key]["call_date"] is None:
                    securities[key]["call_date"] = data_point.get("earliest_call_date")
            elif data_point["type"] == "ranking" and securities[key]["ranking"] is None:
                securities[key]["ranking"] = data_point.get("ranking")
            elif data_point["type"] == "payment_frequency" and securities[key]["payment_frequency"] is None:
                securities[key]["payment_frequency"] = data_point.get("frequency")

            # Update confidence if this data point has higher confidence
            if data_point.get("confidence", 0) > securities[key]["confidence"]:
                securities[key]["confidence"] = data_point["confidence"]

        # FILTER OUT JUNK: Only keep securities with actual financial data
        filtered_securities = []
        for sec in securities.values():
            # Must have at least 2 of: outstanding_shares, par_value, dividend_rate, OR be Series A-Z with data
            data_points = sum([
                sec.get("outstanding_shares") is not None,
                sec.get("par_value") is not None,
                sec.get("dividend_rate") is not None,
                sec.get("authorized_shares") is not None
            ])
            
            # Keep if: has 2+ data points AND (high confidence OR is a valid series name)
            # Valid series: 1-3 letters (A, RR, AAA, etc.)
            is_valid_series = (sec.get("series_name") and 
                              len(sec.get("series_name", "")) <= 3 and 
                              sec.get("series_name").isalpha())
            
            # Keep if:
            # 1. Has 2+ data points (likely real security)
            # 2. Has 1+ data points AND is valid series with high confidence
            # 3. Is valid series from XBRL tags with VERY high confidence (0.99) even without data
            if (data_points >= 2 or 
                (data_points >= 1 and is_valid_series and sec.get("confidence", 0) > 0.95) or
                (is_valid_series and sec.get("confidence", 0) >= 0.99)):
                filtered_securities.append(sec)
        
        return filtered_securities

    def get_preferred_shares_summary(self, ticker: str) -> Dict[str, Any]:
        """Get a focused summary of investment-relevant preferred shares data."""

        result = self.extract_preferred_shares_from_10q(ticker)

        if "error" in result:
            return result

        securities = result.get("securities", [])

        # Extract key identifiers and financial data
        series_names = set()
        cusips = set()
        total_dividend_rate = 0.0
        total_outstanding = 0
        securities_with_rates = 0

        for security in securities:
            if security.get("series_name"):
                series_names.add(security["series_name"])
            if security.get("cusip"):
                cusips.add(security["cusip"])

            # Sum up financial data for averaging
            if security.get("dividend_rate"):
                total_dividend_rate += security["dividend_rate"]
                securities_with_rates += 1
            if security.get("outstanding_shares"):
                total_outstanding += security["outstanding_shares"]

        avg_dividend_rate = total_dividend_rate / securities_with_rates if securities_with_rates > 0 else 0.0

        # Investment-focused summary
        return {
            "ticker": ticker,
            "filing_type": result.get("filing_type", "10-Q"),
            "extraction_date": result.get("extraction_date"),
            "securities_found": len(securities),
            "has_investment_data": len(securities) > 0,
            "series_identified": sorted(list(series_names)),
            "cusips_identified": sorted(list(cusips)),
            "average_dividend_rate": round(avg_dividend_rate, 2),
            "total_outstanding_shares": total_outstanding,
            "data_points_extracted": result.get("total_data_points", 0),
            "investment_relevance_score": min(1.0, len(series_names) * 0.3 + len(cusips) * 0.4 + min(avg_dividend_rate / 10, 0.3))
        }



    def get_structured_xbrl_data(self, ticker: str) -> XBRLPreferredSharesData:
        """Get structured XBRL data using the new model format - focused on actionable data only."""
        result = self.extract_preferred_shares_from_10q(ticker)

        if "error" in result:
            raise ValueError(f"XBRL extraction failed: {result['error']}")

        securities = result.get("securities", [])

        # Convert securities to structured model format
        series_identifiers = []
        numeric_values = []

        for security in securities:
            # Add series identifier
            identifier = XBRLSeriesIdentifier(
                series_name=security.get("series_name"),
                cusip=security.get("cusip"),
                xbrl_tag="InvestmentRelevant",
                source="investment_focused_extraction",
                confidence=security.get("confidence", 0.8)
            )
            series_identifiers.append(identifier)

            # Add financial values as numeric data
            if security.get("dividend_rate"):
                numeric_values.append(str(security["dividend_rate"]))
            if security.get("outstanding_shares"):
                numeric_values.append(str(security["outstanding_shares"]))
            if security.get("par_value"):
                numeric_values.append(str(security["par_value"]))

        return XBRLPreferredSharesData(
            ticker=ticker,
            filing_type=result.get("filing_type", "10-Q"),
            extraction_date=date.fromisoformat(result.get("extraction_date", date.today().isoformat())),
            xbrl_available=True,
            series_identifiers=series_identifiers,
            numeric_values=numeric_values[:5],  # Limit to most relevant values
            contexts_found=0,
            tag_distribution={},
            data_quality_score=result.get("investment_relevance_score", 0.0)
        )

    def fuse_with_llm_data(self, xbrl_data: XBRLPreferredSharesData, llm_securities_data: List[Dict[str, Any]]) -> DataFusionResult:
        """Fuse XBRL data with LLM securities data for comprehensive results."""

        fused_securities = []

        # Create a mapping of series to XBRL data for easy lookup
        xbrl_series_map = {}
        for identifier in xbrl_data.series_identifiers:
            key = identifier.series_name or identifier.cusip or identifier.raw_match
            if key:
                xbrl_series_map[key.lower()] = identifier

        # Fuse each LLM security with XBRL data
        for llm_security in llm_securities_data:
            # Try to match with XBRL data
            security_id = llm_security.get("security_id", "")
            matched_xbrl = None

            # Look for matches in XBRL data
            for key in [security_id, security_id.lower(), security_id.replace(" ", "")]:
                if key in xbrl_series_map:
                    matched_xbrl = xbrl_series_map[key]
                    break

            # If no direct match, try fuzzy matching on series names
            if not matched_xbrl:
                for xbrl_key, xbrl_identifier in xbrl_series_map.items():
                    if (xbrl_identifier.series_name and
                        llm_security.get("description", "").lower().find(xbrl_identifier.series_name.lower()) != -1):
                        matched_xbrl = xbrl_identifier
                        break

            # Create fused security data
            fused_security = FusedSecurityData(
                security_id=security_id,
                company=llm_security.get("company", ""),
                filing_date=llm_security.get("filing_date"),
                source_filing=llm_security.get("source_filing", ""),

                # XBRL data
                xbrl_series_name=matched_xbrl.series_name if matched_xbrl else None,
                xbrl_cusip=matched_xbrl.cusip if matched_xbrl else None,

                # LLM data
                llm_description=llm_security.get("description"),
                llm_conversion_terms=str(llm_security.get("conversion_terms", {})) if llm_security.get("conversion_terms") else None,
                llm_redemption_terms=str(llm_security.get("redemption_terms", {})) if llm_security.get("redemption_terms") else None,
                llm_special_features=str(llm_security.get("special_features", {})) if llm_security.get("special_features") else None,

                # Metadata
                data_sources=[DataFusionSource.XBRL, DataFusionSource.LLM] if matched_xbrl else [DataFusionSource.LLM],
                confidence_score=self._calculate_fusion_confidence(matched_xbrl, llm_security),
                last_updated=date.today()
            )

            fused_securities.append(fused_security)

        # Calculate overall metrics
        xbrl_available = len([s for s in fused_securities if DataFusionSource.XBRL in s.data_sources]) > 0
        llm_available = len([s for s in fused_securities if DataFusionSource.LLM in s.data_sources]) > 0

        # Calculate overall confidence (weighted average)
        total_confidence = sum(s.confidence_score for s in fused_securities)
        overall_confidence = total_confidence / len(fused_securities) if fused_securities else 0.0

        # Calculate data completeness (how many fields are filled)
        total_fields = len(FusedSecurityData.__fields__) - 3  # Exclude metadata fields
        filled_fields = sum(
            sum(1 for field in [s.xbrl_series_name, s.xbrl_cusip, s.llm_description,
                               s.llm_conversion_terms, s.llm_redemption_terms, s.llm_special_features]
                if field is not None)
            for s in fused_securities
        )
        data_completeness_score = filled_fields / (len(fused_securities) * total_fields) if fused_securities else 0.0

        return DataFusionResult(
            ticker=xbrl_data.ticker,
            fusion_date=date.today(),
            xbrl_data_available=xbrl_available,
            llm_data_available=llm_available,
            fused_securities=fused_securities,
            total_securities=len(fused_securities),
            overall_confidence=overall_confidence,
            data_completeness_score=data_completeness_score
        )

    def _calculate_fusion_confidence(self, xbrl_data: Optional[XBRLSeriesIdentifier], llm_data: Dict[str, Any]) -> float:
        """Calculate confidence score for fused data based on data quality and matching."""
        confidence = 0.5  # Base confidence

        # Boost confidence if we have XBRL data
        if xbrl_data:
            confidence += 0.3
            if xbrl_data.cusip:
                confidence += 0.1  # CUSIP is highly reliable
            if xbrl_data.series_name:
                confidence += 0.1  # Series name is reliable

        # Boost confidence if LLM data has detailed information
        if llm_data.get("description"):
            confidence += 0.1
        if llm_data.get("conversion_terms"):
            confidence += 0.05
        if llm_data.get("redemption_terms"):
            confidence += 0.05
        if llm_data.get("special_features"):
            confidence += 0.05

        return min(confidence, 1.0)  # Cap at 1.0

    def save_xbrl_results(self, xbrl_data: XBRLPreferredSharesData, output_dir: str = "output/xbrl"):
        """Save XBRL extraction results to JSON file."""
        os.makedirs(output_dir, exist_ok=True)

        filename = f"{xbrl_data.ticker}_xbrl_data.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(xbrl_data.dict(), f, indent=2, default=str)

        logger.info(f"Saved XBRL data to {filepath}")
        return filepath

    def save_fusion_results(self, fusion_result: DataFusionResult, output_dir: str = "output/fusion"):
        """Save data fusion results to JSON file."""
        os.makedirs(output_dir, exist_ok=True)

        filename = f"{fusion_result.ticker}_fused_data.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(fusion_result.dict(), f, indent=2, default=str)

        logger.info(f"Saved fusion data to {filepath}")
        return filepath

    def save_summary_results(self, summary: XBRLSummary, output_dir: str = "output/summaries"):
        """Save XBRL summary results to JSON file."""
        os.makedirs(output_dir, exist_ok=True)

        filename = f"{summary.ticker}_xbrl_summary.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(summary.dict(), f, indent=2, default=str)

        logger.info(f"Saved XBRL summary to {filepath}")
        return filepath


def extract_xbrl_preferred_shares(ticker: str) -> Dict[str, Any]:
    """Convenience function to extract XBRL preferred shares data."""
    extractor = XBRLPreferredSharesExtractor()

    # Get the full extraction result with investment data
    result = extractor.extract_preferred_shares_from_10q(ticker)

    if "error" in result:
        return result

    # Save the detailed securities data to output/xbrl in CLEAN format
    securities = result.get("securities", [])
    if securities:
        os.makedirs("output/xbrl", exist_ok=True)
        xbrl_filepath = f"output/xbrl/{ticker}_xbrl_data.json"
        
        # Transform to clean format
        clean_securities = []
        for sec in securities:
            clean_sec = {
                "series": sec.get("series_name"),
                "description": f"Series {sec.get('series_name')} Preferred Stock" if sec.get("series_name") else None,
                "cusip": sec.get("cusip"),
                "outstanding_shares": sec.get("outstanding_shares"),
                "authorized_shares": sec.get("authorized_shares"),
                "liquidation_preference_per_share": sec.get("par_value"),
                "dividend_rate": sec.get("dividend_rate"),
                "is_cumulative": sec.get("is_cumulative"),
                "payment_frequency": sec.get("payment_frequency"),
                "par_value": 1.0 if sec.get("series_name") else None,  # Typically $1 par for preferred
                "is_callable": sec.get("is_callable"),
                "call_date": sec.get("call_date"),
                "redemption_type": sec.get("redemption_type"),
                "has_voting_rights": sec.get("has_voting_rights"),
                "ranking": sec.get("ranking"),
                "confidence": sec.get("confidence")
            }
            # Remove None values for cleaner output
            clean_sec = {k: v for k, v in clean_sec.items() if v is not None}
            clean_securities.append(clean_sec)
        
        clean_output = {
            "ticker": ticker,
            "filing_type": result.get("filing_type", "10-Q"),
            "filing_date": str(result.get("extraction_date")),
            "extraction_date": str(result.get("extraction_date")),
            "preferred_shares": clean_securities
        }
        
        with open(xbrl_filepath, 'w') as f:
            json.dump(clean_output, f, indent=2, default=str)
        logger.info(f"Saved XBRL securities data to {xbrl_filepath}")

    # Get and save summary
    summary = extractor.get_preferred_shares_summary(ticker)
    if summary.get("securities_found", 0) > 0:
        try:
            summary_for_file = {
                "ticker": ticker,
                "has_preferred_shares": summary.get("securities_found", 0) > 0,
                "securities_found": summary.get("securities_found", 0),
                "series_identified": summary.get("series_identified", []),
                "cusips_identified": summary.get("cusips_identified", []),
                "average_dividend_rate": summary.get("average_dividend_rate", 0.0),
                "total_outstanding_shares": summary.get("total_outstanding_shares", 0),
                "investment_relevance_score": summary.get("investment_relevance_score", 0.0)
            }
            os.makedirs("output/summaries", exist_ok=True)
            summary_filepath = f"output/summaries/{ticker}_xbrl_summary.json"
            with open(summary_filepath, 'w') as f:
                json.dump(summary_for_file, f, indent=2, default=str)
            logger.info(f"Saved XBRL summary to {summary_filepath}")
        except Exception as e:
            logger.warning(f"Could not save XBRL summary for {ticker}: {e}")

    # Add securities to the returned summary
    summary["securities"] = securities
    return summary


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python xbrl_preferred_shares_extractor.py <TICKER>")
        sys.exit(1)

    ticker = sys.argv[1]
    result = extract_xbrl_preferred_shares(ticker)

    print(f"XBRL Preferred Shares Analysis for {ticker}")
    print("=" * 50)
    print(f"Has preferred shares: {result['has_preferred_shares']}")
    print(f"XBRL tags found: {result['xbrl_tags_found']}")
    print(f"Series identified: {result['series_identified']}")
    print(f"Total mentions: {result['total_mentioned']}")
    print(f"Tag distribution: {result['tag_distribution']}")
