# finance-app-backend/api/dependencies.py

import os
import secrets
from functools import lru_cache
from typing import AsyncGenerator
from fastapi import Header, HTTPException, status

# 🌟 NEW IMPORTS FOR POSTGRESQL/SQLAlchemy ASYNC CONNECTION
from sqlalchemy.ext.asyncio import AsyncSession
# Import the session factory from the file we will create next to hold the engine setup
# Assuming the connection setup is in a new file named database_setup.py in the same directory (api/)
from .database_setup import AsyncSessionLocal 
# -------------------------------------------------------------------------------------

# --- DATABASE DEPENDENCY (UPDATED FOR ASYNC POSTGRESQL) ---

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency that yields an asynchronous SQLAlchemy Session connected to Supabase PostgreSQL.
    It handles automatic commit on success and rollback on exceptions (CRITICAL for financial integrity).
    """
    # 1. Open a new asynchronous session from the factory
    async with AsyncSessionLocal() as session:
        try:
            # 2. Yield the session to the FastAPI endpoint function
            yield session
            # 3. Commit the transaction after the endpoint finishes (if no exceptions)
            await session.commit()
        except Exception:
            # 4. Rollback on any error
            await session.rollback()
            raise

# --- MOCK USER ID (RETAINED/SIMPLIFIED) ---
async def get_current_user_id() -> int:
    """Mocking a user ID for service calls, to be replaced by actual auth logic later."""
    # NOTE: In a real system, this would extract the user ID from the authentication token.
    return 1  


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
