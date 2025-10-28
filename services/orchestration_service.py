from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date, datetime
from sqlalchemy.exc import NoResultFound
from fastapi import HTTPException, status

# 🚨 CRITICAL FIX: Import the Scaling Logic for DMB calculation
# NOTE: Assuming this path is correct for your ML engine
from ..ml.scaling_logic import calculate_dynamic_baseline

# Import the models needed
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, SmartTransferRule
# NOTE: Assuming the EFS calculator is accessible here
from ..ml.efs_calculator import calculate_equivalent_family_size


class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    It handles EFS/DMB calculation, manages the reclaimable salary fund,
    and generates goal/stash suggestions based on Smart Rules.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    # ----------------------------------------------------------------------
    # V2 ML LOGIC INTEGRATION (EFS + Dynamic Baseline Calculation)
    # ----------------------------------------------------------------------
    def calculate_and_save_financial_profile(self) -> FinancialProfile:
        """
        Calculates the EFS, then uses the EFS and income to calculate the Dynamic
        Minimal Baseline (DMB) and Leakage Thresholds for Stratified Dependent Scaling.
        This runs as a part of the daily or monthly batch job.
        """

        # 1. Fetch User Data
        user = self.db.query(User).filter(User.id == self.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User ID {self.user_id} not found."
            )

        # 2. Fetch or Create Financial Profile
        profile = (
            self.db.query(FinancialProfile)
            .filter(FinancialProfile.user_id == self.user_id)
            .first()
        )
        if not profile:
            profile = FinancialProfile(user_id=self.user_id)
            self.db.add(profile)
            self.db.flush()

        # 3. Calculate EFS (Required for Stratified Dependent Scaling)
        profile_data = {
            "num_adults": user.num_adults or 0,
            "num_dependents_under_6": user.num_dependents_under_6 or 0,
            "num_dependents_6_to_17": user.num_dependents_6_to_17 or 0,
            "num_dependents_over_18": user.num_dependents_over_18 or 0,
        }
        new_efs_value = calculate_equivalent_family_size(profile_data)

        # 4. Calculate Dynamic Baselines (Leakage Thresholds)
        net_income = user.monthly_salary or Decimal("0.00")

        baseline_results = calculate_dynamic_baseline(
            net_income=net_income,
            equivalent_family_size=new_efs_value,
            city_tier=user.city_tier,
            income_slab=user.income_slab,
            benchmark_efficiency_factor=None,
        )

        # 5. Persist all calculated results to the FinancialProfile
        profile.e_family_size = new_efs_value

        leakage_threshold = baseline_results.get(
            "Total_Leakage_Threshold", Decimal("0.00")
        )
        profile.essential_target = leakage_threshold

        if net_income > Decimal("0.00"):
            profile.baseline_adjustment_factor = (
                leakage_threshold / net_income
            ).quantize(Decimal("0.0001"))
        else:
            profile.baseline_adjustment_factor = Decimal("0.00")

        profile.last_calculated_at = datetime.utcnow()

        self.db.commit()
        return profile

    # ----------------------------------------------------------------------
    # CORE ORCHESTRATION LOGIC (GUIDED EXECUTION)
    # ----------------------------------------------------------------------
    def _fetch_available_reclaimable_salary(
        self, reporting_period: date
    ) -> SalaryAllocationProfile:
        """Fetches the latest calculated salary profile for the period."""

        salary_profile = (
            self.db.query(SalaryAllocationProfile)
            .filter(
                SalaryAllocationProfile.user_id == self.user_id,
                SalaryAllocationProfile.reporting_period == reporting_period,
            )
            .first()
        )

        if not salary_profile:
            return SalaryAllocationProfile(
                projected_reclaimable_salary=Decimal("0.00")
            )

        return salary_profile

    def generate_consent_suggestion_plan(
        self, reporting_period: date
    ) -> Dict[str, Any]:
        """
        Calculates how the reclaimable fund SHOULD be allocated across active Smart Rules
        (Goals/Stashes) to achieve frictionless financial flow.
        """
        salary_profile = self._fetch_available_reclaimable_salary(reporting_period)

        available_fund = salary_profile.projected_reclaimable_salary
        remaining_fund = available_fund
        suggestion_plan: List[Dict[str, Any]] = []
        total_suggested = Decimal("0.00")

        if available_fund <= Decimal("500.00"):
            return {
                "available_fund": available_fund.quantize(Decimal("0.01")),
                "total_suggested": Decimal("0.00"),
                "suggestion_plan": [],
                "message": "Reclaimable salary below action threshold. Autopilot on standby.",
            }

        # 1. Fetch all active Smart Rules
        active_rules = (
            self.db.query(SmartTransferRule)
            .filter(
                SmartTransferRule.user_id == self.user_id,
                SmartTransferRule.is_active == True,
            )
            .order_by(SmartTransferRule.priority.desc())
            .all()
        )

        # 2. Allocate funds
        for rule in active_rules:
            if remaining_fund <= Decimal("0.00"):
                break

            transfer_amount = min(rule.target_amount_monthly, remaining_fund)

            if transfer_amount > Decimal("0.00"):
                suggestion_plan.append(
                    {
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "transfer_amount": transfer_amount.quantize(Decimal("0.01")),
                        "destination": rule.destination_account_name,
                        "type": rule.rule_type,
                    }
                )

                remaining_fund -= transfer_amount
                total_suggested += transfer_amount

        return {
            "available_fund": available_fund.quantize(Decimal("0.01")),
            "remaining_unallocated": remaining_fund.quantize(Decimal("0.01")),
            "total_suggested": total_suggested.quantize(Decimal("0.01")),
            "suggestion_plan": suggestion_plan,
            "message": f"Autopilot suggests reallocating {total_suggested.quantize(Decimal('0.01'))} across active goals/stashes.",
        }

    # NOTE: The method 'record_consent_and_update_balance' would follow here
    # to handle the user's acceptance of the plan and trigger the actual UPI transfers.
