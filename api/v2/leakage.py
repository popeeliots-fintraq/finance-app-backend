# api/v2/leakage.py (FINAL, FIXED)

from fastapi import APIRouter, Depends, HTTPException, status, Query # <-- Added HTTPException & Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from datetime import date # <-- Added date import

# Import dependencies
from ...dependencies import get_db, get_current_user_id

# Import services
from ...services.financial_profile_service import FinancialProfileService
from ...services.leakage_service import LeakageService

# Import schemas for request/response bodies
from ...schemas.user_profile import UserProfileCreate, UserProfileOut
from ...schemas.financial_profile import FinancialProfileResponse
from ...schemas.leakage_data import LeakageOut

router = APIRouter(
    prefix="/leakage",
    tags=["Leakage & ML (EFS/DMB)"],
)

# ----------------------------------------------------------------------
# ENDPOINT 1: INITIALIZE / UPDATE EFS & DMB (The ML Engine Trigger)
# ----------------------------------------------------------------------
@router.post(
# ... (rest of the file remains the same)
