# db/user_profile.py

from sqlalchemy import Column, String, Integer, PrimaryKeyConstraint, ForeignKey
from .base import Base 

class UserProfile(Base):
    """
    SQLAlchemy ORM Model for the 'user_profile' table.
    Stores dependent and household data required for EFS calculation and ML scaling.
    """
    
    __tablename__ = "user_profile"
    
    # Core User ID - Primary Key
    user_id = Column(String(255), primary_key=True) 
    
    # EFS Calculation Inputs
    
    # 1. Family Structure
    # Total number of adults in the household (user + partner/spouse)
    num_adults = Column(Integer, nullable=False, default=1) 
    
    # 2. Number of Dependent Children
    num_children = Column(Integer, nullable=False, default=0)
    
    # 3. Age Brackets (Simplified input for weighted scaling)
    # The EFS formula typically assigns a higher weight to older children/dependents
    num_dependents_under_6 = Column(Integer, nullable=False, default=0)
    num_dependents_6_to_17 = Column(Integer, nullable=False, default=0)
    num_dependents_over_18 = Column(Integer, nullable=False, default=0)
    
    # Fin-Traq V2 Calculated Output
    # This will be calculated by a backend function and stored here
    equivalent_family_size = Column(DECIMAL(4, 2), nullable=False, default=Decimal("1.00")) 
    
    # You may also want a foreign key reference, but for simplicity, we use user_id as PK
    __table_args__ = (
        PrimaryKeyConstraint('user_id', name='pk_user_profile'),
    )
