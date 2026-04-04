from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Premium, PolicyStatus, Claim, ClaimStatus
from app.schemas import PremiumResponse
from datetime import datetime, timedelta

router = APIRouter(prefix="/premiums", tags=["Premiums"])

ELIGIBILITY_WEEKS = 6
GRACE_PERIOD_DAYS = 2


@router.post("/pay/{worker_id}", response_model=PremiumResponse)
def collect_premium(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.status != PolicyStatus.active:
        raise HTTPException(status_code=400, detail="Policy is not active")

    if policy.grace_period_end is not None:
        policy.grace_period_end = None
        pending_claims = db.query(Claim).filter(
            Claim.policy_id == policy.id,
            Claim.status    == ClaimStatus.pending,
        ).all()
        for claim in pending_claims:
            claim.status = ClaimStatus.approved

    policy.weeks_paid += 1
    if policy.weeks_paid >= ELIGIBILITY_WEEKS:
        policy.is_eligible = True

    premium = Premium(
        policy_id   = policy.id,
        amount      = policy.weekly_premium,
        status      = "paid",
        week_number = policy.weeks_paid,
    )
    db.add(premium)
    db.commit()
    db.refresh(premium)
    return premium


@router.get("/{worker_id}")
def get_premium_history(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {
        "weeks_paid":       policy.weeks_paid,
        "is_eligible":      policy.is_eligible,
        "grace_period_end": policy.grace_period_end,
        "premiums":         policy.premiums,
    }
