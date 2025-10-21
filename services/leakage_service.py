# services/leakage_service.py

from decimal import Decimal
# 🚨 FIX: Added Tuple to the import list from typing
from typing import Dict, Any, List, Tuple 
from sqlalchemy.orm import Session
from ..utils.ml_logic import (
    calculate_equivalent_family_size,
    calculate_dynamic_baseline,
    calculate_stratified_dependent_scaling 
)
from ..db.models import SalaryAllocationProfile, UserProfile 


class LeakageService:
    """
    Core service class for calculating financial leakage based on the 
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        
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
        
    def _mock_leakage_spends(self, dynamic_baselines: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """
        MOCK DATA: Simulates categorized spends from UPI/SMS integration. [cite: 2025-10-15]
        
        In the real system, this data would come from categorized transactions 
        stored in the DB (categorized spends). [cite: 2025-10-15]
        """
        # Actual spending for the Variable Essential categories
        
        # NOTE: Using the categories defined in ml_logic.py (e.g., 'groceries', 'utility')
        mock_spends = {
            "groceries": dynamic_baselines.get("groceries", Decimal(0)) * Decimal("1.25"), # 25% over baseline
            "transport": dynamic_baselines.get("transport", Decimal(0)) * Decimal("0.90"), # 10% under baseline
            "utility": dynamic_baselines.get("utility", Decimal(0)) * Decimal("1.10"), # 10% over baseline
            "housing": dynamic_baselines.get("housing", Decimal(0)) * Decimal("1.00"), # On baseline
        }
        return mock_spends

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
            
        # For simplicity, dependents over 18 are treated as additional adults for SDS.
        if raw_counts["num_dependents_over_18"] > 0:
            sds_structure.append(("additional_adult", raw_counts["num_dependents_over_18"]))
            
        return sds_structure


    def calculate_leakage(self) -> Dict[str, Any]:
        """
        Calculates leakage amount using the refined Stratified Dependent Scaling (SDS) baseline.
        Replaces the old expense dashboard task with the 'Leakage Bucket View.' [cite: 2025-10-15]
        """
        
        profile_data = self._fetch_profile_data()
        net_income = profile_data["net_monthly_income"]
        efs = profile_data["equivalent_family_size"]
        raw_counts = profile_data["raw_dependent_counts"]
        
        # 1. Calculate the initial Dynamic Minimal Baseline
        initial_baselines = calculate_dynamic_baseline(net_income, efs)
        
        # 2. Convert raw counts and apply Stratified Dependent Scaling (SDS)
        sds_structure = self._convert_raw_counts_to_sds_structure(raw_counts)
        # Use the more accurate SDS result
        dynamic_baselines = calculate_stratified_dependent_scaling(initial_baselines, sds_structure)
        
        # 3. Get categorized spends (MOCK for now)
        current_spends = self._mock_leakage_spends(dynamic_baselines) 
        
        leakage_buckets: List[Dict[str, Any]] = []
        total_leakage = Decimal("0.00")
        
        # 4. Calculate Leakage: Leak = Max(0, Spend - Baseline)
        for category, baseline in dynamic_baselines.items():
            
            spend = current_spends.get(category, Decimal("0.00"))
            
            # The definition of Fin-Traq "Leak": any spend amount above the 
            # dynamically adjusted minimal baseline for that category. [cite: 2025-10-17]
            leak_amount = max(Decimal("0.00"), spend - baseline)
            
            if leak_amount > Decimal("0.00"):
                total_leakage += leak_amount
                
                # Build the Leakage Bucket View structure [cite: 2025-10-15]
                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(), # Clean up category name for display
                    "baseline": baseline.quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    # Calculate percentage of overspend relative to baseline
                    "leak_percentage": f"{(leak_amount / baseline) * 100:.2f}%" if baseline > Decimal("0.00") else "N/A"
                })

        # 5. Build reclaimable salary projection logic [cite: 2025-10-15]
        projected_reclaimable_salary = total_leakage
        
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "leakage_buckets": leakage_buckets
        }
