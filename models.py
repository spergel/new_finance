#!/usr/bin/env python3
# models.py - Pydantic models for SEC data extraction

from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import date, datetime
from enum import Enum

class SecurityType(str, Enum):
    """Enumeration of security types."""
    CONVERTIBLE_NOTE = "convertible_note"
    CONVERTIBLE_BOND = "convertible_bond" 
    CONVERTIBLE_DEBT = "convertible_debt"
    PREFERRED_STOCK = "preferred_stock"
    WARRANT = "warrant"
    SENIOR_NOTE = "senior_note"
    CORPORATE_ACTION = "corporate_action"
    DEBT_INSTRUMENT = "debt_instrument"

class FilingType(str, Enum):
    """Enumeration of SEC filing types."""
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    EIGHT_K = "8-K"
    FOUR_TWO_FOUR_B = "424B"
    SC_TO_I = "SC TO-I"
    
class ExtractionSource(str, Enum):
    """Source of the extraction."""
    LLM_ANALYSIS = "llm_analysis"
    XBRL_STRUCTURED = "xbrl_structured"
    HYBRID = "hybrid"

# Base model with proper date serialization
class BaseModelWithConfig(BaseModel):
    """Base model with config for date serialization."""
    class Config:
        """Config for Pydantic models."""
        json_encoders = {
            date: lambda v: v.isoformat() if v else None,
            datetime: lambda v: v.isoformat() if v else None
        }

class FormulaComponents(BaseModelWithConfig):
    """Structured representation of mathematical formulas from securities."""
    
    # Formula type classification
    formula_type: str = "unknown"  # "structured_note", "convertible_bond", "warrant", etc.
    
    # Base parameters
    principal_amount: Optional[float] = None
    multiplier: Optional[float] = None
    
    # Performance components
    performance_component: Optional[str] = None  # "underlying_return", "index_return", etc.
    performance_multiplier: Optional[float] = 1.0
    
    # Buffer/barrier components
    buffer_percentage: Optional[float] = None
    barrier_level: Optional[float] = None
    
    # Caps and floors
    cap_level: Optional[float] = None
    floor_level: Optional[float] = None
    participation_rate: Optional[float] = None
    
    # Formula structure
    formula_structure: str = ""  # Standardized mathematical representation
    original_text: str = ""  # Original text formula
    
    # Extracted numerical parameters
    numerical_parameters: Dict = {}

class StructuredProductMetrics(BaseModelWithConfig):
    """Metrics specific to structured products like notes and warrants."""
    
    # Payoff structure
    payoff_formula: Optional[FormulaComponents] = None
    # Add evaluable spec for programmatic computation
    payoff_model_spec: Optional[dict] = None  # Evaluatable piecewise model (see ConversionTerms.payoff_model)
    
    # Barrier structures
    knock_in_barrier: Optional[float] = None
    knock_out_barrier: Optional[float] = None
    autocall_barriers: List[float] = []
    
    # Buffer and participation
    downside_buffer: Optional[float] = None
    upside_participation: Optional[float] = None
    
    # Index/underlying details
    underlying_assets: List[str] = []
    worst_of_structure: bool = False
    best_of_structure: bool = False
    
    # Time features
    observation_dates: List[str] = []
    autocall_dates: List[str] = []
    
class ConversionMetrics(BaseModelWithConfig):
    """Enhanced metrics for conversion features."""
    
    # Conversion ratios and prices
    initial_conversion_price: Optional[float] = None
    current_conversion_price: Optional[float] = None
    conversion_ratio: Optional[float] = None
    
    # Adjustment mechanisms
    anti_dilution_adjustments: List[str] = []
    reset_provisions: bool = False
    
    # Trigger thresholds
    stock_price_triggers: List[float] = []
    ownership_triggers: List[float] = []
    
    # Exercise conditions
    exercise_windows: List[str] = []
    blackout_periods: List[str] = []

class VWAPMetrics(BaseModelWithConfig):
    """VWAP-based calculation components."""
    
    # VWAP period details
    vwap_period_days: Optional[int] = None  # e.g., 5-day, 20-day
    vwap_calculation_method: Optional[str] = None  # "arithmetic", "volume_weighted"
    
    # VWAP thresholds
    vwap_threshold_percentage: Optional[float] = None  # e.g., 200% of conversion price
    vwap_threshold_days: Optional[int] = None  # e.g., 20 trading days
    vwap_threshold_period: Optional[int] = None  # e.g., during any 30 consecutive days
    
    # VWAP-based pricing
    vwap_based_conversion_price: bool = False
    vwap_based_exercise_price: bool = False
    
    # Share rounding rules
    share_rounding_method: Optional[str] = None  # "up", "down", "nearest"

