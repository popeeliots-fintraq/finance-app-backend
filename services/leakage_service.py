# services/leakage_service.py

from decimal import Decimal
from typing import Dict, Any, List, Tuple 
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound

# 🚨 CRITICAL FIX: Update imports to reflect the file structure
from ..ml.efs_calculator import calculate_equivalent_family_size
from ..ml.scaling_logic import calculate_dynamic_baseline # This now includes the 15% margin logic

# Import models (Adjust path as needed, assuming FinancialProfile is the correct model for EFS/DMB)
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, SmartTransferRule # Assuming UserProfile is now FinancialProfile or User


class LeakageService:
    """
    Core service class for calculating financial leakage based on the 
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: int): # Changed user_id to int for consistency
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

        # 2. Fetch the Financial Profile (which now holds EFS and DMB components)
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()
        
        if not profile:
             raise NoResultFound("Financial Profile not found. Run OrchestrationService.calculate_and_save_financial_profile first.")

        # 3. Recalculate Baselines (Best practice to ensure data is fresh)
        # NOTE: This should ideally be fetched from the FinancialProfile for performance
        # but is recalculated here for demonstration clarity.
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
            "Variable_Essential_Food": baselines["Variable_Essential_Food"] * Decimal("1.30"), # 30% over threshold
            "Variable_Essential_Transport": baselines["Variable_Essential_Transport"] * Decimal("0.80"), # No leak (under threshold)
            "Variable_Essential_Health": baselines["Variable_Essential_Health"] * Decimal("1.05"), # Small leak (5% over threshold)
            
            # --- SD Leak Bucket (High Leakage items with a tight cap) ---
            "Scaled_Discretionary_Routine": baselines["Scaled_Discretionary_Routine"] * Decimal("2.50"), # 150% over threshold - BIG LEAK
            
            # --- PD Leak Bucket (100% is a leak until Smart Rule is attached) ---
            "Pure_Discretionary_DiningOut": Decimal("3500.00"), 
            "Pure_Discretionary_Gadget": Decimal("500.00"),
        }
        return mock_spends

    # The conversion logic is complex and not strictly needed since we are recalculating 
    # the baselines directly from the FinancialProfile, so we will simplify.
    
    def calculate_leakage(self) -> Dict[str, Any]:
        """
        Calculates leakage amount using the refined Stratified Dependent Scaling (SDS) baseline.
        Implements the three-bucket leak calculation for the 'Leakage Bucket View.'
        """
        
        try:
            profile_data = self._fetch_profile_data_and_baselines()
        except NoResultFound as e:
            return {"error": str(e)}

        dynamic_baselines = profile_data["dynamic_baselines"]
        current_spends = self._mock_leakage_spends(dynamic_baselines) 
        
        leakage_buckets: List[Dict[str, Any]] = []
        total_leakage = Decimal("0.00")
        
        # --- 1. Calculate Leakage for SCALED Categories (VE & SD) ---
        for category, threshold in dynamic_baselines.items():
            
            spend = current_spends.get(category, Decimal("0.00"))
            
            # Leak: Max(0, Actual Spend - Leakage Threshold)
            leak_amount = max(Decimal("0.00"), spend - threshold)
            
            if leak_amount > Decimal("0.00"):
                total_leakage += leak_amount
                
                # Build the Leakage Bucket View structure
                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(), 
                    "baseline_threshold": threshold.quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": "Above Scaled Threshold",
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": f"{(leak_amount / spend) * 100:.2f}%" if spend > Decimal("0.00") else "0.00%"
                })
        
        # --- 2. Calculate Leakage for PURE DISCRETIONARY (PD) Categories ---
        # NOTE: We need a definitive list of PD categories from the DB in a real system.
        pd_categories = ["Pure_Discretionary_DiningOut", "Pure_Discretionary_Gadget"]
        
        for category in pd_categories:
            spend = current_spends.get(category, Decimal("0.00"))
            
            if spend > Decimal("0.00"):
                # 100% of this spend is a leak if not covered by a Smart Rule
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


        # --- 3. Add the Guaranteed Leak (15% of DMB) ---
        # This is the 'Potential Recoverable Fund' used to fuel the Autopilot immediately.
        guaranteed_fund = dynamic_baselines.get("Potential_Recoverable_Fund", Decimal("0.00"))
        
        total_leakage += guaranteed_fund
        
        leakage_buckets.append({
            "category": "Guaranteed Savings Fund",
            "baseline_threshold": dynamic_baselines.get("Total_Minimal_Need_DMB").quantize(Decimal("0.01")),
            "spend": dynamic_baselines.get("Total_Leakage_Threshold").quantize(Decimal("0.01")),
            "leak_source": "DMB - 15% Margin",
            "leak_amount": guaranteed_fund.quantize(Decimal("0.01")),
            "leak_percentage_of_spend": "15.00%" # Since it's 15% of DMB
        })
        
        # 4. Build reclaimable salary projection logic
        projected_reclaimable_salary = total_leakage
        
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "leakage_buckets": leakage_buckets
        }
