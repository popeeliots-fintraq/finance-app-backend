# models/smart_transfer.py

from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, DECIMAL, DateTime, ForeignKey, String
from datetime import datetime
from decimal import Decimal

from ..db.base import Base

class SmartTransferRule(Base):
    __tablename__ = "smart_transfer_rules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    
    # --- Rule Definition ---
    
    # Source fund pool (e.g., 'TOTAL_RECLAIMABLE', 'CATEGORY_LEAK:DiningOut')
    source_fund: Mapped[str] = mapped_column(String(50)) 
    
    # Priority (e.g., 1 for Tax, 2 for Emergency Fund, 3 for Vacation Goal)
    priority: Mapped[int] = mapped_column(Integer)
    
    # Target (e.g., 'Tax_Goal_80C', 'Stash_Emergency', 'UPI_Transfer_Goal_X')
    destination_goal: Mapped[str] = mapped_column(String(100))
    
    # Max amount to transfer per execution (to prevent over-commitment)
    max_transfer_limit: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    
    # --- Execution Status ---
    
    # Total amount successfully transferred against this rule
    total_transferred: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    
    is_active: Mapped[bool] = mapped_column(default=True)
    last_executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class SmartTransferLog(Base):
    __tablename__ = "smart_transfer_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("smart_transfer_rules.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    
    amount_transferred: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Status of the actual UPI/Bank transfer
    execution_status: Mapped[str] = mapped_column(String(50)) 
    
    # Relationships (Optional but helpful)
    rule: Mapped["SmartTransferRule"] = relationship()
