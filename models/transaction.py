# models/transaction.py

from typing import Optional
# CRITICAL FIX: Add 'relationship'
from sqlalchemy.orm import Mapped, mapped_column, relationship 
from sqlalchemy import Integer, DECIMAL, DateTime, ForeignKey, String, Text
from datetime import datetime
from decimal import Decimal

from ..db.base import Base
from ..db.enums import SDSWeightClass, TransactionStatus, EnumString

# CRITICAL FIX: Import the related User model
from .user_profile import User 

class Transaction(Base):
    __tablename__ = "transactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # This ForeignKey implies a relationship with the User model
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id")) 
    
    # --- Source Data ---
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    transaction_date: Mapped[datetime] = mapped_column(DateTime)
    # The raw message/description from SMS or UPI
    description: Mapped[str] = mapped_column(Text)
    
    # --- Fin-Traq V2 Categorization (ML Outputs) ---
    
    # ML-assigned granular category (e.g., 'Pure_Discretionary_DiningOut')
    category: Mapped[str] = mapped_column(String(100), index=True) 
    
    # SDS Classification (The weight class determined by the core ML logic)
    sds_class: Mapped[SDSWeightClass] = mapped_column(EnumString(SDSWeightClass), index=True)
    
    # Manual override flag (for user-corrected transactions)
    is_manual_override: Mapped[bool] = mapped_column(default=False)
    
    # --- Status and Metadata ---
    status: Mapped[TransactionStatus] = mapped_column(EnumString(TransactionStatus), default=TransactionStatus.COMPLETED)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # RECOMMENDED ADDITION: Define the relationship for ORM query efficiency
    # user: Mapped["User"] = relationship(back_populates="transactions")
