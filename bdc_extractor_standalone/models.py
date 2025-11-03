#!/usr/bin/env python3
# models.py - Simplified Pydantic models for SEC securities and corporate actions extraction

from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import date, datetime
from enum import Enum

class SecurityType(str, Enum):
    """Enumeration of security types."""
    PREFERRED_STOCK = "preferred_stock"
    SENIOR_NOTE = "senior_note"
    CONVERTIBLE_NOTE = "convertible_note"
    CORPORATE_BOND = "corporate_bond"
    DEBT_INSTRUMENT = "debt_instrument"

class CorporateActionType(str, Enum):
    """Types of corporate actions."""
    TENDER_OFFER = "tender_offer"
    DEBT_REFINANCING = "debt_refinancing"
    ASSET_SALE = "asset_sale"
    ASSET_ACQUISITION = "asset_acquisition"
    SHARE_BUYBACK = "share_buyback"
    MERGER = "merger"
    SPIN_OFF = "spin_off"
    REDEMPTION = "redemption"
    DIVIDEND = "dividend"

class CorporateActionStatus(str, Enum):
    """Status of corporate actions."""
    ANNOUNCED = "announced"
    PENDING = "pending"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"
    CANCELLED = "cancelled"

class FilingType(str, Enum):
    """SEC filing types we process."""
    FOUR_TWO_FOUR_B = "424B"  # Prospectus supplements
    S1 = "S-1"               # Registration statements
    EIGHT_K = "8-K"           # Current reports
    TEN_K = "10-K"            # Annual reports
    TEN_Q = "10-Q"            # Quarterly reports

# Base model with proper date serialization
class BaseModelWithConfig(BaseModel):
    """Base model with config for date serialization."""
    class Config:
        """Config for Pydantic models."""
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None
        }

# === SECURITIES FEATURES MODELS ===

class ConversionTerms(BaseModelWithConfig):
    """Terms for converting the security to common stock"""
    conversion_price: Optional[float] = None
    conversion_ratio: Optional[float] = None
    is_conditional: Optional[bool] = False
    conversion_triggers: List[str] = []  # e.g., ["change_of_control", "delisting"]
    earliest_conversion_date: Optional[date] = None
    conversion_details: Optional[str] = None  # Longer description with paragraph text
    # Additional
    share_cap: Optional[float] = None  # e.g., 7.39645

class RedemptionTerms(BaseModelWithConfig):
    """Terms for redeeming or calling the security"""
    is_callable: Optional[bool] = False
    call_price: Optional[float] = None
    earliest_call_date: Optional[date] = None
    notice_period_days: Optional[int] = None
    has_make_whole: Optional[bool] = False
    # Sinking fund provisions
    has_sinking_fund: Optional[bool] = False
    sinking_fund_schedule: Optional[str] = None
    sinking_fund_amount_per_year: Optional[float] = None
    redemption_details: Optional[str] = None  # Longer description with paragraph text

class Covenants(BaseModelWithConfig):
    """Debt covenants and contractual restrictions"""
    # Financial Covenants
    has_financial_covenants: Optional[bool] = False
    minimum_interest_coverage: Optional[float] = None  # e.g., EBITDA/Interest >= 2.0x
    maximum_debt_to_ebitda: Optional[float] = None     # e.g., Total Debt/EBITDA <= 4.0x
    minimum_ebitda: Optional[float] = None             # Minimum EBITDA requirement
    maximum_debt_to_capital: Optional[float] = None    # Debt/(Debt + Equity) ratio

    # Negative Covenants (things issuer CANNOT do)
    restricted_payments_covenant: Optional[str] = None  # Dividend restrictions
    additional_debt_restrictions: Optional[str] = None  # Limits on new debt
    asset_sale_restrictions: Optional[str] = None       # Limits on asset sales
    merger_restrictions: Optional[str] = None          # Limits on M&A
    investment_restrictions: Optional[str] = None      # Limits on investments

    # Affirmative Covenants (things issuer MUST do)
    reporting_requirements: Optional[str] = None       # Financial reporting
    maintenance_covenants: Optional[str] = None        # Insurance, taxes, etc.
    collateral_maintenance: Optional[str] = None       # Asset maintenance

    # Default Provisions
    cross_default_provision: Optional[str] = None      # Default on other debt triggers this
    events_of_default: List[str] = []                  # What triggers default

    # Other
    change_of_control_covenant: Optional[str] = None   # Change of control triggers
    covenant_summary: Optional[str] = None            # Overall covenant overview

