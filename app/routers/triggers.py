from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Claim, ClaimStatus, PolicyStatus
from app.schemas import TriggerSimulate, ClaimResponse

router = APIRouter(prefix="/triggers", tags=["Triggers"])

THRESHOLDS = {
    "rainfall":    {"min": 70.0,  "unit": "mm"},
    "temperature": {"min": 42.0,  "unit": "°C"},
    "aqi":         {"min": 350.0, "unit": "AQI"},
    "flood":       {"min": 1.0,   "unit": "alert"},
}


def is_triggered(trigger_type: str, value: float) -> bool:
    rule = THRESHOLDS.get(trigger_type.lower())
    if not rule:
        return False
    return value >= rule["min"]


@router.post("/simulate", response_model=ClaimResponse)
def simulate_trigger(data: TriggerSimulate, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == data.worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.status != PolicyStatus.active:
        raise HTTPException(status_code=400, detail="Policy is not active")
    if not policy.is_eligible:
        raise HTTPException(
            status_code=400,
            detail=f"Worker not eligible yet. Weeks paid: {policy.weeks_paid}/6"
        )
    if not is_triggered(data.trigger_type, data.trigger_value):
        threshold = THRESHOLDS.get(data.trigger_type.lower())
        raise HTTPException(
            status_code=400,
            detail=f"Trigger threshold not met. Required: >= {threshold['min']} {threshold['unit']}"
        )

    claim = Claim(
        policy_id=policy.id,
        trigger_type=data.trigger_type,
        trigger_value=data.trigger_value,
        payout_amount=policy.max_payout,
        status=ClaimStatus.approved,
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim
