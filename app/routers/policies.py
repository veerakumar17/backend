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

RISK_MULTIPLIERS = {"Low": 0.9, "Medium": 1.0, "High": 1.2}


def get_risk_level(risk_score: float) -> str:
    if risk_score < 0.3:
        return "Low"
    elif risk_score < 0.6:
        return "Medium"
    else:
        return "High"


@router.get("/dynamic-premium")
def get_dynamic_premiums(risk_score: float):
    risk_level = get_risk_level(risk_score)
    multiplier = RISK_MULTIPLIERS[risk_level]
    plans = {}
    for plan, details in PLAN_DETAILS.items():
        base = details["weekly_premium"]
        final = round(base * multiplier, 2)
        plans[plan.value] = {
            "base_premium": base,
            "final_premium": final,
            "max_payout": details["max_payout"],
            "risk_level": risk_level,
            "risk_score": risk_score,
            "multiplier": multiplier,
        }
    return {"risk_level": risk_level, "multiplier": multiplier, "plans": plans}


@router.post("/create", response_model=PolicyResponse)
def create_policy(data: PolicyCreate, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.id == data.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    existing = db.query(Policy).filter(Policy.worker_id == data.worker_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Policy already exists for this worker")

    plan_info = PLAN_DETAILS[data.plan]
    risk_level = get_risk_level(data.risk_score) if data.risk_score is not None else "Medium"
    multiplier = RISK_MULTIPLIERS[risk_level]
    final_premium = round(plan_info["weekly_premium"] * multiplier, 2)

    policy = Policy(
        worker_id=data.worker_id,
        plan=data.plan,
        weekly_premium=final_premium,
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
