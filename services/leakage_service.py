# services/leakage_service.py

from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from ..utils.ml_logic import

# Import models and logic
from ..db.models import SalaryAllocationProfile
from ..db.user_profile import UserProfile
from ..services.ml_service import calculate_dynamic_minimal_baseline


class LeakageService:
    """
    Core service class for calculating financial leakage based on the 
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        
    def _fetch_profile_data(self) -> Dict[str, Any]:
        """Fetches required user financial data and EFS."""
        
        # 1. Fetch the latest Salary Allocation Profile (to get Net Income)
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id
        ).order_by(SalaryAllocationProfile.reporting_period.desc()).first()

        if not salary_profile:
            raise ValueError("Salary Allocation Profile not found. Cannot calculate leaks.")

        # 2. Fetch the User Profile (to get EFS)
        user_profile = self.db.query(UserProfile).filter(
            UserProfile.user_id == self.user_id
        ).first()
        
        # Default EFS to 1.00 if profile is missing (single person household)
        equivalent_family_size = user_profile.equivalent_family_size if user_profile else Decimal("1.00")
        
        return {
            "net_monthly_income": salary_profile.net_monthly_income,
            "equivalent_family_size": equivalent_family_size
        }
        
    def _mock_leakage_spends(self, dynamic_baselines: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """
        MOCK DATA: Simulates categorized spends from UPI/SMS integration. [cite: 2025-10-15]
        
        In the real system, this data would come from categorized transactions 
        stored in the DB (categorized spends). [cite: 2025-10-15]
        
        This mock data intentionally shows leakage (overspending) in two categories.
        """
        # Actual spending for the Variable Essential categories
        # Note: 'Variable_Essential_Food' baseline is overspent.
        # Note: 'Variable_Essential_Health' baseline is slightly overspent.
        
        mock_spends = {
            "Variable_Essential_Food": dynamic_baselines.get("Variable_Essential_Food", Decimal(0)) * Decimal("1.25"), # 25% over baseline
            "Variable_Essential_Transport": dynamic_baselines.get("Variable_Essential_Transport", Decimal(0)) * Decimal("0.90"), # 10% under baseline
            "Variable_Essential_Health": dynamic_baselines.get("Variable_Essential_Health", Decimal(0)) * Decimal("1.10"), # 10% over baseline
        }
        return mock_spends


    def calculate_leakage(self) -> Dict[str, Any]:
        """
        Calculates leakage amount from categorized spends, replacing the old 
        expense dashboard task with the 'Leakage Bucket View.' [cite: 2025-10-15]
        """
        
        profile_data = self._fetch_profile_data()
        net_income = profile_data["net_monthly_income"]
        efs = profile_data["equivalent_family_size"]
        
        # 1. Calculate the Dynamic Minimal Baseline for all variable essential categories
        dynamic_baselines = calculate_dynamic_baseline(net_income, efs)
        
        # 2. Get categorized spends (MOCK for now)
        current_spends = self._mock_leakage_spends(dynamic_baselines)
        
        leakage_buckets: List[Dict[str, Any]] = []
        total_leakage = Decimal("0.00")
        
        # 3. Calculate Leakage: Leak = Max(0, Spend - Baseline)
        for category, baseline in dynamic_baselines.items():
            if category == "Total_Dynamic_Baseline":
                continue
            
            spend = current_spends.get(category, Decimal("0.00"))
            
            # The definition of Fin-Traq "Leak": any spend amount above the 
            # dynamically adjusted minimal baseline for that category. [cite: 2025-10-17]
            leak_amount = max(Decimal("0.00"), spend - baseline)
            
            if leak_amount > Decimal("0.00"):
                total_leakage += leak_amount
                
                # Build the Leakage Bucket View structure [cite: 2025-10-15]
                leakage_buckets.append({
                    "category": category,
                    "baseline": baseline.quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage": f"{(leak_amount / baseline) * 100:.2f}%" if baseline > Decimal("0.00") else "N/A"
                })

        # 4. Build reclaimable salary projection logic [cite: 2025-10-15]
        # In this first version, the reclaimed amount equals the calculated leakage.
        projected_reclaimable_salary = total_leakage
        
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "leakage_buckets": leakage_buckets
        }
