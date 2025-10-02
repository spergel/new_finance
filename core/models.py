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

class RedemptionTerms(BaseModelWithConfig):
    """Terms for redeeming or calling the security"""
    is_callable: Optional[bool] = False
    call_price: Optional[float] = None
    earliest_call_date: Optional[date] = None
    notice_period_days: Optional[int] = None
    has_make_whole: Optional[bool] = False

class SpecialFeatures(BaseModelWithConfig):
    """Special features like change-of-control provisions"""
    has_change_of_control: Optional[bool] = False
    change_of_control_protection: Optional[str] = None
    has_anti_dilution: Optional[bool] = False
    has_vwap_pricing: Optional[bool] = False

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

    # Conversion features
    conversion_terms: Optional[ConversionTerms] = None

    # Redemption features
    redemption_terms: Optional[RedemptionTerms] = None

    # Special features
    special_features: Optional[SpecialFeatures] = None

    # Source information
    source_filing: str
    extraction_confidence: float = 1.0

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