# services/orchestration_service.py (FINAL INTEGRATED VERSION)

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date, datetime
from sqlalchemy.exc import NoResultFound
from fastapi import HTTPException, status
from sqlalchemy import func

# --- V2 Service Imports ---
from .leakage_service import LeakageService  
from .insight_service import InsightService
# 🚨 NEW CRITICAL IMPORT: Use the integrated service for ML steps
from .financial_profile_service import FinancialProfileService

# Import the models needed
from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, SmartTransferRule, Transaction
from ..db.enums import TransactionType, RuleType 


class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    It handles EFS/DMB calculation, manages the reclaimable salary fund,
    and generates goal/stash suggestions based on Smart Rules.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        # Initialize the Financial Profile Service for ML tasks
        self.financial_profile_service = FinancialProfileService(db, user_id) 

    # ----------------------------------------------------------------------
    # V2 ML LOGIC INTEGRATION (EFS + Dynamic Baseline Calculation)
    # ----------------------------------------------------------------------
    def calculate_and_save_financial_profile(self) -> FinancialProfile:
        """
        Delegates the EFS/BEF/DMB calculation to the FinancialProfileService.
        This runs as a part of the daily or monthly batch job.
        
        FORTIFICATION: This ensures the DMB logic (SDS/EFS/BEF) is executed
        in the correct sequence and is persisted before the LeakageService runs.
        """
        
        # NOTE: The FinancialProfileService handles all persistence (EFS, BEF, DMB)
        return self.financial_profile_service.calculate_and_save_dmb()
        
    # ----------------------------------------------------------------------
    # REAL-TIME POST-TRANSACTION ORCHESTRATION (Autopilot Trigger)
    # ----------------------------------------------------------------------

    def recalculate_current_period_leakage(self, reporting_period: date) -> Dict[str, Any]:
        """
        Triggers the LeakageService to calculate the current MTD leak,
        and then generates proactive insights based on the new spending status.
        """
        leakage_service = LeakageService(self.db, self.user_id)
        
        # 1. Calculate Leakage and persist reclaimable fund
        leakage_data = leakage_service.calculate_leakage(reporting_period) 
        
        projected_reclaimable = leakage_data.get('projected_reclaimable_salary', Decimal("0.00"))
        leakage_buckets = leakage_data.get('leakage_buckets')
        
        # 2. --- GENERATE PROACTIVE INSIGHTS (BEHAVIORAL ML) ---
        insight_service = InsightService(self.db, self.user_id)
        
        proactive_insights = insight_service.generate_proactive_leak_insights(
            reporting_period,
            category_leaks=leakage_buckets # Pass the detailed bucket data
        )
        
        return {
            "projected_reclaimable": projected_reclaimable,
            "insights": proactive_insights,
            "leakage_buckets": leakage_buckets 
        }

    # NOTE: convert_leak_to_goal_if_possible is retained but disabled for Phase 2.
    def convert_leak_to_goal_if_possible(self, projected_reclaimable: Decimal, reporting_period: date):
        """
        ***NOTE: THIS METHOD IS NOW DEPRECATED/DISABLED FOR PHASE 2 (GUIDED EXECUTION).***
        It is retained for Phase 3 (Full Autonomous Maximizer).
        """
        return 

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
             # Return a profile with default zero values if none exists for the period
             return SalaryAllocationProfile(
                 projected_reclaimable_salary=Decimal("0.00"),
                 total_autotransferred=Decimal("0.00")
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
                "remaining_unallocated": available_fund.quantize(Decimal("0.01")),
                "message": "Reclaimable salary below action threshold. Autopilot on standby."
            }

        # 1. Fetch all active Smart Rules, separated by type
        active_rules = self.db.query(SmartTransferRule).filter(
            SmartTransferRule.user_id == self.user_id,
            SmartTransferRule.is_active == True
        ).order_by(SmartTransferRule.priority.desc()).all()
        
        # Separate rules based on RuleType enum
        tax_rules = [r for r in active_rules if r.rule_type == RuleType.TAX_SAVING.value]
        other_rules = [r for r in active_rules if r.rule_type != RuleType.TAX_SAVING.value]
        
        # Get the user's current remaining tax headroom
        remaining_tax_headroom = salary_profile.tax_headroom_remaining or Decimal("0.00")
        
        # 2. --- PRIORITY ALLOCATION: TAX SAVING ---
        for rule in tax_rules:
            if remaining_fund <= Decimal("0.00"):
                break
                
            # NOTE: Logic assumes target_amount_monthly is the target *remaining* to be funded this month
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
                
            # NOTE: Logic assumes target_amount_monthly is the target *remaining* to be funded this month
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
            return {"status": "success", "message": "No transfers to execute.", "total_transferred": Decimal("0.00"), "transfers_executed": []}

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
                # --- B. Record the Internal Financial Transaction (Gap #3 Fortification) ---
                new_transaction = Transaction(
                    user_id=self.user_id,
                    transaction_date=datetime.utcnow().date(),
                    amount=transfer_amount,
                    description=f"Autopilot Transfer: Fund {item.get('rule_name', 'Goal')}",
                    category=item.get('type', 'Autopilot Stash'), 
                    transaction_type=TransactionType.DEBIT_INTERNAL, 
                    smart_rule_id=rule_id,
                    # NEW AUDIT FIELD
                    salary_profile_id=salary_profile.id 
                )
                self.db.add(new_transaction)
                
                total_transferred += transfer_amount
                executed_transfers.append(item)

        # 3. Update the Salary Profile (Closing the Loop)
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
