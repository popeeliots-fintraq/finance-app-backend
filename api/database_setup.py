# api/database_setup.py

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 1. Get the DATABASE_URL from the environment (In deployment, this is from the GitHub Secret)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Use a default URL for local testing if needed, or raise an error
    print("Warning: DATABASE_URL environment variable is not set.")
    # In a real deployed environment, this must raise an error.

# 2. Configure the URL for the asynchronous driver (psycopg)
# We change 'postgresql://' to 'postgresql+psycopg://'
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
else:
    # Use a placeholder or mock URL if not found for initial setup
    ASYNC_DATABASE_URL = "postgresql+psycopg://user:pass@host/db"


# 3. Create the Async Engine
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False, # Set to True for verbose SQL logs (useful for debugging)
    pool_size=10, 
    max_overflow=5
)

# 4. Create the Async Session Factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False # Prevents objects from expiring after commit
)
