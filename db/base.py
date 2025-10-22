# db/base.py - Complete Pasteable File for Fin-Traq V2 Schema Update

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, DateTime, DECIMAL, ForeignKey
from datetime import datetime
from decimal import Decimal

# --- 1. Base Class Definition ---
class Base(DeclarativeBase):
    """
    Base class which provides automated table name
    and represents the declarative base for all ORM models.
    """
    pass

# --- 2. Core User Model Update (User) ---
# NOTE: Replace the contents of this class with your existing User fields, 
# ensuring you include the 'num_dependents' field.
class User(Base):
    __tablename__ = "users"

    # Core Identifiers (PLACEHOLDER - UPDATE WITH YOUR ACTUAL FIELDS)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    monthly_salary: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'))

    # 🚨 CRITICAL V2 INPUT: Required for EFS Calculation
    # Stores the total number of people dependent on this user's salary (includes self + others)
    num_dependents: Mapped[int] = mapped_column(Integer, default=1) 


# --- 3. New V2 Model (FinancialProfile) ---
# This table stores the calculated results of the ML/EFS logic
class FinancialProfile(Base):
    __tablename__ = "financial_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    # Foreign Key to link to the User
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, index=True)

    # 🚨 V2 OUTPUT 1: Calculated Equivalent Family Size (EFS)
    e_family_size: Mapped[float] = mapped_column(DECIMAL(4, 2), default=1.0) 
    
    # 🚨 V2 OUTPUT 2: Dynamic Baseline Adjustment Factor 
    baseline_adjustment_factor: Mapped[float] = mapped_column(DECIMAL(4, 3), default=1.000)
    
    # Monthly calculated target for essential spending
    essential_target: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'))

    # Monthly total leakage calculated by the system
    total_monthly_leakage: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'))
    
    # Timestamp of the last successful V2 calculation
    last_calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# NOTE: Remove or update any old imports that reference external models 
# if you are consolidating them here.
# from . import models
# from . import user_profile
# from . import smart_transfer_rule
