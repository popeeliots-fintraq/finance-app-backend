# services/leakage_service.py (Optimized V2 Integration)

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from datetime import date, timedelta, datetime 
from sqlalchemy import func, and_

# --- CRITICAL V2 ML/DB IMPORTS (KEEPING YOUR EXISTING LOGIC) ---
# NOTE: Keeping your existing imports for the more complex ML calculation
from ..ml.scaling_logic import calculate_dynamic_baseline 
from .benchmarking_service import BenchmarkingService # Benchmarking is critical for robust ML

# Import models
from ..db.base import User, FinancialProfile
# Assumed path/name for models
from ..db.models import SalaryAllocationProfile, Transaction, SmartTransferRule, TaxCommitment 
from ..db.enums import TransactionType

# --- SERVICE CONSTANTS ---
LOOKBACK_MONTHS = 4
FIXED_COMMITMENT_CATEGORIES = [
    "Rent/Mortgage EMI",
    "Loan Repayment",
    "Insurance Premium",
    "Subscriptions & Dues (Annualized)",
    "Utilities (Fixed Component)"
]
GLOBAL_MINIMAL_BASELINE_FLOOR = Decimal("15000.00") # Placeholder for the absolute GMB

# --- V2 TAX LEAK CONSTANTS ---
ANNUAL_MAX_TAX_SAVING_LIMIT = Decimal("150000.00") 
REPORTING_YEAR_START_MONTH = 4 # Example: April 1st for a financial year

# --- V2 CATEGORY MAPPING (NEW: To explicitly map categories to SDS classes) ---
# This is required to populate the 'sds_weight_class' field in the LeakageBucket schema.
SDS_CLASS_MAPPING = {
    "Groceries": "Variable_Essential",
    "Transportation": "Variable_Essential",
    "Health": "Variable_Essential",
    "Pure_Discretionary_DiningOut": "Discretionary",
    "Pure_Discretionary_Gadget": "Discretionary",
    "Tax Optimization Headroom (Annual)": "Tax_Commitment",
    # Add other categories as necessary
}


