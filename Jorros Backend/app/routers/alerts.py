from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import has_permission, require_permission
from app.models import AlertSettings, FarmAlert, User
from app.routers.auth import get_current_user
from app.services.alert_engine import evaluate_automatic_alerts
from app.schemas.alerts import (
    ALLOWED_ALERT_CATEGORIES,
    ALLOWED_ALERT_CONDITIONS,
    ALLOWED_ALERT_PRIORITIES,
    ALLOWED_ALERT_STATUSES,
    AlertSettingsPayload,
    AlertSettingsResponse,
    CropAlertSettings,
    FarmAlertCreate,
    FarmAlertResponse,
    FarmAlertUpdate,
    LivestockAlertSettings,
    SystemAlertSettings,
    WeatherAlertSettings,
)


router = APIRouter(
    prefix="/api/v1/alerts",
    dependencies=[Depends(require_permission("alerts:view"))],
    tags=["Farm Alerts"],
)


def _require_alert_permission(current_user: User, permission: str, message: str) -> User:
    if not has_permission(current_user, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )
    return current_user


def require_alert_creator(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_alert_permission(
        current_user, "alerts:create", "You do not have permission to create alerts."
    )


def require_alert_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_alert_permission(
        current_user, "alerts:update", "You do not have permission to manage alerts."
    )


def require_alert_tester(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_alert_permission(
        current_user, "alerts:test", "You do not have permission to run alert evaluation."
    )


def require_alert_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a System Administrator can change alert settings.",
        )
    return current_user


def clean_required_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} is required.",
        )
    return cleaned


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def validate_alert_values(changes: dict):
    category = changes.get("category")
    priority = changes.get("priority")
    alert_status = changes.get("status")
    condition = changes.get("condition")

    if category is not None and category not in ALLOWED_ALERT_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid alert category.")
    if priority is not None and priority not in ALLOWED_ALERT_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid alert priority.")
    if alert_status is not None and alert_status not in ALLOWED_ALERT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid alert status.")
    if condition is not None and condition not in ALLOWED_ALERT_CONDITIONS:
        raise HTTPException(status_code=400, detail="Invalid alert condition.")


def get_alert_or_404(alert_id: int, db: Session) -> FarmAlert:
    alert = db.scalar(select(FarmAlert).where(FarmAlert.id == alert_id))
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )
    return alert


