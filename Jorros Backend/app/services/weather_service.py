from __future__ import annotations

import hashlib
import math
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings


CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
OFFICIAL_ALERTS_URL = "https://api.openweathermap.org/data/3.0/onecall"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Default coordinates are for Legazpi City, Albay. Change these values in
# Jorros Backend/.env when you have the exact farm coordinates.
DEFAULT_LATITUDE = 13.1391
DEFAULT_LONGITUDE = 123.7438
DEFAULT_LOCATION_NAME = "Joross Farm Area"

_WEATHER_CACHE: dict[str, Any] | None = None
_WEATHER_CACHE_EXPIRES_AT = 0.0
_WEATHER_CACHE_LOCK = Lock()
_WEATHER_CACHE_KEY = None


class WeatherServiceError(RuntimeError):
    pass


def _get_weather_config() -> tuple[str, float, float, str, float]:
    api_key = settings.openweather_api_key.strip()

    if not api_key:
        raise WeatherServiceError(
            "OPENWEATHER_API_KEY is not configured in Jorros Backend/.env."
        )

    latitude = float(settings.openweather_lat)
    longitude = float(settings.openweather_lon)

    location_name = (
        settings.openweather_location_name.strip()
        or DEFAULT_LOCATION_NAME
    )

    timeout_seconds = max(
        2.0,
        float(settings.openweather_timeout_seconds),
    )

    return (
        api_key,
        latitude,
        longitude,
        location_name,
        timeout_seconds,
    )


def _request_json(
    url: str,
    params: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request_url = f"{url}?{urlencode(params)}"
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "JoRoss-Farm-API/1.0",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            error_payload = json.loads(
                exc.read().decode("utf-8")
            )
            message = error_payload.get("message")
        except Exception:
            message = None

        if exc.code == 401:
            detail = (
                "OpenWeather rejected the API key. Check OPENWEATHER_API_KEY."
            )
        elif exc.code == 429:
            detail = (
                "OpenWeather request limit was reached. Please try again later."
            )
        else:
            detail = message or f"OpenWeather returned HTTP {exc.code}."

        raise WeatherServiceError(detail) from exc
    except (URLError, TimeoutError) as exc:
        raise WeatherServiceError(
            "OpenWeather could not be reached. Check the internet connection."
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WeatherServiceError(
            "OpenWeather returned an unreadable response."
        ) from exc

    if not isinstance(payload, dict):
        raise WeatherServiceError(
            "OpenWeather returned an unexpected response."
        )

    return payload


def _local_datetime(
    timestamp: int | float,
    timezone_offset_seconds: int,
) -> datetime:
    local_timezone = timezone(
        timedelta(seconds=timezone_offset_seconds)
    )

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).astimezone(local_timezone)


def _weather_descriptor(payload: dict[str, Any]) -> dict[str, Any]:
    weather_entries = payload.get("weather") or [{}]
    weather = weather_entries[0] if weather_entries else {}

    return {
        "condition": str(weather.get("main") or "Unknown"),
        "description": str(weather.get("description") or "Unknown"),
        "weather_code": int(weather.get("id") or 0),
        "icon": weather.get("icon"),
    }


def _parse_current(
    payload: dict[str, Any],
    timezone_offset_seconds: int,
) -> dict[str, Any]:
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    clouds = payload.get("clouds") or {}
    rain = payload.get("rain") or {}

    descriptor = _weather_descriptor(payload)

    return {
        "observed_at": _local_datetime(
            payload.get("dt") or datetime.now().timestamp(),
            timezone_offset_seconds,
        ),
        "temperature_c": round(float(main.get("temp") or 0), 1),
        "feels_like_c": round(float(main.get("feels_like") or 0), 1),
        "humidity_percent": int(main.get("humidity") or 0),
        **descriptor,
        "wind_speed_kph": round(float(wind.get("speed") or 0) * 3.6, 1),
        "wind_gust_kph": round(float(wind["gust"]) * 3.6, 1) if wind.get("gust") is not None else None,
        "wind_direction_deg": (
            int(wind["deg"])
            if wind.get("deg") is not None
            else None
        ),
        "clouds_percent": int(clouds.get("all") or 0),
        "rain_1h_mm": round(float(rain.get("1h") or 0), 2),
    }


def _parse_forecast_point(
    payload: dict[str, Any],
    timezone_offset_seconds: int,
) -> dict[str, Any]:
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    rain = payload.get("rain") or {}

    descriptor = _weather_descriptor(payload)

    return {
        "forecast_at": _local_datetime(
            payload.get("dt") or datetime.now().timestamp(),
            timezone_offset_seconds,
        ),
        "temperature_c": round(float(main.get("temp") or 0), 1),
        "feels_like_c": round(float(main.get("feels_like") or 0), 1),
        "humidity_percent": int(main.get("humidity") or 0),
        **descriptor,
        "wind_speed_kph": round(float(wind.get("speed") or 0) * 3.6, 1),
        "wind_gust_kph": round(float(wind["gust"]) * 3.6, 1) if wind.get("gust") is not None else None,
        "wind_direction_deg": (
            int(wind["deg"])
            if wind.get("deg") is not None
            else None
        ),
        "rain_probability_percent": round(
            min(max(float(payload.get("pop") or 0), 0), 1) * 100,
            1,
        ),
        "rain_3h_mm": round(float(rain.get("3h") or 0), 2),
    }


def _summarize_next_24_hours(
    forecast: list[dict[str, Any]],
    current: dict[str, Any],
) -> dict[str, Any]:
    next_points = forecast[:8]

    if not next_points:
        current_temperature = float(current["temperature_c"])

        return {
            "max_temperature_c": current_temperature,
            "min_temperature_c": current_temperature,
            "max_wind_speed_kph": float(current["wind_speed_kph"]),
            "rain_total_mm": float(current["rain_1h_mm"]),
            "max_rain_probability_percent": 0,
            "thunderstorm_expected": (
                200 <= int(current["weather_code"]) <= 232
            ),
        }

    temperatures = [
        float(point["temperature_c"])
        for point in next_points
    ]
    wind_speeds = [
        float(point["wind_speed_kph"])
        for point in next_points
    ]
    rain_probabilities = [
        float(point["rain_probability_percent"])
        for point in next_points
    ]

    return {
        "max_temperature_c": round(max(temperatures), 1),
        "min_temperature_c": round(min(temperatures), 1),
        "max_wind_speed_kph": round(max(wind_speeds), 1),
        "max_wind_gust_kph": max((p.get("wind_gust_kph") for p in next_points if p.get("wind_gust_kph") is not None), default=None),
        "rain_total_mm": round(
            sum(float(point["rain_3h_mm"]) for point in next_points),
            2,
        ),
        "max_rain_probability_percent": round(
            max(rain_probabilities),
            1,
        ),
        "thunderstorm_expected": any(
            200 <= int(point["weather_code"]) <= 232
            for point in next_points
        ),
    }


def _validate_observation(payload, *, forecast=False):
    required = ((payload.get("main") or {}).get("temp"),
                (payload.get("main") or {}).get("feels_like"),
                (payload.get("main") or {}).get("humidity"),
                (payload.get("wind") or {}).get("speed"), payload.get("dt"))
    try:
        if any(x is None or not math.isfinite(float(x)) for x in required):
            raise ValueError()
        if forecast and (payload.get("pop") is None or not math.isfinite(float(payload["pop"]))):
            raise ValueError()
    except (TypeError, ValueError, OverflowError) as exc:
        raise WeatherServiceError("OpenWeather returned incomplete observations; conditions are unknown.") from exc


def _parse_official_alerts(payload, latitude, longitude, location):
    now = datetime.now(timezone.utc)
    alerts = {}
    if "alerts" in payload and not isinstance(payload["alerts"], list):
        raise WeatherServiceError("The official warning feed returned an unreadable response.")
    for raw in payload.get("alerts", []):
        if not isinstance(raw, dict):
            continue
        try:
            start = datetime.fromtimestamp(float(raw["start"]), timezone.utc)
            end = datetime.fromtimestamp(float(raw["end"]), timezone.utc)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
        if end <= now or end <= start:
            continue
        source = str(raw.get("sender_name") or "Source not supplied")[:200]
        title = str(raw.get("event") or "Official weather warning")[:200]
        description = str(raw.get("description") or "Description not supplied")[:12000]
        fingerprint = hashlib.sha256(json.dumps([source, title, start.isoformat(), end.isoformat(),
                                                description, latitude, longitude]).encode()).hexdigest()
        alerts[fingerprint] = {"id": fingerprint, "source": source, "event": title,
            "starts_at": start, "ends_at": end, "description": description,
            "location": location, "latitude": latitude, "longitude": longitude,
            "tags": [str(x)[:100] for x in raw.get("tags", [])] if isinstance(raw.get("tags"), list) else [],
            "provider": "OpenWeather One Call 3.0", "reference": "https://openweathermap.org/api/one-call-3"}
    return list(alerts.values())


def _fetch_weather(config):
    api_key, latitude, longitude, location_name, timeout_seconds = config
    params = {"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"}
    enabled = settings.openweather_official_alerts_enabled
    with ThreadPoolExecutor(max_workers=3) as executor:
        current_future = executor.submit(_request_json, CURRENT_WEATHER_URL, params, timeout_seconds)
        forecast_future = executor.submit(_request_json, FORECAST_URL, params, timeout_seconds)
        alert_future = executor.submit(_request_json, OFFICIAL_ALERTS_URL,
            {**params, "exclude": "current,minutely,hourly,daily"}, timeout_seconds) if enabled else None
        current_payload, forecast_payload = current_future.result(), forecast_future.result()
        official_alerts, official_status = [], "Not configured"
        if alert_future:
            try:
                official_alerts = _parse_official_alerts(alert_future.result(), latitude, longitude, location_name)
                official_status = "Available"
            except WeatherServiceError:
                official_status = "Unavailable"
    _validate_observation(current_payload)
    raw_forecast = forecast_payload.get("list")
    if not isinstance(raw_forecast, list) or not raw_forecast:
        raise WeatherServiceError("Weather forecast is unavailable; future conditions are unknown.")
    for point in raw_forecast:
        if not isinstance(point, dict):
            raise WeatherServiceError("Weather forecast contains incomplete observations.")
        _validate_observation(point, forecast=True)
    offset = int(current_payload.get("timezone") or (forecast_payload.get("city") or {}).get("timezone") or 0)
    current = _parse_current(current_payload, offset)
    forecast = [_parse_forecast_point(x, offset) for x in raw_forecast]
    overview = {"location": location_name, "latitude": latitude, "longitude": longitude,
        "timezone_offset_seconds": offset, "current": current,
        "next_24_hours": _summarize_next_24_hours(forecast, current), "forecast": forecast,
        "fetched_at": datetime.now(timezone.utc), "source": "OpenWeather",
        "official_alerts": official_alerts, "official_alerts_status": official_status}
    return overview


def _with_freshness(overview, status, error=None):
    age = max(0, int((datetime.now(timezone.utc) - overview["current"]["observed_at"]).total_seconds()))
    return {**overview, "data_status": "Stale" if age > 3600 else status,
            "observation_age_seconds": age, "last_fetch_error": error or overview.get("last_fetch_error")}


def get_weather_overview() -> dict[str, Any]:
    global _WEATHER_CACHE, _WEATHER_CACHE_EXPIRES_AT, _WEATHER_CACHE_KEY
    config = _get_weather_config()
    key = hashlib.sha256(repr((config, settings.openweather_official_alerts_enabled)).encode()).hexdigest()
    with _WEATHER_CACHE_LOCK:
        cached = _WEATHER_CACHE if _WEATHER_CACHE_KEY == key else None
        if cached is not None and time.monotonic() < _WEATHER_CACHE_EXPIRES_AT:
            return _with_freshness(cached, "Stale" if cached.get("last_fetch_error") else "Cached")
        try:
            overview = _fetch_weather(config)
        except (WeatherServiceError, ValueError, TypeError, OverflowError, OSError) as exc:
            if cached is None:
                raise WeatherServiceError(str(exc) if isinstance(exc, WeatherServiceError) else "Weather data is unavailable.") from exc
            # Last successful observation is visibly stale; never label it normal.
            _WEATHER_CACHE = {**cached, "last_fetch_error": "The latest weather fetch failed. Check the official source.",
                              "official_alerts_status": "Unavailable" if settings.openweather_official_alerts_enabled else "Not configured"}
            _WEATHER_CACHE_EXPIRES_AT = time.monotonic() + 30  # Back off during an outage.
            return _with_freshness(_WEATHER_CACHE, "Stale", _WEATHER_CACHE["last_fetch_error"])
        if overview["official_alerts_status"] == "Unavailable" and cached:
            overview["official_alerts"] = cached.get("official_alerts", [])
        _WEATHER_CACHE, _WEATHER_CACHE_KEY = overview, key
        _WEATHER_CACHE_EXPIRES_AT = time.monotonic() + max(0, int(settings.openweather_cache_seconds))
        return _with_freshness(overview, "Fresh")
