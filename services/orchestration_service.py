# services/orchestration_service.py

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date, datetime
from sqlalchemy.exc import NoResultFound
from fastapi import HTTPException, status
from sqlalchemy import func

# 🚨 CRITICAL FIX: Import the Scaling Logic for DMB calculation
# Assuming the actual file name is scaling_logic, otherwise update this.
from ..ml.scaling_logic import calculate_dynamic_baseline

# New Import for Leakage Service (Required for real-time orchestration)
from .leakage_service import LeakageService # <--- ADDED

# Import the models needed
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, SmartTransferRule, Transaction
from ..db.enums import TransactionType, RuleType # Assuming RuleType is an enum in db.enums
from ..ml.efs_calculator import calculate_equivalent_family_size


class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    It handles EFS/DMB calculation, manages the reclaimable salary fund,
    and generates goal/stash suggestions based on Smart Rules.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    # ----------------------------------------------------------------------
    # V2 ML LOGIC INTEGRATION (EFS + Dynamic Baseline Calculation)
    # ----------------------------------------------------------------------
    def calculate_and_save_financial_profile(self) -> FinancialProfile:
        """
        Calculates the EFS, then uses the EFS and income to calculate the Dynamic
        Minimal Baseline (DMB) and Leakage Thresholds for Stratified Dependent Scaling.
        This runs as a part of the daily or monthly batch job.
        """

        # 1. Fetch User Data
        user = self.db.query(User).filter(User.id == self.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User ID {self.user_id} not found."
            )

        # 2. Fetch or Create Financial Profile
        profile = self.db.query(FinancialProfile).filter(FinancialProfile.user_id == self.user_id).first()
        if not profile:
            profile = FinancialProfile(user_id=self.user_id)
            self.db.add(profile)
            self.db.flush()

        # 3. Calculate EFS
        profile_data = {
            'num_adults': user.num_adults or 0,
            'num_dependents_under_6': user.num_dependents_under_6 or 0,
            'num_dependents_6_to_17': user.num_dependents_6_to_17 or 0,
            'num_dependents_over_18': user.num_dependents_over_18 or 0,
        }
        new_efs_value = calculate_equivalent_family_size(profile_data)

        # 4. Calculate Dynamic Baselines (Leakage Thresholds)
        net_income = user.monthly_salary or Decimal("0.00")

        # NOTE: benchmark_efficiency_factor is currently passed as None as per original code.
        baseline_results = calculate_dynamic_baseline(
            net_income=net_income,
            equivalent_family_size=new_efs_value,
            city_tier=user.city_tier,
            income_slab=user.income_slab,
            benchmark_efficiency_factor=None 
        )

        # 5. Persist all calculated results
        profile.e_family_size = new_efs_value

        leakage_threshold = baseline_results.get("Total_Leakage_Threshold", Decimal("0.00"))
        profile.essential_target = leakage_threshold

        if net_income > Decimal("0.00"):
            profile.baseline_adjustment_factor = (leakage_threshold / net_income).quantize(Decimal("0.0001"))
        else:
            profile.baseline_adjustment_factor = Decimal("0.00")

        profile.last_calculated_at = datetime.utcnow()

        self.db.commit()
        return profile
    
    # ----------------------------------------------------------------------
    # REAL-TIME POST-TRANSACTION ORCHESTRATION (Autopilot Trigger)
    # ----------------------------------------------------------------------

    def recalculate_current_period_leakage(self, reporting_period: date) -> Decimal:
        """
        Triggers the LeakageService to calculate the current MTD leak and update
        the SalaryAllocationProfile's variable spend and reclaimable salary.
        Called immediately after a new transaction is processed.
        """
        leakage_service = LeakageService(self.db, self.user_id)
        
        # This call handles the leakage calculation and persistence
        leakage_data = leakage_service.calculate_leakage(reporting_period)
        
        projected_reclaimable = leakage_data.get('projected_reclaimable_salary', Decimal("0.00"))
        
        # Immediately attempt to convert the new reclaimable amount to a goal/stash
        self.convert_leak_to_goal_if_possible(projected_reclaimable, reporting_period)

        return projected_reclaimable

    def convert_leak_to_goal_if_possible(self, projected_reclaimable: Decimal, reporting_period: date):
        """
        Implements the 'If Leak Fixed → New Salary' engine.
        Converts the identified reclaimable salary into an automatic transfer 
        to the user's highest priority goal or tax commitment.
        """
        # Minimum threshold for triggering Autopilot conversion action (e.g., ₹200)
        AUTOPILOT_THRESHOLD = Decimal("200.00") 
        
        if projected_reclaimable < AUTOPILOT_THRESHOLD: 
            return # Skip if leak is too small (noise)

        # Fetch the Salary Profile to see how much has already been converted MTD
        salary_profile = self._fetch_available_reclaimable_salary(reporting_period)
        
        # Calculate the net newly recovered amount available for immediate transfer
        # This is a simplification; a full model would track the difference since the last conversion.
        available_for_conversion = projected_reclaimable - (salary_profile.total_autotransferred or Decimal("0.00"))

        if available_for_conversion <= Decimal("50.00"): # Check against a smaller noise threshold
             return

        # 1. Find the highest priority active goal/stash that is not fully funded MTD
        top_rule = self.db.query(SmartTransferRule).filter(
            SmartTransferRule.user_id == self.user_id,
            SmartTransferRule.is_active == True,
            # Filter for goals that aren't yet fully funded for the month (amount_allocated_mtd < target_amount_monthly)
            SmartTransferRule.amount_allocated_mtd < SmartTransferRule.target_amount_monthly
        ).order_by(SmartTransferRule.priority.desc()).first()

        if not top_rule:
            return # No active goals to convert the leak to

        # 2. Calculate the conversion amount
        monthly_gap = top_rule.target_amount_monthly - (top_rule.amount_allocated_mtd or Decimal("0.00"))
        
        # The amount to convert is the MIN of the newly recovered money AND the goal's monthly gap
        conversion_amount = min(available_for_conversion, monthly_gap)

        if conversion_amount > Decimal("0.00"):
            # 3. Perform Allocation (Update MTD allocation on the rule)
            top_rule.amount_allocated_mtd += conversion_amount
            salary_profile.total_autotransferred = (salary_profile.total_autotransferred or Decimal("0.00")) + conversion_amount
            
            # 4. Record the Internal Financial Transaction (A critical audit log for the Autopilot action)
            new_transaction = Transaction(
                user_id=self.user_id,
                transaction_date=datetime.utcnow().date(),
                amount=conversion_amount,
                description=f"Autopilot Real-time Stash: Fund {top_rule.name}",
                category='Autopilot Stash', # Internal category
                transaction_type=TransactionType.DEBIT_INTERNAL, 
                smart_rule_id=top_rule.id
            )
            self.db.add(new_transaction)
            
            # 5. Commit changes
            self.db.commit()
            
            # NOTE: An external notification/insight card would be generated here: 
            # "Autopilot Stashed ₹X from your recovered leak into your Y goal."
    
    # ----------------------------------------------------------------------
    # CORE ORCHESTRATION LOGIC (GUIDED EXECUTION)
    # ----------------------------------------------------------------------

    def _fetch_available_reclaimable_salary(self, reporting_period: date) -> SalaryAllocationProfile:
        """Fetches the latest calculated salary profile for the period."""

        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        if not salary_profile:
            # Return a default profile if none exists for the period
            return SalaryAllocationProfile(
                projected_reclaimable_salary=Decimal("0.00")
            )

        return salary_profile


    def generate_consent_suggestion_plan(self, reporting_period: date) -> Dict[str, Any]:
        """
        Calculates how the reclaimable fund SHOULD be allocated across active Smart Rules,
        prioritizing Tax Saving rules up to the user's remaining tax headroom.
        """
        salary_profile = self._fetch_available_reclaimable_salary(reporting_period)
        user = self.db.query(User).filter(User.id == self.user_id).first()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User ID {self.user_id} not found.")

        # Use the money that is NOT yet auto-transferred for the batch suggestion plan
        available_fund = salary_profile.projected_reclaimable_salary - (salary_profile.total_autotransferred or Decimal("0.00"))
        remaining_fund = available_fund
        suggestion_plan: List[Dict[str, Any]] = []
        total_suggested = Decimal("0.00")
        
        if available_fund <= Decimal("500.00"):
            return {
                "available_fund": available_fund.quantize(Decimal("0.01")),
                "total_suggested": Decimal("0.00"),
                "suggestion_plan": [],
                "message": "Reclaimable salary below action threshold. Autopilot on standby."
            }

        # 1. Fetch all active Smart Rules, separated by type
        active_rules = self.db.query(SmartTransferRule).filter(
            SmartTransferRule.user_id == self.user_id,
            SmartTransferRule.is_active == True
        ).order_by(SmartTransferRule.priority.desc()).all()
        
        # Assuming RuleType is an enum with values 'Tax Saving' and others
        tax_rules = [r for r in active_rules if r.rule_type == RuleType.TAX_SAVING.value]
        other_rules = [r for r in active_rules if r.rule_type != RuleType.TAX_SAVING.value]
        
        # Get the user's current remaining tax headroom
        remaining_tax_headroom = user.tax_headroom_remaining or Decimal("0.00")
        
        # 2. --- PRIORITY ALLOCATION: TAX SAVING ---
        for rule in tax_rules:
            if remaining_fund <= Decimal("0.00"):
                break
                
            # Max amount to transfer: The MIN of (Rule Target, Remaining Fund, Remaining Tax Headroom)
            transfer_target = min(rule.target_amount_monthly, remaining_fund, remaining_tax_headroom)
            
            if transfer_target > Decimal("0.00"):
                suggestion_plan.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "transfer_amount": transfer_target.quantize(Decimal("0.01")),
                    "destination": rule.destination_account_name,
                    "type": rule.rule_type 
                })
                
                remaining_fund -= transfer_target
                remaining_tax_headroom -= transfer_target
                total_suggested += transfer_target

        # 3. --- SECONDARY ALLOCATION: OTHER GOALS/STASHES ---
        for rule in other_rules:
            if remaining_fund <= Decimal("0.00"):
                break
                
            transfer_amount = min(rule.target_amount_monthly, remaining_fund)
            
            if transfer_amount > Decimal("0.00"):
                suggestion_plan.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "transfer_amount": transfer_amount.quantize(Decimal("0.01")),
                    "destination": rule.destination_account_name,
                    "type": rule.rule_type 
                })
                
                remaining_fund -= transfer_amount
                total_suggested += transfer_amount

        # 4. Finalize and return the plan
        return {
            "available_fund": available_fund.quantize(Decimal("0.01")),
            "remaining_unallocated": remaining_fund.quantize(Decimal("0.01")),
            "total_suggested": total_suggested.quantize(Decimal("0.01")),
            "suggestion_plan": suggestion_plan,
            "message": f"Autopilot suggests reallocating {total_suggested.quantize(Decimal('0.01'))} across goals, prioritizing tax optimization."
        }
        
    # ----------------------------------------------------------------------
    # AUTOPILOT EXECUTION METHOD (CLOSES THE LOOP & HANDLES CONSENT)
    # ----------------------------------------------------------------------
    def record_consent_and_update_balance(self, transfer_plan: List[Dict[str, Any]], reporting_period: date) -> Dict[str, Any]:
        """
        Executes the final Autopilot action: records the user's consent,
        logs the transfer transactions, and updates the Salary Allocation Profile.
        """
        if not transfer_plan:
            return {"status": "success", "message": "No transfers to execute."}

        # 1. Fetch the relevant Salary Profile
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        if not salary_profile:
            raise NoResultFound("Cannot execute Autopilot: Salary Allocation Profile not found for the period.")

        total_transferred = Decimal("0.00")
        executed_transfers = []

        # 2. Iterate through the consented plan and execute/record
        for item in transfer_plan:
            # Handle float/string conversion from API input
            transfer_amount = item.get("transfer_amount", Decimal("0.00"))
            if isinstance(transfer_amount, (float, str)):
                transfer_amount = Decimal(str(transfer_amount)).quantize(Decimal("0.01"))
            
            rule_id = item.get("rule_id")
            
            if transfer_amount <= Decimal("0.00"):
                continue

            # --- A. (External System Mock) Execute UPI Transfer ---
            transfer_successful = True # Assume success for MVP
            
            if transfer_successful:
                # --- B. Record the Internal Financial Transaction ---
                new_transaction = Transaction(
                    user_id=self.user_id,
                    transaction_date=datetime.utcnow().date(),
                    amount=transfer_amount,
                    description=f"Autopilot Transfer: Fund {item.get('rule_name', 'Goal')}",
                    category=item.get('type', 'Autopilot Stash'), # e.g., 'Goal', 'Tax Saving'
                    transaction_type=TransactionType.DEBIT_INTERNAL, # Internal debit type
                    smart_rule_id=rule_id
                )
                self.db.add(new_transaction)
                
                total_transferred += transfer_amount
                executed_transfers.append(item)

        # 3. Update the Salary Profile (Closing the Loop)
        # Note: We decrease the reclaimable salary fund by the amount transferred.
        salary_profile.projected_reclaimable_salary -= total_transferred
        salary_profile.total_autotransferred = (salary_profile.total_autotransferred or Decimal("0.00")) + total_transferred
        
        # 4. Commit all changes to the database
        self.db.commit()

        # 5. Return Success Message
        return {
            "status": "success",
            "message": "Autopilot execution complete. Your funds have been efficiently allocated.",
            "total_transferred": total_transferred.quantize(Decimal("0.01")),
            "transfers_executed": executed_transfers
        }
