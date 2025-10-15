from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# --- Pydantic Models ---

class Transaction(BaseModel):
    """The structure of the data expected from the Android app (SMS text)."""
    # The key must match the @SerializedName in your Kotlin model (sms_text)
    sms_text: str

class CategoryResult(BaseModel):
    """The structure of the data the server sends back to the Android app."""
    transaction_id: str
    category: str
    amount: float
    confidence_score: float # Included for Fintraq's AI/analysis feature

# --- API Endpoint ---

@app.get("/")
def read_root():
    # Keep the simple root endpoint for basic health checks
    return {"message": "Hello, Fintraq is live!"}

@app.post("/api/v1/categorize", response_model=CategoryResult)
async def categorize_transaction(transaction: Transaction):
    """
    MOCK endpoint for categorization. 
    In the real implementation, this is where the SMS parsing and Gemini AI logic would go.
    """
    print(f"Received SMS: {transaction.sms_text}")
    
    # MOCK Logic: Determines category based on keywords
    if "credit" in transaction.sms_text.lower():
        category = "Income"
        amount = 5000.00
        confidence = 0.95
    elif "groceries" in transaction.sms_text.lower():
        category = "Groceries"
        amount = 549.99
        confidence = 0.88
    else:
        category = "Miscellaneous"
        amount = 100.00
        confidence = 0.50

    return CategoryResult(
        transaction_id="TXN" + str(hash(transaction.sms_text) % 10000), # Simple unique ID
        category=category,
        amount=amount,
        confidence_score=confidence
    )
