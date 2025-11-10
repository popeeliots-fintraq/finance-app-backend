# db/database.py

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import URL
from starlette.config import Config
import os

# --- Configuration (Load from Environment) ---

# Define the path to a .env file if used, otherwise it uses OS environment variables
# NOTE: Replace with your actual configuration loading logic if different
config = Config(".env") 

# Supabase connection string example:
# postgresql://[USER]:[PASSWORD]@[DB_HOST]:5432/[DB_NAME]
DATABASE_URL = config("DATABASE_URL", default=os.environ.get("DATABASE_URL")) 

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# --- Database Engine Setup ---

# Create the Async Engine
# The 'postgresql+asyncpg' dialect is required for asynchronous operation with Postgres
engine = create_async_engine(
    DATABASE_URL, 
    pool_size=15, # Matching your Supabase pool size limit
    max_overflow=0,
    future=True,
    echo=False # Set to True for debugging SQL queries
)

# Create an AsyncSessionLocal class
# This class will be used to create session objects
AsyncSessionLocal = sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False, # Essential for working with ORM objects outside the session
)

# --- Dependency Function for FastAPI ---

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that provides a managed AsyncSession object to FastAPI endpoints.
    Ensures the session is closed after the request is finished.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            # Optionally, add logging for transaction rollback
            await session.rollback()
            raise
        finally:
            # Ensure the session is closed
            await session.close()
            
# --- Utility for creating tables (Use this for initial setup/migrations) ---
from ..db.base import Base # Import your Base definition

async def create_db_and_tables():
    """
    Creates all defined tables in the database.
    This should generally be managed by Alembic in production.
    """
    async with engine.begin() as conn:
        # Import all model modules so that SQLAlchemy knows about them
        from ..models import user_profile, financial_profile, salary_profile, transaction, smart_transfer # Ensure all models are imported here
        
        # Drop all tables (CAUTION: Only for development/testing)
        # await conn.run_sync(Base.metadata.drop_all)
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("Database tables created successfully.")
