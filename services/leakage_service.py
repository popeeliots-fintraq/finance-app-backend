# services/leakage_service.py

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from datetime import date, timedelta
from sqlalchemy import func, and_

# CRITICAL FIX: Update imports to reflect the file structure
from ..ml.scaling_logic import calculate_dynamic_baseline 
# 🚨 NEW IMPORT: Benchmarking Service (Assuming it exists)
from .benchmarking_service import BenchmarkingService 

# Import models
# NOTE: Assuming these imports are correct based on your previous messages
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, Transaction
from ..db.enums import TransactionType 

# --- SERVICE CONSTANTS ---
# NOTE: Assuming this constant is defined elsewhere or imported, using a sensible default for the service
LOOKBACK_MONTHS = 4 
# Assuming FIXED_COMMITMENT_CATEGORIES is either imported or defined here (pulling the definition from fixed_commitment_service)
FIXED_COMMITMENT_CATEGORIES = [
    "Rent/Mortgage EMI",
    "Loan Repayment",
    "Insurance Premium",
    "Subscriptions & Dues (Annualized)",
    "Utilities (Fixed Component)" 
]
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

    # ----------------------------------------------------------------------
    # CORE V2 DMB CALCULATION HELPERS
    # ----------------------------------------------------------------------
    
    def _calculate_user_historical_spend(self, reporting_period: date) -> Dict[str, Decimal]:
        """
        Retrieves and aggregates the median monthly spend for discretionary categories 
        from the historical transactions.
        """
        # Uses the lookback period from the Fixed Commitment logic
        start_date = reporting_period - timedelta(days=30 * LOOKBACK_MONTHS) 

        # Query all non-fixed transactions in the lookback period
        variable_transactions = self.db.query(Transaction).filter(
            Transaction.user_id == self.user_id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date < reporting_period,
            # Exclude Fixed Commitments that were handled separately
            ~Transaction.category.in_(FIXED_COMMITMENT_CATEGORIES),
            Transaction.transaction_type == TransactionType.DEBIT # Focus on spends
        ).all()

        # Group by month and category
        monthly_category_spends: Dict[str, Dict[date, Decimal]] = {}
        
        for tx in variable_transactions:
            month_start = tx.transaction_date.replace(day=1)
            if tx.category not in monthly_category_spends:
                monthly_category_spends[tx.category] = {}
            
            # Calculate monthly total per category
            monthly_category_spends[tx.category][month_start] = (
                monthly_category_spends[tx.category].get(month_start, Decimal("0.00")) + tx.amount
            )
        
        # Calculate the median of the monthly totals for each category
        historical_median_spends: Dict[str, Decimal] = {}
        
        for category, monthly_data in monthly_category_spends.items():
            if not monthly_data:
                continue
                
            # Median is more robust than average against single-month spikes
            monthly_totals = sorted(list(monthly_data.values()))
            n = len(monthly_totals)
            
            # Calculate median
            if n % 2 == 1:
                median = monthly_totals[n // 2]
            else:
                median = (monthly_totals[n // 2 - 1] + monthly_totals[n // 2]) / Decimal("2.00")
                
            historical_median_spends[category] = median.quantize(Decimal("0.01"))
            
        return historical_median_spends

    def calculate_final_dmb_with_history(
        self,
        reporting_period: date,
        dynamic_baselines: Dict[str, Decimal] # The EFS-scaled thresholds from ML
    ) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        """
        Applies the MAX(EFS-Threshold, User Median Spend) logic to finalize the DMB.
        This sets the true DMB against which current month leakage is compared.
        
        Returns:
            Tuple[Dict[str, Decimal], Dict[str, Decimal]]: 
            (final_category_dmb, historical_median_spends)
        """
        
        # 1. Get the user's historical spend metrics
        historical_median_spends = self._calculate_user_historical_spend(reporting_period)
        final_category_dmb: Dict[str, Decimal] = {}
        
        # 2. --- DMB Calculation: MAX(EFS Floor, User Median) ---
        for category, efs_threshold in dynamic_baselines.items():
            # Exclude non-spending metrics from the MAX logic
            if category in ["Total_Leakage_Threshold", "Total_Minimal_Need_DMB", "Potential_Recoverable_Fund"]:
                final_category_dmb[category] = efs_threshold 
                continue
                
            # Fetch the user's historical median for this category
            user_median = historical_median_spends.get(category, Decimal("0.00"))
            
            # Core DMB Logic: Set the DMB to the higher of the two values.
            # EFS-Threshold is the non-negotiable floor; User Median is the ceiling for soft budgeting.
            category_dmb = max(efs_threshold, user_median)
            
            final_category_dmb[category] = category_dmb.quantize(Decimal("0.01"))

        return final_category_dmb, historical_median_spends


    # ----------------------------------------------------------------------
    # ORCHESTRATION & PERSISTENCE
    # ----------------------------------------------------------------------
    
    def _fetch_profile_data_and_baselines(self, reporting_period: date) -> Dict[str, Any]:
        """
        Fetches required user financial data and calculates EFS-Scaled DMB/Thresholds.
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
                fixed_commitment_total=Decimal("0.00"), # Needs calculation by FixedCommitmentService
            )
            self.db.add(salary_profile)
            self.db.flush() 

        # 3. Fetch the Financial Profile (which now holds EFS)
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()

        if not profile or not profile.e_family_size:
            raise NoResultFound("Financial Profile or Equivalent Family Size not found. Run OrchestrationService first to calculate EFS.")
        
        # 4. Calculate Benchmarking Factor using the new service (Batch Process)
        # NOTE: BenchmarkingService.calculate_efficiency_factor should ideally use a cached result here.
        benchmarking_service = BenchmarkingService(self.db, self.user_id)
        benchmark_factor = benchmarking_service.calculate_efficiency_factor(
            current_efs=profile.e_family_size,
            current_fixed_total=salary_profile.fixed_commitment_total,
            city_tier=user_info.city_tier, 
            net_income=salary_profile.net_monthly_income
        )

        # 5. Calculate EFS-Scaled Baselines (ML Output)
        baseline_results = calculate_dynamic_baseline(
            net_income=salary_profile.net_monthly_income,
            equivalent_family_size=profile.e_family_size,
            city_tier=user_info.city_tier,
            income_slab=user_info.income_slab, # Assuming this is correctly fetched
            benchmark_efficiency_factor=benchmark_factor # Factor is None if cohort is too small
        )

        return {
            "net_monthly_income": salary_profile.net_monthly_income,
            "dynamic_baselines": baseline_results, # EFS-Scaled Thresholds
            "efs": profile.e_family_size,
            "salary_profile": salary_profile 
        }

    def _get_current_month_spends(self, reporting_period: date) -> Dict[str, Decimal]:
        """
        CRITICAL: Retrieves the month-to-date (MTD) variable spend, categorized.
        This replaces the _mock_leakage_spends function.
        """
        # Calculate start and end of the reporting period (current month)
        start_date = reporting_period
        end_date = reporting_period.replace(day=1) + timedelta(days=32)
        end_date = end_date.replace(day=1) - timedelta(days=1)
        
        # Query MTD variable spending
        mtd_spends_query = self.db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total_spend")
        ).filter(
            Transaction.user_id == self.user_id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= date.today(), # Only up to today's date
            ~Transaction.category.in_(FIXED_COMMITMENT_CATEGORIES),
            Transaction.transaction_type == TransactionType.DEBIT
        ).group_by(Transaction.category).all()
        
        # Format results into a dictionary
        mtd_spends: Dict[str, Decimal] = {
            row.category: Decimal(row.total_spend).quantize(Decimal("0.01"))
            for row in mtd_spends_query
        }
        
        # Add mock PD categories that might not be in the query if no spend occurred
        mtd_spends["Pure_Discretionary_DiningOut"] = mtd_spends.get("Pure_Discretionary_DiningOut", Decimal("0.00"))
        mtd_spends["Pure_Discretionary_Gadget"] = mtd_spends.get("Pure_Discretionary_Gadget", Decimal("0.00"))
        
        return mtd_spends

    def calculate_leakage(self, reporting_period: date) -> Dict[str, Any]:
        """
        Calculates leakage amount using the refined MAX(EFS-Threshold, User Median) DMB.
        """

        try:
            profile_data = self._fetch_profile_data_and_baselines(reporting_period)
        except NoResultFound as e:
            raise Exception(f"Failed to initialize Leakage Service: {e}")

        # 1. Finalize DMB using EFS-Threshold (Floor) and User Median (Ceiling)
        efs_thresholds = profile_data["dynamic_baselines"]
        
        # final_dmb contains the actual baseline for each category (MAX logic applied)
        final_dmb, historical_median_spends = self.calculate_final_dmb_with_history(
            reporting_period, efs_thresholds
        )

        # 2. Get the current month's actual spend data
        current_spends = self._get_current_month_spends(reporting_period) # Replaces mock spends

        leakage_buckets: List[Dict[str, Any]] = []
        total_leakage = Decimal("0.00")

        # --- 3. Calculate Leakage for SCALED Categories (VE & SD) ---
        for category, dmb_threshold in final_dmb.items():

            if category in ["Total_Leakage_Threshold", "Total_Minimal_Need_DMB", "Potential_Recoverable_Fund"]:
                continue

            spend = current_spends.get(category, Decimal("0.00"))
            
            # Leak: Max(0, Actual Spend - Final DMB)
            leak_amount = max(Decimal("0.00"), spend - dmb_threshold)

            if spend > Decimal("0.00"):
                if leak_amount > Decimal("0.00"):
                    total_leakage += leak_amount
                    leak_source_description = "Above Dynamic Minimal Baseline"
                else:
                    leak_source_description = "Within Baseline (Achieving Flow)"

                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(),
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
                total_leakage += leak_amount

                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(),
                    "baseline_threshold": Decimal("0.00").quantize(Decimal("0.01")), # Always zero for PD
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": "100% Discretionary Spend (Goal Opportunity)",
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": "100.00%"
                })

        # 5. Apply GMB Guardrail to Total Leakage
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
        salary_profile.variable_spend_total = sum(current_spends.values()) # Store total variable spend for reconciliation
        self.db.commit()

        # 6. Return the calculated data for immediate display
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "leakage_buckets": leakage_buckets
        }