class MinMaxFormulaComponents(BaseModelWithConfig):
    """Min/Max calculation structure for convertible securities."""
    
    # Formula type
    formula_type: str = "unknown"  # "greater_of", "lesser_of", "max", "min"
    
    # Components being compared
    component_a: Optional[str] = None  # e.g., "Minimum Consideration"
    component_b: Optional[str] = None  # e.g., "conversion value"
    component_c: Optional[str] = None  # For three-way comparisons
    
    # Numerical values if extractable
    component_a_value: Optional[float] = None
    component_b_value: Optional[float] = None
    component_c_value: Optional[float] = None
    
    # Original formula text
    original_formula: str = ""
    
    # Structured representation
    structured_formula: str = ""  # e.g., "max(A, B)" or "greater_of(A, B-C, 0)"

class AntiDilutionMetrics(BaseModelWithConfig):
    """Anti-dilution adjustment formulas and parameters."""
    
    # Anti-dilution type
    adjustment_type: Optional[str] = None  # "weighted_average_broad", "weighted_average_narrow", "full_ratchet"
    
    # Weighted average parameters
    outstanding_shares_base: Optional[float] = None
    dilutive_shares: Optional[float] = None
    old_exercise_price: Optional[float] = None
    new_issue_price: Optional[float] = None
    
    # Full ratchet parameters
    ratchet_trigger_price: Optional[float] = None
    
    # Formula components
    adjustment_formula: Optional[str] = None
    calculation_method: Optional[str] = None
    
    # Broad vs narrow scope details
    scope: Optional[str] = None  # "broad", "narrow"
    excluded_issuances: List[str] = []

class FloatingRateMetrics(BaseModelWithConfig):
    """Floating rate calculation components."""
    
    # Base rate
    base_rate: Optional[str] = None  # "SOFR", "LIBOR", "Prime", "Treasury"
    base_rate_term: Optional[str] = None  # "3-month", "overnight"
    
    # Spread/margin
    spread_bps: Optional[float] = None  # Basis points over base rate
    spread_percentage: Optional[float] = None  # Percentage spread
    
    # Rate floors and caps
    rate_floor: Optional[float] = None
    rate_cap: Optional[float] = None
    
    # Reset frequency
    reset_frequency: Optional[str] = None  # "daily", "monthly", "quarterly"
    reset_dates: List[str] = []
    
    # Rate calculation method
    compounding_method: Optional[str] = None  # "simple", "compound", "compounded_sofr"
    day_count_convention: Optional[str] = None  # "30/360", "actual/360"

class CashlessExerciseMetrics(BaseModelWithConfig):
    """Cashless exercise calculation formulas."""
    
    # Exercise method
    exercise_type: str = "unknown"  # "cashless", "cash", "net_share_settlement"
    
    # Formula components
    fair_market_value_component: Optional[str] = None  # How FMV is determined
    exercise_price_component: Optional[str] = None
    warrant_shares_component: Optional[str] = None
    
    # Net share calculation
    net_share_formula: Optional[str] = None  # e.g., "(FMV - Exercise) * Shares / FMV"
    
    # FMV determination method
    fmv_calculation_method: Optional[str] = None  # "closing_price", "vwap", "average"
    fmv_calculation_period: Optional[int] = None  # Days for averaging
    
    # Exercise constraints
    minimum_exercise_shares: Optional[int] = None
    fractional_share_treatment: Optional[str] = None  # "cash", "round_up", "round_down"

class QuantitativeMetrics(BaseModelWithConfig):
    """Structured quantitative metrics extracted from securities language."""
    
    # Financial metrics with specific numerical values
    financial_metrics: Dict = {}
    
    # Ownership and control thresholds
    ownership_metrics: Dict = {}
    
    # Time-based metrics 
    time_metrics: Dict = {}
    
    # Trigger and barrier levels
    trigger_metrics: Dict = {}
    
    # Control and governance thresholds
    control_metrics: Dict = {}
    
    # Enhanced structured components
    formula_components: Optional[FormulaComponents] = None
    structured_product_metrics: Optional[StructuredProductMetrics] = None
    conversion_metrics: Optional[ConversionMetrics] = None
    
    # Additional formula types
    vwap_metrics: Optional[VWAPMetrics] = None
    min_max_formulas: Optional[MinMaxFormulaComponents] = None
    anti_dilution_metrics: Optional[AntiDilutionMetrics] = None
    floating_rate_metrics: Optional[FloatingRateMetrics] = None
    cashless_exercise_metrics: Optional[CashlessExerciseMetrics] = None

class BarrierMetrics(BaseModelWithConfig):
    """Barrier and buffer structures for structured products."""
    
    # Barrier levels (e.g., "85% barrier", "knock-in at 75%")
    barrier_levels: List[float] = []
    barrier_types: List[str] = []  # ["knock-in", "knock-out", "american", "european"]
    
    # Buffer protection (e.g., "15% downside buffer")
    buffer_amounts: List[float] = []
    buffer_types: List[str] = []  # ["downside", "upside", "symmetric"]
    
    # Participation rates (e.g., "130% participation", "capped at 200%")
    participation_rates: List[float] = []
    participation_caps: List[float] = []
    participation_floors: List[float] = []

