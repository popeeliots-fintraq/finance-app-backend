# finance-app-backend/api/dependencies.py

import os
from functools import lru_cache
from fastapi import Header, HTTPException, status

# 1. Use lru_cache to read the environment variable only once at server startup
@lru_cache()
def get_expected_api_key() -> str:
    """Retrieves the FASTAPI_API_KEY from the server's environment."""
    return os.getenv("FASTAPI_API_KEY", "")

def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    FastAPI Dependency to validate the API key sent in the X-API-Key header.
    """
    expected_key = get_expected_api_key()
    
    # Check if the server's key is configured (a 500-level error)
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: FASTAPI_API_KEY not set for validation."
        )

    # Validate the key (a 401 Unauthorized error for the client)
    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key provided"
        )
    # If the key is valid, the request proceeds
    return x_api_key
