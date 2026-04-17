import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, Column, Integer, String
from app.database import get_db, Base
from app.models import Policy, Claim, Premium, Worker, ClaimStatus, PayoutStatus, PolicyStatus
from app.services.weather_service import fetch_weather
from app.services.aqi_service import fetch_aqi
from app.services.risk_service import predict_risk_from_env
from app.services.fraud_service import compute_fraud_score, score_to_action, full_fraud_report
from app.config import THRESHOLDS, LABELS
from datetime import datetime, timedelta
from collections import Counter
from passlib.context import CryptContext

router = APIRouter(prefix="/admin", tags=["Admin"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AdminUser(Base):
    __tablename__ = "admin_users"
    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)


@router.post("/register")
def register_admin(data: dict, db: Session = Depends(get_db)):
    name = data.get("name", "").strip()
    password = data.get("password", "")
    if not name or not password:
        raise HTTPException(status_code=400, detail="Name and password are required.")
    if db.query(AdminUser).filter(AdminUser.name == name).first():
        raise HTTPException(status_code=400, detail="Admin name already taken.")
    admin = AdminUser(name=name, password=pwd_context.hash(password))
    db.add(admin)
    db.commit()
    return {"message": "Admin registered successfully."}


@router.post("/login")
def login_admin(data: dict, db: Session = Depends(get_db)):
    name = data.get("name", "").strip()
    password = data.get("password", "")
    admin = db.query(AdminUser).filter(AdminUser.name == name).first()
    if not admin or not pwd_context.verify(password, admin.password):
        raise HTTPException(status_code=401, detail="Invalid name or password.")
    return {"message": "Login successful.", "admin": {"id": admin.id, "name": admin.name}}


@router.post("/trigger-payment/{worker_id}")
def admin_trigger_payment(worker_id: int, db: Session = Depends(get_db)):
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
    if policy.weeks_paid >= 6:
        policy.is_eligible = True

    premium = Premium(policy_id=policy.id, amount=policy.weekly_premium, status="paid", week_number=policy.weeks_paid)
    db.add(premium)
    db.commit()
    return {
        "message": f"Week {policy.weeks_paid} payment triggered for worker {worker_id}.",
        "weeks_paid":  policy.weeks_paid,
        "is_eligible": policy.is_eligible,
        "amount":      policy.weekly_premium,
    }


@router.post("/fire-trigger-by-location")
def admin_fire_trigger_by_location(data: dict, db: Session = Depends(get_db)):
    location   = data.get("location", "").strip()
    admin_name = data.get("admin_name", "Admin")

    if not location:
        raise HTTPException(status_code=400, detail="location is required.")

    try:
        weather  = fetch_weather(location)
        aqi_data = fetch_aqi(location)
    except Exception:
        # Fallback: use mock values that exceed all thresholds for demo purposes
        weather  = {"rainfall": 85.0, "temp": 44.0, "humidity": 90, "wind": 5.0, "pressure": 1005.0}
        aqi_data = {"aqi": 380, "pm25": 120.0, "pm10": 150.0}

    checks = {
        "rainfall":    weather.get("rainfall", 0.0),
        "temperature": weather.get("temp", 0.0),
        "aqi":         aqi_data.get("aqi", 0.0),
        "flood":       weather.get("rainfall", 0.0),
    }

    triggered = [(t, v) for t, v in checks.items() if v >= THRESHOLDS[t]]

    if not triggered:
        vals = ", ".join(f"{LABELS[t]}: {v}" for t, v in checks.items())
        raise HTTPException(status_code=400, detail=f"No thresholds exceeded in {location}. Current values — {vals}")

    policies = (
        db.query(Policy).join(Worker)
        .filter(Worker.location == location, Policy.is_eligible == True, Policy.status == PolicyStatus.active)
        .all()
    )

    if not policies:
        raise HTTPException(status_code=404, detail=f"No eligible workers found in '{location}'.")

    live_weather = {**weather, "aqi": aqi_data.get("aqi", 0.0)}

    created = []
    for policy in policies:
        for trigger_type, value in triggered:
            today = datetime.utcnow().date()
            already = db.query(Claim).filter(
                Claim.policy_id    == policy.id,
                Claim.trigger_type == trigger_type,
                Claim.created_at   >= datetime(today.year, today.month, today.day),
            ).first()
            if already:
                continue

            fraud_score, fraud_flags = compute_fraud_score(
                db            = db,
                policy_id     = policy.id,
                trigger_type  = trigger_type,
                trigger_value = value,
                worker_city   = policy.worker.location,
                claim_city    = location,
            )
            _, action = score_to_action(fraud_score)
            if action == "Block":
                created.append({
                    "claim_id": None,
                    "worker": policy.worker.name,
                    "trigger": LABELS[trigger_type],
                    "payout": 0,
                    "txn_id": None,
                    "blocked": True,
                    "fraud_score": fraud_score,
                    "fraud_flags": fraud_flags,
                })
                continue

            claim_status = ClaimStatus.pending if action == "Monitor" else ClaimStatus.approved
            note = f"{LABELS[trigger_type]} detected in {location} — value {value} exceeded threshold {THRESHOLDS[trigger_type]}."
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
                triggered_by     = f"admin:{admin_name}",
                weather_rainfall = live_weather.get("rainfall"),
                weather_temp     = live_weather.get("temp"),
                weather_aqi      = live_weather.get("aqi"),
            )
            db.add(claim)
            db.flush()

            txn_id = None
            if claim_status == ClaimStatus.approved:
                txn_id = f"payout_{uuid.uuid4().hex[:16].upper()}"
                claim.payout_status         = PayoutStatus.processed
                claim.payout_transaction_id = txn_id
                claim.payout_processed_at   = datetime.utcnow()

            created.append({
                "claim_id":    claim.id,
                "worker":      policy.worker.name,
                "trigger":     LABELS[trigger_type],
                "payout":      policy.max_payout if claim_status == ClaimStatus.approved else 0,
                "txn_id":      txn_id,
                "blocked":     False,
                "fraud_score": fraud_score,
                "fraud_flags": fraud_flags,
            })

    db.commit()
    return {
        "location": location,
        "triggers_detected": [LABELS[t] for t, _ in triggered],
        "claims_created": len(created),
        "details": created,
    }


