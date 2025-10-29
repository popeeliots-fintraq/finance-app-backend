from pydantic import BaseModel, Field, condecimal
from datetime import date
from decimal import Decimal
from typing import Optional, Literal # Added Literal for clear type hinting

FinancialDecimal = condecimal(max_digits=10, decimal_places=2) 

class SalaryAllocationProfileBase(BaseModel):
    """Base schema for the core salary allocation fields (input)."""

    reporting_period: date = Field(..., description="The month/date this allocation profile refers to (e.g., 2025-10-01).")
    net_monthly_income: FinancialDecimal = Field(..., gt=Decimal(0), description="Net Pay / Take-Home Salary.")
    fixed_commitment_total: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="Sum of all fixed, recurring outflows.")
    target_savings_rate: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), le=Decimal(100), description="User's desired percentage for savings/goals.")
    
    # 🚨 CRITICAL ADDITION 1: Input for EFS Calculation
    # This data is necessary for the DMB engine.
    dependents_count: int = Field(0, ge=0, description="Number of financial dependents (children, elderly) the salary supports.")
    marital_status: Literal["Single", "Married", "Cohabiting"] = Field("Single", description="User's living status, impacting EFS calculation.")


class SalaryAllocationProfileCreate(SalaryAllocationProfileBase):
    """Schema for creating a new profile (what the client sends)."""
    pass

class SalaryAllocationProfileOut(SalaryAllocationProfileBase):
    """Schema for returning the complete profile data (the API response)."""

    user_id: str = Field(..., description="The unique identifier of the user.")
    
    # 🚨 CRITICAL ADDITION 2: The calculated EFS value
    equivalent_family_size: FinancialDecimal = Field(Decimal(1.00), gt=Decimal(0), description="The calculated Equivalent Family Size, used to dynamically scale the DMB.")
    
    # The projected float now depends on the calculated DMB (scaled by EFS)
    projected_discretionary_float: FinancialDecimal = Field(..., ge=Decimal(0), description="The calculated remaining amount for Variable Essential and Discretionary spend.")
    projected_reclaimable_salary: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="The potential monthly amount recoverable by fixing current leaks (Total Leakage).")

    class Config:
        from_attributes = True
