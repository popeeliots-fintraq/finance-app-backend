from decimal import Decimal
from typing import Literal
from .efs_calculator import calculate_equivalent_family_size # Import the EFS function

# --- DMB SCALING WEIGHTS (Stratified Dependent Scaling - SDS) ---
# These constants define the monthly cost per EFS unit for a given essential category.
# Values are simplified examples and should be based on regional/economic data.
SDS_WEIGHTS: dict[str, Decimal] = {
    # Variable Essential Categories (Scale with EFS)
    "Groceries": Decimal("2500.00"),  # Cost per EFS unit per month
    "Healthcare": Decimal("800.00"),
    "Utilities": Decimal("1500.00"),
    
    # Non-scaling/Fixed/Discretionary Categories (Baseline is usually 0 unless custom rule is applied)
    "Transportation": Decimal("0.00"), # Often a Fixed Commitment/Debt, not scaled
    "Discretionary_Entertainment": Decimal("0.00"), # Baseline is always 0 for leaks
}

def calculate_dynamic_minimal_baseline(
    category_name: str,
    efs_value: Decimal
) -> Decimal:
    """
    Calculates the Dynamic Minimal Baseline (DMB) for a Variable Essential category.
    
    The DMB is calculated as: DMB = SDS_Weight * EFS_Value
    
    Args:
        category_name: The Variable Essential category (e.g., 'Groceries').
        efs_value: The calculated Equivalent Family Size (EFS) for the user.
        
    Returns:
        The calculated DMB amount for the month.
    """
    
    sds_weight = SDS_WEIGHTS.get(category_name)
    
    if sds_weight is None:
        # If the category is not defined as Variable Essential, its minimal baseline is zero
        # (e.g., Discretionary categories, or Fixed Commitments handled elsewhere).
        return Decimal("0.00")
    
    # DMB Calculation: DMB = SDS_Weight * EFS_Value
    dmb = sds_weight * efs_value
    
    return dmb.quantize(Decimal("0.01"))

# --- Example Usage (How leakage_service will use it) ---
# efs = calculate_equivalent_family_size(dependents_count=1, marital_status="Married") # e.g., 1.80
# groceries_dmb = calculate_dynamic_minimal_baseline("Groceries", efs) # 2500 * 1.80 = 4500.00
# entertainment_dmb = calculate_dynamic_minimal_baseline("Discretionary_Entertainment", efs) # 0.00
