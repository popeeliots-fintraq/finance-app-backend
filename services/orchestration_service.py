# services/orchestration_service.py

from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date

# Import models
from ..db.models import SalaryAllocationProfile, SmartTransferRule

class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    Calculates the final automated transfer plan based on available reclaimable 
    salary and user-defined Smart Rules [cite: 2025-10-15].
    """

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id
        
    def _fetch_available_reclaimable_salary(self, reporting_period: date) -> Decimal:
        """Fetches the latest calculated reclaimable salary for the period."""
        
        # Get the profile that contains the money recovered from leakage calculation
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        if not salary_profile:
            # If no salary profile exists, there is no reclaimable money to allocate.
            return Decimal("0.00") 
        
        # This is the money recovered from stopping leaks and is available for automation
        return salary_profile.projected_reclaimable_salary


    def calculate_automated_transfer_plan(self, reporting_period: date) -> Dict[str, Any]:
        """
        Calculates how the projected_reclaimable_salary should be distributed 
        across active Smart Rules (Goals, Tax Savings, etc.) [cite: 2025-10-15].
        """
        
        available_fund = self._fetch_available_reclaimable_salary(reporting_period)
        
        # If no reclaimable salary is projected, the plan is empty.
        if available_fund <= Decimal("0.00"):
             return {
                "available_fund": Decimal("0.00"),
                "total_allocated": Decimal("0.00"),
                "transfer_plan": [],
                "message": "No reclaimable salary projected. Autopilot is on standby."
            }

        # 1. Fetch all active Smart Rules for the user (ordered by priority/creation date)
        active_rules = self.db.query(SmartTransferRule).filter(
            SmartTransferRule.user_id == self.user_id,
            SmartTransferRule.is_active == True
        ).all()
        
        transfer_plan: List[Dict[str, Any]] = []
        remaining_fund = available_fund
        total_allocated = Decimal("0.00")

        # 2. Allocate funds based on rules (Guided execution logic)
        for rule in active_rules:
            if remaining_fund <= Decimal("0.00"):
                break # Funds exhausted

            # Allocation amount is either the rule's fixed target OR the remaining fund, whichever is less.
            # We assume SmartTransferRule.transfer_amount is the fixed monthly goal contribution.
            
            amount_to_allocate = min(remaining_fund, rule.transfer_amount)
            
            # The Autopilot converts leftover income into tax savings or goals automatically [cite: 2025-10-15]
            transfer_plan.append({
                "rule_id": rule.rule_id,
                "destination": rule.destination_instrument,
                "amount_allocated": amount_to_allocate.quantize(Decimal("0.01")),
                "type": rule.transfer_type
            })
            
            remaining_fund -= amount_to_allocate
            total_allocated += amount_to_allocate

        # 3. Finalize Plan
        return {
            "available_fund": available_fund.quantize(Decimal("0.01")),
            "total_allocated": total_allocated.quantize(Decimal("0.01")),
            "unallocated_fund": remaining_fund.quantize(Decimal("0.01")),
            "transfer_plan": transfer_plan,
            "message": "Transfer plan generated based on Smart Rules and available reclaimable salary."
        }
