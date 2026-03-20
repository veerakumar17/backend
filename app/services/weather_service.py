import requests
import os
from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


def fetch_weather(city: str) -> dict:
    if not OPENWEATHER_API_KEY:
        raise ValueError("OPENWEATHER_API_KEY is not set in .env")

    response = requests.get(BASE_URL, params={
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }, timeout=10)

    if response.status_code == 404:
        raise ValueError(f"City '{city}' not found in OpenWeatherMap")
    if response.status_code != 200:
        raise ConnectionError(f"OpenWeatherMap API error: {response.status_code}")

    data = response.json()

    return {
        "temp":     data["main"]["temp"],
        "min_temp": data["main"]["temp_min"],
        "max_temp": data["main"]["temp_max"],
        "humidity": data["main"]["humidity"],
        "wind":     data["wind"]["speed"],
        "pressure": data["main"]["pressure"],
        "rainfall": data.get("rain", {}).get("1h", 0.0),
    }
