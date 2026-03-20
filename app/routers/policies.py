from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Worker, PlanType
from app.schemas import PolicyCreate, PolicyResponse

router = APIRouter(prefix="/policies", tags=["Policies"])

PLAN_DETAILS = {
    PlanType.basic:    {"weekly_premium": 20.0, "max_payout": 300.0},
    PlanType.standard: {"weekly_premium": 35.0, "max_payout": 600.0},
    PlanType.premium:  {"weekly_premium": 50.0, "max_payout": 1000.0},
}


@router.post("/create", response_model=PolicyResponse)
def create_policy(data: PolicyCreate, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.id == data.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    existing = db.query(Policy).filter(Policy.worker_id == data.worker_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Policy already exists for this worker")

    plan_info = PLAN_DETAILS[data.plan]
    policy = Policy(
        worker_id=data.worker_id,
        plan=data.plan,
        weekly_premium=plan_info["weekly_premium"],
        max_payout=plan_info["max_payout"],
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.get("/{worker_id}", response_model=PolicyResponse)
def get_policy(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy
