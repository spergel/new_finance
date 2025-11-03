#!/usr/bin/env python3
"""
Batch Historical Investment Extractor

Processes all BDCs to extract historical investment data from their 10-Q filings.
Creates time-series datasets for frontend visualization.
"""

import os
import logging
from typing import List, Dict, Optional
from datetime import datetime

from historical_investment_extractor import HistoricalInvestmentExtractor
from bdc_config import BDC_UNIVERSE, get_bdc_by_ticker

logger = logging.getLogger(__name__)


# Mapping of tickers to their parser module names
TICKER_TO_PARSER = {
    'ARCC': None,  # Needs special handling
    'OBDC': 'obdc_parser',
    'MAIN': 'main_parser',
    'GBDC': 'gbdc_parser',
    'BXSL': 'bxsl_parser',
    'HTGC': 'htgc_parser',
    'FSK': 'fsk_parser',
    'TSLX': 'tslx_parser',
    'MSDL': 'msdl_parser',
    'CSWC': 'cswc_parser',
    'MFIC': 'mfic_parser',
    'OCSL': 'ocsl_parser',
    'GSBD': 'gsbd_parser',
    'TRIN': 'trin_parser',
    'PSEC': 'psec_parser',
    'NMFC': 'nmfc_parser',
    'PFLT': 'pflt_parser',
    'CGBD': 'cgbd_parser',
    'BBDC': 'bbdc_parser',
    'FDUS': 'fdus_parser',
    'SLRC': 'slrc_parser',
    'BCSF': 'bcsf_parser',
    'GAIN': 'gain_parser',
    'TCPC': 'tcpc_parser',
    'CION': 'cion_parser',
    'NCDL': 'ncdl_parser',
    'GLAD': 'glad_parser',
    'GECC': 'gecc_parser',
    'PFX': 'pfx_parser',
    'OFS': 'ofs_parser',
    'PNNT': 'pnnt_parser',
    'SSSS': 'ssss_parser',
    'TPVG': 'tpvg_parser',
    'MSIF': 'msif_parser',
    'SCM': 'scm_parser',
    'HRZN': 'hrzn_parser',
    'RWAY': 'rway_parser',
    'LIEN': 'lien_parser',
    'LRFC': 'lrfc_parser',
    'PSBD': 'psbd_parser',
    'RAND': 'rand_parser',
    'WHF': 'whf_parser',
    'CCAP': 'ccap_parser',
    'ICMB': 'icmb_parser',
}


