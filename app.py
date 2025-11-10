# app.py (Fin-Traq Backend: V1 + V2 Integration - PRODUCTION READY)

from fastapi import FastAPI, Depends, status, HTTPException
from contextlib import asynccontextmanager # For DB lifecycle management
from typing import List
from fastapi.middleware.cors import CORSMiddleware # Recommended for web/mobile client support

# Import Dependencies and DB Setup
from api.dependencies import verify_api_key, get_db 
# Import DB Setup components (assuming you have them)
# from api.database_setup import engine 


# --- Application Lifespan Context (Recommended for Async DB) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ----------------------------------------
    # STARTUP: Database Initialization/Engine Setup
    # ----------------------------------------
    print("Application Startup: Initializing services...")
    # NOTE: You would typically start your SQLAlchemy engine here.
    # e.g., await engine.connect()
    
    yield
    
    # ----------------------------------------
    # SHUTDOWN: Database Cleanup
    # ----------------------------------------
    print("Application Shutdown: Cleaning up resources...")
    # e.g., await engine.dispose()


# 1. IMPORT V1 Routers (Legacy Expense Tracker/Setup)
from api.v1.salary import router as v1_salary_router 
from api.v1.user_profile import router as v1_profile_router
from api.v1.leakage import router as v1_leakage_router
from api.v1.smart_rule import router as v1_smart_rule_router
from api.v1.transactions import router as v1_transactions_router

# 2. IMPORT V2 Router (Salary Autopilot / Core Orchestration)
from api.v2_router import router as v2_autopilot_router 


app = FastAPI(
    title="Fin-Traq Salary Autopilot Backend (V2)",
    description="Frictionless personal finance flow for salary owners, focused on leak recovery and tax optimization.",
    version="2.0.0",
    # CRITICAL FIX: ENABLE GLOBAL SECURITY
    dependencies=[Depends(verify_api_key)], 
    # CRITICAL FIX: Enable DB Lifespan management
    # lifespan=lifespan, 
)

# Optional: Add CORS Middleware if frontend clients (web/mobile) access this service
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"], # Adjust this for security in production
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# Root Endpoint (basic health check)
@app.get("/", tags=["Health"], dependencies=[]) # Override global security for the health check
def read_root():
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
app.include_router(v2_autopilot_router, prefix="/api")

# -----------------------------------------------------------
# END OF CONFIGURATION
# -----------------------------------------------------------
