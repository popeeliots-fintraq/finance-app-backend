# app.py

from fastapi import FastAPI
# 1. IMPORT the new salary router
from api.v1.salary import router as salary_router 

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
