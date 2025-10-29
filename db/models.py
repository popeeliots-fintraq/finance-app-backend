# db/models.py

from sqlalchemy import Column, Integer, String, DECIMAL, Date, ForeignKey, PrimaryKeyConstraint, UniqueConstraint, Boolean, DateTime
from sqlalchemy.orm import relationship
from decimal import Decimal
from datetime import datetime

from .base import Base 
# Note: Ensure 'Base' is imported correctly from your relative path


# --- NEW MODEL: RAW TRANSACTION (Fix for Gap #1: Data Integrity) ---
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
    
    target_amount_monthly = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
    amount_allocated_mtd = Column(DECIMAL(10, 2), nullable=False, default=Decimal("0.00"))
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
