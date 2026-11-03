from __future__ import annotations

import calendar
import shutil
import zlib
from pathlib import Path

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.farm_time import farm_today
from app.models import (
    AlertSettings,
    Crop,
    CropPestDisease,
    FarmActivity,
    FarmAlert,
    InventoryItem,
    Livestock,
    LivestockSale,
    LoginHistory,
)


from app.services.db_concurrency import acquire_transaction_lock
from app.services.weather_service import (
    WeatherServiceError,
    get_weather_overview,
)


AUTO_SOURCE_CROP_HARVEST = "crop_harvest"
AUTO_SOURCE_CROP_PEST = "crop_pest_disease"
AUTO_SOURCE_LIVESTOCK_VACCINATION = "livestock_vaccination"
AUTO_SOURCE_LIVESTOCK_HEALTH = "livestock_health"
AUTO_SOURCE_LIVESTOCK_CHECKUP = "livestock_health_check"
AUTO_SOURCE_INVENTORY_LOW = "inventory_low_stock"
AUTO_SOURCE_WEATHER_RAIN = "weather_heavy_rain"
AUTO_SOURCE_WEATHER_TEMPERATURE = "weather_high_temperature"
AUTO_SOURCE_WEATHER_WIND = "weather_strong_wind"
AUTO_SOURCE_WEATHER_OFFICIAL = "weather_official_warning"
AUTO_SOURCE_WEATHER_THUNDERSTORM = "weather_thunderstorm"
AUTO_SOURCE_SYSTEM_FAILED_LOGIN = "system_failed_login"
AUTO_SOURCE_SYSTEM_LOW_STORAGE = "system_low_storage"
AUTO_SOURCE_ACTIVITY_TASK = "activity_task"
AUTO_SOURCE_PRODUCTION_RECEIVABLE = "production_sale_receivable"
WEATHER_SOURCE_ID = 1
SYSTEM_STORAGE_SOURCE_ID = 1
FAILED_LOGIN_WINDOW_MINUTES = 30


def _get_settings(db: Session) -> AlertSettings:
    settings = db.scalar(
        select(AlertSettings).order_by(AlertSettings.id.asc())
    )

    if settings is None:
        settings = AlertSettings()
        db.add(settings)
        db.flush()

    return settings


def _priority_from_severity(value: str | None) -> str:
    normalized = (value or "").strip().lower()

    if normalized in {"critical", "severe"}:
        return "Critical"
    if normalized == "high":
        return "High"
    if normalized in {"moderate", "medium"}:
        return "Medium"
    return "Low"


def _upsert_automatic_alert(
    db: Session,
    *,
    source_type: str,
    source_id: int,
    alert_name: str,
    category: str,
    subject: str,
    alert_type: str,
    condition: str,
    threshold: str,
    unit: str | None,
    priority: str,
    description: str,
) -> tuple[FarmAlert, tuple[str, int, str]]:
    key = (source_type, source_id, alert_type)

    alert = db.scalar(
        select(FarmAlert).where(
            FarmAlert.is_automatic == True,
            FarmAlert.source_type == source_type,
            FarmAlert.source_id == source_id,
            FarmAlert.alert_type == alert_type,
        )
    )

    now = datetime.now()

    if alert is None:
        alert = FarmAlert(
            alert_name=alert_name,
            category=category,
            subject=subject,
            alert_type=alert_type,
            condition=condition,
            threshold=threshold,
            unit=unit,
            priority=priority,
            status="Active",
            description=description,
            last_triggered=now,
            is_automatic=True,
            source_type=source_type,
            source_id=source_id,
            created_by_user_id=None,
        )
        db.add(alert)
    else:
        was_active = alert.status == "Active"

        alert.alert_name = alert_name
        alert.category = category
        alert.subject = subject
        alert.alert_type = alert_type
        alert.condition = condition
        alert.threshold = threshold
        alert.unit = unit
        alert.priority = priority
        alert.status = "Active"
        alert.description = description
        alert.is_automatic = True
        alert.source_type = source_type
        alert.source_id = source_id
        alert.updated_at = now

        if not was_active:
            alert.last_triggered = now

    return alert, key


def _disable_resolved_automatic_alerts(
    db: Session,
    active_keys: set[tuple[str, int, str]],
) -> int:
    now = datetime.now()
    resolved_count = 0

    automatic_alerts = db.scalars(
        select(FarmAlert).where(
            FarmAlert.is_automatic == True,
            FarmAlert.status == "Active",
        )
    ).all()

    for alert in automatic_alerts:
        key = (
            alert.source_type or "",
            alert.source_id or 0,
            alert.alert_type,
        )

        if key not in active_keys and alert.status == "Active":
            alert.status = "Resolved"
            alert.updated_at = now
            resolved_count += 1

    return resolved_count