class AutocallMetrics(BaseModelWithConfig):
    """Autocall and early redemption features."""
    
    # Autocall barriers (e.g., "auto-redeems at 100% of initial level")
    autocall_barriers: List[float] = []
    autocall_frequencies: List[str] = []  # ["quarterly", "semi-annual", "annual"]
    
    # Coupon barriers and rates
    coupon_barriers: List[float] = []
    coupon_rates: List[float] = []
    
    # Memory features
    has_memory_feature: bool = False
    memory_periods: List[int] = []

class PerformanceMetrics(BaseModelWithConfig):
    """Performance-linked and milestone metrics."""
    
    # Revenue/EBITDA targets (e.g., "$100M revenue target")
    revenue_targets: List[float] = []
    ebitda_targets: List[float] = []
    
    # Market cap thresholds
    market_cap_thresholds: List[float] = []
    
    # Stock price triggers
    price_triggers: List[float] = []
    price_trigger_periods: List[int] = []  # days
    
    # FDA/regulatory milestones
    regulatory_milestones: List[str] = []
    milestone_payments: List[float] = []

#
# Pydantic Data Models for structured extraction
#

class VWAPThreshold(BaseModelWithConfig):
    """VWAP price threshold with potential date constraints"""
    price: Optional[float] = None
    end_date: Optional[date] = None
    is_initial: Optional[bool] = None
    is_final: Optional[bool] = None

class ConversionCondition(BaseModelWithConfig):
    """Condition under which conversion may occur"""
    type: str
    description: str
    threshold_percentage: Optional[float] = None
    measurement_days: Optional[int] = None
    window_days: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class RedemptionCondition(BaseModelWithConfig):
    """Condition under which redemption may occur"""
    type: str
    description: str
    threshold_percentage: Optional[float] = None
    measurement_days: Optional[int] = None
    window_days: Optional[int] = None
    earliest_date: Optional[date] = None
    notice_days: Optional[int] = None
    redemption_price: Optional[float] = None
    includes_accrued_interest: Optional[bool] = True
    is_make_whole: Optional[bool] = False

class ConversionTerms(BaseModelWithConfig):
    """Terms for converting the security to common stock"""
    # Basic conversion info
    conversion_price: Optional[float] = None
    conversion_ratio: Optional[float] = None
    shares_per_1000: Optional[float] = None
    settlement_type: Optional[str] = None
    par_value: Optional[float] = None
    
    # Conversion mechanism type
    conversion_type: Optional[str] = None  # "fixed_ratio", "variable_liquidation_based", "conditional_event_based"
    is_conditional_conversion: Optional[bool] = False  # Only converts on specific triggers
    conversion_triggers: Optional[List[str]] = []  # ["change_of_control", "delisting_event", "automatic"]
    
    # Variable conversion mechanics (like BW preferred)
    is_variable_conversion: Optional[bool] = False
    liquidation_preference_per_share: Optional[float] = None
    variable_conversion_formula: Optional[str] = None  # "liquidation_pref / current_stock_price"
    
    # Share caps and limits
    has_share_cap: Optional[bool] = False
    share_cap_maximum: Optional[float] = None  # Maximum shares receivable (like 5.65611 for BW)
    share_cap_calculation: Optional[str] = None  # How the cap was calculated
    
    # Legacy/standard conversion fields
    is_dynamic_pricing: Optional[bool] = False
    vwap_based: Optional[bool] = False
    vwap_days: Optional[int] = None
    vwap_percentage: Optional[float] = None
    price_floor: Optional[float] = None
    price_ceiling: Optional[float] = None
    vwap_thresholds: Optional[List[VWAPThreshold]] = None
    min_volume_millions: Optional[float] = None
    bonus_shares_millions: Optional[float] = None
    bonus_period_start: Optional[date] = None
    bonus_period_end: Optional[date] = None
    has_auto_conversion: Optional[bool] = False
    
    # Evaluable payoff model for dynamic computation in frontend/backend
    # This lightweight spec is intentionally a dict to remain flexible and API-friendly.
    # Structure example:
    # {
    #   "modelType": "piecewise",
    #   "inputs": [{"name":"indexReturn","type":"number","unit":"frac"}],
    #   "parameters": {"principal":1000, "leverage":1.95, "buffer":0.30},
    #   "pieces": [
    #     {"when": "indexReturn > 0", "formula": "principal * (1 + leverage * indexReturn)", "outputs": [{"name":"payoff","unit":"USD"}]},
    #     {"when": "indexReturn >= -buffer && indexReturn <= 0", "formula": "principal * (1 + abs(indexReturn))", "outputs": [{"name":"payoff","unit":"USD"}]},
    #     {"when": "indexReturn < -buffer", "formula": "principal * (1 + (indexReturn + buffer))", "outputs": [{"name":"payoff","unit":"USD"}]}
    #   ],
    #   "constraints": {"min":0, "max": null},
    #   "display": {"name":"Dual-directional buffered payout", "primaryUnit":"USD"}
    # }
    payoff_model: Optional[dict] = None
    
    # Natural-language explanation of payoff given key parameters and inputs
    payoff_explainer: Optional[str] = None

