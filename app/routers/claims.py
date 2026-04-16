import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Claim, ClaimStatus, PayoutStatus, Worker
from app.schemas import ClaimResponse
from typing import List

router = APIRouter(prefix="/claims", tags=["Claims"])


@router.get("/{worker_id}", response_model=List[ClaimResponse])
def get_claims(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy.claims


@router.post("/process-payout/{claim_id}", response_model=ClaimResponse)
def process_payout(claim_id: int, db: Session = Depends(get_db)):
    """
    Simulates instant UPI payout via mock Razorpay Payout API.
    Generates a realistic transaction ID and marks payout as Processed.
    This simulates the insurer sending money TO the worker's UPI ID.
    """
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.status != ClaimStatus.approved:
        raise HTTPException(status_code=400, detail="Only approved claims can be paid out")
    if claim.payout_status == PayoutStatus.processed:
        raise HTTPException(status_code=400, detail="Payout already processed")

    worker = db.query(Worker).filter(Worker.id == claim.policy.worker_id).first()
    upi_id = worker.upi_id if worker else "unknown@upi"

    # Simulate Razorpay Payout API transaction
    txn_id = f"payout_{uuid.uuid4().hex[:16].upper()}"

    claim.payout_status = PayoutStatus.processed
    claim.payout_transaction_id = txn_id
    claim.payout_processed_at = datetime.utcnow()
    db.commit()
    db.refresh(claim)

    return claim
