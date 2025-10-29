# services/orchestration_service.py

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date, datetime
from sqlalchemy.exc import NoResultFound
from fastapi import HTTPException, status
from sqlalchemy import func

# 🚨 CRITICAL FIX: Import the Scaling Logic for DMB calculation
from ..ml.scaling_logic import calculate_dynamic_baseline

# New Import for Leakage Service (Required for real-time orchestration)
from .leakage_service import LeakageService 

# New Import for Benchmarking Service (Required for DMB calculation)
from .benchmarking_service import BenchmarkingService # <--- ADDED

# Import the models needed
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, SmartTransferRule, Transaction
from ..db.enums import TransactionType, RuleType # Assuming RuleType is an enum in db.enums
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
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()
        if not profile:
            profile = FinancialProfile(user_id=self.user_id)
            self.db.add(profile)
            self.db.flush()

        # 3. Calculate EFS
        profile_data = {
            'num_adults': user.num_adults or 0,
            'num_dependents_under_6': user.num_dependents_under_6 or 0,
            'num_dependents_6_to_17': user.num_dependents_6_to_17 or 0,
            'num_dependents_over_18': user.num_dependents_over_18 or 0,
        }
        new_efs_value = calculate_equivalent_family_size(profile_data)

        # 4. Calculate Dynamic Baselines (Leakage Thresholds)
        net_income = user.monthly_salary or Decimal("0.00")
        fixed_total = Decimal("0.00") # NOTE: A real implementation would fetch the user's current fixed total from SalaryAllocationProfile

        # --- BENCHMARKING CALL (INTEGRATION OF ML FALLBACK) ---
        benchmarking_service = BenchmarkingService(self.db, self.user_id)
        benchmark_factor = benchmarking_service.calculate_benchmark_factor(
            current_efs=new_efs_value,
            current_fixed_total=fixed_total,
            city_tier=user.city_tier,
            net_income=net_income
        ) 
        # -----------------------------------------------------

        baseline_results = calculate_dynamic_baseline(
            net_income=net_income,
            equivalent_family_size=new_efs_value,
            city_tier=user.city_tier,
            income_slab=user.income_slab,
            benchmark_efficiency_factor=benchmark_factor # <--- PASSING THE NEW BEF
        )

        # 5. Persist all calculated results
        profile.e_family_size = new_efs_value
        profile.benchmark_efficiency_factor = benchmark_factor # <--- SAVING THE BEF

        leakage_threshold = baseline_results.get("Total_Leakage_Threshold", Decimal("0.00"))
        profile.essential_target = leakage_threshold

        if net_income > Decimal("0.00"):
            profile.baseline_adjustment_factor = (leakage_threshold / net_income).quantize(Decimal("0.0001"))
        else:
            profile.baseline_adjustment_factor = Decimal("0.00")

        profile.last_calculated_at = datetime.utcnow()

        self.db.commit()
        return profile
    
    # ----------------------------------------------------------------------
