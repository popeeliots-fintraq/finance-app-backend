# services/leakage_service.py (Focus on the calculate_leakage method)

# ... (Previous imports and helper methods remain the same) ...

    def calculate_leakage(self) -> Dict[str, Any]:
        """
        Calculates leakage amount using the refined Stratified Dependent Scaling (SDS) baseline.
        Implements the three-bucket leak calculation for the 'Leakage Bucket View.'
        """
        
        try:
            profile_data = self._fetch_profile_data_and_baselines()
        except NoResultFound as e:
            # Handle error gracefully
            return {"error": str(e)} 

        dynamic_baselines = profile_data["dynamic_baselines"]
        current_spends = self._mock_leakage_spends(dynamic_baselines) 
        
        leakage_buckets: List[Dict[str, Any]] = []
        total_leakage = Decimal("0.00")
        
        # --- 1. Calculate Leakage for SCALED Categories (VE & SD) ---
        # This covers overspending above the DMB-15% Threshold
        for category, threshold in dynamic_baselines.items():
            
            # Skip the summary items from the baseline results
            if category in ["Total_Leakage_Threshold", "Total_Minimal_Need_DMB", "Potential_Recoverable_Fund"]:
                continue
                
            spend = current_spends.get(category, Decimal("0.00"))
            
            # Leak: Max(0, Actual Spend - Leakage Threshold)
            leak_amount = max(Decimal("0.00"), spend - threshold)
            
            if leak_amount > Decimal("0.00"):
                total_leakage += leak_amount
                
                # Build the Leakage Bucket View structure
                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(), 
                    "baseline_threshold": threshold.quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": "Above Scaled Threshold",
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": f"{(leak_amount / spend) * 100:.2f}%" if spend > Decimal("0.00") else "0.00%"
                })
        
        # --- 2. Calculate Leakage for PURE DISCRETIONARY (PD) Categories ---
        # 100% of this spend is a leak
        pd_categories = ["Pure_Discretionary_DiningOut", "Pure_Discretionary_Gadget"]
        
        for category in pd_categories:
            spend = current_spends.get(category, Decimal("0.00"))
            
            if spend > Decimal("0.00"):
                leak_amount = spend 
                total_leakage += leak_amount
                
                leakage_buckets.append({
                    "category": category.replace('_', ' ').title(),
                    "baseline_threshold": Decimal("0.00").quantize(Decimal("0.01")),
                    "spend": spend.quantize(Decimal("0.01")),
                    "leak_source": "100% Discretionary Spend",
                    "leak_amount": leak_amount.quantize(Decimal("0.01")),
                    "leak_percentage_of_spend": "100.00%"
                })

        # --- 3. FIX: NO GUARANTEED FUND ADDITION HERE ---
        # The 15% margin defines the threshold; the leak is the money spent above that line. 
        # The recovered amount is the money the user DID NOT spend.
        
        # 4. Build reclaimable salary projection logic
        projected_reclaimable_salary = total_leakage
        
        return {
            "total_leakage_amount": total_leakage.quantize(Decimal("0.01")),
            "projected_reclaimable_salary": projected_reclaimable_salary.quantize(Decimal("0.01")),
            "leakage_buckets": leakage_buckets
        }
