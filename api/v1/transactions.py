# api/v1/transactions.py - UPDATED

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated

from ..schemas.transaction import RawTransactionIn, CategorizedTransactionOut
from ...db.database import get_db
from ...services.transaction_service import TransactionService # <--- NEW IMPORT

router = APIRouter(
    prefix="/transactions",
    tags=["Transaction Ingestion & Categorization"]
)

DBDependency = Annotated[Session, Depends(get_db)]

@router.post(
    "/ingest-raw", 
    response_model=CategorizedTransactionOut, 
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest raw transaction SMS text for categorization and processing."
)
def ingest_raw_transaction(
    raw_data: RawTransactionIn, 
    db: DBDependency,
    user_id: str = Depends(lambda: "user_popeelots_123") 
):
    """
    Receives raw SMS text, extracts transaction details, categorizes it, 
    assesses initial leak potential, and stores the transaction.
    """
    
    # Instantiate the Transaction Service
    txn_service = TransactionService(db=db)
    
    # Call the service to process the data
    try:
        final_transaction = txn_service.process_raw_transaction(raw_data, user_id)
        return final_transaction
    except Exception as e:
        # Log the exception for debugging
        print(f"Error processing transaction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process and categorize transaction."
        )
