from sqlalchemy import Column, Integer, String, DECIMAL, Date, ForeignKey, PrimaryKeyConstraint, UniqueConstraint
from decimal import Decimal
from .base import Base 
# Note: Ensure 'Base' is imported correctly from your relative path

class SalaryAllocationProfile(Base):
    """
    SQLAlchemy ORM Model for the 'salary_allocation_profile' table.
    Tracks the user's monthly income and allocation targets (Fin-Traq V2).
    """

    __tablename__ = "salary_allocation_profile"

    # Best Practice: Dedicated auto-incrementing Primary Key
    id = Column(Integer, primary_key=True, index=True) 

    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    reporting_period = Column(Date, nullable=False)
    net_monthly_income = Column(DECIMAL(10, 2), nullable=False)
    fixed_commitment_total = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    target_savings_rate = Column(DECIMAL(5, 2), nullable=False, default=Decimal("0.00"))

    projected_discretionary_float = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    
    # CRITICAL ADDITION: Variable Spend Total (Benchmarking/Reconciliation)
    variable_spend_total = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00")) 

    # V2 ADDITION 1: Leak Finder Output
    projected_reclaimable_salary = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    
    # V2 ADDITION 2: Guided Orchestration Output
    consented_move_amount = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))

    # 🚨 V2 ADDITION 3: TAX LEAKAGE HEADROOM (New Field)
    # This is the Tax Leak amount (Max Potential - Committed Tax Savings)
    tax_headroom_remaining = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00")) 

    __table_args__ = (
        # Ensures a user only has one profile per reporting period
        UniqueConstraint('user_id', 'reporting_period', name='uc_user_period_allocation'),
    )
