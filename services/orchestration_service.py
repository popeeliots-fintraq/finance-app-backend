# services/orchestration_service.py

from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date
from sqlalchemy.exc import NoResultFound

# Import models
# NOTE: Assumes you will update SalaryAllocationProfile model with 'consented_move_amount'
from ..db.models import SalaryAllocationProfile, SmartTransferRule 

class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    Calculates a CONSENT SUGGESTION PLAN based on available reclaimable 
    salary and user-defined Smart Rules (Goals, Tax Savings) [cite: 2025-10-15].
    """

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        
    def _fetch_available_reclaimable_salary(self, reporting_period: date) -> SalaryAllocationProfile:
        """Fetches the latest calculated salary profile for the period."""
        
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        if not salary_profile:
            # Raise an error if the required profile is missing
            raise NoResultFound("Salary Allocation Profile not found for the period.")
            
        return salary_profile


    def generate_consent_suggestion_plan(self, reporting_period: date) -> Dict[str, Any]:
        """
        🚨 RENAMED/UPDATED: Calculates how the reclaimable fund SHOULD be allocated 
        across active Smart Rules, generating a suggestion plan (not a transfer plan).
        """
        try:
            salary_profile = self._fetch_available_reclaimable_salary(reporting_period)
        except NoResultFound:
             return {
                "available_fund": Decimal("0.00"),
                "total_suggested": Decimal("0.00"),
                "suggestion_plan": [],
                "message": "No reclaimable salary projected. Autopilot is on standby."
            }

        # Use the money recovered from leakage calculation (projected_reclaimable_salary)
        available_fund = salary_profile.projected_reclaimable_salary 
        
        # If no reclaimable salary is projected, the plan is empty.
        if available_fund <= Decimal("0.00"):
             return {
                "available_fund": Decimal("0.00"),
                "total_suggested": Decimal("0.00"),
                "suggestion_plan": [],
                "message": "No reclaimable salary projected. Autopilot is on standby."
            }

        # 1. Fetch all active Smart Rules for the user
        active_rules = self.db.query(SmartTransferRule).filter(
            SmartTransferRule.user_id == self.user_id,
            SmartTransferRule.is_active == True
        ).all()
        
        suggestion_plan: List[Dict[str, Any]] = []
        remaining_fund = available_fund
        total_suggested = Decimal("0.00")

        # 2. Allocate funds based on rules to form the SUGGESTION
        for rule in active_rules:
            if remaining_fund <= Decimal("0.00"):
                break # Funds exhausted

            amount_to_suggest = min(remaining_fund, rule.transfer_amount)
            
            # The suggestion shows where the recovered income COULD go (goals/tax savings)
            suggestion_plan.append({
                "rule_id": rule.rule_id,
                "destination": rule.destination_instrument,
                "amount_suggested": amount_to_suggest.quantize(Decimal("0.01")),
                "type": rule.transfer_type
            })
            
            remaining_fund -= amount_to_suggest
            total_suggested += amount_to_suggest

        # 3. Finalize Plan
        return {
            "available_fund": available_fund.quantize(Decimal("0.01")),
            "total_suggested": total_suggested.quantize(Decimal("0.01")),
            "unallocated_fund": remaining_fund.quantize(Decimal("0.01")),
            "suggestion_plan": suggestion_plan, # 🚨 RENAMED
            "message": "Consent suggestion plan generated based on Smart Rules and reclaimable salary."
        }

    # ----------------------------------------------------------------------
    # 🚨 NEW: CONSENT MOVE EXECUTION LOGIC 
    # ----------------------------------------------------------------------

    def record_consent_and_update_balance(self, consented_amount: Decimal, reporting_period: date) -> Dict[str, Any]:
        """
        Records the user's consent to 'move' the fund internally for display purposes,
        allowing the app to display (Total - Movable Money) once consented.
        
        NOTE: This requires the SalaryAllocationProfile model to have 
              'consented_move_amount' and 'net_monthly_income'.
        """
        try:
            profile = self._fetch_available_reclaimable_salary(reporting_period)
        except NoResultFound:
            raise HTTPException(
                status_code=404, 
                detail=f"Cannot record consent: Profile not found for period {reporting_period.isoformat()}"
            )
        
        # 1. Validation: Ensure the user is not consenting to move more than available
        if consented_amount > profile.projected_reclaimable_salary:
            raise HTTPException(
                status_code=400,
                detail="Consented amount exceeds the projected reclaimable salary."
            )

        # 2. Update the balance tracking fields
        # Add the consented amount to the total consented balance
        profile.consented_move_amount += consented_amount 
        
        # Deduct from the fund available for future suggestions
        profile.projected_reclaimable_salary -= consented_amount 
        
        self.db.commit()
        
        # 3. Calculate and return the new effective balances for display
        new_effective_salary = profile.net_monthly_income - profile.consented_move_amount
        
        return {
            "consented_amount_added": consented_amount.quantize(Decimal("0.01")),
            "total_consented_move": profile.consented_move_amount.quantize(Decimal("0.01")),
            "new_effective_salary_display": new_effective_salary.quantize(Decimal("0.01")),
            "message": "Consent recorded. Display balance updated to reflect internal move to goals/savings."
        }
