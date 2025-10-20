# api/v1/leakage.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated, Dict, Any, List
from pydantic import BaseModel, Field
from decimal import Decimal

# Import necessary components
from ...db.database import get_db
from ...services.leakage_service import LeakageService

# ----------------------------------------------------------------------
# 1. Define Response Schema for Leakage (since it's a dynamic structure)
# ----------------------------------------------------------------------

class LeakageBucket(BaseModel):
    """Schema for a single overspent category ('Leakage Bucket')."""
    category: str
    baseline: Decimal
    spend: Decimal
    leak_amount: Decimal
    leak_percentage: str

class LeakageReportOut(BaseModel):
    """
    Schema for the final Leakage Bucket View report. [cite: 2025-10-15]
    This replaces the old expense dashboard.
    """
    total_leakage_amount: Decimal = Field(..., description="The total calculated monthly salary leak.")
    projected_reclaimable_salary: Decimal = Field(..., description="If leak fixed → New Salary Engine result (in this MVP, equals total_leakage). [cite: 2025-10-15]")
    leakage_buckets: List[LeakageBucket] = Field(..., description="Detailed list of categories showing spending above the dynamic baseline.")


# ----------------------------------------------------------------------
# 2. Define the API Router
# ----------------------------------------------------------------------

router = APIRouter(
    prefix="/leakage",
    tags=["Leak Finder (V2)"]
)

# Define the database dependency type for convenience
DBDependency = Annotated[Session, Depends(get_db)]

@router.get(
    "/report", 
    response_model=LeakageReportOut, 
    status_code=status.HTTP_200_OK,
    summary="Get the Leakage Bucket View and Projected Reclaimable Salary"
)
def get_leakage_report(
    db: DBDependency,
    # Placeholder for user_id - replace with actual auth dependency later
    user_id: str = Depends(lambda: "user_popeelots_123") 
):
    """
    Calculates the current salary leakage based on the dynamic minimal baseline 
    (EFS and ML Logic) and returns the Leakage Bucket View.
    """
    
    try:
        # Initialize and call the core service
        leakage_service = LeakageService(db, user_id)
        report_data = leakage_service.calculate_leakage()
        
        # The service returns a dict, which Pydantic converts to LeakageReportOut
        return report_data
        
    except ValueError as e:
        # Handle cases where necessary profile data is missing
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        # General error handling
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during leakage calculation: {e}"
        )
