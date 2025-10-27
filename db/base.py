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

# --- 2. Core User Model Update (User) ---
class User(Base):
    __tablename__ = "users"

    # Core Identifiers (PLACEHOLDER)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    monthly_salary: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'))

    # V2 EFS INPUTS: Required for EFS calculation in Orchestration Service
    num_adults: Mapped[int] = mapped_column(Integer, default=1) 
    num_dependents_under_6: Mapped[int] = mapped_column(Integer, default=0) 
    num_dependents_6_to_17: Mapped[int] = mapped_column(Integer, default=0) 
    num_dependents_over_18: Mapped[int] = mapped_column(Integer, default=0) 

    # 🚨 V2 CRITICAL INPUTS: REQUIRED FOR DMB/BENCHMARKING LOGIC
    # city_tier is used by DMB for cost multiplier
    city_tier: Mapped[str] = mapped_column(String(50), nullable=True, default="Tier 3") 
    # income_slab is used by DMB for efficiency factor and benchmarking
    income_slab: Mapped[str] = mapped_column(String(50), nullable=True, default="Medium")

    # Relationships
    financial_profile = relationship("FinancialProfile", back_populates="user", uselist=False)
    salary_profiles = relationship("SalaryAllocationProfile", back_populates="user")


# --- 3. V2 Model (FinancialProfile) ---
class FinancialProfile(Base):
    __tablename__ = "financial_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, index=True)

    # 🚨 V2 OUTPUT 1: Calculated Equivalent Family Size (EFS) - Moved from User
    # Required by DMB logic and BenchmarkingService for similarity filtering
    e_family_size: Mapped[Decimal] = mapped_column(DECIMAL(4, 2), default=Decimal("1.00"), index=True) 
    
    # V2 OUTPUT 2: Dynamic Baseline Adjustment Factor 
    baseline_adjustment_factor: Mapped[Decimal] = mapped_column(DECIMAL(4, 3), default=Decimal("1.000"))
    
    # Monthly calculated target for essential spending (Total Leakage Threshold)
    essential_target: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'))

    # Monthly total leakage calculated by the system
    total_monthly_leakage: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0.00'))
    
    last_calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="financial_profile")


# --- 4. V2 Model (SalaryAllocationProfile) ---
# CRITICAL MODEL for monthly state and DMB output persistence
class SalaryAllocationProfile(Base):
    __tablename__ = "salary_allocation_profiles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'))
    reporting_period: Mapped[date] = mapped_column(Date)
    
    net_monthly_income: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    
    # 🚨 CRITICAL FIELD 1: Fixed Commitments
    # Required for GMB Guardrail (LeakageService) and Benchmarking Cohort Filtering
    fixed_commitment_total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00")) 
    
    # 🚨 CRITICAL FIELD 2: Actual Variable Spend
    # Required for true Benchmarking ratio calculation and Month-End Reconciliation
    variable_spend_total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00")) 
    
    # OUTPUT: Projected Reclaimable Salary (The final goal amount after GMB guardrail)
    projected_reclaimable_salary: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=True, default=Decimal("0.00"))
    
    # Constraints (Optional but good practice)
    __table_args__ = (UniqueConstraint('user_id', 'reporting_period', name='_user_period_uc'),)
    
    user = relationship("User", back_populates="salary_profiles")
