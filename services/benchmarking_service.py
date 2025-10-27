from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

# Import the necessary models (assuming they are in the db directory)
from ..db.base import User
from ..db.models import SalaryAllocationProfile

# --- BENCHMARKING CONSTANTS ---
# Define the tolerance for filtering 'similar' users
EFS_TOLERANCE = Decimal("0.10")     # Users must have EFS +/- 10%
FIXED_EXPENSE_TOLERANCE = Decimal("0.05") # Fixed expenses must be +/- 5%

# Define the minimum sample size required to form a statistically reliable cohort
MIN_COHORT_SIZE = 5

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
        net_income: Decimal
    ) -> Optional[Decimal]:
        """
        Calculates the benchmark efficiency factor from a cohort of similar users.

        Returns:
            Decimal: The calculated efficiency factor (e.g., 0.88), or None if the cohort is too small.
        """

        # 1. Define the range for 'similar' users
        efs_min = current_efs * (Decimal("1.0") - EFS_TOLERANCE)
        efs_max = current_efs * (Decimal("1.0") + EFS_TOLERANCE)
        fixed_min = current_fixed_total * (Decimal("1.0") - FIXED_EXPENSE_TOLERANCE)
        fixed_max = current_fixed_total * (Decimal("1.0") + FIXED_EXPENSE_TOLERANCE)

        # 2. Query for the COHORT (Users matching the precise criteria)
        # We need to join User and SalaryAllocationProfile for the current month.
        # This is a complex query: get the average DMB / Average Net Income from the top N% of savers.
        # For simplicity, we benchmark on a proxy: Total Variable Spend / Total Minimal Need DMB ratio.
        
        # A. Find all users who match: City, EFS, and Fixed Expense band
        # NOTE: This query is simplified and assumes a perfect 'Total_Variable_Spend' exists on SalaryAllocationProfile.
        cohort_query = self.db.query(SalaryAllocationProfile).join(User).filter(
            # Matching the essential criteria:
            User.city_tier == city_tier,
            SalaryAllocationProfile.user_id != self.user_id, # Exclude the current user
            
            # Similar EFS (EFS is assumed to be stored on the FinancialProfile, but we simplify to a proxy)
            # 🚨 NOTE: Assuming a temporary EFS field on the User model for this example to work with join
            User.e_family_size >= efs_min,
            User.e_family_size <= efs_max,

            # Similar Fixed Expense Total
            SalaryAllocationProfile.fixed_commitment_total >= fixed_min,
            SalaryAllocationProfile.fixed_commitment_total <= fixed_max,
        )

        cohort_results = cohort_query.all()
        
        # 3. FAILURE PREVENTION: Check Cohort Size (The most critical failure point)
        if len(cohort_results) < MIN_COHORT_SIZE:
            return None # Fallback needed if cohort is too small

        # 4. Calculate Efficiency (simplified for this example)
        # Efficiency = (Variable Spend - Savings) / Total Income Available for Variable Spend
        
        # In a real model, you'd calculate the DMB for *each* cohort member and find the best one.
        # Here, we will simulate by finding the average 'Spend / Income' ratio of the top 20%
        
        # Mock calculation: Find the average ratio of (Variable Spend) / (Variable Income Pool) for the best savers
        
        # 🚨 SIMPLIFICATION: Assuming a high-efficiency user spends 88% of their DMB threshold.
        # In a production system, this 0.88 would be the result of a complex ML model on the cohort.
        
        return Decimal("0.88") # Returning 0.88 as the calculated "Best User" efficiency factor
