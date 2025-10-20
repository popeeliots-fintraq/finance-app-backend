# schemas/user_profile.py

from pydantic import BaseModel, Field, condecimal
from decimal import Decimal
from typing import Optional

# Use condecimal for precision on the EFS factor
EFSDecimal = condecimal(max_digits=4, decimal_places=2) 

class UserProfileBase(BaseModel):
    """Base schema for User Profile data (inputs for EFS calculation)."""
    
    # 1. Family Structure Input
    num_adults: int = Field(1, ge=1, description="Number of adults in the household (user + partner/spouse). Minimum 1.") 
    
    # 2. Age Brackets for Weighted Scaling (Inputs for EFS calculation)
    num_dependents_under_6: int = Field(0, ge=0, description="Number of dependents under 6 years old.")
    num_dependents_6_to_17: int = Field(0, ge=0, description="Number of dependents between 6 and 17 years old.")
    num_dependents_over_18: int = Field(0, ge=0, description="Number of dependents 18 years and older.")

    # Note: total number of children is redundant here but could be calculated
    
class UserProfileCreate(UserProfileBase):
    """Schema for creating a new user profile/EFS data (what the client sends)."""
    pass

class UserProfileOut(UserProfileBase):
    """
    Schema for returning the complete user profile data. 
    Includes the final calculated EFS factor.
    """
    
    user_id: str = Field(..., description="The unique identifier of the user.")
    
    # The calculated output field, used for dynamic baseline adjustment
    equivalent_family_size: EFSDecimal = Field(Decimal("1.00"), ge=Decimal("1.00"), description="The calculated Equivalent Family Size (EFS) factor.")
    
    # Configuration to enable mapping from the SQLAlchemy ORM model
    class Config:
        from_attributes = True