def _evaluate_crop_alerts(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
    today: date,
) -> None:
    crops = db.scalars(
        select(Crop).where(Crop.is_archived == False)
    ).all()

    crops_by_id = {crop.id: crop for crop in crops}

    if settings.crop_harvest_reminder:
        advance_days = max(0, settings.crop_harvest_advance_days)

        for crop in crops:
            if crop.status in {"Harvested", "Failed"}:
                continue

            days_until_harvest = (
                crop.estimated_harvest - today
            ).days

            if crop.confirmed_ready_at is not None:
                description = (
                    f"{crop.name} in {crop.field} has been confirmed Ready for Harvest "
                    "by an authorized user."
                )
                priority = "High"
                _, key = _upsert_automatic_alert(
                    db,
                    source_type=AUTO_SOURCE_CROP_HARVEST,
                    source_id=crop.id,
                    alert_name="Harvest Ready",
                    category="Crop",
                    subject=crop.name,
                    alert_type="Harvest Reminder",
                    condition="Confirmed",
                    threshold="Ready",
                    unit=None,
                    priority=priority,
                    description=description,
                )
                active_keys.add(key)
                continue

            if days_until_harvest > advance_days:
                continue

            if days_until_harvest < 0:
                description = (
                    f"{crop.name} in {crop.field} passed its estimated "
                    f"harvest date by {abs(days_until_harvest)} day(s)."
                )
                priority = "High"
            elif days_until_harvest == 0:
                description = (
                    f"{crop.name} in {crop.field} reached its estimated "
                    "harvest date today."
                )
                priority = "High"
            else:
                description = (
                    f"{crop.name} in {crop.field} is expected to be ready "
                    f"for harvest in {days_until_harvest} day(s)."
                )
                priority = "High" if days_until_harvest <= 3 else "Medium"

            _, key = _upsert_automatic_alert(
                db,
                source_type=AUTO_SOURCE_CROP_HARVEST,
                source_id=crop.id,
                alert_name="Harvest Reminder",
                category="Crop",
                subject=crop.name,
                alert_type="Harvest Reminder",
                condition="Within",
                threshold=str(advance_days),
                unit="days",
                priority=priority,
                description=description,
            )
            active_keys.add(key)

    if settings.crop_pest_disease_alert:
        pest_records = db.scalars(
            select(CropPestDisease).where(
                CropPestDisease.status.in_(["Active", "Under Treatment"])
            )
        ).all()

        for record in pest_records:
            crop = crops_by_id.get(record.crop_id)
            if crop is None:
                continue

            pest_name = record.pest_disease_type
            severity = record.severity or "Not specified"
            affected = record.affected_area or "Not specified"

            _, key = _upsert_automatic_alert(
                db,
                source_type=AUTO_SOURCE_CROP_PEST,
                source_id=record.id,
                alert_name="Pest / Disease Alert",
                category="Crop",
                subject=crop.name,
                alert_type="Pest Detection",
                condition="Equals",
                threshold=record.status,
                unit=None,
                priority=_priority_from_severity(record.severity),
                description=(
                    f"{pest_name} is currently {record.status.lower()} for {crop.name}. "
                    f"Severity: {severity}. Affected area: {affected}."
                ),
            )
            active_keys.add(key)


