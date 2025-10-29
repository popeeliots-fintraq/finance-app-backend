from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Boolean, DateTime, DECIMAL, ForeignKey, Date, UniqueConstraint
from datetime import datetime, date
from decimal import Decimal

# --- 1. Base Class Definition ---
class Base(DeclarativeBase):
    """
    Base class which provides automated table name
    and represents the declarative base for all ORM models.
    """
    pass

# --- 2. Core User Model (EFS & DMB Inputs) ---
class User(Base):
    __tablename__ = "users"

    # Core Identifiers
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Financial Anchor
    monthly_salary: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'), comment="Net monthly take-home income")

    # V2 EFS Inputs: Required for EFS calculation in Orchestration Service
    num_adults: Mapped[int] = mapped_column(Integer, default=1, comment="Number of adults in the household")
    num_dependents_under_6: Mapped[int] = mapped_column(Integer, default=0, comment="Dependents aged 0-5")
    num_dependents_6_to_17: Mapped[int] = mapped_column(Integer, default=0, comment="Dependents aged 6-17")
    num_dependents_over_18: Mapped[int] = mapped_column(Integer, default=0, comment="Dependents aged 18+")

    # V2 CRITICAL INPUTS: REQUIRED FOR DMB/BENCHMARKING LOGIC
    city_tier: Mapped[str] = mapped_column(String(50), nullable=True, default="Tier 3", comment="Geographical cost-of-living tier")
    income_slab: Mapped[str] = mapped_column(String(50), nullable=True, default="Medium", comment="Income bracket for peer benchmarking")
    
    # Orchestration Input (Salary Maximizer) - Note: This is now correctly stored on SalaryAllocationProfile
    # We remove tax_headroom_remaining from here as it's monthly/period specific and lives on SalaryAllocationProfile.

    # Relationships
    financial_profile = relationship("FinancialProfile", back_populates="user", uselist=False)
    salary_profiles = relationship("SalaryAllocationProfile", back_populates="user")
    # NOTE: You will need to add relationships for transactions, raw_transactions, and smart_rules here 
    # if they are defined in another file and reference the User model.


# --- 3. V2 Model (FinancialProfile) - ML Outputs ---
class FinancialProfile(Base):
    __tablename__ = "financial_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, index=True)

    # V2 ML OUTPUTS
    e_family_size: Mapped[Decimal] = mapped_column(DECIMAL(4, 2), default=Decimal("1.00"), index=True, comment="Calculated Equivalent Family Size")
    
    # 🚨 CRITICAL ADDITION: Benchmark Efficiency Factor (BEF) - Fortifies DMB logic
    benchmark_efficiency_factor: Mapped[Decimal] = mapped_column(DECIMAL(4, 3), default=Decimal("1.000"), comment="Efficiency factor derived from benchmarking service")

    baseline_adjustment_factor: Mapped[Decimal] = mapped_column(DECIMAL(4, 3), default=Decimal("1.000"), comment="Income/EFS scaling factor")
    
    # Total Leakage Threshold / Dynamic Minimal Baseline (DMB)
    essential_target: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'), comment="Total monthly DMB spend limit")

    total_monthly_leakage: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'), comment="Accumulated leakage for the month")
    
    last_calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="financial_profile")


# --- 4. V2 Model (SalaryAllocationProfile) - Monthly State ---
class SalaryAllocationProfile(Base):
    __tablename__ = "salary_allocation_profiles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'))
    reporting_period: Mapped[date] = mapped_column(Date)
    
    net_monthly_income: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    
    # Fixed Commitments / Variable Spend (Required for Leakage Service)
    fixed_commitment_total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    variable_spend_total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"), comment="Accumulated variable spend MTD")
    
    # Leak Finder / Guided Orchestration Outputs
    projected_reclaimable_salary: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"), comment="Money recovered from fixed/variable leaks")
    total_autotransferred: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"), comment="Amount transferred with user consent MTD")

    # 🚨 CRITICAL FIELD: TAX LEAKAGE HEADROOM (Salary Maximizer Input)
    tax_headroom_remaining: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"), comment="Remaining annual tax saving capacity")
    
    # Relationships
    user = relationship("User", back_populates="salary_profiles")
    # Link back to transactions sourced from this profile
    # NOTE: You must ensure 'autopilot_transactions' is also defined in your Transaction model
    # autopilot_transactions = relationship("Transaction", back_populates="salary_profile") 

    __table_args__ = (
        UniqueConstraint('user_id', 'reporting_period', name='uc_user_period_allocation'),
    )
    
    
# NOTE: Other models like Transaction, RawTransaction, and SmartTransferRule are likely in db/models.py
# If they are in this file, ensure they are also updated as needed (e.g., SmartTransferRule with target_amount_monthly).
