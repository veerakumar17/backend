import joblib
import numpy as np
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "model", "model.pkl")
FEATURES_PATH = os.path.join(BASE_DIR, "model", "features.pkl")

if not os.path.exists(MODEL_PATH) or not os.path.exists(FEATURES_PATH):
    raise RuntimeError(f"Model files not found at {MODEL_PATH}. Run train_model.py first.")

model = joblib.load(MODEL_PATH)
feature_columns = joblib.load(FEATURES_PATH)


def classify_risk(score: float) -> str:
    if score < 0.3:
        return "Low"
    elif score < 0.6:
        return "Medium"
    else:
        return "High"


def predict_risk_from_env(weather: dict, aqi: dict) -> dict:
    rainfall = weather.get("rainfall", 0.0)
    flood_occurred = 1 if rainfall > 70 else 0
    rainfall_flood = rainfall * 1.5
    water_level = rainfall * 0.1
    elevation_flood = weather.get("pressure", 1013.0) * 0.5

    input_data = {
        "avg_temp":       weather["temp"],
        "min_temp":       weather["min_temp"],
        "max_temp":       weather["max_temp"],
        "wind_speed":     weather["wind"],
        "air_pressure":   weather["pressure"],
        "elevation":      200.0,
        "rainfall":       rainfall,
        "PM2.5":          aqi["pm25"],
        "rainfall_flood": rainfall_flood,
        "water_level":    water_level,
        "elevation_flood":elevation_flood,
        "flood_occurred": flood_occurred,
    }

    input_values = np.array([[input_data[col] for col in feature_columns]])
    proba = model.predict_proba(input_values)[0]

    class_weights = np.array([0.0, 0.5, 1.0])
    risk_score = float(round(proba.dot(class_weights), 4))

    return {
        "risk_score": risk_score,
        "risk_level": classify_risk(risk_score),
        "probabilities": {
            "low":    round(float(proba[0]), 4),
            "medium": round(float(proba[1]), 4),
            "high":   round(float(proba[2]), 4),
        }
    }
