# ml/scaling_logic.py (Updated for Leakage Threshold 15% BELOW DMB)

from decimal import Decimal, getcontext
from typing import Dict, Any

# Set precision for Decimal operations
getcontext().prec = 4 

# Define Standardized Weights for Dependent Categories 
# This now includes Variable Essential (high weight) AND Scaled Discretionary (low weight)
DEPENDENT_CATEGORY_WEIGHTS: Dict[str, Decimal] = {
    # Variable Essential Categories (Budget scales with EFS for necessity)
    "Variable_Essential_Food": Decimal("0.50"),      # Reduced slightly to make room for SD
    "Variable_Essential_Transport": Decimal("0.30"),
    "Variable_Essential_Health": Decimal("0.35"),

    # Scaled Discretionary Category (Budget scales with EFS for routine daily spending cap)
    # This addresses leaks like coffee, office lunch, panipuri, cigarettes (your biggest leaks)
    "Scaled_Discretionary_Routine": Decimal("0.10"), # Low weight ensures a tight budget cap
}

# --- V2 LEAKAGE BUFFER CONSTANT (15% LESS THAN DMB) ---
# This constant defines the intentional margin (savings opportunity) below the DMB.
# Spending above the Leakage Threshold is classified as an immediate 'Leak'.
LEAK_SAVINGS_MARGIN_PERCENTAGE = Decimal("0.15") 
BASE_ALLOCATION_RATE = Decimal("0.20") # Base percentage of income for the DMB calculation

# Define the ML Logic Engine for Stratified Dependent Scaling (Fin-Traq V2)
def calculate_dynamic_baseline(
    net_income: Decimal, 
    equivalent_family_size: Decimal,
    category_weights: Dict[str, Decimal] = DEPENDENT_CATEGORY_WEIGHTS
) -> Dict[str, Decimal]:
    """
    Calculates the Dynamic Minimal Baseline (DMB) and sets the Leakage Threshold 
    15% below the DMB to create an immediate, visible savings opportunity for the user.
    """
    
    # 1. Calculate the Dynamic Minimal Baseline (DMB) - The absolute lowest need
    # DMB = Net Income * Base Allocation Rate * EFS
    total_minimal_need_dmb = net_income * BASE_ALLOCATION_RATE * equivalent_family_size
    
    # 2. Establish the Leakage Threshold (15% below DMB)
    # Threshold = DMB * (1 - 0.15) -> This is the budget limit the user sees
    leakage_threshold_multiplier = Decimal("1.0") - LEAK_SAVINGS_MARGIN_PERCENTAGE
    final_leakage_threshold = total_minimal_need_dmb * leakage_threshold_multiplier
    
    # 3. Stratified Scaling by Category (using the final Leakage Threshold)
    dynamic_baselines = {}
    sum_of_weights = sum(category_weights.values()) # Sum of all weights (e.g., 0.50 + 0.30 + 0.35 + 0.10 = 1.25)
    
    for category, weight in category_weights.items():
        # Calculate the proportional share of the DMB Threshold for this category
        proportional_share = weight / sum_of_weights
        
        # This is the CATEGORY-SPECIFIC Leakage Threshold
        baseline_amount = final_leakage_threshold * proportional_share
        dynamic_baselines[category] = baseline_amount.quantize(Decimal("0.01"))
        
    # Final outputs for the backend Orchestration System
    # This is the line that Fin-Traq V2 will compare against total spending
    dynamic_baselines["Total_Leakage_Threshold"] = final_leakage_threshold.quantize(Decimal("0.01"))
    dynamic_baselines["Total_Minimal_Need_DMB"] = total_minimal_need_dmb.quantize(Decimal("0.01"))

    # The actual recoverable amount is the difference between DMB and the Threshold (15% of DMB)
    dynamic_baselines["Potential_Recoverable_Fund"] = (total_minimal_need_dmb - final_leakage_threshold).quantize(Decimal("0.01"))

    return dynamic_baselines
