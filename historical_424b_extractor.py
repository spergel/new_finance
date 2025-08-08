#!/usr/bin/env python3
"""
Historical 424B Extractor

This extractor searches for ALL historical 424B filings (424B1-424B9) 
and S-1/S-3 shelf registrations going back many years to find original 
offering terms, conversion features, and detailed securities information.
"""

import os
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, date
from sec_api_client import SECAPIClient
from models import SecurityData, SecurityType, ConversionTerms, MetricsSummary, OriginalDataReference

# Load environment variables for LLM
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
logger = logging.getLogger(__name__)

class Historical424BExtractor:
    """
    Extractor for historical 424B filings and S-1/S-3 shelf registrations.
    
    This searches for ALL 424B subtypes and shelf registrations going back many years 
    to capture original offering documents and shelf registrations that contain detailed 
    conversion terms, redemption conditions, and other securities features.
    
    Uses LLM analysis to extract structured SecurityData objects.
    """
    
    def __init__(self, data_dir: str = "output"):
        """Initialize the historical extractor."""
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.sec_client = SECAPIClient(data_dir="historical_424b_data")
        
        # All filing types to search for - 424B offerings + shelf registrations
        self.filing_types = [
            "424B1", "424B2", "424B3", "424B4", "424B5", 
            "424B7", "424B8", "424B9", "424B",
            "S-1", "S-1/A", "S-3", "S-3/A"  # Shelf registration filings
        ]
        
        # Initialize LLM
        api_key = os.getenv('GOOGLE_API_KEY')
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.0-flash-lite')
                logger.info("Historical extractor initialized with Gemini 2.0 Flash-Lite")
            except Exception as e:
                logger.error(f"Failed to initialize LLM model: {e}")
                self.model = None
        else:
            logger.warning("No GOOGLE_API_KEY found. LLM extraction will be disabled.")
            self.model = None
    
    def extract_all_historical_424b(self, ticker: str, years_back: int = 10) -> Dict[str, List[str]]:
        """
        Extract ALL historical 424B filings for a company.
        
        Args:
            ticker: Company ticker symbol
            years_back: How many years back to search (default: 10)
            
        Returns:
            Dictionary mapping filing type to list of file paths
        """
        logger.info(f"Starting historical 424B extraction for {ticker} (last {years_back} years)")
        
        months_back = years_back * 12  # Convert years to months
        all_filings = {}
        
        for filing_type in self.filing_types:
            logger.info(f"Searching for historical {filing_type} filings...")
            
            try:
                # Use the comprehensive search to find ALL historical filings
                filing_paths = self.sec_client.download_filings_by_date_range(
                    ticker=ticker,
                    filing_types=[filing_type],
                    months_back=months_back
                )
                
                if filing_paths:
                    all_filings[filing_type] = filing_paths
                    logger.info(f"Found {len(filing_paths)} {filing_type} historical filings")
                    
                    # Print some info about each filing
                    for path in filing_paths:
                        if os.path.exists(path):
                            size = os.path.getsize(path)
                            logger.info(f"  - {path} ({size:,} bytes)")
                else:
                    logger.info(f"No {filing_type} historical filings found")
                    
            except Exception as e:
                logger.error(f"Error searching for {filing_type}: {e}")
                continue
        
        # Save summary
        summary = {
            "ticker": ticker,
            "search_years": years_back,
            "extraction_date": datetime.now().isoformat(),
            "filings_found": {filing_type: len(paths) for filing_type, paths in all_filings.items()},
            "total_filings": sum(len(paths) for paths in all_filings.values()),
            "filing_details": all_filings
        }
        
        summary_file = os.path.join(self.data_dir, f"{ticker}_historical_424b_summary.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Historical 424B extraction complete for {ticker}")
        logger.info(f"Total filings found: {summary['total_filings']}")
        logger.info(f"Summary saved to: {summary_file}")
        
        return all_filings
    
    def analyze_filing_content(self, ticker: str, filing_paths: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Analyze the content of downloaded 424B filings to extract key information.
        
        Args:
            ticker: Company ticker symbol
            filing_paths: Dictionary of filing type to file paths
            
        Returns:
            Analysis results
        """
        logger.info(f"Analyzing 424B filing content for {ticker}")
        
        analysis = {
            "ticker": ticker,
            "analysis_date": datetime.now().isoformat(),
            "filings_analyzed": {},
            "key_findings": {
                "convertible_securities": [],
                "debt_securities": [],
                "preferred_stock": [],
                "warrants": [],
                "offering_amounts": [],
                "conversion_prices": [],
                "redemption_terms": [],
                "shelf_registrations": [] # New category for shelf registrations
            }
        }
        
        for filing_type, paths in filing_paths.items():
            logger.info(f"Analyzing {filing_type} filings...")
            filing_analysis = []
            
            for path in paths:
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Extract key information using pattern matching
                    file_analysis = self._analyze_single_filing(content, filing_type)
                    file_analysis['file_path'] = path
                    file_analysis['file_size'] = os.path.getsize(path)
                    
                    filing_analysis.append(file_analysis)
                    
                    # Add to key findings
                    self._update_key_findings(analysis['key_findings'], file_analysis)
                    
                except Exception as e:
                    logger.error(f"Error analyzing {path}: {e}")
                    continue
            
            analysis['filings_analyzed'][filing_type] = filing_analysis
        
        # Save analysis
        analysis_file = os.path.join(self.data_dir, f"{ticker}_424b_content_analysis.json")
        with open(analysis_file, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        
        logger.info(f"Content analysis saved to: {analysis_file}")
        return analysis
    
    def analyze_shelf_registrations(self, ticker: str, filing_paths: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Analyze S-1 shelf registrations separately to identify registered securities.
        
        Args:
            ticker: Company ticker symbol
            filing_paths: Dictionary of filing type to file paths
            
        Returns:
            Analysis of shelf registrations
        """
        logger.info(f"Analyzing shelf registrations for {ticker}")
        
        shelf_analysis = {
            "ticker": ticker,
            "analysis_date": datetime.now().isoformat(),
            "shelf_registrations": [],
            "registered_securities": {
                "debt_securities": [],
                "equity_securities": [],
                "preferred_stock": [],
                "warrants": [],
                "other": []
            }
        }
        
        for filing_type in ["S-1", "S-1/A", "S-3", "S-3/A"]:
            if filing_type not in filing_paths:
                continue
                
            for path in filing_paths[filing_type]:
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    shelf_info = self._analyze_shelf_filing(content, filing_type, path)
                    shelf_analysis['shelf_registrations'].append(shelf_info)
                    
                    # Categorize registered securities
                    for security in shelf_info.get('registered_securities', []):
                        sec_type = security.get('type', 'other').lower()
                        if 'debt' in sec_type or 'note' in sec_type or 'bond' in sec_type:
                            shelf_analysis['registered_securities']['debt_securities'].append(security)
                        elif 'common' in sec_type or 'equity' in sec_type:
                            shelf_analysis['registered_securities']['equity_securities'].append(security)
                        elif 'preferred' in sec_type:
                            shelf_analysis['registered_securities']['preferred_stock'].append(security)
                        elif 'warrant' in sec_type:
                            shelf_analysis['registered_securities']['warrants'].append(security)
                        else:
                            shelf_analysis['registered_securities']['other'].append(security)
                    
                except Exception as e:
                    logger.error(f"Error analyzing shelf filing {path}: {e}")
                    continue
        
        # Save shelf analysis
        shelf_file = os.path.join(self.data_dir, f"{ticker}_shelf_registrations.json")
        with open(shelf_file, 'w') as f:
            json.dump(shelf_analysis, f, indent=2, default=str)
        
        logger.info(f"Shelf registration analysis saved to: {shelf_file}")
        return shelf_analysis
    
    def extract_historical_securities(self, ticker: str, years_back: int = 10) -> List[SecurityData]:
        """
        Extract ALL historical securities from 424B filings and shelf registrations.
        
        Args:
            ticker: Company ticker symbol
            years_back: How many years back to search (default: 10)
            
        Returns:
            List of SecurityData objects with shelf_registration markers
        """
        logger.info(f"Starting historical securities extraction for {ticker} (last {years_back} years)")
        
        if not self.model:
            logger.error("LLM model not available. Cannot perform structured extraction.")
            return []
        
        # Download all historical filings
        all_filings = self.extract_all_historical_424b(ticker, years_back)
        
        if not all_filings:
            logger.warning(f"No historical filings found for {ticker}")
            return []
        
        all_securities = []
        
        # Process each filing type
        for filing_type, file_paths in all_filings.items():
            logger.info(f"Processing {filing_type} filings: {len(file_paths)} files")
            
            for file_path in file_paths:
                try:
                    securities = self._extract_securities_from_file(file_path, filing_type, ticker)
                    if securities:
                        all_securities.extend(securities)
                        logger.info(f"Extracted {len(securities)} securities from {file_path}")
                
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    continue
        
        # Save results
        if all_securities:
            output_file = os.path.join(self.data_dir, f"{ticker}_historical_securities.json")
            securities_dict = [self._security_to_dict(s) for s in all_securities]
            
            with open(output_file, 'w') as f:
                json.dump({
                    "ticker": ticker,
                    "extraction_date": datetime.now().isoformat(),
                    "years_searched": years_back,
                    "total_securities": len(all_securities),
                    "securities": securities_dict
                }, f, indent=2, default=str)
            
            logger.info(f"Historical securities saved to: {output_file}")
        
        return all_securities
    
    def _analyze_single_filing(self, content: str, filing_type: str) -> Dict[str, Any]:
        """Analyze a single filing's content."""
        import re
        
        content_lower = content.lower()
        analysis = {
            "filing_type": filing_type,
            "contains_convertible": False,
            "contains_debt": False,
            "contains_preferred": False,
            "contains_warrants": False,
            "dollar_amounts": [],
            "conversion_prices": [],
            "interest_rates": [],
            "key_terms": []
        }
        
        # Check for security types
        if any(term in content_lower for term in ['convertible', 'conversion']):
            analysis['contains_convertible'] = True
            analysis['key_terms'].append('convertible')
        
        if any(term in content_lower for term in ['notes', 'bonds', 'debt', 'debenture']):
            analysis['contains_debt'] = True
            analysis['key_terms'].append('debt')
        
        if any(term in content_lower for term in ['preferred stock', 'preferred shares']):
            analysis['contains_preferred'] = True
            analysis['key_terms'].append('preferred_stock')
        
        if 'warrant' in content_lower:
            analysis['contains_warrants'] = True
            analysis['key_terms'].append('warrants')
        
        # Extract dollar amounts
        dollar_pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion))?'
        dollar_amounts = re.findall(dollar_pattern, content, re.IGNORECASE)
        analysis['dollar_amounts'] = list(set(dollar_amounts[:10]))  # Limit to 10 unique amounts
        
        # Extract conversion prices
        conversion_patterns = [
            r'conversion price of \$?([\d,]+\.?\d*)',
            r'convertible at \$?([\d,]+\.?\d*)',
            r'conversion ratio of ([\d,]+\.?\d*)'
        ]
        
        for pattern in conversion_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            analysis['conversion_prices'].extend(matches)
        
        # Extract interest rates
        rate_pattern = r'(\d+\.?\d*)%'
        rates = re.findall(rate_pattern, content)
        analysis['interest_rates'] = list(set(rates[:5]))  # Limit to 5 unique rates
        
        return analysis
    
    def _analyze_shelf_filing(self, content: str, filing_type: str, file_path: str) -> Dict[str, Any]:
        """Analyze a single S-1 shelf filing."""
        import re
        
        content_lower = content.lower()
        
        shelf_info = {
            "filing_type": filing_type,
            "file_path": file_path,
            "file_size": len(content),
            "is_shelf_registration": True,
            "registered_securities": [],
            "total_shelf_amount": None,
            "key_terms": []
        }
        
        # Look for shelf registration amount
        shelf_amount_patterns = [
            r'aggregate offering price.*?\$?([\d,]+(?:\.\d+)?)\s*(?:million|billion)?',
            r'maximum aggregate offering price.*?\$?([\d,]+(?:\.\d+)?)\s*(?:million|billion)?',
            r'total.*?\$?([\d,]+(?:\.\d+)?)\s*(?:million|billion)?.*?may be offered'
        ]
        
        for pattern in shelf_amount_patterns:
            matches = re.findall(pattern, content_lower)
            if matches:
                shelf_info['total_shelf_amount'] = matches[0]
                break
        
        # Look for types of securities registered
        security_patterns = {
            'debt_securities': [
                r'debt securities',
                r'senior notes',
                r'subordinated notes', 
                r'convertible notes',
                r'bonds'
            ],
            'equity_securities': [
                r'common stock',
                r'ordinary shares'
            ],
            'preferred_stock': [
                r'preferred stock',
                r'preference shares'
            ],
            'warrants': [
                r'warrants',
                r'rights to purchase'
            ]
        }
        
        for sec_type, patterns in security_patterns.items():
            for pattern in patterns:
                if pattern in content_lower:
                    shelf_info['registered_securities'].append({
                        'type': sec_type,
                        'description': pattern,
                        'found_in_text': True
                    })
                    if sec_type not in shelf_info['key_terms']:
                        shelf_info['key_terms'].append(sec_type)
        
        # Look for specific interest rates or terms that might indicate actual securities
        rate_pattern = r'(\d+\.?\d*)%'
        rates = re.findall(rate_pattern, content)
        if rates:
            shelf_info['interest_rates_mentioned'] = list(set(rates[:10]))  # Limit to 10
        
        return shelf_info
    
    def _update_key_findings(self, key_findings: Dict, file_analysis: Dict):
        """Update the key findings with information from a single file."""
        
        if file_analysis['contains_convertible']:
            key_findings['convertible_securities'].append({
                'filing_type': file_analysis['filing_type'],
                'conversion_prices': file_analysis['conversion_prices']
            })
        
        if file_analysis['contains_debt']:
            key_findings['debt_securities'].append({
                'filing_type': file_analysis['filing_type'],
                'interest_rates': file_analysis['interest_rates']
            })
        
        if file_analysis['contains_preferred']:
            key_findings['preferred_stock'].append({
                'filing_type': file_analysis['filing_type']
            })
        
        if file_analysis['contains_warrants']:
            key_findings['warrants'].append({
                'filing_type': file_analysis['filing_type']
            })
        
        # Add dollar amounts and other findings
        key_findings['offering_amounts'].extend(file_analysis['dollar_amounts'])
        key_findings['conversion_prices'].extend(file_analysis['conversion_prices'])

        # Add shelf registrations
        if file_analysis['filing_type'] in ["S-1", "S-1/A", "S-3", "S-3/A"]:
            key_findings['shelf_registrations'].append({
                'filing_type': file_analysis['filing_type'],
                'file_path': file_analysis['file_path']
            })

    def _extract_securities_from_file(self, file_path: str, filing_type: str, ticker: str) -> List[SecurityData]:
        """Extract securities from a single filing using LLM."""
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Determine if this is a shelf registration
        is_shelf_registration = filing_type in ["S-1", "S-1/A", "S-3", "S-3/A"]
        
        # Create LLM prompt
        prompt = self._create_extraction_prompt(ticker, content, filing_type, is_shelf_registration)
        
        # Call LLM
        try:
            response = self.model.generate_content(prompt)
            if not response.text:
                logger.warning(f"No LLM response for {file_path}")
                return []
            
            # Parse response and convert to SecurityData objects
            securities_data = self._parse_llm_response(response.text)
            securities = []
            
            for sec_data in securities_data:
                try:
                    security = self._convert_to_security_data(sec_data, ticker, filing_type, is_shelf_registration)
                    if security:
                        securities.append(security)
                except Exception as e:
                    logger.error(f"Error converting security data: {e}")
                    continue
            
            return securities
            
        except Exception as e:
            logger.error(f"Error in LLM extraction for {file_path}: {e}")
            return []
    
    def _create_extraction_prompt(self, ticker: str, content: str, filing_type: str, is_shelf: bool) -> str:
        """Create LLM prompt for extracting securities."""
        
        shelf_context = ""
        if is_shelf:
            shelf_context = """
IMPORTANT: This is a SHELF REGISTRATION filing. Look for:
- Securities that are REGISTERED for potential future issuance
- Maximum offering amounts and shelf capacity
- Types of securities authorized for issuance
- Registration terms and conditions
"""
        else:
            shelf_context = """
IMPORTANT: This is an ACTUAL OFFERING filing. Look for:
- Securities that are being ACTUALLY ISSUED/OFFERED
- Specific offering prices and terms
- Actual conversion and redemption terms
- Transaction-specific details
"""
        
        prompt = f"""
You are analyzing a {filing_type} filing for {ticker} to extract detailed securities information.

{shelf_context}

Extract ALL securities mentioned in this filing. For each security, provide:

1. BASIC INFO: Type, description, principal amount, interest rate, maturity
2. CONVERSION TERMS: Conversion price, ratio, conditions, VWAP terms
3. REDEMPTION TERMS: Call conditions, prices, notice periods
4. SPECIAL FEATURES: Make-whole, anti-dilution, hedging

Here's the filing content (first 100,000 characters):

{content[:100000]}

Return a JSON object with this structure:

{{
    "securities": [
        {{
            "id": "unique_identifier",
            "type": "convertible_debt|debt_instrument|preferred_stock|warrant|corporate_action",
            "description": "detailed description",
            "principal_amount": 150000000.0,
            "interest_rate": 8.125,
            "maturity_date": "2026-02-28",
            "conversion_price": 15.50,
            "conversion_ratio": 64.516,
            "redemption_conditions": ["130% of conversion price for 20 days"],
            "is_shelf_registration": {str(is_shelf).lower()},
            "filing_source": "{filing_type}",
            "raw_text_excerpt": "relevant excerpt from filing"
        }}
    ]
}}

Return ONLY valid JSON, no additional text.
"""
        return prompt
    
    def _parse_llm_response(self, response_text: str) -> List[Dict]:
        """Parse the LLM response to extract JSON."""
        try:
            # Clean the response text
            cleaned_response = response_text.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            # Parse JSON
            data = json.loads(cleaned_response.strip())
            return data.get('securities', [])
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from LLM response: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return []
    
    def _convert_to_security_data(self, sec_data: Dict, ticker: str, filing_type: str, is_shelf: bool) -> SecurityData:
        """Convert LLM-extracted data to SecurityData object."""
        
        # Parse dates safely
        def safe_parse_date(date_str):
            if not date_str or date_str == 'N/A':
                return None
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                return None
        
        # Create conversion terms if available
        conversion_terms = None
        if sec_data.get('conversion_price') or sec_data.get('conversion_ratio'):
            conversion_terms = ConversionTerms(
                conversion_price=sec_data.get('conversion_price'),
                conversion_ratio=sec_data.get('conversion_ratio'),
                vwap_based=bool(sec_data.get('vwap_terms')),
                has_auto_conversion=sec_data.get('auto_conversion', False)
            )
        
        # Create metrics summary
        metrics = MetricsSummary(
            principal_amount=sec_data.get('principal_amount'),
            coupon_rate=sec_data.get('interest_rate'),
            conversion_price=sec_data.get('conversion_price'),
            conversion_ratio=sec_data.get('conversion_ratio'),
            redemption_price=sec_data.get('redemption_price'),
            maturity_date=safe_parse_date(sec_data.get('maturity_date'))
        )
        
        # Create original data reference with shelf marker
        original_ref = OriginalDataReference(
            id=sec_data.get('id'),
            has_raw_conversion_features=bool(conversion_terms),
            has_raw_redemption_features=bool(sec_data.get('redemption_conditions')),
            has_special_features=bool(sec_data.get('make_whole') or sec_data.get('hedging')),
            llm_commentary=f"Shelf Registration: {is_shelf}"
        )
        
        # Create SecurityData object
        security = SecurityData(
            id=sec_data.get('id', f"{ticker}_{filing_type}_{datetime.now().timestamp()}"),
            company=ticker,
            type=sec_data.get('type', 'unknown'),
            filing_date=date.today(),  # We'll use today as filing date for now
            principal_amount=sec_data.get('principal_amount'),
            rate=sec_data.get('interest_rate'),
            maturity_date=safe_parse_date(sec_data.get('maturity_date')),
            description=sec_data.get('description', ''),
            raw_description=sec_data.get('raw_text_excerpt', ''),
            filing_source=filing_type,
            conversion_terms=conversion_terms,
            metrics=metrics,
            has_make_whole_provisions=sec_data.get('make_whole', False),
            has_hedging=sec_data.get('hedging', False),
            llm_commentary=f"Extracted from {filing_type}. Shelf registration: {is_shelf}",
            original_data_reference=original_ref
        )
        
        return security
    
    def _security_to_dict(self, security: SecurityData) -> Dict:
        """Convert SecurityData object to dict for JSON serialization."""
        return {
            "id": security.id,
            "company": security.company,
            "type": security.type,
            "filing_date": security.filing_date.isoformat() if security.filing_date else None,
            "principal_amount": security.principal_amount,
            "rate": security.rate,
            "maturity_date": security.maturity_date.isoformat() if security.maturity_date else None,
            "description": security.description,
            "raw_description": security.raw_description,
            "filing_source": security.filing_source,
            "conversion_terms": security.conversion_terms.dict() if security.conversion_terms else None,
            "metrics": security.metrics.dict() if security.metrics else None,
            "has_make_whole_provisions": security.has_make_whole_provisions,
            "has_hedging": security.has_hedging,
            "llm_commentary": security.llm_commentary,
            "original_data_reference": security.original_data_reference.dict() if security.original_data_reference else None,
            "is_shelf_registration": "Shelf registration: True" in (security.llm_commentary or "")
        }

