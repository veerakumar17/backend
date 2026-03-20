from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Policy, Claim
from app.schemas import ClaimResponse
from typing import List

router = APIRouter(prefix="/claims", tags=["Claims"])


@router.get("/{worker_id}", response_model=List[ClaimResponse])
def get_claims(worker_id: int, db: Session = Depends(get_db)):
    policy = db.query(Policy).filter(Policy.worker_id == worker_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy.claims
