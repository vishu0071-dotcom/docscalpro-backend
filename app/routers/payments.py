"""
Razorpay Payments Router
Handles: Create Order, Verify Payment, Webhook
Supports INR + international payments
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import razorpay, hmac, hashlib, os, uuid

from app.database import get_db, User, PaymentLog, PlanEnum
from app.routers.auth import verify_token

router = APIRouter()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_XXXXXXXXXX")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "your_secret_here")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Pricing: plan_id → (duration_months, amount_inr_paise)
PLANS = {
    "plan_1m":  {"months": 1,  "amount": 4900,  "name": "1 Month Premium"},
    "plan_3m":  {"months": 3,  "amount": 12900, "name": "3 Months Premium"},
    "plan_6m":  {"months": 6,  "amount": 22900, "name": "6 Months Premium"},
    "plan_1y":  {"months": 12, "amount": 39900, "name": "1 Year Premium"},
}

# ─── Schemas ───────────────────────────────────────────────────
class CreateOrderRequest(BaseModel):
    plan_id: str

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: str

# ─── Auth Helper ───────────────────────────────────────────────
def get_user_from_auth(authorization: str, db: Session) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    user_id = verify_token(authorization.split(" ")[1])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ─── Create Razorpay Order ─────────────────────────────────────
@router.post("/create-order")
async def create_order(
    request: CreateOrderRequest,
    authorization: str = None,
    db: Session = Depends(get_db)
):
    user = get_user_from_auth(authorization, db)

    if request.plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    plan = PLANS[request.plan_id]

    try:
        # Create Razorpay order
        order_data = {
            "amount": plan["amount"],  # Amount in paise (₹49 = 4900 paise)
            "currency": "INR",
            "receipt": f"docscalpro_{user.id[:8]}_{uuid.uuid4().hex[:8]}",
            "notes": {
                "user_id": user.id,
                "plan_id": request.plan_id,
                "plan_name": plan["name"],
                "user_email": user.email
            }
        }
        order = razorpay_client.order.create(data=order_data)

        # Log payment attempt
        payment_log = PaymentLog(
            id=str(uuid.uuid4()),
            user_id=user.id,
            razorpay_order_id=order["id"],
            plan_id=request.plan_id,
            amount_inr=plan["amount"] // 100,
            status="PENDING"
        )
        db.add(payment_log)
        db.commit()

        return {
            "order_id": order["id"],
            "amount": plan["amount"],
            "currency": "INR",
            "razorpay_key": RAZORPAY_KEY_ID
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")

# ─── Verify Payment ────────────────────────────────────────────
@router.post("/verify")
async def verify_payment(
    request: VerifyPaymentRequest,
    authorization: str = None,
    db: Session = Depends(get_db)
):
    user = get_user_from_auth(authorization, db)

    # Verify Razorpay signature (prevents fraud)
    generated_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        f"{request.razorpay_order_id}|{request.razorpay_payment_id}".encode(),
        hashlib.sha256
    ).hexdigest()

    if generated_signature != request.razorpay_signature:
        raise HTTPException(status_code=400, detail="Payment verification failed — invalid signature")

    if request.plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    plan = PLANS[request.plan_id]

    # Update user subscription
    now = datetime.utcnow()
    # If already premium and not expired, extend from current expiry
    if user.plan == PlanEnum.PREMIUM and user.plan_expires_at and user.plan_expires_at > now:
        new_expiry = user.plan_expires_at + timedelta(days=plan["months"] * 30)
    else:
        new_expiry = now + timedelta(days=plan["months"] * 30)

    user.plan = PlanEnum.PREMIUM
    user.plan_expires_at = new_expiry

    # Update payment log
    payment_log = db.query(PaymentLog).filter(
        PaymentLog.razorpay_order_id == request.razorpay_order_id
    ).first()
    if payment_log:
        payment_log.razorpay_payment_id = request.razorpay_payment_id
        payment_log.status = "SUCCESS"

    db.commit()

    # Return updated user
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "plan": user.plan.value,
        "plan_expires_at": user.plan_expires_at.isoformat(),
        "created_at": user.created_at.isoformat(),
        "total_conversions": user.total_conversions
    }

# ─── Razorpay Webhook (for server-side confirmation) ───────────
@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if expected != signature:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    import json
    event = json.loads(body)

    if event.get("event") == "payment.captured":
        payment_id = event["payload"]["payment"]["entity"]["id"]
        order_id = event["payload"]["payment"]["entity"]["order_id"]

        log = db.query(PaymentLog).filter(PaymentLog.razorpay_order_id == order_id).first()
        if log and log.status != "SUCCESS":
            log.razorpay_payment_id = payment_id
            log.status = "SUCCESS"
            db.commit()

    return {"status": "ok"}
