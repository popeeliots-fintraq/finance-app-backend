# api/v1/user_profile.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated

# Import components from our new structure
from ...schemas.user_profile import UserProfileCreate, UserProfileOut
from ...db.database import get_db
from ...db.user_profile import UserProfile
# FIX: Corrected import path to ml_service.py where the function was placed
from ...services.ml_service import calculate_equivalent_family_size 

# Initialize the FastAPI Router
router = APIRouter(
    prefix="/profile",
    tags=["User Profile & EFS"]
)

# Define the database dependency type for convenience
DBDependency = Annotated[Session, Depends(get_db)]

@router.post(
    "/efs", 
    response_model=UserProfileOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create or Update User Profile and Calculate Equivalent Family Size (EFS)"
)
def create_or_update_user_profile(
    profile_data: UserProfileCreate, 
    db: DBDependency,
    # 🚨 NOTE: 'user_id' must be injected here from an authentication system (placeholder for now)
    user_id: str = Depends(lambda: "user_popeelots_123") 
):
    """
    Takes dependent and household data, calculates the Equivalent Family Size (EFS) factor, 
    and saves the profile. The EFS is used for dynamic baseline adjustment in Fin-Traq V2 ML logic.
    """
    
    # ----------------------------------------------------
    # EFS CALCULATION LOGIC INTEGRATION
    # ----------------------------------------------------
    
    # 1. Convert Pydantic data to a dictionary for the calculation function
    profile_dict = profile_data.model_dump() 
    
    # 2. Calculate the EFS factor
    # The calculate_equivalent_family_size function expects individual keyword arguments,
    # so we must pass them explicitly from the profile_data object.
    equivalent_family_size = calculate_equivalent_family_size(
        num_adults=profile_data.num_adults,
        num_children_under_6=profile_data.num_dependents_under_6,
        num_children_6_to_17=profile_data.num_dependents_6_to_17,
        num_dependents_over_18=profile_data.num_dependents_over_18
    )
    
    # ----------------------------------------------------
    # DATABASE INTERACTION: Check if profile exists (Update or Create)
    # ----------------------------------------------------

    # Check for existing profile
    db_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    
    if db_profile:
        # UPDATE existing profile
        for key, value in profile_dict.items():
            setattr(db_profile, key, value)
        
        # Update the calculated EFS field
        db_profile.equivalent_family_size = equivalent_family_size
        
    else:
        # CREATE new profile
        db_profile = UserProfile(
            user_id=user_id,
            equivalent_family_size=equivalent_family_size,
            **profile_dict
        )

        db.add(db_profile)

    # Save changes to database
    db.commit()
    db.refresh(db_profile)

    # Return the saved profile
    return db_profile
