# api/v1/schemas/transaction.py

from pydantic import BaseModel, Field
from typing import Optional

class RawTransactionIn(BaseModel):
    """Schema for raw transaction data ingested from the Android app."""
    
    transaction_text: str = Field(..., description="The raw SMS message text containing the transaction.")
    sms_date_time: str = Field(..., description="The timestamp when the SMS was received (ISO format or similar).")
    bank_identifier: str = Field(..., description="E.g., 'HDFC' or 'ICICI' based on message structure.")
    pre_extracted_amount: Optional[str] = Field(None, description="Optional raw string of the transaction amount.") 

class CategorizedTransactionOut(BaseModel):
    """Schema for the final processed and categorized transaction."""
    
    transaction_id: str
    user_id: str
    amount: float
    merchant: str
    category: str = Field(..., description="The categorization result from the ML model.")
    # This reflects the core Fin-Traq V2 focus: assessing initial leak against the DMB.
    leak_potential: float = Field(..., description="Initial assessment of leak based on category/amount.")
