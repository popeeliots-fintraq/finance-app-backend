# services/insight_service.py (ASYNC INTEGRATED VERSION)

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from datetime import date, datetime

# 🌟 FIX: Import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession 

# Assuming you have a User model, though primary data is passed via arguments
# NOTE: The User model import path is speculative, replace with your actual path if different
# from ..db.base import User # Removed, as it's not strictly needed here

class InsightService:
    """
    Service class responsible for generating actionable, proactive insights 
    (Leak Cards) based on real-time leakage calculation data.
    """

    # 🌟 FIX: Change DB type hint to AsyncSession
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        # Define categories that trigger high-priority behavioral nudges
        self.HIGH_PRIORITY_CATEGORIES = ["Pure_Discretionary_DiningOut", "Pure_Discretionary_Subscription"] 
        self.DMB_BREACH_THRESHOLD = Decimal("0.30") # 30% above DMB triggers a strong warning

    def create_insight_card(self, priority: str, title: str, body: str, call_to_action: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to structure the insight card consistently."""
        return {
            "priority": priority,
            "title": title,
            "body": body,
            "call_to_action": call_to_action,
            "context_data": context_data,
            "generated_at": datetime.utcnow().isoformat()
        }

    # 🌟 FIX: Make the function async for consistency, though it has no await calls
    async def generate_proactive_leak_insights(self, reporting_period: date, category_leaks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyzes the detailed leakage buckets and generates specific, actionable insight cards.
        """
        insights = []
        
        # 1. Calculate the overall projected reclaimable salary
        reclaimable_salary = Decimal("0.00")
        for bucket in category_leaks:
             reclaimable_salary += bucket.get('leak_amount', Decimal("0.00"))


        # 2. Iterate through each leakage bucket to generate category-specific insights
        for bucket in category_leaks:
            category = bucket.get('category')
            # Ensure Decimal conversion from possible string/float input from the caller
            leak_amount = Decimal(str(bucket.get('leak_amount', "0.00"))).quantize(Decimal("0.01"))
            baseline = Decimal(str(bucket.get('baseline_threshold', "0.00")))
            sds_class = bucket.get('sds_weight_class')
            spend = Decimal(str(bucket.get('spend', "0.00")))

            if leak_amount <= Decimal("100.00"): # Ignore trivial leaks
                continue

            # --- INSIGHT TYPE A: HIGH-IMPACT DISCRETIONARY LEAK (Highest priority nudge) ---
            if category in self.HIGH_PRIORITY_CATEGORIES:
                insights.append(self.create_insight_card(
                    priority="HIGH",
                    title=f"🚨 **{category.replace('Pure_Discretionary_', '')} Leak Alert**",
                    body=f"You've already spent **₹{spend.quantize(Decimal('0.01'))}** in this discretionary area, resulting in a **₹{leak_amount}** leak. This entire amount is immediately available for your goals!",
                    call_to_action="REDIRECT TO GOAL",
                    context_data={"source_category": category, "leak_value": leak_amount}
                ))

            # --- INSIGHT TYPE B: VARIABLE ESSENTIAL (VE) DMB BREACH WARNING ---
            elif sds_class in ["Variable_Essential"] and baseline > Decimal("0.00"):
                percentage_over_baseline = leak_amount / baseline  
                
                if percentage_over_baseline >= self.DMB_BREACH_THRESHOLD:
                    insights.append(self.create_insight_card(
                        priority="MEDIUM",
                        title=f"⚠️ **{category} DMB Breach!**",
                        body=f"Your essential variable spend exceeded the EFS-Scaled target by **{int(percentage_over_baseline * 100)}%**. This is a potential pattern leak.",
                        call_to_action="VIEW ANALYTICS",
                        context_data={"source_category": category, "baseline_breach": percentage_over_baseline}
                    ))

            # --- INSIGHT TYPE C: TAX OPTIMIZATION OPPORTUNITY (Salary Maximizer) ---
            elif category == "Tax Optimization Headroom (Annual)":
                insights.append(self.create_insight_card(
                    priority="CRITICAL",
                    title="💰 **Tax Saving Headroom Available**",
                    body=f"You have **₹{leak_amount}** of tax-saving capacity remaining this fiscal year. This is the #1 priority for your reclaimed salary!",
                    call_to_action="VIEW TAX PLAN",
                    context_data={"source_category": category, "tax_headroom": leak_amount}
                ))

        # 3. Add the overall conversion/goal suggestion (highest visibility card)
        if reclaimable_salary >= Decimal("1000.00"):
             insights.append(self.create_insight_card(
                priority="TOP_ACTION", # Custom high priority to ensure it's first
                title="✨ **Salary Autopilot Fund Ready**",
                body=f"Your total projected reclaimable salary this month is **₹{reclaimable_salary.quantize(Decimal('0.01'))}**. Tap to execute the tax-optimized goal transfer plan.",
                call_to_action="EXECUTE AUTOPILOT PLAN",
                context_data={"total_reclaimable": reclaimable_salary}
            ))
        
        # 4. Fallback if no specific issues are detected
        if not insights:
             insights.append(self.create_insight_card(
                priority="LOW",
                title="✅ **Financial Flow Achieved**",
                body="You are currently within your Dynamic Minimal Baseline (EFS-Scaled targets). Maintain this effortless flow!",
                call_to_action="VIEW DMB STATUS",
                context_data={"status": "IN_FLOW"}
            ))

        # Sort the insights for presentation (e.g., Top Action first, then Critical, High, Medium, Low)
        priority_map = {"TOP_ACTION": 0, "CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
        return sorted(insights, key=lambda x: priority_map.get(x['priority'], 99))