class SpecialFeatures(BaseModelWithConfig):
    """Special features like change-of-control provisions"""
    has_change_of_control: Optional[bool] = False
    change_of_control_protection: Optional[str] = None  # Short summary
    change_of_control_put_right: Optional[bool] = False  # Can holders force redemption?
    change_of_control_put_price: Optional[float] = None  # Price for forced redemption
    change_of_control_definition: Optional[str] = None  # What triggers it
    change_of_control_details: Optional[str] = None  # Longer description with paragraph text
    has_anti_dilution: Optional[bool] = False
    has_vwap_pricing: Optional[bool] = False

    # Covenants (NEW)
    covenants: Optional[Covenants] = None

class RateResetTerms(BaseModelWithConfig):
    """Rate reset features for floating or fixed-to-floating preferreds"""
    has_rate_reset: Optional[bool] = False
    reset_frequency: Optional[str] = None  # e.g., "5 years", "quarterly"
    reset_dates: List[str] = []  # e.g., ["2028-03-30", "2033-03-30"]
    initial_fixed_period_end: Optional[date] = None
    reset_spread: Optional[float] = None  # e.g., 3.728 for 3.728%
    reset_benchmark: Optional[str] = None  # e.g., "Five-year U.S. Treasury Rate"
    reset_floor: Optional[float] = None  # Minimum rate if any
    reset_cap: Optional[float] = None  # Maximum rate if any

class DepositarySharesInfo(BaseModelWithConfig):
    """Information about depositary shares structure"""
    is_depositary_shares: Optional[bool] = False
    depositary_ratio: Optional[str] = None  # e.g., "1/1,000th interest"
    depositary_shares_issued: Optional[int] = None
    underlying_preferred_shares: Optional[int] = None
    depositary_symbol: Optional[str] = None  # Trading symbol
    depositary_institution: Optional[str] = None  # e.g., "Equiniti Trust Company"
    price_per_depositary_share: Optional[float] = None

class SpecialRedemptionEvents(BaseModelWithConfig):
    """Special redemption triggers and terms"""
    has_rating_agency_event: Optional[bool] = False
    rating_agency_event_price: Optional[float] = None
    rating_agency_event_window: Optional[str] = None  # e.g., "90 days"
    rating_agency_event_definition: Optional[str] = None  # Exact definition of trigger

    has_regulatory_capital_event: Optional[bool] = False
    regulatory_capital_event_price: Optional[float] = None
    regulatory_capital_event_window: Optional[str] = None
    regulatory_capital_event_definition: Optional[str] = None  # Exact definition

    has_tax_event: Optional[bool] = False
    tax_event_details: Optional[str] = None

    tax_treatment_notes: Optional[str] = None  # General tax treatment info

class SecurityFeatures(BaseModelWithConfig):
    """Main security features data structure"""
    security_id: str
    security_type: SecurityType
    company: str
    filing_date: date
    description: Optional[str] = None

    # Financial terms
    principal_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    maturity_date: Optional[date] = None
    par_value: Optional[float] = None
    
    # Preferred stock specific fields
    liquidation_preference: Optional[float] = None  # Per share liquidation value
    dividend_rate: Optional[float] = None  # Annual dividend rate as percentage
    dividend_type: Optional[str] = None  # "fixed", "floating", "fixed-to-floating"
    is_cumulative: Optional[bool] = None  # Cumulative vs noncumulative dividends
    payment_frequency: Optional[str] = None  # "quarterly", "monthly", "semi-annually"
    dividend_payment_dates: List[str] = []  # Specific payment dates if regular (e.g., ["Mar 30", "Jun 30"])
    dividend_stopper_clause: Optional[str] = None  # Restrictions on common dividends
    dividend_calculation_method: Optional[str] = None  # e.g., "360-day year", "actual/360"
    is_perpetual: Optional[bool] = None  # No maturity date
    # Additional dividend details
    first_dividend_date: Optional[date] = None
    first_dividend_amount: Optional[float] = None
    dividend_payment_schedule: List[str] = []  # e.g., ["Jan 15", "Apr 15", "Jul 15", "Oct 15"]

    # Original offering information (NEW)
    original_offering_size: Optional[int] = None  # Shares originally offered
    original_offering_date: Optional[date] = None  # When originally issued
    original_offering_price: Optional[float] = None  # Original price per share
    is_new_issuance: Optional[bool] = None  # True if recently issued
    
    # Voting and governance (preferred stock)
    voting_rights_description: Optional[str] = None
    can_elect_directors: Optional[bool] = None
    director_election_trigger: Optional[str] = None
    protective_provisions: List[str] = []

    # Conversion features
    conversion_terms: Optional[ConversionTerms] = None

    # Redemption features
    redemption_terms: Optional[RedemptionTerms] = None
    special_redemption_events: Optional[SpecialRedemptionEvents] = None
    partial_redemption_allowed: Optional[bool] = None

    # Rate reset features (for floating/reset preferreds)
    rate_reset_terms: Optional[RateResetTerms] = None
    
    # Depositary shares information
    depositary_shares_info: Optional[DepositarySharesInfo] = None

    # Special features
    special_features: Optional[SpecialFeatures] = None
    
    # Ranking
    ranking_description: Optional[str] = None  # e.g., "senior to common, pari passu with other preferred"
    
    # Exchange listing (for liquidity)
    exchange_listed: Optional[str] = None  # e.g., "NYSE", "Nasdaq", "OTC"
    trading_symbol: Optional[str] = None  # Primary trading symbol
    listing_status: Optional[str] = None  # e.g., "application filed", "approved", "trading"
    ownership_restrictions: Optional[str] = None  # e.g., REIT-related ownership/transfer restrictions summary

    # Source information
    source_filing: str
    extraction_confidence: float = 1.0
    
    # Filing match metadata (from filing_matcher)
    matched_filing_date: Optional[date] = None
    matched_filing_accession: Optional[str] = None
    filing_url: Optional[str] = None  # Direct URL to SEC filing
    match_confidence: Optional[str] = None  # 'high', 'medium', 'low'
    series_mention_count: Optional[int] = None

# === ENHANCED PREFERRED SHARES MODELS (LLM Extracted) ===

class PreferredShareDividendFeatures(BaseModelWithConfig):
    """Dividend-specific features for preferred shares"""
    dividend_rate: Optional[float] = None
    dividend_type: Optional[str] = None  # "fixed", "floating", "auction"
    is_cumulative: Optional[bool] = None
    payment_frequency: Optional[str] = None  # "quarterly", "monthly", "annually", "semi-annually"
    dividend_calculation_method: Optional[str] = None
    dividend_stopper_clause: Optional[str] = None  # Restrictions on common dividends
    has_pik_toggle: Optional[bool] = False  # Payment-in-kind toggle option
    pik_details: Optional[str] = None

class PreferredShareGovernance(BaseModelWithConfig):
    """Governance and voting rights for preferred shares"""
    voting_rights: Optional[str] = None  # Description of voting conditions
    has_board_appointment_rights: Optional[bool] = False
    board_appointment_details: Optional[str] = None  # e.g., "Can elect 2 directors if dividends in arrears"
    protective_provisions: List[str] = []  # e.g., ["Veto on M&A", "Approval for senior debt"]
    protective_provisions_details: Optional[str] = None

class PreferredShareConversionFeatures(BaseModelWithConfig):
    """Enhanced conversion features for preferred shares"""
    is_convertible: Optional[bool] = False
    conversion_ratio: Optional[float] = None
    conversion_price: Optional[float] = None
    is_mandatory: Optional[bool] = False
    conversion_triggers: List[str] = []
    mandatory_conversion_triggers: List[str] = []  # e.g., ["IPO above $30/share"]
    adjustment_formula: Optional[str] = None  # Anti-dilution details
    earliest_conversion_date: Optional[str] = None

class PreferredShareRedemptionFeatures(BaseModelWithConfig):
    """Enhanced redemption features for preferred shares"""
    is_callable: Optional[bool] = False
    earliest_call_date: Optional[str] = None
    call_price: Optional[float] = None
    call_premium_pct: Optional[float] = None
    notice_period_days: Optional[int] = None
    is_mandatory_redemption: Optional[bool] = False
    has_holder_put_rights: Optional[bool] = False
    holder_put_details: Optional[str] = None
    sinking_fund: Optional[bool] = False
    sinking_fund_details: Optional[str] = None

class PreferredShareSpecialProvisions(BaseModelWithConfig):
    """Special provisions for preferred shares"""
    change_of_control_provision: Optional[str] = None
    rate_reset_terms: Optional[str] = None  # For floating rate preferreds
    ranking_details: Optional[str] = None  # e.g., "pari passu with other preferred, senior to common"
    tax_treatment_notes: Optional[str] = None
    other_special_features: List[str] = []

