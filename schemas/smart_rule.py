# finance-app-backend/schemas/smart_rule.py

from pydantic import BaseModel, Field, condecimal
from decimal import Decimal
from typing import Optional
from datetime import datetime

# Define precision for all financial fields
FinancialDecimal = condecimal(max_digits=10, decimal_places=2) 


class SmartTransferRuleCreate(BaseModel):
    """Input for creating a new Smart Autopilot Rule."""
    
    # Matching fields from the SmartTransferRule ORM model
    source_fund: str = Field(..., description="Source fund pool (e.g., 'TOTAL_RECLAIMABLE').")
    priority: int = Field(..., ge=1, description="Execution priority (1 is highest, 10 is lowest).")
    destination_goal: str = Field(..., description="Target goal/account (e.g., 'Tax_Goal_80C', 'Stash_Emergency').")
    max_transfer_limit: FinancialDecimal = Field(
        Decimal("0.00"), 
        description="The maximum amount the Autopilot is allowed to transfer for this rule in one execution cycle."
    )
    is_active: bool = Field(True, description="Whether the rule is currently active for orchestration.")

class SmartTransferRuleOut(SmartTransferRuleCreate):
    """Output schema for a Smart Autopilot Rule (from the database)."""
    
    id: int
    user_id: int
    
    # Orchestration Tracking
    total_transferred: FinancialDecimal = Field(Decimal("0.00"), description="Total amount transferred against this rule so far.")
    last_executed_at: Optional[datetime]
    
    class Config:
        from_attributes = True
