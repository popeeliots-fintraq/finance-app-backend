# services/orchestration_service.py (FIRESTORE INTEGRATED)

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from datetime import date, datetime
from fastapi import HTTPException, status

# --- NEW FIRESTORE IMPORTS ---
from google.cloud.firestore import Client as FirestoreClient, Transaction, Batch
# We will use the standard Python Exception, as SQL's NoResultFound is gone
from firebase_admin import firestore

# --- V2 Service Imports ---
from .leakage_service import LeakageService  
from .insight_service import InsightService
from .financial_profile_service import FinancialProfileService

# NOTE: ALL SQL MODEL IMPORTS AND ENUMS (User, SalaryAllocationProfile, etc.) ARE DELETED.
# We will use Pydantic schemas (if needed) and direct dictionary data from Firestore.
# Assuming user_id is the document ID (string) in Firestore
UserIdType = str


class OrchestrationService:
    """
    Core service class for Fin-Traq's Salary Autopilot (Guided Execution).
    Handles DMB calculation, manages the reclaimable salary fund, and generates suggestions.
    """

    # FIX 1: Change DB type hint to FirestoreClient
    def __init__(self, db_client: FirestoreClient, user_id: UserIdType):
        self.db = db_client 
        self.user_id = user_id
        
        # FIX 2: FinancialProfileService constructor must also accept FirestoreClient
        self.financial_profile_service = FinancialProfileService(db_client, user_id) 
        
        # --- Define Firestore Collection Constants ---
        self.USERS_COLLECTION = 'users'
        self.SALARY_PROFILE_COLLECTION = 'salary_profiles'
        self.SMART_RULES_COLLECTION = 'smart_transfer_rules'
        self.TRANSACTIONS_COLLECTION = 'transactions'

    # ----------------------------------------------------------------------
    # V2 ML LOGIC INTEGRATION (EFS + Dynamic Baseline Calculation)
    # ----------------------------------------------------------------------
    # NOTE: The return type must be updated from FinancialProfile (SQL Model)
    def calculate_and_save_financial_profile(self) -> Dict[str, Any]:
        """Delegates the EFS/BEF/DMB calculation to the FinancialProfileService."""
        # The FinancialProfileService handles all persistence to Firestore
        return self.financial_profile_service.calculate_and_save_dmb()
        
    # ----------------------------------------------------------------------
    # REAL-TIME POST-TRANSACTION ORCHESTRATION (Autopilot Trigger)
    # ----------------------------------------------------------------------

    def recalculate_current_period_leakage(self, reporting_period: date) -> Dict[str, Any]:
        """
        Triggers the LeakageService to calculate the current MTD leak,
        and then generates proactive insights based on the new spending status.
        """
        # NOTE: LeakageService and InsightService must also be updated to accept FirestoreClient
        leakage_service = LeakageService(self.db, self.user_id)
        insight_service = InsightService(self.db, self.user_id)
        
        # 1. Calculate Leakage and persist reclaimable fund
        leakage_data = leakage_service.calculate_leakage(reporting_period)  
        
        projected_reclaimable = leakage_data.get('projected_reclaimable_salary', Decimal("0.00"))
        leakage_buckets = leakage_data.get('leakage_buckets')
        
        # 2. --- GENERATE PROACTIVE INSIGHTS (BEHAVIORAL ML) ---
        proactive_insights = insight_service.generate_proactive_leak_insights(
            reporting_period,
            category_leaks=leakage_buckets 
        )
        
        # NOTE: convert_leak_to_goal_if_possible is retained but disabled for Phase 2.
        self.convert_leak_to_goal_if_possible(projected_reclaimable, reporting_period)

        return {
            "projected_reclaimable": projected_reclaimable.quantize(Decimal("0.01")),
            "insights": proactive_insights,
            "leakage_buckets": leakage_buckets 
        }

    def convert_leak_to_goal_if_possible(self, projected_reclaimable: Decimal, reporting_period: date):
        """Phase 3 method stub."""
        return  

    # ----------------------------------------------------------------------
    # CORE ORCHESTRATION LOGIC (GUIDED EXECUTION)
    # ----------------------------------------------------------------------

    def _fetch_available_reclaimable_salary(self, reporting_period: date) -> Dict[str, Decimal]:
        """
        FIX 3: Rewritten for Firestore. Fetches the latest calculated salary profile.
        Returns the document data (or a default if not found).
        """
        # Format the date for Firestore querying (YYYY-MM-DD string)
        period_str = reporting_period.isoformat()
        
        # Query the salary_profiles collection
        query = self.db.collection(self.SALARY_PROFILE_COLLECTION).where(
            'user_id', '==', self.user_id
        ).where(
            'reporting_period', '==', period_str
        ).limit(1).get()
        
        if query:
            # Return the document data as a dictionary
            profile_data = query[0].to_dict()
            # Convert string/float Decimals back to Decimal objects for calculation
            profile_data['projected_reclaimable_salary'] = Decimal(str(profile_data.get('projected_reclaimable_salary', "0.00")))
            profile_data['total_autotransferred'] = Decimal(str(profile_data.get('total_autotransferred', "0.00")))
            profile_data['tax_headroom_remaining'] = Decimal(str(profile_data.get('tax_headroom_remaining', "0.00")))
            return profile_data
        
        # FIX: Return a profile with default zero values if none exists for the period (Dict)
        return {
            'projected_reclaimable_salary': Decimal("0.00"),
            'total_autotransferred': Decimal("0.00"),
            'tax_headroom_remaining': Decimal("0.00")
        }


    def generate_consent_suggestion_plan(self, reporting_period: date) -> Dict[str, Any]:
        """Calculates how the reclaimable fund SHOULD be allocated across active Smart Rules."""
        
        # FIX 4: Use Firestore fetching function
        salary_profile = self._fetch_available_reclaimable_salary(reporting_period)
        
        # Fetch the User Profile (only need to check if they exist)
        user_ref = self.db.collection(self.USERS_COLLECTION).document(self.user_id)
        if not user_ref.get().exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User ID {self.user_id} not found.")

        # Use the money that is NOT yet auto-transferred for the batch suggestion plan
        available_fund = salary_profile['projected_reclaimable_salary'] - salary_profile['total_autotransferred']
        remaining_fund = available_fund
        suggestion_plan: List[Dict[str, Any]] = []
        total_suggested = Decimal("0.00")
        
        if available_fund <= Decimal("500.00"):
            # ... (returns if below threshold) ...
             return {
                "available_fund": available_fund.quantize(Decimal("0.01")),
                "total_suggested": Decimal("0.00"),
                "suggestion_plan": [],
                "remaining_unallocated": available_fund.quantize(Decimal("0.01")),
                "message": "Reclaimable salary below action threshold. Autopilot on standby."
            }

        # 1. Fetch all active Smart Rules, ordered by priority
        # FIX 5: Rewritten for Firestore query
        rules_query = self.db.collection(self.SMART_RULES_COLLECTION).where(
            'user_id', '==', self.user_id
        ).where(
            'is_active', '==', True
        ).order_by('priority', direction=firestore.Query.DESCENDING).get()
        
        active_rules = [doc.to_dict() for doc in rules_query]
        
        # Separate rules based on RuleType value (assuming it's a string field in Firestore)
        # Assuming RuleType.TAX_SAVING.value is 'TAX_SAVING'
        TAX_SAVING_VALUE = 'TAX_SAVING' # Define this constant based on your enum mapping
        tax_rules = [r for r in active_rules if r.get('rule_type') == TAX_SAVING_VALUE]
        other_rules = [r for r in active_rules if r.get('rule_type') != TAX_SAVING_VALUE]
        
        # Get the user's current remaining tax headroom
        remaining_tax_headroom = salary_profile['tax_headroom_remaining']
        
        # 2. --- PRIORITY ALLOCATION: TAX SAVING ---
        for rule in tax_rules:
            # FIX 6: Decimal conversion for rule fields
            rule_target = Decimal(str(rule.get('target_amount_monthly', "0.00")))

            if remaining_fund <= Decimal("0.00"): break
                
            transfer_target = min(rule_target, remaining_fund, remaining_tax_headroom)
            
            if transfer_target > Decimal("0.00"):
                suggestion_plan.append({
                    "rule_id": rule.get('id'), # Assumes rule has an ID field
                    "rule_name": rule.get('name'),
                    "transfer_amount": transfer_target.quantize(Decimal("0.01")),
                    "destination": rule.get('destination_account_name'),
                    "type": rule.get('rule_type')
                })
                
                remaining_fund -= transfer_target
                remaining_tax_headroom -= transfer_target
                total_suggested += transfer_target

        # 3. --- SECONDARY ALLOCATION: OTHER GOALS/STASHES --- (Similar logic using Decimal conversion)
        for rule in other_rules:
            rule_target = Decimal(str(rule.get('target_amount_monthly', "0.00")))
            if remaining_fund <= Decimal("0.00"): break
                
            transfer_amount = min(rule_target, remaining_fund)
            
            if transfer_amount > Decimal("0.00"):
                suggestion_plan.append({
                    "rule_id": rule.get('id'),
                    "rule_name": rule.get('name'),
                    "transfer_amount": transfer_amount.quantize(Decimal("0.01")),
                    "destination": rule.get('destination_account_name'),
                    "type": rule.get('rule_type')
                })
                
                remaining_fund -= transfer_amount
                total_suggested += transfer_amount

        # 4. Finalize and return the plan
        # ... (returns final plan dictionary) ...
        return {
            "available_fund": available_fund.quantize(Decimal("0.01")),
            "remaining_unallocated": remaining_fund.quantize(Decimal("0.01")),
            "total_suggested": total_suggested.quantize(Decimal("0.01")),
            "suggestion_plan": suggestion_plan,
            "message": f"Autopilot suggests reallocating {total_suggested.quantize(Decimal('0.01'))} across goals, prioritizing tax optimization."
        }
        
    # ----------------------------------------------------------------------
    # AUTOPILOT EXECUTION METHOD (CLOSES THE LOOP & HANDLES CONSENT)
    # ----------------------------------------------------------------------
    def record_consent_and_update_balance(self, transfer_plan: List[Dict[str, Any]], reporting_period: date) -> Dict[str, Any]:
        """
        FIX 7: Rewritten for Firestore Transaction/Batch.
        Executes the final Autopilot action: records consent, logs transfer transactions, 
        and updates the Salary Allocation Profile atomically.
        """
        if not transfer_plan:
            return {"status": "success", "message": "No transfers to execute.", "total_transferred": Decimal("0.00"), "transfers_executed": []}

        # 1. Prepare references and data
        period_str = reporting_period.isoformat()
        salary_profile_query = self.db.collection(self.SALARY_PROFILE_COLLECTION).where(
            'user_id', '==', self.user_id
        ).where(
            'reporting_period', '==', period_str
        ).limit(1)
        
        # Using a Firestore Transaction for atomicity
        @firestore.transactional
        def update_in_transaction(transaction: Transaction) -> Dict[str, Any]:
            
            # Fetch the relevant Salary Profile (within the transaction)
            snapshot = salary_profile_query.get(transaction=transaction)
            if not snapshot:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cannot execute Autopilot: Salary Allocation Profile not found for the period.")
            
            salary_profile_doc = snapshot[0]
            salary_profile_data = salary_profile_doc.to_dict()
            profile_ref = salary_profile_doc.reference
            
            # Initialize transfer variables
            current_total_autotransferred = Decimal(str(salary_profile_data.get('total_autotransferred', "0.00")))
            total_transferred = Decimal("0.00")
            executed_transfers = []
            
            # Use a separate Batch for recording the new transactions (optional, could be done in the transaction)
            transaction_batch = self.db.batch()

            # 2. Iterate through the consented plan and execute/record
            for item in transfer_plan:
                # Handle conversion
                transfer_amount = item.get("transfer_amount", Decimal("0.00"))
                if isinstance(transfer_amount, (float, str)):
                    transfer_amount = Decimal(str(transfer_amount)).quantize(Decimal("0.01"))
                
                if transfer_amount <= Decimal("0.00"): continue
                
                # --- A. (External System Mock) Execute UPI Transfer ---
                transfer_successful = True # Assume success for MVP
                
                if transfer_successful:
                    # --- B. Record the Internal Financial Transaction ---
                    new_transaction_data = {
                        "user_id": self.user_id,
                        "transaction_date": datetime.utcnow().isoformat(), # Store as ISO string
                        "amount": str(transfer_amount), # Store Decimal as string for Firestore
                        "description": f"Autopilot Transfer: Fund {item.get('rule_name', 'Goal')}",
                        "category": item.get('type', 'Autopilot Stash'), 
                        "transaction_type": item.get('transaction_type', 'DEBIT_INTERNAL'), # Fallback on service-side constant
                        "smart_rule_id": item.get('rule_id'),
                        "salary_profile_id": profile_ref.id, # Use the Firestore document ID
                        "created_at": firestore.SERVER_TIMESTAMP
                    }
                    
                    # Add new transaction to the batch (or transaction)
                    new_doc_ref = self.db.collection(self.TRANSACTIONS_COLLECTION).document()
                    transaction_batch.set(new_doc_ref, new_transaction_data)
                    
                    total_transferred += transfer_amount
                    executed_transfers.append(item)

            # 3. Update the Salary Profile (Closing the Loop)
            new_total_autotransferred = current_total_autotransferred + total_transferred
            
            # Update the existing document within the transaction
            transaction.update(profile_ref, {
                'total_autotransferred': str(new_total_autotransferred.quantize(Decimal("0.01"))), # Store as string
                'last_updated': firestore.SERVER_TIMESTAMP
            })
            
            # 4. Commit all batched transaction records
            transaction_batch.commit()

            # 5. Return Success Message
            return {
                "status": "success",
                "message": "Autopilot execution complete. Your funds have been efficiently allocated.",
                "total_transferred": total_transferred.quantize(Decimal("0.01")),
                "transfers_executed": executed_transfers
            }
        
        # Execute the transaction function
        return update_in_transaction(self.db.transaction())
