from fastapi import APIRouter, HTTPException
from app.services.weather_service import fetch_weather
from app.services.aqi_service import fetch_aqi
from app.services.risk_service import predict_risk_from_env

router = APIRouter(prefix="/ml", tags=["ML Risk Prediction"])

# Fallback weather data used when the API key is invalid or city not found
FALLBACK_WEATHER = {
    "temp": 32.0, "min_temp": 28.0, "max_temp": 36.0,
    "humidity": 70, "wind": 3.5, "pressure": 1010.0, "rainfall": 0.0,
}
FALLBACK_AQI = {"aqi": 85, "pm25": 35.0, "pm10": 50.0}


@router.get("/risk-by-location")
def risk_by_location(city: str):
    weather_error = None
    aqi_error = None

    try:
        weather = fetch_weather(city)
    except (ValueError, ConnectionError) as e:
        weather = FALLBACK_WEATHER
        weather_error = str(e)

    try:
        aqi = fetch_aqi(city)
    except (ValueError, ConnectionError) as e:
        aqi = FALLBACK_AQI
        aqi_error = str(e)

    result = predict_risk_from_env(weather, aqi)

    response = {
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

    if weather_error or aqi_error:
        response["warning"] = "Live weather data unavailable; using fallback values. Update OPENWEATHER_API_KEY in .env."

    return response
