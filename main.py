#!/usr/bin/env python3
"""
SEC Securities API

Simple FastAPI backend for securities features and corporate actions extraction.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import date

from core.securities_features_extractor import extract_securities_features, SecuritiesFeaturesResult
from core.corporate_actions_extractor import extract_corporate_actions, CorporateActionsResult
from core.xbrl_preferred_shares_extractor import extract_xbrl_preferred_shares

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SEC Securities API",
    description="API for extracting securities features and corporate actions from SEC filings",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ExtractionRequest(BaseModel):
    ticker: str
    api_key: Optional[str] = None

class ExtractionResponse(BaseModel):
    success: bool
    message: str
    result: Optional[dict] = None

@app.get("/")
async def root():
    """Root endpoint - API status"""
    return {
        "message": "SEC Securities API",
        "version": "1.0.0",
        "endpoints": {
            "securities": "/extract/securities/{ticker}",
            "actions": "/extract/actions/{ticker}",
            "xbrl": "/extract/xbrl/{ticker}",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": date.today().isoformat()}

@app.post("/extract/securities")
async def extract_securities(request: ExtractionRequest, background_tasks: BackgroundTasks):
    """Extract securities features for a ticker"""
    try:
        logger.info(f"Extracting securities features for {request.ticker}")

        result = extract_securities_features(request.ticker, request.api_key)

        # Save LLM data to organized directory
        from core.securities_features_extractor import SecuritiesFeaturesExtractor
        extractor = SecuritiesFeaturesExtractor(request.api_key)
        extractor.save_results(result)

        return ExtractionResponse(
            success=True,
            message=f"Successfully extracted {result.total_securities} securities",
            result=result.dict()
        )

    except Exception as e:
        logger.error(f"Error extracting securities for {request.ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract/actions")
async def extract_actions(request: ExtractionRequest, background_tasks: BackgroundTasks):
    """Extract corporate actions for a ticker"""
    try:
        logger.info(f"Extracting corporate actions for {request.ticker}")

        result = extract_corporate_actions(request.ticker, request.api_key)

        # Save LLM data to organized directory
        from core.corporate_actions_extractor import CorporateActionsExtractor
        extractor = CorporateActionsExtractor(request.api_key)
        extractor.save_results(result)

        return ExtractionResponse(
            success=True,
            message=f"Successfully extracted {result.total_actions} corporate actions",
            result=result.dict()
        )

    except Exception as e:
        logger.error(f"Error extracting actions for {request.ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/extract/securities/{ticker}")
async def get_securities_features(ticker: str, api_key: Optional[str] = None):
    """Get securities features for a ticker (GET endpoint)"""
    try:
        result = extract_securities_features(ticker, api_key)

        return {
            "ticker": result.ticker,
            "extraction_date": result.extraction_date.isoformat(),
            "total_securities": result.total_securities,
            "securities": [
                {
                    "security_id": s.security_id,
                    "security_type": s.security_type.value,
                    "principal_amount": s.principal_amount,
                    "interest_rate": s.interest_rate,
                    "maturity_date": s.maturity_date.isoformat() if s.maturity_date else None,
                    "conversion_terms": s.conversion_terms.dict() if s.conversion_terms else None,
                    "redemption_terms": s.redemption_terms.dict() if s.redemption_terms else None,
                    "special_features": s.special_features.dict() if s.special_features else None,
                }
                for s in result.securities
            ]
        }

    except Exception as e:
        logger.error(f"Error getting securities for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/extract/actions/{ticker}")
async def get_corporate_actions(ticker: str, api_key: Optional[str] = None):
    """Get corporate actions for a ticker (GET endpoint)"""
    try:
        result = extract_corporate_actions(ticker, api_key)

        return {
            "ticker": result.ticker,
            "extraction_date": result.extraction_date.isoformat(),
            "total_actions": result.total_actions,
            "corporate_actions": [
                {
                    "action_id": a.action_id,
                    "action_type": a.action_type.value,
                    "title": a.title,
                    "description": a.description,
                    "announcement_date": a.announcement_date.isoformat() if a.announcement_date else None,
                    "status": a.status.value,
                    "amount": a.amount,
                    "target_security": a.target_security,
                }
                for a in result.corporate_actions
            ]
        }

    except Exception as e:
        logger.error(f"Error getting actions for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract/xbrl")
async def extract_xbrl_data(request: ExtractionRequest):
    """Extract XBRL preferred shares data for a ticker"""
    try:
        logger.info(f"Extracting XBRL data for {request.ticker}")

        result = extract_xbrl_preferred_shares(request.ticker)

        return ExtractionResponse(
            success=True,
            message=f"Successfully extracted XBRL data with {result.get('xbrl_tags_found', 0)} tags found",
            result=result
        )

    except Exception as e:
        logger.error(f"Error extracting XBRL data for {request.ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/extract/xbrl/{ticker}")
async def get_xbrl_data(ticker: str):
    """Get XBRL preferred shares data for a ticker (GET endpoint)"""
    try:
        result = extract_xbrl_preferred_shares(ticker)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        return {
            "ticker": result["ticker"],
            "filing_type": result.get("filing_type", "10-Q"),
            "extraction_date": result.get("extraction_date"),
            "xbrl_available": result.get("xbrl_available", False),
            "summary": {
                "has_preferred_shares": result.get("has_preferred_shares", False),
                "xbrl_tags_found": result.get("xbrl_tags_found", 0),
                "series_identified": result.get("series_identified", []),
                "cusips_identified": result.get("cusips_identified", []),
                "data_quality_score": result.get("data_quality_score", 0.0),
                "total_mentioned": result.get("total_mentioned", 0)
            },
            "tag_distribution": result.get("tag_distribution", {}),
            "numeric_values_found": result.get("numeric_values_found", [])
        }

    except Exception as e:
        logger.error(f"Error getting XBRL data for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
