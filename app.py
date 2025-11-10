# app.py (Fin-Traq Backend: V1 + V2 Integration)

from fastapi import FastAPI
from api.dependencies import verify_api_key, get_db # Assuming these global dependencies are needed (CRITICAL for security/DB)
from fastapi import Depends
# NOTE: If you need DB Lifespan management, you'd add the imports from the previous app.py draft here.


# 1. IMPORT V1 Routers (Legacy Expense Tracker/Setup)
from api.v1.salary import router as v1_salary_router 
from api.v1.user_profile import router as v1_profile_router
from api.v1.leakage import router as v1_leakage_router
from api.v1.smart_rule import router as v1_smart_rule_router
from api.v1.transactions import router as v1_transactions_router

# 2. IMPORT V2 Router (Salary Autopilot / Core Orchestration)
# We import the router instance defined within v2_router.py
from api.v2_router import router as v2_autopilot_router 


app = FastAPI(
    title="Fin-Traq Salary Autopilot Backend (V2)",
    description="Frictionless personal finance flow for salary owners, focused on leak recovery and tax optimization.",
    version="2.0.0",
    # 🌟 OPTIONAL: Add global dependencies (like API Key verification) here for ALL endpoints
    # dependencies=[Depends(verify_api_key)], 
)

# Root Endpoint (basic health check)
@app.get("/", tags=["Health"])
def read_root():
    # Updated message to reflect the V2 status and Leak Finder completion
    return {"message": "✅ Fin-Traq Backend V2 is running. Leak Finder and Autopilot services active. Access V2 endpoints at /api/v2/..."}

# -----------------------------------------------------------
# 3. ROUTER REGISTRATION
# -----------------------------------------------------------

# INCLUDE V1 Routers (Prefix ensures all V1 paths start with /api/v1)
app.include_router(v1_salary_router, prefix="/api/v1")
app.include_router(v1_profile_router, prefix="/api/v1")
app.include_router(v1_leakage_router, prefix="/api/v1")
app.include_router(v1_smart_rule_router, prefix="/api/v1")
app.include_router(v1_transactions_router, prefix="/api/v1")

# INCLUDE V2 Router (Prefix ensures all V2 paths start with /api/v2)
# Since v2_autopilot_router already uses the internal prefix of "/v2",
# registering it under prefix="/api" results in the final paths: /api/v2/...
app.include_router(v2_autopilot_router, prefix="/api")

# -----------------------------------------------------------
# END OF CONFIGURATION
# -----------------------------------------------------------
