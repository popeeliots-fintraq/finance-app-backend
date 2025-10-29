from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional, List, Tuple
from datetime import datetime

# NOTE: The EFSDecimal condecimal alias is removed for simplicity, using Decimal directly.

class UserProfileBase(BaseModel):
    """Base schema for User Profile data (inputs for EFS calculation)."""
    
    # 1. Family Structure Input
    num_adults: int = Field(1, ge=1, description="Number of adults in the household (user + partner/spouse). Minimum 1.") 
    
    # 2. Age Brackets for Weighted Scaling (Inputs for EFS calculation)
    num_dependents_under_6: int = Field(0, ge=0, description="Number of dependents under 6 years old (infant/child weight).")
    num_dependents_6_to_17: int = Field(0, ge=0, description="Number of dependents between 6 and 17 years old (child weight).")
    num_dependents_over_18: int = Field(0, ge=0, description="Number of dependents 18 years and older (additional adult/elderly weight).")

class UserProfileCreate(UserProfileBase):
    """Schema for creating a new user profile/EFS data (what the client sends)."""
    pass

class UserProfileOut(UserProfileBase):
    """
    Schema for returning the complete user financial profile data (Fin-Traq V2). 
    Includes EFS, BEF, and the Dynamic Minimal Baseline (DMB) derived from them.
    """
    
    user_id: int = Field(..., description="The unique identifier of the user.") # Changed to int for typical DB ID
    
    # --- V2 ML Outputs (Calculated & Persisted by OrchestrationService) ---
    equivalent_family_size: Decimal = Field(Decimal("1.00"), ge=Decimal("1.00"), max_digits=5, decimal_places=2, description="The calculated Equivalent Family Size (EFS) factor for Stratified Dependent Scaling.")
    
    benchmark_efficiency_factor: Decimal = Field(Decimal("1.00"), max_digits=5, decimal_places=4, description="The calculated Benchmarking Efficiency Factor (BEF) used to adjust the DMB based on peer comparison.")
    
    essential_target: Decimal = Field(Decimal("0.00"), ge=Decimal("0.00"), max_digits=12, decimal_places=2, description="The total calculated Dynamic Minimal Baseline (DMB) for variable essential spends (the Leakage Threshold).")
    
    baseline_adjustment_factor: Decimal = Field(Decimal("0.00"), max_digits=5, decimal_places=4, description="Ratio of DMB to Net Income, showing the relative tightness of the baseline.")

    last_calculated_at: Optional[datetime] = Field(None, description="Timestamp of the last EFS/DMB calculation.")

    # --- Structural Data (Optional for direct API use) ---
    dependent_structure: List[Tuple[str, int]] = Field(
        [], 
        description="Household composition structure derived from input fields for SDS calculation."
    )

    # Configuration to enable mapping from the SQLAlchemy ORM model
    class Config:
        from_attributes = True
