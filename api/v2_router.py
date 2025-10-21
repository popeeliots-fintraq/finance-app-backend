# finance-app-backend/api/v2_router.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from typing import Dict, Any

# Import Dependencies and Services
from ..dependencies import get_db, get_verified_user_id # Assume get_verified_user_id uses Firebase Auth
from ..services.leakage_service import LeakageService 
from ..services.orchestration_service import OrchestrationService
from ..schemas.leakage_data import LeakageOut  # 🚨 ASSUMPTION: You will create this schema next

router = APIRouter(
    prefix="/v2",
    tags=["Fin-Traq V2 Leak Finder & Autopilot"],
    # 🚨 SECURITY: All V2 endpoints require X-API-Key and a valid Firebase token
    dependencies=[Depends(get_verified_user_id)] 
)

@router.get(
    "/leakage-buckets", 
    response_model=LeakageOut, # 🚨 Assuming you will define this Pydantic schema
    status_code=status.HTTP_200_OK,
    summary="Get the Leakage Bucket View using Stratified Dependent Scaling (SDS)."
)
def get_leakage_bucket_view(
    user_id: str = Depends(get_verified_user_id), # User ID verified from Firebase Token
    db: Session = Depends(get_db)
):
    """
    Calculates the financial leakage amount from categorized spends by comparing 
    spending against the Dynamic Minimal Baseline (DMB) refined by SDS. 
    Replaces the old expense dashboard view. [cite: 2025-10-15]
    """
    try:
        leakage_service = LeakageService(db=db, user_id=user_id)
        
        # This calls the service that uses the EFS/SDS logic you just committed
        leakage_data = leakage_service.calculate_leakage()
        
        return leakage_data
        
    except ValueError as e:
        # Catch errors from the service (e.g., Salary Allocation Profile not found)
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
# 🚨 NEXT ROUTE: SALARY AUTOPILOT (ORCHESTRATION) 
# ----------------------------------------------------------------------

@router.post(
    "/autopilot-plan",
    status_code=status.HTTP_200_OK,
    summary="Calculate the Salary Autopilot transfer plan."
)
def generate_automated_transfer_plan(
    # NOTE: You might need to adjust the date input based on how your client sends it
    reporting_period: str, # Expecting 'YYYY-MM-DD'
    user_id: str = Depends(get_verified_user_id),
    db: Session = Depends(get_db)
):
    """
    Calculates how recovered money (leakage) is converted into tax savings or goals 
    automatically based on Smart Rules (Guided Execution). [cite: 2025-10-15]
    """
    try:
        # Convert string date to datetime.date object
        from datetime import datetime
        period_date = datetime.strptime(reporting_period, "%Y-%m-%d").date()
        
        orchestration_service = OrchestrationService(db=db, user_id=user_id)
        
        plan = orchestration_service.calculate_automated_transfer_plan(
            reporting_period=period_date
        )
        
        return plan
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Invalid date format or data: {e}"
        )

# Don't forget to import this new router into your main application file (e.g., app.py).
