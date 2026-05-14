"""
Database Models — PostgreSQL via SQLAlchemy
Tables: users, subscriptions, conversions, downloads, payment_logs
"""

from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Float, Text, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
import enum
import os
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/docscapro")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── Enums ─────────────────────────────────────────────────────
class PlanEnum(str, enum.Enum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"

class ConversionStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

# ─── User Model ────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True, default=lambda: str(__import__('uuid').uuid4()))
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(500), nullable=False)
    phone = Column(String(20), nullable=True)
    plan = Column(Enum(PlanEnum), default=PlanEnum.FREE)
    plan_expires_at = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, default=False)
    device_info = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    total_conversions = Column(Integer, default=0)
    daily_conversions = Column(Integer, default=0)
    last_conversion_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    conversions = relationship("Conversion", back_populates="user")
    payments = relationship("PaymentLog", back_populates="user")

# ─── Conversion Model ───────────────────────────────────────────
class Conversion(Base):
    __tablename__ = "conversions"

    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    from_format = Column(String(20), nullable=False)
    to_format = Column(String(20), nullable=False)
    original_filename = Column(String(500), nullable=False)
    output_filename = Column(String(500), nullable=True)
    file_size_kb = Column(Integer, nullable=True)
    status = Column(Enum(ConversionStatus), default=ConversionStatus.PENDING)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="conversions")

# ─── Payment Log ────────────────────────────────────────────────
class PaymentLog(Base):
    __tablename__ = "payment_logs"

    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    razorpay_order_id = Column(String(255), nullable=True)
    razorpay_payment_id = Column(String(255), nullable=True)
    plan_id = Column(String(50), nullable=False)
    amount_inr = Column(Integer, nullable=False)
    currency = Column(String(10), default="INR")
    status = Column(String(50), default="PENDING")  # PENDING, SUCCESS, FAILED
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="payments")

# ─── Download Log (tracks who downloaded the app) ──────────────
class DownloadLog(Base):
    __tablename__ = "download_logs"

    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # null = anonymous
    device_info = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    app_version = Column(String(20), nullable=True)
    platform = Column(String(20), default="Android")
    country = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
