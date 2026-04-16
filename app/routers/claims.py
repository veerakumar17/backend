import os
import hmac
import hashlib
import razorpay
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Claim, ClaimStatus, PayoutStatus, Worker
from app.schemas import ClaimResponse
from typing import List

router = APIRouter(prefix="/claims", tags=["Claims"])

RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "rzp_test_SeC3QEyHtn66un")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

def get_razorpay_client():
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


@router.get("/{worker_id}", response_model=List[ClaimResponse])
def get_claims(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy.claims


@router.post("/create-payout-order/{claim_id}")
def create_payout_order(claim_id: int, db: Session = Depends(get_db)):
    """
    Creates a Razorpay test order for the claim payout amount.
    Returns order_id and key_id for frontend checkout.
    """
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != ClaimStatus.approved:
        raise HTTPException(status_code=400, detail="Only approved claims can be paid out")
    if claim.payout_status == PayoutStatus.processed:
        raise HTTPException(status_code=400, detail="Payout already processed")

    worker = db.query(Worker).filter(Worker.id == claim.policy.worker_id).first()

    try:
        client = get_razorpay_client()
        order = client.order.create({
            "amount":   int(claim.payout_amount * 100),  # paise
            "currency": "INR",
            "receipt":  f"claim_{claim_id}",
            "notes": {
                "claim_id":   str(claim_id),
                "worker_name": worker.name if worker else "",
                "upi_id":     worker.upi_id if worker else "",
                "trigger":    claim.trigger_type,
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Razorpay order creation failed: {str(e)}")

    return {
        "order_id":      order["id"],
        "amount":        claim.payout_amount,
        "currency":      "INR",
        "key_id":        RAZORPAY_KEY_ID,
        "worker_name":   worker.name if worker else "",
        "worker_email":  worker.email if worker else "",
        "worker_mobile": worker.mobile if worker else "",
        "upi_id":        worker.upi_id if worker else "",
        "claim_id":      claim_id,
    }


@router.post("/verify-payout/{claim_id}", response_model=ClaimResponse)
def verify_payout(claim_id: int, data: dict, db: Session = Depends(get_db)):
    """
    Verifies Razorpay payment signature and marks payout as processed.
    """
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.payout_status == PayoutStatus.processed:
        return claim

    razorpay_order_id   = data.get("razorpay_order_id", "")
    razorpay_payment_id = data.get("razorpay_payment_id", "")
    razorpay_signature  = data.get("razorpay_signature", "")

    # Verify signature
    msg = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected != razorpay_signature:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    claim.payout_status           = PayoutStatus.processed
    claim.payout_transaction_id   = razorpay_payment_id
    claim.payout_processed_at     = datetime.utcnow()
    db.commit()
    db.refresh(claim)
    return claim


@router.post("/process-payout/{claim_id}", response_model=ClaimResponse)
def process_payout(claim_id: int, db: Session = Depends(get_db)):
    """
    Fallback: marks payout as processed with Razorpay order ID as txn reference.
    Used when frontend completes Razorpay checkout.
    """
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != ClaimStatus.approved:
        raise HTTPException(status_code=400, detail="Only approved claims can be paid out")
    if claim.payout_status == PayoutStatus.processed:
        return claim

    worker = db.query(Worker).filter(Worker.id == claim.policy.worker_id).first()

    try:
        client = get_razorpay_client()
        order  = client.order.create({
            "amount":   int(claim.payout_amount * 100),
            "currency": "INR",
            "receipt":  f"claim_{claim_id}",
        })
        txn_id = order["id"]
    except Exception:
        txn_id = f"RZP_{claim_id}_{int(datetime.utcnow().timestamp())}"

    claim.payout_status           = PayoutStatus.processed
    claim.payout_transaction_id   = txn_id
    claim.payout_processed_at     = datetime.utcnow()
    db.commit()
    db.refresh(claim)
    return claim
