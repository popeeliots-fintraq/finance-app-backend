# services/benchmarking_service.py (ASYNC INTEGRATED VERSION)

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict
from datetime import datetime

# 🌟 FIX: Import AsyncSession and SQLAlchemy 2.0 components
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload # Helpful for eager loading if needed

# Import the necessary models and enums
# NOTE: Update these paths if your models are structured differently
from ..models.user_profile import User
from ..models.financial_profile import FinancialProfile 
from ..models.salary_profile import SalaryAllocationProfile
from ..db.enums import CityTier, IncomeSlab # Assuming you have these enums defined

# --- BENCHMARKING CONSTANTS ---
EFS_TOLERANCE = Decimal("0.10")        
FIXED_EXPENSE_TOLERANCE = Decimal("0.05") 

MIN_COHORT_SIZE = 5
BEST_USER_PERCENTILE = Decimal("0.20")

# CRITICAL FALLBACK FACTOR: A safe, pre-calculated efficiency factor.
DEFAULT_FALLBACK_FACTOR = Decimal("0.85") 

class BenchmarkingService:
    """
    Service responsible for calculating the 'Best User' efficiency factor (BEF) asynchronously.
    """
    # 🌟 FIX: Use the class constant for external reference
    DEFAULT_FALLBACK_FACTOR = DEFAULT_FALLBACK_FACTOR 

    # 🌟 FIX 1: Change DB type hint to AsyncSession
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    # 🌟 FIX 2: Make the core method async
    async def calculate_benchmark_factor(
        self,
        current_efs: Decimal,
        current_fixed_total: Decimal,
        city_tier: str, # Assuming CityTier is stored as a string or enum name
        net_income: Decimal 
    ) -> Decimal:
        """
        Calculates the benchmark efficiency factor from a cohort of similar users asynchronously.
        """

        # 1. Define the range for 'similar' users
        efs_min = current_efs * (Decimal("1.0") - EFS_TOLERANCE)
        efs_max = current_efs * (Decimal("1.0") + EFS_TOLERANCE)
        fixed_min = current_fixed_total * (Decimal("1.0") - FIXED_EXPENSE_TOLERANCE)
        fixed_max = current_fixed_total * (Decimal("1.0") + FIXED_EXPENSE_TOLERANCE)

        # 2. Query for the COHORT using SQLAlchemy 2.0 style select
        
        # NOTE ON QUERY COMPLEXITY: Benchmarking requires selecting the LATEST 
        # SalaryAllocationProfile for *each* similar user. A simple join might
        # return multiple profiles per user. For simplicity and performance, 
        # we'll currently select all matching profiles (assuming the caller
        # of the profile creation ensures data consistency/recency) and 
        # rely on filtering later. For robust production, you would need a 
        # CTE/Subquery to filter for the latest profile per user ID.
        
        # We select the SalaryAllocationProfile model, joining the others for filtering
        cohort_stmt = select(SalaryAllocationProfile).join(User).join(FinancialProfile).where(
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

        # 🌟 FIX 3: Execute the query asynchronously and fetch all results
        cohort_result = await self.db.execute(cohort_stmt)
        cohort_results: List[SalaryAllocationProfile] = cohort_result.scalars().all()
        
        # 3. CRITICAL: FAILURE PREVENTION - Check Cohort Size Guardrail
        if len(cohort_results) < MIN_COHORT_SIZE:
            # print(f"DEBUG: Cohort size too small ({len(cohort_results)}). Returning Fallback Factor.")
            return self.DEFAULT_FALLBACK_FACTOR

        # 4. Calculate Cohort Efficiency Ratios
        efficiency_ratios = []

        for profile in cohort_results:
            variable_income_pool = profile.net_monthly_income - profile.fixed_commitment_total
            
            # --- MOCK/FALLBACK for incomplete data ---
            # NOTE: If 'variable_spend_total' is not a dedicated column, 
            # this logic needs to be replaced by a live calculation or a 
            # persisted value from LeakageService.
            if not hasattr(profile, 'variable_spend_total') or profile.variable_spend_total is None:
                # Use an assumed average variable spend (e.g., 40% of their variable pool)
                # Ensure it's Decimal
                variable_spend = variable_income_pool * Decimal("0.40") 
            else:
                 variable_spend = profile.variable_spend_total
            # -----------------------------------------------------------------

            if variable_income_pool > Decimal("0.00"):
                # Ratio = Variable Spend / Variable Income Pool. Lower ratio is better.
                ratio = (variable_spend / variable_income_pool)
                efficiency_ratios.append(ratio)
        
        if not efficiency_ratios:
             return self.DEFAULT_FALLBACK_FACTOR

        # 5. Identify the Best Users (Lowest Ratio = Most Efficient)
        efficiency_ratios.sort() # Sorts from lowest (best saver) to highest (least efficient)

        # Ensure we take at least 1, but no more than the best_user_percentile
        best_user_count = max(1, int(len(efficiency_ratios) * BEST_USER_PERCENTILE))
        best_user_ratios = efficiency_ratios[:best_user_count]

        # 6. Calculate the Benchmark Factor (Average efficiency of the top savers)
        benchmark_factor = sum(best_user_ratios) / len(best_user_ratios)
        
        return benchmark_factor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
