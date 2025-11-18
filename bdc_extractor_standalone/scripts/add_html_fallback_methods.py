#!/usr/bin/env python3
"""Helper script to add HTML fallback methods to parsers."""
import re
from pathlib import Path

HTML_FALLBACK_METHODS = '''    def _extract_html_fallback(self, filing_url: str, investments: List[{INVESTMENT_TYPE}]) -> Optional[Dict[str, Dict]]:
        """Extract optional fields from HTML as fallback when XBRL doesn't have them."""
        try:
            from flexible_table_parser import FlexibleTableParser
            
            # Get HTML URL from index - construct index URL from .txt URL
            match = re.search(r'/edgar/data/(\\d+)/(\\d+)/([^/]+)\\.txt', filing_url)
            if not match:
                logger.debug("Could not parse filing URL for HTML fallback")
                return None
            
            cik = match.group(1)
            accession_no_hyphens = match.group(2)
            filename_base = match.group(3).replace('.txt', '')
            # Construct index URL: replace the .txt filename with -index.html
            index_url = filing_url.replace(f"{filename_base}.txt", f"{filename_base}-index.html")
            
            # Get HTML document from index
            docs = self.sec_client.get_documents_from_index(index_url)
            main_doc = None
            for d in docs:
                fn = d.filename.lower() if d.filename else ''
                if fn.endswith('.htm') and 'index' not in fn:
                    main_doc = d
                    break
            
            if not main_doc:
                logger.debug(f"HTML fallback: No HTML document found in index")
                return None
            
            html_url = main_doc.url
            logger.info(f"HTML fallback: Using HTML URL: {html_url}")
            
            parser = FlexibleTableParser(user_agent=self.headers['User-Agent'])
            html_investments = parser.parse_html_filing(html_url)
            
            if not html_investments:
                logger.debug(f"HTML fallback: No investments extracted from {html_url}")
                return None
            
            logger.info(f"HTML fallback: Extracted {len(html_investments)} investments from HTML")
            
            # Create lookup by company_name (primary) and investment_type (secondary)
            html_lookup_by_name = {{}}
            html_lookup_by_name_type = {{}}
            for html_inv in html_investments:
                company_name = html_inv.get('company_name', '').strip().lower()
                investment_type = html_inv.get('investment_type', '').strip().lower()
                
                if company_name:
                    # Primary lookup: by company name only
                    if company_name not in html_lookup_by_name:
                        html_lookup_by_name[company_name] = html_inv
                    
                    # Secondary lookup: by company name + investment type
                    key = (company_name, investment_type)
                    html_lookup_by_name_type[key] = html_inv
            
            return {{
                'by_name': html_lookup_by_name,
                'by_name_type': html_lookup_by_name_type
            }}
        except Exception as e:
            logger.debug(f"HTML fallback extraction failed: {{e}}")
            return None
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for better matching."""
        if not name:
            return ""
        name = name.lower().strip()
        name = re.sub(r'\\s*(inc\\.?|incorporated|corp\\.?|corporation|ltd\\.?|limited|llc\\.?|lp\\.?|l\\.p\\.?|l\\.l\\.c\\.?)\\s*$', '', name)
        name = re.sub(r'\\s*\\([^)]*\\)\\s*', ' ', name)
        name = re.sub(r'\\s+', ' ', name).strip()
        name = re.sub(r'^(the\\s+)', '', name)
        return name
    
    def _fuzzy_match_company_names(self, name1: str, name2: str, threshold: float = 0.8) -> bool:
        """Check if two company names are similar enough to match."""
        from difflib import SequenceMatcher
        norm1 = self._normalize_company_name(name1)
        norm2 = self._normalize_company_name(name2)
        if not norm1 or not norm2:
            return False
        if norm1 == norm2:
            return True
        if norm1 in norm2 or norm2 in norm1:
            return True
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        return similarity >= threshold
    
    def _merge_html_data(self, investments: List[{INVESTMENT_TYPE}], html_data: Dict[str, Dict]):
        """Merge HTML-extracted optional fields into XBRL investments."""
        html_by_name = html_data.get('by_name', {{}})
        html_by_name_type = html_data.get('by_name_type', {{}})
        
        # Create normalized lookup for fuzzy matching
        html_by_normalized = {{}}
        for html_inv in html_by_name.values():
            company_name = html_inv.get('company_name', '').strip()
            if company_name:
                normalized = self._normalize_company_name(company_name)
                if normalized and normalized not in html_by_normalized:
                    html_by_normalized[normalized] = html_inv
        
        merged_count = 0
        for inv in investments:
            company_name_lower = inv.company_name.strip().lower()
            investment_type_lower = inv.investment_type.strip().lower()
            
            html_inv = None
            
            # Strategy 1: Try exact match first (company_name + investment_type)
            key = (company_name_lower, investment_type_lower)
            html_inv = html_by_name_type.get(key)
            
            # Strategy 2: Fallback to company name only
            if not html_inv:
                html_inv = html_by_name.get(company_name_lower)
            
            # Strategy 3: Try normalized matching
            if not html_inv:
                normalized = self._normalize_company_name(inv.company_name)
                html_inv = html_by_normalized.get(normalized)
            
            # Strategy 4: Fuzzy matching (last resort)
            if not html_inv:
                for html_name, html_inv_candidate in html_by_name.items():
                    if self._fuzzy_match_company_names(inv.company_name, html_name, threshold=0.8):
                        html_inv = html_inv_candidate
                        break
            
            if html_inv:
                merged = False
                # Only fill in missing fields
                if not inv.acquisition_date and html_inv.get('acquisition_date'):
                    inv.acquisition_date = html_inv['acquisition_date']
                    merged = True
                if not inv.maturity_date and html_inv.get('maturity_date'):
                    inv.maturity_date = html_inv['maturity_date']
                    merged = True
                if not inv.interest_rate and html_inv.get('interest_rate'):
                    inv.interest_rate = html_inv['interest_rate']
                    merged = True
                if merged:
                    merged_count += 1
        
        if merged_count > 0:
            logger.info(f"HTML fallback: Merged data into {{merged_count}} investments")
'''

