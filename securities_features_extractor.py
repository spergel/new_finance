#!/usr/bin/env python3
"""
Securities Features Extractor

Extracts detailed features of bonds and preferred shares from 424B and S-1 filings.
Focuses on conversion terms, redemption terms, and special features like change-of-control.
"""

import os
import re
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, date
from sec_api_client import SECAPIClient
from models import SecurityData, ConversionTerms, MetricsSummary, OriginalDataReference, QuantitativeMetrics, FormulaComponents, StructuredProductMetrics, ConversionMetrics, VWAPMetrics, MinMaxFormulaComponents, AntiDilutionMetrics, FloatingRateMetrics, CashlessExerciseMetrics, FormulaDisplayMetrics, StandardizedSecurityMetrics

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv('.env.local')
except ImportError:
    try:
        with open('.env.local', 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    except FileNotFoundError:
        pass

import google.generativeai as genai

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_SECURITIES_LIMIT = 25  # Limit total securities to avoid overwhelming output from large banks
MAX_DOCUMENTS_LIMIT = 50   # Limit total documents processed to avoid excessive downloads

class SecurityFeaturesClassifier:
    """Classifies exotic securities features from filing content."""
    
    def __init__(self, model):
        self.model = model
    
    def classify_features(self, content: str, ticker: str, filing_type: str) -> List[Dict]:
        """Classify what types of exotic securities features are present."""
        
        prompt = f"""
You are analyzing a {filing_type} filing for {ticker} to IDENTIFY what types of EXOTIC SECURITIES FEATURES are present.

Your job is to scan the document and identify which of these EXOTIC feature categories are present:

1. **EXOTIC_CONVERSION**: Unusual conversion mechanisms
   - Performance-based conversion ratios
   - Multi-step conversion processes  
   - Conversion into non-common securities
   - Volatility or metric-linked conversion
   - Anti-dilution provisions beyond standard

2. **TRIGGER_EVENTS**: Event-driven provisions
   - Delisting event protections
   - Credit rating trigger events
   - Regulatory change provisions
   - Spin-off or merger special terms
   - Performance milestone triggers

3. **CONTROL_RIGHTS**: Unusual voting and control provisions
   - Voting rights that scale with ownership
   - Board nomination rights at thresholds
   - Veto rights on specific actions
   - Tag-along/drag-along rights
   - Special control provisions

4. **EXOTIC_PAYMENTS**: Non-standard payment features
   - Toggle PIK (payment-in-kind) options
   - Step-up interest rate schedules
   - Performance-linked dividends
   - Catch-up payment provisions
   - Contingent payment mechanisms

5. **PERFORMANCE_MILESTONES**: Achievement-based triggers
   - Drug approval milestone payments
   - Revenue/EBITDA achievement triggers
   - Market cap threshold events
   - Earnout mechanisms (SPAC-related)
   - Clinical trial milestone conversions

6. **ADVANCED_CONTROL_RIGHTS**: Sophisticated governance provisions
   - Scaling voting rights based on ownership levels
   - Board nomination rights at specific thresholds
   - Tag-along and drag-along provisions
   - Protective veto rights on material decisions
   - Information and inspection rights

7. **CREDIT_REGULATORY_TRIGGERS**: Financial and regulatory events
   - Credit rating downgrade triggers
   - Basel III regulatory capital events
   - Investment grade to junk triggers
   - Regulatory approval contingencies
   - Financial covenant breaches

Look for these SIGNAL PHRASES in the document:
- "delisting event", "fundamental change", "change of control"
- "anti-dilution", "weighted average", "ratchet"
- "voting threshold", "board rights", "nomination rights"
- "toggle", "step-up", "performance-based", "PIK"
- "milestone", "earnout", "achievement", "approval"
- "credit rating", "investment grade", "regulatory capital"
- "tag-along", "drag-along", "protective provisions"

Here's the filing content (first 150,000 characters):

{content[:150000]}

Return ONLY a JSON object listing the exotic feature types found:

{{
    "exotic_features": [
        {{
            "feature_type": "EXOTIC_CONVERSION",
            "confidence": 0.85,
            "evidence": "Contains anti-dilution provisions with weighted average adjustment"
        }},
        {{
            "feature_type": "EXOTIC_PAYMENTS", 
            "confidence": 0.92,
            "evidence": "PIK toggle notes and step-up interest rate schedules found"
        }}
    ]
}}

Only include features with confidence > 0.7.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                return []
            
            # Parse response using robust JSON parser
            return self._parse_json_response(response.text, 'exotic_features')
            
        except Exception as e:
            logger.error(f"Error in features classification: {e}")
            return []
    
    def _parse_json_response(self, response_text: str, expected_key: str) -> List[Dict]:
        """Parse JSON response with robust error handling."""
        if not response_text:
            return []
        
        try:
            # Clean response text
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            # Try to parse JSON
            data = json.loads(cleaned.strip())
            return data.get(expected_key, [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in {self.__class__.__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON in {self.__class__.__name__}: {e}")
            return []

class ExoticConversionExtractor:
    """Specialized extractor for exotic conversion mechanisms."""
    
    def __init__(self, model, text_extractor=None):
        self.model = model
        self.text_extractor = text_extractor
    
    def extract(self, content: str, ticker: str, filing_type: str) -> List[Dict]:
        """Extract exotic conversion features."""
        
        prompt = f"""
You are a CONVERSION SPECIALIST analyzing {ticker} {filing_type} filing for EXOTIC CONVERSION MECHANISMS.

Hunt for these EXOTIC conversion features that don't fit standard patterns:

1. **PERFORMANCE-BASED CONVERSION**:
   - Conversion ratios that change based on stock performance
   - TSR (total shareholder return) linked conversion
   - Relative performance vs peers or indices

2. **ANTI-DILUTION PROVISIONS**:
   - Weighted average anti-dilution (broad vs narrow)
   - Ratchet provisions (full vs partial)
   - Special dividend adjustments
   - Spin-off protection mechanisms

3. **MULTI-ASSET CONVERSION**:
   - Conversion into preferred stock or other securities
   - Conversion into cash + stock combinations
   - Exchange into different security series

4. **VOLATILITY/METRIC-LINKED**:
   - Conversion tied to VIX or volatility measures
   - ESG metric-based conversion adjustments
   - Credit rating linked conversion terms

5. **COMPLEX TIMING MECHANISMS**:
   - Blackout periods for conversion
   - Multiple conversion windows
   - Performance period requirements

EXTRACT EXACT LANGUAGE from the document. Focus on:
- Specific formulas and calculations
- Exact trigger conditions and thresholds
- Precise adjustment mechanisms

Here's the content (first 200,000 characters):

{content[:200000]}

Return ONLY a JSON object:

{{
    "exotic_conversions": [
        {{
            "security_description": "EXACT NAME FROM DOCUMENT",
            "conversion_type": "performance_based_anti_dilution",
            "exotic_mechanism": "EXACT DESCRIPTION FROM FILING",
            "adjustment_formula": "EXACT FORMULA IF PROVIDED",
            "trigger_conditions": ["SPECIFIC CONDITIONS"],
            "blackout_periods": "ANY TIMING RESTRICTIONS",
            "anti_dilution_type": "weighted_average_broad",
            "performance_metrics": ["TSR", "relative_performance"],
            "exact_language": "VERBATIM QUOTE FROM FILING"
        }}
    ]
}}

CRITICAL: Only extract if you find ACTUAL exotic conversion language, not standard conversion.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                return []
            
            return self._parse_json_response(response.text, 'exotic_conversions')
            
        except Exception as e:
            logger.error(f"Error in exotic conversion extraction: {e}")
            return []
    
    def _parse_json_response(self, response_text: str, expected_key: str) -> List[Dict]:
        """Parse JSON response with robust error handling."""
        if not response_text:
            return []
        
        try:
            # Clean response text
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            # Try to parse JSON
            data = json.loads(cleaned.strip())
            return data.get(expected_key, [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in {self.__class__.__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON in {self.__class__.__name__}: {e}")
            return []

class TriggerEventsExtractor:
    """Specialized extractor for event-driven provisions."""
    
    def __init__(self, model, text_extractor=None):
        self.model = model
        self.text_extractor = text_extractor
    
    def extract(self, content: str, ticker: str, filing_type: str) -> List[Dict]:
        """Extract trigger event provisions."""
        
        prompt = f"""
You are a TRIGGER EVENTS SPECIALIST analyzing {ticker} {filing_type} filing for EVENT-DRIVEN PROVISIONS.

Hunt for these EXOTIC trigger events and their consequences:

1. **DELISTING TRIGGERS**:
   - What happens if stock gets delisted
   - Forced conversion or redemption rights
   - Alternative trading venue provisions

2. **CREDIT RATING TRIGGERS**:
   - Actions triggered by rating downgrades
   - Investment grade to junk triggers
   - Specific rating agency thresholds

3. **REGULATORY TRIGGERS**:
   - Changes due to tax law modifications
   - Basel III compliance triggers
   - Sector-specific regulatory changes

4. **PERFORMANCE TRIGGERS**:
   - Revenue or EBITDA milestone events
   - Market cap threshold triggers
   - Trading volume-based events

5. **CORPORATE ACTION TRIGGERS**:
   - Special merger/acquisition provisions
   - Spin-off protection mechanisms
   - Dividend threshold triggers

Extract EXACT trigger definitions and resulting actions:

Here's the content (first 200,000 characters):

{content[:200000]}

Return ONLY a JSON object:

{{
    "trigger_events": [
        {{
            "security_description": "EXACT NAME FROM DOCUMENT",
            "trigger_type": "delisting_event",
            "trigger_definition": "EXACT DEFINITION FROM FILING",
            "trigger_threshold": "SPECIFIC THRESHOLD IF NUMERIC",
            "resulting_actions": ["forced_conversion", "redemption_right"],
            "holder_rights": "WHAT HOLDERS CAN DO",
            "company_obligations": "WHAT COMPANY MUST DO",
            "notice_periods": "TIMING REQUIREMENTS",
            "exact_language": "VERBATIM QUOTE FROM FILING"
        }}
    ]
}}

CRITICAL: Extract exact trigger language and specific consequences.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                return []
            
            return self._parse_json_response(response.text, 'trigger_events')
            
        except Exception as e:
            logger.error(f"Error in trigger events extraction: {e}")
            return []
    
    def _parse_json_response(self, response_text: str, expected_key: str) -> List[Dict]:
        """Parse JSON response with robust error handling."""
        if not response_text:
            return []
        
        try:
            # Clean response text
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            # Try to parse JSON
            data = json.loads(cleaned.strip())
            return data.get(expected_key, [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in {self.__class__.__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON in {self.__class__.__name__}: {e}")
            return []

class ControlRightsExtractor:
    """Specialized extractor for unusual voting and control provisions."""
    
    def __init__(self, model, text_extractor=None):
        self.model = model
        self.text_extractor = text_extractor
    
    def extract(self, content: str, ticker: str, filing_type: str) -> List[Dict]:
        """Extract control rights provisions."""
        
        prompt = f"""
You are a CONTROL RIGHTS SPECIALIST analyzing {ticker} {filing_type} filing for UNUSUAL VOTING AND CONTROL PROVISIONS.

Hunt for these EXOTIC control features:

1. **SCALING VOTING RIGHTS**:
   - Voting power that increases with ownership percentage
   - Different voting ratios for different matters
   - Super-voting rights at certain thresholds

2. **BOARD RIGHTS**:
   - Director nomination rights at ownership thresholds
   - Board observer rights
   - Committee participation rights

3. **VETO RIGHTS**:
   - Blocking rights on specific corporate actions
   - Consent rights for material decisions
   - Protective provisions

4. **TAG/DRAG RIGHTS**:
   - Tag-along rights (right to participate in sales)
   - Drag-along rights (forced participation)
   - Right of first refusal provisions

5. **INFORMATION RIGHTS**:
   - Enhanced disclosure requirements
   - Inspection rights
   - Financial reporting rights

Extract EXACT ownership thresholds and specific rights:

Here's the content (first 200,000 characters):

{content[:200000]}

Return ONLY a JSON object:

{{
    "control_rights": [
        {{
            "security_description": "EXACT NAME FROM DOCUMENT",
            "rights_type": "board_nomination_rights",
            "ownership_threshold": "EXACT PERCENTAGE OR AMOUNT",
            "specific_rights": ["nominate_2_directors", "board_observer"],
            "voting_mechanics": "HOW VOTING WORKS",
            "approval_thresholds": "WHAT APPROVALS NEEDED",
            "protective_provisions": ["material_transactions", "dividend_changes"],
            "information_rights": "WHAT INFO HOLDER GETS",
            "exercise_conditions": "HOW TO EXERCISE RIGHTS",
            "exact_language": "VERBATIM QUOTE FROM FILING"
        }}
    ]
}}

CRITICAL: Extract exact ownership thresholds and specific control mechanisms.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                return []
            
            return self._parse_json_response(response.text, 'control_rights')
            
        except Exception as e:
            logger.error(f"Error in control rights extraction: {e}")
            return []
    
    def _parse_json_response(self, response_text: str, expected_key: str) -> List[Dict]:
        """Parse JSON response with robust error handling."""
        if not response_text:
            return []
        
        try:
            # Clean response text
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            # Try to parse JSON
            data = json.loads(cleaned.strip())
            return data.get(expected_key, [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in {self.__class__.__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON in {self.__class__.__name__}: {e}")
            return []

class ExoticPaymentsExtractor:
    """Specialized extractor for exotic payment mechanisms."""
    
    def __init__(self, model, text_extractor=None):
        self.model = model
        self.text_extractor = text_extractor
    
    def extract(self, content: str, ticker: str, filing_type: str) -> List[Dict]:
        """Extract exotic payment features."""
        
        prompt = f"""
You are analyzing {ticker} {filing_type} for EXOTIC PAYMENT FEATURES.

Find these specific exotic payment mechanisms:

1. **PIK TOGGLE**: Payment-in-kind vs cash elections
2. **STEP-UP RATES**: Interest rates that increase over time  
3. **PERFORMANCE PAYMENTS**: Payments tied to metrics like revenue/EBITDA
4. **CONTINGENT PAYMENTS**: Conditional or catch-up payments

Look for phrases like:
- "PIK toggle", "payment-in-kind", "cash election"
- "step-up", "escalating rate", "increasing interest"
- "performance-based", "contingent on", "achievement"
- "make-whole", "catch-up payment"

Content sample: {content[:100000]}

Return ONLY valid JSON:

{{
    "exotic_payments": [
        {{
            "security_description": "Name from document",
            "payment_type": "pik_toggle",
            "exotic_mechanism": "Description from filing",
            "rate_schedule": "Any rate details",
            "exact_language": "Quote from filing"
        }}
    ]
}}

Only include if you find ACTUAL exotic payment features.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                return []
            
            return self._parse_json_response(response.text, 'exotic_payments')
            
        except Exception as e:
            logger.error(f"Error in exotic payments extraction: {e}")
            return []
    
    def _parse_json_response(self, response_text: str, expected_key: str) -> List[Dict]:
        """Parse JSON response with robust error handling."""
        if not response_text:
            return []
        
        try:
            # Clean response text
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            # Try to parse JSON
            data = json.loads(cleaned.strip())
            return data.get(expected_key, [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in {self.__class__.__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON in {self.__class__.__name__}: {e}")
            return []

class PerformanceMilestonesExtractor:
    """Specialized extractor for performance milestone features."""
    
    def __init__(self, model, text_extractor=None):
        self.model = model
        self.text_extractor = text_extractor
    
    def extract(self, content: str, ticker: str, filing_type: str) -> List[Dict]:
        """Extract performance milestone features."""
        
        prompt = f"""
You are analyzing {ticker} {filing_type} for PERFORMANCE MILESTONE FEATURES.

Find these specific milestone mechanisms:

1. **BIOTECH MILESTONES**: FDA approvals, clinical trial completions
2. **FINANCIAL MILESTONES**: Revenue/EBITDA achievement targets
3. **SPAC EARNOUTS**: Post-merger performance triggers
4. **OPERATIONAL MILESTONES**: Production, customer, or technology targets

Look for phrases like:
- "milestone payment", "earnout", "achievement"
- "FDA approval", "clinical trial", "regulatory approval"
- "revenue target", "EBITDA threshold", "market cap"
- "post-merger", "sponsor promote", "performance period"

Content sample: {content[:100000]}

Return ONLY valid JSON:

{{
    "performance_milestones": [
        {{
            "security_description": "Name from document",
            "milestone_type": "biotech_approval",
            "milestone_definition": "Description from filing",
            "performance_metrics": ["FDA_approval"],
            "achievement_thresholds": "Specific targets",
            "resulting_actions": ["payment_trigger"],
            "exact_language": "Quote from filing"
        }}
    ]
}}

Only include if you find ACTUAL milestone features.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                return []
            
            return self._parse_json_response(response.text, 'performance_milestones')
            
        except Exception as e:
            logger.error(f"Error in performance milestones extraction: {e}")
            return []
    
    def _parse_json_response(self, response_text: str, expected_key: str) -> List[Dict]:
        """Parse JSON response with robust error handling."""
        if not response_text:
            return []
        
        try:
            # Clean response text
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            # Try to parse JSON
            data = json.loads(cleaned.strip())
            return data.get(expected_key, [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in {self.__class__.__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON in {self.__class__.__name__}: {e}")
            return []

class CreditRegulatoryTriggersExtractor:
    """Specialized extractor for credit rating and regulatory trigger events."""
    
    def __init__(self, model, text_extractor=None):
        self.model = model
        self.text_extractor = text_extractor
    
    def extract(self, content: str, ticker: str, filing_type: str) -> List[Dict]:
        """Extract credit and regulatory trigger features."""
        
        prompt = f"""
You are a CREDIT & REGULATORY SPECIALIST analyzing {ticker} {filing_type} filing for FINANCIAL AND REGULATORY TRIGGERS.

Hunt for these CREDIT/REGULATORY trigger features:

1. **CREDIT RATING TRIGGERS**:
   - Investment grade to junk downgrades
   - Specific rating agency thresholds (S&P, Moody's, Fitch)
   - Multiple notch downgrade triggers
   - Rating upgrade conversion provisions

2. **REGULATORY CAPITAL TRIGGERS**:
   - Basel III compliance events
   - Tier 1 capital ratio thresholds
   - CCAR/stress test failure triggers
   - Regulatory approval contingencies

3. **FINANCIAL COVENANT TRIGGERS**:
   - Debt-to-equity ratio breaches
   - Interest coverage ratio failures
   - Liquidity requirement violations
   - Net worth covenant breaches

4. **REGULATORY APPROVAL EVENTS**:
   - FDA approval contingencies
   - FCC license approval triggers
   - Environmental permit contingencies
   - Antitrust approval requirements

5. **SECTOR-SPECIFIC TRIGGERS**:
   - Bank regulatory actions
   - Insurance solvency triggers
   - Utility rate case outcomes
   - Mining permit approvals

Extract EXACT trigger definitions and resulting consequences:

Here's the content (first 200,000 characters):

{content[:200000]}

Return ONLY a JSON object:

{{
    "credit_regulatory_triggers": [
        {{
            "security_description": "EXACT NAME FROM DOCUMENT",
            "trigger_type": "credit_rating_downgrade",
            "trigger_definition": "EXACT DEFINITION FROM FILING",
            "rating_thresholds": "SPECIFIC RATING LEVELS",
            "rating_agencies": ["SP", "Moodys", "Fitch"],
            "regulatory_body": "WHICH REGULATOR IF APPLICABLE",
            "financial_covenants": "SPECIFIC RATIO THRESHOLDS",
            "resulting_actions": ["rate_increase", "conversion_right"],
            "cure_periods": "TIME TO REMEDY BREACH",
            "enforcement_mechanisms": "HOW TRIGGERS ARE ENFORCED",
            "exact_language": "VERBATIM QUOTE FROM FILING"
        }}
    ]
}}

CRITICAL: Extract exact rating levels, covenant ratios, and regulatory requirements.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                return []
            
            return self._parse_json_response(response.text, 'credit_regulatory_triggers')
            
        except Exception as e:
            logger.error(f"Error in credit/regulatory triggers extraction: {e}")
            return []
    
    def _parse_json_response(self, response_text: str, expected_key: str) -> List[Dict]:
        """Parse JSON response with robust error handling."""
        if not response_text:
            return []
        
        try:
            # Clean response text
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            # Try to parse JSON
            data = json.loads(cleaned.strip())
            return data.get(expected_key, [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in {self.__class__.__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON in {self.__class__.__name__}: {e}")
            return []

class SecuritiesFeaturesExtractor:
    """Extract exotic securities features from SEC filings using specialized extractors."""
    
    def __init__(self):
        """Initialize the extractor with classifier and specialized extractors."""
        # Initialize data directory and SEC client
        self.data_dir = "temp_filings"
        os.makedirs(self.data_dir, exist_ok=True)
        self.sec_client = SECAPIClient(data_dir=self.data_dir)
        
        # Filing types for securities features - prioritized by information richness
        self.filing_types = ["S-3", "S-1", "424B5", "424B4", "424B3", "424B2", "424B1", "424B7"]
        
        # Initialize Gemini model
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-lite')
        
        # Initialize text extractor
        self.text_extractor = TextExtractor()
        
        # Initialize quantitative extractor for numerical analysis
        self.quantitative_extractor = QuantitativeExtractor()
        
        # Initialize classifier and specialized extractors
        self.classifier = SecurityFeaturesClassifier(self.model)
        self.exotic_conversion_extractor = ExoticConversionExtractor(self.model, self.text_extractor)
        self.trigger_events_extractor = TriggerEventsExtractor(self.model, self.text_extractor)
        self.control_rights_extractor = ControlRightsExtractor(self.model, self.text_extractor)
        self.exotic_payments_extractor = ExoticPaymentsExtractor(self.model, self.text_extractor)
        self.performance_milestones_extractor = PerformanceMilestonesExtractor(self.model, self.text_extractor)
        self.credit_regulatory_triggers_extractor = CreditRegulatoryTriggersExtractor(self.model, self.text_extractor)
        
        logger.info("Securities features extractor initialized with specialized exotic extractors")
    
    def extract_features(self, ticker: str, years_back: int = 5) -> List[SecurityData]:
        """
        Extract securities features for a ticker.
        
        Args:
            ticker: Company ticker symbol
            years_back: Years back to search (default: 5)
            
        Returns:
            List of SecurityData objects with detailed features
        """
        logger.info(f"Extracting securities features for {ticker}")
        
        if not self.model:
            logger.error("LLM not available")
            return []
        
        # Download relevant filings
        all_securities = []
        documents_processed = 0
        months_back = years_back * 12
        
        # If only 424B filings are selected, limit to first 5 total across all 424B subtypes
        only_424b_mode = all(ft.startswith("424B") for ft in self.filing_types)
        remaining_424b = 5 if only_424b_mode else None
        
        for filing_type in self.filing_types:
            logger.info(f"Processing {filing_type} filings...")
            
            try:
                # Download filings
                max_results = None
                if only_424b_mode:
                    if remaining_424b is None or remaining_424b <= 0:
                        break
                    max_results = remaining_424b
                file_paths = self.sec_client.download_filings_by_date_range(
                    ticker=ticker,
                    filing_types=[filing_type],
                    months_back=months_back,
                    max_results=max_results
                )
                # Hard slice to remaining total if only 424B mode
                if only_424b_mode and file_paths:
                    file_paths = file_paths[:remaining_424b]
                
                if not file_paths:
                    logger.info(f"No {filing_type} filings found")
                    continue
                
                # Extract features from each filing
                for file_path in file_paths:
                    # Check document limit before processing
                    if documents_processed >= MAX_DOCUMENTS_LIMIT:
                        logger.info(f"Reached document limit of {MAX_DOCUMENTS_LIMIT}, stopping document processing")
                        break
                        
                    documents_processed += 1
                    logger.info(f"Processing document {documents_processed}/{MAX_DOCUMENTS_LIMIT}: {file_path}")
                    
                    securities = self._extract_from_filing(file_path, filing_type, ticker)
                    if securities:
                        all_securities.extend(securities)
                        logger.info(f"Extracted {len(securities)} securities from {filing_type}")
                        
                        # Check if we've reached the securities limit
                        if len(all_securities) >= MAX_SECURITIES_LIMIT:
                            logger.info(f"Reached securities limit of {MAX_SECURITIES_LIMIT}, stopping extraction")
                            all_securities = all_securities[:MAX_SECURITIES_LIMIT]  # Trim to exact limit
                            break
                    
                    # Decrement remaining total 424B allowance
                    if only_424b_mode:
                        remaining_424b -= 1
                        if remaining_424b <= 0:
                            logger.info("Reached total 424B document cap (5), stopping further 424B processing")
                            break
                
                # Break out of filing type loop if either limit reached
                if len(all_securities) >= MAX_SECURITIES_LIMIT or documents_processed >= MAX_DOCUMENTS_LIMIT or (only_424b_mode and remaining_424b is not None and remaining_424b <= 0):
                    break
                
            except Exception as e:
                logger.error(f"Error processing {filing_type}: {e}")
                continue
        
        # Save results
        if all_securities:
            self._save_results(ticker, all_securities)
        
        return all_securities
    
    def _extract_from_filing(self, file_path: str, filing_type: str, ticker: str) -> List[SecurityData]:
        """Extract securities from a single filing using specialized extractors."""
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Classify features first
            exotic_features = self.classifier.classify_features(content, ticker, filing_type)
            
            # Initialize a list to hold SecurityData objects
            securities = []
            
            for feature in exotic_features:
                feature_type = feature.get('feature_type')
                evidence = feature.get('evidence')
                
                if feature_type == 'EXOTIC_CONVERSION':
                    logger.info(f"Extracting exotic conversion features from {file_path}")
                    conversion_features = self.exotic_conversion_extractor.extract(content, ticker, filing_type)
                    for conv_sec in conversion_features:
                        security = self._create_security_data(conv_sec, ticker, filing_type)
                        if security:
                            securities.append(security)
                elif feature_type == 'TRIGGER_EVENTS':
                    logger.info(f"Extracting trigger event features from {file_path}")
                    trigger_features = self.trigger_events_extractor.extract(content, ticker, filing_type)
                    for trigger_sec in trigger_features:
                        security = self._create_security_data(trigger_sec, ticker, filing_type)
                        if security:
                            securities.append(security)
                elif feature_type == 'CONTROL_RIGHTS':
                    logger.info(f"Extracting control rights features from {file_path}")
                    control_features = self.control_rights_extractor.extract(content, ticker, filing_type)
                    for control_sec in control_features:
                        security = self._create_security_data(control_sec, ticker, filing_type)
                        if security:
                            securities.append(security)
                elif feature_type == 'ADVANCED_CONTROL_RIGHTS':
                    logger.info(f"Extracting advanced control rights features from {file_path}")
                    control_features = self.control_rights_extractor.extract(content, ticker, filing_type)
                    for control_sec in control_features:
                        security = self._create_security_data(control_sec, ticker, filing_type)
                        if security:
                            securities.append(security)
                elif feature_type == 'EXOTIC_PAYMENTS':
                    logger.info(f"Extracting exotic payment features from {file_path}")
                    payment_features = self.exotic_payments_extractor.extract(content, ticker, filing_type)
                    for payment_sec in payment_features:
                        security = self._create_security_data(payment_sec, ticker, filing_type)
                        if security:
                            securities.append(security)
                elif feature_type == 'PERFORMANCE_MILESTONES':
                    logger.info(f"Extracting performance milestone features from {file_path}")
                    milestone_features = self.performance_milestones_extractor.extract(content, ticker, filing_type)
                    for milestone_sec in milestone_features:
                        security = self._create_security_data(milestone_sec, ticker, filing_type)
                        if security:
                            securities.append(security)
                elif feature_type == 'CREDIT_REGULATORY_TRIGGERS':
                    logger.info(f"Extracting credit/regulatory triggers from {file_path}")
                    trigger_features = self.credit_regulatory_triggers_extractor.extract(content, ticker, filing_type)
                    for trigger_sec in trigger_features:
                        security = self._create_security_data(trigger_sec, ticker, filing_type)
                        if security:
                            securities.append(security)
                else:
                    logger.warning(f"Skipping unknown exotic feature type: {feature_type} from {file_path}")
            
            # Also try to extract from related exhibits (indentures, etc.)
            exhibit_securities = self._extract_from_exhibits(file_path, ticker, filing_type)
            if exhibit_securities:
                securities.extend(exhibit_securities)
                logger.info(f"Found additional {len(exhibit_securities)} securities in exhibits")
            
            return securities
            
        except Exception as e:
            logger.error(f"Error extracting from {file_path}: {e}")
            return []
    
    def _extract_from_exhibits(self, file_path: str, ticker: str, filing_type: str) -> List[SecurityData]:
        """Extract additional details from exhibit files (indentures, etc.)."""
        
        securities = []
        try:
            # Get the accession number from file path to find related exhibits
            import re
            accession_match = re.search(r'(\d{10}-\d{2}-\d{6})', file_path)
            if not accession_match:
                return securities
                
            accession_number = accession_match.group(1)
            
            # Look for exhibit files in the same directory
            import os
            filing_dir = os.path.dirname(file_path)
            
            # Priority exhibit types for debt securities
            exhibit_patterns = [
                'ex4',     # Indentures 
                'ex-4',    # Indentures (alternate format)
                'ex10',    # Material agreements
                'ex-10',   # Material agreements (alternate)
                'ex3',     # Certificate of incorporation/designation
                'ex-3'     # Certificate (alternate)
            ]
            
            for filename in os.listdir(filing_dir):
                if not filename.endswith('.txt') and not filename.endswith('.htm'):
                    continue
                    
                filename_lower = filename.lower()
                
                # Check if this is a relevant exhibit
                is_relevant_exhibit = any(pattern in filename_lower for pattern in exhibit_patterns)
                
                if is_relevant_exhibit and accession_number in filename:
                    exhibit_path = os.path.join(filing_dir, filename)
                    logger.info(f"Processing exhibit: {filename}")
                    
                    # Process this exhibit
                    try:
                        with open(exhibit_path, 'r', encoding='utf-8', errors='ignore') as f:
                            exhibit_content = f.read()
                        
                        # Create exhibit-specific prompt
                        exhibit_prompt = self._create_exhibit_prompt(ticker, exhibit_content, filename)
                        
                        response = self.model.generate_content(exhibit_prompt)
                        if response.text:
                            exhibit_data = self._parse_response(response.text)
                            for sec_data in exhibit_data:
                                security = self._create_security_data(sec_data, ticker, f"{filing_type}_EXHIBIT")
                                if security:
                                    securities.append(security)
                                    
                    except Exception as e:
                        logger.warning(f"Error processing exhibit {filename}: {e}")
                        continue
            
        except Exception as e:
            logger.error(f"Error extracting from exhibits: {e}")
            
        return securities
    
    def _create_exhibit_prompt(self, ticker: str, content: str, filename: str) -> str:
        """Create LLM prompt specifically for exhibit documents (indentures, etc.)."""
        
        return f"""
You are analyzing an EXHIBIT document ({filename}) for {ticker} to extract DETAILED DEBT SECURITIES PROVISIONS.

This is likely an INDENTURE or CERTIFICATE document containing specific terms for debt securities or preferred stock.

Focus on extracting:

1. REDEMPTION/CALL PROVISIONS:
   - Specific call dates and prices (e.g., "callable at 104% beginning March 1, 2024")
   - Call protection periods
   - Make-whole call provisions with formulas
   - Notice requirements (exact days)

2. CHANGE OF CONTROL PROVISIONS:
   - Definition of "Fundamental Change" or "Change of Control"
   - Holder rights upon change of control
   - Repurchase obligations and prices
   - Notice periods and procedures

3. SECURITY IDENTIFICATION:
   - Full security name and description
   - CUSIP numbers
   - Principal amounts
   - Interest rates and payment dates
   - Maturity dates

4. COVENANTS AND RESTRICTIONS:
   - Financial covenants
   - Restrictions on dividends/distributions
   - Limitations on additional debt

Here's the exhibit content (first 100,000 characters):

{content[:100000]}

Return ONLY a JSON object focusing on DEBT-SPECIFIC terms:

{{
    "securities": [
        {{
            "xbrl_concept": "DebtSecurities",
            "cusip": "EXTRACTED_FROM_DOCUMENT",
            "description": "Full security name from indenture",
            "principal_amount": 000000000,
            "interest_rate": 0.000,
            "maturity_date": "YYYY-MM-DD",
            "conversion_features": null,
            "redemption_features": {{
                "is_callable": true,
                "call_protection_end": "YYYY-MM-DD",
                "redemption_price_schedule": [
                    {{"date": "YYYY-MM-DD", "price": 000.000}},
                    {{"date": "YYYY-MM-DD", "price": 000.000}}
                ],
                "make_whole_provision": true,
                "make_whole_formula": "EXACT FORMULA FROM INDENTURE",
                "notice_period_days": 00
            }},
            "special_features": {{
                "change_of_control": {{
                    "has_provision": true,
                    "trigger_description": "EXACT DEFINITION FROM INDENTURE", 
                    "holder_rights": "SPECIFIC RIGHTS DESCRIBED",
                    "repurchase_price": "EXACT PRICE/FORMULA",
                    "notice_period": "00 days"
                }},
                "interest_payment_dates": ["Month Day", "Month Day"],
                "covenants": "KEY COVENANTS LISTED"
            }},
            "filing_source": "EXHIBIT",
            "document_section": "Indenture"
        }}
    ]
}}

CRITICAL: Only extract if you find specific redemption schedules, change of control definitions, or other debt provisions in this document.
"""
    
    def _create_features_prompt(self, ticker: str, content: str, filing_type: str) -> str:
        """Create LLM prompt focused on securities features with XBRL standards."""
        
        is_shelf = filing_type in ["S-1", "S-3"]
        
        return f"""
You are analyzing a {filing_type} filing for {ticker} to extract DETAILED SECURITIES FEATURES with PRECISION on conversion mechanisms.

CRITICAL CONVERSION ANALYSIS:
You must distinguish between these DIFFERENT conversion types:

1. **FIXED CONVERSION RATIO**: Traditional convertibles with set ratio (e.g., "each bond converts to 50 shares")
2. **VARIABLE LIQUIDATION-BASED**: Conversion ratio depends on stock price at conversion (e.g., "liquidation preference / stock price")  
3. **CONDITIONAL/TRIGGER-BASED**: Only converts on specific events (Change of Control, Delisting)
4. **SHARE CAPS**: Maximum shares receivable, NOT the conversion ratio

LIQUIDATION PREFERENCE FOCUS:
- Extract exact liquidation preference per share (e.g., $25.00)
- Identify if conversion uses liquidation preference in calculation
- Look for "Share Cap" language vs "conversion ratio" language

CRITICAL: Search the ENTIRE document for:
- CUSIP numbers (format: 9-character alphanumeric codes)
- Trading symbols on NYSE/NASDAQ (like "BW PRA", "BWSN", "BWNB")
- **LIQUIDATION PREFERENCES** (exact dollar amounts per share)
- **CONVERSION TRIGGERS** (Change of Control, Delisting Event, automatic)
- **SHARE CAPS** vs conversion ratios
- Redemption dates and call schedules (exact dates and prices)
- Change of control trigger conditions (specific language and prices)
- Outstanding principal amounts (exact dollar figures)
- Maturity dates for debt securities

REQUIRED ANALYSIS FOR EACH SECURITY:

1. BASIC IDENTIFICATION:
   - Exact CUSIP (9-character alphanumeric)
   - Trading symbol (NYSE/NASDAQ symbol)
   - Principal/liquidation preference amount
   - Interest/dividend rate
   - Issue and maturity dates

2. LIQUIDATION ANALYSIS:
   - Liquidation preference per share (exact dollar amount)
   - Liquidation ranking (senior to common, junior to debt)
   - Whether liquidation preference is used in conversion calculations

3. CONVERSION MECHANISM ANALYSIS:
   **Ask these specific questions:**
   - Is this security convertible at all? (Look for explicit conversion language)
   - If convertible, what TYPE of conversion?
     * FIXED RATIO: "converts to X shares" or "conversion ratio of X"
     * VARIABLE: "liquidation preference divided by stock price" 
     * CONDITIONAL: "upon Change of Control" or "upon Delisting Event"
   - Is there a SHARE CAP (maximum shares receivable)?
   - What triggers conversion? (automatic, Change of Control, Delisting, etc.)

4. SHARE CAP vs CONVERSION RATIO:
   - Look for "Share Cap" language specifically
   - If you see a number like 5.65611, determine if it's:
     * A fixed conversion ratio, OR
     * A maximum share cap, OR
     * Part of a liquidation-based formula
   - Extract the CALCULATION method for any caps

5. REDEMPTION/CALL FEATURES:
   - Call protection periods and schedules
   - Redemption prices and dates
   - Make-whole provisions
   - Notice requirements

6. CHANGE OF CONTROL PROVISIONS:
   - Exact trigger definitions
   - Holder rights and options
   - Company redemption rights
   - Notice periods

Here's the filing content (first 300,000 characters):

{content[:300000]}

Return ONLY a JSON object with this ENHANCED structure:

{{
    "securities": [
        {{
            "xbrl_concept": "PreferredStockIncludingAdditionalPaidInCapital",
            "cusip": "05961WAD8",
            "trading_symbol": "BW PRA",
            "description": "7.75% Series A Cumulative Perpetual Preferred Stock",
            "principal_amount": 25.00,
            "outstanding_amount": 260000000,
            "interest_rate": 7.75,
            "issue_date": "2021-05-07",
            "maturity_date": null,
            "listing_exchange": "NYSE",
            
            "liquidation_terms": {{
                "liquidation_preference_per_share": 25.00,
                "liquidation_ranking": "Senior to common stock, junior to debt",
                "includes_accrued_dividends": true
            }},
            
            "conversion_features": {{
                "is_convertible": true,
                "conversion_type": "conditional_variable_liquidation_based",
                "is_conditional_conversion": true,
                "conversion_triggers": ["change_of_control", "delisting_event"],
                "is_variable_conversion": true,
                "variable_conversion_formula": "($25.00 + accrued dividends) / Common Stock Price",
                "has_share_cap": true,
                "share_cap_maximum": 5.65611,
                "share_cap_calculation": "$25.00 liquidation preference / (0.5 * $4.42 stock price on May 3, 2021)",
                "conversion_explanation": "Not freely convertible. Only converts on Change of Control or Delisting. Conversion ratio varies based on stock price at time of event, capped at 5.65611 shares maximum."
            }},
            
            "redemption_features": {{
                "is_callable": true,
                "call_protection_end": "2026-05-07",
                "earliest_redemption_date": "2026-05-07",
                "redemption_price": 25.00,
                "notice_period_days": 30,
                "special_redemption_events": ["change_of_control", "delisting_event"]
            }},
            
            "special_features": {{
                "change_of_control": {{
                    "has_provision": true,
                    "trigger_description": "Acquisition of >50% voting power AND delisting from major exchange",
                    "holder_rights": "Right to convert at variable ratio or receive cash redemption",
                    "conversion_vs_redemption": "Holder choice between conversion and redemption"
                }}
            }},
            
            "filing_source": "{filing_type}",
            "is_shelf_registration": {str(is_shelf).lower()}
        }},
        {{
            "xbrl_concept": "DebtSecurities",
            "cusip": "96705MAC9",
            "trading_symbol": "BWSN",
            "description": "8.125% senior notes due 2026",
            "conversion_features": null,
            "conversion_explanation": "Non-convertible debt security. No conversion provisions.",
            "redemption_features": {{
                "is_callable": true,
                "call_protection_end": "2024-02-28",
                "earliest_redemption_date": "2024-02-28",
                "redemption_price_schedule": [
                    {{"date": "2024-02-28", "price": 104.063}},
                    {{"date": "2025-02-28", "price": 102.031}}
                ],
                "notice_period_days": 30,
                "make_whole_provision": false
            }},
            "special_features": {{
                "change_of_control": {{
                    "has_provision": true,
                    "trigger_description": "Fundamental change as defined in indenture",
                    "holder_rights": "Right to require repurchase at 101% of principal plus accrued interest",
                    "notice_period": "30 days"
                }},
                "interest_payment_dates": ["February 28", "August 28"],
                "covenants": "Standard restrictive covenants as defined in indenture"
            }},
            "filing_source": "{filing_type}",
            "is_shelf_registration": {str(is_shelf).lower()},
            "document_section": "Description of Notes"
        }}
    ]
}}

VALIDATION RULES:
- If security is NOT explicitly described as convertible, set conversion_features to null
- Distinguish between "Share Cap" (maximum) and "conversion ratio" (standard)
- For conditional conversion, clearly identify the trigger events
- For variable conversion, extract the exact formula
- Always include conversion_explanation summarizing the mechanism
"""
    
    def _parse_response(self, response_text: str) -> List[Dict]:
        """Parse LLM response to extract securities data."""
        try:
            # Clean response
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            data = json.loads(cleaned.strip())
            return data.get('securities', [])
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return []
    
    def _create_security_data(self, sec_data: Dict, ticker: str, filing_type: str) -> Optional[SecurityData]:
        """Convert parsed exotic features data to SecurityData object with enhanced exotic details."""
        
        try:
            # Parse date safely
            def safe_date(date_str):
                if not date_str:
                    return None
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except:
                    return None
            
            # Determine data type and create appropriate SecurityData
            if 'exotic_mechanism' in sec_data:  # Exotic conversion data
                return self._create_exotic_conversion_security(sec_data, ticker, filing_type)
            elif 'trigger_definition' in sec_data:  # Trigger events data
                return self._create_trigger_events_security(sec_data, ticker, filing_type)
            elif 'rights_type' in sec_data:  # Control rights data
                return self._create_control_rights_security(sec_data, ticker, filing_type)
            elif 'payment_type' in sec_data:  # Exotic payments data
                return self._create_exotic_payments_security(sec_data, ticker, filing_type)
            elif 'milestone_type' in sec_data:  # Performance milestones data
                return self._create_performance_milestones_security(sec_data, ticker, filing_type)
            elif 'trigger_type' in sec_data:  # Credit/Regulatory triggers data
                return self._create_credit_regulatory_triggers_security(sec_data, ticker, filing_type)
            else:
                # Fall back to original method for backward compatibility
                return self._create_standard_security_data(sec_data, ticker, filing_type)
            
        except Exception as e:
            logger.error(f"Error creating SecurityData: {e}")
            logger.error(f"Input data: {sec_data}")
            return None
    
    def _create_exotic_conversion_security(self, conversion_data: Dict, ticker: str, filing_type: str) -> Optional[SecurityData]:
        """Create SecurityData for exotic conversion features with structured details."""

        # Extract quantitative metrics from conversion text
        # Normalize fields from LLM outputs (they're not always consistent)
        formula_obj = conversion_data.get('conversion_formula')
        if isinstance(formula_obj, dict):
            formula_text = formula_obj.get('formula', '')
        elif isinstance(formula_obj, str):
            formula_text = formula_obj
        else:
            formula_text = conversion_data.get('adjustment_formula', '') or ''

        mechanism_description = conversion_data.get('mechanism_description') or conversion_data.get('exotic_mechanism', '')
        exact_language = conversion_data.get('exact_language', '')
        conversion_text = f"{formula_text} {exact_language} {mechanism_description}"

        quantitative_metrics = self.quantitative_extractor.extract_quantitative_metrics(conversion_text, conversion_data.get('type', ''))

        # Build conversion_formula flags safely
        has_share_cap = False
        has_price_protection = False
        cf = conversion_data.get('conversion_formula')
        if isinstance(cf, dict):
            has_share_cap = bool(cf.get('has_share_cap', False))
            has_price_protection = bool(cf.get('has_price_protection', False))

        # Create structured exotic conversion details
        exotic_conversion_details = {
            "conversion_mechanism": {
                "type": conversion_data.get('type', conversion_data.get('conversion_type', 'unknown')),
                "mechanism_description": mechanism_description or 'N/A',
                "is_conditional": conversion_data.get('is_conditional', False),
                "is_variable": conversion_data.get('is_variable', False)
            },
            "trigger_conditions": [],
            "conversion_formula": {
                "formula": formula_text or 'N/A',
                "has_share_cap": has_share_cap,
                "has_price_protection": has_price_protection
            },
            "anti_dilution": {
                "type": (conversion_data.get('anti_dilution', {}) or {}).get('type', conversion_data.get('anti_dilution_type', 'N/A')),
                "scope": (conversion_data.get('anti_dilution', {}) or {}).get('scope', 'narrow')
            },
            "blackout_periods": conversion_data.get('blackout_periods', 'N/A'),
            "exact_language_sample": (exact_language or '')[:200] + "..." if len(exact_language or '') > 200 else (exact_language or 'N/A')
        }

        # Process trigger conditions if present (list of dicts or strings)
        triggers_list = conversion_data.get('trigger_conditions', []) or []
        if isinstance(triggers_list, list):
            for trig in triggers_list:
                if isinstance(trig, dict):
                    trig_text = trig.get('trigger', 'N/A')
                else:
                    trig_text = str(trig)
                exotic_conversion_details["trigger_conditions"].append({
                    "trigger": trig_text,
                    "category": self._categorize_trigger(trig_text)
                })

        original_ref = OriginalDataReference(
            id=f"{ticker}_{filing_type}_exotic_conversion_{int(datetime.now().timestamp())}",
            has_conversion_features=True,
            has_redemption_features=False,
            has_special_features=True,
            details=f"EXOTIC CONVERSION: {conversion_data.get('type', 'N/A')} with {len(triggers_list)} triggers"
        )

        # Create enhanced conversion terms from the extracted data
        conversion_terms = self._create_conversion_terms_from_data(conversion_data)

        security = SecurityData(
            id=f"{ticker}_{filing_type}_exotic_conversion_{int(datetime.now().timestamp())}",
            company=ticker,
            type='CONVERTIBLE_PREFERRED',  # Use valid enum value instead of custom string
            filing_date=date.today(),
            principal_amount=None,
            rate=None,
            maturity_date=None,
            issue_date=None,
            description=conversion_data.get('security_description', 'Security with exotic conversion features'),
            shares_outstanding=None,
            filing_source=filing_type,
            conversion_terms=conversion_terms,
            liquidation_terms=None,
            metrics=MetricsSummary(
                principal_amount=self._extract_single_amount(conversion_data.get('principal_amount')),
                coupon_rate=self._extract_single_percentage(conversion_data.get('interest_rate')),
                conversion_price=self._extract_single_amount(conversion_data.get('conversion_price')),
                redemption_price=None,
                earliest_redemption_date=None,
                redemption_notice_period=None,
                par_value=self._extract_single_amount(conversion_data.get('par_value')),
                shares_outstanding=self._extract_single_share_count(conversion_data.get('shares_outstanding'))
            ),
            quantitative_metrics=quantitative_metrics,
            original_data_reference=original_ref,
            llm_commentary=f"EXOTIC CONVERSION: {exotic_conversion_details}",
            has_change_control_provisions='change of control' in (conversion_data.get('security_description', '') or '').lower(),
            has_make_whole_provisions='make-whole' in (conversion_data.get('security_description', '') or '').lower()
        )
        return security
    
    def _create_trigger_events_security(self, trigger_data: Dict, ticker: str, filing_type: str) -> Optional[SecurityData]:
        """Create SecurityData for trigger event features with structured details."""
        
        # Create structured trigger event details
        trigger_event_details = {
            "trigger_type": trigger_data.get('trigger_type', 'unknown'),
            "trigger_definition": {
                "definition": trigger_data.get('trigger_definition', 'N/A'),
                "has_threshold": bool(trigger_data.get('trigger_threshold')),
                "threshold_value": trigger_data.get('trigger_threshold', 'N/A')
            },
            "resulting_actions": {
                "actions": trigger_data.get('resulting_actions', []),
                "holder_can_redeem": 'redemption_right' in trigger_data.get('resulting_actions', []),
                "holder_can_convert": 'forced_conversion' in trigger_data.get('resulting_actions', []),
                "company_obligations": trigger_data.get('company_obligations', 'N/A')
            },
            "holder_rights": {
                "description": trigger_data.get('holder_rights', 'N/A'),
                "exercise_conditions": trigger_data.get('exercise_conditions', 'N/A')
            },
            "notice_requirements": {
                "notice_periods": trigger_data.get('notice_periods', 'N/A'),
                "notification_method": "SEC filing disclosure"
            },
            "trigger_category": self._categorize_trigger_type(trigger_data.get('trigger_type', '')),
            "exact_language_sample": (trigger_data.get('exact_language', '') or '')[:200] + "..." if len(trigger_data.get('exact_language', '')) > 200 else trigger_data.get('exact_language', 'N/A')
        }
        
        # Extract quantitative metrics from trigger text
        trigger_text = f"{trigger_data.get('trigger_definition', '')} {trigger_data.get('exact_language', '')} {trigger_data.get('holder_rights', '')} {trigger_data.get('notice_periods', '')}"
        quantitative_metrics = self.quantitative_extractor.extract_quantitative_metrics(trigger_text, trigger_data.get('trigger_type', ''))
        
        # Create enhanced metrics
        metrics = MetricsSummary(
            principal_amount=None,
            coupon_rate=None,
            conversion_price=None,
            redemption_price=None,
            earliest_redemption_date=None,
            redemption_notice_period=None,
            par_value=None,
            shares_outstanding=None
        )
        
        # Create original data reference highlighting trigger events
        original_ref = OriginalDataReference(
            id=f"{ticker}_{filing_type}_trigger_events_{int(datetime.now().timestamp())}",
            has_raw_conversion_features=False,
            has_raw_redemption_features=True,  # Triggers often lead to redemption rights
            has_special_features=True,
            llm_commentary=f"TRIGGER EVENT: {trigger_data.get('trigger_type')} with {len(trigger_data.get('resulting_actions', []))} actions"
        )
        
        # Create SecurityData object focused on trigger events
        security = SecurityData(
            id=f"{ticker}_{filing_type}_trigger_events_{int(datetime.now().timestamp())}",
            company=ticker,
            type='DEBT_INSTRUMENT',  # Use valid enum value instead of custom string
            filing_date=date.today(),
            principal_amount=None,
            rate=None,
            maturity_date=None,
            issue_date=None,
            description=trigger_data.get('security_description', 'Security with trigger event features'),
            shares_outstanding=None,
            filing_source=filing_type,
            conversion_terms=None,
            liquidation_terms=None,
            metrics=metrics,
            has_make_whole_provisions=False,
            has_change_control_provisions=False,
            has_hedging=False,
            liquidation_preference=None,
            original_data_reference=original_ref,
            llm_commentary=f"TRIGGER EVENTS: {trigger_event_details}"
        )
        
        return security
    
    def _create_control_rights_security(self, control_data: Dict, ticker: str, filing_type: str) -> SecurityData:
        """Create structured SecurityData for control rights with proper field organization."""
        
        # Handle both old flat structure and new nested structure
        def safe_get_nested(data, key_path, default='N/A'):
            """Safely get nested values, handling both flat and nested structures."""
            if isinstance(key_path, str):
                return data.get(key_path, default)
            
            current = data
            for key in key_path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current
        
        # Extract ownership requirements (handle flat vs nested)
        ownership_threshold = safe_get_nested(control_data, 'ownership_threshold') or safe_get_nested(control_data, ['ownership_requirements', 'threshold'])
        
        # Extract specific rights (handle list vs nested dict)
        specific_rights_data = control_data.get('specific_rights', [])
        if isinstance(specific_rights_data, list):
            rights_list = specific_rights_data
            board_rights = [r for r in rights_list if 'board' in r.lower() or 'director' in r.lower()]
            veto_rights = [r for r in rights_list if 'veto' in r.lower() or 'consent' in r.lower()]
            info_rights = control_data.get('information_rights', [])
        else:
            # Handle nested structure
            rights_list = specific_rights_data.get('rights_list', [])
            board_rights = specific_rights_data.get('board_rights', [])
            veto_rights = specific_rights_data.get('veto_rights', [])
            info_rights = specific_rights_data.get('information_rights', [])
        
        # Create structured control rights details
        control_rights_details = {
            "rights_type": control_data.get('rights_type', 'unknown'),
            "ownership_requirements": {
                "threshold": ownership_threshold,
                "threshold_type": self._parse_threshold_type(ownership_threshold),
                "exercise_conditions": control_data.get('exercise_conditions', 'N/A')
            },
            "specific_rights": {
                "board_rights": board_rights,
                "veto_rights": veto_rights,
                "information_rights": info_rights if isinstance(info_rights, list) else [info_rights] if info_rights else [],
                "rights_list": rights_list
            },
            "voting_mechanics": {
                "description": control_data.get('voting_mechanics', 'N/A'),
                "approval_thresholds": control_data.get('approval_thresholds', 'N/A')
            },
            "protective_provisions": {
                "provisions": control_data.get('protective_provisions', []),
                "material_transaction_approval": 'material' in str(control_data.get('protective_provisions', [])).lower(),
                "dividend_approval": 'dividend' in str(control_data.get('protective_provisions', [])).lower()
            },
            "control_category": self._categorize_control_rights_type(control_data.get('rights_type', '')),
            "has_board_control": bool(board_rights),
            "has_veto_powers": bool(veto_rights),
            "requires_ownership_threshold": 'threshold' in str(ownership_threshold).lower() or '%' in str(ownership_threshold),
            "exact_language_sample": (control_data.get('exact_language', '') or control_data.get('exact_language_sample', ''))[:200] + "..." if len(control_data.get('exact_language', '') or control_data.get('exact_language_sample', '')) > 200 else control_data.get('exact_language', '') or control_data.get('exact_language_sample', 'N/A')
        }
        
        # Create original data reference
        original_ref = OriginalDataReference(
            cusip_or_id=f"{ticker}_{filing_type}_control_rights_{hash(str(control_data)) & 0x7fffffff}",
            has_conversion_features=False,
            has_redemption_features=False,
            has_special_features=True,
            details=f"CONTROL RIGHTS: {control_data.get('rights_type', 'unknown')} at {ownership_threshold} threshold"
        )
        
        # Create the security with structured control rights details
        security = SecurityData(
            id=f"{ticker}_{filing_type}_control_{hash(str(control_data)) & 0x7fffffff}",
            company=ticker,
            type='ControlRightsSecurities',
            description=control_data.get('security_description', 'Common Stock'),
            cusip='N/A',
            trading_symbol='N/A',
            filing_date=datetime.now().strftime('%Y-%m-%d'),
            filing_source=filing_type,
            original_data_reference=original_ref,
            llm_commentary=f"CONTROL RIGHTS: {control_rights_details}" # Structured details in commentary
        )
        
        return security
    
    def _categorize_control_rights_type(self, rights_type: str) -> str:
        """Categorize control rights into high-level categories."""
        rights_type_lower = rights_type.lower()
        
        if 'board' in rights_type_lower or 'director' in rights_type_lower or 'nomination' in rights_type_lower:
            return 'board_control'
        elif 'veto' in rights_type_lower or 'consent' in rights_type_lower or 'approval' in rights_type_lower:
            return 'veto_powers'
        elif 'voting' in rights_type_lower or 'written_consent' in rights_type_lower:
            return 'voting_control'
        elif 'meeting' in rights_type_lower or 'special_meeting' in rights_type_lower:
            return 'meeting_control'
        elif 'information' in rights_type_lower or 'access' in rights_type_lower:
            return 'information_rights'
        else:
            return 'other_control'
    
    def _parse_threshold_type(self, threshold: str) -> str:
        """Parse threshold string to determine threshold type."""
        if not threshold or threshold == 'N/A':
            return 'unknown'
        
        threshold_lower = str(threshold).lower()
        if '%' in threshold_lower or 'percent' in threshold_lower:
            return 'percentage'
        elif 'majority' in threshold_lower or 'supermajority' in threshold_lower:
            return 'majority'
        elif 'agreement' in threshold_lower or 'contract' in threshold_lower:
            return 'contractual'
        elif 'shares' in threshold_lower or 'voting' in threshold_lower:
            return 'voting_power'
        else:
            return 'other'
    
    def _create_exotic_payments_security(self, payment_data: Dict, ticker: str, filing_type: str) -> Optional[SecurityData]:
        """Create SecurityData for exotic payment features with structured details."""
        
        # Create enhanced metrics
        metrics = MetricsSummary(
            principal_amount=None,
            coupon_rate=None,
            conversion_price=None,
            redemption_price=None,
            earliest_redemption_date=None,
            redemption_notice_period=None,
            par_value=None,
            shares_outstanding=None
        )
        
        # Create structured exotic payment details
        exotic_payment_details = {
            "payment_type": payment_data.get('payment_type', 'unknown'),
            "exotic_mechanism": {
                "description": payment_data.get('exotic_mechanism', 'N/A'),
                "has_election_mechanism": bool(payment_data.get('election_mechanism')),
                "election_mechanism": payment_data.get('election_mechanism', 'N/A')
            },
            "rate_schedule": {
                "formula": payment_data.get('payment_formula', 'N/A'),
                "is_step_up": 'step-up' in str(payment_data.get('rate_schedule', '')).lower(),
                "performance_metrics": payment_data.get('performance_metrics', []),
                "payment_priority": payment_data.get('payment_priority', 'N/A'),
                "contingent_triggers": payment_data.get('contingent_triggers', [])
            },
            "performance_metrics": payment_data.get('performance_metrics', []),
            "exact_language_sample": (payment_data.get('exact_language', '') or '')[:200] + "..." if len(payment_data.get('exact_language', '')) > 200 else payment_data.get('exact_language', 'N/A')
        }
        
        # Create original data reference highlighting exotic payments
        original_ref = OriginalDataReference(
            id=f"{ticker}_{filing_type}_exotic_payments_{int(datetime.now().timestamp())}",
            has_raw_conversion_features=False,
            has_raw_redemption_features=False,
            has_special_features=True,
            llm_commentary=f"EXOTIC PAYMENTS: {payment_data.get('payment_type')} with {len(payment_data.get('performance_metrics', []))} metrics"
        )
        
        # Create SecurityData object focused on exotic payments
        security = SecurityData(
            id=f"{ticker}_{filing_type}_exotic_payment_{int(datetime.now().timestamp())}",
            company=ticker,
            type='PREFERRED_STOCK',  # Use valid enum value instead of custom string
            filing_date=date.today(),
            principal_amount=None,
            rate=None,
            maturity_date=None,
            issue_date=None,
            description=payment_data.get('security_description', 'Security with exotic payment features'),
            shares_outstanding=None,
            filing_source=filing_type,
            conversion_terms=None,
            liquidation_terms=None,
            metrics=metrics,
            has_make_whole_provisions=False,
            has_change_control_provisions=False,
            has_hedging=False,
            liquidation_preference=None,
            original_data_reference=original_ref,
            llm_commentary=f"EXOTIC PAYMENTS: {exotic_payment_details}"
        )
        
        return security
    
    def _create_performance_milestones_security(self, milestone_data: Dict, ticker: str, filing_type: str) -> Optional[SecurityData]:
        """Create SecurityData for performance milestone features with structured details."""
        
        # Create enhanced metrics
        metrics = MetricsSummary(
            principal_amount=None,
            coupon_rate=None,
            conversion_price=None,
            redemption_price=None,
            earliest_redemption_date=None,
            redemption_notice_period=None,
            par_value=None,
            shares_outstanding=None
        )
        
        # Create structured performance milestone details
        performance_milestone_details = {
            "milestone_type": milestone_data.get('milestone_type', 'unknown'),
            "milestone_definition": {
                "definition": milestone_data.get('milestone_definition', 'N/A'),
                "performance_metrics": milestone_data.get('performance_metrics', []),
                "achievement_thresholds": milestone_data.get('achievement_thresholds', 'N/A'),
                "measurement_period": milestone_data.get('measurement_period', 'N/A'),
                "earnout_mechanism": milestone_data.get('earnout_mechanism', 'N/A')
            },
            "resulting_actions": milestone_data.get('resulting_actions', []),
            "milestone_timeline": milestone_data.get('milestone_timeline', 'N/A'),
            "exact_language_sample": (milestone_data.get('exact_language', '') or '')[:200] + "..." if len(milestone_data.get('exact_language', '')) > 200 else milestone_data.get('exact_language', 'N/A')
        }
        
        # Create original data reference highlighting performance milestones
        original_ref = OriginalDataReference(
            id=f"{ticker}_{filing_type}_performance_milestones_{int(datetime.now().timestamp())}",
            has_raw_conversion_features=False,
            has_raw_redemption_features=False,
            has_special_features=True,
            llm_commentary=f"PERFORMANCE MILESTONE: {milestone_data.get('milestone_type')} with {len(milestone_data.get('performance_metrics', []))} metrics"
        )
        
        # Create SecurityData object focused on performance milestones
        security = SecurityData(
            id=f"{ticker}_{filing_type}_performance_milestone_{int(datetime.now().timestamp())}",
            company=ticker,
            type='PREFERRED_STOCK',  # Use valid enum value instead of custom string
            filing_date=date.today(),
            principal_amount=None,
            rate=None,
            maturity_date=None,
            issue_date=None,
            description=milestone_data.get('security_description', 'Security with performance milestone features'),
            shares_outstanding=None,
            filing_source=filing_type,
            conversion_terms=None,
            liquidation_terms=None,
            metrics=metrics,
            has_make_whole_provisions=False,
            has_change_control_provisions=False,
            has_hedging=False,
            liquidation_preference=None,
            original_data_reference=original_ref,
            llm_commentary=f"PERFORMANCE MILESTONES: {performance_milestone_details}"
        )
        
        return security
    
    def _create_credit_regulatory_triggers_security(self, trigger_data: Dict, ticker: str, filing_type: str) -> Optional[SecurityData]:
        """Create SecurityData for credit and regulatory trigger features with structured details."""
        
        # Create enhanced metrics
        metrics = MetricsSummary(
            principal_amount=None,
            coupon_rate=None,
            conversion_price=None,
            redemption_price=None,
            earliest_redemption_date=None,
            redemption_notice_period=None,
            par_value=None,
            shares_outstanding=None
        )
        
        # Create structured credit/regulatory trigger details
        credit_regulatory_trigger_details = {
            "trigger_type": trigger_data.get('trigger_type', 'unknown'),
            "trigger_definition": {
                "definition": trigger_data.get('trigger_definition', 'N/A'),
                "rating_thresholds": trigger_data.get('rating_thresholds', 'N/A'),
                "financial_covenants": trigger_data.get('financial_covenants', 'N/A'),
                "regulatory_body": trigger_data.get('regulatory_body', 'N/A'),
                "cure_periods": trigger_data.get('cure_periods', 'N/A'),
                "enforcement_mechanisms": trigger_data.get('enforcement_mechanisms', 'N/A')
            },
            "resulting_actions": trigger_data.get('resulting_actions', []),
            "exact_language_sample": (trigger_data.get('exact_language', '') or '')[:200] + "..." if len(trigger_data.get('exact_language', '')) > 200 else trigger_data.get('exact_language', 'N/A')
        }
        
        # Create original data reference highlighting credit/regulatory triggers
        original_ref = OriginalDataReference(
            id=f"{ticker}_{filing_type}_credit_regulatory_triggers_{int(datetime.now().timestamp())}",
            has_raw_conversion_features=False,
            has_raw_redemption_features=False,
            has_special_features=True,
            llm_commentary=f"CREDIT/REGULATORY TRIGGER: {trigger_data.get('trigger_type')} with {len(trigger_data.get('resulting_actions', []))} actions"
        )
        
        # Create SecurityData object focused on credit/regulatory triggers
        security = SecurityData(
            id=f"{ticker}_{filing_type}_credit_regulatory_trigger_{int(datetime.now().timestamp())}",
            company=ticker,
            type='DEBT_INSTRUMENT',  # Use valid enum value instead of custom string
            filing_date=date.today(),
            principal_amount=None,
            rate=None,
            maturity_date=None,
            issue_date=None,
            description=trigger_data.get('security_description', 'Security with credit/regulatory trigger features'),
            shares_outstanding=None,
            filing_source=filing_type,
            conversion_terms=None,
            liquidation_terms=None,
            metrics=metrics,
            has_make_whole_provisions=False,
            has_change_control_provisions=False,
            has_hedging=False,
            liquidation_preference=None,
            original_data_reference=original_ref,
            llm_commentary=f"CREDIT/REGULATORY TRIGGERS: {credit_regulatory_trigger_details}"
        )
        
        return security
    
    def _categorize_trigger(self, trigger_text: str) -> str:
        """Categorize trigger condition into standard types."""
        trigger_lower = trigger_text.lower()
        if 'delist' in trigger_lower:
            return 'delisting_event'
        elif 'change of control' in trigger_lower or 'acquisition' in trigger_lower:
            return 'change_of_control'
        elif 'rating' in trigger_lower:
            return 'credit_rating'
        elif 'performance' in trigger_lower or 'milestone' in trigger_lower:
            return 'performance_trigger'
        elif 'dividend' in trigger_lower:
            return 'dividend_trigger'
        else:
            return 'other'
    
    def _categorize_trigger_type(self, trigger_type: str) -> str:
        """Categorize trigger type into broader categories."""
        type_lower = trigger_type.lower()
        if 'delist' in type_lower:
            return 'market_event'
        elif 'corporate' in type_lower or 'control' in type_lower:
            return 'corporate_action'
        elif 'credit' in type_lower or 'rating' in type_lower:
            return 'financial_event'
        elif 'regulatory' in type_lower:
            return 'regulatory_event'
        elif 'performance' in type_lower:
            return 'performance_event'
        else:
            return 'other'
    
    def _parse_threshold_type(self, threshold: str) -> str:
        """Parse ownership threshold to determine type."""
        if '%' in threshold:
            return 'percentage'
        elif '$' in threshold or 'million' in threshold.lower():
            return 'dollar_amount'
        elif 'shares' in threshold.lower():
            return 'share_count'
        else:
            return 'other'
    
    def _create_standard_security_data(self, sec_data: Dict, ticker: str, filing_type: str) -> Optional[SecurityData]:
        """Fallback method for standard securities data (original logic)."""
        
        # This preserves the original _create_security_data logic for backward compatibility
        # when processing standard (non-exotic) securities
        
        try:
            # Parse date safely
            def safe_date(date_str):
                if not date_str:
                    return None
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except:
                    return None
            
            # Extract basic security info
            xbrl_concept = sec_data.get('xbrl_concept', 'OtherSecurities')
            cusip = sec_data.get('cusip', 'N/A')
            
            # Create basic metrics
            metrics = MetricsSummary(
                principal_amount=sec_data.get('principal_amount'),
                coupon_rate=sec_data.get('interest_rate'),
                conversion_price=None,
                redemption_price=None,
                earliest_redemption_date=None,
                redemption_notice_period=None,
                par_value=sec_data.get('par_value'),
                shares_outstanding=sec_data.get('outstanding_amount')
            )
            
            # Create original data reference
            original_ref = OriginalDataReference(
                id=cusip if cusip != 'N/A' else f"{ticker}_security",
                has_raw_conversion_features=False,
                has_raw_redemption_features=False,
                has_special_features=False,
                llm_commentary=f"Standard security: {sec_data.get('description', 'N/A')}"
            )
            
            # Create basic SecurityData object
            security = SecurityData(
                id=cusip if cusip != 'N/A' else f"{ticker}_{filing_type}_{int(datetime.now().timestamp())}",
                company=ticker,
                type=xbrl_concept,
                filing_date=safe_date(sec_data.get('issue_date')) or date.today(),
                principal_amount=sec_data.get('principal_amount'),
                rate=sec_data.get('interest_rate'),
                maturity_date=safe_date(sec_data.get('maturity_date')),
                issue_date=safe_date(sec_data.get('issue_date')),
                description=sec_data.get('description', ''),
                shares_outstanding=sec_data.get('outstanding_amount'),
                filing_source=filing_type,
                conversion_terms=None,
                liquidation_terms=None,
                metrics=metrics,
                has_make_whole_provisions=False,
                has_change_control_provisions=False,
                has_hedging=False,
                liquidation_preference=None,
                original_data_reference=original_ref,
                llm_commentary=f"Standard security from {filing_type}"
            )
            
            return security
            
        except Exception as e:
            logger.error(f"Error creating standard security: {e}")
            return None
    
    def _save_results(self, ticker: str, securities: List[SecurityData]) -> None:
        """Save enhanced results to JSON file."""
        
        output_file = f"output/{ticker}_securities_features.json"
        
        # Convert to enhanced dict format
        securities_dict = []
        for security in securities:
            # Extract detailed conversion terms
            conversion_dict = None
            if security.conversion_terms:
                conversion_dict = {
                    # Basic conversion info
                    "conversion_price": security.conversion_terms.conversion_price,
                    "conversion_ratio": security.conversion_terms.conversion_ratio,
                    "has_auto_conversion": security.conversion_terms.has_auto_conversion,
                    "vwap_based": security.conversion_terms.vwap_based,
                    "price_floor": security.conversion_terms.price_floor,
                    "price_ceiling": security.conversion_terms.price_ceiling,
                    
                    # Enhanced conversion mechanism
                    "conversion_type": security.conversion_terms.conversion_type,
                    "is_conditional_conversion": security.conversion_terms.is_conditional_conversion,
                    "conversion_triggers": security.conversion_terms.conversion_triggers,
                    "is_variable_conversion": security.conversion_terms.is_variable_conversion,
                    "liquidation_preference_per_share": security.conversion_terms.liquidation_preference_per_share,
                    "variable_conversion_formula": security.conversion_terms.variable_conversion_formula,
                    
                    # Share cap information  
                    "has_share_cap": security.conversion_terms.has_share_cap,
                    "share_cap_maximum": security.conversion_terms.share_cap_maximum,
                    "share_cap_calculation": security.conversion_terms.share_cap_calculation,
                    
                    # Evaluable model for frontend/backend computation
                    "payoff_model": security.conversion_terms.payoff_model
                }
            
            # Extract liquidation terms
            liquidation_dict = None
            if security.liquidation_terms:
                liquidation_dict = {
                    "liquidation_preference_per_share": security.liquidation_terms.liquidation_preference_per_share,
                    "liquidation_preference_total": security.liquidation_terms.liquidation_preference_total,
                    "liquidation_ranking": security.liquidation_terms.liquidation_ranking,
                    "liquidation_multiple": security.liquidation_terms.liquidation_multiple,
                    "is_participating": security.liquidation_terms.is_participating,
                    "participation_cap": security.liquidation_terms.participation_cap,
                    "includes_accrued_dividends": security.liquidation_terms.includes_accrued_dividends,
                    "dividend_calculation_method": security.liquidation_terms.dividend_calculation_method
                }
            
            # Extract detailed metrics
            metrics_dict = None
            if security.metrics:
                metrics_dict = {
                    "principal_amount": security.metrics.principal_amount,
                    "coupon_rate": security.metrics.coupon_rate,
                    "conversion_price": security.metrics.conversion_price,
                    "redemption_price": security.metrics.redemption_price,
                    "earliest_redemption_date": security.metrics.earliest_redemption_date.isoformat() if security.metrics.earliest_redemption_date else None,
                    "redemption_notice_period": security.metrics.redemption_notice_period,
                    "par_value": security.metrics.par_value,
                    "shares_outstanding": security.metrics.shares_outstanding
                }
            
            # Extract enhanced original data reference
            original_ref_dict = None
            if security.original_data_reference:
                original_ref_dict = {
                    "cusip_or_id": security.original_data_reference.id,
                    "has_conversion_features": security.original_data_reference.has_raw_conversion_features,
                    "has_redemption_features": security.original_data_reference.has_raw_redemption_features,
                    "has_special_features": security.original_data_reference.has_special_features,
                    "details": security.original_data_reference.llm_commentary
                }
            
            # Extract trading symbol and CUSIP from llm_commentary if available
            trading_symbol = "N/A"
            cusip = "N/A"
            if security.llm_commentary:
                import re
                symbol_match = re.search(r'Trading Symbol: ([A-Z\s]+?)\.', security.llm_commentary)
                if symbol_match:
                    trading_symbol = symbol_match.group(1).strip()
                cusip_match = re.search(r'CUSIP: ([A-Z0-9]+)', security.llm_commentary)
                if cusip_match:
                    cusip = cusip_match.group(1).strip()
            
            sec_dict = {
                "id": security.id,
                "company": security.company,
                "xbrl_concept": security.type,
                "description": security.description,
                "cusip": cusip,
                "trading_symbol": trading_symbol,
                "principal_amount": security.principal_amount,
                "outstanding_amount": security.shares_outstanding,
                "interest_rate": security.rate,
                "issue_date": security.issue_date.isoformat() if security.issue_date else None,
                "maturity_date": security.maturity_date.isoformat() if security.maturity_date else None,
                "filing_date": security.filing_date.isoformat() if security.filing_date else None,
                "liquidation_preference": security.liquidation_preference,
                "liquidation_terms": liquidation_dict,
                "conversion_terms": conversion_dict,
                "financial_metrics": metrics_dict,
                "special_provisions": {
                    "has_change_control": security.has_change_control_provisions,
                    "has_make_whole": security.has_make_whole_provisions,
                    "has_hedging_sinking_fund": security.has_hedging
                },
                "filing_source": security.filing_source,
                "original_data_reference": original_ref_dict,
                "extraction_commentary": security.llm_commentary,
                "is_convertible": bool(security.conversion_terms),
                "security_validation": {
                    "has_cusip": cusip != "N/A" and cusip != "None",
                    "has_trading_symbol": trading_symbol != "N/A" and trading_symbol != "None",
                    "has_maturity_date": security.maturity_date is not None,
                    "conversion_terms_appropriate": self._validate_conversion_assignment(security)
                }
            }
            securities_dict.append(sec_dict)
        
        # Create enhanced summary with XBRL breakdown
        xbrl_types = {}
        special_features_count = {
            "change_of_control": 0,
            "make_whole": 0,
            "convertible": 0,
            "callable": 0
        }
        
        # Count trading symbols and CUSIPs found
        symbols_found = 0
        cusips_found = 0
        
        for security in securities:
            # Count XBRL types
            xbrl_type = security.type
            xbrl_types[xbrl_type] = xbrl_types.get(xbrl_type, 0) + 1
            
            # Count special features
            if security.has_change_control_provisions:
                special_features_count["change_of_control"] += 1
            if security.has_make_whole_provisions:
                special_features_count["make_whole"] += 1
            if security.conversion_terms:
                special_features_count["convertible"] += 1
            if security.metrics and security.metrics.redemption_price:
                special_features_count["callable"] += 1
            
            # Count symbols and CUSIPs
            if security.llm_commentary and "Trading Symbol:" in security.llm_commentary and "N/A" not in security.llm_commentary.split("Trading Symbol:")[1].split(".")[0]:
                symbols_found += 1
            if security.original_data_reference and security.original_data_reference.id and len(security.original_data_reference.id) >= 8:
                cusips_found += 1
        
        # Save enhanced results
        result = {
            "ticker": ticker,
            "extraction_date": datetime.now().isoformat(),
            "total_securities": len(securities),
            "xbrl_breakdown": xbrl_types,
            "special_features_summary": special_features_count,
            "data_quality_metrics": {
                "cusips_found": cusips_found,
                "trading_symbols_found": symbols_found,
                "conversion_details_captured": special_features_count["convertible"],
                "redemption_details_captured": special_features_count["callable"]
            },
            "securities": securities_dict
        }
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"Enhanced securities features saved to: {output_file}")
        logger.info(f"XBRL breakdown: {xbrl_types}")
        logger.info(f"Special features: {special_features_count}")
        logger.info(f"Data quality: {cusips_found} CUSIPs, {symbols_found} trading symbols found")

    def _validate_conversion_assignment(self, security: SecurityData) -> bool:
        """Validate that conversion terms are only assigned to appropriate security types."""
        
        # If no conversion terms, always valid
        if not security.conversion_terms:
            return True
            
        # Conversion terms should only be on these security types
        valid_convertible_types = [
            'ConvertibleDebtSecurities',
            'PreferredStockIncludingAdditionalPaidInCapital'
        ]
        
        # Check if security type is appropriate for conversion terms
        is_valid = security.type in valid_convertible_types
        
        if not is_valid:
            logger.warning(f"Invalid conversion assignment: {security.type} should not have conversion terms")
            
        return is_valid
    
    def _extract_single_amount(self, text: str) -> Optional[float]:
        """Extract the first amount from text, return None if not found."""
        if not text:
            return None
        amounts = self.text_extractor.extract_amounts(str(text))
        return amounts[0] if amounts else None
    
    def _extract_single_percentage(self, text: str) -> Optional[float]:
        """Extract the first percentage from text, return None if not found.""" 
        if not text:
            return None
        percentages = self.text_extractor.extract_percentages(str(text))
        return percentages[0] if percentages else None
        
    def _extract_single_date(self, text: str) -> Optional[str]:
        """Extract the first date from text, return None if not found."""
        if not text:
            return None
        dates = self.text_extractor.extract_dates(str(text))
        return dates[0] if dates else None
        
    def _extract_single_share_count(self, text: str) -> Optional[int]:
        """Extract the first share count from text, return None if not found."""
        if not text:
            return None
        counts = self.text_extractor.extract_share_counts(str(text))
        return counts[0] if counts else None
    
    def _create_conversion_terms_from_data(self, conversion_data: Dict) -> Optional[ConversionTerms]:
        """Create conversion terms from extracted data."""
        try:
            # Extract formula and create basic conversion terms
            formula = conversion_data.get('conversion_formula')
            if isinstance(formula, dict):
                formula_text = formula.get('formula', '')
            elif isinstance(formula, str):
                formula_text = formula
            else:
                formula_text = str(conversion_data.get('adjustment_formula', '') or '')

            # Build evaluable payoff model for performance-based structured notes
            payoff_model = None
            conv_type = conversion_data.get('conversion_type') or conversion_data.get('type')
            mech_desc = (conversion_data.get('mechanism_description', '') or '') + ' ' + (conversion_data.get('exotic_mechanism', '') or '')
            triggers = conversion_data.get('trigger_conditions', []) or []

            # Try to derive parameters from text when available
            buffer_pct = self._extract_single_percentage(mech_desc) or None
            # Try to detect leverage like "1.95" near "Upside Leverage"
            leverage = None
            try:
                m = re.search(r"(Upside\s+Leverage\s+Factor\s*[:=]?\s*)(\d+(?:\.\d+)?)", mech_desc, re.IGNORECASE)
                if m:
                    leverage = float(m.group(2))
            except Exception:
                pass

            if conv_type and 'performance' in str(conv_type).lower():
                payoff_model = {
                    "modelType": "piecewise",
                    "inputs": [
                        {"name": "finalIndex", "type": "number"},
                        {"name": "initialIndex", "type": "number"}
                    ],
                    "parameters": {
                        "principal": 1000,
                        "buffer": (buffer_pct or 30.0) / 100.0 if (buffer_pct and buffer_pct > 1) else (buffer_pct if buffer_pct else 0.30),
                        "leverage": leverage or 1.95
                    },
                    "pieces": [
                        {
                            "when": "finalIndex > initialIndex",
                            "formula": "principal * (1 + leverage * (finalIndex/initialIndex - 1))",
                            "outputs": [{"name": "payoff", "unit": "USD"}]
                        },
                        {
                            "when": "finalIndex >= initialIndex * (1 - buffer) && finalIndex <= initialIndex",
                            "formula": "principal * (1 + abs(finalIndex/initialIndex - 1))",
                            "outputs": [{"name": "payoff", "unit": "USD"}]
                        },
                        {
                            "when": "finalIndex < initialIndex * (1 - buffer)",
                            "formula": "principal * (1 + (finalIndex/initialIndex - 1 + buffer))",
                            "outputs": [{"name": "payoff", "unit": "USD"}]
                        }
                    ],
                    "constraints": {"min": 0, "max": None},
                    "display": {"name": "Dual-directional buffered payout", "primaryUnit": "USD"}
                }

            return ConversionTerms(
                conversion_price=None,
                conversion_ratio=None,
                has_auto_conversion=False,
                vwap_based=False,
                price_floor=None,
                price_ceiling=None,
                conversion_type=conversion_data.get('conversion_type', conversion_data.get('type', 'exotic')),
                is_conditional_conversion=True,
                conversion_triggers=conversion_data.get('trigger_conditions', []),
                is_variable_conversion=True,
                liquidation_preference_per_share=None,
                variable_conversion_formula=formula_text,
                has_share_cap=False,
                share_cap_maximum=None,
                share_cap_calculation=None,
                payoff_model=payoff_model
            )
        except Exception as e:
            logger.error(f"Error creating conversion terms: {e}")
            return None

    def create_standardized_metrics(self, security_data: SecurityData) -> Optional[StandardizedSecurityMetrics]:
        """Convert complex extracted data into clean, standardized format for frontend/API consumption."""
        
        formulas = []
        
        # Process quantitative metrics if available
        if security_data.quantitative_metrics:
            qm = security_data.quantitative_metrics
            
            # Extract VWAP formulas
            if qm.vwap_metrics:
                vwap = qm.vwap_metrics
                if vwap.vwap_threshold_percentage:
                    formulas.append(FormulaDisplayMetrics(
                        formula_category="vwap",
                        formula_type="threshold_trigger",
                        display_name=f"{vwap.vwap_threshold_percentage}% VWAP Trigger",
                        description=f"Stock price must exceed {vwap.vwap_threshold_percentage}% of conversion price for {vwap.vwap_threshold_days or 'specified'} trading days",
                        primary_value=vwap.vwap_threshold_percentage,
                        primary_unit="percent",
                        secondary_value=float(vwap.vwap_threshold_days) if vwap.vwap_threshold_days else None,
                        secondary_unit="trading_days",
                        time_period_days=vwap.vwap_threshold_days,
                        time_period_type="trading_days",
                        mathematical_operator="greater_than",
                        comparison_values=[vwap.vwap_threshold_percentage],
                        is_threshold=True,
                        is_timing=True,
                        tags=["trigger", "conversion", "vwap", "threshold"]
                    ))
                
                if vwap.vwap_period_days:
                    formulas.append(FormulaDisplayMetrics(
                        formula_category="vwap",
                        formula_type="averaging_period",
                        display_name=f"{vwap.vwap_period_days}-Day VWAP Pricing",
                        description=f"Pricing based on {vwap.vwap_period_days}-day volume weighted average price",
                        primary_value=float(vwap.vwap_period_days),
                        primary_unit="days",
                        time_period_days=vwap.vwap_period_days,
                        time_period_type="trading_days",
                        is_pricing=True,
                        tags=["pricing", "vwap", "averaging"]
                    ))
            
            # Extract Min/Max formulas
            if qm.min_max_formulas:
                mm = qm.min_max_formulas
                formulas.append(FormulaDisplayMetrics(
                    formula_category="min_max",
                    formula_type=mm.formula_type,
                    display_name=f"{mm.formula_type.replace('_', ' ').title()} Calculation",
                    description=f"Payment calculated as {mm.formula_type} of multiple components",
                    mathematical_operator=mm.formula_type,
                    source_text=mm.original_formula,
                    is_pricing=True,
                    tags=["pricing", "calculation", mm.formula_type]
                ))
            
            # Extract Anti-dilution formulas
            if qm.anti_dilution_metrics:
                ad = qm.anti_dilution_metrics
                formulas.append(FormulaDisplayMetrics(
                    formula_category="anti_dilution",
                    formula_type=ad.adjustment_type or "unknown",
                    display_name=f"{ad.adjustment_type or 'Anti-Dilution'} Protection".replace('_', ' ').title(),
                    description=f"Conversion terms adjust using {ad.adjustment_type or 'anti-dilution'} method with {ad.scope or 'standard'} scope",
                    is_threshold=True,
                    tags=["protection", "anti_dilution", "conversion"]
                ))
            
            # Extract Floating rate formulas
            if qm.floating_rate_metrics:
                fr = qm.floating_rate_metrics
                spread_text = ""
                if fr.spread_percentage:
                    spread_text = f" {'+' if fr.spread_percentage >= 0 else ''}{fr.spread_percentage}%"
                elif fr.spread_bps:
                    spread_text = f" {'+' if fr.spread_bps >= 0 else ''}{fr.spread_bps} bps"
                
                formulas.append(FormulaDisplayMetrics(
                    formula_category="floating_rate",
                    formula_type="interest_calculation",
                    display_name=f"{fr.base_rate or 'Floating'} Rate{spread_text}",
                    description=f"Interest rate based on {fr.base_rate or 'floating rate'}{spread_text}",
                    primary_value=fr.spread_percentage or (fr.spread_bps / 100 if fr.spread_bps else None),
                    primary_unit="percent",
                    is_pricing=True,
                    tags=["interest", "floating_rate", fr.base_rate.lower() if fr.base_rate else "floating"]
                ))
            
            # Extract Cashless exercise formulas
            if qm.cashless_exercise_metrics:
                ce = qm.cashless_exercise_metrics
                formulas.append(FormulaDisplayMetrics(
                    formula_category="cashless_exercise",
                    formula_type=ce.exercise_type,
                    display_name="Cashless Exercise Formula",
                    description="Net shares calculated based on fair market value minus exercise price",
                    source_text=ce.net_share_formula or "",
                    is_pricing=True,
                    tags=["exercise", "cashless", "calculation"]
                ))
        
        # Determine complexity score
        complexity_score = "low"
        if len(formulas) > 5:
            complexity_score = "high"
        elif len(formulas) > 2:
            complexity_score = "medium"
        
        # Get unique categories
        formula_categories = list(set(f.formula_category for f in formulas))
        
        # Determine risk indicators
        has_trigger_conditions = any(f.is_threshold for f in formulas)
        has_variable_pricing = any(f.is_pricing for f in formulas)
        has_conversion_features = any("conversion" in f.tags for f in formulas)
        
        return StandardizedSecurityMetrics(
            security_id=security_data.id,
            security_name=security_data.description,
            security_type=self._classify_security_type(security_data),
            principal_amount=security_data.principal_amount,
            interest_rate=security_data.interest_rate,
            maturity_date=security_data.maturity_date.isoformat() if security_data.maturity_date else None,
            formulas=formulas,
            total_formulas=len(formulas),
            formula_categories=formula_categories,
            complexity_score=complexity_score,
            has_trigger_conditions=has_trigger_conditions,
            has_variable_pricing=has_variable_pricing,
            has_conversion_features=has_conversion_features,
            last_updated=datetime.now().isoformat(),
            data_quality_score=0.9  # Based on successful extraction
        )
    
    def _classify_security_type(self, security_data: SecurityData) -> str:
        """Classify security type for standardized display."""
        desc = security_data.description.lower()
        if "convertible" in desc and "bond" in desc:
            return "convertible_bond"
        elif "convertible" in desc and "preferred" in desc:
            return "convertible_preferred"
        elif "preferred" in desc:
            return "preferred_stock"
        elif "warrant" in desc:
            return "warrant"
        elif "note" in desc:
            return "note"
        else:
            return "other_security"

class QuantitativeExtractor:
    """Extract specific numerical values and metrics from securities text."""
    
    def __init__(self):
        # Regex patterns for common numerical extractions
        self.percentage_pattern = r'(\d+(?:\.\d+)?)\s*%'
        self.dollar_pattern = r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)'
        self.million_pattern = r'\$?(\d+(?:\.\d+)?)\s*(?:million|M)'
        self.billion_pattern = r'\$?(\d+(?:\.\d+)?)\s*(?:billion|B)'
        self.days_pattern = r'(\d+)\s*days?'
        self.months_pattern = r'(\d+)\s*months?'
        self.years_pattern = r'(\d+)\s*years?'
        self.ratio_pattern = r'(\d+(?:\.\d+)?)\s*(?:to|:)\s*(\d+(?:\.\d+)?)'
        self.share_count_pattern = r'(\d+(?:,\d{3})*)\s*shares?'
        self.interest_rate_pattern = r'(\d+(?:\.\d+)?)\s*%.*?(?:interest|coupon|rate)'
        
    def extract_quantitative_metrics(self, text: str, description: str = "") -> QuantitativeMetrics:
        """Extract comprehensive quantitative metrics from text."""
        
        financial_metrics = self._extract_financial_metrics(text)
        ownership_metrics = self._extract_ownership_metrics(text)
        time_metrics = self._extract_time_metrics(text)
        trigger_metrics = self._extract_trigger_metrics(text)
        control_metrics = self._extract_control_metrics(text)
        
        # Parse mathematical formulas
        formula_components = self._parse_formulas(text)
        structured_product_metrics = self._extract_structured_product_metrics(text)
        conversion_metrics = self._extract_conversion_metrics(text)
        
        # Parse additional formula types
        vwap_metrics = self._extract_vwap_metrics(text)
        min_max_formulas = self._extract_min_max_formulas(text)
        anti_dilution_metrics = self._extract_anti_dilution_metrics(text)
        floating_rate_metrics = self._extract_floating_rate_metrics(text)
        cashless_exercise_metrics = self._extract_cashless_exercise_metrics(text)
        
        return QuantitativeMetrics(
            financial_metrics=financial_metrics,
            ownership_metrics=ownership_metrics,
            time_metrics=time_metrics,
            trigger_metrics=trigger_metrics,
            control_metrics=control_metrics,
            formula_components=formula_components,
            structured_product_metrics=structured_product_metrics,
            conversion_metrics=conversion_metrics,
            vwap_metrics=vwap_metrics,
            min_max_formulas=min_max_formulas,
            anti_dilution_metrics=anti_dilution_metrics,
            floating_rate_metrics=floating_rate_metrics,
            cashless_exercise_metrics=cashless_exercise_metrics
        )
    
    def _extract_financial_metrics(self, text: str) -> Dict:
        """Extract financial amounts, rates, and ratios."""
        metrics = {}
        
        # Extract interest rates
        interest_rates = []
        for match in re.finditer(self.interest_rate_pattern, text, re.IGNORECASE):
            rate = float(match.group(1))
            interest_rates.append(rate)
        if interest_rates:
            metrics['interest_rates'] = interest_rates
            metrics['average_interest_rate'] = sum(interest_rates) / len(interest_rates)
        
        # Extract dollar amounts
        dollar_amounts = []
        for match in re.finditer(self.dollar_pattern, text):
            amount = float(match.group(1).replace(',', ''))
            dollar_amounts.append(amount)
        if dollar_amounts:
            metrics['dollar_amounts'] = dollar_amounts
        
        # Extract millions
        millions = []
        for match in re.finditer(self.million_pattern, text, re.IGNORECASE):
            amount = float(match.group(1)) * 1_000_000
            millions.append(amount)
        if millions:
            metrics['million_amounts'] = millions
            
        # Extract billions
        billions = []
        for match in re.finditer(self.billion_pattern, text, re.IGNORECASE):
            amount = float(match.group(1)) * 1_000_000_000
            billions.append(amount)
        if billions:
            metrics['billion_amounts'] = billions
            
        # Extract ratios
        ratios = []
        for match in re.finditer(self.ratio_pattern, text):
            ratio = float(match.group(1)) / float(match.group(2))
            ratios.append(ratio)
        if ratios:
            metrics['ratios'] = ratios
            
        # Extract maturity years (for bonds)
        maturity_years = []
        maturity_pattern = r'(?:due|maturity|matures?)\s+(?:in\s+)?(\d{4})'
        for match in re.finditer(maturity_pattern, text, re.IGNORECASE):
            year = int(match.group(1))
            if 2020 <= year <= 2100:  # Reasonable range
                maturity_years.append(year)
                years_to_maturity = year - datetime.now().year
                if years_to_maturity > 0:
                    if 'years_to_maturity' not in metrics:
                        metrics['years_to_maturity'] = []
                    metrics['years_to_maturity'].append(years_to_maturity)
        if maturity_years:
            metrics['maturity_years'] = maturity_years
            
        return metrics
    
    def _extract_ownership_metrics(self, text: str) -> Dict:
        """Extract ownership thresholds and percentages."""
        metrics = {}
        
        # Extract all percentages
        percentages = []
        for match in re.finditer(self.percentage_pattern, text):
            pct = float(match.group(1))
            percentages.append(pct)
        
        if percentages:
            metrics['all_percentages'] = percentages
            
        # Extract specific ownership thresholds
        ownership_pattern = r'(?:exceed|above|more than|at least|minimum of)\s+(\d+(?:\.\d+)?)\s*%'
        ownership_thresholds = []
        for match in re.finditer(ownership_pattern, text, re.IGNORECASE):
            threshold = float(match.group(1))
            ownership_thresholds.append(threshold)
        if ownership_thresholds:
            metrics['ownership_thresholds'] = ownership_thresholds
            
        # Extract voting power percentages
        voting_pattern = r'voting\s+(?:power|rights?)\s+.*?(\d+(?:\.\d+)?)\s*%'
        voting_percentages = []
        for match in re.finditer(voting_pattern, text, re.IGNORECASE):
            pct = float(match.group(1))
            voting_percentages.append(pct)
        if voting_percentages:
            metrics['voting_percentages'] = voting_percentages
            
        return metrics
    
    def _extract_time_metrics(self, text: str) -> Dict:
        """Extract time periods and dates."""
        metrics = {}
        
        # Extract days
        days = []
        for match in re.finditer(self.days_pattern, text):
            days.append(int(match.group(1)))
        if days:
            metrics['days_periods'] = days
            
        # Extract months  
        months = []
        for match in re.finditer(self.months_pattern, text):
            months.append(int(match.group(1)))
        if months:
            metrics['months_periods'] = months
            
        # Extract years
        years = []
        for match in re.finditer(self.years_pattern, text):
            years.append(int(match.group(1)))
        if years:
            metrics['years_periods'] = years
            
        # Extract notice periods
        notice_pattern = r'(?:notice|notification)\s+(?:period|of)\s+(?:at least\s+)?(\d+)\s*(days?|months?)'
        notice_periods = []
        for match in re.finditer(notice_pattern, text, re.IGNORECASE):
            period = int(match.group(1))
            unit = match.group(2)
            if 'day' in unit:
                notice_periods.append(period)
            elif 'month' in unit:
                notice_periods.append(period * 30)  # Convert to days
        if notice_periods:
            metrics['notice_periods_days'] = notice_periods
            
        return metrics
    
    def _extract_trigger_metrics(self, text: str) -> Dict:
        """Extract trigger levels and barriers."""
        metrics = {}
        
        # Extract barrier levels
        barrier_pattern = r'(?:barrier|trigger|threshold)\s+(?:at|of|level)\s+(\d+(?:\.\d+)?)\s*%'
        barriers = []
        for match in re.finditer(barrier_pattern, text, re.IGNORECASE):
            barrier = float(match.group(1))
            barriers.append(barrier)
        if barriers:
            metrics['barrier_levels'] = barriers
            
        # Extract buffer amounts
        buffer_pattern = r'buffer\s+(?:amount|of)\s+(\d+(?:\.\d+)?)\s*%'
        buffers = []
        for match in re.finditer(buffer_pattern, text, re.IGNORECASE):
            buffer = float(match.group(1))
            buffers.append(buffer)
        if buffers:
            metrics['buffer_amounts'] = buffers
            
        # Extract participation rates
        participation_pattern = r'participation\s+(?:rate|of)\s+(\d+(?:\.\d+)?)\s*%'
        participation = []
        for match in re.finditer(participation_pattern, text, re.IGNORECASE):
            rate = float(match.group(1))
            participation.append(rate)
        if participation:
            metrics['participation_rates'] = participation
            
        return metrics
    
    def _extract_control_metrics(self, text: str) -> Dict:
        """Extract control and governance thresholds."""
        metrics = {}
        
        # Extract board control percentages
        board_pattern = r'(?:board|director|nomination)\s+.*?(\d+(?:\.\d+)?)\s*%'
        board_percentages = []
        for match in re.finditer(board_pattern, text, re.IGNORECASE):
            pct = float(match.group(1))
            board_percentages.append(pct)
        if board_percentages:
            metrics['board_control_percentages'] = board_percentages
            
        # Extract supermajority thresholds
        supermajority_pattern = r'(?:supermajority|two-thirds|2/3|\d+/\d+)\s+.*?(\d+(?:\.\d+)?)\s*%'
        supermajority = []
        for match in re.finditer(supermajority_pattern, text, re.IGNORECASE):
            pct = float(match.group(1))
            supermajority.append(pct)
        if supermajority:
            metrics['supermajority_thresholds'] = supermajority
            
        return metrics
    
    def _parse_formulas(self, text: str) -> Optional[FormulaComponents]:
        """Parse mathematical formulas from text and extract structured components."""
        
        # Look for common formula patterns
        formula_patterns = [
            r'Payment at maturity = (.+?)(?:\.|$)',
            r'Conversion value = (.+?)(?:\.|$)',
            r'Redemption amount = (.+?)(?:\.|$)',
            r'Final payment = (.+?)(?:\.|$)',
            r'\$1,000.* = (.+?)(?:\.|$)',
            r'Amount payable = (.+?)(?:\.|$)'
        ]
        
        formula_text = ""
        for pattern in formula_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                formula_text = match.group(1).strip()
                break
        
        if not formula_text:
            return None
        
        # Extract numerical components
        principal_amounts = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', formula_text)
        principal_amount = float(principal_amounts[0].replace(',', '')) if principal_amounts else None
        
        # Extract buffer percentage references
        buffer_match = re.search(r'buffer\s+(?:amount|percentage)', formula_text, re.IGNORECASE)
        has_buffer = bool(buffer_match)
        
        # Extract participation rate
        participation_match = re.search(r'(\d+(?:\.\d+)?)\s*%?\s*participation', formula_text, re.IGNORECASE)
        participation_rate = float(participation_match.group(1)) if participation_match else None
        
        # Detect worst-of/best-of structures
        worst_of = bool(re.search(r'worst\s+performing', formula_text, re.IGNORECASE))
        best_of = bool(re.search(r'best\s+performing', formula_text, re.IGNORECASE))
        
        # Extract cap levels
        cap_match = re.search(r'cap(?:ped)?\s+at\s+(\d+(?:\.\d+)?)\s*%', formula_text, re.IGNORECASE)
        cap_level = float(cap_match.group(1)) if cap_match else None
        
        # Extract floor levels  
        floor_match = re.search(r'floor\s+(?:at|of)\s+(\d+(?:\.\d+)?)\s*%', formula_text, re.IGNORECASE)
        floor_level = float(floor_match.group(1)) if floor_match else None
        
        # Standardize formula structure
        formula_structure = self._standardize_formula_structure(formula_text)
        
        # Extract all numerical parameters
        numerical_params = {
            'principal_amount': principal_amount,
            'participation_rate': participation_rate,
            'cap_level': cap_level,
            'floor_level': floor_level,
            'has_buffer': has_buffer,
            'worst_of_structure': worst_of,
            'best_of_structure': best_of
        }
        
        return FormulaComponents(
            formula_type="structured_note" if principal_amount == 1000 else "unknown",
            principal_amount=principal_amount,
            multiplier=principal_amount,  # Often same as principal for structured notes
            performance_component="underlying_return" if worst_of or best_of else "index_return",
            participation_rate=participation_rate,
            cap_level=cap_level,
            floor_level=floor_level,
            formula_structure=formula_structure,
            original_text=formula_text,
            numerical_parameters=numerical_params
        )
    
    def _standardize_formula_structure(self, formula_text: str) -> str:
        """Convert formula text to standardized mathematical structure."""
        
        # Common structured note pattern: Principal + (Principal × Performance Component)
        if re.search(r'\$1,000.*\+.*\$1,000.*×', formula_text, re.IGNORECASE):
            return "P + (P × (R + B))"  # Principal + (Principal × (Return + Buffer))
        elif re.search(r'\$1,000.*×.*return', formula_text, re.IGNORECASE):
            return "P × R"  # Principal × Return
        elif re.search(r'\$1,000.*\+', formula_text, re.IGNORECASE):
            return "P + X"  # Principal + Something
        else:
            return "CUSTOM"
    
    def _extract_structured_product_metrics(self, text: str) -> Optional[StructuredProductMetrics]:
        """Extract metrics specific to structured products."""
        
        # Extract barrier levels
        knock_in_pattern = r'knock.?in.*?(?:barrier|level).*?(\d+(?:\.\d+)?)\s*%'
        knock_out_pattern = r'knock.?out.*?(?:barrier|level).*?(\d+(?:\.\d+)?)\s*%'
        
        knock_in_match = re.search(knock_in_pattern, text, re.IGNORECASE)
        knock_out_match = re.search(knock_out_pattern, text, re.IGNORECASE)
        
        knock_in_barrier = float(knock_in_match.group(1)) if knock_in_match else None
        knock_out_barrier = float(knock_out_match.group(1)) if knock_out_match else None
        
        # Extract autocall barriers
        autocall_pattern = r'autocall.*?(?:barrier|level|at)\s+(\d+(?:\.\d+)?)\s*%'
        autocall_matches = re.findall(autocall_pattern, text, re.IGNORECASE)
        autocall_barriers = [float(x) for x in autocall_matches]
        
        # Extract buffer and participation
        buffer_pattern = r'(?:downside\s+)?buffer.*?(\d+(?:\.\d+)?)\s*%'
        buffer_match = re.search(buffer_pattern, text, re.IGNORECASE)
        downside_buffer = float(buffer_match.group(1)) if buffer_match else None
        
        participation_pattern = r'(?:upside\s+)?participation.*?(\d+(?:\.\d+)?)\s*%'
        participation_match = re.search(participation_pattern, text, re.IGNORECASE)
        upside_participation = float(participation_match.group(1)) if participation_match else None
        
        # Detect underlying structure
        worst_of = bool(re.search(r'worst\s+performing', text, re.IGNORECASE))
        best_of = bool(re.search(r'best\s+performing', text, re.IGNORECASE))
        
        # Extract underlying assets
        underlying_pattern = r'linked to.*?([A-Z]{1,5}(?:\s+Inc\.?|\s+Corp\.?|\s+LLC)?(?:,\s*[A-Z]{1,5}(?:\s+Inc\.?|\s+Corp\.?|\s+LLC)?)*)'
        underlying_match = re.search(underlying_pattern, text, re.IGNORECASE)
        underlying_assets = []
        if underlying_match:
            assets_text = underlying_match.group(1)
            # Split by common separators
            underlying_assets = [asset.strip() for asset in re.split(r',|\sand\s', assets_text)]
        
        if any([knock_in_barrier, knock_out_barrier, autocall_barriers, downside_buffer, upside_participation]):
            return StructuredProductMetrics(
                knock_in_barrier=knock_in_barrier,
                knock_out_barrier=knock_out_barrier,
                autocall_barriers=autocall_barriers,
                downside_buffer=downside_buffer,
                upside_participation=upside_participation,
                underlying_assets=underlying_assets,
                worst_of_structure=worst_of,
                best_of_structure=best_of
            )
        
        return None
    
    def _extract_conversion_metrics(self, text: str) -> Optional[ConversionMetrics]:
        """Extract enhanced conversion-specific metrics."""
        
        # Extract conversion prices
        conversion_price_pattern = r'conversion\s+price.*?\$(\d+(?:\.\d{2})?)'
        conversion_matches = re.findall(conversion_price_pattern, text, re.IGNORECASE)
        initial_conversion_price = float(conversion_matches[0]) if conversion_matches else None
        
        # Extract conversion ratio
        ratio_pattern = r'conversion\s+ratio.*?(\d+(?:\.\d+)?)'
        ratio_match = re.search(ratio_pattern, text, re.IGNORECASE)
        conversion_ratio = float(ratio_match.group(1)) if ratio_match else None
        
        # Extract stock price triggers
        stock_trigger_pattern = r'stock\s+price.*?(?:exceeds?|above|reaches?)\s+\$(\d+(?:\.\d{2})?)'
        stock_triggers = [float(x) for x in re.findall(stock_trigger_pattern, text, re.IGNORECASE)]
        
        # Extract ownership triggers
        ownership_trigger_pattern = r'(?:exceed|above|more than)\s+(\d+(?:\.\d+)?)\s*%.*?(?:ownership|beneficial|voting)'
        ownership_triggers = [float(x) for x in re.findall(ownership_trigger_pattern, text, re.IGNORECASE)]
        
        # Detect anti-dilution features
        anti_dilution_features = []
        if re.search(r'anti.?dilution', text, re.IGNORECASE):
            anti_dilution_features.append("standard")
        if re.search(r'weighted.?average', text, re.IGNORECASE):
            anti_dilution_features.append("weighted_average")
        if re.search(r'full.?ratchet', text, re.IGNORECASE):
            anti_dilution_features.append("full_ratchet")
        
        # Detect reset provisions
        reset_provisions = bool(re.search(r'reset.*?conversion', text, re.IGNORECASE))
        
        if any([initial_conversion_price, conversion_ratio, stock_triggers, ownership_triggers]):
            return ConversionMetrics(
                initial_conversion_price=initial_conversion_price,
                conversion_ratio=conversion_ratio,
                stock_price_triggers=stock_triggers,
                ownership_triggers=ownership_triggers,
                anti_dilution_adjustments=anti_dilution_features,
                reset_provisions=reset_provisions
            )
        
        return None
    
    def _extract_vwap_metrics(self, text: str) -> Optional[VWAPMetrics]:
        """Extract VWAP-based calculation components."""
        
        # Extract VWAP period
        vwap_period_pattern = r'(\d+).?day.*?(?:average\s+)?(?:daily\s+)?VWAP'
        vwap_period_match = re.search(vwap_period_pattern, text, re.IGNORECASE)
        vwap_period_days = int(vwap_period_match.group(1)) if vwap_period_match else None
        
        # Extract VWAP threshold percentage
        threshold_pattern = r'(?:at\s+least\s+)?(\d+(?:\.\d+)?)\s*%.*?(?:of\s+the\s+)?(?:conversion\s+price|exercise\s+price)'
        threshold_match = re.search(threshold_pattern, text, re.IGNORECASE)
        vwap_threshold_percentage = float(threshold_match.group(1)) if threshold_match else None
        
        # Extract VWAP threshold days
        threshold_days_pattern = r'(?:at\s+least\s+)?(\d+)\s+trading\s+days'
        threshold_days_match = re.search(threshold_days_pattern, text, re.IGNORECASE)
        vwap_threshold_days = int(threshold_days_match.group(1)) if threshold_days_match else None
        
        # Extract threshold period
        threshold_period_pattern = r'during\s+any\s+(\d+)\s+consecutive\s+(?:trading\s+)?days'
        threshold_period_match = re.search(threshold_period_pattern, text, re.IGNORECASE)
        vwap_threshold_period = int(threshold_period_match.group(1)) if threshold_period_match else None
        
        # Detect VWAP-based pricing
        vwap_based_conversion = bool(re.search(r'conversion.*VWAP|VWAP.*conversion', text, re.IGNORECASE))
        vwap_based_exercise = bool(re.search(r'exercise.*VWAP|VWAP.*exercise', text, re.IGNORECASE))
        
        # Extract rounding method
        rounding_pattern = r'rounded\s+(up|down|to\s+the\s+nearest)'
        rounding_match = re.search(rounding_pattern, text, re.IGNORECASE)
        share_rounding_method = rounding_match.group(1).replace(' ', '_') if rounding_match else None
        
        if any([vwap_period_days, vwap_threshold_percentage, vwap_based_conversion, vwap_based_exercise]):
            return VWAPMetrics(
                vwap_period_days=vwap_period_days,
                vwap_threshold_percentage=vwap_threshold_percentage,
                vwap_threshold_days=vwap_threshold_days,
                vwap_threshold_period=vwap_threshold_period,
                vwap_based_conversion_price=vwap_based_conversion,
                vwap_based_exercise_price=vwap_based_exercise,
                share_rounding_method=share_rounding_method
            )
        
        return None
    
    def _extract_min_max_formulas(self, text: str) -> Optional[MinMaxFormulaComponents]:
        """Extract min/max formula structures."""
        
        # Look for greater of/lesser of patterns
        greater_pattern = r'(?:equal\s+to\s+the\s+)?greater\s+of\s+(.+?)(?:\.|$|and)'
        lesser_pattern = r'(?:equal\s+to\s+the\s+)?lesser\s+of\s+(.+?)(?:\.|$|and)'
        
        formula_type = None
        formula_text = ""
        
        greater_match = re.search(greater_pattern, text, re.IGNORECASE | re.DOTALL)
        if greater_match:
            formula_type = "greater_of"
            formula_text = greater_match.group(1)
        else:
            lesser_match = re.search(lesser_pattern, text, re.IGNORECASE | re.DOTALL)
            if lesser_match:
                formula_type = "lesser_of"
                formula_text = lesser_match.group(1)
        
        if not formula_type:
            return None
        
        # Extract components
        components = []
        
        # Look for (a), (b), (c) or (x), (y), (z) patterns
        component_pattern = r'\([a-z]\)\s*([^()]+?)(?=\s*\([a-z]\)|$)'
        component_matches = re.findall(component_pattern, formula_text, re.IGNORECASE)
        
        if not component_matches:
            # Try alternative pattern with numbered components
            component_pattern = r'\((\d+)\)\s*([^()]+?)(?=\s*\(\d+\)|$)'
            component_matches = re.findall(component_pattern, formula_text, re.IGNORECASE)
            if component_matches:
                components = [match[1].strip() for match in component_matches]
        else:
            components = [match.strip() for match in component_matches]
        
        # Extract any numerical values
        component_values = []
        for component in components:
            amounts = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', component)
            component_values.append(float(amounts[0].replace(',', '')) if amounts else None)
        
        # Create structured formula
        if len(components) == 2:
            structured_formula = f"{formula_type}({components[0]}, {components[1]})"
        elif len(components) == 3:
            structured_formula = f"{formula_type}({components[0]}, {components[1]}, {components[2]})"
        else:
            structured_formula = f"{formula_type}(...)"
        
        return MinMaxFormulaComponents(
            formula_type=formula_type,
            component_a=components[0] if len(components) > 0 else None,
            component_b=components[1] if len(components) > 1 else None,
            component_c=components[2] if len(components) > 2 else None,
            component_a_value=component_values[0] if len(component_values) > 0 else None,
            component_b_value=component_values[1] if len(component_values) > 1 else None,
            component_c_value=component_values[2] if len(component_values) > 2 else None,
            original_formula=formula_text,
            structured_formula=structured_formula
        )
    
    def _extract_anti_dilution_metrics(self, text: str) -> Optional[AntiDilutionMetrics]:
        """Extract anti-dilution adjustment formulas."""
        
        # Detect anti-dilution type
        adjustment_type = None
        if re.search(r'weighted.?average.?broad', text, re.IGNORECASE):
            adjustment_type = "weighted_average_broad"
        elif re.search(r'weighted.?average.?narrow', text, re.IGNORECASE):
            adjustment_type = "weighted_average_narrow"
        elif re.search(r'weighted.?average', text, re.IGNORECASE):
            adjustment_type = "weighted_average"
        elif re.search(r'full.?ratchet', text, re.IGNORECASE):
            adjustment_type = "full_ratchet"
        
        if not adjustment_type:
            return None
        
        # Extract scope
        scope = None
        if 'broad' in adjustment_type:
            scope = "broad"
        elif 'narrow' in adjustment_type:
            scope = "narrow"
        elif re.search(r'anti.?dilution.*broad|broad.*anti.?dilution', text, re.IGNORECASE):
            scope = "broad"
        
        # Extract excluded issuances for broad-based
        excluded_issuances = []
        exclusion_patterns = [
            r'exclud\w+.*?(employee|option|warrant|incentive)',
            r'not.*includ\w+.*?(employee|option|warrant|incentive)',
            r'except\w*.*?(employee|option|warrant|incentive)'
        ]
        
        for pattern in exclusion_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            excluded_issuances.extend(matches)
        
        return AntiDilutionMetrics(
            adjustment_type=adjustment_type,
            scope=scope,
            excluded_issuances=excluded_issuances
        )
    
    def _extract_floating_rate_metrics(self, text: str) -> Optional[FloatingRateMetrics]:
        """Extract floating rate calculation components."""
        
        # Extract base rate
        base_rate = None
        base_rate_patterns = [
            (r'SOFR', 'SOFR'),
            (r'LIBOR', 'LIBOR'),
            (r'Prime.*Rate', 'Prime'),
            (r'Treasury', 'Treasury'),
            (r'Federal\s+Funds', 'Fed_Funds')
        ]
        
        for pattern, rate_name in base_rate_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                base_rate = rate_name
                break
        
        if not base_rate:
            return None
        
        # Extract spread
        spread_percentage = None
        spread_bps = None
        
        # Look for percentage spreads
        spread_pattern = r'(?:plus|minus|\+|\-)\s*(\d+(?:\.\d+)?)\s*%'
        spread_match = re.search(spread_pattern, text, re.IGNORECASE)
        if spread_match:
            spread_percentage = float(spread_match.group(1))
            if 'minus' in spread_match.group(0) or '-' in spread_match.group(0):
                spread_percentage = -spread_percentage
        
        # Look for basis points
        bps_pattern = r'(?:plus|minus|\+|\-)\s*(\d+(?:\.\d+)?)\s*(?:basis\s+points|bps|bp)'
        bps_match = re.search(bps_pattern, text, re.IGNORECASE)
        if bps_match:
            spread_bps = float(bps_match.group(1))
            if 'minus' in bps_match.group(0) or '-' in bps_match.group(0):
                spread_bps = -spread_bps
        
        # Extract compounding method
        compounding_method = None
        if re.search(r'compounded.?SOFR', text, re.IGNORECASE):
            compounding_method = "compounded_sofr"
        elif re.search(r'compound', text, re.IGNORECASE):
            compounding_method = "compound"
        else:
            compounding_method = "simple"
        
        return FloatingRateMetrics(
            base_rate=base_rate,
            spread_percentage=spread_percentage,
            spread_bps=spread_bps,
            compounding_method=compounding_method
        )
    
    def _extract_cashless_exercise_metrics(self, text: str) -> Optional[CashlessExerciseMetrics]:
        """Extract cashless exercise calculation components."""
        
        # Detect cashless exercise
        if not re.search(r'cashless.*exercise|net.*(?:share|settlement)', text, re.IGNORECASE):
            return None
        
        exercise_type = "cashless"
        
        # Extract net share formula components
        net_share_formula = None
        formula_patterns = [
            r'net.*(?:number|shares).*=.*([^.]+)',
            r'(?:FMV|fair.*market.*value).*-.*(?:exercise|strike).*price',
            r'\([^)]*FMV[^)]*\)\s*/\s*FMV'
        ]
        
        for pattern in formula_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                if len(match.groups()) > 0:
                    net_share_formula = match.group(1).strip()
                else:
                    net_share_formula = match.group(0).strip()
                break
        
        # Extract FMV calculation method
        fmv_calculation_method = None
        fmv_period = None
        
        if re.search(r'closing.*price', text, re.IGNORECASE):
            fmv_calculation_method = "closing_price"
        elif re.search(r'average.*price|VWAP', text, re.IGNORECASE):
            fmv_calculation_method = "average"
            # Extract averaging period
            period_match = re.search(r'(\d+).?day.*average', text, re.IGNORECASE)
            if period_match:
                fmv_period = int(period_match.group(1))
        
        # Extract fractional share treatment
        fractional_treatment = None
        if re.search(r'rounded.*up', text, re.IGNORECASE):
            fractional_treatment = "round_up"
        elif re.search(r'rounded.*down', text, re.IGNORECASE):
            fractional_treatment = "round_down"
        elif re.search(r'cash.*lieu.*fractional', text, re.IGNORECASE):
            fractional_treatment = "cash"
        
        return CashlessExerciseMetrics(
            exercise_type=exercise_type,
            net_share_formula=net_share_formula,
            fmv_calculation_method=fmv_calculation_method,
            fmv_calculation_period=fmv_period,
            fractional_share_treatment=fractional_treatment
        )

class TextExtractor:
    """Utility class for extracting common patterns from text."""
    
    def __init__(self):
        pass
    
    def extract_amounts(self, text: str) -> List[float]:
        """Extract dollar amounts from text."""
        amounts = []
        # Pattern for amounts like $100, $1,000, $1.5M, etc.
        patterns = [
            r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $1,000.00
            r'\$(\d+(?:\.\d+)?)\s*(?:million|M)',  # $1.5M
            r'\$(\d+(?:\.\d+)?)\s*(?:billion|B)',  # $1.5B
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                amount = float(match.group(1).replace(',', ''))
                if 'million' in pattern or 'M' in pattern:
                    amount *= 1_000_000
                elif 'billion' in pattern or 'B' in pattern:
                    amount *= 1_000_000_000
                amounts.append(amount)
        
        return amounts
    
    def extract_percentages(self, text: str) -> List[float]:
        """Extract percentages from text."""
        percentages = []
        pattern = r'(\d+(?:\.\d+)?)\s*%'
        
        for match in re.finditer(pattern, text):
            pct = float(match.group(1))
            percentages.append(pct)
        
        return percentages
    
    def extract_dates(self, text: str) -> List[str]:
        """Extract dates from text."""
        dates = []
        # Common date patterns
        patterns = [
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b',  # MM/DD/YYYY
            r'\b(\d{4}-\d{2}-\d{2})\b',      # YYYY-MM-DD
            r'\b([A-Za-z]+ \d{1,2}, \d{4})\b',  # Month DD, YYYY
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                dates.append(match.group(1))
        
        return dates
    
    def extract_share_counts(self, text: str) -> List[int]:
        """Extract share counts from text."""
        counts = []
        pattern = r'(\d+(?:,\d{3})*)\s*shares?'
        
        for match in re.finditer(pattern, text, re.IGNORECASE):
            count = int(match.group(1).replace(',', ''))
            counts.append(count)
        
        return counts

def main():
    """Main function for command line usage."""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Extract securities features with optional limits")
    parser.add_argument("ticker", type=str, help="Ticker symbol")
    parser.add_argument("years_back", type=int, nargs="?", default=5, help="Years back to search")
    parser.add_argument("--only-424b", action="store_true", help="Limit to 424B filings only")
    parser.add_argument("--per-type-limit", type=int, default=10, help="Max filings per type to process")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    years_back = args.years_back

    print(f"🔍 Extracting securities features for {ticker} (last {years_back} years)")

    extractor = SecuritiesFeaturesExtractor()

    # If only 424B requested, narrow filing types
    if args.only_424b:
        extractor.filing_types = [ft for ft in extractor.filing_types if ft.startswith("424B")]

    # Override per-type limit if provided
    global MAX_DOCUMENTS_LIMIT
    try:
        per_type_limit = int(args.per_type_limit)
        # We respect per-type limit inside extract_features by slicing file_paths
        # but also lower the global cap so overall run ends sooner
        MAX_DOCUMENTS_LIMIT = max(1, min(MAX_DOCUMENTS_LIMIT, per_type_limit * len(extractor.filing_types)))
    except Exception:
        pass

    securities = extractor.extract_features(ticker, years_back)

    if securities:
        print(f"\n✅ Found {len(securities)} securities with features:")
        for security in securities:
            print(f"\n• {security.type}: {security.description}")
            if security.has_change_control_provisions:
                print("  🔄 Change of control provisions")
            if security.has_make_whole_provisions:
                print("  💰 Make-whole provisions")
            if security.conversion_terms:
                print("  🔀 Convertible features")
            print(f"  📁 Source: {security.filing_source}")
        print(f"\n💾 Results saved to output/{ticker}_securities_features.json")
    else:
        print(f"❌ No securities features found for {ticker}")

if __name__ == "__main__":
    main() 