class HedgingInstrument(BaseModelWithConfig):
    """Hedging instrument associated with the security"""
    type: str
    description: str
    strike_price: Optional[float] = None
    cap_price: Optional[float] = None
    premium_paid: Optional[float] = None
    expiration_date: Optional[date] = None
    
    # Anti-dilution formula fields
    adjustment_formula: Optional[str] = None  # Exact anti-dilution adjustment formula
    weighted_average_formula: Optional[str] = None  # Weighted average anti-dilution formula
    ratchet_formula: Optional[str] = None  # Ratchet anti-dilution formula
    full_ratchet_formula: Optional[str] = None  # Full ratchet anti-dilution formula
    broad_based_formula: Optional[str] = None  # Broad-based weighted average formula
    narrow_based_formula: Optional[str] = None  # Narrow-based weighted average formula
    calculation_method: Optional[str] = None  # Mathematical calculation method description

class LiquidationTerms(BaseModelWithConfig):
    """Terms related to liquidation preferences and calculations"""
    liquidation_preference_per_share: Optional[float] = None
    liquidation_preference_total: Optional[float] = None
    liquidation_ranking: Optional[str] = None  # "senior_to_common", "junior_to_debt", "pari_passu_with_X"
    liquidation_multiple: Optional[float] = None  # Multiple of original investment (1x, 2x, etc.)
    
    # Participation rights
    is_participating: Optional[bool] = False
    participation_cap: Optional[float] = None
    
    # Cumulative dividends in liquidation
    includes_accrued_dividends: Optional[bool] = True
    dividend_calculation_method: Optional[str] = None

class MetricsSummary(BaseModelWithConfig):
    """Summary of key metrics for the security."""
    coupon_rate: Optional[float] = None
    principal_amount: Optional[float] = None
    conversion_price: Optional[float] = None
    conversion_ratio: Optional[float] = None
    redemption_price: Optional[float] = None
    par_value: Optional[float] = None
    vwap_trigger_price: Optional[float] = None
    vwap_days_required: Optional[int] = None
    earliest_conversion_date: Optional[date] = None
    latest_conversion_date: Optional[date] = None
    earliest_redemption_date: Optional[date] = None
    days_to_first_call: Optional[int] = None
    volume_threshold: Optional[float] = None
    shares_outstanding: Optional[float] = None  # Number of shares outstanding
    
    # Enhanced liquidation and conversion metrics
    liquidation_preference_per_share: Optional[float] = None
    liquidation_preference_total: Optional[float] = None
    variable_conversion_at_current_price: Optional[float] = None  # Shares receivable at current stock price
    conversion_share_cap: Optional[float] = None  # Maximum shares under any scenario
    conversion_break_even_price: Optional[float] = None  # Stock price where conversion = liquidation pref
    
    # Enhanced redemption metrics
    stock_price_call_threshold: Optional[float] = None  # Price threshold as percentage of conversion price
    call_trigger_price: Optional[float] = None  # Absolute price that triggers call option
    has_holder_put_rights: Optional[bool] = None  # Whether security has holder put rights
    put_price: Optional[float] = None  # Price at which holders can put the security
    has_divestiture_redemption: Optional[bool] = None  # Whether security has divestiture-related redemption
    has_make_whole_adjustment: Optional[bool] = None  # Whether security has make-whole provisions
    redemption_measurement_days: Optional[int] = None  # Days over which stock price must exceed threshold
    redemption_window_days: Optional[int] = None  # Days within which price must exceed threshold
    redemption_notice_period: Optional[int] = None  # Notice days required for redemption

# === CORPORATE ACTIONS MODELS ===

class CorporateActionType(str, Enum):
    """Types of corporate actions."""
    TENDER_OFFER = "tender_offer"
    DEBT_REFINANCING = "debt_refinancing"
    ASSET_SALE = "asset_sale"
    ASSET_ACQUISITION = "asset_acquisition"
    SHARE_BUYBACK = "share_buyback"
    SHARE_ISSUANCE = "share_issuance"
    DIVIDEND = "dividend"
    STOCK_SPLIT = "stock_split"
    MERGER = "merger"
    SPIN_OFF = "spin_off"
    BANKRUPTCY = "bankruptcy"
    DELISTING = "delisting"
    RIGHTS_OFFERING = "rights_offering"
    SPECIAL_DIVIDEND = "special_dividend"
    DEBT_ISSUANCE = "debt_issuance"
    CREDIT_FACILITY = "credit_facility"
    RESTRUCTURING = "restructuring"
    ANNUAL_MEETING = "annual_meeting"
    DIRECTOR_ELECTION = "director_election"
    AUDITOR_CHANGE = "auditor_change"
    REDOMESTICATION = "redomestication"
    PREFERRED_ISSUANCE = "preferred_issuance"
    SHARE_AUTHORIZATION = "share_authorization"

