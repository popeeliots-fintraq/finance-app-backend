# api/v2_router.py

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import date
from typing import List, Dict, Any
from pydantic import BaseModel, Field

# 🌟 CRITICAL: Use AsyncSession for SQLAlchemy
from sqlalchemy.ext.asyncio import AsyncSession 

# Assuming standard FastAPI dependencies and utility functions
from ..dependencies import get_db, get_current_user_id 

# Import the core services
from ..services.orchestration_service import OrchestrationService

# --- V2 ADDITION: Import the Leakage Router ---
# Assuming 'leakage.py' is in 'api/v2/leakage.py' (This path should be confirmed, but structure is fine)
from .v2.leakage import router as leakage_router 

# 🌟 FIX: Import the CORRECTED Pydantic schemas
from ..schemas.orchestration_data import (
    # ConsentPlanOut -> SuggestionPlanResponse (Finalized name)
    SuggestionPlanResponse, 
    # ConsentMoveOut -> ExecutionResponse (Finalized name)
    ExecutionResponse,
    # RecalculationResponse is correct
    RecalculationResponse,
    # We need the Input model for the POST /consent endpoint
    TransferSuggestion
)

# 🌟 FIX: Define the required Pydantic Input model for the /consent body
class ConsentMoveIn(BaseModel):
    # This structure is needed because ConsentMoveIn was not defined in the provided schemas
    reporting_period: str = Field(..., description="The reporting period for the consent (YYYY-MM-DD).")
    transfer_plan: List[TransferSuggestion] = Field(..., description="The list of transfers to be executed (user's consented plan).")


router = APIRouter(
    prefix="/v2",
    tags=["Autopilot V2 (Salary Maximizer)"],
)

# ======================================================================
# V2 ROUTER REGISTRATION
# ======================================================================

# Include the new Leakage Router. 
router.include_router(leakage_router)


# ----------------------------------------------------------------------
# UTILITY: MOCK TRANSACTION HOOK (SIMULATING INGESTION COMPLETION)
# ----------------------------------------------------------------------

@router.post(
    "/autopilot/transaction-hook", 
    response_model=RecalculationResponse, # Correct: Matches the output of recalculate_current_period_leakage
    status_code=status.HTTP_200_OK,
    summary="Simulate new categorized transaction; triggers Orchestration and Proactive Insights."
)
async def transaction_hook_trigger_orchestration(
    reporting_period_str: str,
    db_session: AsyncSession = Depends(get_db), 
    user_id: int = Depends(get_current_user_id) 
):
    """
    Called by the internal categorization worker after a raw SMS/UPI message 
    has been successfully converted into a clean Transaction record. 
    """
    try:
        reporting_period = date.fromisoformat(reporting_period_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid date format. Must be YYYY-MM-DD."
        )

    orch_service = OrchestrationService(db_session, user_id) 
    
    # This executes the 'recalculate_current_period_leakage' method
    result = await orch_service.recalculate_current_period_leakage(reporting_period)

    return result


# ----------------------------------------------------------------------
# GUIDED EXECUTION: SUGGESTION ENDPOINT
# ----------------------------------------------------------------------

@router.get(
    "/autopilot/suggestion-plan", 
    response_model=SuggestionPlanResponse, # 🌟 FIXED: Use the correct schema name
    summary="Generates the tax-optimized allocation plan from the recovered salary pool."
)
async def get_suggestion_plan(
    reporting_period_str: str,
    db_session: AsyncSession = Depends(get_db), 
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

    orch_service = OrchestrationService(db_session, user_id) 
    plan_data = await orch_service.generate_consent_suggestion_plan(reporting_period)

    return plan_data


# ----------------------------------------------------------------------
# GUIDED EXECUTION: CONSENT/EXECUTION ENDPOINT
# ----------------------------------------------------------------------

@router.post(
    "/autopilot/consent", 
    response_model=ExecutionResponse, # 🌟 FIXED: Use the correct schema name
    summary="Executes the user-consented Autopilot transfers and logs the audit trail."
)
async def execute_autopilot_consent(
    consent_data: ConsentMoveIn,
    db_session: AsyncSession = Depends(get_db), 
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

    orch_service = OrchestrationService(db_session, user_id) 
    
    # Convert TransferSuggestion list to a list of dictionaries 
    transfer_plan_dicts = [item.model_dump() for item in consent_data.transfer_plan]

    result = await orch_service.record_consent_and_update_balance(
        transfer_plan=transfer_plan_dicts, 
        reporting_period=reporting_period
    )
    
    return result
