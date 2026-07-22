from datetime import date, timedelta
from functools import lru_cache
import requests
import certifi
import time
import logging

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
LOGGER = logging.getLogger(__name__)
_SESSION = requests.Session()
_FORECAST_CACHE: dict[tuple[str, int], tuple[float, dict]] = {}
FORECAST_CACHE_SECONDS = 300

DEFAULT_LOCATION = "Atlanta"

@lru_cache(maxsize=64)
def geocode_location(location: str = DEFAULT_LOCATION) -> dict:
    location = location.strip() or DEFAULT_LOCATION
    started = time.perf_counter()

    params = {
        "name": location,
        "count": 1,
        "language": "en",
        "format": "json",
    }

    res = _SESSION.get(
        GEOCODE_URL,
        params=params,
        timeout=(3, 7),
        verify=certifi.where(),
    )
    res.raise_for_status()

    LOGGER.info(
        "WEATHER GEOCODE TIMING: %.3fs for %s",
        time.perf_counter() - started,
        location,
    )

    data = res.json()

    results = data.get("results", [])
    if not results:
        raise ValueError(
            f"Could not find weather location: {location}"
        )

    place = results[0]

    return {
        "name": place.get("name"),
        "state": place.get("admin1"),
        "country": place.get("country"),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": place.get("timezone", "auto"),
    }

def get_weather_forecast(
    location: str = DEFAULT_LOCATION,
    days: int = 7,
) -> dict:
    normalized_location = location.strip() or DEFAULT_LOCATION
    cache_key = (normalized_location.casefold(), days)
    now = time.monotonic()

    cached = _FORECAST_CACHE.get(cache_key)

    if cached:
        cached_at, cached_data = cached

        if now - cached_at < FORECAST_CACHE_SECONDS:
            LOGGER.info(
                "WEATHER CACHE HIT: %s, %s days",
                normalized_location,
                days,
            )
            return cached_data

    place = geocode_location(normalized_location)

    params = {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": place["timezone"],
        "forecast_days": days,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain,"
            "weather_code"
        ),
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_probability_max,"
            "weather_code"
        ),
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
    }

    started = time.perf_counter()

    res = _SESSION.get(
        FORECAST_URL,
        params=params,
        timeout=(3, 7),
        verify=certifi.where(),
    )
    res.raise_for_status()

    result = {
        "location": place,
        "weather": res.json(),
    }

    _FORECAST_CACHE[cache_key] = (now, result)

    LOGGER.info(
        "WEATHER FORECAST TIMING: %.3fs for %s",
        time.perf_counter() - started,
        normalized_location,
    )

    return result

def summarize_today(location: str = DEFAULT_LOCATION) -> str:
    data = get_weather_forecast(location, days=1)
    place = data["location"]
    weather = data["weather"]

    current = weather.get("current", {})
    daily = weather.get("daily", {})

    high = daily["temperature_2m_max"][0]
    low = daily["temperature_2m_min"][0]
    rain_chance = daily["precipitation_probability_max"][0]
    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")

    return (
        f"Weather for {place['name']}: currently {temp}°F with {humidity}% humidity. "
        f"Today's high is {high}°F and the low is {low}°F. "
        f"Chance of rain is up to {rain_chance}%."
    )


def summarize_tomorrow(location: str = DEFAULT_LOCATION) -> str:
    data = get_weather_forecast(location, days=2)
    place = data["location"]
    daily = data["weather"]["daily"]

    high = daily["temperature_2m_max"][1]
    low = daily["temperature_2m_min"][1]
    rain_chance = daily["precipitation_probability_max"][1]

    return (
        f"Tomorrow in {place['name']}: high of {high}°F, low of {low}°F, "
        f"with up to a {rain_chance}% chance of rain."
    )


def summarize_week(location: str = DEFAULT_LOCATION) -> str:
    data = get_weather_forecast(location, days=7)
    place = data["location"]
    daily = data["weather"]["daily"]

    lines = [f"Weather this week for {place['name']}:"]
    for i, day in enumerate(daily["time"]):
        high = daily["temperature_2m_max"][i]
        low = daily["temperature_2m_min"][i]
        rain = daily["precipitation_probability_max"][i]
        lines.append(f"- {day}: High {high}°F, low {low}°F, rain chance {rain}%")

    return "\n".join(lines)


def get_high_today(location: str = DEFAULT_LOCATION) -> str:
    data = get_weather_forecast(location, days=1)
    high = data["weather"]["daily"]["temperature_2m_max"][0]
    place = data["location"]["name"]
    return f"The high today in {place} is {high}°F."


def get_humidity_today(location: str = DEFAULT_LOCATION) -> str:
    data = get_weather_forecast(location, days=1)
    humidity = data["weather"]["current"]["relative_humidity_2m"]
    place = data["location"]["name"]
    return f"The current humidity in {place} is {humidity}%."


def get_rain_chance_tomorrow(location: str = DEFAULT_LOCATION) -> str:
    data = get_weather_forecast(location, days=2)
    rain = data["weather"]["daily"]["precipitation_probability_max"][1]
    place = data["location"]["name"]
    return f"The chance of rain tomorrow in {place} is up to {rain}%."