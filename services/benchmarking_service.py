from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

# Import the necessary models (assuming they are in the db directory)
# 🚨 NOTE: Assuming a temporary EFS field on the User model for this example to work with join
from ..db.base import User
from ..db.models import SalaryAllocationProfile

# --- BENCHMARKING CONSTANTS ---
# Define the tolerance for filtering 'similar' users
EFS_TOLERANCE = Decimal("0.10")     # Users must have EFS +/- 10%
FIXED_EXPENSE_TOLERANCE = Decimal("0.05") # Fixed expenses must be +/- 5%

# Define the minimum sample size required to form a statistically reliable cohort
MIN_COHORT_SIZE = 5

# Define the efficiency percentile to select the 'Best Users'
BEST_USER_PERCENTILE = Decimal("0.20") 

class BenchmarkingService:
    """
    Service responsible for calculating the 'Best User' efficiency factor
    by querying similar users who demonstrate high efficiency.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def calculate_efficiency_factor(
        self,
        current_efs: Decimal,
        current_fixed_total: Decimal,
        city_tier: str,
        # net_income is not strictly needed for the efficiency factor but kept for context
        net_income: Decimal 
    ) -> Optional[Decimal]:
        """
        Calculates the benchmark efficiency factor from a cohort of similar users.
        The factor is the average (Variable Spend / (Net Income - Fixed Total)) ratio 
        of the top 20% best savers in the cohort.
        """

        # 1. Define the range for 'similar' users
        efs_min = current_efs * (Decimal("1.0") - EFS_TOLERANCE)
        efs_max = current_efs * (Decimal("1.0") + EFS_TOLERANCE)
        fixed_min = current_fixed_total * (Decimal("1.0") - FIXED_EXPENSE_TOLERANCE)
        fixed_max = current_fixed_total * (Decimal("1.0") + FIXED_EXPENSE_TOLERANCE)

        # 2. Query for the COHORT (Users matching the precise criteria)
        # We assume SalaryAllocationProfile has a 'variable_spend_total' field for this to work.
        
        cohort_query = self.db.query(SalaryAllocationProfile).join(User).filter(
            # Essential criteria
            User.city_tier == city_tier,
            SalaryAllocationProfile.user_id != self.user_id, 

            # Similar EFS 
            User.e_family_size >= efs_min,
            User.e_family_size <= efs_max,

            # Similar Fixed Expense Total
            SalaryAllocationProfile.fixed_commitment_total >= fixed_min,
            SalaryAllocationProfile.fixed_commitment_total <= fixed_max,
            
            # Ensure data integrity for calculation
            SalaryAllocationProfile.net_monthly_income > SalaryAllocationProfile.fixed_commitment_total
        )

        cohort_results: List[SalaryAllocationProfile] = cohort_query.all()
        
        # 3. FAILURE PREVENTION: Check Cohort Size 
        if len(cohort_results) < MIN_COHORT_SIZE:
            return None # Fallback needed

        # 4. Calculate Cohort Efficiency (The Best User Benchmark)
        efficiency_ratios = []

        for profile in cohort_results:
            variable_income_pool = profile.net_monthly_income - profile.fixed_commitment_total
            
            # 🚨 MOCK DATA SIMPLIFICATION: We need a variable_spend_total field.
            # Since that field is not explicitly defined in the provided models, we will 
            # derive a mock variable spend for the calculation to proceed.
            # In a real system: variable_spend_total should be the sum of all variable categories.
            if not hasattr(profile, 'variable_spend_total'):
                # Mock high-efficiency spending to demonstrate the calculation
                profile.variable_spend_total = variable_income_pool * Decimal("0.40") 

            if variable_income_pool > Decimal("0.00"):
                # Ratio = Variable Spend / Variable Income Pool
                ratio = (profile.variable_spend_total / variable_income_pool)
                efficiency_ratios.append(ratio)
        
        if not efficiency_ratios:
             return None

        # Sort the ratios (lowest ratio = most efficient/best saver)
        efficiency_ratios.sort()

        # Identify the top 20% (Best Users)
        best_user_count = max(1, int(len(efficiency_ratios) * BEST_USER_PERCENTILE))
        best_user_ratios = efficiency_ratios[:best_user_count]

        # The Benchmark Factor is the AVERAGE efficiency of the top savers.
        # This average represents the *spending* pattern of the best users.
        benchmark_factor = sum(best_user_ratios) / len(best_user_ratios)
        
        # We need to round the result
        return benchmark_factor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
