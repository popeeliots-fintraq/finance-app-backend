# api/v2/leakage.py (FIXED)

from fastapi import APIRouter, Depends, HTTPException, status, Query # <-- ADDED HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from datetime import date

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
# ... (rest of the file remains the same)
