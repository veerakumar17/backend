import requests
import os
from dotenv import load_dotenv

load_dotenv()

AQICN_API_KEY = os.getenv("AQICN_API_KEY")
BASE_URL = "https://api.waqi.info/feed"


def fetch_aqi(city: str) -> dict:
    if not AQICN_API_KEY:
        raise ValueError("AQICN_API_KEY is not set in .env")

    response = requests.get(f"{BASE_URL}/{city}/", params={
        "token": AQICN_API_KEY
    }, timeout=10)

    if response.status_code != 200:
        raise ConnectionError(f"AQICN API error: {response.status_code}")

    data = response.json()

    if data.get("status") != "ok":
        raise ValueError(f"City '{city}' not found in AQICN")

    iaqi = data["data"].get("iaqi", {})

    return {
        "aqi":  data["data"].get("aqi", 0),
        "pm25": iaqi.get("pm25", {}).get("v", 0.0),
        "pm10": iaqi.get("pm10", {}).get("v", 0.0),
    }
