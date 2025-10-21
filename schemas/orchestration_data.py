# finance-app-backend/schemas/orchestration_data.py

from pydantic import BaseModel, Field, condecimal
from decimal import Decimal
from typing import List, Optional
from datetime import date

# Use condecimal for precise financial values
FinancialDecimal = condecimal(max_digits=12, decimal_places=2)


# --- 1. Output Schema for /autopilot-plan (Suggestion) ---

class SuggestedAllocation(BaseModel):
    """Details of a single suggested allocation based on a Smart Rule."""
    
    rule_id: str = Field(..., description="The ID of the Smart Rule (Goal, Tax Saving).")
    destination: str = Field(..., description="The target destination (e.g., Goal 'Vacation Fund', Tax Instrument 'ELSS').")
    amount_suggested: FinancialDecimal = Field(Decimal("0.00"), description="The amount suggested to allocate to this destination.")
    type: str = Field(..., description="The type of transfer (e.g., 'Goal', 'Tax Saving').")


class ConsentPlanOut(BaseModel):
    """
    Schema for the Consent Suggestion Plan. This is a READ-ONLY view of 
    how reclaimable money SHOULD be spent, awaiting user consent.
    """
    available_fund: FinancialDecimal = Field(Decimal("0.00"), description="Total reclaimable salary available for suggestion.")
    total_suggested: FinancialDecimal = Field(Decimal("0.00"), description="Total amount allocated across all Smart Rules.")
    unallocated_fund: FinancialDecimal = Field(Decimal("0.00"), description="Leftover fund after rules are satisfied.")
    suggestion_plan: List[SuggestedAllocation] = Field(..., description="The suggested allocation plan for the available fund.")
    message: str = Field(..., description="A status message for the generated plan.")


# --- 2. Input Schema for /autopilot-consent (Consent Action) ---

class ConsentMoveIn(BaseModel):
    """
    Input schema for the user consenting to move funds.
    """
    # The amount the user is explicitly consenting to move (usually total_suggested)
    consented_amount: FinancialDecimal = Field(..., gt=Decimal("0.00"), description="The specific amount the user consents to internally 'move'.")
    # Needs the reporting period to target the correct salary profile
    reporting_period: str = Field(..., description="The month/period the consent applies to (YYYY-MM-DD).")
    
    # Optional: could include which rules were consented to if partial consent is allowed
    rules_consented_to: Optional[List[str]] = Field(None, description="List of rule IDs the user consented to (optional).")


# --- 3. Output Schema for /autopilot-consent (Consent Result) ---

class ConsentMoveOut(BaseModel):
    """
    Output schema after the consent has been successfully recorded, showing the new effective balances.
    """
    consented_amount_added: FinancialDecimal = Field(Decimal("0.00"), description="The amount added in this specific transaction.")
    total_consented_move: FinancialDecimal = Field(Decimal("0.00"), description="The cumulative total of funds the user has consented to move internally.")
    new_effective_salary_display: FinancialDecimal = Field(Decimal("0.00"), description="The user's Net Income minus total_consented_move, used for front-end display.")
    message: str = Field(..., description="Confirmation message for the successful consent and balance update.")
