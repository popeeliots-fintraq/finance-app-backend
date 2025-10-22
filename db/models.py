# db/models.py - Corrected and ready to paste

from sqlalchemy import Column, Integer, String, DECIMAL, Date, ForeignKey, PrimaryKeyConstraint
from decimal import Decimal
from .base import Base 

class SalaryAllocationProfile(Base):
    """
    SQLAlchemy ORM Model for the 'salary_allocation_profile' table.
    Tracks the user's monthly income and allocation targets (Fin-Traq V2).
    """

    __tablename__ = "salary_allocation_profile"

    # FIX: Changed to Integer and ForeignKey now points to 'users.id' to match db/base.py
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    reporting_period = Column(Date, nullable=False)
    net_monthly_income = Column(DECIMAL(10, 2), nullable=False)
    fixed_commitment_total = Column(DECIMAL(10, 2), nullable=False)
    target_savings_rate = Column(DECIMAL(5, 2), nullable=False, default=Decimal("0.00"))

    projected_discretionary_float = Column(DECIMAL(10, 2), nullable=False)
    
    # 🚨 V2 ADDITION 1: Leak Finder Output (Money found and available for suggestion)
    projected_reclaimable_salary = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    
    # 🚨 V2 ADDITION 2: Guided Orchestration Output (Money user has consented to 'move' internally)
    consented_move_amount = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))

    __table_args__ = (
        PrimaryKeyConstraint('user_id', 'reporting_period', name='pk_salary_allocation'),
    )
