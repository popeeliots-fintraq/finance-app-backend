# db/models.py

from sqlalchemy import Column, Integer, String, DECIMAL, Date, ForeignKey, PrimaryKeyConstraint, UniqueConstraint, Boolean, DateTime
from sqlalchemy.orm import relationship
from decimal import Decimal
from datetime import datetime

from .base import Base 
# Note: Ensure 'Base' is imported correctly from your relative path


# --- NEW MODEL: RAW TRANSACTION (Fix for Gap #1: Data Integrity) ---

class FinancialProfile(Base):
    """
    Stores long-term financial factors and ML outputs for Stratified Dependent Scaling.
    Calculated by the FinancialProfileService.
    """
    __tablename__ = 'financial_profile'

    # Primary Key is the user_id (one-to-one relationship with User)
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    
    # --- V2 ML LOGIC FIELDS (EFS & DMB Parameters) ---
    
    # 1. Equivalent Family Size (EFS) - Max 5 digits total, 2 decimal places (e.g., 2.35)
    e_family_size = Column(DECIMAL(5, 2), nullable=False, default=Decimal("1.00"), comment="The calculated Equivalent Family Size (EFS) factor.")
    
    # 2. Benchmark Efficiency Factor (BEF) - Max 5 digits total, 4 decimal places (e.g., 0.9850)
    benchmark_efficiency_factor = Column(DECIMAL(5, 4), nullable=False, default=Decimal("1.0000"), comment="Efficiency factor derived from benchmarking peers.")
    
    # 3. Dynamic Minimal Baseline (DMB) - Max 12 digits total, 2 decimal places (The Leakage Threshold)
    essential_target = Column(DECIMAL(12, 2), nullable=False, default=Decimal("0.00"), comment="The total calculated Dynamic Minimal Baseline (DMB) for variable essential spends.")
    
    # 4. Baseline Adjustment Factor (DMB / Net Income) - Max 5 digits total, 4 decimal places
    baseline_adjustment_factor = Column(DECIMAL(5, 4), nullable=False, default=Decimal("0.0000"), comment="The ratio of DMB to Net Income.")

    # Metadata
    last_calculated_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship back to the User model
    user = relationship("User", back_populates="financial_profile")


# --- Necessary Update to the User Model (Assuming it exists) ---
class User(Base):
    """(Partial definition showing necessary relationships)"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    # ... other user fields ...
    
    # --- V2 User Profile Inputs (Required for EFS calculation logic if not using a separate profile table) ---
    # NOTE: These were in your Pydantic model for input, and should be on the User model
    num_adults = Column(Integer, default=1)
    num_dependents_under_6 = Column(Integer, default=0)
    num_dependents_6_to_17 = Column(Integer, default=0)
    num_dependents_over_18 = Column(Integer, default=0)
    monthly_salary = Column(DECIMAL(12, 2), default=Decimal("0.00")) # Used for DMB scaling
    city_tier = Column(String, default="Tier 1")
    income_slab = Column(String, default="Mid")

    # --- Relationships ---
    transactions = relationship("Transaction", back_populates="user")
    smart_rules = relationship("SmartTransferRule", back_populates="user")
    raw_transactions = relationship("RawTransaction", back_populates="user")
    # CRITICAL: Link to the FinancialProfile for EFS/DMB data
    financial_profile = relationship("FinancialProfile", uselist=False, back_populates="user")
    
# ... (All other models follow: Transaction, SmartTransferRule, SalaryAllocationProfile) ...

class RawTransaction(Base):
    """
    Stores raw, unprocessed SMS/UPI messages. This ensures no data is lost
    and provides an audit trail for categorization.
    """
    __tablename__ = 'raw_transactions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Raw source data fields
    source_type = Column(String, default='SMS') # SMS, UPI_WEBHOOK, API
    raw_text = Column(String, nullable=False)
    
    # Categorization Status
    is_processed = Column(Boolean, default=False)
    categorization_attempts = Column(Integer, default=0)
    
    # Link to the cleaned Transaction (if successful)
    # Allows a raw message to link to the final transaction record
    transaction_id = Column(Integer, ForeignKey('transactions.id'), nullable=True)

    # Relationships
    user = relationship("User", back_populates="raw_transactions")
    # Note: Need to set up 'raw_source' relationship on Transaction model below.


class Transaction(Base):
    """
    SQLAlchemy ORM Model for the 'transactions' table. 
    Stores CLEAN, CATEGORIZED financial movements.
    """
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    transaction_date = Column(Date, nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False) # CREDIT, DEBIT, DEBIT_INTERNAL (Autopilot)
    
    # V2 Autopilot Audit Fields
    smart_rule_id = Column(Integer, ForeignKey('smart_transfer_rules.id'), nullable=True)
    
    # 🚨 FORTIFICATION FIX (Gap #3): Link the Autopilot transaction to its source salary calculation
    salary_profile_id = Column(Integer, ForeignKey('salary_allocation_profile.id'), nullable=True)

    # Relationships
    user = relationship("User", back_populates="transactions")
    smart_rule = relationship("SmartTransferRule", back_populates="transactions")
    salary_profile = relationship("SalaryAllocationProfile", back_populates="autopilot_transactions")
    
    # Link back to the RawTransaction that created it (Fix for Gap #1)
    raw_source = relationship("RawTransaction", backref="processed_transaction_ref", foreign_keys=[RawTransaction.transaction_id], uselist=False)

    
class SmartTransferRule(Base):
    """
    SQLAlchemy ORM Model for Smart Rules (Goals, Tax Saving commitments).
    """
    __tablename__ = "smart_transfer_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    rule_type = Column(String, nullable=False) # e.g., 'GOAL', 'TAX_SAVING', 'STASH'
    priority = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    
    target_amount_monthly = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"), comment="Monthly funding target for this rule.")
    amount_allocated_mtd = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"), comment="Total amount funded towards this rule in the current month.")
    destination_account_name = Column(String, nullable=True)

    # Relationships
    user = relationship("User", back_populates="smart_rules")
    transactions = relationship("Transaction", back_populates="smart_rule")


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
    # Renamed from 'consented_move_amount' to 'total_autotransferred' for clarity
    total_autotransferred = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))

    # 🚨 V2 ADDITION 3: TAX LEAKAGE HEADROOM (New Field)
    tax_headroom_remaining = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00")) 
    
    # Relationships
    # FORTIFICATION FIX (Gap #3): Tracks all Autopilot transactions sourced from this profile
    autopilot_transactions = relationship("Transaction", back_populates="salary_profile")

    __table_args__ = (
        # Ensures a user only has one profile per reporting period
        UniqueConstraint('user_id', 'reporting_period', name='uc_user_period_allocation'),
    )

# NOTE: The User and FinancialProfile models should also exist in this file or imported/defined elsewhere
# For example, the User model needs:
#   transactions = relationship("Transaction", back_populates="user")
#   smart_rules = relationship("SmartTransferRule", back_populates="user")
#   raw_transactions = relationship("RawTransaction", back_populates="user")
