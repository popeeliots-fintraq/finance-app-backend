# api/v1/transactions.py

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import Annotated

from ...schemas.transaction import RawTransactionIn, CategorizedTransactionOut
from ...db.database import get_db
# Placeholder for Categorization Service
# from ...services.categorization_service import process_raw_transaction

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
    # User ID will be passed via authentication tokens in a real system
    user_id: str = Depends(lambda: "user_popeelots_123") 
):
    """
    Receives raw SMS text, extracts transaction details, categorizes it, 
    assesses initial leak potential, and stores the transaction.
    """
    
    # NOTE: Placeholder for service call that will handle the heavy lifting.
    # We are mocking the response for now, but this is where the ML Categorizer 
    # (from your separate 'categorizer/' component) would be called.
    
    # In a real system, this would call a service:
    # final_transaction = process_raw_transaction(raw_data, user_id, db)
    
    # Mocking the successful categorization and processing response:
    mock_id = f"txn_{user_id}_{hash(raw_data.transaction_text)}"
    
    return CategorizedTransactionOut(
        transaction_id=mock_id,
        user_id=user_id,
        amount=550.00,
        merchant="Swiggy",
        category="Discretionary_Food",
        leak_potential=550.00 if 550.00 > 100.00 else 0.00 # Mock leak logic
    )
