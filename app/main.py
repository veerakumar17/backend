import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import workers, policies, premiums, triggers, claims, ml, advisor, admin
from app.scheduler import start_scheduler, last_run_info

Base.metadata.create_all(bind=engine)

# ensure AdminUser table is created (model defined in routers/admin)
from app.routers.admin import AdminUser  # noqa: F401, E402
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()


app = FastAPI(title="AI Gig Worker Insurance", version="1.0.0", lifespan=lifespan)

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
app.include_router(admin.router)


@app.get("/")
def root():
    return {"message": "AI Gig Worker Insurance API - Phase 1"}


@app.get("/scheduler/status")
def scheduler_status():
    return last_run_info
