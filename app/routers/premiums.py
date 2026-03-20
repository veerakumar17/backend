from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Premium, PolicyStatus
from app.schemas import PremiumResponse

router = APIRouter(prefix="/premiums", tags=["Premiums"])

ELIGIBILITY_WEEKS = 6


@router.post("/pay/{worker_id}", response_model=PremiumResponse)
def simulate_premium_payment(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.status != PolicyStatus.active:
        raise HTTPException(status_code=400, detail="Policy is not active")

    premium = Premium(policy_id=policy.id, amount=policy.weekly_premium, status="paid")
    db.add(premium)

    policy.weeks_paid += 1
    if policy.weeks_paid >= ELIGIBILITY_WEEKS:
        policy.is_eligible = True

    db.commit()
    db.refresh(premium)
    return premium


@router.get("/{worker_id}")
def get_premium_history(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {
        "weeks_paid": policy.weeks_paid,
        "is_eligible": policy.is_eligible,
        "premiums": policy.premiums
    }
