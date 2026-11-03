from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.models import User, WeatherHistory
from app.routers.auth import get_current_user
from app.schemas.weather import WeatherHistoryResponse, WeatherOverviewResponse
from app.services.weather_service import (
    WeatherServiceError,
    get_weather_overview,
)


router = APIRouter(
    prefix="/api/v1/weather",
    dependencies=[Depends(require_permission("weather:view"))],
    tags=["Weather"],
)

def _save_daily_observation(db: Session, overview: dict) -> WeatherHistory:
    current = overview["current"]
    observed_at = current["observed_at"]
    if getattr(observed_at, "tzinfo", None) is not None:
        observed_at = observed_at.replace(tzinfo=None)

    recorded_date = observed_at.date()
    record = db.scalar(
        select(WeatherHistory).where(
            WeatherHistory.recorded_date == recorded_date
        )
    )

    if record is None:
        record = WeatherHistory(recorded_date=recorded_date)
        db.add(record)

    record.observed_at = observed_at
    record.location = overview["location"]
    record.temperature_c = float(current["temperature_c"])
    record.humidity_percent = int(current["humidity_percent"])
    record.rainfall_mm = float(current.get("rain_1h_mm") or 0)
    record.wind_speed_kph = float(current["wind_speed_kph"])
    record.condition = str(current["condition"])
    record.weather_code = int(current["weather_code"])
    record.source = "OpenWeather current observation"

    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=WeatherOverviewResponse)
def get_weather(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        overview = get_weather_overview()
        if overview.get("data_status") != "Stale":
            _save_daily_observation(db, overview)
        return overview
    except WeatherServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/history", response_model=list[WeatherHistoryResponse])
def get_weather_history(
    days: int = Query(default=90, ge=1, le=730),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    start_date = date.today() - timedelta(days=days - 1)
    statement = (
        select(WeatherHistory)
        .where(WeatherHistory.recorded_date >= start_date)
        .order_by(WeatherHistory.recorded_date.asc())
    )
    return list(db.scalars(statement).all())