class CorporateActionStatus(str, Enum):
    """Status of corporate actions."""
    ANNOUNCED = "announced"
    PENDING = "pending"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"
    CANCELLED = "cancelled"
    CONDITIONAL = "conditional"
    ONGOING = "ongoing"

class ImpactCategory(str, Enum):
    """Impact severity categories."""
    MAJOR = "major"
    MODERATE = "moderate"
    MINOR = "minor"

class BaseCorporateAction(BaseModelWithConfig):
    """Base corporate action with common fields."""
    action_id: str
    action_type: CorporateActionType
    announcement_date: Optional[date] = None
    effective_date: Optional[date] = None
    record_date: Optional[date] = None
    ex_date: Optional[date] = None
    payment_date: Optional[date] = None
    
    title: str
    description: str
    status: CorporateActionStatus
    
    # Transaction parties
    counterparty: Optional[str] = None
    target_company: Optional[str] = None
    
    # Impact assessment
    impact_category: ImpactCategory
    impact_description: Optional[str] = None
    
    # Conditions and approvals
    conditions_precedent: List[str] = []
    regulatory_approvals: Optional[str] = None
    expected_completion: Optional[date] = None
    
    # Source information
    source_filing: str
    source_file: str
    extracted_date: datetime
    
    # Currency
    currency: str = "USD"

class TenderOfferAction(BaseCorporateAction):
    """Specific fields for tender offers and debt exchanges."""
    action_type: CorporateActionType = CorporateActionType.TENDER_OFFER
    
    # Offer terms
    offer_price: Optional[float] = None
    price_per_share: Optional[float] = None
    total_consideration: Optional[float] = None
    premium_to_market: Optional[float] = None  # Premium percentage over market price
    
    # Securities being offered for
    target_security_type: Optional[str] = None  # "6.50% Senior Notes due 2026"
    target_principal_amount: Optional[float] = None  # Amount of debt being tendered
    target_share_count: Optional[float] = None  # Number of shares being tendered
    
    # Securities being offered (if exchange)
    offered_security_type: Optional[str] = None  # "8.75% Senior Secured Second Lien Notes due 2030"
    offered_principal_amount: Optional[float] = None
    offered_share_count: Optional[float] = None
    exchange_ratio: Optional[float] = None  # Ratio between old and new securities
    
    # Tender mechanics
    tender_expiration_date: Optional[date] = None
    withdrawal_deadline: Optional[date] = None
    minimum_tender_condition: Optional[float] = None
    maximum_tender_amount: Optional[float] = None
    proration_possible: Optional[bool] = None
    
    # Financing
    financing_source: Optional[str] = None  # "cash on hand", "new debt", etc.
    cash_consideration: Optional[float] = None
    stock_consideration: Optional[float] = None

class DebtRefinancingAction(BaseCorporateAction):
    """Specific fields for debt refinancing and credit facility actions."""
    action_type: CorporateActionType = CorporateActionType.DEBT_REFINANCING
    
    # Old debt being refinanced
    old_debt_amount: Optional[float] = None
    old_interest_rate: Optional[float] = None
    old_maturity_date: Optional[date] = None
    old_debt_type: Optional[str] = None
    
    # New debt terms
    new_debt_amount: Optional[float] = None
    new_interest_rate: Optional[float] = None
    new_maturity_date: Optional[date] = None
    new_debt_type: Optional[str] = None
    
    # Credit facility details
    facility_size: Optional[float] = None
    borrowing_base: Optional[float] = None
    borrowing_base_change: Optional[float] = None  # Change in borrowing capacity
    undrawn_availability: Optional[float] = None
    
    # Terms and covenants
    interest_rate_type: Optional[str] = None  # "fixed", "floating", "variable"
    interest_rate_benchmark: Optional[str] = None  # "SOFR", "Prime", etc.
    margin_over_benchmark: Optional[float] = None
    financial_covenants: List[str] = []
    
    # Transaction details
    refinancing_costs: Optional[float] = None
    prepayment_penalty: Optional[float] = None
    net_proceeds: Optional[float] = None
    use_of_proceeds: Optional[str] = None

class AssetSaleAction(BaseCorporateAction):
    """Specific fields for asset sales and divestitures."""
    action_type: CorporateActionType = CorporateActionType.ASSET_SALE
    
    # Asset details
    asset_description: str
    business_segment: Optional[str] = None
    geographic_location: Optional[str] = None
    
    # Purchase price
    purchase_price: Optional[float] = None
    cash_consideration: Optional[float] = None
    stock_consideration: Optional[float] = None
    earnout_potential: Optional[float] = None
    contingent_payments: Optional[str] = None
    
    # Asset metrics
    asset_book_value: Optional[float] = None
    annual_revenue: Optional[float] = None
    annual_ebitda: Optional[float] = None
    purchase_price_multiple: Optional[float] = None  # Multiple of revenue/EBITDA
    
    # Transaction structure
    deal_structure: Optional[str] = None  # "asset sale", "stock sale", "merger"
    assumed_liabilities: Optional[float] = None
    retained_liabilities: Optional[float] = None
    
    # Use of proceeds
    use_of_proceeds: Optional[str] = None
    debt_repayment_amount: Optional[float] = None
    
    # Buyer information
    buyer_name: Optional[str] = None
    buyer_type: Optional[str] = None  # "strategic", "financial", "management"

