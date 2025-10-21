# finance-app-backend/api/v2_router.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from typing import Dict, Any
from datetime import datetime

# Import Dependencies and Services
from ..dependencies import get_db, get_verified_user_id 
from ..services.leakage_service import LeakageService 
from ..services.orchestration_service import OrchestrationService

# 🚨 V2 ADDITION: Import Schemas for Leakage/Consent
from ..schemas.leakage_data import LeakageOut 
from ..schemas.orchestration_data import (
    ConsentPlanOut,          # Output schema for the suggestion plan
    ConsentMoveIn,           # Input schema for the consent move request
    ConsentMoveOut           # Output schema after the consent is recorded
)


router = APIRouter(
    prefix="/v2",
    tags=["Fin-Traq V2 Leak Finder & Autopilot"],
    # 🚨 SECURITY: All V2 endpoints require X-API-Key and a valid Firebase token
    dependencies=[Depends(get_verified_user_id)] 
)

# ----------------------------------------------------------------------
# 1. LEAK FINDER (PHASE 1) - READ-ONLY 
# ----------------------------------------------------------------------

@router.get(
    "/leakage-buckets", 
    response_model=LeakageOut,
    status_code=status.HTTP_200_OK,
    summary="Get the Leakage Bucket View using Stratified Dependent Scaling (SDS)."
)
def get_leakage_bucket_view(
    user_id: str = Depends(get_verified_user_id), 
    db: Session = Depends(get_db)
):
    """
    Calculates the financial leakage amount, replacing the old expense dashboard view.
    """
    try:
        leakage_service = LeakageService(db=db, user_id=user_id)
        leakage_data = leakage_service.calculate_leakage()
        return leakage_data
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An error occurred during leakage calculation."
        )

# ----------------------------------------------------------------------
# 2. AUTOPILOT SUGGESTION (PHASE 2) - READ-ONLY 
# ----------------------------------------------------------------------

@router.post(
    "/autopilot-plan",
    response_model=ConsentPlanOut, # 🚨 UPDATED RESPONSE MODEL
    status_code=status.HTTP_200_OK,
    summary="Generates the Consent Suggestion Plan for recovered money (read-only)."
)
def generate_consent_suggestion_plan(
    reporting_period: str, # Expecting 'YYYY-MM-DD'
    user_id: str = Depends(get_verified_user_id),
    db: Session = Depends(get_db)
):
    """
    Calculates how recovered money SHOULD be converted into goals based on Smart Rules.
    This is a READ operation; it does NOT commit any balance changes.
    """
    try:
        period_date = datetime.strptime(reporting_period, "%Y-%m-%d").date()
        orchestration_service = OrchestrationService(db=db, user_id=user_id)
        
        # 🚨 UPDATED CALL: Use the new suggestion method
        plan = orchestration_service.generate_consent_suggestion_plan(
            reporting_period=period_date
        )
        
        return plan
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Invalid date format or data: {e}"
        )
    except Exception as e:
        # Catch NoResultFound from the service if the profile is missing
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=str(e)
        )

# ----------------------------------------------------------------------
# 3. CONSENT EXECUTION (PHASE 2) - WRITE ACTION 
# ----------------------------------------------------------------------

@router.post(
    "/autopilot-consent",
    response_model=ConsentMoveOut, # 🚨 NEW RESPONSE MODEL
    status_code=status.HTTP_200_OK,
    summary="Records user consent and updates the internal displayed balance (WRITE action)."
)
def record_consent_move(
    consent_request: ConsentMoveIn, # 🚨 NEW INPUT SCHEMA
    user_id: str = Depends(get_verified_user_id),
    db: Session = Depends(get_db)
):
    """
    This endpoint is called when the user consents ('YES'). It performs the
    internal 'move' by adjusting the user's tracking fields in the database.
    """
    try:
        # Convert string date from schema input to datetime.date object
        period_date = datetime.strptime(consent_request.reporting_period, "%Y-%m-%d").date()
        
        orchestration_service = OrchestrationService(db=db, user_id=user_id)
        
        # This is the function that contains the db.commit()
        result = orchestration_service.record_consent_and_update_balance(
            consented_amount=consent_request.consented_amount,
            reporting_period=period_date
        )
        
        return result
        
    except HTTPException:
        # Re-raise explicit HTTP exceptions (e.g., 400 validation from the service)
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to record consent: {e}"
        )
