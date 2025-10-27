# services/leakage_service.py

from decimal import Decimal
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from datetime import date

# CRITICAL FIX: Update imports to reflect the file structure
from ..ml.scaling_logic import calculate_dynamic_baseline 
# 🚨 NEW IMPORT: Benchmarking Service
from .benchmarking_service import BenchmarkingService 

# Import models
# 🚨 NOTE: Assuming User model now contains city_tier and income_slab
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile

# 🚨 DEFINITION: Absolute floor for essential spending to prevent below-par living
GLOBAL_MINIMAL_BASELINE_FLOOR = Decimal("15000.00") # Placeholder for the absolute GMB

class LeakageService:
    """
    Core service class for calculating financial leakage based on the
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def _fetch_profile_data_and_baselines(self, reporting_period: date) -> Dict[str, Any]:
        """
        Fetches required user financial data and calculates DMB/Thresholds.
        CRITICAL FIX: Creates a SalaryAllocationProfile if one does not exist for the period
        and fetches all data needed for benchmarking.
        """
        
        # 1. Fetch or Create the Salary Allocation Profile (to get Net Income)
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        # 2. Fetch User data (needed for income_slab and city_tier)
        user_info = self.db.query(User).filter(User.id == self.user_id).first()
        if not user_info:
            raise NoResultFound(f"User ID {self.user_id} not found.")

        if not salary_profile:
            # 🚨 FAILURE PREVENTION: If profile is missing, create a new one.
            salary_profile = SalaryAllocationProfile(
                user_id=self.user_id,
                reporting_period=reporting_period,
                net_monthly_income=user_info.monthly_salary,
                fixed_commitment_total=Decimal("0.00"), # Placeholder/Needs calculation
            )
            self.db.add(salary_profile)
            self.db.flush() 

        # 3. Fetch the Financial Profile (which now holds EFS)
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()

        if not profile or not profile.e_family_size:
            raise NoResultFound("Financial Profile or Equivalent Family Size not found. Run OrchestrationService first to calculate EFS.")
        
        # 4. Calculate Benchmarking Factor using the new service
        benchmarking_service = BenchmarkingService(self.db, self.user_id)
        
        # 🚨 NEW LOGIC: Attempt to find the best user benchmark
        benchmark_factor = benchmarking_service.calculate_efficiency_factor(
            current_efs=profile.e_family_size,
            current_fixed_total=salary_profile.fixed_commitment_total,
            city_tier=user_info.city_tier, 
            net_income=salary_profile.net_monthly_income
        )

        # 5. Recalculate Baselines using the latest EFS and all factors
        # The benchmark_efficiency_factor is passed to trigger the Best User logic or the default fallback.
        baseline_results = calculate_dynamic_baseline(
            net_income=salary_profile.net_monthly_income,
            equivalent_family_size=profile.e_family_size,
            city_tier=user_info.city_tier,
            income_slab=user_info.income_slab, # Assuming this is correctly fetched
            benchmark_efficiency_factor=benchmark_factor # Factor is None if cohort is too small
        )

        return {
            "net_monthly_income": salary_profile.net_monthly_income,
            "dynamic_baselines": baseline_results,
            "efs": profile.e_family_size,
            "salary_profile": salary_profile 
        }

    def _mock_leakage_spends(self, baselines: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """
        MOCK DATA: Simulates categorized spends. (Keep this as is for now)
        """
        mock_spends = {
            # --- VE Leak Buckets (Spending > Threshold is Leak) ---
            "Variable_Essential_Food": baselines.get("Variable_Essential_Food", Decimal("0.00")) * Decimal("1.30"),
            "Variable_Essential_Transport": baselines.get("Variable_Essential_Transport", Decimal("0.00")) * Decimal("0.80"),
            "Variable_Essential_Health": baselines.get("Variable_Essential_Health", Decimal("0.00")) * Decimal("1.05"),

            # --- SD Leak Bucket (High Leakage items with a tight cap) ---
            "Scaled_Discretionary_Routine": baselines.get("Scaled_Discretionary_Routine", Decimal("0.00")) * Decimal("2.50"),

            # --- PD Leak Bucket (100% is a leak until Smart Rule is attached) ---
            "Pure_Discretionary_DiningOut": Decimal("3500.00"),
            "Pure_Discretionary_Gadget": Decimal("500.00"),
        }
        return mock_spends

    def calculate_leakage(self, reporting_period: date) -> Dict[str, Any]:
        """
        Calculates leakage amount using the refined Stratified Dependent Scaling (SDS) baseline.
        Implements the three-bucket leak calculation for the 'Leakage Bucket View,'
        and PERSISTS the projected reclaimable salary to the DB.
        """

        # Ensure we are inside a transaction or can commit at the end
        try:
            profile_data = self._fetch_profile_data_and_baselines(reporting_period)
        except NoResultFound as e:
            raise Exception(f"Failed to initialize Leakage Service: {e}")

        dynamic_baselines = profile_data["dynamic_baselines"]
        current_spends = self._mock_leakage_spends(dynamic_baselines)

        leakage_buckets: List[Dict[str, Any]] = []
        total_leakage = Decimal("0.00")

        # --- 1. Calculate Leakage for SCALED Categories (VE & SD) ---
        for category, threshold in dynamic_baselines.items():

            if category in ["Total_Leakage_Threshold", "Total_Minimal_Need_DMB", "Potential_Recoverable_Fund"]:
                continue

            spend = current_spends.get(category, Decimal("0.00"))
            
            # Leak: Max(0, Actual Spend - Leakage Threshold)
            leak_amount = max(Decimal("0.00"), spend - threshold)

            if spend > Decimal("0.00"):
                if leak_amount > Decimal("0.00"):
                    total_leakage += leak_amount
                    leak_source_description = "Above Scaled Threshold"
                else:
                    leak_source_description = "Within Scaled Threshold (Savings)"

                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(),
                    "baseline_threshold": threshold.quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": leak_source_description,
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": f"{(leak_amount / spend) * 100:.2f}%" if spend > Decimal("0.00") else "0.00%"
                })

        # --- 2. Calculate Leakage for PURE DISCRETIONARY (PD) Categories ---
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

        # 3. Apply GMB Guardrail to Total Leakage
        # We ensure the result doesn't push the effective *remaining* salary too low.
        net_income = profile_data["salary_profile"].net_monthly_income
        fixed_commitments = profile_data["salary_profile"].fixed_commitment_total
        
        # Total necessary fixed + GMB floor
        absolute_floor = fixed_commitments + GLOBAL_MINIMAL_BASELINE_FLOOR
        
        # Max Leakage is Net Income minus Absolute Floor
        max_possible_leakage = max(Decimal("0.00"), net_income - absolute_floor)
        
        # The projected reclaimable salary cannot exceed this maximum possible leakage
        projected_reclaimable_salary = min(total_leakage, max_possible_leakage)


        # 🚨 CRITICAL STEP: PERSIST THE LEAKAGE RESULT TO THE DB
        salary_profile = profile_data["salary_profile"]
        salary_profile.projected_reclaimable_salary = projected_reclaimable_salary
        
        # Ensure the entire block (fetch/create/update) is committed as one unit.
        self.db.commit()

        # 4. Return the calculated data for immediate display
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "leakage_buckets": leakage_buckets
        }