def add_html_fallback_to_parser(parser_file: Path, investment_type: str):
    """Add HTML fallback methods to a parser file."""
    content = parser_file.read_text(encoding='utf-8')
    
    # Check if already has HTML fallback
    if '_extract_html_fallback' in content:
        print(f"{parser_file.name} already has HTML fallback")
        return
    
    # Find insertion point (before _select_reporting_instant)
    pattern = r'(def _select_reporting_instant\(self, contexts: List\[Dict\]\) -> Optional\[str\]:)'
    match = re.search(pattern, content)
    if not match:
        print(f"Could not find insertion point in {parser_file.name}")
        return
    
    insert_pos = match.start()
    
    # Prepare methods with correct investment type
    methods = HTML_FALLBACK_METHODS.replace('{INVESTMENT_TYPE}', investment_type)
    
    # Insert methods
    new_content = content[:insert_pos] + '\n' + methods + '\n\n    ' + content[insert_pos:]
    
    parser_file.write_text(new_content, encoding='utf-8')
    print(f"Added HTML fallback methods to {parser_file.name}")

if __name__ == '__main__':
    parsers = [
        ('glad_parser.py', 'GLADInvestment'),
        ('gain_parser.py', 'GAINInvestment'),
        ('gsbd_parser.py', 'GSBDInvestment'),
    ]
    
    base_dir = Path(__file__).parent.parent
    for parser_name, inv_type in parsers:
        parser_file = base_dir / parser_name
        if parser_file.exists():
            add_html_fallback_to_parser(parser_file, inv_type)
        else:
            print(f"File not found: {parser_file}")



