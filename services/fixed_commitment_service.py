from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta

# Import models
from ..db.base import User # Used for context if needed
from ..db.models import SalaryAllocationProfile
# 🚨 NOTE: Assuming you have a Transaction model for historical data analysis
from ..db.models import Transaction 

# --- SERVICE CONSTANTS ---
LOOKBACK_MONTHS = 4  # Analyze the last 4 months to establish a pattern
FIXED_COMMITMENT_CATEGORIES = [
    "Rent/Mortgage EMI",
    "Loan Repayment",
    "Insurance Premium",
    "Subscriptions & Dues (Annualized)",
    "Utilities (Fixed Component)" 
]
# Threshold for a commitment to be considered 'Fixed' (e.g., must occur at least 2 out of LOOKBACK_MONTHS)
OCCURRENCE_THRESHOLD = 0.5 

class FixedCommitmentService:
    """
    Service responsible for calculating and projecting the user's stable, 
    non-negotiable monthly fixed expenses.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def _get_fixed_transactions(self, end_date: date) -> List[Transaction]:
        """
        Retrieves all transactions categorized as fixed commitments within the lookback window.
        """
        start_date = end_date - timedelta(days=30 * LOOKBACK_MONTHS)

        # 🚨 NOTE: This query requires 'Transaction' model to have a 'category' and 'date' field.
        transactions = self.db.query(Transaction).filter(
            Transaction.user_id == self.user_id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
            Transaction.category.in_(FIXED_COMMITMENT_CATEGORIES)
        ).all()
        
        return transactions

    def calculate_fixed_total(self, reporting_period: date) -> Decimal:
        """
        Analyzes historical fixed spending and projects the monthly total.

        Returns:
            Decimal: The projected total fixed commitment amount.
        """
        
        # 1. Fetch relevant transactions
        fixed_transactions = self._get_fixed_transactions(reporting_period)

        if not fixed_transactions:
            return Decimal("0.00")

        # 2. Group transactions by category and normalize to a monthly amount
        category_spending: Dict[str, List[Decimal]] = {}
        
        for tx in fixed_transactions:
            if tx.category not in category_spending:
                category_spending[tx.category] = []
            category_spending[tx.category].append(tx.amount)

        projected_total = Decimal("0.00")
        
        # 3. Project Monthly Amount per Category
        for category, amounts in category_spending.items():
            
            # Count the number of unique months in which this category had a transaction
            unique_months = len(set(tx.transaction_date.replace(day=1) for tx in fixed_transactions if tx.category == category))
            
            # Check for fixed recurrence (e.g., 2/4 months or 1/4 for large annual payments)
            if unique_months < LOOKBACK_MONTHS * OCCURRENCE_THRESHOLD:
                # If the transaction is too sporadic, we skip it or categorize it differently
                # For Fin-Traq V2, we assume anything in FIXED_COMMITMENT_CATEGORIES is critical.
                pass 
            
            # Calculate the total spend in this category over the lookback period
            total_spend = sum(amounts)
            
            # Normalize the total spend to a monthly average over the lookback period
            monthly_average = total_spend / LOOKBACK_MONTHS
            
            # Add to the running total
            projected_total += monthly_average

        # Round the final result
        return projected_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def orchestrate_update(self, reporting_period: date) -> Decimal:
        """
        Calculates the fixed total and updates the SalaryAllocationProfile.
        This is the method called by the main Orchestration Service.
        """
        
        # 1. Calculate the fixed total
        calculated_fixed_total = self.calculate_fixed_total(reporting_period)
        
        # 2. Fetch or create the SalaryAllocationProfile for the month
        salary_profile = self.db.query(SalaryAllocationProfile).filter(
            SalaryAllocationProfile.user_id == self.user_id,
            SalaryAllocationProfile.reporting_period == reporting_period
        ).first()

        if not salary_profile:
            # 🚨 FAILURE PREVENTION: If profile doesn't exist, create a minimal one.
            # Assuming you have a service to get the latest net income (or fetch it from User model)
            user_info = self.db.query(User).filter(User.id == self.user_id).one() 

            salary_profile = SalaryAllocationProfile(
                user_id=self.user_id,
                reporting_period=reporting_period,
                net_monthly_income=user_info.monthly_salary,
                # Other defaults will kick in
            )
            self.db.add(salary_profile)

        # 3. Update the CRITICAL FIELD and commit
        salary_profile.fixed_commitment_total = calculated_fixed_total
        self.db.commit()
        
        return calculated_fixed_total
