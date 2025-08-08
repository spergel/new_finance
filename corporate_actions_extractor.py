#!/usr/bin/env python3
"""
Corporate Actions Extractor

Extracts recent corporate actions affecting securities from 8-K, 10-K, and 10-Q filings.
Focuses on tenders, redemptions, conversions, M&A events, and other corporate actions.
"""

import os
import json
import logging
import re
from typing import List, Dict, Optional
from datetime import datetime, date
from sec_api_client import SECAPIClient
from models import (
    BaseCorporateAction, TenderOfferAction, DebtRefinancingAction, 
    AssetSaleAction, ShareTransactionAction, AnnualMeetingAction,
    RedomesticationAction, PreferredStockAction, ShareAuthorizationAction,
    CorporateActionResult, CorporateActionType, CorporateActionStatus, ImpactCategory
)

class TextExtractor:
    """Enhanced text extraction for corporate actions with regex patterns and NLP."""
    
    def __init__(self):
        # Compile regex patterns for better performance
        self.amount_patterns = [
            # $1.2 billion, $500 million, $1.5M, etc.
            r'\$\s?(\d+(?:\.\d+)?)\s?(billion|billion|mil+ion|mil+|thousand|k)\b',
            # $123,456,789 or $123.4 format
            r'\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
            # 1.2 billion dollars, 500 million USD
            r'(\d+(?:\.\d+)?)\s?(billion|mil+ion|mil+|thousand|k)?\s?(?:dollars?|USD|usd)',
            # €500M, £1.2B format
            r'[€£¥]\s?(\d+(?:\.\d+)?)\s?([BMK]?)',
        ]
        
        self.percentage_patterns = [
            r'(\d+(?:\.\d+)?)\s?%',  # 8.375%
            r'(\d+)\s?(\d+)/(\d+)\s?%',  # 8 3/8%
            r'(\d+(?:\.\d+)?)\s?percent',  # 8.5 percent
        ]
        
        self.share_count_patterns = [
            r'(\d+(?:,\d{3})*(?:\.\d+)?)\s?(?:million|mil+|thousand|k)?\s?(?:shares?|common shares?|preferred shares?)',
            r'(\d{1,3}(?:,\d{3})*)\s?(?:shares?|common shares?|preferred shares?)',
        ]
        
        self.date_patterns = [
            r'(\w+ \d{1,2}, \d{4})',  # July 15, 2025
            r'(\d{1,2}/\d{1,2}/\d{4})',  # 7/15/2025
            r'(\d{4}-\d{2}-\d{2})',  # 2025-07-15
        ]
        
        self.cusip_pattern = r'CUSIP[:\s]?([A-Z0-9]{9})'
        self.series_pattern = r'Series\s+([A-Z](?:-[A-Z])?)'
        self.credit_rating_patterns = [
            r"Moody's\s+([A-Z][a-z0-9]+)",
            r"S&P\s+([A-Z]{1,3}[+-]?)",
            r"Fitch\s+([A-Z]{1,3}[+-]?)"
        ]
    
    def extract_financial_amounts(self, text: str) -> Dict[str, float]:
        """Extract various financial amounts from text."""
        amounts = {}
        text_lower = text.lower()
        
        for pattern in self.amount_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                try:
                    amount = float(match.group(1).replace(',', ''))
                    multiplier = self._get_multiplier(match.group(2) if len(match.groups()) > 1 else '')
                    final_amount = amount * multiplier
                    
                    # Categorize the amount based on context
                    context = text_lower[max(0, match.start()-50):match.end()+50]
                    
                    if any(term in context for term in ['debt', 'borrow', 'loan', 'credit', 'facility']):
                        amounts['debt_amount'] = final_amount
                    elif any(term in context for term in ['proceeds', 'purchase price', 'consideration']):
                        amounts['transaction_value'] = final_amount
                    elif any(term in context for term in ['dividend', 'distribution']):
                        amounts['dividend_amount'] = final_amount
                    elif any(term in context for term in ['authorized', 'shares']):
                        amounts['share_amount'] = final_amount
                    else:
                        amounts['general_amount'] = final_amount
                        
                except (ValueError, IndexError):
                    continue
        
        return amounts
    
    def extract_percentages(self, text: str) -> Dict[str, float]:
        """Extract percentage values from text."""
        percentages = {}
        
        for pattern in self.percentage_patterns:
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                try:
                    if len(match.groups()) == 1:
                        pct = float(match.group(1))
                    elif len(match.groups()) == 3:
                        # Handle fractional percentages like "8 3/8%"
                        whole = int(match.group(1))
                        numerator = int(match.group(2))
                        denominator = int(match.group(3))
                        pct = whole + (numerator / denominator)
                    else:
                        continue
                    
                    # Categorize based on context
                    context = text.lower()[max(0, match.start()-30):match.end()+30]
                    
                    if any(term in context for term in ['interest', 'rate', 'coupon']):
                        percentages['interest_rate'] = pct
                    elif any(term in context for term in ['dividend', 'yield']):
                        percentages['dividend_rate'] = pct
                    elif any(term in context for term in ['premium', 'discount']):
                        percentages['premium_discount'] = pct
                    elif any(term in context for term in ['conversion', 'exchange']):
                        percentages['conversion_rate'] = pct
                    else:
                        percentages['general_percentage'] = pct
                        
                except (ValueError, IndexError):
                    continue
        
        return percentages
    
    def extract_share_counts(self, text: str) -> Dict[str, float]:
        """Extract share counts from text."""
        shares = {}
        
        for pattern in self.share_count_patterns:
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                try:
                    count_str = match.group(1).replace(',', '')
                    count = float(count_str)
                    
                    # Check for multiplier words in the match
                    full_match = match.group(0)
                    if 'million' in full_match or 'mil' in full_match:
                        count *= 1_000_000
                    elif 'thousand' in full_match or 'k' in full_match:
                        count *= 1_000
                    
                    # Categorize based on context
                    context = text.lower()[max(0, match.start()-30):match.end()+30]
                    
                    if 'common' in context:
                        shares['common_shares'] = count
                    elif 'preferred' in context:
                        shares['preferred_shares'] = count
                    elif 'outstanding' in context:
                        shares['outstanding_shares'] = count
                    elif 'authorized' in context:
                        shares['authorized_shares'] = count
                    else:
                        shares['total_shares'] = count
                        
                except (ValueError, IndexError):
                    continue
        
        return shares
    
    def extract_dates(self, text: str) -> Dict[str, str]:
        """Extract key dates from text."""
        dates = {}
        
        for pattern in self.date_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                date_str = match.group(1)
                
                # Categorize based on context
                context = text.lower()[max(0, match.start()-30):match.end()+30]
                
                if any(term in context for term in ['expir', 'deadline', 'due']):
                    dates['expiration_date'] = date_str
                elif any(term in context for term in ['record', 'record date']):
                    dates['record_date'] = date_str
                elif any(term in context for term in ['effective', 'closing']):
                    dates['effective_date'] = date_str
                elif any(term in context for term in ['meeting', 'annual']):
                    dates['meeting_date'] = date_str
                elif any(term in context for term in ['payment', 'distribution']):
                    dates['payment_date'] = date_str
                else:
                    dates['general_date'] = date_str
        
        return dates
    
    def extract_securities_info(self, text: str) -> Dict[str, str]:
        """Extract security identifiers and related info."""
        securities_info = {}
        
        # CUSIP numbers
        cusip_match = re.search(self.cusip_pattern, text.upper())
        if cusip_match:
            securities_info['cusip'] = cusip_match.group(1)
        
        # Series information
        series_match = re.search(self.series_pattern, text)
        if series_match:
            securities_info['series'] = f"Series {series_match.group(1)}"
        
        # Credit ratings
        for pattern in self.credit_rating_patterns:
            rating_match = re.search(pattern, text)
            if rating_match:
                securities_info['credit_rating'] = rating_match.group(1)
                break
        
        return securities_info
    
    def extract_voting_results(self, text: str) -> Dict[str, any]:
        """Extract voting results from annual meeting descriptions."""
        voting_results = {}
        
        # Say-on-pay results
        if re.search(r'say.on.pay|compensation.*approv', text.lower()):
            if re.search(r'approv|ratif|pass', text.lower()):
                voting_results['say_on_pay_approved'] = True
            elif re.search(r'reject|fail|defeat', text.lower()):
                voting_results['say_on_pay_approved'] = False
        
        # Auditor ratification
        auditor_terms = ['auditor', 'accounting firm', 'ernst', 'young', 'deloitte', 'kpmg', 'pwc']
        if any(term in text.lower() for term in auditor_terms):
            if re.search(r'ratif|approv|elect', text.lower()):
                voting_results['auditor_ratified'] = True
            elif re.search(r'reject|fail', text.lower()):
                voting_results['auditor_ratified'] = False
        
        # Extract auditor name
        for auditor in ['Ernst & Young', 'Deloitte', 'KPMG', 'PwC', 'PricewaterhouseCoopers']:
            if auditor.lower() in text.lower():
                voting_results['auditor_name'] = auditor
                break
        
        return voting_results
    
    def extract_director_names(self, text: str) -> List[str]:
        """Extract director names from text."""
        directors = []
        
        # Pattern for names in format "John Smith, Jane Doe, Bob Johnson"
        name_patterns = [
            r'(?:elect|appoint|nominate)(?:ed|d)?\s+([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+)*)',
            r'directors?[:\s]+([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+)*)',
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Split on commas and 'and'
                names = re.split(r',\s*(?:and\s+)?', match)
                directors.extend([name.strip() for name in names if name.strip()])
        
        return list(set(directors))  # Remove duplicates
    
    def _get_multiplier(self, unit: str) -> float:
        """Convert unit strings to numeric multipliers."""
        unit_lower = unit.lower() if unit else ''
        
        if 'billion' in unit_lower or unit_lower == 'b':
            return 1_000_000_000
        elif 'million' in unit_lower or 'mil' in unit_lower or unit_lower == 'm':
            return 1_000_000
        elif 'thousand' in unit_lower or unit_lower == 'k':
            return 1_000
        else:
            return 1
    
    def extract_all_fields(self, text: str) -> Dict[str, any]:
        """Extract all available fields from text in one pass."""
        extracted = {}
        
        # Extract all types of data
        extracted.update(self.extract_financial_amounts(text))
        extracted.update(self.extract_percentages(text))
        extracted.update(self.extract_share_counts(text))
        extracted.update(self.extract_dates(text))
        extracted.update(self.extract_securities_info(text))
        extracted.update(self.extract_voting_results(text))
        
        # Director names as a list
        extracted['directors_elected'] = self.extract_director_names(text)
        
        return extracted

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

class CorporateActionsExtractor:
    """
    Extracts recent corporate actions affecting securities.
    
    Sources: 8-K, 10-K, and 10-Q filings
    Target: Tenders, redemptions, conversions, M&A events
    """
    
    def __init__(self, data_dir: str = "temp_filings"):
        """Initialize the corporate actions extractor."""
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.sec_client = SECAPIClient(data_dir=data_dir)
        self.text_extractor = TextExtractor()  # Initialize enhanced text extraction
        
        # Filing types for corporate actions
        self.filing_types = ["8-K", "10-K", "10-Q"]
        
        # Initialize LLM
        api_key = os.getenv('GOOGLE_API_KEY')
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.0-flash-lite')
                logger.info("Corporate actions extractor initialized with LLM")
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}")
                self.model = None
        else:
            logger.warning("No GOOGLE_API_KEY found. LLM extraction disabled.")
            self.model = None
    
    def extract_actions(self, ticker: str, months_back: int = 12) -> List[Dict]:
        """
        Extract corporate actions for a ticker.
        
        Args:
            ticker: Company ticker symbol
            months_back: Months back to search (default: 12)
            
        Returns:
            List of standardized corporate action dictionaries
        """
        logger.info(f"Extracting corporate actions for {ticker}")
        
        if not self.model:
            logger.error("LLM not available")
            return []
        
        # Download recent filings
        all_actions = []
        
        for filing_type in self.filing_types:
            logger.info(f"Processing {filing_type} filings...")
            
            try:
                # Download filings
                file_paths = self.sec_client.download_filings_by_date_range(
                    ticker=ticker,
                    filing_types=[filing_type],
                    months_back=months_back
                )
                
                if not file_paths:
                    logger.info(f"No {filing_type} filings found")
                    continue
                
                # Extract actions from each filing
                for file_path in file_paths:
                    actions = self._extract_from_filing(file_path, filing_type, ticker)
                    if actions:
                        all_actions.extend(actions)
                        logger.info(f"Extracted {len(actions)} actions from {filing_type}")
                    # --- NEW: Process all exhibits for this filing ---
                    try:
                        # Get accession number from file path
                        import re
                        accession_match = re.search(r'(\d{10}-\d{2}-\d{6})', file_path)
                        if accession_match:
                            accession_number = accession_match.group(1)
                            # Find all files in the same directory
                            import os
                            filing_dir = os.path.dirname(file_path)
                            for filename in os.listdir(filing_dir):
                                if not (filename.endswith('.txt') or filename.endswith('.htm')):
                                    continue
                                # Skip the main file
                                if filename == os.path.basename(file_path):
                                    continue
                                # Only process exhibits with the same accession number
                                if accession_number not in filename:
                                    continue
                                exhibit_path = os.path.join(filing_dir, filename)
                                logger.info(f"Processing exhibit: {filename}")
                                try:
                                    with open(exhibit_path, 'r', encoding='utf-8', errors='ignore') as f:
                                        exhibit_content = f.read()
                                    # Use the same prompt as the main filing
                                    prompt = self._create_standardized_prompt(ticker, exhibit_content, f"{filing_type}_EXHIBIT")
                                    response = self.model.generate_content(prompt)
                                    if response.text:
                                        exhibit_actions = self._parse_response(response.text, exhibit_path, f"{filing_type}_EXHIBIT")
                                        if exhibit_actions:
                                            all_actions.extend(exhibit_actions)
                                            logger.info(f"Extracted {len(exhibit_actions)} actions from exhibit {filename}")
                                except Exception as e:
                                    logger.warning(f"Error processing exhibit {filename}: {e}")
                    except Exception as e:
                        logger.warning(f"Error in exhibit processing for {file_path}: {e}")
                # --- END NEW ---
            except Exception as e:
                logger.error(f"Error processing {filing_type}: {e}")
                continue
        
        # Standardize and deduplicate actions
        standardized_actions = self._standardize_and_deduplicate(all_actions, ticker)
        
        # Save results
        if standardized_actions:
            self._save_standardized_results(ticker, standardized_actions)
        
        return standardized_actions
    
    def _extract_from_filing(self, file_path: str, filing_type: str, ticker: str) -> List[Dict]:
        """Extract corporate actions from a single filing with standardized prompt."""
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Create standardized prompt
            prompt = self._create_standardized_prompt(ticker, content, filing_type)
            
            # Get LLM response
            response = self.model.generate_content(prompt)
            if not response.text:
                logger.warning(f"No LLM response for {file_path}")
                return []
            
            # Parse response
            actions_data = self._parse_response(response.text, file_path, filing_type)
            return actions_data
            
        except Exception as e:
            logger.error(f"Error extracting from {file_path}: {e}")
            return []
    
    def _create_standardized_prompt(self, ticker: str, content: str, filing_type: str) -> str:
        """Create standardized LLM prompt for consistent corporate actions extraction."""
        
        return f"""
You are analyzing a {filing_type} filing for {ticker} to extract CORPORATE ACTIONS with STANDARDIZED formatting.

EXTRACT ONLY SIGNIFICANT CORPORATE ACTIONS:
1. **DEBT REFINANCING**: Credit agreement amendments, bond refinancing, debt modifications
2. **ASSET TRANSACTIONS**: Acquisitions, divestitures, asset sales, spin-offs
3. **CAPITAL STRUCTURE**: Stock splits, dividends, share buybacks, warrant exercises
4. **M&A ACTIVITY**: Mergers, tender offers, going private transactions
5. **EXECUTIVE CHANGES**: CEO/CFO changes, board changes (only if material)
6. **LEGAL EVENTS**: Bankruptcy, litigation settlements, regulatory actions

CRITICAL REQUIREMENTS:
- Each action must be MATERIALLY SIGNIFICANT to the company
- Avoid duplicate descriptions of the same transaction
- Extract exact dollar amounts and dates
- Categorize precisely using standard action types

For each corporate action, extract:

REQUIRED FIELDS:
- **action_id**: Unique identifier (format: "{ticker}_YYYY_MM_DD_ActionType_##")
- **action_type**: One of ["debt_refinancing", "asset_sale", "asset_acquisition", "merger_acquisition", "dividend", "stock_split", "share_buyback", "warrant_exercise", "executive_change", "legal_settlement", "spin_off", "tender_offer", "going_private"]
- **announcement_date**: Date announced (YYYY-MM-DD format)
- **effective_date**: Date effective (YYYY-MM-DD format, or null if TBD)
- **title**: Brief descriptive title (max 100 chars)
- **description**: Detailed description (max 500 chars)
- **status**: One of ["announced", "pending", "completed", "cancelled"]

FINANCIAL DETAILS (when applicable):
- **transaction_value**: Total transaction value in USD (number or null)
- **debt_amount**: Debt amount involved in USD (number or null)
- **share_count**: Number of shares involved (number or null)
- **price_per_share**: Price per share in USD (number or null)

PARTIES INVOLVED:
- **counterparty**: Other party involved (string or null)
- **target_company**: Target company if M&A (string or null)
- **target_assets**: Specific assets/subsidiaries involved (string or null)

IMPACT ASSESSMENT:
- **impact_category**: One of ["major", "moderate", "minor"]
- **impact_description**: Brief impact summary (max 200 chars)

CONDITIONS AND TIMING:
- **conditions_precedent**: List of conditions (array of strings or null)
- **regulatory_approvals**: Required approvals (array of strings or null)
- **expected_completion**: Expected completion date (YYYY-MM-DD or null)

Here's the filing content (first 200,000 characters):

{content[:200000]}

Return ONLY a JSON object with this EXACT structure:

{{
    "corporate_actions": [
        {{
            "action_id": "BW_2025_07_03_DEBT_REFINANCING_01",
            "action_type": "debt_refinancing",
            "announcement_date": "2025-07-03",
            "effective_date": "2025-07-03",
            "title": "Eighth Amendment to Credit Agreement",
            "description": "Amended credit agreement to temporarily increase borrowing base and reduce PBGC Reserve by $3M, with proceeds from Diamond Power disposition applied to debt repayment totaling $51.3M.",
            "status": "completed",
            "transaction_value": null,
            "debt_amount": 51300000,
            "share_count": null,
            "price_per_share": null,
            "counterparty": "Axos Bank",
            "target_company": null,
            "target_assets": "Diamond Power assets",
            "impact_category": "moderate",
            "impact_description": "Improves liquidity and reduces debt burden through asset disposition proceeds",
            "conditions_precedent": ["Net cash proceeds from Diamond Power Disposition"],
            "regulatory_approvals": null,
            "expected_completion": "2025-09-15"
        }}
    ]
}}

CRITICAL VALIDATION:
- Use EXACT action_type values from the list above
- Include monetary amounts as numbers (not strings)
- Use ISO date format (YYYY-MM-DD)
- Ensure action_id is unique and follows the format
- Focus on MATERIAL actions only (avoid minor operational updates)
"""
    
    def _parse_response(self, response_text: str, file_path: str, filing_type: str) -> List[Dict]:
        """Parse LLM response and add metadata."""
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
            actions = data.get('corporate_actions', [])
            
            # Add metadata to each action
            for action in actions:
                action['source_filing'] = filing_type
                action['source_file'] = file_path
                action['extracted_date'] = datetime.now().isoformat()
            
            return actions
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return []
    
    def _standardize_and_deduplicate(self, all_actions: List[Dict], ticker: str) -> List[Dict]:
        """Standardize and deduplicate corporate actions with enhanced logic."""
        
        # Step 1: Apply enhanced deduplication to main actions
        unique_main_actions = self._deduplicate_actions(all_actions)
        logger.info(f"Deduplicated {len(all_actions)} to {len(unique_main_actions)} unique main actions")
        
        # Step 2: Process exhibits for detailed corporate actions (like tender offers)
        try:
            exhibit_actions = self._process_exhibits_for_corporate_actions(ticker, 12)  # Last 12 months
            logger.info(f"Found {len(exhibit_actions)} additional actions from exhibits")
        except Exception as e:
            logger.warning(f"Could not process exhibits: {e}")
            exhibit_actions = []
        
        # Step 3: Combine and standardize all actions
        all_unique_actions = unique_main_actions + exhibit_actions
        
        # Step 4: Standardize the action format
        standardized_actions = []
        action_counter = 1
        
        for action in all_unique_actions:
            standardized_action = self._standardize_action(action, ticker, action_counter)
            if standardized_action:
                standardized_actions.append(standardized_action)
                action_counter += 1
        
        # Step 5: Final deduplication in case exhibits had overlaps
        final_unique_actions = self._deduplicate_actions(standardized_actions)
        
        # Sort by announcement date (newest first)
        final_unique_actions.sort(key=lambda x: x.get('announcement_date', ''), reverse=True)
        
        logger.info(f"Final unique actions: {len(final_unique_actions)}")
        return final_unique_actions
    
    def _standardize_action(self, action: Dict, ticker: str, counter: int) -> Dict:
        """Standardize individual action format and create specialized action objects."""
        
        # Enhanced action type classification
        action_type = action.get('action_type', 'other')
        desc = action.get('description', '').lower()
        title = action.get('title', '').lower()
        
        # Map tender/exchange/repurchase offers to tender_offer
        if any(keyword in desc or keyword in title for keyword in ['tender offer', 'exchange offer', 'repurchase offer', 'offer to purchase']):
            action_type = 'tender_offer'
        elif action_type in ['refinancing']:
            action_type = 'debt_refinancing'
        elif action_type in ['executive_change'] or any(keyword in desc or keyword in title for keyword in [
            'director', 'board', 'annual meeting', 'stockholder', 'shareholder', 'election', 'voted', 'nominees'
        ]):
            if any(keyword in desc or keyword in title for keyword in ['auditor', 'accounting firm', 'ernst', 'young', 'deloitte', 'kpmg', 'pwc']):
                action_type = 'auditor_change'
            elif any(keyword in desc or keyword in title for keyword in ['annual meeting', 'meeting of stockholders', 'meeting of shareholders']):
                action_type = 'annual_meeting'
            elif any(keyword in desc or keyword in title for keyword in ['director', 'board', 'election', 'nominees']):
                action_type = 'director_election'
            else:
                action_type = 'annual_meeting'  # Default governance events to annual meeting
        elif any(keyword in desc or keyword in title for keyword in ['redomestic', 'jurisdiction', 'delaware', 'indiana', 'incorporation', 'conversion']):
            action_type = 'redomestication'
        elif any(keyword in desc or keyword in title for keyword in ['preferred stock', 'preferred shares', 'series']):
            action_type = 'preferred_issuance'
        elif any(keyword in desc or keyword in title for keyword in ['authorized', 'authorization', 'increase', 'capital stock']):
            action_type = 'share_authorization'
        elif action_type in ['stock_split'] and any(keyword in desc or keyword in title for keyword in ['authorized', 'authorization']):
            action_type = 'share_authorization'
        elif action_type in ['merger', 'disposition']:
            if any(word in desc for word in ['sale', 'sold', 'disposition', 'divest']):
                action_type = 'asset_sale'
            else:
                action_type = 'merger'
        
        # Create the appropriate specialized action object
        try:
            # Enhanced text extraction from description and title
            full_text = f"{action.get('title', '')} {action.get('description', '')}"
            extracted_data = self.text_extractor.extract_all_fields(full_text)
            
            base_fields = {
                'action_id': action.get('action_id', f"{ticker}_{action.get('announcement_date', '2025-01-01').replace('-', '_')}_{action_type.upper()}_{counter:02d}"),
                'announcement_date': self._parse_date(action.get('announcement_date')),
                'effective_date': self._parse_date(extracted_data.get('effective_date')) or self._parse_date(action.get('effective_date')),
                'record_date': self._parse_date(extracted_data.get('record_date')),
                'payment_date': self._parse_date(extracted_data.get('payment_date')),
                'title': action.get('title', '')[:100],
                'description': action.get('description', '')[:500],
                'status': CorporateActionStatus(action.get('status', 'completed')),
                'counterparty': action.get('counterparty'),
                'target_company': action.get('target_company'),
                'impact_category': ImpactCategory(action.get('impact_category', 'moderate')),
                'impact_description': action.get('impact_description', ''),
                'conditions_precedent': action.get('conditions_precedent') or [],
                'regulatory_approvals': action.get('regulatory_approvals') if isinstance(action.get('regulatory_approvals'), str) else None,
                'expected_completion': self._parse_date(extracted_data.get('expiration_date')) or self._parse_date(action.get('expected_completion')),
                'source_filing': action.get('source_filing', ''),
                'source_file': action.get('source_file', ''),
                'extracted_date': datetime.now(),
                'currency': action.get('currency', 'USD')
            }
            
            # Create specialized action object based on type
            if action_type == 'tender_offer':
                specialized_action = TenderOfferAction(
                    **base_fields,
                    target_security_type=action.get('target_security_type') or extracted_data.get('series'),
                    target_principal_amount=self._parse_float(extracted_data.get('debt_amount')) or self._parse_float(action.get('target_principal_amount')),
                    offered_security_type=action.get('offered_security_type'),
                    offered_principal_amount=self._parse_float(action.get('offered_principal_amount')),
                    exchange_ratio=self._parse_float(extracted_data.get('conversion_rate')) or self._parse_float(action.get('exchange_ratio')),
                    offer_price=self._parse_float(action.get('offer_price') or action.get('price_per_share')),
                    total_consideration=self._parse_float(extracted_data.get('transaction_value')) or self._parse_float(action.get('transaction_value')),
                    tender_expiration_date=self._parse_date(extracted_data.get('expiration_date')) or self._parse_date(action.get('tender_expiration_date')),
                    cash_consideration=self._parse_float(action.get('cash_consideration')),
                    premium_to_market=self._parse_float(extracted_data.get('premium_discount')),
                    minimum_tender_condition=self._parse_float(action.get('minimum_tender_condition')),
                    proration_threshold=self._parse_float(action.get('proration_threshold')),
                )
            elif action_type == 'debt_refinancing':
                specialized_action = DebtRefinancingAction(
                    **base_fields,
                    old_debt_amount=self._parse_float(action.get('old_debt_amount')),
                    old_interest_rate=self._parse_float(action.get('old_interest_rate')),
                    new_debt_amount=self._parse_float(extracted_data.get('debt_amount')) or self._parse_float(action.get('new_debt_amount') or action.get('debt_amount')),
                    new_interest_rate=self._parse_float(extracted_data.get('interest_rate')) or self._parse_float(action.get('new_interest_rate')),
                    facility_size=self._parse_float(action.get('facility_size')),
                    borrowing_base_change=self._parse_float(action.get('borrowing_base_change')),
                    refinancing_costs=self._parse_float(action.get('refinancing_costs')),
                    net_proceeds=self._parse_float(extracted_data.get('transaction_value')) or self._parse_float(action.get('net_proceeds')),
                    use_of_proceeds=action.get('use_of_proceeds'),
                    credit_rating=extracted_data.get('credit_rating')
                )
            elif action_type == 'asset_sale':
                specialized_action = AssetSaleAction(
                    **base_fields,
                    asset_description=action.get('asset_description', action.get('target_assets', 'Asset sale')),
                    purchase_price=self._parse_float(extracted_data.get('transaction_value')) or self._parse_float(action.get('purchase_price') or action.get('transaction_value')),
                    cash_consideration=self._parse_float(action.get('cash_consideration')),
                    earnout_potential=self._parse_float(action.get('earnout_potential')),
                    annual_revenue=self._parse_float(action.get('annual_revenue')),
                    annual_ebitda=self._parse_float(action.get('annual_ebitda')),
                    buyer_name=action.get('buyer_name', action.get('counterparty')),
                    debt_repayment_amount=self._parse_float(extracted_data.get('debt_amount')) or self._parse_float(action.get('debt_repayment_amount')),
                    use_of_proceeds=action.get('use_of_proceeds')
                )
            elif action_type in ['share_buyback', 'share_issuance']:
                specialized_action = ShareTransactionAction(
                    **base_fields,
                    action_type=CorporateActionType(action_type),
                    share_count=self._parse_float(extracted_data.get('total_shares')) or self._parse_float(action.get('share_count')),
                    price_per_share=self._parse_float(action.get('price_per_share')),
                    total_consideration=self._parse_float(extracted_data.get('transaction_value')) or self._parse_float(action.get('transaction_value')),
                    transaction_method=action.get('transaction_method'),
                    program_size=self._parse_float(action.get('program_size')),
                    percentage_of_outstanding=self._parse_float(extracted_data.get('general_percentage')) or self._parse_float(action.get('percentage_of_outstanding')),
                    use_of_proceeds=action.get('use_of_proceeds'),
                    shares_outstanding_before=self._parse_float(extracted_data.get('outstanding_shares')),
                    shares_outstanding_after=self._parse_float(action.get('shares_outstanding_after'))
                )
            elif action_type in ['annual_meeting', 'director_election']:
                specialized_action = AnnualMeetingAction(
                    **base_fields,
                    action_type=CorporateActionType(action_type),
                    meeting_date=self._parse_date(extracted_data.get('meeting_date')) or self._parse_date(action.get('meeting_date') or action.get('announcement_date')),
                    meeting_type=action.get('meeting_type', 'annual'),
                    directors_elected=extracted_data.get('directors_elected', []),
                    say_on_pay_approved=extracted_data.get('say_on_pay_approved'),
                    auditor_ratified=extracted_data.get('auditor_ratified'),
                    auditor_name=extracted_data.get('auditor_name'),
                    shares_represented=self._parse_float(extracted_data.get('total_shares')) or self._parse_float(action.get('shares_represented')),
                    total_shares_outstanding=self._parse_float(extracted_data.get('outstanding_shares')) or self._parse_float(action.get('total_shares_outstanding'))
                )
            elif action_type == 'redomestication':
                specialized_action = RedomesticationAction(
                    **base_fields,
                    old_jurisdiction=self._extract_old_jurisdiction(action.get('description', '')),
                    new_jurisdiction=self._extract_new_jurisdiction(action.get('description', '')),
                    old_entity_type=action.get('old_entity_type'),
                    new_entity_type=action.get('new_entity_type'),
                    conversion_ratio=self._parse_float(action.get('conversion_ratio', 1.0)),
                    tax_free_reorganization=action.get('tax_free_reorganization', True),
                    stated_reasons=self._extract_redomestication_reasons(action.get('description', ''))
                )
            elif action_type == 'preferred_issuance':
                specialized_action = PreferredStockAction(
                    **base_fields,
                    series_name=extracted_data.get('series') or self._extract_series_name(action.get('description', '')),
                    shares_authorized=self._parse_float(extracted_data.get('authorized_shares')) or self._parse_float(action.get('shares_authorized')),
                    shares_issued=self._parse_float(extracted_data.get('preferred_shares')) or self._parse_float(action.get('shares_issued')),
                    dividend_rate=self._parse_float(extracted_data.get('dividend_rate')) or self._extract_dividend_rate(action.get('description', '')),
                    dividend_type=action.get('dividend_type', 'cumulative'),
                    gross_proceeds=self._parse_float(extracted_data.get('transaction_value')) or self._parse_float(action.get('gross_proceeds')),
                    use_of_proceeds=action.get('use_of_proceeds'),
                    credit_rating=extracted_data.get('credit_rating')
                )
            elif action_type == 'share_authorization':
                specialized_action = ShareAuthorizationAction(
                    **base_fields,
                    old_authorized_shares=self._parse_float(action.get('old_authorized_shares')),
                    new_authorized_shares=self._parse_float(extracted_data.get('authorized_shares')) or self._parse_float(action.get('new_authorized_shares')),
                    authorization_increase=self._parse_float(extracted_data.get('share_amount')) or self._parse_float(action.get('authorization_increase')),
                    share_class=action.get('share_class', 'common'),
                    stated_purpose=action.get('stated_purpose'),
                    shareholder_approval_required=action.get('shareholder_approval_required', True),
                    shares_outstanding_current=self._parse_float(extracted_data.get('outstanding_shares')) or self._parse_float(action.get('shares_outstanding_current'))
                )
            else:
                # Default to base action
                specialized_action = BaseCorporateAction(
                    **base_fields,
                    action_type=CorporateActionType(action_type) if action_type in [e.value for e in CorporateActionType] else CorporateActionType.RESTRUCTURING
                )
            
            # Convert to dict for JSON serialization
            return specialized_action.model_dump()
            
        except Exception as e:
            logger.error(f"Error creating specialized action: {e}")
            # Fallback to original format
            return action
    
    def _save_standardized_results(self, ticker: str, actions: List[Dict]) -> None:
        """Save standardized results with summary statistics."""
        
        output_file = f"output/{ticker}_corporate_actions.json"
        
        # Calculate summary statistics
        action_types = {}
        total_transaction_value = 0
        total_debt_amount = 0
        
        for action in actions:
            action_type = action['action_type']
            action_types[action_type] = action_types.get(action_type, 0) + 1
            
            if action.get('transaction_value'):
                total_transaction_value += action['transaction_value']
            if action.get('debt_amount'):
                total_debt_amount += action['debt_amount']
        
        # Impact distribution
        impact_distribution = {
            "major": len([a for a in actions if a.get('impact_category') == 'major']),
            "moderate": len([a for a in actions if a.get('impact_category') == 'moderate']),
            "minor": len([a for a in actions if a.get('impact_category') == 'minor'])
        }
        
        # Recent activity (last 6 months)
        recent_cutoff = datetime.now().replace(month=datetime.now().month-6 if datetime.now().month > 6 else datetime.now().month+6, year=datetime.now().year-1 if datetime.now().month <= 6 else datetime.now().year)
        def parse_date_for_stats(date_val):
            if isinstance(date_val, date):
                return datetime.combine(date_val, datetime.min.time())
            elif isinstance(date_val, str):
                return datetime.strptime(date_val, '%Y-%m-%d')
            return None
        
        recent_actions = []
        for a in actions:
            if a.get('announcement_date'):
                parsed_date = parse_date_for_stats(a['announcement_date'])
                if parsed_date and parsed_date > recent_cutoff:
                    recent_actions.append(a)
        
        result = {
            "ticker": ticker,
            "extraction_metadata": {
            "extraction_date": datetime.now().isoformat(),
            "total_actions": len(actions),
                "unique_actions": len(actions),  # After deduplication
                "date_range": {
                    "earliest": min([a.get('announcement_date') for a in actions if a.get('announcement_date')], default=None),
                    "latest": max([a.get('announcement_date') for a in actions if a.get('announcement_date')], default=None)
                }
            },
            "summary_statistics": {
                "actions_by_type": action_types,
                "impact_distribution": impact_distribution,
                "financial_totals": {
                    "total_transaction_value": total_transaction_value,
                    "total_debt_activity": total_debt_amount,
                    "currency": "USD"
                },
                "recent_activity": {
                    "last_6_months": len(recent_actions),
                    "most_recent_action": actions[0].get('announcement_date') if actions else None
                }
            },
            "corporate_actions": actions
        }
        
        # Save to JSON file with custom date serialization
        def json_serializer(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            elif isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=json_serializer)
        
        logger.info(f"Standardized corporate actions saved to: {output_file}")
        logger.info(f"Total unique actions: {len(actions)}")
        logger.info(f"Action types: {action_types}")
        logger.info(f"Impact distribution: {impact_distribution}")

    def _deduplicate_actions(self, actions: List[Dict]) -> List[Dict]:
        """Enhanced deduplication based on content similarity and core attributes"""
        if not actions:
            return []
        
        unique_actions = []
        seen_signatures = set()
        
        for action in actions:
            # Create comprehensive signature for deduplication
            date_part = action.get('announcement_date', '') or ''
            type_part = action.get('action_type', '') or ''
            desc = (action.get('description', '') or '').lower()
            title = (action.get('title', '') or '').lower()
            counterparty = (action.get('counterparty', '') or '').lower()
            
            # Extract key numbers for financial similarity
            amounts = self._extract_amounts(f"{desc} {title}")
            amount_signature = "_".join(sorted([str(amt) for amt in amounts[:3]]))  # Top 3 amounts
            
            # Create content-based signature
            key_words = set()
            for text in [desc, title]:
                words = [w for w in text.split() if len(w) > 3 and w not in ['the', 'and', 'for', 'with', 'from']]
                key_words.update(words[:5])  # Top 5 meaningful words
            
            content_signature = "_".join(sorted(list(key_words)))
            
            # Comprehensive signature
            signature = f"{date_part}_{type_part}_{counterparty}_{amount_signature}_{content_signature}"
            
            # Check for similar signatures (allows for minor variations)
            is_duplicate = False
            for seen_sig in seen_signatures:
                if self._signatures_similar(signature, seen_sig, threshold=0.8):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_signatures.add(signature)
                unique_actions.append(action)
        
        return unique_actions
    
    def _extract_amounts(self, text: str) -> List[float]:
        """Extract monetary amounts from text"""
        import re
        
        # Patterns for various amount formats
        patterns = [
            r'\$[\d,]+\.?\d*',  # $1,000.00
            r'[\d,]+\.?\d*\s*(?:million|billion|thousand)',  # 100 million
            r'[\d,]+\.?\d*\s*RMB',  # 162,260,000 RMB
            r'[\d,]+\.?\d*\s*(?:USD|EUR|GBP)',  # Currency codes
        ]
        
        amounts = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Extract numeric part
                numeric = re.sub(r'[^\d.]', '', match.split()[0])
                try:
                    amounts.append(float(numeric))
                except:
                    continue
        
        return sorted(amounts, reverse=True)
    
    def _signatures_similar(self, sig1: str, sig2: str, threshold: float = 0.8) -> bool:
        """Check if two signatures are similar using Jaccard similarity"""
        set1 = set(sig1.split('_'))
        set2 = set(sig2.split('_'))
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        if union == 0:
            return False
        
        similarity = intersection / union
        return similarity >= threshold
    
    def _process_exhibits_for_corporate_actions(self, ticker: str, months: int) -> List[Dict]:
        """Process exhibit documents for detailed corporate actions like tender offers"""
        logger.info(f"Processing exhibits for detailed corporate actions...")
        
        exhibit_actions = []
        
        # Look for SC 13D/G, SC 14D9 (tender offer related), and key 8-K exhibits
        relevant_filings = ['SC 13D', 'SC 13G', 'SC 14D9', 'SC TO-I', 'SC TO-C']
        
        for filing_type in relevant_filings:
            try:
                documents = self.sec_client.get_documents_from_index(ticker, filing_type, months)
                
                for document in documents:
                    # Process tender offer and ownership change documents
                    actions = self._extract_from_tender_exhibits(document, filing_type)
                    if actions:
                        exhibit_actions.extend(actions)
                        logger.info(f"Extracted {len(actions)} actions from {filing_type}")
                        
            except Exception as e:
                logger.info(f"No {filing_type} filings found")
                continue
        
        # Also check 8-K exhibits that might contain tender details
        try:
            k8_documents = self.sec_client.get_documents_from_index(ticker, '8-K', months)
            for document in k8_documents:
                # Look for exhibits that indicate tender offers or major corporate actions
                exhibit_actions_from_8k = self._extract_from_8k_exhibits(document)
                if exhibit_actions_from_8k:
                    exhibit_actions.extend(exhibit_actions_from_8k)
                    
        except Exception as e:
            logger.info(f"No additional 8-K exhibit processing: {e}")
        
        return self._deduplicate_actions(exhibit_actions)
    
    def _extract_from_tender_exhibits(self, document: str, filing_type: str) -> List[Dict]:
        """Extract corporate actions from tender offer and ownership documents"""
        
        prompt = f"""
You are analyzing a {filing_type} document to extract TENDER OFFERS, PROXY CONTESTS, and OWNERSHIP CHANGES.

Focus on extracting:
1. **Tender Offers**: Offers to purchase shares at specific prices
2. **Proxy Contests**: Attempts to gain control through shareholder votes  
3. **Ownership Changes**: Significant stake acquisitions/dispositions
4. **Merger Proposals**: Acquisition offers or proposals
5. **Share Buyback Programs**: Company repurchase programs

For each action found, extract:
- Action type (tender_offer, proxy_contest, ownership_change, merger_proposal, share_buyback)
- Announcement date
- Offering price per share
- Total shares sought
- Deadline/expiration date
- Conditions and terms
- Bidder/acquirer identity

Return as JSON array. If no relevant actions found, return empty array.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                logger.warning(f"No LLM response for tender exhibits document: {filing_type}")
                return []
            
            content = response.text
            actions_data = json.loads(content)
            
            standardized_actions = []
            for action_data in actions_data:
                standardized_action = self._standardize_action(action_data, filing_type, 1) # Use a placeholder counter for exhibits
                if standardized_action:
                    standardized_actions.append(standardized_action)
            
            return standardized_actions
            
        except Exception as e:
            logger.error(f"Error processing {filing_type} document: {e}")
            return []
    
    def _extract_from_8k_exhibits(self, document: str) -> List[Dict]:
        """Extract corporate actions from 8-K exhibit documents"""
        
        # Look for exhibit keywords that suggest corporate actions
        exhibit_keywords = ['tender', 'offer', 'merger', 'acquisition', 'buyback', 'repurchase', 'exchange offer']
        
        doc_lower = document.lower()
        if not any(keyword in doc_lower for keyword in exhibit_keywords):
            return []
        
        prompt = f"""
