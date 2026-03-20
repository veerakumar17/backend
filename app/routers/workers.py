from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.database import get_db
from app.models import Worker
from app.schemas import WorkerCreate, WorkerLogin, WorkerResponse

router = APIRouter(prefix="/workers", tags=["Workers"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/register", response_model=WorkerResponse)
def register_worker(worker: WorkerCreate, db: Session = Depends(get_db)):
    if db.query(Worker).filter(Worker.username == worker.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(Worker).filter(Worker.mobile == worker.mobile).first():
        raise HTTPException(status_code=400, detail="Mobile number already registered")
    if db.query(Worker).filter(Worker.email == worker.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    data = worker.model_dump()
    data["password"] = pwd_context.hash(data["password"])
    new_worker = Worker(**data)
    db.add(new_worker)
    db.commit()
    db.refresh(new_worker)
    return new_worker


@router.post("/login")
def login_worker(credentials: WorkerLogin, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.username == credentials.username).first()
    if not worker or not pwd_context.verify(credentials.password, worker.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {
        "message": "Login successful",
        "worker": {
            "id":                worker.id,
            "username":          worker.username,
            "name":              worker.name,
            "email":             worker.email,
            "location":          worker.location,
            "weekly_salary":     worker.weekly_salary,
            "delivery_platform": worker.delivery_platform,
        }
    }


@router.get("/{worker_id}", response_model=WorkerResponse)
def get_worker(worker_id: int, db: Session = Depends(get_db)):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker
