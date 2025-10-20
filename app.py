# app.py

from fastapi import FastAPI
# 1. IMPORT the new salary router
from api.v1.salary import router as salary_router 
from api.v1.user_profile import router as profile_router
from api.v1.leakage import router as leakage_router
from api.v1.smart_rule import router as smart_rule_router
app = FastAPI(
    title="Fin-Traq Backend API",
    version="V2"
)

# Root Endpoint (basic health check)
@app.get("/")
def read_root():
    return {"message": "Welcome to Fin-Traq V2 Backend! Running Salary Autopilot Logic."}

# 2. INCLUDE the new Salary Router
app.include_router(salary_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(leakage_router, prefix="/api/v1")
app.include_router(smart_rule_router, prefix="/api/v1")
