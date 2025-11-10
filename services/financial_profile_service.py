# services/financial_profile_service.py (ASYNC INTEGRATED VERSION)

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict
from datetime import datetime, date

# 🌟 FIX: Import AsyncSession, select, and update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import NoResultFound

# --- NEW MODEL IMPORTS ---
# NOTE: Replace with your actual model paths if different
from ..models.user_profile import User
from ..models.financial_profile import FinancialProfile
from ..models.salary_profile import SalaryAllocationProfile
from .benchmarking_service import BenchmarkingService 

# --- SDS CONSTANTS (Simplified weights for EFS calculation) ---
ADULT_WEIGHT = Decimal("1.00")
SECOND_ADULT_WEIGHT = Decimal("0.50")
DEPENDENT_6_TO_17_WEIGHT = Decimal("0.30")
DEPENDENT_UNDER_6_WEIGHT = Decimal("0.20")
DEPENDENT_OVER_18_WEIGHT = Decimal("0.50") 

# --- DMB CALCULATION CONSTANTS ---
DEFAULT_ESSENTIAL_TARGET_PERCENT = Decimal("0.50")

class FinancialProfileService:
    """
    Service responsible for calculating and updating the user's FinancialProfile (ML Outputs),
    including EFS and the Dynamic Minimal Baseline (DMB).
    """

    # 🌟 FIX: Change DB type hint to AsyncSession
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        # BenchmarkingService MUST also be updated to accept AsyncSession
        self.benchmarking_service = BenchmarkingService(db, user_id)
        
    # 🌟 FIX: Make helper async and use execute
    async def _get_user_and_latest_profile(self) -> Optional[tuple[User, FinancialProfile, SalaryAllocationProfile]]:
        """Helper to fetch necessary records for ML calculation asynchronously."""
        
        # 1. Fetch User
        user_stmt = select(User).where(User.id == self.user_id)
        user_result = await self.db.execute(user_stmt)
        user = user_result.scalars().first()
        if not user: return None

        # 2. Fetch FinancialProfile (or create one)
        profile_stmt = select(FinancialProfile).where(FinancialProfile.user_id == self.user_id)
        profile_result = await self.db.execute(profile_stmt)
        profile = profile_result.scalars().first()
        
        if not profile: # Create a profile if it doesn't exist
            profile = FinancialProfile(user_id=self.user_id)
            self.db.add(profile)
            # Need to flush to get the ID, but no commit yet
            # NOTE: We rely on the parent transaction to commit, so flush is sufficient.
            await self.db.flush() 

        # 3. Get the latest allocation profile for fixed/variable data
        latest_salary_profile_stmt = select(SalaryAllocationProfile)\
            .where(SalaryAllocationProfile.user_id == self.user_id)\
            .order_by(SalaryAllocationProfile.reporting_period.desc())\
            .limit(1)
            
        latest_profile_result = await self.db.execute(latest_salary_profile_stmt)
        latest_salary_profile = latest_profile_result.scalars().first()
            
        return user, profile, latest_salary_profile


    def _calculate_equivalent_family_size(self, user: User) -> Decimal:
        """
        Calculates the Equivalent Family Size (EFS) based on demographic inputs.
        (Remains sync as it has no DB calls)
        """
        # Start with the primary adult
        efs = ADULT_WEIGHT
        
        # Add weights for second adult/dependents over 18
        if user.num_adults > 1:
            efs += (user.num_adults - 1) * SECOND_ADULT_WEIGHT
            
        # Add remaining dependents
        efs += user.num_dependents_under_6 * DEPENDENT_UNDER_6_WEIGHT
        efs += user.num_dependents_6_to_17 * DEPENDENT_6_TO_17_WEIGHT
        efs += user.num_dependents_over_18 * DEPENDENT_OVER_18_WEIGHT

        return efs.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


    # 🌟 FIX: Make the core method async
    async def calculate_and_save_dmb(self) -> FinancialProfile:
        """
        Executes the three-step ML pipeline: EFS -> BEF -> DMB.
        Updates and returns the FinancialProfile.
        """
        # 🌟 FIX: Await the async helper
        result = await self._get_user_and_latest_profile()
        if not result:
            raise ValueError("User not found or initial setup incomplete.")
            
        user, profile, latest_salary_profile = result
        
        # --- STEP 1: Calculate EFS (Stratified Dependent Scaling base) ---
        new_efs = self._calculate_equivalent_family_size(user)
        profile.e_family_size = new_efs
        
        # --- STEP 2: Calculate Benchmark Efficiency Factor (BEF) ---
        if latest_salary_profile:
            current_fixed_total = latest_salary_profile.fixed_commitment_total
            
            # 🌟 FIX: BenchmarkingService method must be awaited
            benchmark_factor = await self.benchmarking_service.calculate_benchmark_factor(
                current_efs=new_efs,
                current_fixed_total=current_fixed_total,
                city_tier=user.city_tier,
                net_income=user.monthly_salary
            )
        else:
            benchmark_factor = BenchmarkingService.DEFAULT_FALLBACK_FACTOR 
            current_fixed_total = Decimal("0.00")

        profile.benchmark_efficiency_factor = benchmark_factor
        
        # --- STEP 3: Calculate Dynamic Minimal Baseline (DMB) ---
        variable_income_pool = user.monthly_salary - current_fixed_total
        if variable_income_pool < Decimal("0.00"):
            variable_income_pool = Decimal("0.00")

        base_dmb_target = variable_income_pool * DEFAULT_ESSENTIAL_TARGET_PERCENT
        dynamic_minimal_baseline = base_dmb_target * benchmark_factor
        
        # Save the final DMB
        profile.essential_target = dynamic_minimal_baseline.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        profile.last_calculated_at = datetime.utcnow()
        
        # The profile object is already 'dirty' in the session; 
        # we don't need a manual commit, but we should flush to ensure data is updated 
        # before the final commit by the dependency.
        await self.db.flush() 
        return profile
