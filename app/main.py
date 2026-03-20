import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import workers, policies, premiums, triggers, claims, ml, advisor

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Gig Worker Insurance", version="1.0.0")

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workers.router)
app.include_router(policies.router)
app.include_router(premiums.router)
app.include_router(triggers.router)
app.include_router(claims.router)
app.include_router(ml.router)
app.include_router(advisor.router)


@app.get("/")
def root():
    return {"message": "AI Gig Worker Insurance API - Phase 1"}
