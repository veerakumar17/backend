from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.advisor_service import get_plan_recommendation

router = APIRouter(prefix="/advisor", tags=["AI Plan Advisor"])


class AdvisorRequest(BaseModel):
    weekly_salary: float
    risk_score: float
    weather_condition: str


@router.post("/recommend-plan")
def recommend_plan(data: AdvisorRequest):
    try:
        result = get_plan_recommendation(
            weekly_salary=data.weekly_salary,
            risk_score=data.risk_score,
            weather_condition=data.weather_condition,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
