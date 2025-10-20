# schemas/salary.py

from pydantic import BaseModel, Field, condecimal
from datetime import date
from decimal import Decimal
from typing import Optional

FinancialDecimal = condecimal(max_digits=10, decimal_places=2) 

class SalaryAllocationProfileBase(BaseModel):
    """Base schema for the core salary allocation fields (input)."""

    reporting_period: date = Field(..., description="The month/date this allocation profile refers to (e.g., 2025-10-01).")
    net_monthly_income: FinancialDecimal = Field(..., gt=Decimal(0), description="Net Pay / Take-Home Salary.")
    fixed_commitment_total: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="Sum of all fixed, recurring outflows.")
    target_savings_rate: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), le=Decimal(100), description="User's desired percentage for savings/goals.")

class SalaryAllocationProfileCreate(SalaryAllocationProfileBase):
    """Schema for creating a new profile (what the client sends)."""
    pass

class SalaryAllocationProfileOut(SalaryAllocationProfileBase):
    """Schema for returning the complete profile data (the API response)."""

    user_id: str = Field(..., description="The unique identifier of the user.")
    projected_discretionary_float: FinancialDecimal = Field(..., ge=Decimal(0), description="The calculated remaining amount for Variable Essential and Discretionary spend.")
    projected_reclaimable_salary: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="The potential monthly amount recoverable by fixing current leaks.")

    class Config:
        from_attributes = True
