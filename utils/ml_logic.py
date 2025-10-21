# utils/ml_logic.py

from decimal import Decimal
from typing import Dict, List, Tuple

# -------------------------------------------------------------
# --- V2: STRATIFIED DEPENDENT SCALING (SDS) CONFIGURATION ---
# -------------------------------------------------------------

# Standardized weights for different dependent categories (based on OECD modified equivalence scale concept). 
# Used to adjust the consumption unit of different household members. [cite: 2025-10-20]
STANDARD_DEPENDENT_WEIGHTS: Dict[str, Decimal] = {
    "first_adult": Decimal("1.0"),
    "additional_adult": Decimal("0.5"),
    "child": Decimal("0.3"),
    "infant": Decimal("0.2"),
    "elderly": Decimal("0.4")
}

# Base proportion of income allocated to discretionary spending categories (as a ratio)
# These weights drive financial orchestration and goal suggestion.
DISCRETIONARY_CATEGORY_WEIGHTS: Dict[str, Decimal] = {
    "dining_out": Decimal("0.35"), 
    "entertainment": Decimal("0.25"),
    "shopping_non_essential": Decimal("0.40") 
}

# --- 1. EQUIVALENT FAMILY SIZE (EFS) CALCULATION ---

def calculate_equivalent_family_size(user_id: str) -> float:
    """
    Implements the Equivalent Family Size (EFS) calculation function in the backend.
    [cite: 2025-10-20]
    
    NOTE: This is a simplified mock implementation.
    A full implementation would query user profile data (dependents, location, etc.) 
    to determine the final EFS weight.
    """
    # Mock: Assume EFS is 1.0 (individual) + 0.5 (for one dependent)
    return 1.5

# --- 2. DYNAMIC BASELINE ADJUSTMENT (DMB) ---

def calculate_dynamic_baseline(net_income: Decimal, efs: float) -> Dict[str, Decimal]:
    """
    Updates the core ML logic for dynamic baseline adjustment using the EFS.
    This defines the initial Dynamic Minimal Baseline (DMB) for core spending categories.
    [cite: 2025-10-20, 2025-10-17]
    
    NOTE: This is a simplified mock implementation for the initial DMB.
    """
    
    # Mock base consumption unit values (in rupees) based on an average income
    BASE_HOUSING_UNIT = Decimal("15000.00")
    BASE_GROCERIES_UNIT = Decimal("4000.00")
    BASE_TRANSPORT_UNIT = Decimal("2500.00")
    BASE_UTILITY_UNIT = Decimal("1500.00")
    
    # Apply EFS (scaling factor) to dependent categories.
    groceries_baseline = BASE_GROCERIES_UNIT * Decimal(str(efs))
    
    # Return the Dynamic Minimal Baseline (DMB)
    return {
        "housing": BASE_HOUSING_UNIT, # Often not scaled by EFS in simple models
        "groceries": groceries_baseline.quantize(Decimal('0.01')),
        "transport": BASE_TRANSPORT_UNIT,
        "utility": BASE_UTILITY_UNIT * Decimal(str(efs)).quantize(Decimal('0.01')) # Utility often scales too
    }

# --- 3. STRATIFIED DEPENDENT SCALING (SDS) REFINEMENT ---

def calculate_stratified_dependent_scaling(
    dmb: Dict[str, Decimal], 
    user_dependent_structure: List[Tuple[str, int]]
) -> Dict[str, Decimal]:
    """
    Refines the Dynamic Minimal Baseline (DMB) using Stratified Dependent Scaling (SDS) for Fin-Traq V2.
    [cite: 2025-10-20]
    
    This adjusts DMB categories based on the specific type and count of dependents 
    using the STANDARD_DEPENDENT_WEIGHTS.
    
    Args:
        dmb: The Dynamic Minimal Baseline calculated by calculate_dynamic_baseline.
        user_dependent_structure: List of (dependent_type, count), e.g., 
                                  [('additional_adult', 1), ('child', 2)].
                                  
    Returns:
        A more accurately scaled Dynamic Minimal Baseline (DMB) for leak analysis.
    """
    scaled_baseline = dmb.copy()
    
    # 1. Calculate a more precise EFS scaling factor based on stratification
    # Start with the first adult (1.0) and add the specific weights of dependents
    precise_efs_scaling_factor = STANDARD_DEPENDENT_WEIGHTS["first_adult"]
    
    for dep_type, count in user_dependent_structure:
        weight = STANDARD_DEPENDENT_WEIGHTS.get(dep_type)
        if weight is not None: 
            precise_efs_scaling_factor += weight * Decimal(str(count))

    # 2. Apply refined scaling to dependent categories (using original per-unit bases)
    
    # Assuming the original unit values are needed for accurate recalculation:
    BASE_GROCERIES_UNIT = Decimal("4000.00")
    BASE_UTILITY_UNIT = Decimal("1500.00")
    
    scaled_baseline["groceries"] = (BASE_GROCERIES_UNIT * precise_efs_scaling_factor).quantize(Decimal('0.01'))
    scaled_baseline["utility"] = (BASE_UTILITY_UNIT * precise_efs_scaling_factor).quantize(Decimal('0.01'))
    
    return scaled_baseline