class BatchHistoricalExtractor:
    """
    Batch processor for extracting historical investment data from all BDCs.
    """
    
    def __init__(
        self,
        years_back: int = 5,
        output_dir: str = "output",
        user_agent: str = "BDC-Extractor/1.0 contact@example.com"
    ):
        self.years_back = years_back
        self.output_dir = output_dir
        self.extractor = HistoricalInvestmentExtractor(user_agent=user_agent)
        self.results = []
        
        os.makedirs(output_dir, exist_ok=True)
    
    def process_all_bdcs(
        self,
        ticker_filter: Optional[List[str]] = None,
        skip_processed: bool = False
    ) -> Dict[str, Dict]:
        """
        Process all BDCs to extract historical investment data.
        
        Args:
            ticker_filter: Optional list of tickers to process (if None, processes all)
            skip_processed: If True, skip BDCs that already have historical CSV files
            
        Returns:
            Dictionary mapping tickers to their processing results
        """
        results = {}
        
        # Determine which BDCs to process
        if ticker_filter:
            bdcs_to_process = [
                get_bdc_by_ticker(t) for t in ticker_filter
                if get_bdc_by_ticker(t) is not None
            ]
        else:
            bdcs_to_process = BDC_UNIVERSE
        
        total = len(bdcs_to_process)
        logger.info(f"Processing {total} BDCs for historical investment data")
        
        for i, bdc in enumerate(bdcs_to_process, 1):
            ticker = bdc['ticker']
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing {i}/{total}: {ticker} - {bdc['name']}")
            logger.info(f"{'='*60}")
            
            # Check if already processed
            if skip_processed:
                company_name = bdc['name'].replace(' ', '_').replace(',', '')
                expected_file = os.path.join(
                    self.output_dir,
                    f"{ticker}_{company_name}_historical_investments.csv"
                )
                if os.path.exists(expected_file):
                    logger.info(f"Skipping {ticker} - historical file already exists")
                    results[ticker] = {
                        'status': 'skipped',
                        'reason': 'file_exists',
                        'file': expected_file
                    }
                    continue
            
            try:
                # Get parser module name
                parser_module = TICKER_TO_PARSER.get(ticker)
                
                # Extract historical investments
                investments = self.extractor.extract_historical_investments(
                    ticker=ticker,
                    parser_module_name=parser_module,
                    years_back=self.years_back
                )
                
                if investments:
                    # Save to CSV
                    csv_path = self.extractor.save_historical_csv(
                        investments,
                        ticker,
                        self.output_dir
                    )
                    
                    # Calculate statistics
                    unique_periods = len(set(inv.get('reporting_period', '') for inv in investments))
                    unique_companies = len(set(inv.get('company_name', '') for inv in investments))
                    
                    results[ticker] = {
                        'status': 'success',
                        'investments_count': len(investments),
                        'unique_periods': unique_periods,
                        'unique_companies': unique_companies,
                        'file': csv_path,
                        'years_back': self.years_back
                    }
                    
                    logger.info(f"✅ {ticker}: {len(investments)} investments across {unique_periods} periods")
                else:
                    results[ticker] = {
                        'status': 'failed',
                        'reason': 'no_investments_extracted'
                    }
                    logger.warning(f"❌ {ticker}: No investments extracted")
                    
            except Exception as e:
                logger.error(f"❌ {ticker}: Error - {e}")
                results[ticker] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        self.results = results
        return results
    
    def generate_summary_report(self, output_file: str = None) -> str:
        """
        Generate a summary report of the batch processing results.
        
        Args:
            output_file: Optional path to save report (if None, prints to console)
            
        Returns:
            Report text
        """
        if not self.results:
            return "No results to report"
        
        report_lines = [
            "="*80,
            "BATCH HISTORICAL INVESTMENT EXTRACTION SUMMARY",
            "="*80,
            f"Processing Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Years Back: {self.years_back}",
            "",
            "RESULTS BY STATUS:",
            "-"*80
        ]
        
        # Group by status
        by_status = {}
        for ticker, result in self.results.items():
            status = result.get('status', 'unknown')
            if status not in by_status:
                by_status[status] = []
            by_status[status].append((ticker, result))
        
        for status in ['success', 'skipped', 'failed', 'error']:
            if status not in by_status:
                continue
            
            status_name = status.upper()
            count = len(by_status[status])
            report_lines.append(f"\n{status_name}: {count} BDCs")
            report_lines.append("-"*40)
            
            for ticker, result in by_status[status]:
                if status == 'success':
                    inv_count = result.get('investments_count', 0)
                    periods = result.get('unique_periods', 0)
                    report_lines.append(
                        f"  {ticker:6s} - {inv_count:5d} investments, {periods} periods"
                    )
                elif status == 'skipped':
                    reason = result.get('reason', 'unknown')
                    report_lines.append(f"  {ticker:6s} - {reason}")
                elif status == 'failed':
                    reason = result.get('reason', 'unknown')
                    report_lines.append(f"  {ticker:6s} - {reason}")
                else:  # error
                    error = result.get('error', 'Unknown error')
                    report_lines.append(f"  {ticker:6s} - {error[:60]}")
        
        # Summary statistics
        successful = len(by_status.get('success', []))
        total_investments = sum(
            r.get('investments_count', 0)
            for r in self.results.values()
            if r.get('status') == 'success'
        )
        total_periods = sum(
            r.get('unique_periods', 0)
            for r in self.results.values()
            if r.get('status') == 'success'
        )
        
        report_lines.extend([
            "",
            "="*80,
            "SUMMARY STATISTICS",
            "="*80,
            f"Total BDCs Processed: {len(self.results)}",
            f"Successfully Extracted: {successful}",
            f"Total Historical Investments: {total_investments:,}",
            f"Total Reporting Periods: {total_periods}",
            f"Success Rate: {(successful/len(self.results)*100) if self.results else 0:.1f}%",
            "="*80
        ])
        
        report_text = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            logger.info(f"Summary report saved to {output_file}")
        else:
            print(report_text)
        
        return report_text


def main():
    """Main entry point for batch historical extraction."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract historical investment data from BDC 10-Q filings"
    )
    parser.add_argument(
        '--years-back',
        type=int,
        default=5,
        help='Number of years to look back (default: 5)'
    )
    parser.add_argument(
        '--ticker',
        action='append',
        help='Specific ticker(s) to process (can be used multiple times)'
    )
    parser.add_argument(
        '--skip-processed',
        action='store_true',
        help='Skip BDCs that already have historical CSV files'
    )
    parser.add_argument(
        '--output-dir',
        default='output',
        help='Output directory for CSV files (default: output)'
    )
    parser.add_argument(
        '--report-file',
        help='Path to save summary report (optional)'
    )
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create batch extractor
    batch_extractor = BatchHistoricalExtractor(
        years_back=args.years_back,
        output_dir=args.output_dir
    )
    
    # Process BDCs
    results = batch_extractor.process_all_bdcs(
        ticker_filter=args.ticker,
        skip_processed=args.skip_processed
    )
    
    # Generate summary report
    batch_extractor.generate_summary_report(output_file=args.report_file)
    
    # Exit with appropriate code
    successful = sum(1 for r in results.values() if r.get('status') == 'success')
    if successful > 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit(main())



