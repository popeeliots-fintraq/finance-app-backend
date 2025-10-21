# services/leakage_service.py

from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from ..utils.ml_logic import (
    # 🚨 Updated Import: Use all necessary ML functions
    calculate_equivalent_family_size,
    calculate_dynamic_baseline,
    calculate_stratified_dependent_scaling # 🚨 NEW: Import SDS logic
)
# 🚨 Fix: Cleaned up import to use UserProfile model
from ..db.models import SalaryAllocationProfile, UserProfile 
# 🚨 Remove the incorrect import: from ..services.ml_service import calculate_dynamic_minimal_baseline


class LeakageService:
    # ... (init remains the same) ...
        
    def _fetch_profile_data(self) -> Dict[str, Any]:
        """Fetches required user financial data, including raw counts for SDS."""
        
        # 1. Fetch the latest Salary Allocation Profile (to get Net Income)
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id
        ).order_by(SalaryAllocationProfile.reporting_period.desc()).first()

        if not salary_profile:
            raise ValueError("Salary Allocation Profile not found. Cannot calculate leaks.")

        # 2. Fetch the User Profile (to get EFS and raw dependent counts for SDS)
        user_profile = self.db.query(UserProfile).filter(
            UserProfile.user_id == self.user_id
        ).first()
        
        # Default EFS to 1.00 if profile is missing (single person household)
        # 🚨 FIX: Ensure all raw inputs for SDS are fetched, defaulting to 1 adult if profile is missing
        if user_profile:
            profile_data = {
                "equivalent_family_size": user_profile.equivalent_family_size,
                "raw_dependent_counts": {
                    "num_adults": user_profile.num_adults,
                    "num_dependents_under_6": user_profile.num_dependents_under_6,
                    "num_dependents_6_to_17": user_profile.num_dependents_6_to_17,
                    "num_dependents_over_18": user_profile.num_dependents_over_18,
                }
            }
        else:
            profile_data = {
                "equivalent_family_size": Decimal("1.00"),
                "raw_dependent_counts": {"num_adults": 1, "num_dependents_under_6": 0, "num_dependents_6_to_17": 0, "num_dependents_over_18": 0}
            }

        return {
            "net_monthly_income": salary_profile.net_monthly_income,
            **profile_data
        }
        
    # ... (_mock_leakage_spends remains the same, but category names should match ml_logic) ...
    # NOTE: The categories in _mock_leakage_spends (e.g., Variable_Essential_Food) 
    # should ideally match the categories returned by calculate_dynamic_baseline (e.g., groceries, utility)

    def _convert_raw_counts_to_sds_structure(self, raw_counts: Dict[str, int]) -> List[Tuple[str, int]]:
        """Maps raw user input counts to the stratified dependent structure required by SDS."""
        
        sds_structure: List[Tuple[str, int]] = []
        
        # Add additional adults (num_adults - 1)
        num_additional_adults = raw_counts["num_adults"] - 1
        if num_additional_adults > 0:
            sds_structure.append(("additional_adult", num_additional_adults))
            
        # Map age brackets to SDS weights (using 'child' and 'infant' logic)
        if raw_counts["num_dependents_under_6"] > 0:
            sds_structure.append(("infant", raw_counts["num_dependents_under_6"]))
        
        if raw_counts["num_dependents_6_to_17"] > 0:
            sds_structure.append(("child", raw_counts["num_dependents_6_to_17"]))
            
        # NOTE: Dependents over 18 could be "additional_adult" or "elderly." 
        # For simplicity, we'll map them as "additional_adult" for now.
        if raw_counts["num_dependents_over_18"] > 0:
            sds_structure.append(("additional_adult", raw_counts["num_dependents_over_18"]))
            
        return sds_structure


    def calculate_leakage(self) -> Dict[str, Any]:
        """
        Calculates leakage amount using the refined Stratified Dependent Scaling (SDS) baseline.
        """
        
        profile_data = self._fetch_profile_data()
        net_income = profile_data["net_monthly_income"]
        efs = profile_data["equivalent_family_size"]
        raw_counts = profile_data["raw_dependent_counts"]
        
        # 1. Calculate the initial Dynamic Minimal Baseline
        initial_baselines = calculate_dynamic_baseline(net_income, efs)
        
        # 2. Convert raw counts and apply Stratified Dependent Scaling (SDS)
        sds_structure = self._convert_raw_counts_to_sds_structure(raw_counts)
        dynamic_baselines = calculate_stratified_dependent_scaling(initial_baselines, sds_structure)
        
        # 3. Get categorized spends (MOCK for now)
        # NOTE: Renamed to match the categories in ml_logic.py
        current_spends = self._mock_leakage_spends(dynamic_baselines) 
        
        # ... (rest of the leakage calculation logic remains the same) ...
        # (It will now correctly use the refined dynamic_baselines from SDS)
