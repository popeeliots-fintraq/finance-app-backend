from pydantic import BaseModel, Field, condecimal
from decimal import Decimal
from typing import List, Literal

# Use condecimal for precise financial values
FinancialDecimal = condecimal(max_digits=12, decimal_places=2)

class LeakageBucket(BaseModel):
    """Schema for a single identified financial 'leak' bucket."""
    
    category: str = Field(..., description="The expense category where leakage was found (e.g., Groceries, Utility).")
    
    # 🚨 CRITICAL ADDITION 1: Stratified Dependent Scaling (SDS) Weight Class
    # Essential categories have a DMB derived from EFS. Discretionary is often zero.
    sds_weight_class: Literal["Variable_Essential", "Fixed_Commitment", "Discretionary"] = Field(
        ...,
        description="The class defining how DMB is calculated (Essential scales with EFS, Discretionary is based on user history)."
    )
    
    baseline: FinancialDecimal = Field(Decimal("0.00"), description="The calculated Dynamic Minimal Baseline (DMB) for this category.")
    spend: FinancialDecimal = Field(Decimal("0.00"), description="The user's actual spending in this category.")
    leak_amount: FinancialDecimal = Field(Decimal("0.00"), description="The calculated leak amount (Spend - Baseline).")
    leak_percentage: str = Field(..., description="The leak amount expressed as a percentage of the baseline (e.g., '25.00%').")


class LeakageOut(BaseModel):
    """
    Schema for the complete Leakage Bucket View, replacing the old expense dashboard.
    This drives the financial recovery projection in Fin-Traq V2. [cite: 2025-10-15]
    """

    total_leakage_amount: FinancialDecimal = Field(Decimal("0.00"), description="The sum of all leak amounts across all categories.")
    
    projected_reclaimable_salary: FinancialDecimal = Field(
        Decimal("0.00"), 
        description="The amount of money recovered from stopping leaks, available for Autopilot allocation (goals/tax savings)."
    )
    
    leakage_buckets: List[LeakageBucket] = Field(
        ..., 
        description="A list of specific spending categories where leakage was detected."
    )
    
    class Config:
        # Allows for returning Decimal objects from the service functions
        from_attributes = True
