# services/financial_profile_service.py

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from datetime import datetime, date

from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile
from .benchmarking_service import BenchmarkingService # Import your service

# --- SDS CONSTANTS (Simplified weights for EFS calculation) ---
# Weights based on the OECD-modified equivalence scale (or similar, customized)
ADULT_WEIGHT = Decimal("1.00")
SECOND_ADULT_WEIGHT = Decimal("0.50")
DEPENDENT_6_TO_17_WEIGHT = Decimal("0.30")
DEPENDENT_UNDER_6_WEIGHT = Decimal("0.20")
# Assuming over 18 dependents are treated as full adults/second adults depending on their status
DEPENDENT_OVER_18_WEIGHT = Decimal("0.50") 

# --- DMB CALCULATION CONSTANTS ---
# Percentage of Variable Income Pool that should go to the Essential Target, pre-scaling.
DEFAULT_ESSENTIAL_TARGET_PERCENT = Decimal("0.50") # 50% of the non-fixed income pool

class FinancialProfileService:
    """
    Service responsible for calculating and updating the user's FinancialProfile (ML Outputs),
    including EFS and the Dynamic Minimal Baseline (DMB).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.benchmarking_service = BenchmarkingService(db, user_id)
        
    def _get_user_and_latest_profile(self) -> Optional[tuple[User, FinancialProfile, SalaryAllocationProfile]]:
        """Helper to fetch necessary records for ML calculation."""
        user = self.db.query(User).filter(User.id == self.user_id).first()
        if not user: return None

        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()
        if not profile: # Create a profile if it doesn't exist
            profile = FinancialProfile(user_id=self.user_id)
            self.db.add(profile)
            self.db.flush()

        # Get the latest allocation profile for fixed/variable data
        latest_salary_profile = self.db.query(SalaryAllocationProfile)\
            .filter(SalaryAllocationProfile.user_id == self.user_id)\
            .order_by(SalaryAllocationProfile.reporting_period.desc())\
            .first()
            
        return user, profile, latest_salary_profile


    def _calculate_equivalent_family_size(self, user: User) -> Decimal:
        """
        Calculates the Equivalent Family Size (EFS) based on demographic inputs.
        """
        # Start with the primary adult
        efs = ADULT_WEIGHT
        
        # Add weights for second adult/dependents over 18
        if user.num_adults > 1:
            # We assume one primary adult and all others are weighted by 0.50
            efs += (user.num_adults - 1) * SECOND_ADULT_WEIGHT
            
        # Add remaining dependents (assuming they are not counted as adults/second adults)
        efs += user.num_dependents_under_6 * DEPENDENT_UNDER_6_WEIGHT
        efs += user.num_dependents_6_to_17 * DEPENDENT_6_TO_17_WEIGHT
        # Handle dependents over 18; if not included in num_adults, apply a weight
        # If dependents over 18 are covered by num_adults, this line can be removed.
        # For robustness, we'll keep it, assuming they are non-adult dependents:
        efs += user.num_dependents_over_18 * DEPENDENT_OVER_18_WEIGHT

        return efs.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


    def calculate_and_save_dmb(self) -> FinancialProfile:
        """
        Executes the three-step ML pipeline: EFS -> BEF -> DMB.
        Updates and returns the FinancialProfile.
        """
        result = self._get_user_and_latest_profile()
        if not result:
            raise ValueError("User not found or initial setup incomplete.")
            
        user, profile, latest_salary_profile = result
        
        # --- STEP 1: Calculate EFS (Stratified Dependent Scaling base) ---
        new_efs = self._calculate_equivalent_family_size(user)
        profile.e_family_size = new_efs
        
        # --- STEP 2: Calculate Benchmark Efficiency Factor (BEF) ---
        
        # We need a recent salary profile to calculate BEF, otherwise use the fallback
        if latest_salary_profile:
            current_fixed_total = latest_salary_profile.fixed_commitment_total
            
            # The net_income passed to benchmarking should ideally be stable, using monthly_salary from User
            benchmark_factor = self.benchmarking_service.calculate_benchmark_factor(
                current_efs=new_efs,
                current_fixed_total=current_fixed_total,
                city_tier=user.city_tier,
                net_income=user.monthly_salary
            )
        else:
            # Cannot benchmark without spending history, use safe default
            benchmark_factor = BenchmarkingService.DEFAULT_FALLBACK_FACTOR 
            current_fixed_total = Decimal("0.00")

        profile.benchmark_efficiency_factor = benchmark_factor
        
        # --- STEP 3: Calculate Dynamic Minimal Baseline (DMB) ---
        
        variable_income_pool = user.monthly_salary - current_fixed_total
        if variable_income_pool < Decimal("0.00"):
            # Handle edge case where fixed expenses exceed salary (system failure/data issue)
            variable_income_pool = Decimal("0.00")

        # Base DMB Target = (Variable Income Pool * Default Target %)
        base_dmb_target = variable_income_pool * DEFAULT_ESSENTIAL_TARGET_PERCENT

        # Dynamic Minimal Baseline (DMB) calculation:
        # DMB = Base Target * EFS Factor * Benchmark Efficiency Factor
        # The EFS and BEF factors are assumed to dynamically adjust the base target.
        
        # For simplicity, we assume EFS is a linear factor for now, though it's typically used to calculate per-capita costs.
        # Here, we use the BEF to scale the DMB down (if user is inefficient) or up (if target is aggressive).
        
        # DMB = Base Target * BEF
        dynamic_minimal_baseline = base_dmb_target * benchmark_factor
        
        # Save the final DMB
        profile.essential_target = dynamic_minimal_baseline.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        profile.last_calculated_at = datetime.utcnow()
        
        self.db.commit()
        return profile
