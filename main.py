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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
