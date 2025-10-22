# ml/weights_config.py

from typing import Dict, Any
from decimal import Decimal

# --- V2 ML Weights Configuration ---
# These weights define the standardized factor applied to different spending 
# categories when calculating the dynamic minimal baseline for Fin-Traq V2.
# This configuration corresponds to the deployed environment flag: ML_WEIGHTS_VERSION=v2.0

V2_ML_WEIGHTS: Dict[str, Dict[str, Decimal]] = {
    # 1. CORE LIVING EXPENSES (Generally less recoverable, high baseline priority)
    "CORE_LIVING": {
        "RENT_MORTGAGE": Decimal("0.05"),  # Very low potential for 'leakage' recovery
        "UTILITIES_BILLS": Decimal("0.10"),
        "GROCERIES_ESSENTIALS": Decimal("0.30"),
        "HEALTHCARE": Decimal("0.15"),
    },
    
    # 2. STRATIFIED DEPENDENT SPENDING (High variability, key for dynamic baseline)
    "STRATIFIED_DEPENDENT": {
        "EDUCATION_FEE": Decimal("0.55"),  # Moderately recoverable (e.g., unnecessary private tuition)
        "TRANSPORT_COMMUTE": Decimal("0.40"),
        "CHILD_CARE_SUPPLIES": Decimal("0.25"),
    },

    # 3. DISCRETIONARY & LIFESTYLE (High potential for leakage recovery)
    "DISCRETIONARY_LIFESTYLE": {
        "EATING_OUT_COFFEE": Decimal("0.85"), # High potential leakage
        "SUBSCRIPTIONS_ENTERTAINMENT": Decimal("0.70"),
        "SHOPPING_GENERAL": Decimal("0.90"),
    },

    # 4. DEBT & GOALS (Usually managed by Smart Rules, factor is for baseline calculation)
    "DEBT_GOALS": {
        "LOAN_REPAYMENT": Decimal("0.05"),
        "INVESTMENT_SAVINGS": Decimal("0.00"),
    }
}

# General constant for the V2 scaling factor (can be adjusted later)
DEFAULT_BASELINE_SCALING_FACTOR = Decimal("0.65")
