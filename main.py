"""
DocScan Pro — FastAPI Backend
Handles: Auth, File Conversion, Payments (Razorpay), Admin Dashboard
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

from app.routers import auth, convert, payments, admin
from app.database import engine, Base

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="DocScan Pro API",
    description="Document scanning and conversion API",
    version="1.0.0",
    docs_url="/docs",  # Disable in production: docs_url=None
    redoc_url=None
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router,     prefix="/api/v1/auth",     tags=["Authentication"])
app.include_router(convert.router,  prefix="/api/v1/convert",  tags=["File Conversion"])
app.include_router(payments.router, prefix="/api/v1/payments", tags=["Payments"])
app.include_router(admin.router,    prefix="/api/v1/admin",    tags=["Admin"])

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "DocScan Pro API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
