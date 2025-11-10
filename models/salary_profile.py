# models/salary_profile.py

from typing import List, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, DECIMAL, Date, ForeignKey, JSON
from datetime import date
from decimal import Decimal

from ..db.base import Base

# CRITICAL FIX: Import the related User model
from .user_profile import User 

class SalaryAllocationProfile(Base):
    __tablename__ = "salary_allocation_profiles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reporting_period: Mapped[date] = mapped_column(Date) # The month being analyzed
    
    # --- Income & Fixed Commitments (Inputs) ---
    net_monthly_income: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    fixed_commitment_total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    
    # --- Leakage Bucket View (Outputs) ---
    # Stores the structure: [{"category": "...", "leak_amount": "...", "baseline_threshold": "..."}, ...]
    # This is the "Salary & Leak Buckets" structure you specified.
    leakage_buckets: Mapped[List[Dict[str, Any]]] = mapped_column(JSON) 
    
    # --- Leakage Summary (Core KPIs) ---
    # The total amount recovered/reclaimable this month
    total_leakage_amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    
    # Total variable spend (for BEF calculation reference)
    variable_spend_total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00")) 

    # Relationships
    user: Mapped["User"] = relationship(back_populates="salary_profiles")
