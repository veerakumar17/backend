from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class DeliveryPlatform(str, enum.Enum):
    swiggy = "Swiggy"
    zomato = "Zomato"


class PlanType(str, enum.Enum):
    basic = "Basic"
    standard = "Standard"
    premium = "Premium"


class PolicyStatus(str, enum.Enum):
    active = "Active"
    cancelled = "Cancelled"
    suspended = "Suspended"


class ClaimStatus(str, enum.Enum):
    approved = "Approved"
    pending = "Pending"
    rejected = "Rejected"


class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    mobile = Column(String, unique=True, nullable=False)
    delivery_platform = Column(Enum(DeliveryPlatform), nullable=False)
    location = Column(String, nullable=False)
    upi_id = Column(String, nullable=False)
    weekly_salary = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    policy = relationship("Policy", back_populates="worker", uselist=False)


class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), unique=True, nullable=False)
    plan = Column(Enum(PlanType), nullable=False)
    weekly_premium = Column(Float, nullable=False)
    max_payout = Column(Float, nullable=False)
    weeks_paid = Column(Integer, default=0)
    is_eligible = Column(Boolean, default=False)
    status = Column(Enum(PolicyStatus), default=PolicyStatus.active)
    grace_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    worker = relationship("Worker", back_populates="policy")
    premiums = relationship("Premium", back_populates="policy")
    claims = relationship("Claim", back_populates="policy")


class Premium(Base):
    __tablename__ = "premiums"

    id          = Column(Integer, primary_key=True, index=True)
    policy_id   = Column(Integer, ForeignKey("policies.id"), nullable=False)
    amount      = Column(Float, nullable=False)
    week_number = Column(Integer, nullable=True)
    status      = Column(String, default="paid")
    paid_at     = Column(DateTime, default=datetime.utcnow)

    policy = relationship("Policy", back_populates="premiums")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=False)
    trigger_type = Column(String, nullable=False)
    trigger_value = Column(Float, nullable=False)
    payout_amount = Column(Float, nullable=False)
    fraud_score = Column(Float, default=0.0)
    status = Column(Enum(ClaimStatus), default=ClaimStatus.approved)
    admin_note = Column(String, nullable=True)
    triggered_by = Column(String, default="system")
    created_at = Column(DateTime, default=datetime.utcnow)

    policy = relationship("Policy", back_populates="claims")
