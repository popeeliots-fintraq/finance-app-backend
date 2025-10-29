# v2_router.py (in the 'api' folder)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from typing import List, Dict, Any

# Assuming standard FastAPI dependencies and utility functions
# Paths are correct because 'api' is a sibling to 'db', 'services', etc.
from ..dependencies import get_db, get_current_user_id 

# Import the core services
from ..services.orchestration_service import OrchestrationService

# --- V2 ADDITION: Import the Leakage Router ---
# CRITICAL FIX: The path must be relative to this file's location ('api/').
# Assuming 'leakage.py' is in 'api/v2/leakage.py'
from .v2.leakage import router as leakage_router 

# Import the Pydantic schemas you provided
from ..schemas.orchestration_data import (
    ConsentPlanOut, ConsentMoveIn, ConsentMoveOut, 
    RecalculationResponse, SuggestedAllocation
)

router = APIRouter(
    prefix="/v2",
    tags=["Autopilot V2 (Salary Maximizer)"],
)

# ======================================================================
# V2 ROUTER REGISTRATION
# ======================================================================

# Include the new Leakage Router. 
# Endpoints available: /v2/leakage/calculate and /v2/leakage/insights
router.include_router(leakage_router)


# ----------------------------------------------------------------------
# UTILITY: MOCK TRANSACTION HOOK (SIMULATING INGESTION COMPLETION)
# ----------------------------------------------------------------------

@router.post(
    "/autopilot/transaction-hook", 
    response_model=RecalculationResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate new categorized transaction; triggers Orchestration and Proactive Insights."
)
def transaction_hook_trigger_orchestration(
    # In a real system, the body would contain the new Transaction ID and its date
    reporting_period_str: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id) 
):
    """
    Called by the internal categorization worker after a raw SMS/UPI message 
    has been successfully converted into a clean Transaction record. 
    
    This runs the core Autopilot loop: recalculating leakage, attempting immediate 
    real-time conversion, and generating proactive/reactive insights (Leak Cards).
    """
    try:
        reporting_period = date.fromisoformat(reporting_period_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid date format. Must be YYYY-MM-DD."
        )

    orch_service = OrchestrationService(db, user_id)
    
    # This call executes the 'recalculate_current_period_leakage' method
    result = orch_service.recalculate_current_period_leakage(reporting_period)

    return result


# ----------------------------------------------------------------------
# GUIDED EXECUTION: SUGGESTION ENDPOINT
# ----------------------------------------------------------------------

@router.get(
    "/autopilot/suggestion-plan", 
    response_model=ConsentPlanOut,
    summary="Generates the tax-optimized allocation plan from the recovered salary pool."
)
def get_suggestion_plan(
    reporting_period_str: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    Fetches the Autopilot's recommended allocation plan for the current available 
    reclaimable fund, prioritizing tax savings and goals.
    """
    try:
        reporting_period = date.fromisoformat(reporting_period_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid date format. Must be YYYY-MM-DD."
        )

    orch_service = OrchestrationService(db, user_id)
    plan_data = orch_service.generate_consent_suggestion_plan(reporting_period)

    # Note: Pydantic will validate the dictionary returned by the service method 
    # against the ConsentPlanOut schema automatically.
    return plan_data


# ----------------------------------------------------------------------
# GUIDED EXECUTION: CONSENT/EXECUTION ENDPOINT
# ----------------------------------------------------------------------

@router.post(
    "/autopilot/consent", 
    response_model=ConsentMoveOut,
    summary="Executes the user-consented Autopilot transfers and logs the audit trail."
)
def execute_autopilot_consent(
    consent_data: ConsentMoveIn,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    This endpoint executes the final step of the Guided Orchestration. 
    It records the consent, logs the transfers with the audit field, 
    and updates the Salary Allocation Profile.
    """
    try:
        reporting_period = date.fromisoformat(consent_data.reporting_period)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid date format for reporting_period. Must be YYYY-MM-DD."
        )

    orch_service = OrchestrationService(db, user_id)
    
    # Convert ConsentTransferItem list to a list of dictionaries 
    # expected by the service method's 'transfer_plan' argument
    transfer_plan_dicts = [item.model_dump() for item in consent_data.transfer_plan]

    result = orch_service.record_consent_and_update_balance(
        transfer_plan=transfer_plan_dicts, 
        reporting_period=reporting_period
    )
    
    return result
