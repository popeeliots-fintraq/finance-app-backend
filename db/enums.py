# db/enums.py

import enum
from sqlalchemy import TypeDecorator, String

class CityTier(enum.Enum):
    """Tier classification for cost-of-living adjustment (Benchmarking)."""
    TIER_1 = "T1" # High cost (e.g., Mumbai, Delhi, Bengaluru)
    TIER_2 = "T2" # Medium cost
    TIER_3 = "T3" # Low cost

class IncomeSlab(enum.Enum):
    """Categorization for income-based cohort filtering (Benchmarking)."""
    SLAB_A = "1M+"
    SLAB_B = "500K-1M"
    SLAB_C = "200K-500K"
    SLAB_D = "Below 200K"

class SDSWeightClass(enum.Enum):
    """Stratified Dependent Scaling (SDS) category for DMB calculation."""
    FIXED_ESSENTIAL = "Fixed_Essential"          # Rent, EMI, Insurance (Non-leakage)
    VARIABLE_ESSENTIAL = "Variable_Essential"    # Groceries, Transport (Leakage possible based on DMB)
    PURE_DISCRETIONARY = "Pure_Discretionary"    # Dining Out, Subscriptions (Max leakage potential)
    TAX_OPTIMIZATION = "Tax_Optimization"        # Investments, ELSS (Goal/Maximizer)

class TransactionStatus(enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Custom TypeDecorator for storing Python Enums as native Postgres ENUMs (if using native ENUMs)
# For simplicity with Supabase (which often uses TEXT fields for enums), we can use String type
class EnumString(TypeDecorator):
    """Ensures Enum values are stored as strings."""
    impl = String
    cache_ok = True

    def __init__(self, enum_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enum_type = enum_type

    def process_bind_param(self, value, dialect):
        if value is not None:
            return value.value
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return self.enum_type(value)
        return value
