# models/user_profile.py
from typing import List
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DECIMAL, ForeignKey
from datetime import datetime


from ..db.base import Base
from ..db.enums import CityTier, EnumString # Import the Enum helper

class User(Base):
    __tablename__ = "users"
    
    # Core Identification
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Financial Inputs (Base for DMB calculation)
    monthly_salary: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    
    # EFS Inputs (For Equivalent Family Size calculation)
    num_adults: Mapped[int] = mapped_column(Integer, default=1)
    num_dependents_under_6: Mapped[int] = mapped_column(Integer, default=0)
    num_dependents_6_to_17: Mapped[int] = mapped_column(Integer, default=0)
    num_dependents_over_18: Mapped[int] = mapped_column(Integer, default=0)
    
    # Benchmarking Input
    city_tier: Mapped[CityTier] = mapped_column(EnumString(CityTier), default=CityTier.TIER_2)
    
    # Relationships
    financial_profile: Mapped["FinancialProfile"] = relationship(back_populates="user", uselist=False)
    salary_profiles: Mapped[List["SalaryAllocationProfile"]] = relationship(back_populates="user")
