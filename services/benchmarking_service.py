from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

# Import the necessary models (assuming they are in the db directory)
# 🚨 NOTE: Assuming 'e_family_size' is now correctly moved to the 'FinancialProfile' model
#          The SQL query will need to be updated to JOIN FinancialProfile.
from ..db.base import User, FinancialProfile # <-- Added FinancialProfile
from ..db.models import SalaryAllocationProfile

# --- BENCHMARKING CONSTANTS ---
# Define the tolerance for filtering 'similar' users
EFS_TOLERANCE = Decimal("0.10")     # Users must have EFS +/- 10%
FIXED_EXPENSE_TOLERANCE = Decimal("0.05") # Fixed expenses must be +/- 5%

# Define the minimum sample size required to form a statistically reliable cohort
MIN_COHORT_SIZE = 5

# Define the efficiency percentile to select the 'Best Users'
# Lowest ratio = Best Saver (e.g., top 20% of lowest ratios)
BEST_USER_PERCENTILE = Decimal("0.20") 

class BenchmarkingService:
    """
    Service responsible for calculating the 'Best User' efficiency factor
    by querying similar users who demonstrate high efficiency. This factor 
    is used by the LeakageService to adjust the Dynamic Minimal Baseline (DMB).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def calculate_efficiency_factor(
        self,
        current_efs: Decimal,
        current_fixed_total: Decimal,
        city_tier: str,
        net_income: Decimal 
    ) -> Optional[Decimal]:
        """
        Calculates the benchmark efficiency factor from a cohort of similar users.
        The factor is the average (Variable Spend / (Net Income - Fixed Total)) ratio 
        of the top 20% best savers (lowest ratios) in the cohort.
        """

        # 1. Define the range for 'similar' users
        efs_min = current_efs * (Decimal("1.0") - EFS_TOLERANCE)
        efs_max = current_efs * (Decimal("1.0") + EFS_TOLERANCE)
        fixed_min = current_fixed_total * (Decimal("1.0") - FIXED_EXPENSE_TOLERANCE)
        fixed_max = current_fixed_total * (Decimal("1.0") + FIXED_EXPENSE_TOLERANCE)

        # 2. Query for the COHORT (Users matching the precise criteria)
        # We join User, FinancialProfile (for EFS), and SalaryAllocationProfile (for spends)
        
        cohort_query = self.db.query(SalaryAllocationProfile).join(User).join(FinancialProfile).filter(
            # Exclude the current user and ensure necessary data integrity
            SalaryAllocationProfile.user_id != self.user_id, 
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
        
        # 3. FAILURE PREVENTION: Check Cohort Size Guardrail
        if len(cohort_results) < MIN_COHORT_SIZE:
            return None # Cannot generate a reliable benchmark

        # 4. Calculate Cohort Efficiency Ratios
        efficiency_ratios = []

        for profile in cohort_results:
            variable_income_pool = profile.net_monthly_income - profile.fixed_commitment_total
            
            # --- MOCK DATA SIMPLIFICATION ---
            # NOTE: In the live system, 'variable_spend_total' must be populated
            # by the LeakageService for historical periods.
            if not hasattr(profile, 'variable_spend_total') or profile.variable_spend_total is None:
                # Fallback or Mock for calculation completeness. 
                # This should be replaced with real data lookup.
                profile.variable_spend_total = variable_income_pool * Decimal("0.40") 
            # ---------------------------------

            if variable_income_pool > Decimal("0.00"):
                # Ratio = Variable Spend / Variable Income Pool
                ratio = (profile.variable_spend_total / variable_income_pool)
                efficiency_ratios.append(ratio)
        
        if not efficiency_ratios:
             return None

        # 5. Identify the Best Users (Lowest Ratio = Most Efficient)
        efficiency_ratios.sort() # Sorts from lowest (best) to highest (least efficient)

        best_user_count = max(1, int(len(efficiency_ratios) * BEST_USER_PERCENTILE))
        best_user_ratios = efficiency_ratios[:best_user_count]

        # 6. Calculate the Benchmark Factor (Average efficiency of the top savers)
        benchmark_factor = sum(best_user_ratios) / len(best_user_ratios)
        
        return benchmark_factor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
