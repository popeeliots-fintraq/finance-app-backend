# db/base.py

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    Base class which provides automated table name
    and represents the declarative base for all ORM models.
    """
    pass

# Import all models here so that Base has them before being
# imported by Alembic, etc.
# from . import models