def main():
    """Example usage of the historical extractor."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 historical_424b_extractor.py <TICKER> [YEARS_BACK]")
        print("Example: python3 historical_424b_extractor.py BW 10")
        sys.exit(1)
    
    ticker = sys.argv[1].upper()
    years_back = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    print(f"🔍 Extracting historical securities for {ticker} (last {years_back} years)")
    
    extractor = Historical424BExtractor()
    
    # Extract all historical securities using LLM
    securities = extractor.extract_historical_securities(ticker, years_back)
    
    if securities:
        print(f"\n✅ Extracted {len(securities)} securities:")
        
        # Group by filing type and shelf status
        shelf_securities = [s for s in securities if "Shelf registration: True" in (s.llm_commentary or "")]
        offering_securities = [s for s in securities if "Shelf registration: False" in (s.llm_commentary or "")]
        
        print(f"\n📋 Shelf Registrations: {len(shelf_securities)}")
        for security in shelf_securities[:5]:  # Show first 5
            print(f"  • {security.type}: {security.description[:80]}...")
        
        print(f"\n🎯 Actual Offerings: {len(offering_securities)}")
        for security in offering_securities[:5]:  # Show first 5
            print(f"  • {security.type}: {security.description[:80]}...")
        
        # Show summary by security type
        print(f"\n📊 Securities by Type:")
        type_counts = {}
        for security in securities:
            sec_type = security.type
            type_counts[sec_type] = type_counts.get(sec_type, 0) + 1
        
        for sec_type, count in type_counts.items():
            print(f"  {sec_type}: {count}")
        
        print(f"\n💾 Results saved to: output/{ticker}_historical_securities.json")
    
    else:
        print(f"❌ No historical securities found for {ticker}")

if __name__ == "__main__":
    main() 