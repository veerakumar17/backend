from fastapi import APIRouter, HTTPException
from app.services.weather_service import fetch_weather
from app.services.aqi_service import fetch_aqi
from app.services.risk_service import predict_risk_from_env

router = APIRouter(prefix="/ml", tags=["ML Risk Prediction"])


@router.get("/risk-by-location")
def risk_by_location(city: str):
    try:
        weather = fetch_weather(city)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        aqi = fetch_aqi(city)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))

    result = predict_risk_from_env(weather, aqi)

    return {
        "location": city,
        "features": {
            "rainfall":  weather["rainfall"],
            "temp":      weather["temp"],
            "humidity":  weather["humidity"],
            "wind":      weather["wind"],
            "aqi":       aqi["aqi"],
            "pm25":      aqi["pm25"],
        },
        "risk_score":    result["risk_score"],
        "risk_level":    result["risk_level"],
        "probabilities": result["probabilities"],
    }
