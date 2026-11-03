"""Weather retrieval uses synthetic provider payloads; no external API calls."""
from datetime import datetime, timedelta, timezone
import pytest
from app.services import weather_service as weather

@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(weather.settings, "openweather_api_key", "synthetic-test-key")
    monkeypatch.setattr(weather.settings, "openweather_cache_seconds", 300)
    monkeypatch.setattr(weather.settings, "openweather_official_alerts_enabled", False)
    monkeypatch.setattr(weather, "_WEATHER_CACHE", None)
    monkeypatch.setattr(weather, "_WEATHER_CACHE_KEY", None)
    monkeypatch.setattr(weather, "_WEATHER_CACHE_EXPIRES_AT", 0)
    now = datetime.now(timezone.utc)
    point = {"dt": int(now.timestamp()), "main": {"temp": 30, "feels_like": 32, "humidity": 80},
             "wind": {"speed": 8, "gust": 19}, "pop": .5, "weather": [{"id": 500, "main": "Rain", "description": "light rain"}]}
    calls = []
    def request(url, params, timeout):
        calls.append(url)
        if url == weather.CURRENT_WEATHER_URL: return {**point, "timezone": 28800}
        if url == weather.FORECAST_URL: return {"list": [{**point, "dt": point["dt"] + 10800}]}
        return {"alerts": [{"sender_name": "Test issuing authority", "event": "Test wind advisory", "start": int((now - timedelta(hours=1)).timestamp()), "end": int((now + timedelta(hours=2)).timestamp()), "description": "Synthetic advisory for configured coordinates", "tags": ["Wind"]}]}
    monkeypatch.setattr(weather, "_request_json", request)
    return calls, point, request


def test_official_feed_is_opt_in_and_cached_data_keeps_age_and_gusts(provider):
    calls, point, _ = provider
    result = weather.get_weather_overview()
    assert result["data_status"] == "Fresh"
    assert result["current"]["wind_gust_kph"] == 68.4
    assert result["next_24_hours"]["max_wind_gust_kph"] == 68.4
    assert result["official_alerts_status"] == "Not configured"
    assert weather.OFFICIAL_ALERTS_URL not in calls
    again = weather.get_weather_overview()
    assert again["data_status"] == "Cached" and again["fetched_at"] == result["fetched_at"]
    assert len(calls) == 2


def test_opted_in_alerts_keep_source_validity_location_and_stable_identity(provider, monkeypatch):
    monkeypatch.setattr(weather.settings, "openweather_official_alerts_enabled", True)
    first = weather.get_weather_overview()
    assert first["official_alerts_status"] == "Available"
    warning = first["official_alerts"][0]
    assert warning["source"] == "Test issuing authority"
    assert warning["ends_at"] > warning["starts_at"]
    assert warning["latitude"] == first["latitude"] and len(warning["id"]) == 64
    monkeypatch.setattr(weather, "_WEATHER_CACHE_EXPIRES_AT", 0)
    assert weather.get_weather_overview()["official_alerts"][0]["id"] == warning["id"]


def test_feed_failure_does_not_claim_no_warning_or_hide_weather(provider, monkeypatch):
    calls, point, request = provider
    monkeypatch.setattr(weather.settings, "openweather_official_alerts_enabled", True)
    def fail_feed(url, params, timeout):
        if url == weather.OFFICIAL_ALERTS_URL: raise weather.WeatherServiceError("Unavailable")
        return request(url, params, timeout)
    monkeypatch.setattr(weather, "_request_json", fail_feed)
    result = weather.get_weather_overview()
    assert result["data_status"] == "Fresh"
    assert result["official_alerts_status"] == "Unavailable"


def test_fetch_failure_returns_visibly_stale_last_success_without_new_history(provider, monkeypatch):
    first = weather.get_weather_overview()
    monkeypatch.setattr(weather, "_WEATHER_CACHE_EXPIRES_AT", 0)
    def fail(*args): raise weather.WeatherServiceError("Network unavailable")
    monkeypatch.setattr(weather, "_request_json", fail)
    result = weather.get_weather_overview()
    assert result["data_status"] == "Stale" and result["last_fetch_error"]
    assert result["current"] == first["current"] and result["fetched_at"] == first["fetched_at"]


@pytest.mark.parametrize("missing", ["main", "wind", "dt", "forecast"])
def test_incomplete_data_is_unavailable_instead_of_zero_and_normal(provider, monkeypatch, missing):
    calls, point, request = provider
    def incomplete(url, params, timeout):
        if url == weather.FORECAST_URL and missing == "forecast": return {"list": []}
        payload = request(url, params, timeout)
        if url == weather.CURRENT_WEATHER_URL: payload.pop(missing, None)
        return payload
    monkeypatch.setattr(weather, "_request_json", incomplete)
    with pytest.raises(weather.WeatherServiceError, match="incomplete|unavailable"):
        weather.get_weather_overview()


def test_expired_malformed_and_duplicate_official_warnings_are_filtered(provider):
    now = datetime.now(timezone.utc).timestamp()
    alert = {"sender_name": "Test authority", "event": "Test advisory", "start": now - 10, "end": now + 100}
    payload = {"alerts": [alert, dict(alert), {**alert, "end": now - 1}, {**alert, "end": "bad"}]}
    assert len(weather._parse_official_alerts(payload, 1, 2, "Test farm")) == 1
