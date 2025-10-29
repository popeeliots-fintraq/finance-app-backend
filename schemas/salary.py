# schemas/salary.py (Finalized V2)

from pydantic import BaseModel, Field, condecimal
from datetime import date
from decimal import Decimal
from typing import Optional, Literal 

# Defines precision for all financial fields (up to 10 digits total, 2 decimal places)
FinancialDecimal = condecimal(max_digits=10, decimal_places=2) 

class SalaryAllocationProfileBase(BaseModel):
    """Base schema for the core salary allocation fields (input)."""

    reporting_period: date = Field(..., description="The month/date this allocation profile refers to (e.g., 2025-10-01).")
    net_monthly_income: FinancialDecimal = Field(..., gt=Decimal(0), description="Net Pay / Take-Home Salary.")
    fixed_commitment_total: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="Sum of all fixed, recurring outflows (rent, EMIs, etc.).")
    target_savings_rate: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), le=Decimal(100), description="User's desired percentage for savings/goals.")
    
    # --- V2 EFS INPUT FIELDS (Used by FinancialProfileService) ---
    dependents_count: int = Field(0, ge=0, description="Number of financial dependents (children, elderly) the salary supports.")
    marital_status: Literal["Single", "Married", "Cohabiting"] = Field("Single", description="User's living status, impacting EFS calculation.")


class SalaryAllocationProfileCreate(SalaryAllocationProfileBase):
    """Schema for creating a new profile (what the client sends)."""
    pass

class SalaryAllocationProfileOut(SalaryAllocationProfileBase):
    """
    Schema for returning the complete profile data (the API response).
    Includes all calculated V2 leakage and orchestration fields.
    """

    user_id: int = Field(..., description="The unique identifier of the user.") # Changed to int for typical DB ID
    
    # --- V2 ML OUTPUT FIELDS (Calculated by FinancialProfileService) ---
    equivalent_family_size: Decimal = Field(Decimal(1.00), gt=Decimal(0), max_digits=5, decimal_places=2, description="The calculated Equivalent Family Size (EFS) factor.")
    
    # --- V2 LEAKAGE SERVICE OUTPUT FIELDS ---
    projected_discretionary_float: FinancialDecimal = Field(..., ge=Decimal(0), description="The calculated remaining amount for Variable Essential and Discretionary spend.")
    projected_reclaimable_salary: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="The potential monthly amount recoverable by fixing current leaks (Total Leakage).")
    
    # --- V2 LEAKAGE & ORCHESTRATION FIELDS ---
    tax_headroom_remaining: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="Remaining tax-saving capacity this fiscal year (Salary Maximizer).")
    total_autotransferred: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="Total amount from the reclaimable fund already transferred to goals/tax rules this period (Used by Orchestration).")
    
    variable_spend_total: FinancialDecimal = Field(Decimal(0.00), ge=Decimal(0), description="Total money spent on Variable categories this period.")


    class Config:
        from_attributes = True
