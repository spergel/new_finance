#!/usr/bin/env python3
"""
XBRL Preferred Shares Extractor

Main orchestrator for XBRL preferred shares extraction.
Uses modular components for extraction, processing, model conversion, and saving.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import date

from core.sec_api_client import SECAPIClient
from core.xbrl_data_extractor import XBRLDataExtractor
from core.xbrl_data_processor import XBRLDataProcessor
from core.xbrl_data_models import XBRLDataModelConverter
from core.xbrl_data_saver import XBRLDataSaver
from core.models import XBRLPreferredSharesData, XBRLSummary, DataFusionResult

logger = logging.getLogger(__name__)


class XBRLPreferredSharesExtractor:
    """Extracts ONLY investment-relevant preferred shares data from XBRL filings."""

    def __init__(self):
        self.sec_client = SECAPIClient()
        self.extractor = XBRLDataExtractor()
        self.processor = XBRLDataProcessor()
        self.model_converter = XBRLDataModelConverter()
        self.data_saver = XBRLDataSaver()

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
            investment_data = self.extractor.extract_investment_relevant_data(filing_content)

            # Group by security (series/CUSIP combination)
            securities = self.processor.group_investment_data(investment_data)

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

    def get_preferred_shares_summary_from_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Get a focused summary of investment-relevant preferred shares data from existing result."""

        if "error" in result:
            return result

        securities = result.get("securities", [])
        ticker = result.get("ticker", "UNKNOWN")

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

        return self.model_converter.create_structured_xbrl_data(ticker, securities)

    def fuse_with_llm_data(self, xbrl_data: XBRLPreferredSharesData, llm_securities_data: List[Dict[str, Any]]) -> DataFusionResult:
        """Fuse XBRL data with LLM securities data for comprehensive results."""
        return self.model_converter.create_fusion_result(xbrl_data, llm_securities_data)

    def save_xbrl_results(self, xbrl_data: XBRLPreferredSharesData, output_dir: str = "output/xbrl"):
        """Save XBRL extraction results to JSON file."""
        return self.data_saver.save_xbrl_data(xbrl_data, output_dir)

    def save_fusion_results(self, fusion_result: DataFusionResult, output_dir: str = "output/fusion"):
        """Save data fusion results to JSON file."""
        return self.data_saver.save_fusion_results(fusion_result, output_dir)

    def save_summary_results(self, summary: XBRLSummary, output_dir: str = "output/summaries"):
        """Save XBRL summary results to JSON file."""
        return self.data_saver.save_xbrl_summary(summary, output_dir)


def extract_xbrl_preferred_shares(ticker: str) -> Dict[str, Any]:
    """Convenience function to extract XBRL preferred shares data."""
    extractor = XBRLPreferredSharesExtractor()

    # Get the full extraction result with investment data (only once!)
    result = extractor.extract_preferred_shares_from_10q(ticker)

    if "error" in result:
        return result

    # Save the detailed securities data to output/xbrl in CLEAN format
    securities = result.get("securities", [])
    if securities:
        extractor.data_saver.save_preferred_shares_data(ticker, securities)

    # Get and save summary (using the existing result, not re-extracting)
    summary = extractor.get_preferred_shares_summary_from_result(result)
    if summary.get("securities_found", 0) > 0:
        try:
            extractor.data_saver.save_extraction_summary(ticker, summary)
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
    print(f"Has preferred shares: {result.get('has_investment_data', False)}")
    print(f"Securities found: {result.get('securities_found', 0)}")
    print(f"Series identified: {result.get('series_identified', [])}")
    print(f"Data points extracted: {result.get('data_points_extracted', 0)}")
    if result.get('securities'):
        for sec in result['securities'][:2]:  # Show first 2 securities
            print(f"  Series {sec.get('series_name')}: Outstanding={sec.get('outstanding_shares')}, Rate={sec.get('dividend_rate')}")