class ShareTransactionAction(BaseCorporateAction):
    """Specific fields for share buybacks and issuances."""
    action_type: CorporateActionType = CorporateActionType.SHARE_BUYBACK  # Can be overridden
    
    # Share details
    share_count: Optional[float] = None
    price_per_share: Optional[float] = None
    total_consideration: Optional[float] = None
    
    # Transaction mechanics
    transaction_method: Optional[str] = None  # "open market", "private placement", "ATM", "block trade"
    execution_period: Optional[str] = None
    average_price: Optional[float] = None
    
    # Program details (for buybacks)
    program_size: Optional[float] = None  # Total authorized amount
    program_remaining: Optional[float] = None
    program_expiration: Optional[date] = None
    
    # Issuance details
    offering_type: Optional[str] = None  # "public", "private", "rights"
    use_of_proceeds: Optional[str] = None
    underwriters: List[str] = []
    
    # Impact on shares
    shares_outstanding_before: Optional[float] = None
    shares_outstanding_after: Optional[float] = None
    percentage_of_outstanding: Optional[float] = None

class AnnualMeetingAction(BaseCorporateAction):
    """Annual shareholder meeting results and governance events."""
    action_type: CorporateActionType = CorporateActionType.ANNUAL_MEETING
    
    # Meeting details
    meeting_date: Optional[date] = None
    meeting_type: Optional[str] = None  # "annual", "special", "adjourned"
    
    # Director elections
    directors_elected: List[str] = []
    directors_continuing: List[str] = []
    directors_retired: List[str] = []
    
    # Voting results - Say on Pay
    say_on_pay_approved: Optional[bool] = None
    say_on_pay_votes_for: Optional[int] = None
    say_on_pay_votes_against: Optional[int] = None
    say_on_pay_abstentions: Optional[int] = None
    
    # Auditor ratification
    auditor_ratified: Optional[bool] = None
    auditor_name: Optional[str] = None
    auditor_votes_for: Optional[int] = None
    auditor_votes_against: Optional[int] = None
    
    # Other proposals
    proposals_voted: List[Dict] = []  # [{"proposal": "...", "result": "passed/failed", "votes_for": 123, "votes_against": 456}]
    
    # Quorum and participation
    shares_represented: Optional[float] = None
    total_shares_outstanding: Optional[float] = None
    quorum_percentage: Optional[float] = None
    
    # Meeting logistics
    meeting_location: Optional[str] = None
    virtual_meeting: Optional[bool] = None

class RedomesticationAction(BaseCorporateAction):
    """Corporate redomestication events and jurisdiction changes."""
    action_type: CorporateActionType = CorporateActionType.REDOMESTICATION
    
    # Jurisdictional change
    old_jurisdiction: Optional[str] = None  # "Delaware"
    new_jurisdiction: Optional[str] = None  # "Indiana"
    
    # Entity type changes
    old_entity_type: Optional[str] = None  # "corporation", "limited_partnership", "LLC"
    new_entity_type: Optional[str] = None  # Same options
    
    # Share/unit conversion
    conversion_ratio: Optional[float] = None  # Usually 1:1
    shares_before: Optional[float] = None
    shares_after: Optional[float] = None
    cusip_change: Optional[bool] = None
    ticker_change: Optional[bool] = None
    new_cusip: Optional[str] = None
    
    # Tax implications
    tax_free_reorganization: Optional[bool] = None
    irs_ruling_obtained: Optional[bool] = None
    tax_opinion_obtained: Optional[bool] = None
    
    # Governance changes
    governance_changes: List[str] = []
    voting_rights_changes: Optional[str] = None
    charter_changes: List[str] = []
    
    # Reasons for redomestication
    stated_reasons: List[str] = []
    cost_savings_expected: Optional[float] = None
    regulatory_benefits: List[str] = []
    
    # Approval process
    board_approval_date: Optional[date] = None
    shareholder_approval_date: Optional[date] = None
    regulatory_approval_required: Optional[bool] = None

