from __future__ import annotations

from collections import defaultdict
from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
import re

from sqlalchemy import func, select

from app.core.farm_time import farm_now_naive, farm_today
from sqlalchemy.orm import Session

from app.services.db_concurrency import acquire_transaction_lock, try_acquire_transaction_lock
from app.services.code_counter_service import next_record_code
from app.services.task_assignment import (
    assignment_is_protected,
    recalculate_task_reassignment,
    record_assignment_change,
)
from app.services.work_schedule_service import apply_schedule_aware_assignment
from app.services.leave_coverage_service import (
    apply_leave_coverage_to_task,
    reconcile_expired_leave_coverage,
)
from app.services.care_task_overlap import resolve_pending_protocol_overlaps

from app.models.activity import FarmActivity
from app.models.crop import (
    Crop,
    CropGrowthRecord,
    CropPestDisease,
)
from app.models.inventory import (
    InventoryItem,
    InventoryStockRecord,
)
from app.models.workforce import Employee, TaskSubmission
from app.models.livestock import (
    Livestock,
    LivestockFeedingRecord,
    LivestockReproductionRecord,
)


HARVEST_ADVANCE_DAYS = 7
GROWTH_CHECK_FREQUENCY_DAYS = 7
VACCINATION_ADVANCE_DAYS = 7
HEALTH_CHECK_FREQUENCY_DAYS = 14
REPRODUCTION_ADVANCE_DAYS = 7


# Only these task families are fully owned by this evaluator and may be
# reconciled against the active key set produced during a scheduler pass.
#
# Important exclusions:
# - care_template_step tasks are created by the workforce care-template
#   workflow and must remain actionable until an employee/manager workflow
#   closes them (or a future explicit protocol-reconciliation rule does so).
# - livestock_feeding tasks have their own occurrence-aware reconciliation in
#   _livestock_tasks(), including feeding-record checks and overdue behavior.
EVALUATOR_CLEANUP_SOURCE_TYPES = frozenset(
    {
        "crop_watering",
        "crop_harvest",
        "crop_pest_followup",
        "livestock_vaccination",
        "livestock_health_check",
        "livestock_reproduction",
        "inventory_restock",
    }
)


def _generate_activity_code(db: Session) -> str:
    return next_record_code(
        db,
        namespace="activity",
        prefix="ACT",
        seed_model=FarmActivity,
        code_column=FarmActivity.activity_code,
    )


def _parse_first_feed_time(value: str | None) -> time:
    if not value:
        return time(6, 0)

    match = re.search(
        r"(?P<hour>\d{1,2})"
        r"(?::(?P<minute>\d{2}))?"
        r"\s*(?P<period>AM|PM)?",
        str(value),
        flags=re.IGNORECASE,
    )

    if not match:
        return time(6, 0)

    hour = int(match.group("hour"))
    minute = int(
        match.group("minute") or 0
    )
    period = (
        match.group("period") or ""
    ).upper()

    if period == "PM" and hour < 12:
        hour += 12
    elif period == "AM" and hour == 12:
        hour = 0

    if not 0 <= hour <= 23:
        return time(6, 0)

    if not 0 <= minute <= 59:
        minute = 0

    return time(hour, minute)


def _named_feeding_slots(value: str | None) -> list[str]:
    text_value = (value or "").strip().lower()
    slot_terms = [
        (("morning",), "Morning"),
        (("midday", "noon"), "Midday"),
        (("afternoon",), "Afternoon"),
        (("evening", "night"), "Evening"),
    ]

    slots: list[str] = []
    for terms, label in slot_terms:
        if any(
            re.search(rf"\b{re.escape(term)}\b", text_value)
            for term in terms
        ):
            slots.append(label)

    return slots


def _parse_feedings_per_day(value: str | None) -> int:
    text_value = (value or "").strip().lower()

    for separator in ("×", "x"):
        if separator in text_value:
            left = text_value.split(separator, 1)[0].strip()
            try:
                return max(1, min(int(left), 12))
            except ValueError:
                pass

    if "twice" in text_value:
        return 2
    if "three" in text_value or "thrice" in text_value:
        return 3
    if "four" in text_value:
        return 4

    named_slots = _named_feeding_slots(value)
    if named_slots:
        return max(1, min(len(named_slots), 12))

    return 1


def _feeding_slots(
    count: int,
    value: str | None = None,
) -> list[str]:
    named_slots = _named_feeding_slots(value)
    if len(named_slots) == count:
        return named_slots

    if count == 1:
        return ["Daily Feeding"]
    if count == 2:
        return ["Morning", "Afternoon"]
    if count == 3:
        return ["Morning", "Midday", "Evening"]

    return [
        f"Feeding {index + 1}"
        for index in range(count)
    ]