def get_or_create_settings(db: Session) -> AlertSettings:
    settings = db.scalar(select(AlertSettings).order_by(AlertSettings.id.asc()))
    if settings is not None:
        return settings

    settings = AlertSettings()
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def settings_to_response(settings: AlertSettings) -> AlertSettingsResponse:
    return AlertSettingsResponse(
        id=settings.id,
        crop=CropAlertSettings(
            planting_reminder=settings.crop_planting_reminder,
            growth_check=settings.crop_growth_check,
            harvest_reminder=settings.crop_harvest_reminder,
            pest_disease_alert=settings.crop_pest_disease_alert,
            harvest_advance_days=settings.crop_harvest_advance_days,
            growth_check_frequency=settings.crop_growth_check_frequency,
            soil_moisture_threshold=settings.crop_soil_moisture_threshold,
        ),
        livestock=LivestockAlertSettings(
            feeding_reminder=settings.livestock_feeding_reminder,
            vaccination_reminder=settings.livestock_vaccination_reminder,
            health_check=settings.livestock_health_check,
            production_check=settings.livestock_production_check,
            vaccination_advance_days=settings.livestock_vaccination_advance_days,
            health_check_frequency=settings.livestock_health_check_frequency,
            feeding_reminder_time=settings.livestock_feeding_reminder_time,
        ),
        weather=WeatherAlertSettings(
            heavy_rain_alert=settings.weather_heavy_rain_alert,
            high_temperature_alert=settings.weather_high_temperature_alert,
            strong_wind_alert=settings.weather_strong_wind_alert,
            thunderstorm_alert=settings.weather_thunderstorm_alert,
            rainfall_threshold=settings.weather_rainfall_threshold,
            temperature_threshold=settings.weather_temperature_threshold,
            wind_speed_threshold=settings.weather_wind_speed_threshold,
        ),
        system=SystemAlertSettings(
            backup_reminder=settings.system_backup_reminder,
            low_inventory_alert=settings.system_low_inventory_alert,
            low_storage_alert=settings.system_low_storage_alert,
            failed_login_alert=settings.system_failed_login_alert,
            backup_frequency=settings.system_backup_frequency,
            storage_threshold=settings.system_storage_threshold,
            failed_login_limit=settings.system_failed_login_limit,
        ),
        updated_by_user_id=settings.updated_by_user_id,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get("/settings", response_model=AlertSettingsResponse)
def get_alert_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return settings_to_response(get_or_create_settings(db))


@router.put("/settings", response_model=AlertSettingsResponse)
def update_alert_settings(
    payload: AlertSettingsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_alert_admin),
):
    settings = get_or_create_settings(db)

    crop = payload.crop
    settings.crop_planting_reminder = crop.planting_reminder
    settings.crop_growth_check = crop.growth_check
    settings.crop_harvest_reminder = crop.harvest_reminder
    settings.crop_pest_disease_alert = crop.pest_disease_alert
    settings.crop_harvest_advance_days = crop.harvest_advance_days
    settings.crop_growth_check_frequency = crop.growth_check_frequency
    settings.crop_soil_moisture_threshold = crop.soil_moisture_threshold

    livestock = payload.livestock
    settings.livestock_feeding_reminder = livestock.feeding_reminder
    settings.livestock_vaccination_reminder = livestock.vaccination_reminder
    settings.livestock_health_check = livestock.health_check
    settings.livestock_production_check = livestock.production_check
    settings.livestock_vaccination_advance_days = livestock.vaccination_advance_days
    settings.livestock_health_check_frequency = livestock.health_check_frequency
    settings.livestock_feeding_reminder_time = livestock.feeding_reminder_time

    weather = payload.weather
    settings.weather_heavy_rain_alert = weather.heavy_rain_alert
    settings.weather_high_temperature_alert = weather.high_temperature_alert
    settings.weather_strong_wind_alert = weather.strong_wind_alert
    settings.weather_thunderstorm_alert = weather.thunderstorm_alert
    settings.weather_rainfall_threshold = weather.rainfall_threshold
    settings.weather_temperature_threshold = weather.temperature_threshold
    settings.weather_wind_speed_threshold = weather.wind_speed_threshold

    system = payload.system
    settings.system_backup_reminder = system.backup_reminder
    settings.system_low_inventory_alert = system.low_inventory_alert
    settings.system_low_storage_alert = system.low_storage_alert
    settings.system_failed_login_alert = system.failed_login_alert
    settings.system_backup_frequency = system.backup_frequency
    settings.system_storage_threshold = system.storage_threshold
    settings.system_failed_login_limit = system.failed_login_limit

    settings.updated_by_user_id = current_user.id
    settings.updated_at = datetime.now()

    db.commit()
    db.refresh(settings)
    return settings_to_response(settings)


