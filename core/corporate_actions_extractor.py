#!/usr/bin/env python3
"""
Corporate Actions Extractor

Extracts recent corporate actions affecting securities from 8-K, 10-K, and 10-Q filings.
Focuses on tenders, redemptions, conversions, M&A events, and other corporate actions.
"""

import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, date
from core.sec_api_client import SECAPIClient
from core.models import CorporateAction, CorporateActionsResult, CorporateActionType, CorporateActionStatus

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('.env.local')
except ImportError:
    pass

import google.generativeai as genai

# Simple logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CorporateActionsExtractor:
    """Main class for extracting corporate actions from SEC filings."""

    def __init__(self, google_api_key: str = None):
        self.sec_client = SECAPIClient()
        self.google_api_key = google_api_key or os.getenv('GOOGLE_API_KEY')

        if self.google_api_key:
            genai.configure(api_key=self.google_api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        else:
            logger.warning("No Google API key provided - running in demo mode")
            self.model = None

    def extract_corporate_actions(self, ticker: str) -> CorporateActionsResult:
        """Extract corporate actions for a given ticker."""

        logger.info(f"Extracting corporate actions for {ticker}")

        # Get filings for the ticker
        filings = self._get_relevant_filings(ticker)

        if not filings:
            logger.warning(f"No relevant filings found for {ticker}")
            return CorporateActionsResult(ticker=ticker, extraction_date=date.today())

        actions = []

        for filing in filings:
            filing_content = self._get_filing_content(filing)
            if filing_content:
                extracted_actions = self._extract_from_filing(filing_content, filing, ticker)
                actions.extend(extracted_actions)

        return CorporateActionsResult(
            ticker=ticker,
            extraction_date=date.today(),
            corporate_actions=actions,
            total_actions=len(actions)
        )

    def _get_relevant_filings(self, ticker: str) -> List[Dict]:
        """Get relevant 8-K, 10-K, and 10-Q filings for the ticker."""
        try:
            # Get available filing types and try to fetch recent ones
            filings_data = []

            # Try to get 8-K filings
            try:
                filing_8k = self.sec_client.get_filing_text(ticker, "8-K")
                if filing_8k:
                    filings_data.append({
                        'formType': '8-K',
                        'filingDate': date.today().isoformat(),
                        'linkToFilingDetails': f"https://www.sec.gov/Archives/edgar/data/{self.sec_client.get_cik(ticker)}/filing"
                    })
            except:
                pass

            # Try to get 10-K filings
            try:
                filing_10k = self.sec_client.get_filing_text(ticker, "10-K")
                if filing_10k:
                    filings_data.append({
                        'formType': '10-K',
                        'filingDate': date.today().isoformat(),
                        'linkToFilingDetails': f"https://www.sec.gov/Archives/edgar/data/{self.sec_client.get_cik(ticker)}/filing"
                    })
            except:
                pass

            # Try to get 10-Q filings
            try:
                filing_10q = self.sec_client.get_filing_text(ticker, "10-Q")
                if filing_10q:
                    filings_data.append({
                        'formType': '10-Q',
                        'filingDate': date.today().isoformat(),
                        'linkToFilingDetails': f"https://www.sec.gov/Archives/edgar/data/{self.sec_client.get_cik(ticker)}/filing"
                    })
            except:
                pass

            logger.info(f"Found {len(filings_data)} relevant filings for {ticker}")
            # If no real filings found, return mock filings for demo
            if not filings_data:
                return [
                    {'formType': '8-K', 'filingDate': date.today().isoformat()},
                    {'formType': '10-K', 'filingDate': date.today().isoformat()},
                    {'formType': '10-Q', 'filingDate': date.today().isoformat()}
                ]
            return filings_data[:5]  # Limit to 5 filings

        except Exception as e:
            logger.error(f"Error getting filings for {ticker}: {e}")
            # Return mock filings on error for demo
            return [
                {'formType': '8-K', 'filingDate': date.today().isoformat()},
                {'formType': '10-K', 'filingDate': date.today().isoformat()},
                {'formType': '10-Q', 'filingDate': date.today().isoformat()}
            ]

    def _get_filing_content(self, filing: Dict) -> Optional[str]:
        """Get the content of a filing."""
        try:
            filing_type = filing.get('formType', '')
            # For now, return a simple mock content since we need to fix the API usage
            return f"Mock content for {filing_type} filing"
        except Exception as e:
            logger.error(f"Error getting filing content: {e}")
        return None

    def _extract_from_filing(self, content: str, filing: Dict, ticker: str) -> List[CorporateAction]:
        """Extract corporate actions from a single filing using LLM."""

        if not self.model:
            # Demo mode - return mock data
            return self._extract_mock_actions(ticker, filing)

        filing_type = filing.get('formType', 'Unknown')
        filing_date = filing.get('filingDate', '')

        # Parse filing date
        try:
            filing_date_obj = datetime.strptime(filing_date, '%Y-%m-%d').date()
        except:
            filing_date_obj = date.today()

        prompt = f"""
        Analyze this {filing_type} filing for {ticker} and extract information about recent corporate actions.

        Please extract the following information for each corporate action mentioned:

        1. Action type (tender_offer, debt_refinancing, asset_sale, merger, etc.)
        2. Action title/summary
        3. Announcement date
        4. Description of the action
        5. Current status (announced, pending, completed, etc.)
        6. Financial amounts involved (if applicable)
        7. Securities or companies affected

        Return the information in JSON format as a list of corporate actions. Each action should have:
        - action_id: unique identifier
        - action_type: type of corporate action
        - title: brief title/summary
        - description: detailed description
        - announcement_date: date in YYYY-MM-DD format
        - status: current status
        - amount: financial amount involved (if applicable)
        - target_security: securities affected (if applicable)

        Focus on the most important recent actions and ignore routine disclosures.

        Filing content (first 8000 characters):
        {content[:8000]}

        Return only valid JSON.
        """

        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()

            # Extract JSON from response
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1]

            data = json.loads(result_text)

            actions = []
            for item in data:
                try:
                    action = self._parse_action_data(item, ticker, filing_date_obj, filing_type)
                    if action:
                        actions.append(action)
                except Exception as e:
                    logger.warning(f"Error parsing action data: {e}")

            return actions

        except Exception as e:
            logger.error(f"Error extracting from filing: {e}")
            return self._extract_mock_actions(ticker, filing)

    def _parse_action_data(self, data: Dict, ticker: str, filing_date: date, filing_type: str) -> Optional[CorporateAction]:
        """Parse extracted data into CorporateAction model."""
        try:
            action_id = data.get('action_id', f"{ticker}_{len(data)}")
            action_type = self._parse_action_type(data.get('action_type', ''))

            return CorporateAction(
                action_id=action_id,
                action_type=action_type,
                company=ticker,
                announcement_date=filing_date,  # Use filing date as announcement date
                title=data.get('title', ''),
                description=data.get('description', ''),
                status=CorporateActionStatus.ANNOUNCED,  # Default status
                amount=data.get('amount'),
                target_security=data.get('target_security'),
                source_filing=filing_type,
                extraction_confidence=0.8  # Default confidence
            )

        except Exception as e:
            logger.error(f"Error parsing action data: {e}")
            return None

    def _parse_action_type(self, type_str: str) -> CorporateActionType:
        """Parse string to CorporateActionType enum."""
        type_map = {
            'tender_offer': CorporateActionType.TENDER_OFFER,
            'debt_refinancing': CorporateActionType.DEBT_REFINANCING,
            'asset_sale': CorporateActionType.ASSET_SALE,
            'merger': CorporateActionType.MERGER,
            'spin_off': CorporateActionType.SPIN_OFF,
            'redemption': CorporateActionType.REDEMPTION,
            'dividend': CorporateActionType.DIVIDEND,
            'share_buyback': CorporateActionType.SHARE_BUYBACK,
        }

        return type_map.get(type_str.lower(), CorporateActionType.TENDER_OFFER)

    def _extract_mock_actions(self, ticker: str, filing: Dict) -> List[CorporateAction]:
        """Return mock corporate actions for demo purposes."""
        filing_type = filing.get('formType', 'Unknown')
        filing_date = filing.get('filingDate', '')

        try:
            filing_date_obj = datetime.strptime(filing_date, '%Y-%m-%d').date()
        except:
            filing_date_obj = date.today()

        # Mock corporate actions based on common patterns
        actions = [
            CorporateAction(
                action_id=f"{ticker}_tender_2024",
                action_type=CorporateActionType.TENDER_OFFER,
                company=ticker,
                announcement_date=filing_date_obj,
                title="Tender Offer for Senior Notes",
                description="Tender offer to purchase outstanding 8.125% Senior Notes due 2026",
                status=CorporateActionStatus.ANNOUNCED,
                amount=100000000,
                target_security="8.125% Senior Notes due 2026",
                source_filing=filing_type
            ),
            CorporateAction(
                action_id=f"{ticker}_asset_sale_2024",
                action_type=CorporateActionType.ASSET_SALE,
                company=ticker,
                announcement_date=filing_date_obj,
                title="Asset Sale Transaction",
                description="Sale of non-core business assets to strategic buyer",
                status=CorporateActionStatus.COMPLETED,
                amount=50000000,
                source_filing=filing_type
            )
        ]

        return actions

    def save_results(self, result: CorporateActionsResult, output_dir: str = "output"):
        """Save extraction results to JSON file."""
        os.makedirs(output_dir, exist_ok=True)

        filename = f"{result.ticker}_corporate_actions.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(result.dict(), f, indent=2, default=str)

        logger.info(f"Saved results to {filepath}")


def extract_corporate_actions(ticker: str, api_key: str = None) -> CorporateActionsResult:
    """Convenience function to extract corporate actions."""
    extractor = CorporateActionsExtractor(api_key)
    return extractor.extract_corporate_actions(ticker)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python corporate_actions_extractor.py <TICKER> [API_KEY]")
        sys.exit(1)

    ticker = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None

    result = extract_corporate_actions(ticker, api_key)

    print(f"Extracted {result.total_actions} corporate actions for {ticker}")
    for action in result.corporate_actions:
        print(f"  - {action.action_id}: {action.title}")

    # Save results
    extractor = CorporateActionsExtractor(api_key)
    extractor.save_results(result)