@router.post("/fire-trigger")
def admin_fire_trigger(data: dict, db: Session = Depends(get_db)):
    worker_id    = data.get("worker_id")
    trigger_type = data.get("trigger_type")
    trigger_value = float(data.get("trigger_value", 0))
    admin_note   = data.get("admin_note", "")
    admin_name   = data.get("admin_name", "Admin")

    if not worker_id or not trigger_type:
        raise HTTPException(status_code=400, detail="worker_id and trigger_type are required.")

    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.status != PolicyStatus.active:
        raise HTTPException(status_code=400, detail="Policy is not active")
    if not policy.is_eligible:
        raise HTTPException(status_code=400, detail=f"Worker not eligible yet. Weeks paid: {policy.weeks_paid}/6")

    claim = Claim(
        policy_id     = policy.id,
        trigger_type  = trigger_type,
        trigger_value = trigger_value,
        payout_amount = policy.max_payout,
        status        = ClaimStatus.approved,
        admin_note    = admin_note,
        triggered_by  = f"admin:{admin_name}",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return {
        "message": "Trigger fired and claim created.",
        "claim_id": claim.id,
        "payout": claim.payout_amount,
        "trigger_type": trigger_type,
        "admin_note": admin_note,
    }


@router.get("/dashboard")
def admin_dashboard(db: Session = Depends(get_db)):
    # ── Core counts ──
    total_workers  = db.query(Worker).count()
    total_policies = db.query(Policy).filter(Policy.status == PolicyStatus.active).count()
    eligible       = db.query(Policy).filter(Policy.is_eligible == True).count()

    # ── Premium revenue ──
    total_premium_collected = db.query(func.sum(Premium.amount)).scalar() or 0.0

    # ── Claims ──
    all_claims      = db.query(Claim).all()
    approved_claims = [c for c in all_claims if c.status == ClaimStatus.approved]
    total_payout    = sum(c.payout_amount for c in approved_claims)
    total_claims    = len(all_claims)
    approved_count  = len(approved_claims)

    # ── Loss Ratio = Total Payouts / Total Premiums Collected ──
    loss_ratio = round((total_payout / total_premium_collected * 100), 2) if total_premium_collected > 0 else 0.0

    # ── Claims by trigger type (exclude worker_inactivity) ──
    trigger_counts = Counter(c.trigger_type for c in approved_claims if c.trigger_type != "worker_inactivity")

    # ── Weekly trend (last 4 weeks) ──
    weekly_trend = []
    for i in range(3, -1, -1):
        week_start = datetime.utcnow() - timedelta(weeks=i + 1)
        week_end   = datetime.utcnow() - timedelta(weeks=i)
        week_claims = [c for c in approved_claims if week_start <= c.created_at <= week_end]
        week_premiums = db.query(func.sum(Premium.amount)).filter(
            Premium.paid_at >= week_start,
            Premium.paid_at <= week_end,
        ).scalar() or 0.0
        weekly_trend.append({
            "week":     f"Week -{i}" if i > 0 else "This Week",
            "claims":   len(week_claims),
            "payout":   round(sum(c.payout_amount for c in week_claims), 2),
            "premiums": round(week_premiums, 2),
        })

    # ── Predictive analytics: next week risk per unique city ──
    cities = db.query(Worker.location).distinct().all()
    city_predictions = []
    for (city,) in cities:
        try:
            weather  = fetch_weather(city)
            aqi_data = fetch_aqi(city)
            risk     = predict_risk_from_env(weather, aqi_data)
            workers_in_city = db.query(func.count(Worker.id)).filter(Worker.location == city).scalar()
            city_predictions.append({
                "city":             city,
                "risk_score":       risk["risk_score"],
                "risk_level":       risk["risk_level"],
                "workers_affected": workers_in_city,
                "temp":             weather.get("temp"),
                "rainfall":         weather.get("rainfall"),
                "aqi":              aqi_data.get("aqi"),
            })
        except Exception:
            continue

    city_predictions.sort(key=lambda x: x["risk_score"], reverse=True)

    # ── Estimated next-week payout exposure ──
    high_risk_cities = {cp["city"] for cp in city_predictions if cp["risk_level"] == "High"}
    estimated_exposure = 0.0
    for city in high_risk_cities:
        policies_in_city = db.query(Policy).join(Worker).filter(
            Worker.location == city,
            Policy.is_eligible == True,
        ).all()
        estimated_exposure += sum(pol.max_payout for pol in policies_in_city)

    return {
        "overview": {
            "total_workers":           total_workers,
            "active_policies":         total_policies,
            "eligible_policies":       eligible,
            "total_premium_collected": round(total_premium_collected, 2),
            "total_payout":            round(total_payout, 2),
            "total_claims":            total_claims,
            "approved_claims":         approved_count,
            "loss_ratio_percent":      loss_ratio,
        },
        "claims_by_trigger": dict(trigger_counts),
        "weekly_trend":      weekly_trend,
        "city_risk_forecast": city_predictions,
        "estimated_next_week_exposure": round(estimated_exposure, 2),
    }


@router.get("/fraud-detection")
def fraud_detection(db: Session = Depends(get_db)):
    workers = db.query(Worker).all()
    results = []
    for worker in workers:
        report = full_fraud_report(db, worker)
        if report:
            results.append(report)
    results.sort(key=lambda x: x["fraud_score"], reverse=True)
    return results


@router.get("/workers-summary")
def workers_summary(db: Session = Depends(get_db)):
    workers = db.query(Worker).all()
    result = []
    for w in workers:
        policy = w.policy
        claims = policy.claims if policy else []
        approved = [c for c in claims if c.status == ClaimStatus.approved]
        result.append({
            "id":               w.id,
            "name":             w.name,
            "location":         w.location,
            "platform":         w.delivery_platform,
            "plan":             policy.plan if policy else None,
            "weeks_paid":       policy.weeks_paid if policy else 0,
            "is_eligible":      policy.is_eligible if policy else False,
            "total_claims":     len(claims),
            "total_payout":     sum(c.payout_amount for c in approved),
            "premium_paid":     (policy.weeks_paid * policy.weekly_premium) if policy else 0,
        })
    return result
