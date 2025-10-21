# schemas/user_profile.py

from pydantic import BaseModel, Field, condecimal
from decimal import Decimal
# 🚨 FIX: Import List and Tuple from typing module
from typing import Optional, List, Tuple

# Use condecimal for precision on the EFS factor
EFSDecimal = condecimal(max_digits=4, decimal_places=2) 

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
    Schema for returning the complete user profile data. 
    Includes the final calculated EFS factor and the structure used for SDS.
    """
    
    user_id: str = Field(..., description="The unique identifier of the user.")
    
    # The calculated output field, used for dynamic baseline adjustment
    equivalent_family_size: EFSDecimal = Field(Decimal("1.00"), ge=Decimal("1.00"), description="The calculated Equivalent Family Size (EFS) factor.")
    
    # The structured input that was derived/calculated for the Stratified Dependent Scaling function.
    dependent_structure: List[Tuple[str, int]] = Field(
        ..., 
        description="Household composition structure derived from input fields for SDS calculation. E.g., [('additional_adult', 1), ('child', 2)]"
    )

    # Configuration to enable mapping from the SQLAlchemy ORM model
    class Config:
        from_attributes = True