def _extract_explicit_feed_times(value: str | None) -> list[time]:
    if not value:
        return []

    text_value = str(value)
    parsed: list[tuple[int, time]] = []
    occupied_spans: list[tuple[int, int]] = []

    for match in re.finditer(
        r"(?P<hour>\d{1,2})"
        r"(?::(?P<minute>\d{2}))?"
        r"\s*(?P<period>AM|PM)",
        text_value,
        flags=re.IGNORECASE,
    ):
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        period = match.group("period").upper()

        if period == "PM" and hour < 12:
            hour += 12
        elif period == "AM" and hour == 12:
            hour = 0

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            parsed.append((match.start(), time(hour, minute)))
            occupied_spans.append(match.span())

    for match in re.finditer(
        r"(?<!\d)(?P<hour>\d{1,2}):(?P<minute>\d{2})(?!\d)",
        text_value,
    ):
        if any(
            start <= match.start() < end
            for start, end in occupied_spans
        ):
            continue

        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            parsed.append((match.start(), time(hour, minute)))

    return [
        parsed_time
        for _, parsed_time in sorted(parsed, key=lambda item: item[0])
    ]


def _feeding_occurrences(value: str | None) -> list[tuple[int, str, time]]:
    count = _parse_feedings_per_day(value)
    slots = _feeding_slots(count, value)
    explicit_times = _extract_explicit_feed_times(value)

    default_slot_times = {
        "Daily Feeding": time(6, 0),
        "Morning": time(6, 0),
        "Midday": time(12, 0),
        "Afternoon": time(15, 0),
        "Evening": time(18, 0),
    }

    if all(slot in default_slot_times for slot in slots):
        fallback_times = [
            default_slot_times[slot]
            for slot in slots
        ]
    else:
        start_minutes = 6 * 60
        end_minutes = 18 * 60
        step = (end_minutes - start_minutes) / max(count - 1, 1)
        fallback_times = []
        for index in range(count):
            total_minutes = round(start_minutes + (step * index))
            fallback_times.append(
                time(
                    min(total_minutes // 60, 23),
                    total_minutes % 60,
                )
            )

    occurrence_times = list(fallback_times)
    for index, explicit_time in enumerate(explicit_times[:count]):
        occurrence_times[index] = explicit_time

    return [
        (index + 1, slot, occurrence_times[index])
        for index, slot in enumerate(slots)
    ]


def _feeding_source_key(
    livestock_id: int,
    activity_date: date,
    slot: str,
) -> str:
    slot_key = re.sub(
        r"[^a-z0-9]+",
        "-",
        slot.strip().lower(),
    ).strip("-")
    return (
        f"livestock:feeding:{livestock_id}:"
        f"{activity_date.isoformat()}:{slot_key}"
    )


def _upsert_automatic_task(
    db: Session,
    *,
    source_key: str,
    source_module: str,
    source_type: str,
    source_record_id: int,
    source_detail_id: int | None,
    source_code: str | None,
    source_path: str,
    name: str,
    category: str,
    related_to: str,
    location: str,
    description: str,
    activity_date: date,
    start_time: time,
    assigned_to: str,
    priority: str,
) -> tuple[FarmActivity, str]:
    task = db.scalar(
        select(FarmActivity).where(
            FarmActivity.source_key == source_key,
        )
    )

    now = farm_now_naive()

    # The source record supplies the default only for a new occurrence. Existing
    # task assignments belong to the task workflow and may have been explicitly
    # overridden/reassigned by a manager.
    default_employee_id = None
    default_employee = None
    source_record = None
    if source_module == "Livestock":
        source_record = db.get(Livestock, source_record_id)
    elif source_module == "Crop":
        source_record = db.get(Crop, source_record_id)
    if source_record is not None:
        default_employee_id = getattr(source_record, "assigned_employee_id", None)
        if default_employee_id:
            employee = db.get(Employee, default_employee_id)
            if employee is not None and not employee.is_archived:
                default_employee = employee
            else:
                default_employee_id = None

    # New automatic crop/livestock work is reviewable by default.  Inventory
    # reminders are not employee-performed work and continue to use Resolve.
    requires_review = source_module in {"Crop", "Livestock"}

    if task is None:
        task = FarmActivity(
            activity_code=_generate_activity_code(db),
            name=name,
            category=category,
            related_to=related_to,
            location=location,
            description=description,
            activity_date=activity_date,
            start_time=start_time,
            end_time=None,
            duration=None,
            assigned_by="System",
            assigned_to=(default_employee.full_name if default_employee else assigned_to),
            assigned_employee_id=default_employee_id,
            default_employee_id=default_employee_id,
            assignment_source="automatic_default",
            requires_review=requires_review,
            status="Pending",
            priority=priority,
            is_automatic=True,
            source_module=source_module,
            source_type=source_type,
            source_record_id=source_record_id,
            source_detail_id=source_detail_id,
            source_code=source_code,
            source_path=source_path,
            source_key=source_key,
            completed_at=None,
            is_archived=False,
            created_by_user_id=None,
        )
        db.add(task)
        db.flush()
        if default_employee_id is not None:
            record_assignment_change(
                db,
                task,
                old_employee_id=None,
                new_employee_id=default_employee_id,
                assignment_source="automatic_default",
                actor_user_id=None,
                actor_name="System",
                reason=f"Initial automatic assignment from the {source_module.lower()} record default employee.",
            )
        apply_leave_coverage_to_task(
            db,
            task,
            default_employee_id=default_employee_id,
        )
        if task.assignment_source != "Leave Coverage":
            apply_schedule_aware_assignment(db, task, default_employee_id=default_employee_id)
        recalculate_task_reassignment(db, task)
        return task, "created"

    # A manager may schedule the native occurrence from Calendar/Task Management.
    # Its source key is shared, while its explicit plan and assignment stay intact.
    if not task.is_automatic:
        return task, "unchanged"

    if (source_type in {"crop_growth_check", "livestock_growth_check"}
            and task.status == "Resolved" and task.activity_date >= farm_today()
            and task.problem_report == "Monitoring schedule changed or monitoring stopped."
            and not db.scalar(select(TaskSubmission.id).where(TaskSubmission.activity_id == task.id).limit(1))):
        task.status = "Pending"
        task.problem_report = None

    # Historical/review records and archived tasks must not be mutated by the
    # periodic generator, especially not silently reassigned.
    if assignment_is_protected(task):
        return task, "unchanged"
    from app.services.farm_event_service import task_schedule_locked
    if task_schedule_locked(db, task.id):
        return task, "unchanged"

    if (source_type in {"crop_growth_check", "livestock_growth_check"}
            and task.status == "Pending" and task.activity_date >= farm_today()
            and task.assignment_source in {"automatic_default", "Rest-Day Coverage"}
            and task.default_employee_id != default_employee_id):
        old_employee_id = task.assigned_employee_id
        task.default_employee_id = default_employee_id
        task.assigned_employee_id = default_employee_id
        task.assigned_to = default_employee.full_name if default_employee else "Unassigned"
        task.assignment_source = "automatic_default"
        record_assignment_change(db, task, old_employee_id=old_employee_id, new_employee_id=default_employee_id,
                                 assignment_source="automatic_default", actor_user_id=None, actor_name="System",
                                 reason="Future monitoring follows the resource's reassigned employee.")

    task.name = name
    task.category = category
    task.related_to = related_to
    task.location = location
    task.description = description
    task.activity_date = activity_date
    task.start_time = start_time
    # Intentionally preserve assigned_to, assigned_employee_id, and
    # assignment_source for existing occurrences.
    # Preserve the review state of an existing occurrence. The scheduler owns
    # generation metadata, not a manager/reviewer workflow decision.
    task.priority = priority
    task.source_module = source_module
    task.source_type = source_type
    task.source_record_id = source_record_id
    task.source_detail_id = source_detail_id
    task.source_code = source_code
    task.source_path = source_path
    task.source_key = source_key
    task.is_automatic = True
    if task.default_employee_id is None and task.assignment_source == "automatic_default":
        task.default_employee_id = default_employee_id
    if task.assignment_source in {"automatic_default", "Rest-Day Coverage"}:
        apply_leave_coverage_to_task(
            db,
            task,
            default_employee_id=task.default_employee_id or default_employee_id,
        )
        if task.assignment_source != "Leave Coverage":
            apply_schedule_aware_assignment(
                db, task, default_employee_id=task.default_employee_id or default_employee_id
            )
    recalculate_task_reassignment(db, task)
    if db.is_modified(task, include_collections=False):
        task.updated_at = now
    # Preserve the existing upsert result contract for synchronized occurrences,
    # while an identical refresh performs no UPDATE and holds no write row lock.
    return task, "updated"



WATERING_PERIOD_TIMES = {
    "Morning": time(6, 0),
    "Afternoon": time(15, 0),
    "Evening": time(18, 0),
}

WEEKDAY_INDEX = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def _watering_schedule_config(value: str | None) -> dict | None:
    text_value = str(value or "").strip()
    if not text_value or text_value.lower() in {"not specified", "none"}:
        return None

    segments = [segment.strip() for segment in text_value.split("|") if segment.strip()]
    frequency = segments[0] if segments else ""
    days: list[str] = []
    periods: list[str] = []

    for segment in segments[1:]:
        lower = segment.lower()
        if lower.startswith("days:"):
            days = [
                item.strip()
                for item in segment.split(":", 1)[1].split(",")
                if item.strip() in WEEKDAY_INDEX
            ]
        elif lower.startswith("periods:"):
            periods = [
                item.strip()
                for item in segment.split(":", 1)[1].split(",")
                if item.strip() in WATERING_PERIOD_TIMES
            ]

    allowed = {
        "Daily",
        "Twice Daily",
        "Every 2 Days",
        "3 Times per Week",
        "Weekly",
        "As Needed",
        "Rain-Fed",
        "Automated/Continuous",
    }

    if frequency in allowed:
        if frequency in {"As Needed", "Rain-Fed", "Automated/Continuous"}:
            return {"frequency": frequency, "days": [], "periods": []}
        if not periods:
            periods = ["Morning", "Afternoon"] if frequency == "Twice Daily" else ["Morning"]
        return {"frequency": frequency, "days": days, "periods": periods}

    # Compatibility with a few common old free-text values. Unknown legacy
    # text intentionally produces no automatic task until the crop is edited
    # into the standardized schedule controls.
    normalized = " ".join(text_value.lower().replace("-", " ").split())
    if normalized in {"every morning", "daily morning", "morning daily"}:
        return {"frequency": "Daily", "days": [], "periods": ["Morning"]}
    if "morning" in normalized and "afternoon" in normalized:
        return {
            "frequency": "Twice Daily",
            "days": [],
            "periods": ["Morning", "Afternoon"],
        }
    if normalized in {"daily", "every day", "everyday"}:
        return {"frequency": "Daily", "days": [], "periods": ["Morning"]}
    return None


def _watering_occurrences(crop: Crop, today: date) -> list[tuple[date, str, time]]:
    config = _watering_schedule_config(crop.watering_schedule)
    if not config:
        return []

    frequency = config["frequency"]
    if frequency in {"As Needed", "Rain-Fed", "Automated/Continuous"}:
        return []

    periods = config["periods"] or ["Morning"]
    selected_days = {WEEKDAY_INDEX[day] for day in config["days"] if day in WEEKDAY_INDEX}
    occurrences: list[tuple[date, str, time]] = []

    for offset in range(0, 8):
        activity_date = today + timedelta(days=offset)
        if activity_date < crop.planting_date:
            continue

        include_date = False
        if frequency in {"Daily", "Twice Daily"}:
            include_date = True
        elif frequency == "Every 2 Days":
            elapsed = (activity_date - crop.planting_date).days
            include_date = elapsed >= 0 and elapsed % 2 == 0
        elif frequency == "3 Times per Week":
            include_date = activity_date.weekday() in selected_days
        elif frequency == "Weekly":
            include_date = activity_date.weekday() in selected_days

        if not include_date:
            continue

        for period in periods:
            period_time = WATERING_PERIOD_TIMES.get(period, time(6, 0))
            occurrences.append((activity_date, period, period_time))

    return occurrences


def _watering_source_key(crop_id: int, activity_date: date, period: str) -> str:
    period_key = re.sub(r"[^a-z0-9]+", "-", period.lower()).strip("-")
    return f"crop:watering:{crop_id}:{activity_date.isoformat()}:{period_key}"


def _sync_crop_watering_tasks(
    db: Session,
    *,
    crop: Crop,
    crop_status: str,
    today: date,
    active_keys: set[str],
    counters: dict[str, int],
) -> None:
    now = farm_now_naive()
    existing = db.scalars(
        select(FarmActivity).where(
            FarmActivity.is_automatic == True,
            FarmActivity.source_type == "crop_watering",
            FarmActivity.source_record_id == crop.id,
            FarmActivity.status.in_(["Pending", "In Progress"]),
        )
    ).all()

    if crop_status in {"Harvested", "Failed"} or crop.is_archived:
        # Final harvest/closure only voids future work that has not started.
        # In-progress work is deliberately preserved for an authorized manager
        # to resolve, matching the crop lifecycle protection rules.
        for task in existing:
            if task.status != "Pending":
                if task.source_key:
                    active_keys.add(task.source_key)
                continue
            task.status = "Voided"
            task.completed_at = None
            task.problem_report = "Crop cycle fully harvested." if crop_status == "Harvested" else task.problem_report
            task.updated_at = now
            counters["updated"] += 1
        return

    generated_keys: set[str] = set()
    for activity_date, period, start_time in _watering_occurrences(crop, today):
        key = _watering_source_key(crop.id, activity_date, period)
        generated_keys.add(key)
        _, result = _upsert_automatic_task(
            db,
            source_key=key,
            source_module="Crop",
            source_type="crop_watering",
            source_record_id=crop.id,
            source_detail_id=None,
            source_code=crop.crop_code,
            source_path="/crops",
            name=f"Water {crop.name} — {period}",
            category="Crop Watering",
            related_to=f"{crop.name} — {crop.field}",
            location=crop.field,
            description=(
                f"Scheduled {period.lower()} watering for {crop.name}. "
                "Complete this occurrence after the crop has been watered."
            ),
            activity_date=activity_date,
            start_time=start_time,
            assigned_to="Farm Staff",
            priority="Medium",
        )
        active_keys.add(key)
        counters[result] += 1

    # Keep missed watering occurrences visible as overdue work. Future tasks
    # that no longer belong to the edited schedule are cancelled.
    for task in existing:
        if task.activity_date < today:
            if task.source_key:
                active_keys.add(task.source_key)
            continue
        if task.source_key and task.source_key not in generated_keys:
            task.status = "Cancelled"
            task.completed_at = None
            task.updated_at = now
            counters["updated"] += 1

def _crop_tasks(
    db: Session,
    *,
    today: date,
    active_keys: set[str],
    counters: dict[str, int],
) -> None:
    crops = db.scalars(
        select(Crop).where(
            Crop.is_archived == False
        )
    ).all()

    active_pests = db.scalars(
        select(CropPestDisease).where(
            CropPestDisease.status.in_(["Active", "Under Treatment"])
        )
    ).all()

    pests_by_crop: dict[
        int,
        list[CropPestDisease],
    ] = defaultdict(list)

    for record in active_pests:
        pests_by_crop[
            record.crop_id
        ].append(record)

    for crop in crops:
        crop_status = str(
            crop.status or ""
        ).strip()

        _sync_crop_watering_tasks(
            db,
            crop=crop,
            crop_status=crop_status,
            today=today,
            active_keys=active_keys,
            counters=counters,
        )

        if crop_status in {"Harvested", "Failed"}:
            continue

        if crop_status not in {
            "Harvesting",
            "Harvested",
            "Failed",
        }:
            days_until_harvest = (
                crop.estimated_harvest -
                today
            ).days

            if (
                days_until_harvest <=
                HARVEST_ADVANCE_DAYS
            ):
                key = (
                    "crop:harvest:"
                    f"{crop.id}:"
                    f"{crop.estimated_harvest.isoformat()}"
                )

                priority = (
                    "High"
                    if days_until_harvest <= 3
                    else "Medium"
                )

                if days_until_harvest < 0:
                    wording = (
                        f"Harvest is overdue by "
                        f"{abs(days_until_harvest)} day(s)."
                    )
                elif days_until_harvest == 0:
                    wording = (
                        "Estimated harvest is due today."
                    )
                else:
                    wording = (
                        "Estimated harvest is due in "
                        f"{days_until_harvest} day(s)."
                    )

                _, result = _upsert_automatic_task(
                    db,
                    source_key=key,
                    source_module="Crop",
                    source_type="crop_harvest",
                    source_record_id=crop.id,
                    source_detail_id=None,
                    source_code=crop.crop_code,
                    source_path="/crops",
                    name=(
                        f"Harvest {crop.name}"
                    ),
                    category="Harvesting",
                    related_to=(
                        f"{crop.name} — {crop.field}"
                    ),
                    location=crop.field,
                    description=(
                        f"{wording} The assigned employee records this occurrence's actual yield and reports "
                        "Partial Harvest or Final Harvest in My Tasks. Crop Management waits for manager "
                        "confirmation in Task Management; approval creates the authoritative harvest record."
                    ),
                    activity_date=(
                        crop.estimated_harvest
                    ),
                    start_time=time(7, 0),
                    assigned_to="Farm Staff",
                    priority=priority,
                )
                active_keys.add(key)
                counters[result] += 1

        for pest_record in pests_by_crop.get(
            crop.id,
            [],
        ):
            key = (
                "crop:pest-followup:"
                f"{crop.id}:"
                f"{pest_record.id}"
            )

            severity = str(
                pest_record.severity or ""
            ).strip().lower()

            if severity in {
                "critical",
                "severe",
                "very high",
            }:
                priority = "Critical"
            elif severity in {
                "high",
                "major",
            }:
                priority = "High"
            else:
                priority = "Medium"

            _, result = _upsert_automatic_task(
                db,
                source_key=key,
                source_module="Crop",
                source_type="crop_pest_followup",
                source_record_id=crop.id,
                source_detail_id=pest_record.id,
                source_code=crop.crop_code,
                source_path="/crops",
                name=(
                    "Pest/Disease Follow-up — "
                    f"{crop.name}"
                ),
                category="Pest Control",
                related_to=(
                    f"{pest_record.pest_disease_type} "
                    f"— {crop.name}"
                ),
                location=crop.field,
                description=(
                    "An active pest/disease record "
                    "requires follow-up. Update or "
                    "resolve the case in Crop Management."
                ),
                activity_date=today,
                start_time=time(8, 0),
                assigned_to="Farm Staff",
                priority=priority,
            )
            active_keys.add(key)
            counters[result] += 1


def _livestock_tasks(
    db: Session,
    *,
    today: date,
    active_keys: set[str],
    counters: dict[str, int],
) -> None:
    livestock_records = db.scalars(
        select(Livestock).where(
            Livestock.is_archived == False
        )
    ).all()

    reproduction_records = db.scalars(
        select(
            LivestockReproductionRecord
        ).where(
            LivestockReproductionRecord.expected_date.is_not(None),
            LivestockReproductionRecord.actual_date.is_(None),
            LivestockReproductionRecord.expected_date
            <= today + timedelta(days=REPRODUCTION_ADVANCE_DAYS),
        )
    ).all()

    reproduction_by_livestock: dict[
        int,
        list[LivestockReproductionRecord],
    ] = defaultdict(list)

    for record in reproduction_records:
        reproduction_by_livestock[
            record.livestock_id
        ].append(record)

    feeding_records = db.scalars(
        select(LivestockFeedingRecord).where(
            LivestockFeedingRecord.feeding_date == today
        )
    ).all()
    feeding_slots_by_livestock: dict[int, set[str]] = defaultdict(set)

    for record in feeding_records:
        feeding_slots_by_livestock[record.livestock_id].add(
            str(record.feeding_slot or "").strip().lower()
        )

    for animal in livestock_records:
        if animal.next_vaccination:
            days_until = (
                animal.next_vaccination -
                today
            ).days

            if (
                days_until <=
                VACCINATION_ADVANCE_DAYS
            ):
                key = (
                    "livestock:vaccination:"
                    f"{animal.id}:"
                    f"{animal.next_vaccination.isoformat()}"
                )

                priority = (
                    "High"
                    if days_until <= 3
                    else "Medium"
                )

                _, result = _upsert_automatic_task(
                    db,
                    source_key=key,
                    source_module="Livestock",
                    source_type=(
                        "livestock_vaccination"
                    ),
                    source_record_id=animal.id,
                    source_detail_id=None,
                    source_code=animal.animal_code,
                    source_path="/livestock",
                    name=(
                        "Vaccinate "
                        f"{animal.record_name}"
                    ),
                    category="Vaccination",
                    related_to=animal.record_name,
                    location=animal.pen_location,
                    description=(
                        "Vaccination is due or approaching. Perform the vaccination, "
                        "record the actual vaccine usage through My Tasks or manager-assisted "
                        "Record Work, and submit it for review. A vaccination recorded outside "
                        "the workforce workflow may resolve the reminder, but it is not treated "
                        "as employee-completed work."
                    ),
                    activity_date=(
                        animal.next_vaccination
                    ),
                    start_time=time(8, 0),
                    assigned_to=(
                        "Livestock Caretaker"
                    ),
                    priority=priority,
                )
                active_keys.add(key)
                counters[result] += 1

        last_check = (
            animal.last_checkup or
            animal.date_acquired
        )
        health_due = (
            last_check +
            timedelta(
                days=
                HEALTH_CHECK_FREQUENCY_DAYS
            )
        )

        unhealthy = (
            str(
                animal.health_status or ""
            )
            .strip()
            .lower()
            not in {
                "",
                "healthy",
                "good",
            }
        )

        if (
            health_due <= today
            or unhealthy
        ):
            key_date = (
                health_due
                if not unhealthy
                else today
            )

            key = (
                "livestock:health-check:"
                f"{animal.id}:"
                f"{key_date.isoformat()}"
            )

            _, result = _upsert_automatic_task(
                db,
                source_key=key,
                source_module="Livestock",
                source_type=(
                    "livestock_health_check"
                ),
                source_record_id=animal.id,
                source_detail_id=None,
                source_code=animal.animal_code,
                source_path="/livestock",
                name=(
                    "Health Check — "
                    f"{animal.record_name}"
                ),
                category=(
                    "Livestock Health Check"
                ),
                related_to=animal.record_name,
                location=animal.pen_location,
                description=(
                    "Review the livestock health "
                    "condition and update Last Checkup "
                    "in Livestock Management. "
                    f"Current health status: "
                    f"{animal.health_status}."
                ),
                activity_date=(
                    today
                    if unhealthy
                    else health_due
                ),
                start_time=time(9, 0),
                assigned_to=(
                    "Livestock Caretaker"
                ),
                priority=(
                    "High"
                    if unhealthy
                    else "Medium"
                ),
            )
            active_keys.add(key)
            counters[result] += 1

        if (
            animal.feed_times
            and str(
                animal.feed_times
            ).strip()
        ):
            completed_slots = feeding_slots_by_livestock.get(
                animal.id,
                set(),
            )
            occurrences = _feeding_occurrences(
                animal.feed_times
            )

            legacy_key = (
                "livestock:feeding:"
                f"{animal.id}:"
                f"{today.isoformat()}"
            )
            legacy_task = db.scalar(
                select(FarmActivity).where(
                    FarmActivity.is_automatic == True,
                    FarmActivity.source_key == legacy_key,
                )
            )
            if (
                legacy_task is not None
                and not legacy_task.is_archived
                and legacy_task.status in {
                    "Pending",
                    "In Progress",
                }
            ):
                # Legacy one-per-day feeding reminders are obsolete once slot-based
                # feeding tasks exist. Resolve them instead of pretending an
                # employee completed the work.
                legacy_task.status = "Resolved"
                legacy_task.completed_at = None
                legacy_task.is_archived = True
                legacy_task.updated_at = farm_now_naive()
                counters["updated"] += 1

            for (
                occurrence_index,
                slot,
                occurrence_time,
            ) in occurrences:
                key = _feeding_source_key(
                    animal.id,
                    today,
                    slot,
                )
                slot_complete = (
                    slot.strip().lower()
                    in completed_slots
                )

                existing_task = db.scalar(
                    select(FarmActivity).where(
                        FarmActivity.source_key == key,
                    )
                )

                if slot_complete:
                    if (
                        existing_task is not None
                        and existing_task.status in {
                            "Pending",
                            "In Progress",
                        }
                    ):
                        # A feeding record created outside the workforce submission
                        # flow proves the reminder is no longer actionable, but it
                        # does not prove which employee performed the work. Resolve
                        # the reminder instead of marking it Completed.
                        existing_task.status = "Resolved"
                        existing_task.completed_at = None
                        existing_task.updated_at = farm_now_naive()
                        counters["updated"] += 1
                    continue

                if slot == "Daily Feeding":
                    task_name = (
                        "Daily Feeding - "
                        f"{animal.record_name}"
                    )
                elif slot.startswith("Feeding "):
                    task_name = (
                        f"{slot} - "
                        f"{animal.record_name}"
                    )
                else:
                    task_name = (
                        f"{slot} Feeding - "
                        f"{animal.record_name}"
                    )

                _, result = _upsert_automatic_task(
                    db,
                    source_key=key,
                    source_module="Livestock",
                    source_type="livestock_feeding",
                    source_record_id=animal.id,
                    source_detail_id=occurrence_index,
                    source_code=animal.animal_code,
                    source_path="/livestock",
                    name=task_name,
                    category="Livestock Feeding",
                    related_to=animal.record_name,
                    location=animal.pen_location,
                    description=(
                        f"{slot} feeding occurrence "
                        f"{occurrence_index} of {len(occurrences)}. "
                        f"Daily schedule: {animal.feed_times}. "
                        f"Feed type: "
                        f"{animal.feed_type or 'Not specified'}. "
                        "Completing this activity records only this "
                        "feeding occurrence; the next feeding stays "
                        "pending in Upcoming Tasks."
                    ),
                    activity_date=today,
                    start_time=occurrence_time,
                    assigned_to="Livestock Caretaker",
                    priority="Medium",
                )
                active_keys.add(key)
                counters[result] += 1

        for reproduction in (
            reproduction_by_livestock.get(
                animal.id,
                [],
            )
        ):
            if (
                reproduction.expected_date is None
                or reproduction.actual_date
                is not None
            ):
                continue

            days_until = (
                reproduction.expected_date -
                today
            ).days

            if (
                days_until >
                REPRODUCTION_ADVANCE_DAYS
            ):
                continue

            record_type = str(
                reproduction.record_type or ""
            )

            normalized = (
                record_type.lower()
            )

            if (
                "hatch" in normalized
                or "egg" in normalized
            ):
                task_name = (
                    "Hatch Follow-up — "
                    f"{animal.record_name}"
                )
            else:
                task_name = (
                    "Reproduction Follow-up — "
                    f"{animal.record_name}"
                )

            key = (
                "livestock:reproduction:"
                f"{animal.id}:"
                f"{reproduction.id}:"
                f"{reproduction.expected_date.isoformat()}"
            )

            _, result = _upsert_automatic_task(
                db,
                source_key=key,
                source_module="Livestock",
                source_type=(
                    "livestock_reproduction"
                ),
                source_record_id=animal.id,
                source_detail_id=(
                    reproduction.id
                ),
                source_code=animal.animal_code,
                source_path="/production-sales",
                name=task_name,
                category="Livestock",
                related_to=(
                    f"{record_type} — "
                    f"{animal.record_name}"
                ),
                location=animal.pen_location,
                description=(
                    "A livestock reproduction event "
                    "has an expected date approaching. "
                    "Record the actual birth/hatch or "
                    "follow-up result in Production & Sales."
                ),
                activity_date=(
                    reproduction.expected_date
                ),
                start_time=time(7, 0),
                assigned_to=(
                    "Livestock Caretaker"
                ),
                priority=(
                    "High"
                    if days_until <= 1
                    else "Medium"
                ),
            )
            active_keys.add(key)
            counters[result] += 1


def _inventory_tasks(
    db: Session,
    *,
    today: date,
    active_keys: set[str],
    counters: dict[str, int],
) -> None:
    items = db.scalars(
        select(InventoryItem).where(
            InventoryItem.is_archived == False,
            InventoryItem.quantity <= InventoryItem.reorder_level,
        )
    ).all()

    stock_records = db.scalars(
        select(InventoryStockRecord)
        .join(
            InventoryItem,
            InventoryItem.id == InventoryStockRecord.inventory_item_id,
        )
        .where(
            InventoryItem.is_archived == False,
            InventoryItem.quantity <= InventoryItem.reorder_level,
            InventoryStockRecord.previous_quantity > InventoryItem.reorder_level,
            InventoryStockRecord.new_quantity <= InventoryItem.reorder_level,
        )
        .order_by(InventoryStockRecord.id.asc())
    ).all()

    history_by_item: dict[
        int,
        list[InventoryStockRecord],
    ] = defaultdict(list)

    for record in stock_records:
        history_by_item[
            record.inventory_item_id
        ].append(record)

    for item in items:
        quantity = float(
            item.quantity or 0
        )
        reorder_level = float(
            item.reorder_level or 0
        )

        if quantity > reorder_level:
            continue

        crossing_record_id = None

        for record in history_by_item.get(
            item.id,
            [],
        ):
            previous_quantity = float(
                record.previous_quantity or 0
            )
            new_quantity = float(
                record.new_quantity or 0
            )

            if (
                previous_quantity >
                reorder_level
                and new_quantity <=
                reorder_level
            ):
                crossing_record_id = (
                    record.id
                )

        episode = (
            str(crossing_record_id)
            if crossing_record_id
            else "initial"
        )

        key = (
            "inventory:restock:"
            f"{item.id}:{episode}"
        )

        if quantity <= 0:
            priority = "Critical"
        elif (
            reorder_level > 0
            and quantity <=
            reorder_level * 0.5
        ):
            priority = "High"
        else:
            priority = "Medium"

        _, result = _upsert_automatic_task(
            db,
            source_key=key,
            source_module="Inventory",
            source_type="inventory_restock",
            source_record_id=item.id,
            source_detail_id=(
                crossing_record_id
            ),
            source_code=item.item_code,
            source_path="/inventory",
            name=f"Restock {item.name}",
            category="Inventory Restocking",
            related_to=(
                f"{item.name} "
                f"({item.item_code})"
            ),
            location=item.location,
            description=(
                f"Current stock is "
                f"{quantity:g} {item.unit}; "
                f"reorder level is "
                f"{reorder_level:g} "
                f"{item.unit}. Restock the "
                "inventory item. The task "
                "completes automatically when "
                "stock rises above the reorder "
                "level."
            ),
            activity_date=today,
            start_time=time(8, 0),
            assigned_to="Farm Staff",
            priority=priority,
        )
        active_keys.add(key)
        counters[result] += 1


def _complete_resolved_tasks(
    db: Session,
    *,
    active_keys: set[str],
    counters: dict[str, int],
) -> None:
    now = farm_now_naive()

    tasks = db.scalars(
        select(FarmActivity).where(
            FarmActivity.is_automatic == True,
            FarmActivity.is_archived == False,
            FarmActivity.source_type.in_(
                EVALUATOR_CLEANUP_SOURCE_TYPES
            ),
            FarmActivity.status.in_(
                [
                    "Pending",
                    "In Progress",
                ]
            ),
        )
    ).all()

    for task in tasks:
        if (
            task.source_key
            and task.source_key
            not in active_keys
        ):
            task.status = "Resolved"
            task.completed_at = None
            task.updated_at = now
            counters["completed"] += 1


def evaluate_automatic_tasks(
    db: Session,
    *,
    commit: bool = True,
    skip_if_busy: bool = False,
) -> dict[str, int]:
    """Synchronize actionable module data into farm activities.

    Source records remain the authoritative operational data.
    Activities only represent the work that needs to be done.
    """
    if skip_if_busy:
        if not try_acquire_transaction_lock(db, "automation:tasks", timeout_ms=0):
            # This optional refresh owns no mutations. Never commit or roll back
            # someone else's pending work when another evaluator owns the lock.
            return {"created": 0, "updated": 0, "unchanged": 0, "completed": 0, "active": 0, "skipped": 1}
    else:
        acquire_transaction_lock(db, "automation:tasks")
    today = farm_today()

    active_keys: set[str] = set()

    counters = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "completed": 0,
        "active": 0,
    }

    _crop_tasks(
        db,
        today=today,
        active_keys=active_keys,
        counters=counters,
    )

    _livestock_tasks(
        db,
        today=today,
        active_keys=active_keys,
        counters=counters,
    )

    from app.services.monitoring_scheduler import sync_monitoring_tasks
    sync_monitoring_tasks(db, today=today, active_keys=active_keys, counters=counters)

    _inventory_tasks(
        db,
        today=today,
        active_keys=active_keys,
        counters=counters,
    )

    _complete_resolved_tasks(
        db,
        active_keys=active_keys,
        counters=counters,
    )

    # A later edit to a crop watering plan or livestock feeding schedule may
    # create native work for a previously planned protocol step. Only Pending
    # protocol duplicates are resolved; started and reviewed work is history.
    counters["updated"] += resolve_pending_protocol_overlaps(db, today=today)

    # Leave restoration is idempotent and runs in the same scheduler
    # transaction. It never touches completed, in-progress, submitted, or
    # manager-overridden work.
    reconcile_expired_leave_coverage(db)

    from app.services.farm_event_service import reconcile_event_holds
    reconcile_event_holds(db)

    counters["active"] = len(
        active_keys
    )

    if commit:
        db.commit()
    else:
        db.flush()

    return counters