def _evaluate_livestock_alerts(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
    today: date,
) -> None:
    livestock_records = db.scalars(
        select(Livestock).where(Livestock.is_archived == False)
    ).all()

    if settings.livestock_vaccination_reminder:
        advance_days = max(0, settings.livestock_vaccination_advance_days)

        for record in livestock_records:
            if record.next_vaccination is None:
                continue

            days_until = (record.next_vaccination - today).days

            if days_until > advance_days:
                continue

            if days_until < 0:
                description = (
                    f"{record.record_name} has a vaccination overdue by "
                    f"{abs(days_until)} day(s)."
                )
                priority = "High"
            elif days_until == 0:
                description = (
                    f"{record.record_name} has a vaccination due today."
                )
                priority = "High"
            else:
                description = (
                    f"{record.record_name} has a vaccination due in "
                    f"{days_until} day(s)."
                )
                priority = "High" if days_until <= 3 else "Medium"

            _, key = _upsert_automatic_alert(
                db,
                source_type=AUTO_SOURCE_LIVESTOCK_VACCINATION,
                source_id=record.id,
                alert_name="Vaccination Reminder",
                category="Livestock",
                subject=record.record_name,
                alert_type="Vaccination Reminder",
                condition="Within",
                threshold=str(advance_days),
                unit="days",
                priority=priority,
                description=description,
            )
            active_keys.add(key)

    if settings.livestock_health_check:
        frequency_days = max(1, settings.livestock_health_check_frequency)

        for record in livestock_records:
            normalized_health = (record.health_status or "").strip().lower()

            if normalized_health not in {"", "healthy", "good"}:
                sick_count = max(0, int(getattr(record, "sick_quantity", 0) or 0))
                at_risk_count = max(0, int(getattr(record, "at_risk_quantity", 0) or 0))
                treatment_count = max(
                    0,
                    int(getattr(record, "under_treatment_quantity", 0) or 0),
                )
                healthy_count = max(
                    0,
                    int(getattr(record, "healthy_quantity", 0) or 0),
                )

                if normalized_health in {"critical", "emergency"}:
                    health_priority = "Critical"
                elif sick_count > 0 or normalized_health in {"sick", "ill"}:
                    health_priority = "High"
                else:
                    health_priority = "Medium"

                count_parts = []
                if healthy_count:
                    count_parts.append(f"{healthy_count} healthy")
                if sick_count:
                    count_parts.append(f"{sick_count} sick")
                if at_risk_count:
                    count_parts.append(f"{at_risk_count} at risk")
                if treatment_count:
                    count_parts.append(f"{treatment_count} under treatment")
                count_text = ", ".join(count_parts)

                _, key = _upsert_automatic_alert(
                    db,
                    source_type=AUTO_SOURCE_LIVESTOCK_HEALTH,
                    source_id=record.id,
                    alert_name="Livestock Health Alert",
                    category="Livestock",
                    subject=record.record_name,
                    alert_type="Health Check",
                    condition="Equals",
                    threshold=record.health_status,
                    unit=None,
                    priority=health_priority,
                    description=(
                        f"{record.record_name} is currently marked as "
                        f"{record.health_status}. "
                        + (f"Batch condition: {count_text}. " if count_text else "")
                        + "Review and update the health record in Livestock Management."
                    ),
                )
                active_keys.add(key)

            days_since_check = None
            if record.last_checkup is not None:
                days_since_check = (today - record.last_checkup).days

            if record.last_checkup is None or days_since_check >= frequency_days:
                if record.last_checkup is None:
                    description = (
                        f"{record.record_name} does not have a recorded "
                        "health check yet."
                    )
                else:
                    description = (
                        f"{record.record_name} was last checked "
                        f"{days_since_check} day(s) ago."
                    )

                _, key = _upsert_automatic_alert(
                    db,
                    source_type=AUTO_SOURCE_LIVESTOCK_CHECKUP,
                    source_id=record.id,
                    alert_name="Livestock Health Check",
                    category="Livestock",
                    subject=record.record_name,
                    alert_type="Health Check",
                    condition="Every",
                    threshold=str(frequency_days),
                    unit="days",
                    priority="Medium",
                    description=description,
                )
                active_keys.add(key)


def _evaluate_inventory_alerts(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
) -> None:
    if not settings.system_low_inventory_alert:
        return

    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.is_archived == False,
            InventoryItem.quantity <= InventoryItem.reorder_level,
        )
    ).all()

    for item in items:
        quantity = float(item.quantity)
        reorder_level = float(item.reorder_level)

        priority = "Critical" if quantity <= 0 else "Medium"

        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_INVENTORY_LOW,
            source_id=item.id,
            alert_name="Low Inventory",
            category="Inventory",
            subject=item.name,
            alert_type="Low Inventory",
            condition="Below",
            threshold=str(reorder_level),
            unit=item.unit,
            priority=priority,
            description=(
                f"{item.name} has {quantity:g} {item.unit} remaining. "
                f"Reorder level is {reorder_level:g} {item.unit}."
            ),
        )
        active_keys.add(key)



def _stable_login_source_id(username: str) -> int:
    """Create a repeatable integer source id for a username.

    FarmAlert.source_id is an integer and is not a foreign key, so a stable
    CRC32 value lets automatic failed-login alerts be updated instead of
    duplicated even when the attempted username does not belong to a user.
    """

    normalized = (username or "unknown").strip().lower()
    return 1_000_000_000 + (
        zlib.crc32(normalized.encode("utf-8")) % 1_000_000_000
    )


def _evaluate_failed_login_alerts(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
) -> None:
    if not settings.system_failed_login_alert:
        return

    limit = max(1, int(settings.system_failed_login_limit))
    cutoff = datetime.now() - timedelta(
        minutes=FAILED_LOGIN_WINDOW_MINUTES
    )

    histories = db.scalars(
        select(LoginHistory)
        .where(LoginHistory.created_at >= cutoff)
        .order_by(LoginHistory.created_at.asc())
    ).all()

    # A successful login resets the recent failed-attempt streak for the same
    # username. This prevents an old alert from staying active after the user
    # successfully signs in.
    failed_by_username: dict[str, list[LoginHistory]] = {}

    for history in histories:
        username = (history.username or "").strip()
        key = username.lower() or "unknown"

        if history.success:
            failed_by_username[key] = []
            continue

        failed_by_username.setdefault(key, []).append(history)

    for username_key, failures in failed_by_username.items():
        if len(failures) < limit:
            continue

        latest = failures[-1]
        display_username = (
            latest.username.strip()
            if latest.username
            else "Unknown account"
        )

        source_id = _stable_login_source_id(username_key)
        latest_ip = latest.ip_address or "Unknown IP"

        priority = (
            "High"
            if len(failures) >= limit
            else "Medium"
        )

        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_SYSTEM_FAILED_LOGIN,
            source_id=source_id,
            alert_name="Failed Login Attempts",
            category="System",
            subject=display_username,
            alert_type="Failed Login",
            condition="At least",
            threshold=str(limit),
            unit=f"attempts/{FAILED_LOGIN_WINDOW_MINUTES} min",
            priority=priority,
            description=(
                f"{display_username} has {len(failures)} failed login "
                f"attempt(s) within the last "
                f"{FAILED_LOGIN_WINDOW_MINUTES} minutes. "
                f"Latest source IP: {latest_ip}. Review account access "
                "and confirm that the attempts are legitimate."
            ),
        )
        active_keys.add(key)


def _evaluate_low_storage_alert(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
) -> None:
    if not settings.system_low_storage_alert:
        return

    threshold = max(
        0.0,
        min(100.0, float(settings.system_storage_threshold)),
    )

    try:
        project_path = Path.cwd()
        usage = shutil.disk_usage(project_path)
    except OSError:
        # Do not break every alert if the host filesystem cannot be inspected.
        return

    if usage.total <= 0:
        return

    free_percent = (usage.free / usage.total) * 100.0

    if free_percent > threshold:
        return

    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)

    priority = (
        "High"
        if free_percent <= max(2.0, threshold / 2)
        else "Medium"
    )

    _, key = _upsert_automatic_alert(
        db,
        source_type=AUTO_SOURCE_SYSTEM_LOW_STORAGE,
        source_id=SYSTEM_STORAGE_SOURCE_ID,
        alert_name="Low Storage",
        category="System",
        subject="Backend Server Storage",
        alert_type="Low Storage",
        condition="Below",
        threshold=f"{threshold:g}",
        unit="% free",
        priority=priority,
        description=(
            f"The server running Joross Farm has approximately "
            f"{free_percent:.1f}% free storage "
            f"({free_gb:.1f} GB free of {total_gb:.1f} GB). "
            f"The configured warning threshold is {threshold:g}% free."
        ),
    )
    active_keys.add(key)


def _evaluate_system_alerts(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
) -> None:
    _evaluate_failed_login_alerts(
        db,
        settings,
        active_keys,
    )

    _evaluate_low_storage_alert(
        db,
        settings,
        active_keys,
    )


def _activity_priority(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "critical":
        return "Critical"
    if normalized == "high":
        return "High"
    if normalized == "low":
        return "Low"
    return "Medium"


def _activity_alert_category(activity: FarmActivity) -> str:
    source_module = str(activity.source_module or "").strip().lower()
    if source_module == "crop":
        return "Crop"
    if source_module == "livestock":
        return "Livestock"
    if source_module == "inventory":
        return "Inventory"
    if source_module in {"production & sales", "production sales", "production-sales"}:
        return "Production & Sales"
    return "System"


def _activity_alert_enabled(activity: FarmActivity, settings: AlertSettings) -> bool:
    source_type = str(activity.source_type or "").strip().lower()

    if source_type == "crop_growth_check":
        return bool(settings.crop_growth_check)
    if source_type == "crop_harvest":
        return bool(settings.crop_harvest_reminder)
    if source_type == "crop_pest_followup":
        return bool(settings.crop_pest_disease_alert)
    if source_type == "livestock_feeding":
        return bool(settings.livestock_feeding_reminder)
    if source_type == "livestock_vaccination":
        return bool(settings.livestock_vaccination_reminder)
    if source_type == "livestock_health_check":
        return bool(settings.livestock_health_check)
    if source_type == "inventory_restock":
        return bool(settings.system_low_inventory_alert)

    # Watering and reproduction follow-ups are backed by real source records,
    # even though the current settings table does not expose a dedicated switch.
    return True


def _evaluate_activity_alerts(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
) -> None:
    """Create alerts only for farm tasks that are actually overdue.

    Normal upcoming work remains on the Dashboard/Tasks workflow. This keeps
    Farm Alerts focused on exceptions that need attention instead of creating
    a second copy of every routine task.
    """
    now = datetime.now().replace(microsecond=0)

    activities = db.scalars(
        select(FarmActivity).where(
            FarmActivity.is_archived == False
        )
    ).all()

    for activity in activities:
        if activity.status in {"Completed", "Cancelled", "Resolved", "Voided"}:
            continue

        if not _activity_alert_enabled(activity, settings):
            continue

        due_at = datetime.combine(
            activity.activity_date,
            activity.start_time,
        )

        # Due-soon tasks stay on Dashboard/Tasks and do not become alerts.
        if due_at >= now:
            continue

        overdue = now - due_at
        overdue_hours = max(1, int(overdue.total_seconds() // 3600))
        overdue_days = overdue_hours // 24

        if overdue_days >= 7:
            priority = "Critical"
        elif overdue_hours >= 24:
            priority = "High"
        else:
            priority = max(
                [_activity_priority(activity.priority), "Medium"],
                key=lambda value: {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}[value],
            )

        if overdue_hours >= 24:
            timing_text = f"overdue by {max(1, overdue_days)} day(s)"
        else:
            timing_text = f"overdue by {overdue_hours} hour(s)"

        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_ACTIVITY_TASK,
            source_id=activity.id,
            alert_name="Overdue Task",
            category=_activity_alert_category(activity),
            subject=activity.name,
            alert_type="Task Reminder",
            condition="Equals",
            threshold="Overdue",
            unit=None,
            priority=priority,
            description=(
                f"{activity.name} is {timing_text}. "
                f"Assigned to {activity.assigned_to}. "
                "Open the source workflow and complete or reschedule the task."
            ),
        )
        active_keys.add(key)


def _evaluate_production_sales_alerts(
    db: Session,
    active_keys: set[tuple[str, int, str]],
    today: date,
) -> None:
    """Track measurable financial exceptions from Production & Sales.

    A partial/unpaid sale creates one outstanding-receivable alert. The same
    alert automatically resolves when the balance reaches zero or the sale is
    voided, so recording a later payment never creates duplicate alerts.
    """
    sales = db.scalars(
        select(LivestockSale).where(
            LivestockSale.is_voided == False,
            LivestockSale.balance_due > 0,
        )
    ).all()

    for sale in sales:
        balance = float(sale.balance_due or 0)
        if balance <= 0:
            continue

        age_days = max(0, (today - sale.sale_date).days)
        if age_days >= 30:
            priority = "Critical"
        elif age_days >= 7:
            priority = "High"
        else:
            priority = "Medium"

        buyer = (sale.buyer_name or "Customer").strip()
        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_PRODUCTION_RECEIVABLE,
            source_id=sale.id,
            alert_name="Outstanding Receivable",
            category="Production & Sales",
            subject=f"{sale.sale_code} — {buyer}",
            alert_type="Outstanding Receivable",
            condition="Above",
            threshold="0",
            unit="PHP",
            priority=priority,
            description=(
                f"{sale.sale_code} has an outstanding balance of "
                f"₱{balance:,.2f}. Payment status: {sale.payment_status}. "
                f"The sale was recorded {age_days} day(s) ago. "
                "Record a payment in Production & Sales to reduce or clear this alert."
            ),
        )
        active_keys.add(key)


def _normalize_legacy_history_statuses(db: Session) -> None:
    """Convert older Disabled records into the clearer history statuses."""
    now = datetime.now()

    automatic_disabled = db.scalars(
        select(FarmAlert).where(
            FarmAlert.is_automatic == True,
            FarmAlert.status == "Disabled",
        )
    ).all()

    for alert in automatic_disabled:
        alert.status = "Resolved"
        alert.updated_at = now

    completed_one_time = db.scalars(
        select(FarmAlert).where(
            FarmAlert.is_automatic == False,
            FarmAlert.condition == "Scheduled",
            FarmAlert.status == "Disabled",
            FarmAlert.last_triggered.is_not(None),
        )
    ).all()

    for alert in completed_one_time:
        repeat = (alert.unit or "None").strip().lower()
        if repeat not in {"daily", "weekly", "monthly"}:
            alert.status = "Completed"
            alert.updated_at = now


def _preserve_existing_weather_alerts(
    db: Session,
    active_keys: set[tuple[str, int, str]],
) -> None:
    """Keep current weather alerts unchanged if OpenWeather is unavailable."""

    source_types = {
        AUTO_SOURCE_WEATHER_RAIN,
        AUTO_SOURCE_WEATHER_TEMPERATURE,
        AUTO_SOURCE_WEATHER_WIND,
        AUTO_SOURCE_WEATHER_THUNDERSTORM,
        AUTO_SOURCE_WEATHER_OFFICIAL,
    }

    weather_alerts = db.scalars(
        select(FarmAlert).where(
            FarmAlert.is_automatic == True,
            FarmAlert.source_type.in_(source_types),
            FarmAlert.status == "Active",
        )
    ).all()

    for alert in weather_alerts:
        active_keys.add(
            (
                alert.source_type or "",
                alert.source_id or WEATHER_SOURCE_ID,
                alert.alert_type,
            )
        )


def _evaluate_weather_alerts(
    db: Session,
    settings: AlertSettings,
    active_keys: set[tuple[str, int, str]],
) -> None:
    weather = get_weather_overview()
    if weather.get("data_status") == "Stale":
        raise WeatherServiceError("Latest weather fetch is unavailable; preserve existing warnings.")
    if weather.get("official_alerts_status") == "Unavailable":
        for alert in db.scalars(select(FarmAlert).where(FarmAlert.source_type == AUTO_SOURCE_WEATHER_OFFICIAL, FarmAlert.is_automatic == True)).all():
            active_keys.add((alert.source_type, alert.source_id or WEATHER_SOURCE_ID, alert.alert_type))
    for warning in weather.get("official_alerts", []):
        if warning["ends_at"] <= datetime.now(warning["ends_at"].tzinfo):
            continue
        _, key = _upsert_automatic_alert(db, source_type=AUTO_SOURCE_WEATHER_OFFICIAL,
            source_id=int(warning["id"][:7], 16), alert_name=str(warning["event"])[:150],
            category="Weather", subject=weather["location"], alert_type="Official Warning",
            condition="Issued", threshold=warning["id"], unit=None, priority="High",
            description=f"{warning['source']} via OpenWeather · {warning['location']} · Valid {warning['starts_at'].isoformat()} to {warning['ends_at'].isoformat()}. {warning['description']}")
        active_keys.add(key)
    location = weather["location"]
    next_24 = weather["next_24_hours"]
    current = weather["current"]

    rainfall = float(next_24["rain_total_mm"])
    max_temperature = max(
        float(next_24["max_temperature_c"]),
        float(current["temperature_c"]),
    )
    max_wind = max(
        float(next_24["max_wind_speed_kph"]),
        float(current["wind_speed_kph"]),
        float(current.get("wind_gust_kph") or 0),
        float(next_24.get("max_wind_gust_kph") or 0),
    )
    thunderstorm_expected = bool(
        next_24["thunderstorm_expected"]
        or 200 <= int(current["weather_code"]) <= 232
    )

    if (
        settings.weather_heavy_rain_alert
        and rainfall >= float(settings.weather_rainfall_threshold)
    ):
        threshold = float(settings.weather_rainfall_threshold)

        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_WEATHER_RAIN,
            source_id=WEATHER_SOURCE_ID,
            alert_name="Heavy Rain Alert",
            category="Weather",
            subject=location,
            alert_type="Heavy Rain",
            condition="Above",
            threshold=f"{threshold:g}",
            unit="mm/24h",
            priority="High",
            description=(
                f"OpenWeather forecasts approximately {rainfall:g} mm of "
                f"rain in the next 24 hours for {location}. The configured "
                f"heavy-rain threshold is {threshold:g} mm/24h."
            ),
        )
        active_keys.add(key)

    if (
        settings.weather_high_temperature_alert
        and max_temperature >= float(settings.weather_temperature_threshold)
    ):
        threshold = float(settings.weather_temperature_threshold)
        priority = (
            "High"
            if max_temperature >= threshold + 3
            else "Medium"
        )

        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_WEATHER_TEMPERATURE,
            source_id=WEATHER_SOURCE_ID,
            alert_name="High Temperature",
            category="Weather",
            subject=location,
            alert_type="High Temperature",
            condition="Above",
            threshold=f"{threshold:g}",
            unit="°C",
            priority=priority,
            description=(
                f"Temperature may reach {max_temperature:g} °C in the next "
                f"24 hours for {location}. The configured threshold is "
                f"{threshold:g} °C."
            ),
        )
        active_keys.add(key)

    if (
        settings.weather_strong_wind_alert
        and max_wind >= float(settings.weather_wind_speed_threshold)
    ):
        threshold = float(settings.weather_wind_speed_threshold)
        priority = (
            "High"
            if max_wind >= threshold + 10
            else "Medium"
        )

        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_WEATHER_WIND,
            source_id=WEATHER_SOURCE_ID,
            alert_name="Strong Wind Alert",
            category="Weather",
            subject=location,
            alert_type="Strong Wind",
            condition="Above",
            threshold=f"{threshold:g}",
            unit="km/h",
            priority=priority,
            description=(
                f"Wind speed or gusts may reach {max_wind:g} km/h in the next 24 "
                f"hours for {location}. The configured threshold is "
                f"{threshold:g} km/h."
            ),
        )
        active_keys.add(key)

    if settings.weather_thunderstorm_alert and thunderstorm_expected:
        _, key = _upsert_automatic_alert(
            db,
            source_type=AUTO_SOURCE_WEATHER_THUNDERSTORM,
            source_id=WEATHER_SOURCE_ID,
            alert_name="Thunderstorm Alert",
            category="Weather",
            subject=location,
            alert_type="Thunderstorm",
            condition="Equals",
            threshold="Expected",
            unit=None,
            priority="High",
            description=(
                f"Thunderstorm conditions are present or forecast within "
                f"the next 24 hours for {location}."
            ),
        )
        active_keys.add(key)



def _parse_manual_schedule(value: str | None) -> datetime | None:
    """Read the local date/time stored by the manual alert form."""
    raw = (value or "").strip()
    if not raw:
        return None

    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _latest_daily_occurrence(base: datetime, now: datetime) -> datetime | None:
    occurrence = now.replace(
        hour=base.hour,
        minute=base.minute,
        second=base.second,
        microsecond=0,
    )
    if occurrence > now:
        occurrence -= timedelta(days=1)
    return occurrence if occurrence >= base else None


def _latest_weekly_occurrence(base: datetime, now: datetime) -> datetime | None:
    days_back = (now.weekday() - base.weekday()) % 7
    occurrence = (now - timedelta(days=days_back)).replace(
        hour=base.hour,
        minute=base.minute,
        second=base.second,
        microsecond=0,
    )
    if occurrence > now:
        occurrence -= timedelta(days=7)
    return occurrence if occurrence >= base else None


def _monthly_occurrence(year: int, month: int, base: datetime) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    day = min(base.day, last_day)
    return datetime(
        year,
        month,
        day,
        base.hour,
        base.minute,
        base.second,
    )


def _latest_monthly_occurrence(base: datetime, now: datetime) -> datetime | None:
    occurrence = _monthly_occurrence(now.year, now.month, base)

    if occurrence > now:
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1
        occurrence = _monthly_occurrence(year, month, base)

    return occurrence if occurrence >= base else None


