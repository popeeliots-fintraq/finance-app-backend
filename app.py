# app.py

from fastapi import FastAPI
# 1. IMPORT the new salary router
from api.v1.salary import router as salary_router 
from api.v1.user_profile import router as profile_router
from api.v1.leakage import router as leakage_router
from api.v1.smart_rule import router as smart_rule_router
from api.v1.transactions import router as transactions_router

# 🚨 V2 ADDITION: Import the new consolidated V2 router
from api import v2_router 

app = FastAPI(
    title="Fin-Traq Backend API",
    version="V2"
)

# Root Endpoint (basic health check)
@app.get("/")
def read_root():
    # 🚨 Updated message to reflect the V2 status and Leak Finder completion
    return {"message": "✅ Fin-Traq Backend V2 is running. Leak Finder and Autopilot services active."}

# 2. INCLUDE the V1 Routers
app.include_router(salary_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(leakage_router, prefix="/api/v1")
app.include_router(smart_rule_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")

# 🚨 V2 ADDITION: INCLUDE the new V2 router
# Note: The prefix="/api" ensures the routes are accessible at /api/v2/...
# since v2_router.py already defines the internal prefix as "/v2".
app.include_router(v2_router.router, prefix="/api")
