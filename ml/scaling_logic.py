# ml/scaling_logic.py (Updated for Leakage Threshold < DMB)

from decimal import Decimal, getcontext
from typing import Dict, Any

# Set precision for Decimal operations
getcontext().prec = 4 

# Define Standardized Weights for Dependent Categories (Used for internal distribution)
DEPENDENT_CATEGORY_WEIGHTS: Dict[str, Decimal] = {
    "Variable_Essential_Food": Decimal("0.55"),
    "Variable_Essential_Transport": Decimal("0.30"),
    "Variable_Essential_Health": Decimal("0.65"),
}

# --- V2 LEAKAGE BUFFER CONSTANT (15% LESS THAN DMB) ---
# This constant defines the intentional margin (savings opportunity) below the DMB.
LEAK_SAVINGS_MARGIN_PERCENTAGE = Decimal("0.15") 
BASE_ALLOCATION_RATE = Decimal("0.20") 

# Define the ML Logic Engine for Stratified Dependent Scaling (Fin-Traq V2)
def calculate_dynamic_baseline(
    net_income: Decimal, 
    equivalent_family_size: Decimal,
    category_weights: Dict[str, Decimal] = DEPENDENT_CATEGORY_WEIGHTS
) -> Dict[str, Decimal]:
    """
    Calculates the Dynamic Minimal Baseline (DMB) and sets the Leakage Threshold 
    15% below the DMB, creating an immediate, visible savings opportunity.
    """
    
    # 1. Calculate the Dynamic Minimal Baseline (DMB) - The absolute lowest need
    total_minimal_need_dmb = net_income * BASE_ALLOCATION_RATE * equivalent_family_size
    
    # 2. Establish the Leakage Threshold (15% below DMB)
    # Threshold = DMB * (1 - 0.15)
    leakage_threshold_multiplier = Decimal("1.0") - LEAK_SAVINGS_MARGIN_PERCENTAGE
    final_leakage_threshold = total_minimal_need_dmb * leakage_threshold_multiplier
    
    # 3. Stratified Scaling by Category (using the final Leakage Threshold)
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

    # The actual recoverable amount is the difference between DMB and the Threshold
    dynamic_baselines["Potential_Recoverable_Fund"] = (total_minimal_need_dmb - final_leakage_threshold).quantize(Decimal("0.01"))

    return dynamic_baselines
