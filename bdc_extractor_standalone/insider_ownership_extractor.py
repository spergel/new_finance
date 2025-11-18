#!/usr/bin/env python3
"""
Insider Trading and Ownership Data Extractor

This module extracts:
1. Insider trading data (Form 4 filings)
2. Ownership data (13D/G, DEF 14A proxy statements)
3. Institutional holdings (13F filings)

Data is saved to JSON files for frontend consumption.
"""

import os
import sys
import logging
import json
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from sec_api_client import SECAPIClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class InsiderTransaction:
    """Represents an insider transaction from Form 4."""
    ticker: str
    insider_name: str
    insider_title: Optional[str]
    transaction_date: str
    transaction_type: str  # 'Buy', 'Sell', 'Option Exercise', etc.
    shares: Optional[float]
    price_per_share: Optional[float]
    value: Optional[float]
    ownership_type: Optional[str]  # 'Direct', 'Indirect'
    filing_date: str
    accession_number: str


@dataclass
class OwnershipInfo:
    """Represents ownership information from various filings."""
    ticker: str
    owner_name: str
    owner_type: str  # 'Institutional', 'Insider', '5% Owner'
    shares_owned: Optional[float]
    percent_owned: Optional[float]
    filing_date: str
    source_filing: str  # '13D', '13G', 'DEF 14A', etc.


