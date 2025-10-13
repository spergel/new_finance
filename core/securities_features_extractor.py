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
    ConversionTerms, RedemptionTerms, SpecialFeatures, Covenants,
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

    def extract_securities_features(self, ticker: str, matched_filings: List[Dict] = None) -> SecuritiesFeaturesResult:
        """Extract securities features for a given ticker from pre-matched filings."""

        logger.info(f"Extracting securities features for {ticker}")

        if not matched_filings:
            # Fallback to old method if no pre-matched filings provided
            matched_filings = self._get_relevant_filings(ticker)

        if not matched_filings:
            logger.warning(f"No relevant filings found for {ticker}")
            return SecuritiesFeaturesResult(ticker=ticker, extraction_date=date.today())

        securities = []

        for filing in matched_filings:
            # Filing should already have content from matcher
            filing_content = filing.get('content')
            if filing_content:
                extracted_securities = self._extract_from_filing(filing_content, filing, ticker)
                securities.extend(extracted_securities)

        # Deduplicate securities - keep the most complete/recent filing for each unique security_id
        unique_securities = {}
        for security in securities:
            security_key = security.security_id

            if security_key not in unique_securities:
                unique_securities[security_key] = security
            else:
                # Compare securities - prefer one with more complete financial data
                existing = unique_securities[security_key]
                new = security

                # Score completeness: prefer securities with more financial data
                def score_security(sec):
                    score = 0
                    if sec.dividend_rate: score += 1
                    if sec.par_value: score += 1
                    if sec.liquidation_preference: score += 1
                    if sec.principal_amount: score += 1
                    # Prefer more recent filing date as tiebreaker
                    score += sec.filing_date.day / 31 if sec.filing_date else 0
                    return score

                existing_score = score_security(existing)
                new_score = score_security(new)

                if new_score > existing_score:
                    logger.info(f"Deduplicating {security_key}: keeping more complete data from {new.filing_date} (score: {new_score}) over {existing.filing_date} (score: {existing_score})")
                    unique_securities[security_key] = security
                else:
                    logger.info(f"Deduplicating {security_key}: keeping existing from {existing.filing_date} (score: {existing_score}) over {new.filing_date} (score: {new_score})")
        
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

    def _extract_dividend_rates_from_text(self, content: str) -> Dict[str, float]:
        """Extract dividend rates from 424B text using comprehensive regex patterns."""
        import re

        rates = {}

        # Pattern 1: "X.XXX% Series Y" in titles/headers (most common)
        pattern1 = r'(\d+\.?\d*)\s*%\s+Series\s+([A-Z])\b'
        matches = re.findall(pattern1, content[:15000], re.IGNORECASE | re.MULTILINE)
        for rate, series in matches:
            rates[f"Series {series}"] = float(rate)

        # Pattern 2: "Series Y ... X.XXX%" (reverse order)
        pattern2 = r'Series\s+([A-Z])\s+[^(]*?(\d+\.?\d*)\s*%\s'
        matches = re.findall(pattern2, content[:15000], re.IGNORECASE | re.MULTILINE)
        for series, rate in matches:
            rates[f"Series {series}"] = float(rate)

        # Pattern 3: Look in prospectus supplement titles
        pattern3 = r'(\d+\.?\d*)\s*%\s+[^%]*?Preferred\s+Stock.*?Series\s+([A-Z])\b'
        matches = re.findall(pattern3, content[:8000], re.IGNORECASE | re.MULTILINE)
        for rate, series in matches:
            rates[f"Series {series}"] = float(rate)

        # Pattern 4: "Series Y X.XXX%" (Series first, then rate)
        pattern4 = r'Series\s+([A-Z])\s+(\d+\.?\d*)\s*%'
        matches = re.findall(pattern4, content[:15000], re.IGNORECASE | re.MULTILINE)
        for series, rate in matches:
            rates[f"Series {series}"] = float(rate)

        # Pattern 5: In offering descriptions (broader search)
        pattern5 = r'(\d+\.?\d*)\s*%\s+.*?Series\s+([A-Z])\b.*?Preferred\s+Stock'
        matches = re.findall(pattern5, content[:8000], re.IGNORECASE | re.MULTILINE)
        for rate, series in matches:
            rates[f"Series {series}"] = float(rate)

        # Pattern 6: "X.XXX% Cumulative Preferred Stock, Series Y"
        pattern6 = r'(\d+\.?\d*)\s*%\s+.*?Series\s+([A-Z])\b'
        matches = re.findall(pattern6, content[:10000], re.IGNORECASE | re.MULTILINE)
        for rate, series in matches:
            rates[f"Series {series}"] = float(rate)

        # Pattern 7: Look for floating rate patterns like "LIBOR + X.XXX%"
        pattern7 = r'(\w+\s*\+\s*|\w+\s*plus\s*)(\d+\.?\d*)\s*%\s+.*?Series\s+([A-Z])\b'
        matches = re.findall(pattern7, content[:10000], re.IGNORECASE | re.MULTILINE)
        for base, spread, series in matches:
            try:
                rates[f"Series {series}"] = float(spread)
            except ValueError:
                pass

        logger.info(f"Extracted dividend rates from text: {rates}")
        return rates

    def _extract_key_terms_from_text(self, content: str) -> Dict[str, Dict]:
        """Extract key terms from 424B text using comprehensive regex patterns."""
        import re

        extracted = {}

        # First, identify all series mentioned in the filing
        series_patterns = [
            r'Series\s+([A-Z])\b',
            r'Series\s+([A-Z])\s+Preferred\s+Stock',
        ]

        all_series = set()
        for pattern in series_patterns:
            matches = re.findall(pattern, content[:20000], re.IGNORECASE)
            all_series.update(matches)

        # Initialize entries for all found series
        for series in all_series:
            if series not in extracted:
                extracted[series] = {}

        # Extract dividend rates from titles with enhanced patterns
        div_patterns = [
            r'(\d+\.?\d*)\s*%\s+Series\s+([A-Z])',  # "7.375% Series B"
            r'Series\s+([A-Z])\s+[^(]*?(\d+\.?\d*)\s*%',  # "Series B ... 7.375%"
            r'Series\s+([A-Z])\s+(\d+\.?\d*)\s*%',  # "Series B 7.375%"
            r'(\d+\.?\d*)\s*%\s+.*?Series\s+([A-Z])\b.*?Preferred\s+Stock',  # "7.375% ... Series B Preferred Stock"
            r'(\d+\.?\d*)\s*%\s+.*?Series\s+([A-Z])\b',  # "7.375% ... Series B"
        ]

        for pattern in div_patterns:
            matches = re.findall(pattern, content[:20000], re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if len(match) == 2:
                    rate, series = match
                    series = series.upper()
                    if series not in extracted:
                        extracted[series] = {}
                    try:
                        extracted[series]['dividend_rate'] = float(rate)
                    except ValueError:
                        pass

        # Extract liquidation preference - more specific for preferred stocks
        liq_patterns = [
            r'liquidation.*?preference.*?\$?([\d,]+\.?\d*).*?per.*?share',
            r'\$?([\d,]+\.?\d*).*?liquidation.*?preference.*?per.*?share',
            r'per.*?share.*?liquidation.*?preference.*?\$?([\d,]+\.?\d*)',
        ]

        for pattern in liq_patterns:
            matches = re.findall(pattern, content[:15000], re.IGNORECASE | re.MULTILINE)
            for match in matches:
                try:
                    value = float(match.replace(',', ''))
                    # Only reasonable values for preferred stock liquidation preference
                    if 1 <= value <= 100:  # Typical range for preferred stock
                        for series in extracted:
                            if 'liquidation_preference' not in extracted[series]:
                                extracted[series]['liquidation_preference'] = value
                                break
                except ValueError:
                    continue

        # Extract par value - more specific patterns
        par_patterns = [
            r'par\s+value.*?\$?([\d,]+\.?\d*).*?per.*?share',
            r'\$?([\d,]+\.?\d*).*?par.*?value.*?per.*?share',
            r'par.*?value.*?of.*?\$?([\d,]+\.?\d*).*?per.*?share',
        ]

        for pattern in par_patterns:
            matches = re.findall(pattern, content[:15000], re.IGNORECASE | re.MULTILINE)
            for match in matches:
                try:
                    value = float(match.replace(',', ''))
                    # Only reasonable values for preferred stock par value
                    if 0.001 <= value <= 5.0:  # Typical range for preferred stock par values
                        for series in extracted:
                            if 'par_value' not in extracted[series]:
                                extracted[series]['par_value'] = value
                                break
                except ValueError:
                    continue

        # Extract offering size - more specific for preferred stocks
        size_patterns = [
            r'offering.*?([\d,]+).*?depositary.*?shares',
            r'([\d,]+).*?depositary.*?shares.*?offered',
            r'aggregate.*?offering.*?([\d,]+).*?shares',
        ]

        for pattern in size_patterns:
            matches = re.findall(pattern, content[:15000], re.IGNORECASE | re.MULTILINE)
            for match in matches:
                try:
                    value = int(match.replace(',', ''))
                    # Only reasonable values for preferred stock offerings (in thousands)
                    if 10000 <= value <= 50000000:  # Reasonable range for depositary shares
                        for series in extracted:
                            if 'offering_size' not in extracted[series]:
                                extracted[series]['offering_size'] = value
                                break
                except ValueError:
                    continue

        # Extract offering price - more specific for preferred stocks
        price_patterns = [
            r'public.*?offering.*?price.*?\$?([\d,]+\.?\d*).*?per.*?share',
            r'offering.*?price.*?\$?([\d,]+\.?\d*).*?per.*?depositary.*?share',
            r'price.*?to.*?public.*?\$?([\d,]+\.?\d*).*?per.*?share',
        ]

        for pattern in price_patterns:
            matches = re.findall(pattern, content[:15000], re.IGNORECASE | re.MULTILINE)
            for match in matches:
                try:
                    value = float(match.replace(',', ''))
                    # Only reasonable values for preferred stock offering prices
                    if 10 <= value <= 50:  # Typical range for preferred stock offering prices
                        for series in extracted:
                            if 'offering_price' not in extracted[series]:
                                extracted[series]['offering_price'] = value
                                break
                except ValueError:
                    continue

        # Extract tax treatment notes - more specific patterns for preferred stocks
        tax_patterns = [
            r'(?:qualifies|qualified|is).*?(?:as|for).*?Tier\s+\d+.*?capital',
            r'Tier\s+\d+.*?capital.*?(?:treatment|qualifies|is)',
            r'(?:qualified|qualifying).*?dividend.*?(?:income|treatment)',
            r'dividend.*?received.*?deduction.*?(\d+).*?%',
            r'regulatory.*?capital.*?(?:treatment|qualifies)',
            r'additional.*?Tier\s+\d+.*?capital',
            r'(?:qualifies|qualified).*?additional.*?Tier\s+\d+',
            r'capital.*?treatment.*?Tier\s+\d+',
            r'(?:qualifies|qualified).*?Tier\s+\d+.*?regulatory.*?capital',
        ]

        tax_notes = []
        for pattern in tax_patterns:
            matches = re.findall(pattern, content[:20000], re.IGNORECASE | re.MULTILINE)
            if matches:
                # Clean up matches - remove empty strings and duplicates
                clean_matches = [m.strip() for m in matches if m.strip()]
                tax_notes.extend(clean_matches)

        if tax_notes:
            # Join unique tax treatment phrases, limit to reasonable length
            unique_tax_notes = list(set(tax_notes))
            tax_note = ". ".join(unique_tax_notes[:3]).strip()  # Limit to top 3 matches
            if tax_note:
                for series in extracted:
                    if 'tax_treatment_notes' not in extracted[series]:
                        extracted[series]['tax_treatment_notes'] = tax_note

        # Extract dividend restriction information - more specific patterns
        restriction_patterns = [
            r'(?:non.?cumulative|cumulative).*?preferred.*?stock',
            r'dividends?.*?(?:not.*?mandatory|are.*?not.*?mandatory)',
            r'no.*?obligation.*?to.*?pay.*?preferred.*?dividends?',
            r'(?:discretionary|may.*?declare).*?preferred.*?dividends?',
            r'preferred.*?stock.*?dividends?.*?(?:not.*?mandatory|may.*?declare)',
        ]

        restrictions = []
        for pattern in restriction_patterns:
            matches = re.findall(pattern, content[:15000], re.IGNORECASE | re.MULTILINE)
            if matches:
                # Clean up matches - remove empty strings
                clean_matches = [m.strip() for m in matches if m.strip()]
                restrictions.extend(clean_matches)

        if restrictions:
            # Join unique restrictions, limit to reasonable length
            unique_restrictions = list(set(restrictions))
            restriction_note = ". ".join(unique_restrictions[:2]).strip()  # Limit to top 2 matches
            if restriction_note:
                for series in extracted:
                    if 'dividend_restrictions' not in extracted[series]:
                        extracted[series]['dividend_restrictions'] = restriction_note

        # Extract offering date
        date_patterns = [
            r'filing.*?date.*?(\d{4}-\d{2}-\d{2})',
            r'dated.*?(\d{4}-\d{2}-\d{2})',
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, content[:5000], re.IGNORECASE | re.MULTILINE)
            for match in matches:
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(match, '%Y-%m-%d').date()
                    for series in extracted:
                        if 'offering_date' not in extracted[series]:
                            extracted[series]['offering_date'] = date_obj.isoformat()
                            break
                except ValueError:
                    continue

        logger.info(f"Extracted key terms from text: {extracted}")
        return extracted

    def _extract_from_filing(self, content: str, filing: Dict, ticker: str) -> List[SecurityFeatures]:
        """Extract securities from a single filing using LLM."""

        # First, extract dividend rates using regex (these are often in headers/titles)
        extracted_rates = self._extract_dividend_rates_from_text(content)

        # Also extract other key terms
        extracted_terms = self._extract_key_terms_from_text(content)

        if not self.model:
            # Demo mode - return mock data
            return self._extract_mock_securities(ticker, filing)

        filing_type = filing.get('formType', 'Unknown')
        filing_date = filing.get('filingDate', '')
        filing_url = filing.get('url', filing.get('linkToFilingDetails', ''))
        filing_accession = filing.get('accession', '')
        match_confidence = filing.get('match_confidence', '')
        series_mention_count = filing.get('series_mention_count', 0)

        # Get the target series this filing was matched to
        target_series = filing.get('matched_series', [''])[0]  # e.g., "C" for Series C

        # Parse filing date
        try:
            filing_date_obj = datetime.strptime(filing.get('filingDate', ''), '%Y-%m-%d').date()
        except:
            filing_date_obj = date.today()

        # Include extracted terms in the prompt
        extracted_text = ""
        if extracted_rates or extracted_terms:
            extracted_text = "\n\nPRE-EXTRACTED INFORMATION (from text analysis):"
            for series, terms in extracted_terms.items():
                extracted_text += f"\n- Series {series}:"
                if 'dividend_rate' in terms:
                    extracted_text += f" dividend_rate: {terms['dividend_rate']}%"
                if 'par_value' in terms:
                    extracted_text += f" par_value: ${terms['par_value']}"
                if 'liquidation_preference' in terms:
                    extracted_text += f" liquidation_preference: ${terms['liquidation_preference']}"
                if 'offering_size' in terms:
                    extracted_text += f" offering_size: {terms['offering_size']:,}"
                if 'offering_price' in terms:
                    extracted_text += f" offering_price: ${terms['offering_price']}"
                if 'tax_treatment_notes' in terms:
                    extracted_text += f" tax_treatment_notes: {terms['tax_treatment_notes'][:200]}..."  # Truncate long text
                if 'dividend_restrictions' in terms:
                    extracted_text += f" dividend_restrictions: {terms['dividend_restrictions']}"

        prompt = f"""
        Analyze this {filing_type} filing for {ticker} and extract information about PREFERRED SHARES and other securities.{extracted_text}

        **TARGET SERIES FOCUS:** This filing was specifically matched to Series {target_series}. Extract information PRIMARILY for Series {target_series} preferred stock. If other series are mentioned, only extract them if they are the main subject of this filing.

        **IMPORTANT INSTRUCTIONS:**
        - Extract ALL information from the filing content provided below
        - USE THE PRE-EXTRACTED INFORMATION section above - it contains reliable data found via text analysis
        - If the pre-extracted information has values for fields, use those as the primary source
        - Fill in any missing fields by searching the filing text carefully
        - For preferred stocks, pay special attention to tax treatment and dividend restrictions

        **CRITICAL EXTRACTION TARGETS FOR PREFERRED STOCK:**
        1. **Dividend Rates**: Use pre-extracted if available, otherwise look for "8.25% Series D", "Series B 7.375%" patterns
        2. **Original Offering Info**: Use pre-extracted size/price/date if available, verify from filing
        3. **Tax Treatment**: Use pre-extracted if available, otherwise search for "Tier 1 capital", "qualified dividend", "regulatory capital"
        4. **Dividend Restrictions**: Use pre-extracted if available, search for "non-cumulative", "dividends not mandatory", "no obligation to pay"
        5. **Regulatory Capital**: Critical for bank preferreds - search for "qualifies as Tier 1 capital", "additional Tier 1 capital"
        6. **Covenants**: Extract dividend restrictions, events of default, change of control provisions

        **For PREFERRED SHARES, extract these CRITICAL investment features:**

        **Core Terms:**
        1. Series name/identifier (e.g., "Series A", "Series B")
        2. Description (full name like "8.125% Non-Cumulative Preferred Stock, Series A")
        3. Par value (stated as "$X.XX per share" or "par value $X.XX")
        4. Liquidation preference (stated as "$X.XX per share" or "liquidation preference $X.XX")

        **Dividend Features:**
        5. Dividend rate (fixed or floating) - CRITICAL - extract from title/headers like "7.375% Series B"
        6. Dividend calculation method (e.g., "360-day year", "actual/360", "quarterly at 8.125% per annum")
        7. Is cumulative or non-cumulative - SEARCH for "non-cumulative", "cumulative", "dividends not mandatory"
        8. Dividend stopper clause (restrictions on common dividends if preferred dividends not paid)
        9. Dividend payment obligations - "may declare dividends", "no obligation to pay", "discretionary dividends"

        **Offering Information:**
        10. Original offering details: size of offering, offering date, offering price - SEARCH CAREFULLY
        11. Is this a new issuance or refinancing of existing debt?

        **Conversion Features:**
        12. Is convertible to common stock? If yes:
           - Conversion ratio or price
           - Conversion triggers (mandatory vs optional) - INCLUDE RELEVANT PARAGRAPH TEXT
           - Adjustment formulas (anti-dilution provisions)
           - Earliest conversion date

        **Redemption/Call Features:**
        13. Is callable by company? If yes:
            - Earliest call date
            - Call price or premium - INCLUDE RELEVANT PARAGRAPH TEXT
            - Notice period required
            - Optional vs mandatory redemption
        14. Holder put rights (can holders force redemption?)

        **Governance Rights:**
        15. Voting rights (conditions under which preferred holders can vote)
        16. Board appointment rights (can elect directors?)
        17. Protective provisions (veto rights over major decisions like M&A, new senior debt, etc.)

        **Special Provisions:**
        18. Change of control provisions (what happens on acquisition) - INCLUDE RELEVANT PARAGRAPH TEXT
        19. Rate reset terms (for floating rate preferreds)
        20. Ranking/priority (senior vs junior vs pari passu with other securities)
        21. Tax treatment notes (qualified dividend status, dividend received deduction) - SEARCH FOR "Tier", "regulatory", "qualified", "dividend received"
        22. Regulatory capital treatment (Tier 1, additional Tier 1, Tier 2 capital) - CRITICAL for bank preferreds
        23. Mandatory conversion triggers (e.g., IPO, change of control)
        24. Sinking fund provisions

        **Covenants and Restrictions:**
        25. Financial covenants: interest coverage ratios, debt-to-EBITDA limits, minimum EBITDA
        26. Negative covenants: restrictions on dividends, new debt, asset sales, mergers
        27. Affirmative covenants: reporting requirements, maintenance obligations
        28. Events of default: payment defaults, bankruptcy, covenant breaches
        29. Cross-default provisions: default on other debt
        30. Change of control covenants: what triggers on ownership changes

        Return ONLY valid JSON (no markdown, no explanations) as a list of securities:
        [
          {{
            "security_id": "SOHO Series D Preferred",
            "security_type": "preferred_stock",
            "description": "8.25% Series D Cumulative Redeemable Perpetual Preferred Stock",
            "par_value": 0.01,
            "liquidation_preference": 25.00,
            "dividend_rate": 8.25,
            "dividend_type": "fixed-to-floating",
            "dividend_calculation_method": "360-day year",
            "is_cumulative": false,
            "payment_frequency": "quarterly",
            "is_perpetual": true,

            "original_offering_size": 109054,
            "original_offering_date": "2024-06-24",
            "original_offering_price": 16.0,
            "is_new_issuance": true,
            "voting_rights": "Can elect 2 directors if dividends not paid for 6 quarters",
            "can_elect_directors": true,
            "director_election_trigger": "6 quarterly dividend periods unpaid",
            "protective_provisions": ["Amendment requires 2/3 vote", "Senior stock issuance requires 2/3 vote"],
            "conversion_terms": {{
              "conversion_price": null,
              "conversion_ratio": null,
              "is_conditional": false,
              "conversion_triggers": [],
              "earliest_conversion_date": null,
              "conversion_details": null
            }},
            "redemption_terms": {{
              "is_callable": true,
              "call_price": 25000.0,
              "earliest_call_date": "2028-03-30",
              "notice_period_days": 30,
              "has_make_whole": false,
              "redemption_details": null
            }},
            "special_redemption_events": {{
              "has_rating_agency_event": true,
              "rating_agency_event_price": 25500.0,
              "rating_agency_event_window": "90 days after occurrence",
              "rating_agency_event_definition": "any nationally recognized statistical rating organization lowers rating below investment grade",
              "has_regulatory_capital_event": true,
              "regulatory_capital_event_price": 25000.0,
              "regulatory_capital_event_window": "90 days after occurrence",
              "regulatory_capital_event_definition": "Company becomes subject to capital requirements such that preferred stock ceases to qualify as Tier 1 capital",
              "has_tax_event": false,
              "tax_event_details": null,
              "tax_treatment_notes": "Qualifies as Tier 1 capital for regulatory purposes. Qualified dividends eligible for 23.8% tax rate for individuals."
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
              "change_of_control_details": null,
              "has_anti_dilution": false,
              "has_vwap_pricing": false,
              "covenants": {{
                "has_financial_covenants": false,
                "restricted_payments_covenant": "No dividends may be paid on common stock if preferred dividends are in arrears",
                "events_of_default": ["Payment default", "Bankruptcy", "Covenant breach"],
                "cross_default_provision": "Default on other debt obligations",
                "covenant_summary": "Standard preferred stock covenants including dividend restrictions and change of control provisions"
              }}
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
                        filing_accession, match_confidence, series_mention_count, extracted_rates
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
        series_mention_count: int = 0, extracted_rates: Dict[str, float] = None
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
                        earliest_conversion_date=conv_data.get('earliest_conversion_date'),
                        conversion_details=conv_data.get('conversion_details')
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
                        sinking_fund_amount_per_year=self._safe_float(red_data.get('sinking_fund_amount_per_year')),
                        redemption_details=red_data.get('redemption_details')
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
                        rating_agency_event_definition=sre_data.get('rating_agency_event_definition'),
                        has_regulatory_capital_event=sre_data.get('has_regulatory_capital_event', False),
                        regulatory_capital_event_price=self._safe_float(sre_data.get('regulatory_capital_event_price')),
                        regulatory_capital_event_window=sre_data.get('regulatory_capital_event_window'),
                        regulatory_capital_event_definition=sre_data.get('regulatory_capital_event_definition'),
                        has_tax_event=sre_data.get('has_tax_event', False),
                        tax_event_details=sre_data.get('tax_event_details'),
                        tax_treatment_notes=sre_data.get('tax_treatment_notes')
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

            # Build covenants
            covenants = None
            if data.get('special_features', {}).get('covenants'):
                cov_data = data['special_features']['covenants']
                try:
                    covenants = Covenants(
                        has_financial_covenants=cov_data.get('has_financial_covenants', False),
                        minimum_interest_coverage=self._safe_float(cov_data.get('minimum_interest_coverage')),
                        maximum_debt_to_ebitda=self._safe_float(cov_data.get('maximum_debt_to_ebitda')),
                        minimum_ebitda=self._safe_float(cov_data.get('minimum_ebitda')),
                        maximum_debt_to_capital=self._safe_float(cov_data.get('maximum_debt_to_capital')),
                        restricted_payments_covenant=cov_data.get('restricted_payments_covenant'),
                        additional_debt_restrictions=cov_data.get('additional_debt_restrictions'),
                        asset_sale_restrictions=cov_data.get('asset_sale_restrictions'),
                        merger_restrictions=cov_data.get('merger_restrictions'),
                        investment_restrictions=cov_data.get('investment_restrictions'),
                        reporting_requirements=cov_data.get('reporting_requirements'),
                        maintenance_covenants=cov_data.get('maintenance_covenants'),
                        collateral_maintenance=cov_data.get('collateral_maintenance'),
                        cross_default_provision=cov_data.get('cross_default_provision'),
                        events_of_default=cov_data.get('events_of_default', []),
                        change_of_control_covenant=cov_data.get('change_of_control_covenant'),
                        covenant_summary=cov_data.get('covenant_summary')
                    )
                except Exception as e:
                    logger.warning(f"Error creating covenants: {e}")

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
                    change_of_control_details=spec_data.get('change_of_control_details'),
                    has_anti_dilution=spec_data.get('has_anti_dilution', False),
                    has_vwap_pricing=spec_data.get('has_vwap_pricing', False),
                    covenants=covenants
                )

            # Use LLM dividend rate, but fallback to regex-extracted rate if LLM doesn't provide it
            dividend_rate_llm = self._safe_float(data.get('dividend_rate'))
            dividend_rate_final = dividend_rate_llm

            if dividend_rate_llm is None and extracted_rates:
                logger.warning(f"LLM did not extract dividend rate for {data.get('security_id', 'unknown')}, using regex fallback")

                # Try to match by series name from LLM output
                series_name = data.get('series_name')
                if series_name and series_name in extracted_rates:
                    dividend_rate_final = extracted_rates[series_name]
                    logger.info(f"Using regex-extracted dividend rate for {series_name}: {dividend_rate_final}%")

                # Try to extract series from security_id
                elif 'Series' in data.get('security_id', ''):
                    import re
                    match = re.search(r'Series\s+([A-Z])\b', data.get('security_id', ''), re.IGNORECASE)
                    if match:
                        series_key = f"Series {match.group(1).upper()}"
                        if series_key in extracted_rates:
                            dividend_rate_final = extracted_rates[series_key]
                            logger.info(f"Using regex-extracted dividend rate for {series_key}: {dividend_rate_final}%")

                # Try to match by description content
                else:
                    description = data.get('description', '').upper()
                    for series_key, rate in extracted_rates.items():
                        if series_key.upper() in description:
                            dividend_rate_final = rate
                            logger.info(f"Using regex-extracted dividend rate for series in description: {rate}%")
                            break

                if dividend_rate_final is None:
                    logger.warning(f"No dividend rate found for {data.get('security_id', 'unknown')} - LLM: {dividend_rate_llm}, regex rates available: {list(extracted_rates.keys())}")

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
                dividend_rate=dividend_rate_final,
                dividend_type=data.get('dividend_type'),
                is_cumulative=data.get('is_cumulative'),
                payment_frequency=data.get('payment_frequency'),
                dividend_payment_dates=data.get('dividend_payment_dates', []),
                dividend_stopper_clause=data.get('dividend_stopper_clause'),
                dividend_calculation_method=data.get('dividend_calculation_method'),
                is_perpetual=data.get('is_perpetual'),

                # Original offering information
                original_offering_size=self._safe_int(data.get('original_offering_size')),
                original_offering_date=data.get('original_offering_date'),
                original_offering_price=self._safe_float(data.get('original_offering_price')),
                is_new_issuance=data.get('is_new_issuance'),
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


def extract_securities_features(ticker: str, api_key: str = None, matched_filings: List[Dict] = None) -> SecuritiesFeaturesResult:
    """Convenience function to extract securities features."""
    extractor = SecuritiesFeaturesExtractor(api_key)
    return extractor.extract_securities_features(ticker, matched_filings)


def extract_preferred_stocks_simple(ticker: str, api_key: str = None) -> SecuritiesFeaturesResult:
    """
    Simplified preferred stock extraction pipeline:

    1. Get basic data from 10-Q (series names, outstanding shares)
    2. Find matching 424B filings via simple regex
    3. Extract detailed features from matched 424Bs
    """
    logger.info(f"Starting simplified preferred stock extraction for {ticker}")

    # Step 1: Get series names from 10-Q via simple regex
    client = SECAPIClient()
    filing_content = client.get_filing_text(ticker, '10-Q')

    if not filing_content:
        logger.warning(f"No 10-Q filing found for {ticker}")
        return SecuritiesFeaturesResult(ticker=ticker, extraction_date=date.today())

    # Simple regex to find preferred stock series in 10-Q
    import re
    series_pattern = r'Series\s+([A-Z]+).*?Preferred\s+Stock'
    series_matches = re.findall(series_pattern, filing_content, re.IGNORECASE | re.MULTILINE)

    # Also look for "Preferred Stock, Series X" pattern
    reverse_pattern = r'Preferred\s+Stock.*?Series\s+([A-Z]+)'
    reverse_matches = re.findall(reverse_pattern, filing_content, re.IGNORECASE | re.MULTILINE)

    # Combine and deduplicate series names
    series_names = list(set(series_matches + reverse_matches))

    if not series_names:
        logger.warning(f"No preferred stock series found in 10-Q for {ticker}")
        return SecuritiesFeaturesResult(ticker=ticker, extraction_date=date.today())

    logger.info(f"Found preferred stock series in 10-Q: {series_names}")

    # Step 2: Find matching 424B filings
    from core.filing_matcher import match_series_to_424b
    matched_filings = match_series_to_424b(ticker, series_names, max_filings=20)

    if not matched_filings:
        logger.warning(f"No matching 424B filings found for {ticker}")
        return SecuritiesFeaturesResult(ticker=ticker, extraction_date=date.today())

    # Step 3: Extract detailed features from matched filings
    extractor = SecuritiesFeaturesExtractor(api_key)
    result = extractor.extract_securities_features(ticker, matched_filings)

    logger.info(f"Completed extraction: {result.total_securities} securities")
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python securities_features_extractor.py <TICKER> [API_KEY]")
        sys.exit(1)

    ticker = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None

    result = extract_preferred_stocks_simple(ticker, api_key)

    print(f"Extracted {result.total_securities} securities for {ticker}")
    for security in result.securities:
        print(f"  - {security.security_id}: {security.security_type}")
        if security.dividend_rate:
            print(f"    Dividend Rate: {security.dividend_rate}%")

    # Save results
    extractor = SecuritiesFeaturesExtractor(api_key)
    extractor.save_results(result)
