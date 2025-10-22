# finance-app-backend/api/dependencies.py

import os
import secrets # Used for secure string comparison (timing attack resistance)
from functools import lru_cache
from fastapi import Header, HTTPException, status
from starlette.requests import Request # Added to log the user agent if needed (optional)

# 1. Use lru_cache to read the environment variable only once at server startup
# Using a specific name for the Fin-Traq backend API Key for clarity
@lru_cache()
def get_expected_fin_traq_api_key() -> str:
    """Retrieves the FIN_TRAQ_API_KEY from the server's environment."""
    # Renamed the environment variable for better project clarity
    return os.getenv("FIN_TRAQ_API_KEY", "")

def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    FastAPI Dependency to validate the API key sent in the X-API-Key header.
    This ensures only the trusted Fin-Traq Android client or internal services 
    can access the Locked Backend Financial Orchestration System.
    """
    expected_key = get_expected_fin_traq_api_key()
    
    # Check 1: Server Configuration Error (500)
    # The expected key should always be set as a secret in the Cloud Run deployment.
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: FIN_TRAQ_API_KEY not set for secure validation."
        )

    # Check 2: Key Validation (401 Unauthorized)
    # CRITICAL: Use secrets.compare_digest for constant-time comparison to mitigate timing attacks.
    if not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key provided for Fin-Traq Backend Access"
        )
        
    # If the key is valid, the request proceeds
    return x_api_key
