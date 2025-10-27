# ml/scaling_logic.py (Updated for Leakage Threshold 15% BELOW DMB)

from decimal import Decimal, getcontext
from typing import Dict, Any, List, Optional

# Set precision for Decimal operations
getcontext().prec = 4

# --- V2 LOOKUP TABLES (MOCK DATA) ---

# BASE COST: Base cost for a single adult (EFS=1.0) in a Tier 3 (Multiplier=1.0) city.
BASE_NEEDS_INDEX: Dict[str, Decimal] = {
    "Variable_Essential_Food": Decimal("5000.00"),
    "Variable_Essential_Transport": Decimal("2500.00"),
    "Variable_Essential_Health": Decimal("1500.00"),
    "Scaled_Discretionary_Routine": Decimal("1000.00"),
}

CITY_COST_MULTIPLIERS: Dict[str, Decimal] = {
    "Tier 1": Decimal("1.25"),
    "Tier 2": Decimal("1.10"),
    "Tier 3": Decimal("1.00"),
    "Tier 4": Decimal("0.90"),
}

# 🚨 DEFAULT FALLBACK EFFICIENCY: Used if a comparable "Best User" cohort is NOT found.
# This represents the internal ML estimation of achievable efficiency for each slab.
DEFAULT_EFFICIENCY_FACTORS: Dict[str, Decimal] = {
    "High": Decimal("0.90"),   # High Income: Assume 10% more efficient than average need.
    "Medium": Decimal("1.00"),  # Medium Income: Assume average efficiency (1.0).
    "Low": Decimal("1.05"),    # Low Income: Assume 5% less efficient (needs more buffer).
}

# --- V2 LEAKAGE BUFFER CONSTANT ---
LEAK_SAVINGS_MARGIN_PERCENTAGE = Decimal("0.15")

# Define the ML Logic Engine for Stratified Dependent Scaling (Fin-Traq V2)
def calculate_dynamic_baseline(
    net_income: Decimal,
    equivalent_family_size: Decimal,
    city_tier: str,
    income_slab: str,
    # 🚨 NEW: Optional input to allow the Benchmarking Service to set the factor
    benchmark_efficiency_factor: Optional[Decimal] = None,
    base_needs: Dict[str, Decimal] = BASE_NEEDS_INDEX
) -> Dict[str, Decimal]:
    """
    Calculates the DMB based on the Needs Index, scaled by EFS, City Cost, and the
    Achievable Efficiency derived either from Best User Benchmarking or a default factor.
    """

    # 1. Determine the Efficiency Factor (Benchmarking Fallback Logic)
    if benchmark_efficiency_factor is not None:
        efficiency_factor = benchmark_efficiency_factor
    else:
        # Fallback to the default factor if no specific benchmark is provided
        efficiency_factor = DEFAULT_EFFICIENCY_FACTORS.get(income_slab, Decimal("1.00"))

    # 2. Look up other multipliers
    city_multiplier = CITY_COST_MULTIPLIERS.get(city_tier, Decimal("1.00"))

    dynamic_baselines = {}
    total_minimal_need_dmb = Decimal("0.00")

    # 3. Calculate Category-Specific DMB (Best User Benchmark)
    for category, base_cost in base_needs.items():

        # Category DMB = Base Cost * EFS * City Multiplier * Efficiency Factor
        # This DMB is the "Best User's" spending level for this category.
        category_dmb = (
            base_cost * equivalent_family_size * city_multiplier * efficiency_factor
        ).quantize(Decimal("0.01"))

        # 4. Set the Leakage Threshold (The goal to surpass the 'Best User' benchmark by 15%)
        # If no other users are found, the threshold is the DMB * 0.85
        leakage_threshold_multiplier = Decimal("1.0") - LEAK_SAVINGS_MARGIN_PERCENTAGE
        category_threshold = (category_dmb * leakage_threshold_multiplier).quantize(Decimal("0.01"))

        # Store the Leakage Threshold
        dynamic_baselines[category] = category_threshold
        total_minimal_need_dmb += category_dmb

    # 5. Calculate Final Outputs
    final_leakage_threshold = sum(dynamic_baselines.values()).quantize(Decimal("0.01"))

    dynamic_baselines["Total_Leakage_Threshold"] = final_leakage_threshold
    dynamic_baselines["Total_Minimal_Need_DMB"] = total_minimal_need_dmb.quantize(Decimal("0.01"))
    dynamic_baselines["Potential_Recoverable_Fund"] = (
        dynamic_baselines["Total_Minimal_Need_DMB"] - dynamic_baselines["Total_Leakage_Threshold"]
    ).quantize(Decimal("0.01"))

    return dynamic_baselines
