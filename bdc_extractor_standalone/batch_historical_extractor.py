#!/usr/bin/env python3
"""
Batch Historical Investment Extractor

Processes all BDCs to extract historical investment data from their 10-Q filings.
Creates time-series datasets for frontend visualization.
"""

import os
import logging
import shutil
import glob
from typing import List, Dict, Optional
from datetime import datetime

from historical_investment_extractor import HistoricalInvestmentExtractor
from bdc_config import BDC_UNIVERSE, get_bdc_by_ticker

logger = logging.getLogger(__name__)


# Mapping of tickers to their parser module names
# Note: Custom parsers are automatically prioritized by historical_investment_extractor
# This mapping is only used if custom parser doesn't exist
TICKER_TO_PARSER = {
    'ARCC': None,  # Needs special handling
    'OBDC': 'obdc_parser',  # Has obdc_custom_parser.py (auto-prioritized)
    'MAIN': 'main_parser',  # Has main_custom_parser.py (auto-prioritized)
    'GBDC': 'gbdc_parser',  # Has gbdc_custom_parser.py (auto-prioritized)
    'BXSL': 'bxsl_parser',
    'HTGC': 'htgc_parser',  # Has htgc_custom_parser.py (auto-prioritized)
    'FSK': 'fsk_parser',  # Has fsk_custom_parser.py (auto-prioritized)
    'TSLX': 'tslx_parser',  # Has tslx_custom_parser.py (auto-prioritized)
    'MSDL': 'msdl_parser',  # Has msdl_custom_parser.py (auto-prioritized)
    'CSWC': 'cswc_parser',  # Has cswc_custom_parser.py (auto-prioritized)
    'MFIC': 'mfic_parser',  # Has mfic_custom_parser.py (auto-prioritized)
    'OCSL': 'ocsl_parser',  # Has ocsl_custom_parser.py (auto-prioritized)
    'GSBD': 'gsbd_parser',
    'TRIN': 'trin_parser',  # Has trin_custom_parser.py (auto-prioritized)
    'PSEC': 'psec_parser',  # Has psec_custom_parser.py (auto-prioritized)
    'NMFC': 'nmfc_parser',  # Has nmfc_custom_parser.py (auto-prioritized)
    'PFLT': 'pflt_parser',  # Has pflt_custom_parser.py (auto-prioritized)
    'CGBD': 'cgbd_parser',  # Has cgbd_custom_parser.py (auto-prioritized)
    'BBDC': 'bbdc_parser',  # Has bbdc_custom_parser.py (auto-prioritized)
    'FDUS': 'fdus_parser',  # Has fdus_custom_parser.py (auto-prioritized)
    'SLRC': 'slrc_parser',
    'BCSF': 'bcsf_parser',  # Has bcsf_custom_parser.py (auto-prioritized)
    'GAIN': 'gain_parser',  # Has gain_custom_parser.py (auto-prioritized)
    'TCPC': 'tcpc_parser',  # Has tcpc_custom_parser.py (auto-prioritized)
    'CION': 'cion_parser',  # Has cion_custom_parser.py (auto-prioritized)
    'NCDL': 'ncdl_parser',  # Has ncdl_custom_parser.py (auto-prioritized)
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
    'KBDC': 'kbdc_parser',  # Has kbdc_custom_parser.py (auto-prioritized)
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
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_dir)
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
    
    def copy_to_frontend_data(self, frontend_data_dir: Optional[str] = None) -> Dict[str, int]:
        """
        Copy CSV files from output directory to frontend data directory.
        
        Args:
            frontend_data_dir: Path to frontend data directory. If None, uses default.
            
        Returns:
            Dictionary with copy statistics
        """
        if frontend_data_dir is None:
            # Default to frontend/public/data relative to bdc_extractor_standalone
            script_dir = os.path.dirname(os.path.abspath(__file__))
            frontend_data_dir = os.path.join(script_dir, 'frontend', 'public', 'data')
        
        os.makedirs(frontend_data_dir, exist_ok=True)
        
        stats = {
            'tickers_copied': 0,
            'files_copied': 0,
            'errors': 0
        }
        
        logger.info(f"\n{'='*60}")
        logger.info("Copying CSV files to frontend data directory...")
        logger.info(f"Source: {self.output_dir}")
        logger.info(f"Destination: {frontend_data_dir}")
        logger.info(f"{'='*60}\n")
        
        # Get all CSV files in output directory
        csv_pattern = os.path.join(self.output_dir, "*.csv")
        csv_files = glob.glob(csv_pattern)
        
        if not csv_files:
            logger.warning(f"No CSV files found in {self.output_dir}")
            return stats
        
        # Group files by ticker
        ticker_files = {}
        for csv_file in csv_files:
            filename = os.path.basename(csv_file)
            # Extract ticker from filename (format: TICKER_Company_Name_investments.csv)
            parts = filename.split('_')
            if parts:
                ticker = parts[0].upper()
                if ticker not in ticker_files:
                    ticker_files[ticker] = []
                ticker_files[ticker].append(csv_file)
        
        # Copy files for each ticker
        for ticker, files in ticker_files.items():
            ticker_data_dir = os.path.join(frontend_data_dir, ticker)
            os.makedirs(ticker_data_dir, exist_ok=True)
            
            for source_file in files:
                filename = os.path.basename(source_file)
                dest_file = os.path.join(ticker_data_dir, filename)
                
                try:
                    shutil.copy2(source_file, dest_file)
                    stats['files_copied'] += 1
                    logger.debug(f"Copied {filename} to {ticker_data_dir}")
                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"Error copying {filename}: {e}")
            
            if files:
                stats['tickers_copied'] += 1
                logger.info(f"✅ {ticker}: Copied {len(files)} file(s)")
        
        logger.info(f"\n{'='*60}")
        logger.info("Copy Summary:")
        logger.info(f"  Tickers processed: {stats['tickers_copied']}")
        logger.info(f"  Files copied: {stats['files_copied']}")
        logger.info(f"  Errors: {stats['errors']}")
        logger.info(f"{'='*60}\n")
        
        return stats
    
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
    parser.add_argument(
        '--no-copy-to-frontend',
        dest='copy_to_frontend',
        action='store_false',
        default=True,
        help='Do not copy CSV files to frontend data directory (default: copies to frontend)'
    )
    parser.add_argument(
        '--frontend-data-dir',
        help='Path to frontend data directory (default: frontend/public/data)'
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
    
    # Copy to frontend data directory if requested
    if args.copy_to_frontend:
        batch_extractor.copy_to_frontend_data(frontend_data_dir=args.frontend_data_dir)
    
    # Exit with appropriate code
    successful = sum(1 for r in results.values() if r.get('status') == 'success')
    if successful > 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit(main())



