# db/base.py

from typing import Any
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

# Define the common base class for all models
class Base(AsyncAttrs, DeclarativeBase, MappedAsDataclass):
    __abstract__ = True
    
    # Optional: Define a column to use as primary key
    # id: Mapped[int] = mapped_column(primary_key=True) 

    # Recommended: Include the default to handle typing
    type_annotation_map = {
        dict[str, Any]: dict,
    }
