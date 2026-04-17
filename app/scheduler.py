import uuid
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Policy, Claim, ClaimStatus, PayoutStatus, PolicyStatus, Worker
from app.services.weather_service import fetch_weather, fetch_flood_alert
from app.services.aqi_service import fetch_aqi
from app.services.fraud_service import compute_fraud_score, score_to_action
from app.config import THRESHOLDS
from datetime import datetime, date

FRAUD_BLOCK_SCORE = 70.0

last_run_info = {"last_run": None, "claims_created": 0, "payouts_processed": 0}


def _already_claimed_today(db: Session, policy_id: int, trigger_type: str) -> bool:
    today = date.today()
    return db.query(Claim).filter(
        Claim.policy_id    == policy_id,
        Claim.trigger_type == trigger_type,
        Claim.created_at   >= datetime(today.year, today.month, today.day),
    ).first() is not None


def _is_payment_overdue(policy: Policy) -> bool:
    if policy.grace_period_end is None:
        return False
    return datetime.utcnow() <= policy.grace_period_end


def run_auto_trigger():
    db: Session = SessionLocal()
    claims_created    = 0
    payouts_processed = 0
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

            # merge aqi into weather dict so fraud service can read it
            live_weather = {**weather, "aqi": aqi_data.get("aqi", 0.0)}

            checks = {
                "rainfall":    weather.get("rainfall", 0.0),
                "temperature": weather.get("temp", 0.0),
                "aqi":         aqi_data.get("aqi", 0.0),
                "flood":       flood_24h,
            }

            payment_overdue = _is_payment_overdue(policy)

            for trigger_type, value in checks.items():
                if value < THRESHOLDS[trigger_type]:
                    continue
                if _already_claimed_today(db, policy.id, trigger_type):
                    continue

                fraud_score, fraud_flags = compute_fraud_score(
                    db            = db,
                    policy_id     = policy.id,
                    trigger_type  = trigger_type,
                    trigger_value = value,
                    worker_city   = city,
                    claim_city    = city,
                )

                risk_level, action = score_to_action(fraud_score)

                if action == "Block":
                    continue  # fraud blocked — no claim created

                if payment_overdue or action == "Monitor":
                    claim_status = ClaimStatus.pending
                else:
                    claim_status = ClaimStatus.approved

                note = (
                    f"Auto-triggered: {trigger_type} value {value} exceeded "
                    f"threshold of {THRESHOLDS[trigger_type]}."
                )
                if fraud_flags:
                    note += " | Fraud flags: " + "; ".join(fraud_flags)

                claim = Claim(
                    policy_id        = policy.id,
                    trigger_type     = trigger_type,
                    trigger_value    = value,
                    payout_amount    = policy.max_payout,
                    fraud_score      = fraud_score,
                    status           = claim_status,
                    admin_note       = note,
                    triggered_by     = "auto",
                    weather_rainfall = live_weather.get("rainfall"),
                    weather_temp     = live_weather.get("temp"),
                    weather_aqi      = live_weather.get("aqi"),
                )
                db.add(claim)
                db.flush()
                claims_created += 1

                if claim_status == ClaimStatus.approved:
                    txn_id = f"payout_{uuid.uuid4().hex[:16].upper()}"
                    claim.payout_status         = PayoutStatus.processed
                    claim.payout_transaction_id = txn_id
                    claim.payout_processed_at   = datetime.utcnow()
                    payouts_processed += 1

        db.commit()
        last_run_info["last_run"]          = datetime.utcnow().isoformat()
        last_run_info["claims_created"]    = claims_created
        last_run_info["payouts_processed"] = payouts_processed
        print(f"[Scheduler] Run complete — {claims_created} claims, {payouts_processed} payouts processed")
    except Exception as e:
        print(f"[Scheduler] Error: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_auto_trigger, "interval", minutes=5, id="auto_trigger", next_run_time=datetime.utcnow())
    scheduler.start()
    print("[Scheduler] Auto-trigger job started (runs every 5 minutes for testing).")
    return scheduler
