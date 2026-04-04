from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models import DeliveryPlatform, PlanType, PolicyStatus, ClaimStatus


class WorkerCreate(BaseModel):
    username: str
    password: str
    name: str
    email: str
    mobile: str
    delivery_platform: DeliveryPlatform
    location: str
    upi_id: str
    weekly_salary: float


class WorkerLogin(BaseModel):
    username: str
    password: str


class WorkerResponse(BaseModel):
    id: int
    username: str
    name: str
    email: str
    mobile: str
    delivery_platform: DeliveryPlatform
    location: str
    upi_id: str
    weekly_salary: float
    created_at: datetime

    class Config:
        from_attributes = True


class PolicyCreate(BaseModel):
    worker_id: int
    plan: PlanType
    risk_score: Optional[float] = 0.5


class PolicyResponse(BaseModel):
    id: int
    worker_id: int
    plan: PlanType
    weekly_premium: float
    max_payout: float
    weeks_paid: int
    is_eligible: bool
    status: PolicyStatus
    created_at: datetime

    class Config:
        from_attributes = True


class PremiumResponse(BaseModel):
    id: int
    policy_id: int
    amount: float
    week_number: Optional[int]
    status: str
    paid_at: datetime

    class Config:
        from_attributes = True


class TriggerSimulate(BaseModel):
    worker_id: int
    trigger_type: str
    trigger_value: float


class ClaimResponse(BaseModel):
    id: int
    policy_id: int
    trigger_type: str
    trigger_value: float
    payout_amount: float
    fraud_score: float
    status: ClaimStatus
    admin_note: Optional[str] = None
    triggered_by: Optional[str] = "system"
    created_at: datetime

    class Config:
        from_attributes = True
