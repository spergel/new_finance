#!/usr/bin/env python3
"""
Securities Features Extractor

Extracts detailed features of bonds and preferred shares from 424B and S-1 filings.
Focuses on conversion terms, redemption terms, and special features like change-of-control.
"""

import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, date
from core.sec_api_client import SECAPIClient
from core.models import (
    SecurityFeatures, SecuritiesFeaturesResult, SecurityType, 
    ConversionTerms, RedemptionTerms, SpecialFeatures,
    RateResetTerms, DepositarySharesInfo, SpecialRedemptionEvents
)

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


class SecuritiesFeaturesExtractor:
    """Main class for extracting securities features from SEC filings."""

    def __init__(self, google_api_key: str = None):
        self.sec_client = SECAPIClient()
        self.google_api_key = google_api_key or os.getenv('GOOGLE_API_KEY')

        if self.google_api_key:
            genai.configure(api_key=self.google_api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        else:
            logger.warning("No Google API key provided - running in demo mode")
            self.model = None

    def extract_securities_features(self, ticker: str) -> SecuritiesFeaturesResult:
        """Extract securities features for a given ticker."""

        logger.info(f"Extracting securities features for {ticker}")

        # Get filings for the ticker
        filings = self._get_relevant_filings(ticker)

        if not filings:
            logger.warning(f"No relevant filings found for {ticker}")
            return SecuritiesFeaturesResult(ticker=ticker, extraction_date=date.today())

        securities = []

        for filing in filings:
            filing_content = self._get_filing_content(filing)
            if filing_content:
                extracted_securities = self._extract_from_filing(filing_content, filing, ticker)
                securities.extend(extracted_securities)

        # Deduplicate securities - keep only the most recent filing for each unique security_id
        unique_securities = {}
        for security in securities:
            security_key = security.security_id
            
            # If we haven't seen this security yet, or this filing is more recent, keep it
            if security_key not in unique_securities:
                unique_securities[security_key] = security
            else:
                # Compare filing dates - keep the more recent one
                existing_date = unique_securities[security_key].filing_date
                new_date = security.filing_date
                
                if new_date and existing_date:
                    if new_date > existing_date:
                        logger.info(f"Deduplicating {security_key}: keeping {new_date} over {existing_date}")
                        unique_securities[security_key] = security
                    else:
                        logger.info(f"Deduplicating {security_key}: keeping {existing_date} over {new_date}")
        
        deduplicated_securities = list(unique_securities.values())
        
        if len(securities) > len(deduplicated_securities):
            logger.info(f"Deduplicated {len(securities)} securities down to {len(deduplicated_securities)}")

        return SecuritiesFeaturesResult(
            ticker=ticker,
            extraction_date=date.today(),
            securities=deduplicated_securities,
            total_securities=len(deduplicated_securities)
        )

    def _get_relevant_filings(self, ticker: str) -> List[Dict]:
        """Get 424B filings that match known securities from 10-Q."""
        try:
            # Step 1: Get known securities from XBRL/regex extraction
            from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares
            
            logger.info(f"Getting known securities from 10-Q for {ticker}")
            xbrl_result = extract_xbrl_preferred_shares(ticker)
            known_securities = xbrl_result.get("securities", [])
            
            if not known_securities:
                logger.info(f"No securities found in 10-Q for {ticker}, skipping 424B matching")
                return []
            
            logger.info(f"Found {len(known_securities)} securities in 10-Q: "
                       f"{[sec.get('series_name') for sec in known_securities]}")
            
            # Step 2: Match 424B filings to known securities
            from core.filing_matcher import match_all_filings_to_securities
            
            logger.info(f"Matching 424B filings to securities...")
            matched_filings = match_all_filings_to_securities(
                ticker, 
                known_securities, 
                max_filings=50  # Check up to 50 most recent 424Bs
            )
            
            if not matched_filings:
                logger.info(f"No recent 424B filings matched for {ticker} - "
                           f"likely old issuances (using 10-Q data only, which is sufficient)")
                return []
            
            # Step 3: Convert to expected format
            filings_data = []
            for filing in matched_filings:
                filings_data.append({
                    'ticker': ticker,
                    'formType': filing['form'],
                    'filingDate': filing['date'],
                    'linkToFilingDetails': filing.get('url', ''),
                    'matched_series': filing['matched_series'],
                    'security_type': filing['security_type'],
                    'match_confidence': filing['match_confidence'],
                    'series_mention_count': filing['series_mention_count'],
                    'accession': filing['accession']
                })
            
            logger.info(f"Matched {len(filings_data)} 424B filings to securities")
            return filings_data
            
        except Exception as e:
            logger.error(f"Error getting matched filings for {ticker}: {e}", exc_info=True)
            return []

    def _get_filing_content(self, filing: Dict) -> Optional[str]:
        """Get the content of a filing by accession number."""
        try:
            accession = filing.get('accession')
            filing_type = filing.get('formType', '')
            ticker = filing.get('ticker', '')
            
            if not accession:
                logger.warning(f"No accession number in filing data")
                return None
            
            # Fetch content using the accession number (not the most recent filing)
            content = self.sec_client.get_filing_by_accession(ticker, accession, filing_type)
            
            if content:
                logger.info(f"Fetched {len(content):,} characters from {filing_type} ({accession})")
                return content
            else:
                logger.warning(f"No content returned for {filing_type} ({accession})")
                return None
                
        except Exception as e:
            logger.error(f"Error getting filing content: {e}", exc_info=True)
            return None

    def _extract_from_filing(self, content: str, filing: Dict, ticker: str) -> List[SecurityFeatures]:
        """Extract securities from a single filing using LLM."""

        if not self.model:
            # Demo mode - return mock data
            return self._extract_mock_securities(ticker, filing)

        filing_type = filing.get('formType', 'Unknown')
        filing_date = filing.get('filingDate', '')
        filing_url = filing.get('url', filing.get('linkToFilingDetails', ''))
        filing_accession = filing.get('accession', '')
        match_confidence = filing.get('match_confidence', '')
        series_mention_count = filing.get('series_mention_count', 0)

        # Parse filing date
        try:
            filing_date_obj = datetime.strptime(filing.get('filingDate', ''), '%Y-%m-%d').date()
        except:
            filing_date_obj = date.today()
        
        prompt = f"""
        Analyze this {filing_type} filing for {ticker} and extract information about PREFERRED SHARES and other securities.

        For PREFERRED SHARES, extract these CRITICAL investment features:

        **Core Terms:**
        1. Series name/identifier (e.g., "Series A", "Series B")
        2. Description (full name like "8.125% Non-Cumulative Preferred Stock, Series A")
        3. Par value and liquidation preference
        
        **Dividend Features:**
        4. Dividend rate (fixed or floating)
        5. Dividend calculation method (e.g., "quarterly at 8.125% per annum")
        6. Is cumulative or non-cumulative
        7. Dividend stopper clause (restrictions on common dividends if preferred dividends not paid)
        8. PIK (Payment-in-Kind) toggle option if any
        
        **Conversion Features:**
        9. Is convertible to common stock? If yes:
           - Conversion ratio or price
           - Conversion triggers (mandatory vs optional)
           - Adjustment formulas (anti-dilution provisions)
           - Earliest conversion date
        
        **Redemption/Call Features:**
        10. Is callable by company? If yes:
            - Earliest call date
            - Call price or premium
            - Notice period required
            - Optional vs mandatory redemption
        11. Holder put rights (can holders force redemption?)
        
        **Governance Rights:**
        12. Voting rights (conditions under which preferred holders can vote)
        13. Board appointment rights (can elect directors?)
        14. Protective provisions (veto rights over major decisions like M&A, new senior debt, etc.)
        
        **Special Provisions:**
        15. Change of control provisions (what happens on acquisition)
        16. Rate reset terms (for floating rate preferreds)
        17. Ranking/priority (senior vs junior vs pari passu with other securities)
        18. Tax treatment notes (qualified dividend status, etc.)
        19. Mandatory conversion triggers (e.g., IPO, change of control)
        20. Sinking fund provisions
        
        Return ONLY valid JSON (no markdown, no explanations) as a list of securities:
        [
          {{
            "security_id": "JXN Series A Preferred",
            "security_type": "preferred_stock",
            "description": "Fixed-Rate Reset Noncumulative Perpetual Preferred Stock, Series A",
            "par_value": 1.0,
            "liquidation_preference": 25000.0,
            "dividend_rate": 8.0,
            "dividend_type": "fixed-to-floating",
            "is_cumulative": false,
            "payment_frequency": "quarterly",
            "is_perpetual": true,
            "voting_rights": "Can elect 2 directors if dividends not paid for 6 quarters",
            "can_elect_directors": true,
            "director_election_trigger": "6 quarterly dividend periods unpaid",
            "protective_provisions": ["Amendment requires 2/3 vote", "Senior stock issuance requires 2/3 vote"],
            "conversion_terms": {{
              "conversion_price": null,
              "conversion_ratio": null,
              "is_conditional": false,
              "conversion_triggers": [],
              "earliest_conversion_date": null
            }},
            "redemption_terms": {{
              "is_callable": true,
              "call_price": 25000.0,
              "earliest_call_date": "2028-03-30",
              "notice_period_days": 30,
              "has_make_whole": false
            }},
            "special_redemption_events": {{
              "has_rating_agency_event": true,
              "rating_agency_event_price": 25500.0,
              "rating_agency_event_window": "90 days after occurrence",
              "has_regulatory_capital_event": true,
              "regulatory_capital_event_price": 25000.0,
              "regulatory_capital_event_window": "90 days after occurrence",
              "has_tax_event": false,
              "tax_event_details": null
            }},
            "partial_redemption_allowed": true,
            "rate_reset_terms": {{
              "has_rate_reset": true,
              "reset_frequency": "5 years",
              "reset_dates": ["2028-03-30"],
              "initial_fixed_period_end": "2028-03-30",
              "reset_spread": 3.728,
              "reset_benchmark": "Five-year U.S. Treasury Rate",
              "reset_floor": null,
              "reset_cap": null
            }},
            "depositary_shares_info": {{
              "is_depositary_shares": true,
              "depositary_ratio": "1/1,000th interest",
              "depositary_shares_issued": 22000000,
              "underlying_preferred_shares": 22000,
              "depositary_symbol": "JXN PR A",
              "depositary_institution": "Equiniti Trust Company",
              "price_per_depositary_share": 25.0
            }},
            "ranking": "senior to common stock and junior stock, pari passu with other preferred series",
            "special_features": {{
              "has_change_of_control": false,
              "change_of_control_protection": null,
              "has_anti_dilution": false,
              "has_vwap_pricing": false
            }}
          }}
        ]

        Filing content (first 12000 characters):
        {content[:12000]}

        Return ONLY the JSON array, no other text.
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

            securities = []
            seen_securities = set()  # Track unique securities to avoid duplicates

            for item in data:
                try:
                    security = self._parse_security_data(
                        item, ticker, filing_date_obj, filing_type, filing_url, 
                        filing_accession, match_confidence, series_mention_count
                    )
                    if security:
                        # Create a unique key for this security to detect duplicates
                        security_key = self._get_security_key(security)
                        if security_key not in seen_securities:
                            seen_securities.add(security_key)
                            securities.append(security)
                        else:
                            logger.info(f"Skipping duplicate security: {security.security_id}")
                except Exception as e:
                    logger.warning(f"Error parsing security data: {e}")

            return securities
            
        except Exception as e:
            logger.error(f"Error extracting from filing: {e}")
            return self._extract_mock_securities(ticker, filing)

    def _parse_security_data(
        self, data: Dict, ticker: str, filing_date: date, filing_type: str, 
        filing_url: str = "", filing_accession: str = "", match_confidence: str = "", 
        series_mention_count: int = 0
    ) -> Optional[SecurityFeatures]:
        """Parse extracted data into SecurityFeatures model."""
        try:
            security_id = data.get('security_id', f"{ticker}_{len(data)}")
            security_type = self._parse_security_type(data.get('security_type', ''))

            # Build conversion terms
            conversion_terms = None
            if data.get('conversion_terms'):
                conv_data = data['conversion_terms']
                try:
                    conversion_terms = ConversionTerms(
                        conversion_price=self._safe_float(conv_data.get('conversion_price')),
                        conversion_ratio=self._safe_float(conv_data.get('conversion_ratio')),
                        is_conditional=conv_data.get('is_conditional', False),
                        conversion_triggers=conv_data.get('conversion_triggers', []),
                        earliest_conversion_date=conv_data.get('earliest_conversion_date')
                    )
                except Exception as e:
                    logger.warning(f"Error creating conversion terms: {e}")

            # Build redemption terms
            redemption_terms = None
            if data.get('redemption_terms'):
                red_data = data['redemption_terms']
                try:
                    redemption_terms = RedemptionTerms(
                        is_callable=red_data.get('is_callable', False),
                        call_price=self._safe_float(red_data.get('call_price')),
                        earliest_call_date=red_data.get('earliest_call_date'),
                        notice_period_days=self._safe_int(red_data.get('notice_period_days')),
                        has_make_whole=red_data.get('has_make_whole', False),
                        has_sinking_fund=red_data.get('has_sinking_fund', False),
                        sinking_fund_schedule=red_data.get('sinking_fund_schedule'),
                        sinking_fund_amount_per_year=self._safe_float(red_data.get('sinking_fund_amount_per_year'))
                    )
                except Exception as e:
                    logger.warning(f"Error creating redemption terms: {e}")

            # Build special redemption events
            special_redemption_events = None
            if data.get('special_redemption_events'):
                sre_data = data['special_redemption_events']
                try:
                    special_redemption_events = SpecialRedemptionEvents(
                        has_rating_agency_event=sre_data.get('has_rating_agency_event', False),
                        rating_agency_event_price=self._safe_float(sre_data.get('rating_agency_event_price')),
                        rating_agency_event_window=sre_data.get('rating_agency_event_window'),
                        has_regulatory_capital_event=sre_data.get('has_regulatory_capital_event', False),
                        regulatory_capital_event_price=self._safe_float(sre_data.get('regulatory_capital_event_price')),
                        regulatory_capital_event_window=sre_data.get('regulatory_capital_event_window'),
                        has_tax_event=sre_data.get('has_tax_event', False),
                        tax_event_details=sre_data.get('tax_event_details')
                    )
                except Exception as e:
                    logger.warning(f"Error creating special redemption events: {e}")

            # Build rate reset terms
            rate_reset_terms = None
            if data.get('rate_reset_terms'):
                rrt_data = data['rate_reset_terms']
                try:
                    rate_reset_terms = RateResetTerms(
                        has_rate_reset=rrt_data.get('has_rate_reset', False),
                        reset_frequency=rrt_data.get('reset_frequency'),
                        reset_dates=rrt_data.get('reset_dates', []),
                        initial_fixed_period_end=rrt_data.get('initial_fixed_period_end'),
                        reset_spread=self._safe_float(rrt_data.get('reset_spread')),
                        reset_benchmark=rrt_data.get('reset_benchmark'),
                        reset_floor=self._safe_float(rrt_data.get('reset_floor')),
                        reset_cap=self._safe_float(rrt_data.get('reset_cap'))
                    )
                except Exception as e:
                    logger.warning(f"Error creating rate reset terms: {e}")

            # Build depositary shares info
            depositary_shares_info = None
            if data.get('depositary_shares_info'):
                dsi_data = data['depositary_shares_info']
                try:
                    depositary_shares_info = DepositarySharesInfo(
                        is_depositary_shares=dsi_data.get('is_depositary_shares', False),
                        depositary_ratio=dsi_data.get('depositary_ratio'),
                        depositary_shares_issued=self._safe_int(dsi_data.get('depositary_shares_issued')),
                        underlying_preferred_shares=self._safe_int(dsi_data.get('underlying_preferred_shares')),
                        depositary_symbol=dsi_data.get('depositary_symbol'),
                        depositary_institution=dsi_data.get('depositary_institution'),
                        price_per_depositary_share=self._safe_float(dsi_data.get('price_per_depositary_share'))
                    )
                except Exception as e:
                    logger.warning(f"Error creating depositary shares info: {e}")

            # Build special features
            special_features = None
            if data.get('special_features'):
                spec_data = data['special_features']
                special_features = SpecialFeatures(
                    has_change_of_control=spec_data.get('has_change_of_control', False),
                    change_of_control_protection=spec_data.get('change_of_control_protection'),
                    change_of_control_put_right=spec_data.get('change_of_control_put_right', False),
                    change_of_control_put_price=self._safe_float(spec_data.get('change_of_control_put_price')),
                    change_of_control_definition=spec_data.get('change_of_control_definition'),
                    has_anti_dilution=spec_data.get('has_anti_dilution', False),
                    has_vwap_pricing=spec_data.get('has_vwap_pricing', False)
                )

            return SecurityFeatures(
                security_id=security_id,
                security_type=security_type,
                company=ticker,
                filing_date=filing_date,
                description=data.get('description'),
                principal_amount=self._safe_float(data.get('principal_amount')),
                interest_rate=self._safe_float(data.get('interest_rate')),
                maturity_date=data.get('maturity_date'),
                par_value=self._safe_float(data.get('par_value')),
                # Preferred stock specific fields
                liquidation_preference=self._safe_float(data.get('liquidation_preference')),
                dividend_rate=self._safe_float(data.get('dividend_rate')),
                dividend_type=data.get('dividend_type'),
                is_cumulative=data.get('is_cumulative'),
                payment_frequency=data.get('payment_frequency'),
                dividend_payment_dates=data.get('dividend_payment_dates', []),
                dividend_stopper_clause=data.get('dividend_stopper_clause'),
                is_perpetual=data.get('is_perpetual'),
                # Voting and governance
                voting_rights_description=data.get('voting_rights'),
                can_elect_directors=data.get('can_elect_directors'),
                director_election_trigger=data.get('director_election_trigger'),
                protective_provisions=data.get('protective_provisions', []),
                # Terms
                conversion_terms=conversion_terms,
                redemption_terms=redemption_terms,
                special_redemption_events=special_redemption_events,
                partial_redemption_allowed=data.get('partial_redemption_allowed'),
                rate_reset_terms=rate_reset_terms,
                depositary_shares_info=depositary_shares_info,
                special_features=special_features,
                ranking_description=data.get('ranking'),
                # Exchange listing
                exchange_listed=data.get('exchange_listed'),
                trading_symbol=data.get('trading_symbol'),
                source_filing=filing_type,
                filing_url=filing_url,
                extraction_confidence=0.8,  # Default confidence
                # Filing match metadata
                matched_filing_accession=filing_accession,
                match_confidence=match_confidence,
                series_mention_count=series_mention_count
            )
            
        except Exception as e:
            logger.error(f"Error parsing security data: {e}")
            return None
    
    def _parse_security_type(self, type_str: str) -> SecurityType:
        """Parse string to SecurityType enum."""
        type_map = {
            'preferred_stock': SecurityType.PREFERRED_STOCK,
            'preferred stock': SecurityType.PREFERRED_STOCK,
            'senior_note': SecurityType.SENIOR_NOTE,
            'senior note': SecurityType.SENIOR_NOTE,
            'convertible_note': SecurityType.CONVERTIBLE_NOTE,
            'convertible note': SecurityType.CONVERTIBLE_NOTE,
            'corporate_bond': SecurityType.CORPORATE_BOND,
            'corporate bond': SecurityType.CORPORATE_BOND,
            'debt_instrument': SecurityType.DEBT_INSTRUMENT,
            'debt instrument': SecurityType.DEBT_INSTRUMENT,
        }

        return type_map.get(type_str.lower(), SecurityType.DEBT_INSTRUMENT)

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float, return None if invalid."""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                # Remove common suffixes and convert
                value = value.replace('$', '').replace(',', '').replace('%', '')
                if value.endswith('M'):
                    value = float(value[:-1]) * 1000000
                elif value.endswith('B'):
                    value = float(value[:-1]) * 1000000000
                else:
                    return float(value)
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value) -> Optional[int]:
        """Safely convert value to int, return None if invalid."""
        if value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _get_security_key(self, security: SecurityFeatures) -> str:
        """Generate a unique key for a security to detect duplicates."""
        # Use combination of company, description, and filing date as unique identifier
        # This should be unique for each distinct security
        key_parts = [
            security.company,
            security.description or "No description",
            security.filing_date.isoformat(),
            str(security.principal_amount or 0),
            str(security.par_value or 0),
            security.security_type.value
        ]
        return "|".join(key_parts)

    def _extract_mock_securities(self, ticker: str, filing: Dict) -> List[SecurityFeatures]:
        """Return mock securities for demo purposes."""
        filing_type = filing.get('formType', 'Unknown')
        filing_date = filing.get('filingDate', '')

        try:
            filing_date_obj = datetime.strptime(filing_date, '%Y-%m-%d').date()
        except:
            filing_date_obj = date.today()

        # Mock securities based on common patterns
        securities = [
            SecurityFeatures(
                security_id=f"{ticker}_8.125_notes",
                security_type=SecurityType.SENIOR_NOTE,
                company=ticker,
                filing_date=filing_date_obj,
                description="8.125% Senior Notes due 2026",
                principal_amount=150000000.0,
                interest_rate=0.08125,
                maturity_date=date(2026, 2, 28),
                source_filing=filing_type,
                special_features=SpecialFeatures(
                    has_change_of_control=True,
                    change_of_control_protection="Standard change of control put option"
                )
            ),
            SecurityFeatures(
                security_id=f"{ticker}_7.75_pref",
                security_type=SecurityType.PREFERRED_STOCK,
                company=ticker,
                filing_date=filing_date_obj,
                description="7.75% Preferred Stock",
                par_value=25.0,
                source_filing=filing_type,
                conversion_terms=ConversionTerms(
                    conversion_price=15.0,
                    conversion_ratio=1.0,
                    is_conditional=True,
                    conversion_triggers=["change_of_control"]
                ),
                redemption_terms=RedemptionTerms(
                    is_callable=True,
                    call_price=25.0,
                    earliest_call_date=date(2025, 1, 1)
                )
            )
        ]

        # Apply deduplication to mock data as well
        seen_securities = set()
        unique_securities = []

        for security in securities:
            security_key = self._get_security_key(security)
            if security_key not in seen_securities:
                seen_securities.add(security_key)
                unique_securities.append(security)

        return unique_securities

    def save_results(self, result: SecuritiesFeaturesResult, output_dir: str = "output/llm"):
        """Save extraction results to JSON file."""
        os.makedirs(output_dir, exist_ok=True)

        filename = f"{result.ticker}_securities_features.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(result.dict(), f, indent=2, default=str)

        logger.info(f"Saved results to {filepath}")


def extract_securities_features(ticker: str, api_key: str = None) -> SecuritiesFeaturesResult:
    """Convenience function to extract securities features."""
    extractor = SecuritiesFeaturesExtractor(api_key)
    return extractor.extract_securities_features(ticker)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python securities_features_extractor.py <TICKER> [API_KEY]")
        sys.exit(1)

    ticker = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None

    result = extract_securities_features(ticker, api_key)

    print(f"Extracted {result.total_securities} securities for {ticker}")
    for security in result.securities:
        print(f"  - {security.security_id}: {security.security_type}")

    # Save results
    extractor = SecuritiesFeaturesExtractor(api_key)
    extractor.save_results(result)
