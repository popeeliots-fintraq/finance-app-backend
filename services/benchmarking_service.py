from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

# Import the necessary models and enums
from ..db.base import User, FinancialProfile 
from ..db.models import SalaryAllocationProfile
from ..db.enums import CityTier, IncomeSlab # Assuming you have these enums defined

# --- BENCHMARKING CONSTANTS ---
# Define the tolerance for filtering 'similar' users
EFS_TOLERANCE = Decimal("0.10")        # Users must have EFS +/- 10%
FIXED_EXPENSE_TOLERANCE = Decimal("0.05") # Fixed expenses must be +/- 5%

# Define the minimum sample size required to form a statistically reliable cohort
MIN_COHORT_SIZE = 5

# Define the efficiency percentile to select the 'Best Users'
# Lowest ratio = Best Saver (e.g., top 20% of lowest ratios)
BEST_USER_PERCENTILE = Decimal("0.20")

# CRITICAL FALLBACK FACTOR: A safe, pre-calculated efficiency factor to use when cohort size is too small.
# This prevents Behavioral Failure due to an unstable DMB.
DEFAULT_FALLBACK_FACTOR = Decimal("0.85") # Represents 85% efficiency for new users

class BenchmarkingService:
    """
    Service responsible for calculating the 'Best User' efficiency factor (BEF).
    This factor is derived from querying similar users who demonstrate high efficiency
    and is used by the LeakageService/OrchestrationService to adjust the Dynamic Minimal Baseline (DMB).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def calculate_benchmark_factor(
        self,
        current_efs: Decimal,
        current_fixed_total: Decimal,
        city_tier: str, # Assuming CityTier is stored as a string or enum name
        net_income: Decimal 
    ) -> Decimal:
        """
        Calculates the benchmark efficiency factor from a cohort of similar users.
        The factor is the average (Variable Spend / (Net Income - Fixed Total)) ratio 
        of the top X% best savers (lowest ratios) in the cohort.
        
        Returns the calculated factor (Decimal) or the safe DEFAULT_FALLBACK_FACTOR.
        """

        # 1. Define the range for 'similar' users
        efs_min = current_efs * (Decimal("1.0") - EFS_TOLERANCE)
        efs_max = current_efs * (Decimal("1.0") + EFS_TOLERANCE)
        fixed_min = current_fixed_total * (Decimal("1.0") - FIXED_EXPENSE_TOLERANCE)
        fixed_max = current_fixed_total * (Decimal("1.0") + FIXED_EXPENSE_TOLERANCE)

        # 2. Query for the COHORT (Users matching the precise criteria)
        # We join User, FinancialProfile (for EFS), and SalaryAllocationProfile (for spends)
        # IMPORTANT: Filters should target only the LATEST SalaryAllocationProfile for the cohort users
        
        cohort_query = self.db.query(SalaryAllocationProfile).join(User).join(FinancialProfile).filter(
            # Exclude the current user
            SalaryAllocationProfile.user_id != self.user_id, 
            # Ensure the cohort has calculated data for the ratio
            SalaryAllocationProfile.net_monthly_income > SalaryAllocationProfile.fixed_commitment_total,
            
            # Essential criteria
            User.city_tier == city_tier,

            # Similar EFS (using FinancialProfile)
            FinancialProfile.e_family_size >= efs_min,
            FinancialProfile.e_family_size <= efs_max,

            # Similar Fixed Expense Total (using SalaryAllocationProfile)
            SalaryAllocationProfile.fixed_commitment_total >= fixed_min,
            SalaryAllocationProfile.fixed_commitment_total <= fixed_max,
        )

        cohort_results: List[SalaryAllocationProfile] = cohort_query.all()
        
        # 3. CRITICAL: FAILURE PREVENTION - Check Cohort Size Guardrail
        if len(cohort_results) < MIN_COHORT_SIZE:
            print(f"DEBUG: Cohort size too small ({len(cohort_results)}). Returning Fallback Factor.")
            return self.DEFAULT_FALLBACK_FACTOR

        # 4. Calculate Cohort Efficiency Ratios
        efficiency_ratios = []

        for profile in cohort_results:
            variable_income_pool = profile.net_monthly_income - profile.fixed_commitment_total
            
            # --- MOCK/FALLBACK for incomplete data (REMOVE FOR PRODUCTION) ---
            if not hasattr(profile, 'variable_spend_total') or profile.variable_spend_total is None:
                # Use an assumed average variable spend (e.g., 40% of their variable pool)
                profile.variable_spend_total = variable_income_pool * Decimal("0.40") 
            # -----------------------------------------------------------------

            if variable_income_pool > Decimal("0.00"):
                # Ratio = Variable Spend / Variable Income Pool. Lower ratio is better.
                ratio = (profile.variable_spend_total / variable_income_pool)
                efficiency_ratios.append(ratio)
        
        if not efficiency_ratios:
             # This should be caught by the cohort size check, but acts as a final safeguard.
             return self.DEFAULT_FALLBACK_FACTOR

        # 5. Identify the Best Users (Lowest Ratio = Most Efficient)
        efficiency_ratios.sort() # Sorts from lowest (best saver) to highest (least efficient)

        # Ensure we take at least 1, but no more than the best_user_percentile
        best_user_count = max(1, int(len(efficiency_ratios) * BEST_USER_PERCENTILE))
        best_user_ratios = efficiency_ratios[:best_user_count]

        # 6. Calculate the Benchmark Factor (Average efficiency of the top savers)
        benchmark_factor = sum(best_user_ratios) / len(best_user_ratios)
        
        return benchmark_factor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