class LeakageService:
    """
    Core service class for calculating financial leakage based on the
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    # ----------------------------------------------------------------------
    # HISTORICAL & DMB CALCULATION HELPERS (UNCHANGED/ASSUMED)
    # ----------------------------------------------------------------------
    
    # ... (Keep your _calculate_user_historical_spend function) ...
    # ... (Keep your calculate_final_dmb_with_history function) ...
    # ... (Keep your _get_current_month_spends function) ...
    
    # NOTE: These functions are kept as you provided them, as they perform 
    # the necessary aggregation and the MAX(EFS-Threshold, User Median Spend) logic.

    # ----------------------------------------------------------------------
    # V2 TAX LEAK IDENTIFICATION (UNCHANGED)
    # ----------------------------------------------------------------------

    def _calculate_tax_headroom_leak(self, current_period_profile: SalaryAllocationProfile) -> Decimal:
        # ... (Keep existing logic) ...
        current_date = date.today()
        
        if current_date.month >= REPORTING_YEAR_START_MONTH:
            fiscal_year_start = date(current_date.year, REPORTING_YEAR_START_MONTH, 1)
        else:
            fiscal_year_start = date(current_date.year - 1, REPORTING_YEAR_START_MONTH, 1)

        current_month_index = (current_date.month - REPORTING_YEAR_START_MONTH) % 12
        months_passed = current_month_index + 1
        
        ytd_committed_tax_spend = self.db.query(func.sum(TaxCommitment.amount)).filter(
            TaxCommitment.user_id == self.user_id,
            and_(
                TaxCommitment.commitment_date >= fiscal_year_start,
                TaxCommitment.commitment_date < current_date
            )
        ).scalar() or Decimal("0.00")
        
        if ytd_committed_tax_spend == Decimal("0.00"):
             ytd_committed_tax_spend = current_period_profile.fixed_commitment_total * Decimal(months_passed)
        
        tax_headroom = ANNUAL_MAX_TAX_SAVING_LIMIT - ytd_committed_tax_spend
        tax_leak = max(Decimal("0.00"), tax_headroom)
        
        current_period_profile.tax_headroom_remaining = tax_leak.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return tax_leak

    # ----------------------------------------------------------------------
    # ORCHESTRATION & PERSISTENCE (V2 EFS INTEGRATION)
    # ----------------------------------------------------------------------
    
    def _fetch_profile_data_and_baselines(self, reporting_period: date) -> Dict[str, Any]:
        """
        Fetches required user financial data and calculates EFS-Scaled DMB/Thresholds
        using the dedicated ML/Scaling logic.
        """
        
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        user_info = self.db.query(User).filter(User.id == self.user_id).first()
        if not user_info:
            raise NoResultFound(f"User ID {self.user_id} not found.")

        # CRITICAL V2: FinancialProfile must contain the calculated EFS from OrchestrationService
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()

        if not profile or not profile.e_family_size:
             # This is a critical failure point. In production, OrchestrationService must run first.
             raise NoResultFound("Equivalent Family Size (EFS) not found. Cannot run DMB calculation.")
        
        # --- 1. Get EFS and Benchmarking Factor ---
        efs_value = profile.e_family_size

        # Benchmarking Service is crucial for SDS weighting and is kept
        benchmarking_service = BenchmarkingService(self.db, self.user_id)
        benchmark_factor = benchmarking_service.calculate_efficiency_factor(
            current_efs=efs_value,
            current_fixed_total=salary_profile.fixed_commitment_total,
            city_tier=user_info.city_tier,
            net_income=salary_profile.net_monthly_income
        )

        # --- 2. Call Complex ML Scaling Logic ---
        baseline_results = calculate_dynamic_baseline(
            net_income=salary_profile.net_monthly_income,
            equivalent_family_size=efs_value, # Explicitly using EFS here
            city_tier=user_info.city_tier,
            income_slab=user_info.income_slab, 
            benchmark_efficiency_factor=benchmark_factor
        )

        return {
            "net_monthly_income": salary_profile.net_monthly_income,
            "dynamic_baselines": baseline_results, 
            "efs": efs_value,
            "salary_profile": salary_profile
        }

    
    def calculate_leakage(self, reporting_period: date) -> Dict[str, Any]:
        """
        Calculates leakage amount, includes Tax Leak, and persists the reclaimable salary fund.
        """

        try:
            profile_data = self._fetch_profile_data_and_baselines(reporting_period)
        except NoResultFound as e:
            raise Exception(f"Failed to initialize Leakage Service: {e}")
        except Exception as e:
            raise Exception(f"Failed to initialize Leakage Service: {e}")

        salary_profile = profile_data["salary_profile"]

        # 1. Calculate Tax Leak (Priority 1 Leak)
        tax_leak_amount = self._calculate_tax_headroom_leak(salary_profile)

        # 2. Calculate Variable Spending Leakage
        efs_thresholds = profile_data["dynamic_baselines"]
        final_dmb, _ = self.calculate_final_dmb_with_history(
            reporting_period, efs_thresholds
        )

        current_spends = self._get_current_month_spends(reporting_period)

        variable_leakage = Decimal("0.00")
        leakage_buckets: List[Dict[str, Any]] = []

        # --- 3. Calculate Leakage for SCALED Categories (VE & SD) ---
        for category, dmb_threshold in final_dmb.items():

            if category in ["Total_Leakage_Threshold", "Total_Minimal_Need_DMB", "Potential_Recoverable_Fund"]:
                continue

            spend = current_spends.get(category, Decimal("0.00"))
            leak_amount = max(Decimal("0.00"), spend - dmb_threshold)
            
            # CRITICAL V2: Determine SDS Class for schema output
            sds_class = SDS_CLASS_MAPPING.get(category, "Undefined_Category")
            
            if spend > Decimal("0.00"):
                if leak_amount > Decimal("0.00"):
                    variable_leakage += leak_amount
                    leak_source_description = "Above Dynamic Minimal Baseline"
                else:
                    leak_source_description = "Within Baseline (Achieving Flow)"

                leakage_buckets.append({
                    "category": category, 
                    "sds_weight_class": sds_class, # Added V2 field
                    "baseline_threshold": dmb_threshold.quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": leak_source_description,
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": f"{(leak_amount / spend) * 100:.2f}%" if spend > Decimal("0.00") else "0.00%"
                })

        # --- 4. Calculate Leakage for PURE DISCRETIONARY (PD) Categories ---
        pd_categories = ["Pure_Discretionary_DiningOut", "Pure_Discretionary_Gadget"]

        for category in pd_categories:
            spend = current_spends.get(category, Decimal("0.00"))

            if spend > Decimal("0.00"):
                leak_amount = spend
                variable_leakage += leak_amount

                leakage_buckets.append({
                    "category": category, 
                    "sds_weight_class": "Discretionary", # Explicitly set
                    "baseline_threshold": Decimal("0.00").quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": "100% Discretionary Spend (Goal Opportunity)",
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": "100.00%"
                })

        # --- 5. Final Total Leakage (Variable Leak + Tax Leak) ---
        total_leakage = variable_leakage + tax_leak_amount

        # 6. Apply GMB Guardrail to Total Leakage (UNCHANGED)
        net_income = profile_data["salary_profile"].net_monthly_income
        fixed_commitments = profile_data["salary_profile"].fixed_commitment_total
        
        absolute_floor = fixed_commitments + GLOBAL_MINIMAL_BASELINE_FLOOR
        max_possible_leakage = max(Decimal("0.00"), net_income - absolute_floor)
        projected_reclaimable_salary = min(total_leakage, max_possible_leakage)

        # 7. Add Tax Leak to Buckets for Display
        if tax_leak_amount > Decimal("0.00"):
            leakage_buckets.append({
                "category": "Tax Optimization Headroom (Annual)", 
                "sds_weight_class": "Tax_Commitment", # Explicitly set
                "baseline_threshold": ANNUAL_MAX_TAX_SAVING_LIMIT, 
                "spend": ANNUAL_MAX_TAX_SAVING_LIMIT - tax_leak_amount, 
                "leak_source": "Unused Tax Capacity (Salary Maximizer)",
                "leak_amount": tax_leak_amount.quantize(Decimal("0.01")), 
                "leak_percentage_of_spend": f"{tax_leak_amount / ANNUAL_MAX_TAX_SAVING_LIMIT * 100:.2f}%"
            })


        # 8. CRITICAL STEP: PERSIST THE LEAKAGE RESULT TO THE DB (UNCHANGED)
        salary_profile.projected_reclaimable_salary = projected_reclaimable_salary
        salary_profile.variable_spend_total = sum(current_spends.values()) 
        self.db.commit()

        # 9. Return the calculated data (UNCHANGED)
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "tax_headroom_remaining": salary_profile.tax_headroom_remaining,
            "leakage_buckets": leakage_buckets
        }

    # ----------------------------------------------------------------------
    # BEHAVIORAL ML INSIGHT CARDS (UNCHANGED)
    # ----------------------------------------------------------------------
    # ... (Keep get_leakage_insights function as provided) ...