You are analyzing an 8-K filing that may contain DETAILED CORPORATE ACTION information in exhibits.

Look for exhibits (EX-99, EX-10, etc.) that contain:
1. **Tender Offer Details**: Complete terms, pricing, conditions
2. **Exchange Offer Terms**: Security swaps, conversion offers  
3. **Merger/Acquisition Details**: Purchase agreements, LOIs
4. **Share Buyback Details**: Program terms, authorization amounts
5. **Spin-off Information**: Distribution details, record dates

Extract comprehensive details including:
- Exact offer terms and pricing
- Timeline and deadlines  
- Conditions precedent
- Regulatory requirements
- Financial metrics (premiums, valuations)

Return as JSON array with detailed action objects.
"""
        
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                logger.warning(f"No LLM response for 8-K exhibits document.")
                return []
            
            content = response.text
            actions_data = json.loads(content)
            
            standardized_actions = []
            for action_data in actions_data:
                standardized_action = self._standardize_action(action_data, '8-K-EXHIBIT', 1) # Use a placeholder counter for exhibits
                if standardized_action:
                    standardized_actions.append(standardized_action)
            
            return standardized_actions
            
        except Exception as e:
            logger.error(f"Error processing 8-K exhibits: {e}")
            return []

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string to date object."""
        if not date_str:
            return None
        try:
            if isinstance(date_str, str):
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            return date_str
        except:
            return None
    
    def _parse_float(self, value) -> Optional[float]:
        """Parse various formats to float."""
        if value is None or value == '':
            return None
        try:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                # Remove common formatting
                cleaned = value.replace(',', '').replace('$', '').replace('%', '').strip()
                if cleaned:
                    return float(cleaned)
        except:
            pass
        return None
    
    def _extract_directors_from_text(self, text: str) -> List[str]:
        """Extract director names from text description."""
        directors = []
        text_lower = text.lower()
        
        # Common patterns for director names
        import re
        
        # Look for patterns like "elected John Smith, Jane Doe, and Bob Johnson"
        # or "directors: John Smith, Jane Doe, Bob Johnson"
        patterns = [
            r'elected\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:,\s*[A-Z][a-z]+\s+[A-Z][a-z]+)*)',
            r'directors[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+(?:,\s*[A-Z][a-z]+\s+[A-Z][a-z]+)*)',
            r'nominees[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+(?:,\s*[A-Z][a-z]+\s+[A-Z][a-z]+)*)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Split on commas and 'and'
                names = re.split(r',\s*(?:and\s+)?', match)
                directors.extend([name.strip() for name in names if name.strip()])
        
        return list(set(directors))  # Remove duplicates
    
    def _extract_say_on_pay_result(self, text: str) -> Optional[bool]:
        """Extract say-on-pay voting result from text."""
        text_lower = text.lower()
        if 'say on pay' in text_lower or 'compensation' in text_lower:
            if 'approved' in text_lower or 'ratified' in text_lower:
                return True
            elif 'rejected' in text_lower or 'failed' in text_lower:
                return False
        return None
    
    def _extract_auditor_ratification(self, text: str) -> Optional[bool]:
        """Extract auditor ratification result from text."""
        text_lower = text.lower()
        auditor_terms = ['auditor', 'accounting firm', 'ernst', 'young', 'deloitte', 'kpmg', 'pwc']
        
        if any(term in text_lower for term in auditor_terms):
            if 'ratified' in text_lower or 'approved' in text_lower:
                return True
            elif 'rejected' in text_lower or 'failed' in text_lower:
                return False
        return None
    
    def _extract_auditor_name(self, text: str) -> Optional[str]:
        """Extract auditor name from text."""
        auditors = ['Ernst & Young', 'Deloitte', 'KPMG', 'PwC', 'PricewaterhouseCoopers']
        text_lower = text.lower()
        
        for auditor in auditors:
            if auditor.lower() in text_lower:
                return auditor
        
        # Look for "LLP" pattern
        import re
        llp_match = re.search(r'([A-Z][a-zA-Z\s&]+LLP)', text)
        if llp_match:
            return llp_match.group(1).strip()
        
        return None
    
    def _extract_old_jurisdiction(self, text: str) -> Optional[str]:
        """Extract old jurisdiction from redomestication text."""
        text_lower = text.lower()
        jurisdictions = ['delaware', 'nevada', 'california', 'new york', 'texas', 'florida']
        
        for jurisdiction in jurisdictions:
            if f'from {jurisdiction}' in text_lower:
                return jurisdiction.title()
        
        return None
    
    def _extract_new_jurisdiction(self, text: str) -> Optional[str]:
        """Extract new jurisdiction from redomestication text."""
        text_lower = text.lower()
        jurisdictions = ['indiana', 'delaware', 'nevada', 'california', 'new york', 'texas', 'florida']
        
        for jurisdiction in jurisdictions:
            if f'to {jurisdiction}' in text_lower or f'{jurisdiction} corporation' in text_lower:
                return jurisdiction.title()
        
        return None
    
    def _extract_redomestication_reasons(self, text: str) -> List[str]:
        """Extract reasons for redomestication from text."""
        reasons = []
        text_lower = text.lower()
        
        reason_keywords = {
            'cost savings': ['cost', 'expense', 'saving'],
            'regulatory benefits': ['regulatory', 'compliance'],
            'governance flexibility': ['governance', 'flexibility'],
            'tax benefits': ['tax', 'taxation']
        }
        
        for reason, keywords in reason_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                reasons.append(reason)
        
        return reasons
    
    def _extract_series_name(self, text: str) -> Optional[str]:
        """Extract preferred stock series name from text."""
        import re
        # Look for patterns like "Series J", "Series A", etc.
        match = re.search(r'[Ss]eries\s+([A-Z])', text)
        if match:
            return f"Series {match.group(1)}"
        return None
    
    def _extract_dividend_rate(self, text: str) -> Optional[float]:
        """Extract dividend rate from text."""
        import re
        # Look for percentage patterns like "8.375%", "8 3/8%"
        patterns = [
            r'(\d+\.?\d*)\s*%',
            r'(\d+)\s*(\d+)/(\d+)\s*%'  # For fractional percentages like "8 3/8%"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 1:
                    return float(match.group(1))
                elif len(match.groups()) == 3:
                    # Convert fraction to decimal
                    whole = int(match.group(1))
                    numerator = int(match.group(2))
                    denominator = int(match.group(3))
                    return whole + (numerator / denominator)
        
        return None

def main():
    """Main function for command line usage."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 corporate_actions_extractor.py <TICKER> [MONTHS_BACK]")
        print("Example: python3 corporate_actions_extractor.py BW 12")
        sys.exit(1)
    
    ticker = sys.argv[1].upper()
    months_back = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    
    print(f"🔍 Extracting standardized corporate actions for {ticker} (last {months_back} months)")
    
    extractor = CorporateActionsExtractor()
    actions = extractor.extract_actions(ticker, months_back)
    
    if actions:
        print(f"\n✅ Found {len(actions)} unique corporate actions:")
        
        # Group by type for summary
        by_type = {}
        for action in actions:
            action_type = action['action_type']
            by_type[action_type] = by_type.get(action_type, 0) + 1
        
        for action_type, count in by_type.items():
            print(f"📋 {action_type.replace('_', ' ').title()}: {count}")
        
        print(f"\n💾 Standardized results saved to output/{ticker}_corporate_actions.json")
    else:
        print(f"❌ No corporate actions found for {ticker}")

if __name__ == "__main__":
    main() 