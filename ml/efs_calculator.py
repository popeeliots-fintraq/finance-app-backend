# ml/efs_calculator.py

from decimal import Decimal, getcontext
from typing import Dict, Any

# Set precision for Decimal operations
getcontext().prec = 4

def calculate_equivalent_family_size(profile_data: Dict[str, Any]) -> Decimal:
    """
    Calculates the Equivalent Family Size (EFS) using a simplified, weighted scale.
    This factor is critical for dynamically adjusting the minimal baseline 
    in the Stratified Dependent Scaling (Fin-Traq V2) ML logic. [cite: 2025-10-20]
    
    Formula based on a modified scale:
    - First Adult (User): 1.00
    - Additional Adults: 0.75
    - Dependents 18+: 0.50
    - Dependents 6-17: 0.33
    - Dependents <6: 0.25
    """
    
    num_adults = profile_data.get('num_adults', 1)
    num_dependents_under_6 = profile_data.get('num_dependents_under_6', 0)
    num_dependents_6_to_17 = profile_data.get('num_dependents_6_to_17', 0)
    num_dependents_over_18 = profile_data.get('num_dependents_over_18', 0)
    
    # --- EFS Calculation ---
    
    # 1. First Adult Base
    efs = Decimal("1.00")
    
    # 2. Additional Adults (Partner/Spouse)
    if num_adults > 1:
        efs += Decimal(num_adults - 1) * Decimal("0.75")
        
    # 3. Add Dependents based on age weights
    efs += Decimal(num_dependents_over_18) * Decimal("0.50")
    efs += Decimal(num_dependents_6_to_17) * Decimal("0.33")
    efs += Decimal(num_dependents_under_6) * Decimal("0.25")
    
    return efs.quantize(Decimal("0.01"))
