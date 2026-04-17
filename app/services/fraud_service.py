"""
fraud_service.py
Advanced fraud detection for gig worker insurance.

Improvement 1: Fake weather check uses stored weather snapshot on the Claim row
               (weather_rainfall, weather_temp, weather_aqi) — not live weather.
               This means the check is always accurate regardless of when fraud
               detection runs.

Improvement 2: IsolationForest ML model detects anomalous claim patterns per
               worker. Trained on 4 features per claim:
                 - claims_per_month
                 - days_since_last_claim
                 - trigger_value_ratio  (trigger_value / threshold)
                 - payout_amount
               Anomaly score is added to the rule-based score.

Checks:
  1. Fake weather claim     — stored weather at claim time doesn't confirm trigger
  2. GPS / city spoofing    — claim city differs from worker's registered city
  3. Multi-city same day    — claims from >1 city on the same calendar day
  4. Claim velocity         — >2 claims in any rolling 7-day window
  5. Abnormal monthly freq  — 5+ claims in a calendar month
  6. Repeated trigger       — same trigger type claimed 3+ times total
  7. Rapid successive       — two claims within 1 hour of each other
  8. ML anomaly (IF)        — IsolationForest flags pattern as outlier
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Claim
import numpy as np

# ── weights ───────────────────────────────────────────────────────────────────
W_FAKE_WEATHER   = 50
W_GPS_SPOOF      = 40
W_RAPID_CLAIMS   = 40
W_MULTI_CITY_DAY = 35
W_REPEATED_TRIG  = 30
W_VELOCITY       = 25
W_MONTHLY_FREQ   = 20
W_ML_ANOMALY     = 30   # Isolation Forest anomaly signal

MAX_SCORE = 90.0


# ── Isolation Forest helpers ──────────────────────────────────────────────────

def _build_claim_features(claims: list, now: datetime) -> list[list[float]]:
    """
    Build feature vectors for each claim:
    [claims_per_month, days_since_last_claim, trigger_value_ratio, payout_amount]
    """
    from app.config import THRESHOLDS
    rows = []
    sorted_claims = sorted(claims, key=lambda c: c.created_at)
    for i, c in enumerate(sorted_claims):
        month_claims = sum(
            1 for x in claims
            if x.created_at.month == c.created_at.month
            and x.created_at.year == c.created_at.year
        )
        days_since = (
            (c.created_at - sorted_claims[i - 1].created_at).total_seconds() / 86400
            if i > 0 else 30.0
        )
        threshold = THRESHOLDS.get(c.trigger_type, 1)
        ratio = c.trigger_value / threshold if threshold > 0 else 1.0
        rows.append([
            float(month_claims),
            float(days_since),
            float(ratio),
            float(c.payout_amount),
        ])
    return rows


def _isolation_forest_anomaly(claims: list, now: datetime) -> tuple[bool, float]:
    """
    Returns (is_anomaly, contamination_score 0-1).
    Needs at least 3 claims to train — returns False otherwise.
    """
    if len(claims) < 3:
        return False, 0.0

    try:
        from sklearn.ensemble import IsolationForest
        features = _build_claim_features(claims, now)
        X = np.array(features)

        # Train on all historical claims for this worker
        clf = IsolationForest(contamination=0.2, random_state=42, n_estimators=50)
        clf.fit(X)

        # Score the most recent claim (last row)
        # decision_function: negative = more anomalous
        score = clf.decision_function([X[-1]])[0]
        prediction = clf.predict([X[-1]])[0]  # -1 = anomaly, 1 = normal

        # Normalise score to 0-1 (higher = more anomalous)
        # decision_function typically ranges -0.5 to 0.5
        normalised = float(np.clip((0.0 - score) / 0.5, 0.0, 1.0))

        return prediction == -1, normalised
    except Exception:
        return False, 0.0


# ── Main scoring function ─────────────────────────────────────────────────────

def compute_fraud_score(
    db: Session,
    policy_id: int,
    trigger_type: str,
    trigger_value: float,
    worker_city: str,
    claim_city: str,
    live_weather: dict | None = None,  # kept for backward compat, not used for fake-weather check
) -> tuple[float, list[str]]:
    """
    Returns (fraud_score, flags).
    Fake weather check now uses stored weather on existing claims, not live_weather.
    live_weather param is kept so callers don't need to change.
    """
    score = 0.0
    flags = []
    now   = datetime.utcnow()

    all_claims = db.query(Claim).filter(Claim.policy_id == policy_id).all()

    # ── 1. Fake weather claim (uses stored snapshot) ──────────────────────────
    # Check the most recent claim for this trigger type — if its stored weather
    # doesn't confirm the trigger, flag it.
    from app.config import THRESHOLDS
    threshold = THRESHOLDS.get(trigger_type, 0)
    same_trigger_claims = [c for c in all_claims if c.trigger_type == trigger_type]
    if same_trigger_claims:
        last = max(same_trigger_claims, key=lambda c: c.created_at)
        stored_val = _stored_value(trigger_type, last)
        if stored_val is not None and stored_val < threshold:
            score += W_FAKE_WEATHER
            flags.append(
                f"Fake weather claim: stored {trigger_type} was {stored_val} "
                f"at claim time but threshold is {threshold}"
            )

    # ── 2. GPS / city spoofing ────────────────────────────────────────────────
    if claim_city and worker_city and claim_city.lower() != worker_city.lower():
        score += W_GPS_SPOOF
        flags.append(
            f"GPS spoofing: worker registered in {worker_city} "
            f"but claim triggered from {claim_city}"
        )

    # ── 3. Multi-city same day ────────────────────────────────────────────────
    cities_today = _cities_claimed_today(all_claims, now)
    if claim_city and claim_city.lower() not in cities_today and len(cities_today) >= 1:
        score += W_MULTI_CITY_DAY
        flags.append(
            f"Multi-city same day: already has claims from "
            f"{', '.join(cities_today)} today, now claiming from {claim_city}"
        )

    # ── 4. Claim velocity (>2 in rolling 7 days) ─────────────────────────────
    week_ago  = now - timedelta(days=7)
    recent_7d = [c for c in all_claims if c.created_at >= week_ago]
    if len(recent_7d) >= 2:
        score += W_VELOCITY
        flags.append(f"High claim velocity: {len(recent_7d)} claims in last 7 days")

    # ── 5. Abnormal monthly frequency ────────────────────────────────────────
    this_month = [c for c in all_claims
                  if c.created_at.month == now.month and c.created_at.year == now.year]
    if len(this_month) >= 5:
        score += W_MONTHLY_FREQ
        flags.append(f"Abnormal frequency: {len(this_month)} claims this month")

    # ── 6. Repeated trigger ───────────────────────────────────────────────────
    trigger_counts = Counter(c.trigger_type for c in all_claims)
    if trigger_counts.get(trigger_type, 0) >= 3:
        score += W_REPEATED_TRIG
        flags.append(
            f"Repeated trigger: {trigger_type} claimed "
            f"{trigger_counts[trigger_type]} times previously"
        )

    # ── 7. Rapid successive claims (within 1 hour) ────────────────────────────
    recent_1h = [c for c in all_claims if (now - c.created_at).total_seconds() < 3600]
    if recent_1h:
        score += W_RAPID_CLAIMS
        flags.append("Rapid successive claims: another claim exists within the last 1 hour")

    # ── 8. Isolation Forest ML anomaly ───────────────────────────────────────
    is_anomaly, anomaly_strength = _isolation_forest_anomaly(all_claims, now)
    if is_anomaly:
        ml_score = round(W_ML_ANOMALY * anomaly_strength)
        score += ml_score
        flags.append(
            f"ML anomaly detected (Isolation Forest): claim pattern is statistically "
            f"abnormal (anomaly strength {round(anomaly_strength * 100)}%)"
        )

    return round(min(score, MAX_SCORE), 1), flags


def score_to_action(score: float) -> tuple[str, str]:
    """Returns (risk_level, action)."""
    if score >= 70:
        return "High", "Block"
    if score >= 30:
        return "Medium", "Monitor"
    return "Low", "Allow"


# ── Full report for /admin/fraud-detection ────────────────────────────────────

def full_fraud_report(db: Session, worker) -> dict:
    """
    Full fraud report for a single worker.
    Uses stored weather snapshots on claims — no live weather needed.
    """
    policy = worker.policy
    if not policy:
        return None

    all_claims = db.query(Claim).filter(Claim.policy_id == policy.id).all()
    now        = datetime.utcnow()
    score      = 0.0
    flags      = []

    from app.config import THRESHOLDS

    # ── 1. Fake weather: check stored snapshot on every claim ─────────────────
    for c in all_claims:
        stored_val = _stored_value(c.trigger_type, c)
        threshold  = THRESHOLDS.get(c.trigger_type, 0)
        if stored_val is not None and stored_val < threshold:
            score += W_FAKE_WEATHER
            flags.append(
                f"Fake weather claim (claim #{c.id}): stored {c.trigger_type} "
                f"was {stored_val} but threshold is {threshold}"
            )
            break  # one flag is enough

    # ── 2. GPS spoofing ───────────────────────────────────────────────────────
    claim_cities = _extract_claim_cities(all_claims)
    foreign_cities = {c for c in claim_cities if c.lower() != worker.location.lower()}
    if foreign_cities:
        score += W_GPS_SPOOF
        flags.append(
            f"GPS spoofing: claims from {', '.join(foreign_cities)} "
            f"but worker registered in {worker.location}"
        )

    # ── 3. Multi-city same day ────────────────────────────────────────────────
    cities_by_day: dict = defaultdict(set)
    for c in all_claims:
        city = _extract_city_from_note(c.admin_note)
        if city:
            cities_by_day[c.created_at.date()].add(city.lower())
    for day, cities in cities_by_day.items():
        if len(cities) > 1:
            score += W_MULTI_CITY_DAY
            flags.append(f"Multi-city same day on {day}: {', '.join(cities)}")
            break

    # ── 4. Claim velocity ─────────────────────────────────────────────────────
    week_ago  = now - timedelta(days=7)
    recent_7d = [c for c in all_claims if c.created_at >= week_ago]
    if len(recent_7d) >= 2:
        score += W_VELOCITY
        flags.append(f"High velocity: {len(recent_7d)} claims in last 7 days")

    # ── 5. Monthly frequency ──────────────────────────────────────────────────
    this_month = [c for c in all_claims
                  if c.created_at.month == now.month and c.created_at.year == now.year]
    if len(this_month) >= 5:
        score += W_MONTHLY_FREQ
        flags.append(f"Abnormal frequency: {len(this_month)} claims this month")

    # ── 6. Repeated trigger ───────────────────────────────────────────────────
    trigger_counts = Counter(c.trigger_type for c in all_claims)
    for ttype, count in trigger_counts.items():
        if count >= 3:
            score += W_REPEATED_TRIG
            flags.append(f"Repeated trigger: {ttype} claimed {count} times")
            break

    # ── 7. Rapid successive ───────────────────────────────────────────────────
    sorted_claims = sorted(all_claims, key=lambda c: c.created_at)
    for i in range(1, len(sorted_claims)):
        diff = (sorted_claims[i].created_at - sorted_claims[i-1].created_at).total_seconds()
        if diff < 3600:
            score += W_RAPID_CLAIMS
            flags.append("Rapid successive claims: two claims within 1 hour")
            break

    # ── 8. Isolation Forest ML anomaly ───────────────────────────────────────
    is_anomaly, anomaly_strength = _isolation_forest_anomaly(all_claims, now)
    if is_anomaly:
        ml_score = round(W_ML_ANOMALY * anomaly_strength)
        score += ml_score
        flags.append(
            f"ML anomaly (Isolation Forest): claim pattern is statistically "
            f"abnormal (anomaly strength {round(anomaly_strength * 100)}%)"
        )

    score = round(min(score, MAX_SCORE), 1)
    risk_level, action = score_to_action(score)

    return {
        "worker_id":    worker.id,
        "worker_name":  worker.name,
        "location":     worker.location,
        "plan":         policy.plan,
        "total_claims": len(all_claims),
        "claims_month": len(this_month),
        "fraud_score":  score,
        "risk_level":   risk_level,
        "action":       action,
        "flags":        flags,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _stored_value(trigger_type: str, claim: Claim) -> float | None:
    """Read the stored weather snapshot from the claim row."""
    mapping = {
        "rainfall":    claim.weather_rainfall,
        "flood":       claim.weather_rainfall,
        "temperature": claim.weather_temp,
        "aqi":         claim.weather_aqi,
    }
    return mapping.get(trigger_type)


def _cities_claimed_today(claims: list, now: datetime) -> set:
    today  = now.date()
    cities = set()
    for c in claims:
        if c.created_at.date() == today:
            city = _extract_city_from_note(c.admin_note)
            if city:
                cities.add(city.lower())
    return cities


def _extract_city_from_note(note: str | None) -> str | None:
    if not note:
        return None
    if " in " in note:
        parts = note.split(" in ")
        if len(parts) > 1:
            return parts[1].split(" ")[0].rstrip(".—,")
    return None


def _extract_claim_cities(claims: list) -> set:
    cities = set()
    for c in claims:
        city = _extract_city_from_note(c.admin_note)
        if city:
            cities.add(city)
    return cities