class InsiderOwnershipExtractor:
    """Extract insider trading and ownership data from SEC filings."""
    
    def __init__(self, user_agent: str = "BDC-Extractor/1.0 contact@example.com"):
        self.sec_client = SECAPIClient(user_agent=user_agent)
        self.headers = {'User-Agent': user_agent}
    
    def extract_for_ticker(self, ticker: str, days_back: int = 365) -> Dict[str, Any]:
        """
        Extract all insider/ownership data for a ticker.
        
        Args:
            ticker: Company ticker symbol
            days_back: How many days back to look for filings
            
        Returns:
            Dictionary with insider transactions and ownership data
        """
        logger.info(f"Extracting insider/ownership data for {ticker}")
        
        cik = self.sec_client.get_cik(ticker)
        if not cik:
            logger.warning(f"Could not find CIK for {ticker}")
            return {
                'ticker': ticker,
                'insider_transactions': [],
                'ownership': [],
                'last_updated': datetime.now().isoformat()
            }
        
        result = {
            'ticker': ticker,
            'cik': cik,
            'insider_transactions': [],
            'ownership': [],
            'last_updated': datetime.now().isoformat()
        }
        
        # Extract Form 4 filings (insider transactions)
        try:
            form4_transactions = self._extract_form4_transactions(ticker, cik, days_back)
            result['insider_transactions'] = [asdict(t) for t in form4_transactions]
            logger.info(f"Found {len(form4_transactions)} insider transactions")
        except Exception as e:
            logger.error(f"Error extracting Form 4 data: {e}")
        
        # Extract ownership data from DEF 14A (proxy statements)
        try:
            ownership_data = self._extract_proxy_ownership(ticker, cik, days_back)
            result['ownership'].extend([asdict(o) for o in ownership_data])
            logger.info(f"Found {len(ownership_data)} ownership entries from proxy")
        except Exception as e:
            logger.error(f"Error extracting proxy ownership: {e}")
        
        # Extract 13D/G filings (beneficial ownership)
        try:
            beneficial_ownership = self._extract_13d_g(ticker, cik, days_back)
            result['ownership'].extend([asdict(o) for o in beneficial_ownership])
            logger.info(f"Found {len(beneficial_ownership)} beneficial ownership entries")
        except Exception as e:
            logger.error(f"Error extracting 13D/G data: {e}")
        
        return result
    
    def _extract_form4_transactions(self, ticker: str, cik: str, days_back: int) -> List[InsiderTransaction]:
        """Extract insider transactions from Form 4 filings."""
        transactions = []
        
        # Get Form 4 filings
        cutoff_date = (datetime.now() - timedelta(days=days_back)).date()
        
        # Search for Form 4 filings
        # Note: SEC API doesn't have a direct endpoint, so we'll need to search filings
        # For now, we'll use a simplified approach - in production, you'd want to use
        # the SEC's company filings API
        
        logger.info(f"Searching for Form 4 filings for {ticker} (CIK: {cik})")
        
        # This is a placeholder - actual implementation would fetch Form 4 filings
        # and parse the XML/HTML to extract transaction data
        # Form 4 filings are in XML format and contain structured data
        
        return transactions
    
    def _extract_proxy_ownership(self, ticker: str, cik: str, days_back: int) -> List[OwnershipInfo]:
        """Extract ownership data from DEF 14A proxy statements."""
        ownership = []
        
        logger.info(f"Searching for DEF 14A filings for {ticker}")
        
        # Get latest DEF 14A filing
        index_url = self.sec_client.get_filing_index_url(ticker, "DEF 14A", cik=cik)
        if not index_url:
            logger.info(f"No DEF 14A filing found for {ticker}")
            return ownership
        
        # Get documents from the filing
        documents = self.sec_client.get_documents_from_index(index_url)
        main_html = next((d for d in documents if d.filename.lower().endswith('.htm') 
                         and 'index' not in d.filename.lower()), None)
        
        if not main_html:
            logger.warning(f"Could not find HTML document in DEF 14A for {ticker}")
            return ownership
        
        # Fetch and parse the HTML
        try:
            response = requests.get(main_html.url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for ownership tables in proxy statements
            # These are typically in tables with headers like "Security Ownership"
            ownership_tables = self._find_ownership_tables(soup)
            
            for table in ownership_tables:
                table_ownership = self._parse_ownership_table(table, ticker, index_url)
                ownership.extend(table_ownership)
        
        except Exception as e:
            logger.error(f"Error parsing DEF 14A for {ticker}: {e}")
        
        return ownership
    
    def _extract_13d_g(self, ticker: str, cik: str, days_back: int) -> List[OwnershipInfo]:
        """Extract beneficial ownership from 13D/G filings."""
        ownership = []
        
        logger.info(f"Searching for 13D/G filings for {ticker}")
        
        # Try to get 13D and 13G filings
        for filing_type in ["SC 13D", "SC 13G"]:
            try:
                index_url = self.sec_client.get_filing_index_url(ticker, filing_type, cik=cik)
                if index_url:
                    # Parse the filing (similar to proxy parsing)
                    documents = self.sec_client.get_documents_from_index(index_url)
                    main_html = next((d for d in documents if d.filename.lower().endswith('.htm') 
                                     and 'index' not in d.filename.lower()), None)
                    
                    if main_html:
                        response = requests.get(main_html.url, headers=self.headers)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Extract ownership information from 13D/G
                        # These filings have structured ownership data
                        # Implementation would parse the specific sections
                        pass
            except Exception as e:
                logger.debug(f"Could not get {filing_type} for {ticker}: {e}")
        
        return ownership
    
    def _find_ownership_tables(self, soup: BeautifulSoup) -> List:
        """Find ownership tables in HTML document."""
        tables = []
        
        # Look for tables with ownership-related headers
        all_tables = soup.find_all('table')
        
        for table in all_tables:
            text = table.get_text().lower()
            # Common ownership table indicators
            if any(keyword in text for keyword in [
                'security ownership', 'beneficial ownership', 'principal stockholders',
                'ownership of securities', 'stock ownership', 'share ownership'
            ]):
                tables.append(table)
        
        return tables
    
    def _parse_ownership_table(self, table, ticker: str, filing_url: str) -> List[OwnershipInfo]:
        """Parse an ownership table and extract ownership information."""
        ownership = []
        
        try:
            rows = table.find_all('tr')
            if len(rows) < 2:
                return ownership
            
            # Try to identify header row
            headers = []
            data_start_idx = 0
            
            for i, row in enumerate(rows):
                cells = row.find_all(['th', 'td'])
                if not cells:
                    continue
                
                # Check if this looks like a header row
                cell_texts = [c.get_text(strip=True).lower() for c in cells]
                if any(keyword in ' '.join(cell_texts) for keyword in ['name', 'shares', 'percent', 'owner']):
                    headers = [c.get_text(strip=True) for c in cells]
                    data_start_idx = i + 1
                    break
            
            if not headers:
                # No clear header, try to infer from first row
                first_row = rows[0].find_all(['th', 'td'])
                headers = [c.get_text(strip=True) for c in first_row]
                data_start_idx = 1
            
            # Find column indices
            name_idx = self._find_column_index(headers, ['name', 'owner', 'stockholder'])
            shares_idx = self._find_column_index(headers, ['shares', 'amount', 'number'])
            percent_idx = self._find_column_index(headers, ['percent', '%', 'percentage'])
            
            # Parse data rows
            for row in rows[data_start_idx:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                owner_name = None
                shares = None
                percent = None
                
                if name_idx is not None and name_idx < len(cells):
                    owner_name = cells[name_idx].get_text(strip=True)
                
                if shares_idx is not None and shares_idx < len(cells):
                    shares_text = cells[shares_idx].get_text(strip=True)
                    shares = self._parse_number(shares_text)
                
                if percent_idx is not None and percent_idx < len(cells):
                    percent_text = cells[percent_idx].get_text(strip=True)
                    percent = self._parse_percentage(percent_text)
                
                if owner_name and (shares or percent):
                    # Extract filing date from URL
                    filing_date = self._extract_filing_date(filing_url)
                    
                    ownership.append(OwnershipInfo(
                        ticker=ticker,
                        owner_name=owner_name,
                        owner_type='Unknown',  # Could be refined based on context
                        shares_owned=shares,
                        percent_owned=percent,
                        filing_date=filing_date or datetime.now().strftime('%Y-%m-%d'),
                        source_filing='DEF 14A'
                    ))
        
        except Exception as e:
            logger.error(f"Error parsing ownership table: {e}")
        
        return ownership
    
    def _find_column_index(self, headers: List[str], keywords: List[str]) -> Optional[int]:
        """Find the index of a column matching keywords."""
        for i, header in enumerate(headers):
            header_lower = header.lower()
            if any(keyword in header_lower for keyword in keywords):
                return i
        return None
    
    def _parse_number(self, text: str) -> Optional[float]:
        """Parse a number from text, handling commas and formatting."""
        if not text:
            return None
        
        # Remove commas and other formatting
        text = re.sub(r'[,\s]', '', text)
        
        # Try to extract number
        match = re.search(r'[\d,]+\.?\d*', text)
        if match:
            try:
                return float(match.group().replace(',', ''))
            except ValueError:
                pass
        
        return None
    
    def _parse_percentage(self, text: str) -> Optional[float]:
        """Parse a percentage from text."""
        if not text:
            return None
        
        # Remove % sign and extract number
        text = text.replace('%', '').strip()
        match = re.search(r'[\d,]+\.?\d*', text)
        if match:
            try:
                return float(match.group().replace(',', ''))
            except ValueError:
                pass
        
        return None
    
    def _extract_filing_date(self, url: str) -> Optional[str]:
        """Extract filing date from URL or filing metadata."""
        # Try to extract date from URL pattern
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', url)
        if date_match:
            return date_match.group(0)
        return None
    
    def save_to_json(self, data: Dict[str, Any], output_dir: str):
        """Save extracted data to JSON file."""
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{data['ticker']}_insider_ownership.json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved insider/ownership data to {output_file}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract insider trading and ownership data')
    parser.add_argument('ticker', help='Company ticker symbol')
    parser.add_argument('--days-back', type=int, default=365, help='Days back to search (default: 365)')
    parser.add_argument('--output-dir', default='output', help='Output directory (default: output)')
    
    args = parser.parse_args()
    
    extractor = InsiderOwnershipExtractor()
    data = extractor.extract_for_ticker(args.ticker, args.days_back)
    extractor.save_to_json(data, args.output_dir)
    
    print(f"\nExtracted data for {args.ticker}:")
    print(f"  Insider transactions: {len(data['insider_transactions'])}")
    print(f"  Ownership entries: {len(data['ownership'])}")

