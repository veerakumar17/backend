from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Claim, ClaimStatus, PolicyStatus
from app.schemas import TriggerSimulate, ClaimResponse
from app.config import THRESHOLDS, LABELS

router = APIRouter(prefix="/triggers", tags=["Triggers"])


def is_triggered(trigger_type: str, value: float) -> bool:
    threshold = THRESHOLDS.get(trigger_type.lower())
    if threshold is None:
        return False
    return value >= threshold


@router.get("/list")
def list_triggers():
    return [
        {"type": "rainfall",    "label": "Heavy Rain",       "threshold": "Rainfall > 70 mm",    "mock_value": 85.0,  "icon": "🌧"},
        {"type": "temperature", "label": "Extreme Heat",     "threshold": "Temperature > 42°C",  "mock_value": 45.0,  "icon": "🌡"},
        {"type": "aqi",         "label": "Severe Pollution", "threshold": "AQI > 350",            "mock_value": 380.0, "icon": "💨"},
        {"type": "flood",       "label": "Flood Alert",      "threshold": "Rainfall > 120 mm",   "mock_value": 130.0, "icon": "🌊"},
    ]


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
        label     = LABELS.get(data.trigger_type.lower(), data.trigger_type)
        raise HTTPException(
            status_code=400,
            detail=f"Trigger threshold not met for {label}. Required: >= {threshold}"
        )

    claim = Claim(
        policy_id     = policy.id,
        trigger_type  = data.trigger_type,
        trigger_value = data.trigger_value,
        payout_amount = policy.max_payout,
        status        = ClaimStatus.approved,
        triggered_by  = "simulation",
        admin_note    = f"Manual simulation: {LABELS.get(data.trigger_type, data.trigger_type)} value {data.trigger_value}.",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim
