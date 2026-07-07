from datetime import date, timedelta
import requests
import certifi

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_LOCATION = "Atlanta"


def geocode_location(location: str = DEFAULT_LOCATION) -> dict:
    params = {
        "name": location,
        "count": 1,
        "language": "en",
        "format": "json",
    }

    res = requests.get(
        GEOCODE_URL,
        params=params,
        timeout=10,
        verify=certifi.where(),
    )
    res.raise_for_status()
    data = res.json()

    results = data.get("results", [])
    if not results:
        raise ValueError(f"Could not find weather location: {location}")

    place = results[0]
    return {
        "name": place.get("name"),
        "state": place.get("admin1"),
        "country": place.get("country"),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": place.get("timezone", "auto"),
    }


def get_weather_forecast(location: str = DEFAULT_LOCATION, days: int = 7) -> dict:
    place = geocode_location(location)

    params = {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": place["timezone"],
        "forecast_days": days,
        "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code",
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,rain",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
    }

    res = requests.get(
        FORECAST_URL,
        params=params,
        timeout=10,
        verify=certifi.where(),
    )
    res.raise_for_status()

    return {
        "location": place,
        "weather": res.json(),
    }


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