class PreferredStockAction(BaseCorporateAction):
    """Preferred stock issuance, modification, or redemption."""
    action_type: CorporateActionType = CorporateActionType.PREFERRED_ISSUANCE
    
    # Series details
    series_name: Optional[str] = None  # "Series J"
    shares_authorized: Optional[float] = None
    shares_issued: Optional[float] = None
    par_value: Optional[float] = None
    issue_price: Optional[float] = None
    
    # Dividend terms
    dividend_rate: Optional[float] = None  # 8.375%
    dividend_type: Optional[str] = None  # "cumulative", "non-cumulative"
    dividend_payment_frequency: Optional[str] = None  # "quarterly", "annually"
    dividend_payment_dates: List[str] = []
    first_dividend_date: Optional[date] = None
    
    # Liquidation terms
    liquidation_preference: Optional[float] = None
    liquidation_ranking: Optional[str] = None  # "senior_to_common", "pari_passu"
    liquidation_multiple: Optional[float] = None
    
    # Conversion features
    convertible_to_common: Optional[bool] = None
    conversion_ratio: Optional[float] = None
    conversion_price: Optional[float] = None
    conversion_triggers: List[str] = []
    
    # Redemption features
    redeemable_by_company: Optional[bool] = None
    earliest_redemption_date: Optional[date] = None
    redemption_price: Optional[float] = None
    mandatory_redemption: Optional[bool] = None
    redemption_conditions: List[str] = []
    
    # Voting rights
    voting_rights: Optional[str] = None  # "full", "limited", "none"
    voting_conditions: List[str] = []
    special_voting_rights: Optional[str] = None
    
    # Financial details
    gross_proceeds: Optional[float] = None
    net_proceeds: Optional[float] = None
    use_of_proceeds: Optional[str] = None
    offering_expenses: Optional[float] = None
    
    # Rating and features
    credit_rating: Optional[str] = None
    callable: Optional[bool] = None
    puttable: Optional[bool] = None

class ShareAuthorizationAction(BaseCorporateAction):
    """Changes to authorized share capital."""
    action_type: CorporateActionType = CorporateActionType.SHARE_AUTHORIZATION
    
    # Authorization changes
    old_authorized_shares: Optional[float] = None
    new_authorized_shares: Optional[float] = None
    authorization_increase: Optional[float] = None
    authorization_decrease: Optional[float] = None
    
    # Share class details
    share_class: Optional[str] = None  # "common", "preferred", "Class A", etc.
    par_value: Optional[float] = None
    share_class_rights: Optional[str] = None
    
    # Rationale and purpose
    stated_purpose: Optional[str] = None
    immediate_issuance_planned: Optional[bool] = None
    planned_issuance_amount: Optional[float] = None
    future_financing_flexibility: Optional[bool] = None
    
    # Approval details
    shareholder_approval_required: Optional[bool] = None
    board_approval_date: Optional[date] = None
    shareholder_approval_date: Optional[date] = None
    votes_for: Optional[int] = None
    votes_against: Optional[int] = None
    
    # Current utilization
    shares_outstanding_current: Optional[float] = None
    shares_reserved_for_options: Optional[float] = None
    shares_available_for_issuance: Optional[float] = None
    utilization_percentage_before: Optional[float] = None
    utilization_percentage_after: Optional[float] = None
    
    # Anti-dilution provisions
    preemptive_rights_affected: Optional[bool] = None
    dilution_protection: Optional[str] = None

class CorporateActionResult(BaseModelWithConfig):
    """Complete result of corporate action extraction for a company."""
    ticker: str
    extraction_metadata: Dict = {}
    summary_statistics: Dict = {}
    corporate_actions: List[BaseCorporateAction] = []

class OriginalDataReference(BaseModelWithConfig):
    """Reference to the original data with feature flags."""
    id: Optional[str] = None
    has_raw_redemption_features: Optional[bool] = False
    has_raw_conversion_features: Optional[bool] = False
    has_special_features: Optional[bool] = False
    llm_commentary: Optional[str] = None  # Field for LLM commentary on this security

class SecurityData(BaseModelWithConfig):
    """Comprehensive data about a convertible security"""
    # Basic information
    id: str
    company: str
    type: str
    filing_date: date
    principal_amount: Optional[float] = None
    rate: Optional[float] = None
    maturity_date: Optional[date] = None
    issue_date: Optional[date] = None
    description: str
    raw_description: Optional[str] = None  # Full unprocessed description text
    shares_outstanding: Optional[float] = None  # Number of shares still outstanding
    is_active: Optional[bool] = True  # Whether the security is still active
    is_publicly_traded: Optional[bool] = False  # Whether the security is publicly traded
    filing_source: Optional[str] = None  # Source filing type (10-K, 10-Q, 8-K, etc.)
    
    # Core features
    conversion_terms: Optional[ConversionTerms] = None
    liquidation_terms: Optional[LiquidationTerms] = None
    conversion_conditions: Optional[List[ConversionCondition]] = []
    redemption_conditions: Optional[List[RedemptionCondition]] = []
    hedging_features: Optional[List[HedgingInstrument]] = []
    
    # Quick filters
    has_make_whole_provisions: Optional[bool] = False
    has_vwap_pricing: Optional[bool] = False
    has_change_control_provisions: Optional[bool] = False
    has_hedging: Optional[bool] = False
    has_dynamic_pricing: Optional[bool] = False
    
    # Quantitative metrics for modeling
    metrics: Optional[MetricsSummary] = None
    
    # Enhanced quantitative metrics for numerical analysis
    quantitative_metrics: Optional[QuantitativeMetrics] = None
    
    # Additional metadata
    currency: Optional[str] = "USD"
    liquidation_preference: Optional[float] = None
    
    # LLM special commentary and insights
    llm_commentary: Optional[str] = None  # Additional LLM insights not captured in structured fields
    
    # Reference to original data
    original_data_reference: Optional[OriginalDataReference] = None

