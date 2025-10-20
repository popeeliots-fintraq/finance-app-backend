# api/v1/salary.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from typing import Annotated

from ...schemas.salary import SalaryAllocationProfileCreate, SalaryAllocationProfileOut
from ...db.database import get_db
from ...db.models import SalaryAllocationProfile

router = APIRouter(
    prefix="/salary",
    tags=["Salary Allocation"]
)

DBDependency = Annotated[Session, Depends(get_db)]

@router.post(
    "/allocation", 
    response_model=SalaryAllocationProfileOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create or Update Salary Allocation Profile for a Period"
)
def create_salary_allocation_profile(
    profile_data: SalaryAllocationProfileCreate, 
    db: DBDependency,
    user_id: str = Depends(lambda: "user_popeelots_123") 
):
    """
    Executes the initial Fin-Traq V2 Autopilot calculation and saves the profile.
    """

    # CORE FIN-TRAQ V2 SALARY AUTOPILOT LOGIC

    income_after_fixed = profile_data.net_monthly_income - profile_data.fixed_commitment_total
    target_savings_amount = profile_data.net_monthly_income * (profile_data.target_savings_rate / Decimal(100))

    projected_discretionary_float = income_after_fixed - target_savings_amount
    projected_reclaimable_salary = Decimal("0.00") # Initial value, to be updated by AI/ML

    if projected_discretionary_float < Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fixed commitments and target savings exceed net income."
        )

    # DATABASE INTERACTION
    db_profile = SalaryAllocationProfile(
        user_id=user_id,
        reporting_period=profile_data.reporting_period,
        net_monthly_income=profile_data.net_monthly_income,
        fixed_commitment_total=profile_data.fixed_commitment_total,
        target_savings_rate=profile_data.target_savings_rate,
        projected_discretionary_float=projected_discretionary_float,
        projected_reclaimable_salary=projected_reclaimable_salary
    )

    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)

    return db_profile
