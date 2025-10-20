# db/smart_transfer_rule.py

from sqlalchemy import Column, String, DECIMAL, ForeignKey, Integer, Boolean, Enum
from .base import Base 
from enum import Enum as PyEnum

# Define an Enum for the type of action (for validation and clarity)
class RuleActionType(PyEnum):
    GOAL = "Goal"
    TAX_SAVING = "Tax Saving"
    DEBT_PAYMENT = "Debt Payment"
    CASHBACK_MAXIMIZATION = "Cashback Maximization" # Phase 3 (Tax Optimization) [cite: 2025-10-15]

class SmartTransferRule(Base):
    """
    SQLAlchemy ORM Model for the 'smart_transfer_rule' table.
    Defines the automatic transfer rules for converting leftover/recovered income 
    into goals or tax savings (Guided Execution). [cite: 2025-10-15]
    """
    
    __tablename__ = "smart_transfer_rule"
    
    # Primary Key
    rule_id = Column(Integer, primary_key=True, index=True) 
    
    # Foreign Key
    user_id = Column(String(255), ForeignKey('user_profile.user_id'), nullable=False)
    
    # Rule Definition
    rule_name = Column(String(255), nullable=False)
    action_type = Column(Enum(RuleActionType), nullable=False) 
    
    # Allocation Logic
    # Percentage to allocate from the 'projected_reclaimable_salary'
    allocation_percentage = Column(DECIMAL(5, 2), nullable=False, default=Decimal("100.00")) 
    
    # Destination Account/Instrument (e.g., Bank Account, Mutual Fund ID, Credit Card ID)
    destination_target_id = Column(String(255), nullable=False) 
    
    # Orchestration/Execution Status
    is_active = Column(Boolean, default=True)
    
    # Frequency/Conditions (simplified for now)
    execute_on_day = Column(Integer, default=1) # 1 = 1st of the month, etc.
    
    # Ensures the combination of user and rule name is unique
    __table_args__ = (
        UniqueConstraint('user_id', 'rule_name', name='uc_user_rule_name'),
    )
