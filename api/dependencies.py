# finance-app-backend/api/dependencies.py

import os
import secrets
from functools import lru_cache
from fastapi import Header, HTTPException, status
# NEW IMPORT: Need the Firestore Client library
from google.cloud import firestore
from google.cloud.firestore import Client as FirestoreClient
from starlette.requests import Request

# --- GLOBAL FIREBASE/FIRESTORE CLIENT INITIALIZATION ---
# Use a global variable to hold the client instance
# This adheres to the singleton pattern for efficiency in Cloud Run/FastAPI
firestore_client: FirestoreClient = None

def get_firestore_client() -> FirestoreClient:
    """Initializes the global Firestore client instance if it doesn't exist."""
    global firestore_client
    if firestore_client is None:
        # Client initialization is done only once. 
        # It automatically handles authentication (ADC) from the Cloud Run environment.
        firestore_client = firestore.Client()
    return firestore_client

def get_db() -> FirestoreClient:
    """
    FastAPI Dependency that provides the Cloud Firestore Client object.
    
    This replaces the old get_db function that provided an SQLAlchemy Session.
    The 'yield' pattern is used, although for a simple client object (unlike a session), 
    'return' is often sufficient, but 'yield' can be safer for future cleanup logic.
    """
    try:
        db_client = get_firestore_client()
        yield db_client
    except Exception as e:
        # Raise an exception if the database client fails to initialize/connect
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection error: Could not initialize Firestore client. Detail: {e}"
        )

# --------------------------------------------------------------------------
# EXISTING API KEY VALIDATION CODE (NO CHANGES NEEDED)
# --------------------------------------------------------------------------

@lru_cache()
def get_expected_fin_traq_api_key() -> str:
    """Retrieves the FIN_TRAQ_API_KEY from the server's environment."""
    return os.getenv("FIN_TRAQ_API_KEY", "")

def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    FastAPI Dependency to validate the API key sent in the X-API-Key header.
    """
    expected_key = get_expected_fin_traq_api_key()
    
    # Check 1: Server Configuration Error (500)
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: FIN_TRAQ_API_KEY not set for secure validation."
        )

    # Check 2: Key Validation (401 Unauthorized)
    if not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key provided for Fin-Traq Backend Access"
        )
        
    return x_api_key