def _latest_scheduled_occurrence(
    base: datetime,
    repeat: str,
    now: datetime,
) -> datetime | None:
    if now < base:
        return None

    normalized = (repeat or "None").strip().lower()
    if normalized == "daily":
        return _latest_daily_occurrence(base, now)
    if normalized == "weekly":
        return _latest_weekly_occurrence(base, now)
    if normalized == "monthly":
        return _latest_monthly_occurrence(base, now)

    return base


def _evaluate_manual_scheduled_alerts(db: Session) -> None:
    """Trigger active manual reminders when their scheduled time is due."""
    now = datetime.now().replace(microsecond=0)

    alerts = db.scalars(
        select(FarmAlert).where(
            FarmAlert.is_automatic == False,
            FarmAlert.status == "Active",
            FarmAlert.condition == "Scheduled",
        )
    ).all()

    for alert in alerts:
        scheduled_at = _parse_manual_schedule(alert.threshold)
        if scheduled_at is None:
            continue

        repeat = (alert.unit or "None").strip()
        occurrence = _latest_scheduled_occurrence(
            scheduled_at,
            repeat,
            now,
        )
        if occurrence is None:
            continue

        # Already triggered for this exact occurrence.
        if alert.last_triggered is not None and alert.last_triggered >= occurrence:
            continue

        alert.last_triggered = now
        alert.updated_at = now

        # A one-time reminder is finished after it fires once and moves to history.
        if repeat.lower() not in {"daily", "weekly", "monthly"}:
            alert.status = "Completed"


