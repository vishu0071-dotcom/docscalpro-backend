"""
Admin Router — Protected endpoints for app owner
View all users, download logs, revenue stats
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from app.database import get_db, User, Conversion, PaymentLog, DownloadLog, PlanEnum
from app.routers.auth import verify_token

router = APIRouter()

ADMIN_EMAIL = "admin@docscalpro.com"  # Set your admin email here

def get_admin_user(authorization: str = None, db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    user_id = verify_token(authorization.split(" ")[1])
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ─── Stats Dashboard ───────────────────────────────────────────
@router.get("/stats")
async def get_stats(
    authorization: str = None,
    db: Session = Depends(get_db)
):
    get_admin_user(authorization, db)

    total_users = db.query(func.count(User.id)).scalar()
    premium_users = db.query(func.count(User.id)).filter(User.plan == PlanEnum.PREMIUM).scalar()
    total_conversions = db.query(func.sum(User.total_conversions)).scalar() or 0
    total_downloads = db.query(func.count(DownloadLog.id)).scalar()
    revenue_inr = db.query(func.sum(PaymentLog.amount_inr)).filter(PaymentLog.status == "SUCCESS").scalar() or 0.0

    from datetime import datetime, timedelta
    today = datetime.utcnow().date()
    new_users_today = db.query(func.count(User.id)).filter(
        func.date(User.created_at) == today
    ).scalar()

    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "total_downloads": total_downloads,
        "total_conversions": total_conversions,
        "revenue_inr": float(revenue_inr),
        "new_users_today": new_users_today
    }

# ─── All Users ─────────────────────────────────────────────────
@router.get("/users")
async def get_all_users(
    authorization: str = None,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    get_admin_user(authorization, db)

    users = db.query(User).order_by(User.created_at.desc())\
              .offset((page - 1) * limit).limit(limit).all()

    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "plan": u.plan.value,
            "phone": u.phone,
            "device_info": u.device_info,
            "total_conversions": u.total_conversions,
            "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
            "ip_address": u.ip_address
        }
        for u in users
    ]

# ─── Download Logs ─────────────────────────────────────────────
@router.get("/downloads")
async def get_download_logs(
    authorization: str = None,
    db: Session = Depends(get_db)
):
    get_admin_user(authorization, db)

    logs = db.query(DownloadLog).order_by(DownloadLog.created_at.desc()).limit(500).all()
    return [
        {
            "id": l.id,
            "user_id": l.user_id,
            "device_info": l.device_info,
            "ip_address": l.ip_address,
            "platform": l.platform,
            "country": l.country,
            "created_at": l.created_at.isoformat()
        }
        for l in logs
    ]

# ─── Revenue Report ────────────────────────────────────────────
@router.get("/revenue")
async def get_revenue(authorization: str = None, db: Session = Depends(get_db)):
    get_admin_user(authorization, db)

    payments = db.query(PaymentLog).filter(
        PaymentLog.status == "SUCCESS"
    ).order_by(PaymentLog.created_at.desc()).all()

    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "plan_id": p.plan_id,
            "amount_inr": p.amount_inr,
            "razorpay_payment_id": p.razorpay_payment_id,
            "created_at": p.created_at.isoformat()
        }
        for p in payments
    ]

# ─── Make Admin (run once for yourself) ────────────────────────
@router.post("/make-admin/{user_email}")
async def make_admin(
    user_email: str,
    secret: str,
    db: Session = Depends(get_db)
):
    """One-time endpoint to promote a user to admin. Protect with a secret."""
    import os
    if secret != os.getenv("ADMIN_SETUP_SECRET", "setup-secret-change-me"):
        raise HTTPException(status_code=403, detail="Invalid secret")

    user = db.query(User).filter(User.email == user_email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = True
    db.commit()
    return {"message": f"{user_email} is now an admin"}