@router.get("", response_model=list[FarmAlertResponse])
def list_alerts(
    category: str | None = Query(default=None),
    alert_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = select(FarmAlert).order_by(FarmAlert.id.desc())

    if category is not None:
        statement = statement.where(FarmAlert.category == category)
    if alert_status is not None:
        statement = statement.where(FarmAlert.status == alert_status)

    return list(db.scalars(statement).all())


@router.get("/page")
def alert_page(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    view: str = Query("active", pattern="^(active|history)$"),
    category: str | None = None, search: str | None = Query(None, max_length=120),
    priority: str | None = None, source_type: str | None = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    stmt = select(FarmAlert).where(FarmAlert.status == "Active" if view == "active" else
                                   FarmAlert.status != "Active")
    if category and category != "All":
        stmt = stmt.where(FarmAlert.category == category)
    if priority == "high":
        stmt = stmt.where(FarmAlert.priority.in_(["High", "Critical"]))
    if source_type == "task":
        stmt = stmt.where(FarmAlert.source_type == "activity_task")
    if search and search.strip():
        word = search.strip().lower()
        needle = f"%{word}%"
        fields = [FarmAlert.alert_name.ilike(needle), FarmAlert.subject.ilike(needle),
                  FarmAlert.category.ilike(needle), FarmAlert.alert_type.ilike(needle),
                  FarmAlert.description.ilike(needle), FarmAlert.source_type.ilike(needle)]
        if "system".find(word) >= 0:
            fields.append(FarmAlert.is_automatic == True)
        if "manual".find(word) >= 0:
            fields.append(FarmAlert.is_automatic == False)
        stmt = stmt.where(or_(*fields))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = (FarmAlert.updated_at.desc(), FarmAlert.id.desc()) if view == "history" else (FarmAlert.id.desc(),)
    rows = list(db.scalars(stmt.order_by(*order).offset(offset).limit(limit)).all())
    return {"items": [FarmAlertResponse.model_validate(row).model_dump(mode="json") for row in rows],
            "total": total, "offset": offset, "limit": limit}


@router.get("/summary")
def alert_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    grouped = db.execute(select(FarmAlert.status, func.count(FarmAlert.id))
                         .group_by(FarmAlert.status)).all()
    counts = dict(grouped)
    high, overdue = db.execute(select(
        func.sum(case((FarmAlert.priority.in_(["High", "Critical"]), 1), else_=0)),
        func.sum(case(((FarmAlert.source_type == "activity_task") &
                       (FarmAlert.alert_name == "Overdue Task"), 1), else_=0)),
    ).where(FarmAlert.status == "Active")).one()
    return {"active": counts.get("Active", 0), "history": sum(counts.values()) - counts.get("Active", 0),
            "high_priority": high or 0, "overdue_tasks": overdue or 0}


@router.get("/notification-preview", response_model=list[FarmAlertResponse])
def notification_preview(limit: int = Query(30, ge=1, le=50), db: Session = Depends(get_db),
                         _: User = Depends(get_current_user)):
    return list(db.scalars(select(FarmAlert).where(FarmAlert.last_triggered.is_not(None))
                           .order_by(FarmAlert.last_triggered.desc(), FarmAlert.id.desc()).limit(limit)).all())


@router.get("/active-count")
def active_alert_count(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"count": db.scalar(select(func.count(FarmAlert.id)).where(
        FarmAlert.status == "Active", FarmAlert.last_triggered.is_not(None))) or 0}


@router.post(
    "",
    response_model=FarmAlertResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_alert(
    payload: FarmAlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_alert_creator),
):
    alert = FarmAlert(
        alert_name=clean_required_text(payload.alert_name, "Alert name"),
        category=payload.category,
        subject=clean_required_text(payload.subject, "Subject"),
        alert_type=clean_required_text(payload.alert_type, "Alert type"),
        condition=payload.condition,
        threshold=clean_required_text(payload.threshold, "Threshold"),
        unit=clean_optional_text(payload.unit),
        priority=payload.priority,
        status=payload.status,
        description=clean_optional_text(payload.description),
        is_automatic=False,
        source_type=clean_optional_text(payload.source_type),
        source_id=payload.source_id,
        created_by_user_id=current_user.id,
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/evaluate", response_model=list[FarmAlertResponse])
def evaluate_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(require_alert_tester),
):
    evaluate_automatic_alerts(db)
    return list(
        db.scalars(
            select(FarmAlert).order_by(FarmAlert.id.desc())
        ).all()
    )


@router.get("/{alert_id}", response_model=FarmAlertResponse)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return get_alert_or_404(alert_id, db)


@router.put("/{alert_id}", response_model=FarmAlertResponse)
def update_alert(
    alert_id: int,
    payload: FarmAlertUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_alert_editor),
):
    alert = get_alert_or_404(alert_id, db)
    if alert.is_automatic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System-generated alerts are managed automatically and cannot be edited.",
        )

    changes = payload.model_dump(exclude_unset=True)
    validate_alert_values(changes)

    required_text_fields = {
        "alert_name": "Alert name",
        "subject": "Subject",
        "alert_type": "Alert type",
        "threshold": "Threshold",
    }
    optional_text_fields = {"unit", "description", "source_type"}

    for field_name, value in changes.items():
        if field_name in required_text_fields:
            value = clean_required_text(value, required_text_fields[field_name])
        elif field_name in optional_text_fields:
            value = clean_optional_text(value)
        setattr(alert, field_name, value)

    alert.updated_at = datetime.now()
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/{alert_id}/trigger", response_model=FarmAlertResponse)
def trigger_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_alert_editor),
):
    alert = get_alert_or_404(alert_id, db)
    if alert.is_automatic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System-generated alerts cannot be manually triggered.",
        )
    alert.last_triggered = datetime.now()
    alert.updated_at = datetime.now()
    db.commit()
    db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_alert_editor),
):
    alert = get_alert_or_404(alert_id, db)
    if alert.is_automatic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System-generated alerts are audit records and cannot be deleted manually.",
        )
    db.delete(alert)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
