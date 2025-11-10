# services/orchestration_service.py (ASYNC INTEGRATED VERSION)

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from datetime import date, datetime
from fastapi import HTTPException, status

# --- ASYNC SQL IMPORTS ---
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import NoResultFound

# --- V2 Service Imports (All must be Async-compatible) ---
from .leakage_service import LeakageService
from .insight_service import InsightService
from .financial_profile_service import FinancialProfileService
from .benchmarking_service import BenchmarkingService # Used to fetch the fallback factor

# --- V2 Model Imports ---
from ..models.salary_profile import SalaryAllocationProfile
from ..models.user_profile import User
from ..models.smart_transfer import SmartTransferRule, SmartTransferLog
# NOTE: Assuming you have an Enum definition imported (e.g., RuleType)
from ..db.enums import TransactionStatus 

UserIdType = int # Revert to integer ID for SQL primary key


class OrchestrationService:
    """
    Core service for Fin-Traq's Salary Autopilot (Guided Execution).
    Handles DMB calculation, manages the reclaimable salary fund, and generates suggestions.
    """
    # 🌟 FIX 1: Change DB type hint back to AsyncSession
    def __init__(self, db: AsyncSession, user_id: UserIdType):
        self.db = db
        self.user_id = user_id
        
        # 🌟 FIX 2: Initialize dependent services with AsyncSession
        self.financial_profile_service = FinancialProfileService(db, user_id)
        self.leakage_service = LeakageService(db, user_id)
        self.insight_service = InsightService(db, user_id)
        # Note: Benchmarking is used as a class helper below, no instance needed yet

    # ----------------------------------------------------------------------
    # V2 ML LOGIC INTEGRATION (EFS + Dynamic Baseline Calculation)
    # ----------------------------------------------------------------------
    async def calculate_and_save_financial_profile(self) -> Dict[str, Any]:
        """Delegates the EFS/BEF/DMB calculation to the FinancialProfileService."""
        # FinancialProfileService handles fetching user, calculating EFS/BEF/DMB and persistence
        return await self.financial_profile_service.calculate_and_save_dmb()
        
    # ----------------------------------------------------------------------
    # REAL-TIME POST-TRANSACTION ORCHESTRATION (Autopilot Trigger)
    # ----------------------------------------------------------------------
    async def recalculate_current_period_leakage(self, reporting_period: date) -> Dict[str, Any]:
        """
        Triggers the LeakageService to calculate the current MTD leak,
        and then generates proactive insights based on the new spending status.
        """
        
        # 1. Calculate Leakage and persist reclaimable fund
        # LeakageService handles the MTD analysis and persists the SalaryAllocationProfile
        leakage_data = await self.leakage_service.calculate_leakage(reporting_period)
        
        projected_reclaimable = leakage_data.get('projected_reclaimable_salary', Decimal("0.00"))
        leakage_buckets = leakage_data.get('leakage_buckets')
        
        # 2. --- GENERATE PROACTIVE INSIGHTS (BEHAVIORAL ML) ---
        proactive_insights = await self.insight_service.generate_proactive_leak_insights(
            reporting_period,
            category_leaks=leakage_buckets 
        )
        
        # Phase 3 stub
        # self.convert_leak_to_goal_if_possible(projected_reclaimable, reporting_period) 

        return {
            "projected_reclaimable": projected_reclaimable.quantize(Decimal("0.01")),
            "insights": proactive_insights,
            "leakage_buckets": leakage_buckets 
        }

    # ----------------------------------------------------------------------
    # CORE ORCHESTRATION LOGIC (GUIDED EXECUTION)
    # ----------------------------------------------------------------------

    async def _fetch_available_reclaimable_salary(self, reporting_period: date) -> SalaryAllocationProfile:
        """
        🌟 FIX 3: Rewritten for SQLAlchemy Async. Fetches the latest calculated salary profile.
        """
        stmt = select(SalaryAllocationProfile).where(
            and_(
                SalaryAllocationProfile.user_id == self.user_id,
                SalaryAllocationProfile.reporting_period == reporting_period
            )
        ).order_by(SalaryAllocationProfile.reporting_period.desc()).limit(1)

        result = await self.db.execute(stmt)
        # Use .scalar_one_or_none() for a single result or None
        profile = result.scalar_one_or_none()

        if profile is None:
            # For robustness, we return an empty profile object with defaults, not raise an error
            # If a proper SalaryAllocationProfile isn't found, the orchestration can't run.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Salary Allocation Profile not calculated for this period."
            )
        return profile


    async def generate_consent_suggestion_plan(self, reporting_period: date) -> Dict[str, Any]:
        """Calculates how the reclaimable fund SHOULD be allocated across active Smart Rules."""
        
        # 🌟 FIX 4: Use the async SQLAlchemy fetch function
        salary_profile = await self._fetch_available_reclaimable_salary(reporting_period)
        
        # Use the money that is NOT yet auto-transferred for the batch suggestion plan
        available_fund = salary_profile.projected_reclaimable_salary - salary_profile.total_autotransferred
        remaining_fund = available_fund
        suggestion_plan: List[Dict[str, Any]] = []
        total_suggested = Decimal("0.00")
        
        # User check (optional, but good for validation)
        user_exists_stmt = select(User).where(User.id == self.user_id)
        user_exists = await self.db.execute(user_exists_stmt)
        if user_exists.scalar_one_or_none() is None:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User ID {self.user_id} not found.")

        if available_fund <= Decimal("500.00"):
             return {
                "available_fund": available_fund.quantize(Decimal("0.01")),
                "total_suggested": Decimal("0.00"),
                "suggestion_plan": [],
                "remaining_unallocated": available_fund.quantize(Decimal("0.01")),
                "message": "Reclaimable salary below action threshold. Autopilot on standby."
             }

        # 1. Fetch all active Smart Rules, ordered by priority
        # 🌟 FIX 5: Rewritten for SQLAlchemy Async query
        rules_stmt = select(SmartTransferRule).where(
            and_(
                SmartTransferRule.user_id == self.user_id,
                SmartTransferRule.is_active == True
            )
        ).order_by(SmartTransferRule.priority.desc()) # Assuming higher number is higher priority
        
        rules_result = await self.db.execute(rules_stmt)
        active_rules: List[SmartTransferRule] = rules_result.scalars().all()
        
        # Separate rules based on destination (Tax optimization is highest priority)
        # NOTE: You'll need to define how to identify a Tax Rule (e.g., 'destination_goal' starts with 'Tax_')
        TAX_GOAL_PREFIX = 'Tax_' 
        tax_rules = [r for r in active_rules if r.destination_goal.startswith(TAX_GOAL_PREFIX)]
        other_rules = [r for r in active_rules if not r.destination_goal.startswith(TAX_GOAL_PREFIX)]
        
        # Get the user's current remaining tax headroom (Assuming this field exists on SalaryAllocationProfile)
        remaining_tax_headroom = salary_profile.tax_headroom_remaining
        
        # 2. --- PRIORITY ALLOCATION: TAX SAVING ---
        for rule in tax_rules:
            if remaining_fund <= Decimal("0.00"): break
                
            # Rule target is defined by the transfer limit or a specific goal target (adjust as needed)
            transfer_target = min(rule.max_transfer_limit, remaining_fund, remaining_tax_headroom)
            
            if transfer_target > Decimal("0.00"):
                suggestion_plan.append({
                    "rule_id": rule.id,
                    "rule_name": rule.destination_goal,
                    "transfer_amount": transfer_target.quantize(Decimal("0.01")),
                    "destination": rule.destination_goal,
                    "type": "TAX_SAVING"
                })
                
                remaining_fund -= transfer_target
                remaining_tax_headroom -= transfer_target
                total_suggested += transfer_target

        # 3. --- SECONDARY ALLOCATION: OTHER GOALS/STASHES ---
        for rule in other_rules:
            if remaining_fund <= Decimal("0.00"): break
                
            transfer_amount = min(rule.max_transfer_limit, remaining_fund)
            
            if transfer_amount > Decimal("0.00"):
                suggestion_plan.append({
                    "rule_id": rule.id,
                    "rule_name": rule.destination_goal,
                    "transfer_amount": transfer_amount.quantize(Decimal("0.01")),
                    "destination": rule.destination_goal,
                    "type": "GOAL_STASH"
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
    async def record_consent_and_update_balance(self, transfer_plan: List[Dict[str, Any]], reporting_period: date) -> Dict[str, Any]:
        """
        🌟 FIX 7: Rewritten for SQLAlchemy Async. Records consent, logs transfer transactions, 
        and updates the Salary Allocation Profile atomically using the session's transaction.
        """
        if not transfer_plan:
             return {"status": "success", "message": "No transfers to execute.", "total_transferred": Decimal("0.00"), "transfers_executed": []}

        # 1. Fetch the Salary Profile (within the transaction context)
        salary_profile = await self._fetch_available_reclaimable_salary(reporting_period)
        
        current_total_autotransferred = salary_profile.total_autotransferred
        total_transferred = Decimal("0.00")
        executed_transfers = []
        
        # 2. Iterate through the consented plan and execute/record
        for item in transfer_plan:
            transfer_amount = item.get("transfer_amount", Decimal("0.00"))
            
            # Ensure Decimal type (it should be from the plan generation, but safety check)
            if isinstance(transfer_amount, (float, str)):
                transfer_amount = Decimal(str(transfer_amount)).quantize(Decimal("0.01"))
                
            if transfer_amount <= Decimal("0.00"): continue
                
            # --- A. (External System Mock) Execute UPI Transfer (This is the external call) ---
            transfer_successful = True # Mock success for backend logic testing
            
            if transfer_successful:
                # --- B. Record the Internal Financial Transaction/Log ---
                # Record the Smart Transfer Log
                log = SmartTransferLog(
                    rule_id=item.get('rule_id'),
                    user_id=self.user_id,
                    amount_transferred=transfer_amount,
                    execution_status="COMPLETED"
                )
                self.db.add(log)

                total_transferred += transfer_amount
                executed_transfers.append(item)

        # 3. Update the Salary Profile (Closing the Loop)
        salary_profile.total_autotransferred = current_total_autotransferred + total_transferred
        
        # 4. Commit all changes (Salary Profile update and Transfer Logs) atomically
        await self.db.commit()
        
        # 5. Return Success Message
        return {
            "status": "success",
            "message": "Autopilot execution complete. Your funds have been efficiently allocated.",
            "total_transferred": total_transferred.quantize(Decimal("0.01")),
            "transfers_executed": executed_transfers
        }