def evaluate_livestock_alerts_only(
    db: Session,
    *,
    commit: bool = True,
) -> list[FarmAlert]:
    """Synchronize only livestock automatic alerts without weather/system work.

    This is used by transactional livestock workflows so a completed sale or
    restored livestock record updates its directly related alerts immediately
    without paying the cost of a full farm/weather alert evaluation.
    """
    acquire_transaction_lock(db, "automation:alerts")
    settings = _get_settings(db)
    active_keys: set[tuple[str, int, str]] = set()
    _evaluate_livestock_alerts(db, settings, active_keys, farm_today())

    livestock_sources = {
        AUTO_SOURCE_LIVESTOCK_VACCINATION,
        AUTO_SOURCE_LIVESTOCK_HEALTH,
        AUTO_SOURCE_LIVESTOCK_CHECKUP,
    }
    now = datetime.now()
    alerts = list(
        db.scalars(
            select(FarmAlert).where(
                FarmAlert.is_automatic == True,
                FarmAlert.source_type.in_(livestock_sources),
            )
        ).all()
    )
    for alert in alerts:
        key = (alert.source_type, int(alert.source_id or 0), alert.alert_type)
        if key not in active_keys and alert.status not in {"Resolved", "Completed"}:
            alert.status = "Resolved"
            alert.updated_at = now

    if commit:
        db.commit()
    else:
        db.flush()

    return alerts

def evaluate_production_sales_alerts_only(
    db: Session,
    *,
    commit: bool = True,
) -> list[FarmAlert]:
    """Synchronize Production & Sales receivable alerts immediately."""
    acquire_transaction_lock(db, "automation:alerts")
    active_keys: set[tuple[str, int, str]] = set()
    _evaluate_production_sales_alerts(db, active_keys, farm_today())

    now = datetime.now()
    alerts = list(
        db.scalars(
            select(FarmAlert).where(
                FarmAlert.is_automatic == True,
                FarmAlert.source_type == AUTO_SOURCE_PRODUCTION_RECEIVABLE,
            )
        ).all()
    )
    for alert in alerts:
        key = (alert.source_type, int(alert.source_id or 0), alert.alert_type)
        if key not in active_keys and alert.status not in {"Resolved", "Completed"}:
            alert.status = "Resolved"
            alert.updated_at = now

    if commit:
        db.commit()
    else:
        db.flush()

    return alerts


def evaluate_automatic_alerts(
    db: Session,
    *,
    return_metrics: bool = False,
) -> list[FarmAlert] | dict[str, int]:
    """Synchronize automatic alerts with current farm records.

    This engine evaluates automatic farm rules and due manual schedules
    backed by crop, livestock, inventory, authentication history, server
    storage, and OpenWeather data. If OpenWeather is temporarily unavailable, existing
    weather alerts are preserved instead of incorrectly being resolved.
    """
    acquire_transaction_lock(db, "automation:alerts")

    settings = _get_settings(db)
    today = farm_today()
    active_keys: set[tuple[str, int, str]] = set()

    _normalize_legacy_history_statuses(db)
    _evaluate_crop_alerts(db, settings, active_keys, today)
    _evaluate_livestock_alerts(db, settings, active_keys, today)
    _evaluate_inventory_alerts(db, settings, active_keys)
    _evaluate_activity_alerts(db, settings, active_keys)
    _evaluate_production_sales_alerts(db, active_keys, today)
    _evaluate_system_alerts(db, settings, active_keys)
    _evaluate_manual_scheduled_alerts(db)

    try:
        _evaluate_weather_alerts(db, settings, active_keys)
    except WeatherServiceError:
        _preserve_existing_weather_alerts(db, active_keys)

    resolved_count = _disable_resolved_automatic_alerts(db, active_keys)
    created_count = sum(isinstance(item, FarmAlert) for item in db.new)

    db.commit()

    alerts = list(
        db.scalars(
            select(FarmAlert)
            .where(FarmAlert.is_automatic == True)
            .order_by(FarmAlert.id.desc())
        ).all()
    )

    if return_metrics:
        return {
            "created": created_count,
            "resolved": resolved_count,
            "active": sum(alert.status == "Active" for alert in alerts),
        }

    return alerts
