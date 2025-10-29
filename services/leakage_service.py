# services/leakage_service.py

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from datetime import date, timedelta, datetime 
from sqlalchemy import func, and_

# CRITICAL FIX: Update imports to reflect the file structure
from ..ml.scaling_logic import calculate_dynamic_baseline
# 🚨 NEW IMPORT: Benchmarking Service (Assuming it exists)
from .benchmarking_service import BenchmarkingService

# Import models
from ..db.base import User, FinancialProfile
# Assumed path/name for models
from ..db.models import SalaryAllocationProfile, Transaction, SmartTransferRule, TaxCommitment # <-- Added TaxCommitment (future proofing)
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

class LeakageService:
    """
    Core service class for calculating financial leakage based on the
    Dynamic Minimal Baseline (Fin-Traq V2 Leak Finder).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    # ----------------------------------------------------------------------
    # CORE V2 DMB CALCULATION HELPERS (omitted for brevity, assume unchanged)
    # ----------------------------------------------------------------------
    
    def _calculate_user_historical_spend(self, reporting_period: date) -> Dict[str, Decimal]:
        """
        Retrieves and aggregates the median monthly spend for discretionary categories
        from the historical transactions. (omitted for brevity)
        """
        start_date = reporting_period - timedelta(days=30 * LOOKBACK_MONTHS)

        variable_transactions = self.db.query(Transaction).filter(
            Transaction.user_id == self.user_id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date < reporting_period,
            ~Transaction.category.in_(FIXED_COMMITMENT_CATEGORIES),
            Transaction.transaction_type == TransactionType.DEBIT 
        ).all()

        monthly_category_spends: Dict[str, Dict[date, Decimal]] = {}
        
        for tx in variable_transactions:
            month_start = tx.transaction_date.replace(day=1)
            if tx.category not in monthly_category_spends:
                monthly_category_spends[tx.category] = {}
            
            monthly_category_spends[tx.category][month_start] = (
                monthly_category_spends[tx.category].get(month_start, Decimal("0.00")) + tx.amount
            )
        
        historical_median_spends: Dict[str, Decimal] = {}
        
        for category, monthly_data in monthly_category_spends.items():
            if not monthly_data:
                continue
                
            monthly_totals = sorted(list(monthly_data.values()))
            n = len(monthly_totals)
            
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
        (omitted for brevity)
        """
        
        historical_median_spends = self._calculate_user_historical_spend(reporting_period)
        final_category_dmb: Dict[str, Decimal] = {}
        
        for category, efs_threshold in dynamic_baselines.items():
            if category in ["Total_Leakage_Threshold", "Total_Minimal_Need_DMB", "Potential_Recoverable_Fund"]:
                final_category_dmb[category] = efs_threshold
                continue
                
            user_median = historical_median_spends.get(category, Decimal("0.00"))
            category_dmb = max(efs_threshold, user_median)
            
            final_category_dmb[category] = category_dmb.quantize(Decimal("0.01"))

        return final_category_dmb, historical_median_spends


    # ----------------------------------------------------------------------
    # V2 TAX LEAK IDENTIFICATION (New Method for Salary Maximizer)
    # ----------------------------------------------------------------------

    def _calculate_tax_headroom_leak(self, current_period_profile: SalaryAllocationProfile) -> Decimal:
        """
        Calculates the remaining tax-saving capacity (Tax Leak) for the financial year.
        This is treated as a high-priority 'leak' to stop.
        """
        current_date = date.today()
        
        # 1. Calculate the start of the current financial year
        if current_date.month >= REPORTING_YEAR_START_MONTH:
            fiscal_year_start = date(current_date.year, REPORTING_YEAR_START_MONTH, 1)
        else:
            fiscal_year_start = date(current_date.year - 1, REPORTING_YEAR_START_MONTH, 1)

        # 2. Sum tax-related commitments/investments made this fiscal year.
        # This is the actual amount the user has *committed* to saving for tax this year.
        # Future-Proofing: Use TaxCommitment model or categorized transactions.
        
        # SIMPLIFIED MVP PROXY: Use the Fixed Commitments (as a proxy for tax/investment portion)
        # and assume it has been paid for (current_date.month - REPORTING_YEAR_START_MONTH + 1) months.
        
        current_month_index = (current_date.month - REPORTING_YEAR_START_MONTH) % 12
        months_passed = current_month_index + 1
        
        # A rough estimate of YTD tax committed (needs refinement with actual TaxCommitment model)
        ytd_committed_tax_spend = self.db.query(func.sum(TaxCommitment.amount)).filter(
            TaxCommitment.user_id == self.user_id,
            and_(
                TaxCommitment.commitment_date >= fiscal_year_start,
                TaxCommitment.commitment_date < current_date
            )
        ).scalar() or Decimal("0.00")
        
        # If no explicit TaxCommitments, fall back to a fixed * 12 projection
        if ytd_committed_tax_spend == Decimal("0.00"):
             ytd_committed_tax_spend = current_period_profile.fixed_commitment_total * Decimal(months_passed)
        
        # 3. Calculate Tax Leak (Headroom)
        tax_headroom = ANNUAL_MAX_TAX_SAVING_LIMIT - ytd_committed_tax_spend

        # The tax leak cannot be negative (it is capped at 0 if the limit is exceeded)
        tax_leak = max(Decimal("0.00"), tax_headroom)
        
        # 4. Persist the Tax Leak amount to the profile (NOTE: NOT COMMITTED HERE)
        current_period_profile.tax_headroom_remaining = tax_leak.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        return tax_leak

    # ----------------------------------------------------------------------
    # ORCHESTRATION & PERSISTENCE (Updated)
    # ----------------------------------------------------------------------
    
    def _fetch_profile_data_and_baselines(self, reporting_period: date) -> Dict[str, Any]:
        """
        Fetches required user financial data and calculates EFS-Scaled DMB/Thresholds.
        (omitted for brevity)
        """
        
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        user_info = self.db.query(User).filter(User.id == self.user_id).first()
        if not user_info:
            raise NoResultFound(f"User ID {self.user_id} not found.")

        if not salary_profile:
            salary_profile = SalaryAllocationProfile(
                user_id=self.user_id,
                reporting_period=reporting_period,
                net_monthly_income=user_info.monthly_salary,
                fixed_commitment_total=Decimal("0.00"), 
            )
            self.db.add(salary_profile)
            self.db.flush()

        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()

        if not profile or not profile.e_family_size:
            raise NoResultFound("Financial Profile or Equivalent Family Size not found. Run OrchestrationService first to calculate EFS.")
        
        benchmarking_service = BenchmarkingService(self.db, self.user_id)
        benchmark_factor = benchmarking_service.calculate_efficiency_factor(
            current_efs=profile.e_family_size,
            current_fixed_total=salary_profile.fixed_commitment_total,
            city_tier=user_info.city_tier,
            net_income=salary_profile.net_monthly_income
        )

        baseline_results = calculate_dynamic_baseline(
            net_income=salary_profile.net_monthly_income,
            equivalent_family_size=profile.e_family_size,
            city_tier=user_info.city_tier,
            income_slab=user_info.income_slab, 
            benchmark_efficiency_factor=benchmark_factor
        )

        return {
            "net_monthly_income": salary_profile.net_monthly_income,
            "dynamic_baselines": baseline_results, 
            "efs": profile.e_family_size,
            "salary_profile": salary_profile
        }

    def _get_current_month_spends(self, reporting_period: date) -> Dict[str, Decimal]:
        """
        Retrieves the month-to-date (MTD) variable spend, categorized.
        (omitted for brevity)
        """
        start_date = reporting_period
        
        mtd_spends_query = self.db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total_spend")
        ).filter(
            Transaction.user_id == self.user_id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= date.today(),
            ~Transaction.category.in_(FIXED_COMMITMENT_CATEGORIES),
            Transaction.transaction_type == TransactionType.DEBIT
        ).group_by(Transaction.category).all()
        
        mtd_spends: Dict[str, Decimal] = {
            row.category: Decimal(row.total_spend).quantize(Decimal("0.01"))
            for row in mtd_spends_query
        }
        
        mtd_spends["Pure_Discretionary_DiningOut"] = mtd_spends.get("Pure_Discretionary_DiningOut", Decimal("0.00"))
        mtd_spends["Pure_Discretionary_Gadget"] = mtd_spends.get("Pure_Discretionary_Gadget", Decimal("0.00"))
        
        return mtd_spends

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

            if spend > Decimal("0.00"):
                if leak_amount > Decimal("0.00"):
                    variable_leakage += leak_amount
                    leak_source_description = "Above Dynamic Minimal Baseline"
                else:
                    leak_source_description = "Within Baseline (Achieving Flow)"

                leakage_buckets.append({
                    "category": category, 
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
                    "baseline_threshold": Decimal("0.00").quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": "100% Discretionary Spend (Goal Opportunity)",
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": "100.00%"
                })

        # --- 5. Final Total Leakage (Variable Leak + Tax Leak) ---
        total_leakage = variable_leakage + tax_leak_amount

        # 6. Apply GMB Guardrail to Total Leakage
        net_income = profile_data["salary_profile"].net_monthly_income
        fixed_commitments = profile_data["salary_profile"].fixed_commitment_total
        
        absolute_floor = fixed_commitments + GLOBAL_MINIMAL_BASELINE_FLOOR
        max_possible_leakage = max(Decimal("0.00"), net_income - absolute_floor)
        projected_reclaimable_salary = min(total_leakage, max_possible_leakage)

        # 7. Add Tax Leak to Buckets for Display (Only if it's a positive leak/headroom)
        if tax_leak_amount > Decimal("0.00"):
            leakage_buckets.append({
                "category": "Tax Optimization Headroom (Annual)", 
                "baseline_threshold": ANNUAL_MAX_TAX_SAVING_LIMIT, 
                "spend": ANNUAL_MAX_TAX_SAVING_LIMIT - tax_leak_amount, 
                "leak_source": "Unused Tax Capacity (Salary Maximizer)",
                "leak_amount": tax_leak_amount.quantize(Decimal("0.01")), 
                "leak_percentage_of_spend": f"{tax_leak_amount / ANNUAL_MAX_TAX_SAVING_LIMIT * 100:.2f}%"
            })


        # 8. CRITICAL STEP: PERSIST THE LEAKAGE RESULT TO THE DB
        salary_profile.projected_reclaimable_salary = projected_reclaimable_salary
        salary_profile.variable_spend_total = sum(current_spends.values()) 
        # Note: tax_headroom_remaining was set in _calculate_tax_headroom_leak()
        self.db.commit()

        # 9. Return the calculated data
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "tax_headroom_remaining": salary_profile.tax_headroom_remaining, # New Field!
            "leakage_buckets": leakage_buckets
        }

    # ----------------------------------------------------------------------
    # BEHAVIORAL ML INSIGHT CARDS (Updated to include Tax Leak insight)
    # ----------------------------------------------------------------------

    def get_leakage_insights(self, reporting_period: date) -> List[Dict[str, Any]]:
        """
        Calculates leakage and transforms major leaks/headroom into actionable insight cards, 
        linking them to the user's highest priority goal/stash.
        """
        
        # 1. Get the raw leakage data (assumes calculate_leakage was run)
        try:
            leakage_data = self.calculate_leakage(reporting_period)
            leakage_buckets = leakage_data['leakage_buckets']
            tax_leak_amount = leakage_data['tax_headroom_remaining'] # Use the calculated field
        except Exception as e:
            print(f"Error during leakage calculation for insights: {e}")
            return [] 

        # 2. Get the highest priority Smart Rule (Goal/Stash)
        top_rule = self.db.query(SmartTransferRule).filter(
            SmartTransferRule.user_id == self.user_id,
            SmartTransferRule.is_active == True
        ).order_by(SmartTransferRule.priority.desc()).first()

        insight_cards = []
        
        # --- A. Tax Leak Insight (Highest Priority) ---
        if tax_leak_amount > Decimal("5000.00"): # Larger threshold for annual tax leak
            annual_leak_percent = (tax_leak_amount / ANNUAL_MAX_TAX_SAVING_LIMIT) * 100
            
            insight_cards.append({
                "headline": f"🚨 Tax Leak Alert: {annual_leak_percent:.0f}% Unused Capacity",
                "diagnostic": (
                    f"You have **₹{tax_leak_amount:,.2f}** remaining in tax-saving headroom for the year. "
                    f"This is a guaranteed leak from your maximum salary."
                ),
                "opportunity": (
                    f"Autopilot can allocate this monthly to maximize your tax refund, ensuring you keep the maximum salary."
                ),
                "action_text": "Set Tax Saving Rule",
                "linked_rule_id": None # No specific rule, directs to general Tax Rule creation
            })
            
        # --- B. Variable/Behavioral Leak Insights (Based on Goals) ---
        if top_rule and top_rule.target_amount_monthly > Decimal("0.00"):
            for bucket in leakage_buckets:
                
                # Skip the Tax Leak bucket for this goal-based comparison
                if bucket['category'] == "Tax Optimization Headroom (Annual)":
                    continue
                    
                category_key = bucket.get('category', 'Spending') 
                display_category = category_key.replace('_', ' ').title()
                leak_amount = bucket.get('leak_amount', Decimal("0.00"))
                
                if isinstance(leak_amount, str):
                    try:
                        leak_amount = Decimal(leak_amount.replace(',', ''))
                    except:
                        continue
                        
                if leak_amount > Decimal("500.00"): # Noise threshold for monthly spend
                    
                    percent_of_goal = (leak_amount / top_rule.target_amount_monthly) * 100
                    
                    card = {
                        "headline": f"💸 Behavioral Leak Alert: ₹{leak_amount:,.2f}",
                        "diagnostic": (
                            f"You spent **₹{leak_amount:,.2f}** above your baseline in **{display_category}** this month. "
                            f"This is a recurring leak pattern."
                        ),
                        "opportunity": (
                            f"This single leak could cover **{percent_of_goal:.0f}%** of your monthly **{top_rule.name}** goal, "
                            f"a high-value conversion opportunity."
                        ),
                        "action_text": "View Leak Details & Set Limit",
                        "linked_rule_id": top_rule.id 
                    }
                    insight_cards.append(card)

        return insight_cards
