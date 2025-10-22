# services/leakage_service.py

from decimal import Decimal
from typing import Dict, Any, List, Tuple 
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from datetime import date # Import for the reporting_period function argument

# 🚨 CRITICAL FIX: Update imports to reflect the file structure (assuming ml/ for logic)
# We only need the calculation logic, not the EFS one as it's handled in Orchestration
from ..ml.scaling_logic import calculate_dynamic_baseline

# Import models (Adjust path as needed to match your project structure)
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile # Assuming this holds the projected_reclaimable_salary


class LeakageService:
    """
    Core service class for calculating financial leakage based on the 
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: int): 
        self.db = db
        self.user_id = user_id
        
    def _fetch_profile_data_and_baselines(self) -> Dict[str, Any]:
        """Fetches required user financial data and calculates DMB/Thresholds."""
        
        # 1. Fetch the latest Salary Allocation Profile (to get Net Income)
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id
        ).order_by(SalaryAllocationProfile.reporting_period.desc()).first()

        if not salary_profile:
            raise NoResultFound("Salary Allocation Profile not found. Cannot calculate leaks.")

        # 2. Fetch the Financial Profile (which now holds EFS)
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()
        
        if not profile or not profile.e_family_size:
             raise NoResultFound("Financial Profile or Equivalent Family Size not found. Run OrchestrationService first.")

        # 3. Recalculate Baselines using the latest EFS and Income
        # This is essential to ensure the most current DMB/Thresholds are used
        baseline_results = calculate_dynamic_baseline(
            net_income=salary_profile.net_monthly_income,
            equivalent_family_size=profile.e_family_size
        )

        return {
            "net_monthly_income": salary_profile.net_monthly_income,
            "dynamic_baselines": baseline_results,
            "efs": profile.e_family_size
        }
        
    def _mock_leakage_spends(self, baselines: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """
        MOCK DATA: Simulates categorized spends for all relevant V2 Leak Buckets:
        VE (Variable Essential), SD (Scaled Discretionary), and PD (Pure Discretionary).
        """
        # NOTE: Using the categories defined in ml/scaling_logic.py
        mock_spends = {
            # --- VE Leak Buckets (Spending > Threshold is Leak) ---
            "Variable_Essential_Food": baselines.get("Variable_Essential_Food", Decimal("0.00")) * Decimal("1.30"), # 30% over threshold
            "Variable_Essential_Transport": baselines.get("Variable_Essential_Transport", Decimal("0.00")) * Decimal("0.80"), # No leak (under threshold)
            "Variable_Essential_Health": baselines.get("Variable_Essential_Health", Decimal("0.00")) * Decimal("1.05"), # Small leak (5% over threshold)
            
            # --- SD Leak Bucket (High Leakage items with a tight cap) ---
            "Scaled_Discretionary_Routine": baselines.get("Scaled_Discretionary_Routine", Decimal("0.00")) * Decimal("2.50"), # 150% over threshold - BIG LEAK
            
            # --- PD Leak Bucket (100% is a leak until Smart Rule is attached) ---
            "Pure_Discretionary_DiningOut": Decimal("3500.00"), 
            "Pure_Discretionary_Gadget": Decimal("500.00"),
        }
        return mock_spends
    
    # NOTE: The _convert_raw_counts_to_sds_structure helper method has been removed 
    # as the latest logic relies on the Dynamic Baseline calculation from Orchestration.

    def calculate_leakage(self, reporting_period: date) -> Dict[str, Any]:
        """
        Calculates leakage amount using the refined Stratified Dependent Scaling (SDS) baseline.
        Implements the three-bucket leak calculation for the 'Leakage Bucket View,'
        and PERSISTS the projected reclaimable salary to the DB.
        """
        
        try:
            profile_data = self._fetch_profile_data_and_baselines() 
        except NoResultFound as e:
            # Handle error gracefully
            return {"error": str(e)}

        dynamic_baselines = profile_data["dynamic_baselines"]
        current_spends = self._mock_leakage_spends(dynamic_baselines) 
        
        leakage_buckets: List[Dict[str, Any]] = []
        total_leakage = Decimal("0.00")
        
        # --- 1. Calculate Leakage for SCALED Categories (VE & SD) ---
        # Leak = Spend > Threshold (The Threshold is DMB minus the 15% margin)
        for category, threshold in dynamic_baselines.items():
            
            # Skip the summary items from the baseline results
            if category in ["Total_Leakage_Threshold", "Total_Minimal_Need_DMB", "Potential_Recoverable_Fund"]:
                continue
                
            spend = current_spends.get(category, Decimal("0.00"))
            
            # Leak: Max(0, Actual Spend - Leakage Threshold)
            leak_amount = max(Decimal("0.00"), spend - threshold)
            
            if spend > Decimal("0.00") and leak_amount >= Decimal("0.00"): # Check if there is actual spending or overspend
                
                # Only add to total_leakage if it's an overspend (leak_amount > 0)
                if leak_amount > Decimal("0.00"):
                    total_leakage += leak_amount
                    leak_source_description = "Above Scaled Threshold"
                else:
                    # If spending is below the threshold, it is a savings, not a leak for total_leakage, 
                    # but we include it in the buckets for the Leakage View.
                    leak_source_description = "Within Scaled Threshold (Savings)"
                
                # Build the Leakage Bucket View structure
                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(), 
                    "baseline_threshold": threshold.quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": leak_source_description,
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": f"{(leak_amount / spend) * 100:.2f}%" if spend > Decimal("0.00") else "0.00%"
                })
        
        # --- 2. Calculate Leakage for PURE DISCRETIONARY (PD) Categories ---
        # 100% of this spend is a leak if not covered by a Smart Rule
        pd_categories = ["Pure_Discretionary_DiningOut", "Pure_Discretionary_Gadget"]
        
        for category in pd_categories:
            spend = current_spends.get(category, Decimal("0.00"))
            
            if spend > Decimal("0.00"):
                leak_amount = spend 
                total_leakage += leak_amount
                
                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(),
                    "baseline_threshold": Decimal("0.00").quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": "100% Discretionary Spend",
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": "100.00%"
                })

        # 3. Final Reclaimable Salary is the total leak found
        projected_reclaimable_salary = total_leakage

        # 🚨 CRITICAL STEP: PERSIST THE LEAKAGE RESULT TO THE DB
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        if salary_profile:
            salary_profile.projected_reclaimable_salary = projected_reclaimable_salary
            self.db.commit()
        else:
            raise NoResultFound(f"Salary Allocation Profile not found for period {reporting_period}. Cannot save leak.")

        # 4. Return the calculated data for immediate display
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "leakage_buckets": leakage_buckets
        }
