"""Current model conditions and short-term forecasts, independent of NASA.

API contract: https://open-meteo.com/en/docs. Successful responses are cached
for 15 minutes; a failed refresh never becomes a fabricated or stale forecast.
"""
from datetime import date, datetime, timedelta
import math
from zoneinfo import ZoneInfo

import requests
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _


ENDPOINT = "https://api.open-meteo.com/v1/forecast"
DOCUMENTATION_URL = "https://open-meteo.com/en/docs"
CACHE_SECONDS = 15 * 60
DHAKA = ZoneInfo("Asia/Dhaka")
CURRENT_UNITS = {
    "temperature_2m": "°C", "relative_humidity_2m": "%",
    "precipitation": "mm", "weather_code": "wmo code", "wind_speed_10m": "km/h",
}
DAILY_UNITS = {
    "weather_code": "wmo code", "temperature_2m_max": "°C",
    "temperature_2m_min": "°C", "precipitation_sum": "mm",
    "precipitation_probability_max": "%", "wind_speed_10m_max": "km/h",
}


class WeatherUnavailable(Exception):
    """The provider could not supply a complete, valid forecast."""


def condition_label(code):
    """WMO codes are presented at request time so cached data stay bilingual."""
    labels = {
        0: _("Clear sky"), 1: _("Mainly clear"), 2: _("Partly cloudy"),
        3: _("Overcast"), 45: _("Fog"), 48: _("Freezing fog"),
        51: _("Light drizzle"), 53: _("Drizzle"), 55: _("Heavy drizzle"),
        56: _("Freezing drizzle"), 57: _("Freezing drizzle"),
        61: _("Light rain"), 63: _("Rain"), 65: _("Heavy rain"),
        66: _("Freezing rain"), 67: _("Freezing rain"),
        71: _("Light snow"), 73: _("Snow"), 75: _("Heavy snow"),
        77: _("Snow grains"), 80: _("Light rain showers"),
        81: _("Rain showers"), 82: _("Heavy rain showers"),
        85: _("Snow showers"), 86: _("Heavy snow showers"),
        95: _("Thunderstorm"), 96: _("Thunderstorm with hail"),
        99: _("Thunderstorm with hail"),
    }
    return labels.get(code, _("Conditions unavailable"))


def _number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("Invalid weather value")
    return value


def _values(record, *, daily=False):
    code = _number(record["weather_code"], 0, 99)
    if int(code) != code:
        raise ValueError("Invalid WMO code")
    result = {"weather_code": int(code)}
    if daily:
        low = _number(record["temperature_2m_min"], -100, 70)
        high = _number(record["temperature_2m_max"], -100, 70)
        if low > high:
            raise ValueError("Inverted temperature range")
        result.update({
            "minimum_c": low, "maximum_c": high,
            "precipitation_mm": _number(record["precipitation_sum"], 0, 3000),
            "rain_probability": _number(record["precipitation_probability_max"], 0, 100),
            "wind_kmh": _number(record["wind_speed_10m_max"], 0, 500),
        })
    else:
        result.update({
            "temperature_c": _number(record["temperature_2m"], -100, 70),
            "humidity_pct": _number(record["relative_humidity_2m"], 0, 100),
            "precipitation_mm": _number(record["precipitation"], 0, 1000),
            "wind_kmh": _number(record["wind_speed_10m"], 0, 500),
        })
    return result


def _normalize(payload, retrieved_at):
    if not isinstance(payload, dict) or payload.get("error"):
        raise ValueError("Provider error")
    if payload.get("timezone") != "Asia/Dhaka" or payload.get("utc_offset_seconds") != 21600:
        raise ValueError("Unexpected forecast timezone")
    for section, expected in (("current_units", CURRENT_UNITS), ("daily_units", DAILY_UNITS)):
        if any(payload.get(section, {}).get(key) != unit for key, unit in expected.items()):
            raise ValueError("Unexpected weather units")
    current = _values(payload["current"])
    current_time = datetime.fromisoformat(payload["current"]["time"])
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=DHAKA)
    # Do not label an old fixture or stale upstream response as current weather.
    if abs((retrieved_at - current_time).total_seconds()) > 3 * 60 * 60:
        raise ValueError("Current weather timestamp is stale")
    current["time"] = current_time
    current["interval_minutes"] = _number(payload["current"]["interval"], 60, 3600) / 60
    daily = payload["daily"]
    variables = ("time", *DAILY_UNITS)
    if any(not isinstance(daily.get(key), list) or len(daily[key]) != 7 for key in variables):
        raise ValueError("Incomplete seven-day forecast")
    days = []
    for index in range(7):
        day = date.fromisoformat(daily["time"][index])
        if day != retrieved_at.astimezone(DHAKA).date() + timedelta(days=index):
            raise ValueError("Unexpected forecast dates")
        values = _values({key: daily[key][index] for key in DAILY_UNITS}, daily=True)
        days.append({"date": day, **values})
    return {"current": current, "days": days, "retrieved_at": retrieved_at, "timezone": "Asia/Dhaka", "source_url": DOCUMENTATION_URL}


def get_weather(latitude, longitude, *, refresh=False):
    """Fetch weather for coordinates; never reuse the NASA historical baseline."""
    try:
        _number(latitude, -90, 90)
        _number(longitude, -180, 180)
    except ValueError as error:
        raise WeatherUnavailable(_("Weather is unavailable for these coordinates.")) from error
    now = timezone.now()
    key = f"weather:v1:{latitude:.5f}:{longitude:.5f}:{now.astimezone(DHAKA).date().isoformat()}"
    if not refresh:
        saved = cache.get(key)
        if saved is not None:
            return saved
    params = {
        "latitude": latitude, "longitude": longitude,
        "current": ",".join(CURRENT_UNITS), "daily": ",".join(DAILY_UNITS),
        "timezone": "Asia/Dhaka", "forecast_days": 7,
        "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
    }
    try:
        response = requests.get(ENDPOINT, params=params, timeout=(4, 12))
        response.raise_for_status()
        result = _normalize(response.json(), timezone.now())
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        raise WeatherUnavailable(_("The weather provider is unavailable or returned incomplete data. Please try again shortly.")) from error
    cache.set(key, result, CACHE_SECONDS)
    return result
