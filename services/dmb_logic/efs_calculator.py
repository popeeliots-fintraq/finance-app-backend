from decimal import Decimal
from typing import Literal

# --- EFS SCALING FACTORS ---
# These are representative constants. You may update them based on localized or research-backed data.
# Source: Simplified square-root scale or similar equivalence scales.
EFS_CONSTANTS = {
    "HEAD_OF_HOUSEHOLD": Decimal("1.0"),  # First adult (the salary owner)
    "SPOUSE_OR_PARTNER": Decimal("0.5"), # Second adult
    "DEPENDENT_CHILD": Decimal("0.3"),   # Each dependent child/elderly
}

def calculate_equivalent_family_size(
    dependents_count: int, 
    marital_status: Literal["Single", "Married", "Cohabiting"]
) -> Decimal:
    """
    Calculates the Equivalent Family Size (EFS) using a simplified equivalence scale.
    This value is used to scale the Dynamic Minimal Baseline (DMB) for Variable Essential spending.
    
    Args:
        dependents_count: The number of financial dependents (children, elderly).
        marital_status: The user's status ("Single", "Married", "Cohabiting").
        
    Returns:
        The EFS value (e.g., Decimal('1.8'))
    """
    
    # 1. Start with the Head of Household (the user)
    efs = EFS_CONSTANTS["HEAD_OF_HOUSEHOLD"]
    
    # 2. Add the Second Adult (Spouse/Partner) based on marital status
    if marital_status in ["Married", "Cohabiting"]:
        efs += EFS_CONSTANTS["SPOUSE_OR_PARTNER"]
        
    # 3. Add dependents
    if dependents_count > 0:
        efs += EFS_CONSTANTS["DEPENDENT_CHILD"] * Decimal(dependents_count)
        
    # Ensure EFS is rounded to two decimal places for financial calculations
    return efs.quantize(Decimal("0.01"))

# --- Example Usage (for testing) ---
# efs_single_two_dependents = calculate_equivalent_family_size(2, "Single") # EFS = 1.0 + 2*0.3 = 1.60
# efs_married_one_dependent = calculate_equivalent_family_size(1, "Married") # EFS = 1.0 + 0.5 + 1*0.3 = 1.80
