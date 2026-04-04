from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Policy, Claim, ClaimStatus, PolicyStatus, Worker
from app.services.weather_service import fetch_weather, fetch_flood_alert
from app.services.aqi_service import fetch_aqi
from app.config import THRESHOLDS
from datetime import datetime, date

# Fraud score thresholds
FRAUD_BLOCK_SCORE = 70.0
FRAUD_MONITOR_SCORE = 30.0


def _already_claimed_today(db: Session, policy_id: int, trigger_type: str) -> bool:
    today = date.today()
    return db.query(Claim).filter(
        Claim.policy_id    == policy_id,
        Claim.trigger_type == trigger_type,
        Claim.created_at   >= datetime(today.year, today.month, today.day),
    ).first() is not None


def _is_payment_overdue(policy: Policy) -> bool:
    """Returns True if policy is in grace period or post-grace pending state."""
    if policy.grace_period_end is None:
        return False
    return datetime.utcnow() <= policy.grace_period_end


def _compute_fraud_score(db: Session, policy_id: int, trigger_type: str) -> float:
    """
    Simple rule-based fraud scoring:
    - Abnormal claim frequency this month  → +20
    - Same trigger claimed 3+ times total  → +30
    - Claim within 1 hour of last claim    → +40
    Max score = 90
    """
    score = 0.0
    now = datetime.utcnow()

    all_claims = db.query(Claim).filter(Claim.policy_id == policy_id).all()

    # Abnormal frequency: more than 5 claims this month
    this_month = [c for c in all_claims if c.created_at.month == now.month and c.created_at.year == now.year]
    if len(this_month) >= 5:
        score += 20.0

    # Same trigger claimed 3+ times total
    same_trigger = [c for c in all_claims if c.trigger_type == trigger_type]
    if len(same_trigger) >= 3:
        score += 30.0

    # Claim within last 1 hour
    recent = [c for c in all_claims if (now - c.created_at).total_seconds() < 3600]
    if recent:
        score += 40.0

    return min(score, 90.0)


def run_auto_trigger():
    db: Session = SessionLocal()
    try:
        policies = (
            db.query(Policy)
            .filter(Policy.status == PolicyStatus.active, Policy.is_eligible == True)
            .all()
        )

        for policy in policies:
            worker: Worker = policy.worker
            if not worker or not worker.location:
                continue

            city = worker.location
            try:
                weather   = fetch_weather(city)
                aqi_data  = fetch_aqi(city)
                flood_24h = fetch_flood_alert(city)
            except Exception:
                continue

            checks = {
                "rainfall":    weather.get("rainfall", 0.0),
                "temperature": weather.get("temp", 0.0),
                "aqi":         aqi_data.get("aqi", 0.0),
                "flood":       flood_24h,
            }

            # Determine if payment is overdue (grace period active)
            payment_overdue = _is_payment_overdue(policy)

            for trigger_type, value in checks.items():
                if value < THRESHOLDS[trigger_type]:
                    continue
                if _already_claimed_today(db, policy.id, trigger_type):
                    continue

                # Fraud check
                fraud_score = _compute_fraud_score(db, policy.id, trigger_type)
                if fraud_score >= FRAUD_BLOCK_SCORE:
                    continue

                # Determine claim status
                if payment_overdue:
                    claim_status = ClaimStatus.pending
                elif fraud_score >= FRAUD_MONITOR_SCORE:
                    claim_status = ClaimStatus.pending
                else:
                    claim_status = ClaimStatus.approved

                claim = Claim(
                    policy_id     = policy.id,
                    trigger_type  = trigger_type,
                    trigger_value = value,
                    payout_amount = policy.max_payout,
                    fraud_score   = fraud_score,
                    status        = claim_status,
                    admin_note    = f"Auto-triggered: {trigger_type} value {value} exceeded threshold of {THRESHOLDS[trigger_type]}.",
                    triggered_by  = "auto",
                )
                db.add(claim)

        db.commit()
    except Exception as e:
        print(f"[Scheduler] Error: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_auto_trigger, "interval", hours=1, id="auto_trigger", next_run_time=datetime.utcnow())
    scheduler.start()
    print("[Scheduler] Auto-trigger job started.")
    return scheduler