class EnhancedPreferredShareFeatures(BaseModelWithConfig):
    """Comprehensive preferred share features extracted via LLM"""
    # Basic identification
    security_id: str
    series_name: Optional[str] = None
    company: str
    filing_date: date
    source_filing: str
    description: Optional[str] = None
    
    # Core terms
    par_value: Optional[float] = None
    liquidation_preference: Optional[float] = None
    
    # Feature groups
    dividend_features: Optional[PreferredShareDividendFeatures] = None
    conversion_features: Optional[PreferredShareConversionFeatures] = None
    redemption_features: Optional[PreferredShareRedemptionFeatures] = None
    governance: Optional[PreferredShareGovernance] = None
    special_provisions: Optional[PreferredShareSpecialProvisions] = None
    
    # Metadata
    extraction_confidence: float = 1.0
    notes: Optional[str] = None

# === CORPORATE ACTIONS MODELS ===

class CorporateAction(BaseModelWithConfig):
    """Corporate action data structure"""
    action_id: str
    action_type: CorporateActionType
    company: str
    announcement_date: Optional[date] = None
    effective_date: Optional[date] = None
    
    title: str
    description: str
    status: CorporateActionStatus
    
    # Financial terms
    amount: Optional[float] = None
    price_per_share: Optional[float] = None
    total_value: Optional[float] = None

    # Securities affected
    target_security: Optional[str] = None
    target_security_type: Optional[str] = None
    
    # Source information
    source_filing: str
    extraction_confidence: float = 1.0

# === XBRL DATA MODELS ===

class XBRLSeriesIdentifier(BaseModelWithConfig):
    """Represents a specific preferred share series identified from XBRL data"""
    series_name: Optional[str] = None
    cusip: Optional[str] = None
    xbrl_tag: str
    raw_match: Optional[str] = None
    context: Optional[str] = None
    unit: Optional[str] = None
    source: str
    confidence: float = 1.0

class XBRLPreferredSharesData(BaseModelWithConfig):
    """XBRL data for preferred shares"""
    ticker: str
    filing_type: str
    extraction_date: date
    xbrl_available: bool
    series_identifiers: List[XBRLSeriesIdentifier] = []
    numeric_values: List[str] = []
    contexts_found: int = 0
    tag_distribution: Dict[str, int] = {}
    data_quality_score: float = 0.0

class XBRLSummary(BaseModelWithConfig):
    """Summary of XBRL extraction results"""
    ticker: str
    has_preferred_shares: bool
    xbrl_tags_found: int
    series_identified: List[str] = []
    cusips_identified: List[str] = []
    total_mentioned: int = 0
    data_quality_score: float = 0.0

# === DATA FUSION MODELS ===

class DataFusionSource(str, Enum):
    """Sources of data for fusion"""
    XBRL = "xbrl"
    LLM = "llm"
    COMBINED = "combined"

class FusedSecurityData(BaseModelWithConfig):
    """Security data that combines XBRL and LLM sources"""
    security_id: str
    company: str

    # XBRL-sourced data (structured, reliable)
    xbrl_series_name: Optional[str] = None
    xbrl_cusip: Optional[str] = None
    xbrl_outstanding_shares: Optional[str] = None
    xbrl_balance_sheet_value: Optional[str] = None

    # LLM-sourced data (contextual, detailed)
    llm_description: Optional[str] = None
    llm_conversion_terms: Optional[str] = None
    llm_redemption_terms: Optional[str] = None
    llm_special_features: Optional[str] = None

    # Combined/confidence data
    data_sources: List[DataFusionSource] = []
    confidence_score: float = 0.0
    last_updated: date

    # Metadata
    filing_date: Optional[date] = None
    source_filing: Optional[str] = None

class DataFusionResult(BaseModelWithConfig):
    """Result of data fusion between XBRL and LLM sources"""
    ticker: str
    fusion_date: date
    xbrl_data_available: bool = False
    llm_data_available: bool = False
    fused_securities: List[FusedSecurityData] = []
    total_securities: int = 0

    # Quality metrics
    overall_confidence: float = 0.0
    data_completeness_score: float = 0.0

# === RESULT MODELS ===

class SecuritiesFeaturesResult(BaseModelWithConfig):
    """Result of securities features extraction"""
    ticker: str
    extraction_date: date
    securities: List[SecurityFeatures] = []
    total_securities: int = 0

class CorporateActionsResult(BaseModelWithConfig):
    """Result of corporate actions extraction"""
    ticker: str
    extraction_date: date
    corporate_actions: List[CorporateAction] = []
    total_actions: int = 0