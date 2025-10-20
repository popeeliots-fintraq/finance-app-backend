# api/v1/smart_rule.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Annotated, List, Optional

# Import components from our new structure
from ...schemas.smart_rule import SmartTransferRuleCreate, SmartTransferRuleUpdate, SmartTransferRuleOut
from ...db.database import get_db
from ...db.smart_transfer_rule import SmartTransferRule 

# Initialize the FastAPI Router
router = APIRouter(
    prefix="/smart-rules",
    tags=["Guided Orchestration (Phase 2)"]
)

# Define the database dependency type for convenience
DBDependency = Annotated[Session, Depends(get_db)]

# Placeholder for user_id dependency (will be replaced by actual authentication)
def get_user_id() -> str:
    return "user_popeelots_123"

# --- CREATE Rule ---
@router.post(
    "/", 
    response_model=SmartTransferRuleOut, 
    status_code=status.HTTP_201_CREATED,
    summary="Create a new automatic transfer rule"
)
def create_smart_rule(
    rule_data: SmartTransferRuleCreate, 
    db: DBDependency,
    user_id: str = Depends(get_user_id) 
):
    try:
        db_rule = SmartTransferRule(
            user_id=user_id,
            **rule_data.model_dump()
        )

        db.add(db_rule)
        db.commit()
        db.refresh(db_rule)

        return db_rule
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A rule with this name already exists for the user."
        )

# --- READ All Rules ---
@router.get(
    "/", 
    response_model=List[SmartTransferRuleOut], 
    summary="Get all active and inactive rules for the user"
)
def get_all_smart_rules(
    db: DBDependency,
    user_id: str = Depends(get_user_id)
):
    rules = db.query(SmartTransferRule).filter(SmartTransferRule.user_id == user_id).all()
    return rules

# --- READ Single Rule ---
@router.get(
    "/{rule_id}", 
    response_model=SmartTransferRuleOut, 
    summary="Get a specific rule by ID"
)
def get_smart_rule(
    rule_id: int, 
    db: DBDependency,
    user_id: str = Depends(get_user_id)
):
    rule = db.query(SmartTransferRule).filter(
        SmartTransferRule.rule_id == rule_id,
        SmartTransferRule.user_id == user_id
    ).first()
    
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Smart rule not found.")
    
    return rule

# --- UPDATE Rule ---
@router.patch(
    "/{rule_id}", 
    response_model=SmartTransferRuleOut, 
    summary="Update an existing rule (e.g., change allocation or activate/deactivate)"
)
def update_smart_rule(
    rule_id: int,
    rule_data: SmartTransferRuleUpdate, 
    db: DBDependency,
    user_id: str = Depends(get_user_id)
):
    db_rule = db.query(SmartTransferRule).filter(
        SmartTransferRule.rule_id == rule_id,
        SmartTransferRule.user_id == user_id
    ).first()

    if not db_rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Smart rule not found.")

    # Update only the fields provided in the request body
    update_data = rule_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_rule, key, value)
        
    db.commit()
    db.refresh(db_rule)
    return db_rule

# --- DELETE Rule ---
@router.delete(
    "/{rule_id}", 
    status_code=status.HTTP_204_NO_CONTENT, 
    summary="Delete a smart transfer rule"
)
def delete_smart_rule(
    rule_id: int, 
    db: DBDependency,
    user_id: str = Depends(get_user_id)
):
    db_rule = db.query(SmartTransferRule).filter(
        SmartTransferRule.rule_id == rule_id,
        SmartTransferRule.user_id == user_id
    ).first()

    if not db_rule:
        # Return 204 even if not found, to be idempotent (it's gone either way)
        return

    db.delete(db_rule)
    db.commit()
    return
