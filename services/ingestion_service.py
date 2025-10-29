# services/ingestion_service.py

from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from ..db.models import RawTransaction, Transaction
from ..db.enums import TransactionType
# from ..ml.categorization_engine import categorize_text # Conceptual ML import

class IngestionService:
    """
    Handles the high-speed ingestion of raw SMS/UPI data (Gap #1 fix). 
    It saves the raw data instantly and triggers the asynchronous categorization 
    pipeline, ensuring the 'Frictionless' flow.
    """
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def ingest_raw_data(self, raw_message: str, source: str = 'SMS') -> RawTransaction:
        """
        Saves the raw message instantly to the RawTransaction table.
        This is the primary function for securing data integrity.
        """
        raw_tx = RawTransaction(
            user_id=self.user_id,
            raw_text=raw_message,
            source_type=source,
            timestamp=datetime.utcnow()
        )
        self.db.add(raw_tx)
        self.db.commit()
        self.db.refresh(raw_tx) # Get the generated ID
        
        # --- Asynchronous Trigger (Conceptual) ---
        # In a production system, this would trigger a dedicated background worker 
        # (like Celery/RQ) to process the categorization using ML.
        # Example: start_categorization_worker(raw_tx.id)
        # ----------------------------------------
        
        return raw_tx
    
    # --- Conceptual Asynchronous Categorization (Worker Function) ---
    def process_categorization_worker(self, raw_transaction_id: int):
        """
        Conceptual worker function that runs the heavy ML categorization logic.
        This must run separately from the main API thread to keep the ingestion API fast.
        """
        raw_tx = self.db.query(RawTransaction).filter(RawTransaction.id == raw_transaction_id).first()
        if not raw_tx or raw_tx.is_processed:
            return

        # Increment attempts and try categorization
        raw_tx.categorization_attempts += 1
        self.db.commit()
        
        try:
            # 1. ML Categorization (MOCK)
            # categorized_data = categorize_text(raw_tx.raw_text)
            
            # MOCK result for integration testing
            categorized_data = {
                "amount": Decimal("500.00"),
                "category": "Discretionary: Food & Dining",
                "type": TransactionType.DEBIT.value,
                "description": "UPI payment for dinner"
            }

            # 2. Create the Clean Transaction
            new_transaction = Transaction(
                user_id=self.user_id,
                transaction_date=raw_tx.timestamp.date(),
                amount=categorized_data["amount"],
                description=categorized_data["description"],
                category=categorized_data["category"],
                transaction_type=categorized_data["type"],
            )
            self.db.add(new_transaction)
            self.db.flush() # Get the new_transaction ID

            # 3. Finalize Raw Transaction and Link
            raw_tx.is_processed = True
            raw_tx.transaction_id = new_transaction.id
            
            # 4. Commit and Trigger Orchestration
            self.db.commit()

            # CRITICAL STEP: Trigger the Autopilot Orchestration on new, clean data
            # from .orchestration_service import OrchestrationService
            # orch_service = OrchestrationService(self.db, self.user_id)
            # orch_service.recalculate_current_period_leakage(new_transaction.transaction_date) 
            
            return new_transaction.id
            
        except Exception as e:
            # Handle logging and retry logic here
            self.db.rollback()
            print(f"Error processing transaction {raw_transaction_id}: {e}")


# NOTE: For deployment, ensure the categorization logic is handled via a separate, 
# non-blocking worker process to maintain high API throughput.
