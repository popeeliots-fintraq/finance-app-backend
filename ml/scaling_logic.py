# ml/scaling_logic.py (Updated for Leakage Threshold 15% BELOW DMB)

from decimal import Decimal, getcontext
from typing import Dict, Any, List

# Set precision for Decimal operations
getcontext().prec = 4

# --- V2 LOOKUP TABLES (MOCK DATA) ---
# NOTE: In a production environment, these should be loaded from a config DB or file
CITY_COST_MULTIPLIERS: Dict[str, Decimal] = {
    "Tier 1": Decimal("1.25"), # Highest cost cities (e.g., Mumbai, Delhi, Bangalore)
    "Tier 2": Decimal("1.10"),
    "Tier 3": Decimal("1.00"), # Baseline
    "Tier 4": Decimal("0.90"),
}

# Income weights adjust the DMB based on the user's salary band/percentile
# This implements the 'Ability' factor to ensure a comfortable baseline.
INCOME_WEIGHTS: Dict[str, Decimal] = {
    "High": Decimal("1.10"), # Top 25% of the user base
    "Medium": Decimal("1.00"),
    "Low": Decimal("0.90"),
}

# Define Standardized Weights for Dependent Categories
DEPENDENT_CATEGORY_WEIGHTS: Dict[str, Decimal] = {
    "Variable_Essential_Food": Decimal("0.50"),
    "Variable_Essential_Transport": Decimal("0.30"),
    "Variable_Essential_Health": Decimal("0.35"),
    "Scaled_Discretionary_Routine": Decimal("0.10"),
}

# --- V2 LEAKAGE BUFFER CONSTANT (15% LESS THAN DMB) ---
LEAK_SAVINGS_MARGIN_PERCENTAGE = Decimal("0.15")
BASE_ALLOCATION_RATE = Decimal("0.20") # Base percentage of income for the DMB calculation

# Define the ML Logic Engine for Stratified Dependent Scaling (Fin-Traq V2)
def calculate_dynamic_baseline(
    net_income: Decimal,
    equivalent_family_size: Decimal,
    city_tier: str,             # New: Geographical Cost Factor
    income_slab: str,           # New: Ability Factor (e.g., "High", "Medium", "Low")
    category_weights: Dict[str, Decimal] = DEPENDENT_CATEGORY_WEIGHTS
) -> Dict[str, Decimal]:
    """
    Calculates the Dynamic Minimal Baseline (DMB) using EFS, City Tier, and Income Slab,
    and then sets the Leakage Threshold 15% below the DMB.
    """

    # 1. Apply City and Income Weights
    city_multiplier = CITY_COST_MULTIPLIERS.get(city_tier, Decimal("1.00"))
    income_multiplier = INCOME_WEIGHTS.get(income_slab, Decimal("1.00"))

    # 2. Calculate the Dynamic Minimal Baseline (DMB) - The Recommended/Safe Ceiling
    # DMB = Net Income * Base Allocation Rate * EFS * City Multiplier * Income Multiplier
    total_minimal_need_dmb = (
        net_income * BASE_ALLOCATION_RATE * equivalent_family_size * city_multiplier * income_multiplier
    )

    # 3. Establish the Leakage Threshold (15% below DMB) - The Savings Trigger Target
    leakage_threshold_multiplier = Decimal("1.0") - LEAK_SAVINGS_MARGIN_PERCENTAGE
    final_leakage_threshold = total_minimal_need_dmb * leakage_threshold_multiplier

    # 4. Stratified Scaling by Category
    dynamic_baselines = {}
    sum_of_weights = sum(category_weights.values())

    for category, weight in category_weights.items():
        proportional_share = weight / sum_of_weights
        
        # This is the CATEGORY-SPECIFIC Leakage Threshold
        baseline_amount = final_leakage_threshold * proportional_share
        dynamic_baselines[category] = baseline_amount.quantize(Decimal("0.01"))

    # Final outputs for the backend Orchestration System
    dynamic_baselines["Total_Leakage_Threshold"] = final_leakage_threshold.quantize(Decimal("0.01"))
    dynamic_baselines["Total_Minimal_Need_DMB"] = total_minimal_need_dmb.quantize(Decimal("0.01"))
    dynamic_baselines["Potential_Recoverable_Fund"] = (total_minimal_need_dmb - final_leakage_threshold).quantize(Decimal("0.01"))

    return dynamic_baselines
