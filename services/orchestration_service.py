# services/orchestration_service.py

from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date, datetime 
from sqlalchemy.exc import NoResultFound
from fastapi import HTTPException, status 

# 🚨 CRITICAL FIX: Import the Scaling Logic for DMB calculation
from ..ml.scaling_logic import calculate_dynamic_baseline

# Import the models needed
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, SmartTransferRule 
from ..ml.efs_calculator import calculate_equivalent_family_size


class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    ...
    """

    def __init__(self, db: Session, user_id: int):
        # NOTE: user_id is passed as int, assuming it matches the User.id model
        self.db = db
        self.user_id = user_id
        
    # ----------------------------------------------------------------------
    # V2 ML LOGIC INTEGRATION (EFS + Dynamic Baseline Calculation)
    # ----------------------------------------------------------------------
    def calculate_and_save_financial_profile(self) -> FinancialProfile: # <--- RENAMED AND UPDATED METHOD
        """
        Calculates the EFS, then uses the EFS and income to calculate the Dynamic 
        Minimal Baseline (DMB) and Leakage Thresholds for Stratified Dependent Scaling.
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

        # 3. Calculate EFS (Required for Stratified Dependent Scaling)
        profile_data = {
            'num_adults': user.num_adults,
            'num_dependents_under_6': user.num_dependents_under_6,
            'num_dependents_6_to_17': user.num_dependents_6_to_17,
            'num_dependents_over_18': user.num_dependents_over_18,
        }
        new_efs_value = calculate_equivalent_family_size(profile_data)
        
        # 4. Calculate Dynamic Baselines (Leakage Thresholds)
        # We use user.monthly_salary (Net Income) and the calculated EFS
        net_income = user.monthly_salary 
        
        baseline_results = calculate_dynamic_baseline(
            net_income=net_income,
            equivalent_family_size=new_efs_value
        )

        # 5. Persist all calculated results to the FinancialProfile
        profile.e_family_size = new_efs_value
        
        # FinancialProfile.essential_target stores the Total_Leakage_Threshold for V2
        leakage_threshold = baseline_results.get("Total_Leakage_Threshold", Decimal("0.00"))
        profile.essential_target = leakage_threshold
        
        # Calculate the final adjustment factor (Total Leakage Threshold / Net Income)
        if net_income and net_income > Decimal("0.00"):
            profile.baseline_adjustment_factor = leakage_threshold / net_income
        else:
            profile.baseline_adjustment_factor = Decimal("0.00")

        profile.last_calculated_at = datetime.utcnow()
        
        self.db.commit()
        return profile

    # ----------------------------------------------------------------------
    # HELPER AND CORE ORCHESTRATION LOGIC (REMAINING EXISTING METHODS)
    # ----------------------------------------------------------------------
    
    # NOTE: The rest of the methods (_fetch_available_reclaimable_salary, 
    # generate_consent_suggestion_plan, and record_consent_and_update_balance)
    # are assumed to be correct based on the previous interaction and remain unchanged.

    def _fetch_available_reclaimable_salary(self, reporting_period: date) -> SalaryAllocationProfile:
        """Fetches the latest calculated salary profile for the period."""
        
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        if not salary_profile:
            raise NoResultFound("Salary Allocation Profile not found for the period.")
            
        return salary_profile


    def generate_consent_suggestion_plan(self, reporting_period: date) -> Dict[str, Any]:
        """
        Calculates how the reclaimable fund SHOULD be allocated across active Smart Rules.
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

        available_fund = salary_profile.projected_reclaimable_salary 
        
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
