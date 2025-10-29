# services/insight_service.py

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from sqlalchemy import func

from ..db.base import User, FinancialProfile
from ..db.models import SalaryAllocationProfile, Transaction
from ..db.enums import TransactionType

# Insight thresholds (can be fine-tuned based on behavioral ML testing)
WARNING_THRESHOLD_PERCENT = Decimal("0.85") # 85% of DMB used
CRITICAL_THRESHOLD_PERCENT = Decimal("0.95") # 95% of DMB used

class InsightService:
    """
    Generates proactive behavioral insights based on DMB tracking.
    This helps STOP leaks (proactive) rather than just RECLAIMING them (reactive).
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def _get_current_spending_status(self, reporting_period: date) -> Dict[str, Decimal]:
        """
        Fetches the DMB (Essential Target) and the user's total variable spend MTD.
        """
        # 1. Get the DMB (Leakage Threshold) from the FinancialProfile
        profile = self.db.query(FinancialProfile).filter(
            FinancialProfile.user_id == self.user_id
        ).first()

        # 2. Get current period spending status
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()
        
        # Fallback if profile or DMB is missing (should not happen in production)
        if not profile or not profile.essential_target:
            return {"essential_target": Decimal("0.00"), "variable_spend_mtd": Decimal("0.00")}

        # Calculate MTD spend on DMB-eligible categories (variable spend)
        # Note: In a full system, a LeakageService function would filter non-essential variable spending
        
        # MOCK IMPLEMENTATION: Use total_variable_spend if available, or calculate it.
        # This will be replaced by accurate LeakageService aggregation.
        if salary_profile and salary_profile.total_variable_spend:
             variable_spend_mtd = salary_profile.total_variable_spend
        else:
            variable_spend_mtd = self.db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == self.user_id,
                Transaction.transaction_date >= reporting_period,
                Transaction.transaction_date < reporting_period + timedelta(days=30),
                Transaction.transaction_type == TransactionType.DEBIT,
                # Exclude fixed/saving categories
                Transaction.category.notin_(['Fixed Expense', 'Goal Transfer', 'Tax Saving']) 
            ).scalar() or Decimal("0.00")


        return {
            "essential_target": profile.essential_target,
            "variable_spend_mtd": variable_spend_mtd
        }


    def generate_proactive_leak_insights(self, reporting_period: date) -> List[Dict[str, Any]]:
        """
        Compares MTD variable spend against the DMB and generates actionable insight cards.
        """
        status_data = self._get_current_spending_status(reporting_period)
        
        essential_target = status_data["essential_target"]
        variable_spend_mtd = status_data["variable_spend_mtd"]
        
        if essential_target <= Decimal("0.00"):
            return [] # Cannot benchmark without a DMB

        # Calculate the percentage of the DMB target used
        usage_ratio = variable_spend_mtd / essential_target if essential_target > Decimal("0.00") else Decimal("0.00")
        
        insights = []

        # 1. Proactive Insight: CRITICAL THRESHOLD
        if usage_ratio >= CRITICAL_THRESHOLD_PERCENT:
            amount_over = variable_spend_mtd - essential_target
            insights.append({
                "type": "CRITICAL_LEAK_WARNING",
                "title": "🚨 Imminent Leak Alert",
                "body": f"Your **variable spending** is {amount_over.quantize(Decimal('0.01'))} above your maximum healthy baseline. A leak is confirmed. **Tap to check impact.**",
                "action": "VIEW_LEAK_IMPACT", # Actionable hook for the app
                "priority": 1
            })

        # 2. Proactive Insight: WARNING THRESHOLD
        elif usage_ratio >= WARNING_THRESHOLD_PERCENT:
            amount_remaining = essential_target - variable_spend_mtd
            insights.append({
                "type": "BEHAVIORAL_NUDGE",
                "title": "⚠️ Behavioral Nudge: Check spending",
                "body": f"You've used **{int(usage_ratio * 100)}%** of your monthly variable pool. You only have {amount_remaining.quantize(Decimal('0.01'))} remaining before impacting your goals.",
                "action": "VIEW_REMAINING_POOL",
                "priority": 2
            })
            
        # 3. Proactive Insight: RECLAIMED FUNDS SUMMARY (This is the "Leak Fixed" message)
        # Note: This is an important reactive insight derived from the OrchestrationService
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()
        
        if salary_profile and salary_profile.projected_reclaimable_salary > Decimal("500.00"):
             insights.append({
                "type": "RECLAIMED_FUNDS_SUMMARY",
                "title": "💰 Salary Autopilot Success",
                "body": f"We've recovered **{salary_profile.projected_reclaimable_salary.quantize(Decimal('0.01'))}** this month by fixing recurring leak patterns. **Tap to allocate/save this amount.**",
                "action": "VIEW_SUGGESTION_PLAN",
                "priority": 0 # Highest priority, as it leads to an action/goal
            })


        return sorted(insights, key=lambda x: x['priority'])
