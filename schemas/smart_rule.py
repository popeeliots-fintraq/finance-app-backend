# schemas/smart_rule.py

from pydantic import BaseModel, Field, condecimal
from decimal import Decimal
from typing import Optional
# Import the Enum defined in the ORM file
from ..db.smart_transfer_rule import RuleActionType 

# Condecimal for percentage precision
PercentDecimal = condecimal(max_digits=5, decimal_places=2) 

class SmartTransferRuleBase(BaseModel):
    """Base schema for Smart Rule data (used for both Create and Update)."""
    
    rule_name: str = Field(..., max_length=255, description="A descriptive name for the rule (e.g., 'Vacation Goal Automation').")
    action_type: RuleActionType = Field(..., description="The type of financial goal this rule is targeting (Goal, Tax Saving, Debt Payment).")
    
    # Allocation Logic
    allocation_percentage: PercentDecimal = Field(Decimal("100.00"), ge=Decimal("0.00"), le=Decimal("100.00"), description="Percentage of recovered income to allocate to this rule.")
    
    # Destination Account (Shadow Account ID in Fin-Traq's internal ledger)
    destination_target_id: str = Field(..., max_length=255, description="Internal ID of the goal/tax bucket where money is symbolically 'moved'.")
    
    # Execution
    is_active: Optional[bool] = Field(True, description="Whether the rule is currently active.")
    execute_on_day: Optional[int] = Field(1, ge=1, le=28, description="Day of the month to execute the shadow transfer (e.g., 5th of the month).")

class SmartTransferRuleCreate(SmartTransferRuleBase):
    """Schema for creating a new rule."""
    pass

class SmartTransferRuleUpdate(SmartTransferRuleBase):
    """Schema for updating an existing rule (all fields optional for patching)."""
    # Override fields to be optional for update logic
    rule_name: Optional[str] = None
    action_type: Optional[RuleActionType] = None
    allocation_percentage: Optional[PercentDecimal] = None
    destination_target_id: Optional[str] = None
    execute_on_day: Optional[int] = None

class SmartTransferRuleOut(SmartTransferRuleBase):
    """
    Schema for returning the complete rule data from the API. 
    Includes the database-generated ID.
    """
    rule_id: int = Field(..., description="The unique database ID of the smart rule.")
    user_id: str = Field(..., description="The user who owns this rule.")
    
    class Config:
        from_attributes = True
