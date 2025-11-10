# api/v2/leakage.py (FastAPI Router)

from fastapi import APIRouter, Depends, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

# Import dependencies
from ...dependencies import get_db, get_current_user_id

# Import services
from ...services.financial_profile_service import FinancialProfileService
from ...services.leakage_service import LeakageService

# Import schemas for request/response bodies
from ...schemas.user_profile import UserProfileCreate, UserProfileOut
from ...schemas.financial_profile import FinancialProfileResponse # Simplified response for DMB output
from ...schemas.leakage_data import LeakageOut

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
    This locks in the core DMB parameters used for Leakage tracking.
    """
    # 1. Update the User's demographic data (input for EFS)
    fp_service = FinancialProfileService(db_session, user_id)
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
    reporting_period_str: str,
    db_session: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    Exposes the leakage dashboard which shows: total reclaimable salary and the category breakdown 
    of spending vs. the Dynamic Minimal Baseline.
    """
    from datetime import date
    try:
        reporting_period = date.fromisoformat(reporting_period_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid date format. Must be YYYY-MM-DD."
        )

    # Note: We use LeakageService directly here as it encapsulates the view logic
    leak_service = LeakageService(db_session, user_id)
    # The LeakageService.calculate_leakage method is suitable as it calculates and returns the full profile
    leak_data = await leak_service.calculate_leakage(reporting_period)

    # Return the data that matches the LeakageOut schema (which is a subset of the profile dict)
    return leak_data
