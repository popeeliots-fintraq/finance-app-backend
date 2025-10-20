# ml/scaling_logic.py

from decimal import Decimal
from typing import Dict, Any

# Define Standardized Weights for Dependent Categories [cite: 2025-10-20]
# These weights represent the proportional cost factor relative to the single-adult baseline.
# These values are examples and would be tuned with real data.
DEPENDENT_CATEGORY_WEIGHTS: Dict[str, Decimal] = {
    # Essential variable spending categories that are highly affected by household size
    "Variable_Essential_Food": Decimal("0.55"),  # Food spending is highly scalable
    "Variable_Essential_Transport": Decimal("0.30"), # Transport costs scale moderately
    "Variable_Essential_Health": Decimal("0.65"),  # Health costs scale highly
    # Other dependent categories can be added here
}

# Define the ML Logic Engine for Stratified Dependent Scaling (Fin-Traq V2) [cite: 2025-10-20]
def calculate_dynamic_baseline(
    net_income: Decimal, 
    equivalent_family_size: Decimal,
    category_weights: Dict[str, Decimal] = DEPENDENT_CATEGORY_WEIGHTS
) -> Dict[str, Decimal]:
    """
    Updates the core ML logic for dynamic baseline adjustment using the EFS. [cite: 2025-10-20]
    
    This function simulates how the EFS factor adjusts the 'minimal acceptable' 
    spending baseline for core variable categories, helping to identify "leaks" (overspending 
    relative to need). [cite: 2025-10-15, 2025-10-20]
    
    Args:
        net_income: The user's net monthly income.
        equivalent_family_size: The EFS factor calculated from user_profile.
        category_weights: Standardized weights for different dependent categories.
        
    Returns:
        A dictionary of adjusted minimal baseline amounts per category.
    """
    
    # 🚨 NOTE: Base_Allocation_Rate is a simplified placeholder. In a real ML model, 
    # this would come from a regression model based on income quintiles, location, etc.
    BASE_ALLOCATION_RATE = Decimal("0.20") # 20% of income for total Variable Essential
    
    # 1. Calculate the base minimal allocation amount for Variable Essential spending
    total_variable_base = net_income * BASE_ALLOCATION_RATE
    
    # 2. Apply Dynamic Baseline Adjustment using EFS
    # The EFS acts as a multiplier to scale the total base amount to the household size.
    # EFS = 1.00 (single adult) means no scaling. EFS = 1.75 means 75% more baseline spending needed.
    dynamically_adjusted_total_base = total_variable_base * equivalent_family_size
    
    # 3. Stratified Scaling by Category
    dynamic_baselines = {}
    
    for category, weight in category_weights.items():
        # Distribute the dynamically adjusted total base across weighted categories
        # The sum of all weights should ideally equal 1.00 for clean distribution.
        # This implementation scales the total based on each category's relative importance (weight).
        baseline_amount = dynamically_adjusted_total_base * weight 
        dynamic_baselines[category] = baseline_amount.quantize(Decimal("0.01"))
        
    # Example: return the adjusted total baseline (used for leakage assessment)
    dynamic_baselines["Total_Dynamic_Baseline"] = dynamically_adjusted_total_base.quantize(Decimal("0.01"))
    
    return dynamic_baselines
