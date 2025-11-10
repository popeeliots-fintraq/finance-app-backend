# api/v2/leakage.py (FastAPI Router for ML Initialization and Leak View)

from fastapi import APIRouter, Depends, HTTPException, status, Query # <-- FIXED: Added HTTPException and Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from datetime import date # <-- FIXED: Added date import

# Import dependencies
from ...dependencies import get_db, get_current_user_id

# Import services
from ...services.financial_profile_service import FinancialProfileService
from ...services.leakage_service import LeakageService

# Import schemas for request/response bodies
from ...schemas.user_profile import UserProfileCreate, UserProfileOut
from ...schemas.financial_profile import FinancialProfileResponse # Returns the EFS, BEF, and DMB values
from ...schemas.leakage_data import LeakageOut # Matches the full Leakage Bucket View

router = APIRouter(
    prefix="/leakage",
    tags=["Leakage & ML (EFS/DMB)"],
)

# ----------------------------------------------------------------------
# ENDPOINT 1: INITIALIZE / UPDATE EFS & DMB (The ML Engine Trigger)
# ----------------------------------------------------------------------
@router.post(
    "/initialize-profile",
    response_model=FinancialProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculates and saves the Equivalent Family Size (EFS) and Dynamic Minimal Baseline (DMB) for a user."
)
async def initialize_user_profile(
    profile_data: UserProfileCreate, # Input fields for EFS/DMB calculation
    db_session: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    Called upon user onboarding or when family/financial circumstances change. 
    This locks in the core DMB parameters used for Stratified Dependent Scaling (SDS) [cite: 2025-10-20].
    """
    # 1. Update the User's demographic data (input for EFS)
    fp_service = FinancialProfileService(db_session, user_id)
    # Use profile_data.model_dump() to get the dictionary payload
    await fp_service.update_user_profile(profile_data.model_dump())
    
    # 2. Calculate and persist EFS/BEF/DMB
    # This calls the complex ML logic: EFS calculation -> BEF calculation -> DMB persistence
    dmb_result = await fp_service.calculate_and_save_dmb()
    
    return dmb_result

# ----------------------------------------------------------------------
# ENDPOINT 2: GET LATEST LEAKAGE BUCKET VIEW (The V2 Dashboard)
# ----------------------------------------------------------------------
@router.get(
    "/current-leak-view",
    response_model=LeakageOut, # This matches the full Leakage Bucket View
    summary="Retrieves the current MTD Leakage Bucket View based on the latest DMB and transactions."
)
async def get_current_leakage_view(
    # Use Query for URL parameters
    reporting_period_str: str = Query(..., description="Reporting period start date (YYYY-MM-DD)"),
    db_session: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    Exposes the core 'Leakage Bucket View' which shows: total reclaimable salary 
    (leakage recovery) and the category breakdown of spending vs. the Dynamic Minimal Baseline. 
    This replaces the old expense dashboard task [cite: 2025-10-15].
    """
    try:
        reporting_period = date.fromisoformat(reporting_period_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid date format. Must be YYYY-MM-DD."
        )

    leak_service = LeakageService(db_session, user_id)
    
    # The calculate_leakage method calculates and returns the full profile leak data
    leak_data = await leak_service.calculate_leakage(reporting_period)

    return leak_data
