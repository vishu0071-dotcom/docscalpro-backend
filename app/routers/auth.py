"""
Auth Router — Register, Login, Profile, Logout
Uses JWT for stateless authentication
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import uuid, bcrypt, jwt, os

from app.database import get_db, User, PlanEnum, DownloadLog

router = APIRouter()

SECRET_KEY = os.getenv("JWT_SECRET", "change-this-to-a-secure-random-secret-key")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

# ─── Schemas ───────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    device_info: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str]
    plan: str
    plan_expires_at: Optional[str]
    created_at: str
    total_conversions: int
    class Config:
        from_attributes = True

class AuthResponse(BaseModel):
    token: str
    user: UserOut

# ─── Helpers ───────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")

def get_current_user(authorization: str = None, db: Session = Depends(get_db)):
    from fastapi import Header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing")
    token = authorization.split(" ")[1]
    user_id = verify_token(token)
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_premium(user: User = Depends(get_current_user)):
    if user.plan == PlanEnum.FREE:
        raise HTTPException(status_code=403, detail="Premium plan required for this feature")
    if user.plan_expires_at and user.plan_expires_at < datetime.utcnow():
        user.plan = PlanEnum.FREE
        raise HTTPException(status_code=403, detail="Premium plan expired. Please renew.")
    return user

def format_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "plan": user.plan.value,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "created_at": user.created_at.isoformat(),
        "total_conversions": user.total_conversions
    }

# ─── Endpoints ─────────────────────────────────────────────────
@router.post("/register", status_code=201)
async def register(request: RegisterRequest, req: Request, db: Session = Depends(get_db)):
    # Check email exists
    if db.query(User).filter(User.email == request.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        name=request.name.strip(),
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
        phone=request.phone,
        plan=PlanEnum.FREE,
        device_info=request.device_info,
        ip_address=req.client.host
    )
    db.add(user)

    # Log download/registration
    dl = DownloadLog(
        id=str(uuid.uuid4()),
        user_id=user.id,
        device_info=request.device_info,
        ip_address=req.client.host
    )
    db.add(dl)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    return {"token": token, "user": format_user(user)}

@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email.lower()).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    user.last_login = datetime.utcnow()
    db.commit()

    token = create_token(user.id)
    return {"token": token, "user": format_user(user)}

@router.get("/me")
async def get_profile(authorization: str = None, db: Session = Depends(get_db)):
    from fastapi import Header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization missing")
    token = authorization.split(" ")[1]
    user_id = verify_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return format_user(user)

@router.post("/logout")
async def logout(authorization: str = None):
    # JWT is stateless — client just deletes token
    return {"message": "Logged out successfully"}
