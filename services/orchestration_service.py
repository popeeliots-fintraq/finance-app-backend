# services/orchestration_service.py

from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date, datetime # <--- Added datetime for profile timestamp
from sqlalchemy.exc import NoResultFound
from fastapi import HTTPException, status # <--- Added status import

# 🚨 FIX: Import the models needed for EFS calculation
from ..db.base import User, FinancialProfile
# Import other models (adjust path if needed)
from ..db.models import SalaryAllocationProfile, SmartTransferRule 
# 🚨 FIX: Import EFS Calculator
from ..ml.efs_calculator import calculate_equivalent_family_size


class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    Calculates a CONSENT SUGGESTION PLAN based on available reclaimable 
    salary and user-defined Smart Rules (Goals, Tax Savings) [cite: 2025-10-15].
    """

    def __init__(self, db: Session, user_id: int): # <--- Changed user_id to int for SQLAlchemy
        self.db = db
        self.user_id = user_id
        
    # ----------------------------------------------------------------------
    # V2 ML LOGIC INTEGRATION (EFS Calculation)
    # ----------------------------------------------------------------------
    def calculate_and_save_efs(self) -> FinancialProfile:
        """
        Calculates the Equivalent Family Size (EFS) and updates the user's 
        FinancialProfile. This MUST run before leakage calculation.
        """
        
        # 1. Fetch User Data
        user = self.db.query(User).filter(User.id == self.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User ID {self.user_id} not found."
            )
            
        # 2. Fetch or Create Financial Profile
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()
        if not profile:
            profile = FinancialProfile(user_id=self.user_id)
            self.db.add(profile)
            self.db.flush() 

        # 3. Prepare Input Data for EFS Calculator
        profile_data = {
            'num_adults': user.num_adults,
            'num_dependents_under_6': user.num_dependents_under_6,
            'num_dependents_6_to_17': user.num_dependents_6_to_17,
            'num_dependents_over_18': user.num_dependents_over_18,
        }

        # 4. Calculate EFS and Update Profile
        new_efs_value = calculate_equivalent_family_size(profile_data)
        
        profile.e_family_size = new_efs_value
        profile.last_calculated_at = datetime.utcnow()
        
        # NOTE: baseline_adjustment_factor update will be added here next
        
        self.db.commit()
        return profile

    # ----------------------------------------------------------------------
    # HELPER AND CORE ORCHESTRATION LOGIC (EXISTING METHODS)
    # ----------------------------------------------------------------------
    
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
        # ... (Existing code remains the same)
        """
        Calculates how the reclaimable fund SHOULD be allocated 
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
            "suggestion_plan": suggestion_plan, 
            "message": "Consent suggestion plan generated based on Smart Rules and reclaimable salary."
        }


    def record_consent_and_update_balance(self, consented_amount: Decimal, reporting_period: date) -> Dict[str, Any]:
        # ... (Existing code remains the same)
        """
        Records the user's consent to 'move' the fund internally for display purposes.
        """
        try:
            profile = self._fetch_available_reclaimable_salary(reporting_period)
        except NoResultFound:
            # Re-raise as HTTPException for the API router to catch and return 404
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
