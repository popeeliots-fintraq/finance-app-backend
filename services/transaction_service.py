# services/transaction_service.py

from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
import uuid

# Import schemas and models
from ..api.v1.schemas.transaction import RawTransactionIn, CategorizedTransactionOut
from ..db.models import Transaction, LeakBucket, SalaryAllocationProfile
from ..db.enums import TransactionType

class TransactionService:
    """
    Handles the ingestion, ML categorization, and initial leakage assessment 
    of raw SMS transaction data.
    """

    def __init__(self, db: Session):
        self.db = db

    def _call_ml_categorizer(self, transaction_text: str) -> dict:
        """
        [MOCK] Placeholder for calling the external ML categorization service.
        In production, this would be an HTTP call to the 'categorizer_api.py'.
        """
        # Mocking the ML model response for a typical expense SMS
        return {
            "merchant": "Zomato/Swiggy/CloudKitchen",
            "category": "Discretionary_Food_Delivery",
            "amount": 450.00,  # Extracted by ML or parser
            "type": TransactionType.DEBIT.value
        }
        
    def _assess_leak_potential(self, amount: Decimal, category: str) -> Decimal:
        """
        [MOCK] Performs an initial, coarse leak assessment based on category rules.
        A proper leak assessment (against DMB) happens later in LeakageService.
        """
        # Simple mock rule: flag all high discretionary spending as potential leak
        if 'Discretionary' in category and amount > Decimal(200.00):
            return amount
        return Decimal("0.00")

    def process_raw_transaction(self, raw_data: RawTransactionIn, user_id: str) -> CategorizedTransactionOut:
        """
        Orchestrates the categorization, storage, and initial leak assessment.
        """
        
        # 1. ML Categorization and Extraction
        ml_result = self._call_ml_categorizer(raw_data.transaction_text)
        
        # Use Decimal for accurate financial calculations
        amount = Decimal(ml_result['amount']).quantize(Decimal('0.01'))
        
        # 2. Initial Leak Assessment
        leak_potential = self._assess_leak_potential(amount, ml_result['category'])
        
        # 3. Create the Database Transaction Record
        transaction_id = str(uuid.uuid4())
        
        # Convert string date to datetime object
        try:
            # Assuming ISO format like "YYYY-MM-DD HH:MM:SS"
            transaction_date = datetime.fromisoformat(raw_data.sms_date_time)
        except ValueError:
            # Fallback for date parsing errors
            transaction_date = datetime.now()

        new_transaction = Transaction(
            transaction_id=transaction_id,
            user_id=user_id,
            transaction_type=ml_result['type'],
            amount=amount,
            merchant=ml_result['merchant'],
            category=ml_result['category'],
            leak_potential=leak_potential,
            transaction_date=transaction_date,
            raw_sms_text=raw_data.transaction_text
        )

        self.db.add(new_transaction)
        self.db.commit()
        self.db.refresh(new_transaction)
        
        # 4. Return the categorized schema (for the API response)
        return CategorizedTransactionOut(
            transaction_id=new_transaction.transaction_id,
            user_id=new_transaction.user_id,
            amount=float(new_transaction.amount), # Convert back to float for JSON response model
            merchant=new_transaction.merchant,
            category=new_transaction.category,
            leak_potential=float(new_transaction.leak_potential)
        )
