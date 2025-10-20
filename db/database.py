# db/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

# Load the database URL from an environment variable (best practice)
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@localhost/dbname" # Placeholder
)

# SQLAlchemy Engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL
)

# SessionLocal is the factory to create a new Session object
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Dependency function for FastAPI
def get_db() -> Generator[Session, None, None]:
    """
    Provides a database session for a FastAPI request.
    It automatically closes the session after the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
