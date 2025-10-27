# services/leakage_service.py

from decimal import Decimal
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from datetime import date

# CRITICAL FIX: Update imports to reflect the file structure
from ..ml.scaling_logic import calculate_dynamic_baseline 
# 🚨 NEW IMPORT: Benchmarking Service
from .benchmarking_service import BenchmarkingService 

# Import models
# 🚨 NOTE: Assuming User model now contains city_tier and income_slab
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile

# 🚨 DEFINITION: Absolute floor for essential spending to prevent below-par living
GLOBAL_MINIMAL_BASELINE_FLOOR = Decimal("15000.00") # Placeholder for the absolute GMB

class LeakageService:
    """
    Core service class for calculating financial leakage based on the
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def _fetch_profile_data_and_baselines(self, reporting_period: date) -> Dict[str, Any]:
        """
        Fetches required user financial data and calculates DMB/Thresholds.
        CRITICAL FIX: Creates a SalaryAllocationProfile if one does not exist for the period
        and fetches all data needed for benchmarking.
        """
        
        # 1. Fetch or Create the Salary Allocation Profile (to get Net Income)
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        # 2. Fetch User data (needed for income_slab and city_tier)
        user_info = self.db.query(User).filter(User.id == self.user_id).first()
        if not user_info:
            raise NoResultFound(f"User ID {self.user_id} not found.")

        if not salary_profile:
            # 🚨 FAILURE PREVENTION: If profile is missing, create a new one.
            salary_profile = SalaryAllocationProfile(
                user_id=self.user_id,
                reporting_period=reporting_period,
                net_monthly_income=user_info.monthly_salary,
                fixed_commitment_total=Decimal("0.00"), # Placeholder/Needs calculation
            )
            self.db.add(salary_profile)
            self.db.flush() 

        # 3. Fetch the Financial Profile (which now holds EFS)
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()

        if not profile or not profile.e_family_size:
            raise NoResultFound("Financial Profile or Equivalent Family Size not found. Run OrchestrationService first to calculate EFS.")
        
        # 4. Calculate Benchmarking Factor using the new service
        benchmarking_service = BenchmarkingService(self.db, self.user_id)
        
        # 🚨 NEW LOGIC: Attempt to find the best user benchmark
        benchmark_factor = benchmarking_service.calculate_efficiency_factor(
            current_efs=profile.e_family_size,
            current_fixed_total=salary_profile.fixed_commitment_total,
