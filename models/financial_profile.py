# models/financial_profile.py (FINAL, FIXED)

from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, DECIMAL, DateTime, ForeignKey
from datetime import datetime
from decimal import Decimal

from ..db.base import Base

# CRITICAL FIX: Import related model for relationship type hinting
from .user_profile import User # <--- FIX

class FinancialProfile(Base):
    __tablename__ = "financial_profiles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    
    # --- ML Outputs ---
    
    # Stratified Dependent Scaling (SDS) / EFS
    e_family_size: Mapped[Decimal] = mapped_column(DECIMAL(4, 2), default=Decimal("1.00"))
    
    # Benchmark Efficiency Factor (BEF)
    benchmark_efficiency_factor: Mapped[Decimal] = mapped_column(DECIMAL(4, 2), default=Decimal("1.00"))
    
    # Dynamic Minimal Baseline (DMB) - The target Variable Essential Spend
    essential_target: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    
    # Metadata
    last_calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="financial_profile")