class ComprehensiveSecurityResult(BaseModelWithConfig):
    """
    Represents the comprehensive result of security extraction, 
    including both LLM and XBRL extracted data.
    """
    ticker: str
    filing_type: str
    extraction_timestamp: datetime = datetime.now()
    extraction_methods: List[str] = []
    securities: Optional[List[SecurityData]] = [] # Combined LLM and XBRL securities
    llm_securities: Optional[List[SecurityData]] = []
    xbrl_securities: Optional[List[Dict]] = []
    total_securities: int = 0
    llm_securities_count: int = 0
    xbrl_securities_count: int = 0
    metadata: Dict = {} # General metadata about the extraction process 
    
    # Enhanced liquidation and conversion metrics
    liquidation_preference_per_share: Optional[float] = None
    liquidation_preference_total: Optional[float] = None
    variable_conversion_at_current_price: Optional[float] = None  # Shares receivable at current stock price
    conversion_share_cap: Optional[float] = None  # Maximum shares under any scenario
    conversion_break_even_price: Optional[float] = None  # Stock price where conversion = liquidation pref
    
    # Enhanced redemption metrics
    stock_price_call_threshold: Optional[float] = None  # Price threshold as percentage of conversion price
    call_trigger_price: Optional[float] = None  # Absolute price that triggers call option
    has_holder_put_rights: Optional[bool] = None  # Whether security has holder put rights
    put_price: Optional[float] = None  # Price at which holders can put the security
    has_divestiture_redemption: Optional[bool] = None  # Whether security has divestiture-related redemption
    has_make_whole_adjustment: Optional[bool] = None  # Whether security has make-whole provisions
    redemption_measurement_days: Optional[int] = None  # Days over which stock price must exceed threshold
    redemption_window_days: Optional[int] = None  # Days within which price must exceed threshold
    redemption_notice_period: Optional[int] = None  # Notice days required for redemption 

class FormulaDisplayMetrics(BaseModelWithConfig):
    """Standardized formula metrics optimized for frontend display and API consumption."""
    
    # High-level formula classification for easy filtering
    formula_category: str = "unknown"  # "vwap", "min_max", "anti_dilution", "floating_rate", "cashless_exercise"
    formula_type: str = "unknown"  # More specific type within category
    
    # Human-readable summary for display
    display_name: str = ""  # e.g., "200% VWAP Trigger", "5-Day Average Pricing"
    description: str = ""   # e.g., "Stock price must exceed 200% of conversion price for 20 trading days"
    
    # Key numerical values for charts/analysis
    primary_value: Optional[float] = None      # Main number (e.g., 200 for "200%")
    primary_unit: Optional[str] = None         # Unit (e.g., "percent", "days", "dollars")
    secondary_value: Optional[float] = None    # Secondary number if applicable
    secondary_unit: Optional[str] = None
    
    # Time components for timeline displays
    time_period_days: Optional[int] = None     # e.g., 20 for "20 trading days"
    time_period_type: Optional[str] = None     # e.g., "trading_days", "calendar_days"
    
    # Mathematical structure for programmatic use
    mathematical_operator: Optional[str] = None  # "greater_than", "less_than", "equals", "between"
    comparison_values: List[float] = []           # Values being compared
    
    # Original text for transparency
    source_text: str = ""                     # Original formula text
    confidence_score: float = 1.0             # How confident we are in the extraction (0-1)
    
    # Frontend display helpers
    is_threshold: bool = False                # True for trigger conditions
    is_pricing: bool = False                  # True for pricing formulas
    is_timing: bool = False                   # True for time-based conditions
    
    # API-friendly tags for filtering
    tags: List[str] = []                      # e.g., ["trigger", "conversion", "vwap"]

class StandardizedSecurityMetrics(BaseModelWithConfig):
    """Clean, API-friendly security metrics for frontend consumption."""
    
    # Core identification
    security_id: str
    security_name: str
    security_type: str  # "convertible_bond", "preferred_stock", "warrant", "note"
    
    # Key financial metrics (always populated when available)
    principal_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    maturity_date: Optional[str] = None
    
    # Formula library - standardized for easy frontend consumption
    formulas: List[FormulaDisplayMetrics] = []
    
    # Summary statistics for quick display
    total_formulas: int = 0
    formula_categories: List[str] = []  # Unique categories present
    complexity_score: str = "low"      # "low", "medium", "high" based on formula count/complexity
    
    # Risk indicators for highlighting
    has_trigger_conditions: bool = False
    has_variable_pricing: bool = False
    has_conversion_features: bool = False
    
    # Frontend display metadata
    last_updated: str = ""
    data_quality_score: float = 1.0  # 0-1 confidence in all data
    
    # API versioning
    schema_version: str = "1.0" 