from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, Column, Integer, String
from app.database import get_db, Base
from app.models import Policy, Claim, Premium, Worker, ClaimStatus, PolicyStatus
from app.services.weather_service import fetch_weather
from app.services.aqi_service import fetch_aqi
from app.services.risk_service import predict_risk_from_env
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch weather for '{location}': {str(e)}")

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
            note = f"{LABELS[trigger_type]} detected in {location} — value {value} exceeded threshold {THRESHOLDS[trigger_type]}."
            claim = Claim(
                policy_id     = policy.id,
                trigger_type  = trigger_type,
                trigger_value = value,
                payout_amount = policy.max_payout,
                status        = ClaimStatus.approved,
                admin_note    = note,
                triggered_by  = f"admin:{admin_name}",
            )
            db.add(claim)
            created.append({"worker": policy.worker.name, "trigger": LABELS[trigger_type], "payout": policy.max_payout})

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
    """
    Runs fraud detection on all workers using rule-based scoring:
    - Abnormal claim frequency (5+ claims/month)  → +20
    - Same trigger claimed 3+ times total          → +30
    - Duplicate claim within 1 hour               → +40
    - GPS/location mismatch (multiple cities)      → +30
    Score 0-30: Low, 30-70: Medium (Monitor), 70+: High (Block)
    """
    workers = db.query(Worker).all()
    results = []
    now = datetime.utcnow()

    for worker in workers:
        policy = worker.policy
        if not policy:
            continue

        all_claims = db.query(Claim).filter(Claim.policy_id == policy.id).all()
        score = 0.0
        flags = []

        # 1. Abnormal claim frequency this month
        this_month = [c for c in all_claims
                      if c.created_at.month == now.month and c.created_at.year == now.year]
        if len(this_month) >= 5:
            score += 20.0
            flags.append(f"High claim frequency: {len(this_month)} claims this month")

        # 2. Same trigger claimed 3+ times total
        from collections import Counter
        trigger_counts = Counter(c.trigger_type for c in all_claims)
        for trigger, count in trigger_counts.items():
            if count >= 3:
                score += 30.0
                flags.append(f"Repeated trigger: {trigger} claimed {count} times")
                break

        # 3. Any claim within 1 hour of a previous claim (rapid successive claims)
        sorted_claims = sorted(all_claims, key=lambda c: c.created_at)
        for i in range(1, len(sorted_claims)):
            diff = (sorted_claims[i].created_at - sorted_claims[i-1].created_at).total_seconds()
            if diff < 3600:
                score += 40.0
                flags.append("Rapid successive claims detected (within 1 hour)")
                break

        # 4. Multiple locations detected (worker location vs claim trigger locations)
        # If worker has claims triggered from admin for different cities — flag
        admin_locations = set()
        for c in all_claims:
            if c.admin_note:
                for word in c.admin_note.split():
                    if "detected" in c.admin_note and "in" in c.admin_note:
                        parts = c.admin_note.split(" in ")
                        if len(parts) > 1:
                            city = parts[1].split(" ")[0].rstrip(".—,")
                            admin_locations.add(city)
        if len(admin_locations) > 1 and worker.location not in admin_locations:
            score += 30.0
            flags.append(f"Location mismatch: worker in {worker.location}, claims from {', '.join(admin_locations)}")

        score = min(score, 90.0)

        if score >= 70:
            risk_level = "High"
            action     = "Block"
        elif score >= 30:
            risk_level = "Medium"
            action     = "Monitor"
        else:
            risk_level = "Low"
            action     = "Allow"

        results.append({
            "worker_id":    worker.id,
            "worker_name":  worker.name,
            "location":     worker.location,
            "plan":         policy.plan,
            "total_claims": len(all_claims),
            "claims_month": len(this_month),
            "fraud_score":  round(score, 1),
            "risk_level":   risk_level,
            "action":       action,
            "flags":        flags,
        })

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
