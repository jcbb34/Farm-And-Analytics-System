from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.crop_report_history import crop_statuses_at_period_end
from app.services.query_batching import scalar_rows_in_batches

from app.core.farm_time import farm_today
from app.models import (
    AuditLog,
    Crop,
    CropYieldRecord,
    Employee,
    FarmActivity,
    FarmReport,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    LivestockGrowthRecord,
    LivestockPen,
    LivestockProductionRecord,
    LivestockSale,
    LivestockSaleItem,
    LivestockTransaction,
    LivestockVaccinationRecord,
    ResourceUsage,
    StaffAttendance,
    StaffAttendanceAudit,
    TaskAssignmentHistory,
    TaskSubmission,
)
from app.services.work_schedule_service import resolve_availability_range
from app.services.farm_event_service import hold_context, task_hold_info


OPERATIONAL_REPORT_TYPES = {
    "Daily Attendance Report",
    "Weekly Attendance Summary",
    "Task Completion and Employee Performance",
    "Task Coverage and Reassignment",
    "Care Protocol Compliance",
    "Crop Yield and Input Usage",
    "Livestock Feeding, Growth, and Health",
    "Inventory Movement and Resource Usage",
    "Production and Sales Summary",
    "Generated Report History and Audit Trail",
}

CARE_KEYWORDS = {
    "watering": "Watering",
    "water": "Watering",
    "feeding": "Feeding",
    "feed": "Feeding",
    "fertilizer": "Fertilizer",
    "fertilization": "Fertilizer",
    "pesticide": "Pesticide",
    "vaccination": "Vaccination",
    "vaccine": "Vaccination",
    "vitamin": "Vitamins",
    "health": "Health Inspection",
    "inspection": "Health Inspection",
    "weigh": "Weighing",
    "weight": "Weighing",
}

TERMINAL_APPROVED = {"Approved", "Completed"}
ACTIVE_TASK_STATUSES = {"Pending", "In Progress", "Submitted for Review", "Returned for Correction"}


def _rows_for_ids(db: Session, ids, model, id_column, *conditions, order_by=()):
    """Load report sources without exceeding SQL Server's bound-parameter limit."""
    return scalar_rows_in_batches(
        db, ids,
        lambda batch: select(model).where(id_column.in_(batch), *conditions).order_by(*order_by),
    )


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _time(value: time | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%H:%M")


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _display(value: Any) -> Any:
    if value is None or value == "":
        return "Not Recorded"
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _filter_id(filters: dict[str, Any], key: str) -> int | None:
    value = filters.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_matches(filters: dict[str, Any], value: str | None) -> bool:
    selected = str(filters.get("status") or "").strip()
    return not selected or selected.lower() == str(value or "").lower()


def _source_matches(filters: dict[str, Any], is_system: bool) -> bool:
    selected = str(filters.get("source") or "").strip().lower()
    if not selected:
        return True
    return (selected == "system" and is_system) or (selected == "manual" and not is_system)


def _employment_in_range(employee: Employee, start: date, end: date) -> bool:
    if employee.date_hired and employee.date_hired > end:
        return False
    # A previous archive timestamp is not an end-of-employment date after restore.
    # Existing installations can have both is_archived=False and archived_at set.
    ended = employee.archived_at.date() if employee.is_archived and employee.archived_at else None
    if ended and ended < start:
        return False
    return True


def _working_hours(att: StaffAttendance) -> float | str:
    if not att.check_in_at or not att.check_out_at:
        return "Not Recorded"
    seconds = max(0.0, (att.check_out_at - att.check_in_at).total_seconds())
    return round(seconds / 3600.0, 2)


def _fingerprint(snapshot: dict[str, Any]) -> str:
    material = {
        "metrics": snapshot.get("metrics", {}),
        "operational_rows": snapshot.get("operational_rows", []),
        "sections": snapshot.get("sections", {}),
        "filters": snapshot.get("filters", {}),
    }
    raw = json.dumps(material, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _base(report_type: str, start: date, end: date, filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_kind": "operational_factual",
        "report_type": report_type,
        "period": {"start": start.isoformat(), "end": end.isoformat(), "timezone": "Asia/Manila"},
        "filters": filters,
        "metrics": {},
        "operational_rows": [],
        "sections": {},
        "data_notes": [
            "This report contains recorded historical facts only.",
            "Not Recorded / No Data is used when a source value is unavailable; missing values are not silently treated as zero.",
        ],
    }


def _employees(db: Session, start: date, end: date, filters: dict[str, Any]) -> list[Employee]:
    stmt = select(Employee)
    employee_id = _filter_id(filters, "employee_id")
    if employee_id:
        stmt = stmt.where(Employee.id == employee_id)
    return [row for row in db.scalars(stmt.order_by(Employee.full_name)).all() if _employment_in_range(row, start, end)]


def _build_daily_attendance(db: Session, start: date, end: date, filters: dict[str, Any], weekly: bool) -> dict[str, Any]:
    snapshot = _base("Weekly Attendance Summary" if weekly else "Daily Attendance Report", start, end, filters)
    employees = _employees(db, start, end, filters)
    ids = [e.id for e in employees]
    availability = resolve_availability_range(db, ids, start, end) if ids else []
    availability_map = {(row.employee_id, row.work_date): row for row in availability}
    attendance_rows = _rows_for_ids(
        db, ids, StaffAttendance, StaffAttendance.employee_id,
        StaffAttendance.attendance_date >= start,
        StaffAttendance.attendance_date <= end,
    )
    attendance_map = {(row.employee_id, row.attendance_date): row for row in attendance_rows}
    audit_ids = [row.id for row in attendance_rows]
    audits = _rows_for_ids(db, audit_ids, StaffAttendanceAudit, StaffAttendanceAudit.attendance_id)
    audits_by_attendance: dict[int, list[StaffAttendanceAudit]] = defaultdict(list)
    for audit in audits:
        audits_by_attendance[audit.attendance_id].append(audit)

    detail_rows: list[dict[str, Any]] = []
    today = farm_today()
    current = start
    while current <= end:
        for employee in employees:
            if employee.date_hired and current < employee.date_hired:
                continue
            if employee.is_archived and employee.archived_at and current > employee.archived_at.date():
                continue
            avail = availability_map.get((employee.id, current))
            att = attendance_map.get((employee.id, current))
            availability_status = avail.status if avail else "Schedule Needs Setup"
            event_excused = bool(avail and avail.suspension_full_shift and not (att and att.check_in_at))
            excluded = availability_status in {"Rest Day", "On Leave", "Special Day Off"} or event_excused
            if current > today:
                attendance_status = "Not Recorded"
            elif excluded:
                attendance_status = availability_status
            elif att:
                attendance_status = att.status
            else:
                attendance_status = "Not Checked In" if current == today else "Not Recorded"
            if not _status_matches(filters, attendance_status):
                continue
            corrections = audits_by_attendance.get(att.id, []) if att else []
            detail_rows.append({
                "employee_id": employee.id,
                "employee": employee.full_name,
                "employee_code": employee.employee_code,
                "work_date": current.isoformat(),
                "scheduled_shift": (
                    f"{_time(att.scheduled_start_time)}-{_time(att.scheduled_end_time)}" if att and att.scheduled_start_time and att.scheduled_end_time
                    else f"{_time(avail.start_time)}-{_time(avail.end_time)}" if avail and avail.start_time and avail.end_time
                    else "Schedule Needs Setup" if avail and avail.schedule_status == "Needs Setup" else "Not Recorded"
                ),
                "check_in": _dt(att.check_in_at) if att else "Not Recorded",
                "check_out": _dt(att.check_out_at) if att else "Not Recorded",
                "attendance_status": attendance_status,
                "original_attendance_status": att.status if att else "Not Recorded",
                "farm_declarations": "; ".join(x["title"] for x in (avail.suspensions if avail else [])) or "None",
                "minutes_late": att.minutes_late if not event_excused and att and att.minutes_late is not None else "Not Recorded",
                "minutes_early": att.minutes_early if not event_excused and att and att.minutes_early is not None else "Not Recorded",
                "overtime_minutes": att.overtime_minutes if att and att.overtime_minutes is not None else "Not Recorded",
                "hours_worked": _working_hours(att) if att else "Not Recorded",
                "missing_check_out": bool(att and att.check_in_at and not att.check_out_at and current < today),
                "leave_or_rest_day": availability_status if excluded else "No",
                "attendance_source": att.attendance_source if att else "Not Recorded",
                "notes": att.notes if att and att.notes else "Not Recorded",
                "correction_count": len(corrections),
                "latest_correction_reason": corrections[-1].reason if corrections and corrections[-1].reason else "Not Recorded",
                "attendance_id": att.id if att else None,
            })
        current += timedelta(days=1)

    if weekly:
        per_employee: list[dict[str, Any]] = []
        for employee in employees:
            rows = [row for row in detail_rows if row["employee_id"] == employee.id]
            eligible = []
            schedule_known = True
            current = start
            while current <= end:
                if employee.date_hired and current < employee.date_hired:
                    current += timedelta(days=1); continue
                if employee.is_archived and employee.archived_at and current > employee.archived_at.date():
                    current += timedelta(days=1); continue
                avail = availability_map.get((employee.id, current))
                if not avail or avail.schedule_status == "Needs Setup":
                    schedule_known = False
                elif avail.status not in {"Rest Day", "On Leave", "Special Day Off"} and avail.is_working_day is not False:
                    eligible.append(current)
                current += timedelta(days=1)
            present_states = {"On Time", "Late", "Present", "Checked Out", "Early Departure", "Missing Check Out"}
            days_present = sum(1 for r in rows if r["attendance_status"] in present_states)
            scheduled = len(eligible) if schedule_known else "Not Recorded"
            percentage = round((days_present / len(eligible)) * 100.0, 2) if schedule_known and eligible else ("No Data" if schedule_known else "Not Recorded")
            hours = [r["hours_worked"] for r in rows if isinstance(r["hours_worked"], (int, float))]
            per_employee.append({
                "employee_id": employee.id,
                "employee": employee.full_name,
                "scheduled_workdays": scheduled,
                "days_present": days_present,
                "on_time_arrivals": sum(1 for r in rows if r["attendance_status"] in present_states and r["minutes_late"] == 0),
                "late_arrivals": sum(1 for r in rows if isinstance(r["minutes_late"], int) and r["minutes_late"] > 0),
                "absences": sum(1 for r in rows if r["attendance_status"] == "Absent"),
                "sick_days": sum(1 for r in rows if r["attendance_status"] == "Sick"),
                "approved_leave": sum(1 for r in rows if r["leave_or_rest_day"] == "On Leave"),
                "rest_days": sum(1 for r in rows if r["leave_or_rest_day"] == "Rest Day"),
                "special_days_off": sum(1 for r in rows if r["leave_or_rest_day"] == "Special Day Off"),
                "early_departures": sum(1 for r in rows if isinstance(r["minutes_early"], int) and r["minutes_early"] > 0),
                "missing_checkouts": sum(1 for r in rows if r["missing_check_out"]),
                "total_minutes_late": sum(r["minutes_late"] for r in rows if isinstance(r["minutes_late"], int)),
                "total_hours_worked": round(sum(hours), 2) if hours else "Not Recorded",
                "attendance_percentage": percentage,
            })
        snapshot["operational_rows"] = per_employee
        snapshot["sections"] = {"daily_details": detail_rows}
        valid_percentages = [r["attendance_percentage"] for r in per_employee if isinstance(r["attendance_percentage"], (int, float))]
        snapshot["metrics"] = {
            "employees": len(per_employee),
            "average_attendance_percentage": round(sum(valid_percentages) / len(valid_percentages), 2) if valid_percentages else "Not Recorded",
            "total_late_arrivals": sum(r["late_arrivals"] for r in per_employee),
            "total_absences": sum(r["absences"] for r in per_employee),
            "total_sick_days": sum(r["sick_days"] for r in per_employee),
            "missing_checkouts": sum(r["missing_checkouts"] for r in per_employee),
        }
    else:
        snapshot["operational_rows"] = detail_rows
        snapshot["metrics"] = {
            "employees": len({r["employee_id"] for r in detail_rows}),
            "present": sum(1 for r in detail_rows if r["attendance_status"] in {"On Time", "Late", "Present", "Checked Out", "Early Departure", "Missing Check Out"}),
            "late": sum(1 for r in detail_rows if isinstance(r["minutes_late"], int) and r["minutes_late"] > 0),
            "absent": sum(1 for r in detail_rows if r["attendance_status"] == "Absent"),
            "sick": sum(1 for r in detail_rows if r["attendance_status"] == "Sick"),
            "approved_leave": sum(1 for r in detail_rows if r["leave_or_rest_day"] == "On Leave"),
            "rest_days": sum(1 for r in detail_rows if r["leave_or_rest_day"] == "Rest Day"),
            "possible_absences": sum(1 for r in detail_rows if r["attendance_status"] in {"Not Recorded", "Not Checked In"} and r["leave_or_rest_day"] == "No"),
            "missing_checkouts": sum(1 for r in detail_rows if r["missing_check_out"]),
        }
    return snapshot


def _activities(db: Session, start: date, end: date, filters: dict[str, Any]) -> list[FarmActivity]:
    stmt = select(FarmActivity).where(FarmActivity.activity_date >= start, FarmActivity.activity_date <= end)
    employee_id = _filter_id(filters, "employee_id")
    if employee_id:
        stmt = stmt.where(FarmActivity.assigned_employee_id == employee_id)
    rows = list(db.scalars(stmt.order_by(FarmActivity.activity_date, FarmActivity.id)).all())
    return [r for r in rows if _status_matches(filters, r.status)]


def _build_task_performance(db: Session, start: date, end: date, filters: dict[str, Any]) -> dict[str, Any]:
    snapshot = _base("Task Completion and Employee Performance", start, end, filters)
    tasks = _activities(db, start, end, filters)
    employee_ids = {v for task in tasks for v in (task.assigned_employee_id, task.default_employee_id) if v}
    employees = {e.id: e.full_name for e in _rows_for_ids(db, employee_ids, Employee, Employee.id)}
    task_ids = [task.id for task in tasks]
    submissions = _rows_for_ids(db, task_ids, TaskSubmission, TaskSubmission.activity_id)
    latest_submission: dict[int, TaskSubmission] = {}
    for row in submissions:
        current = latest_submission.get(row.activity_id)
        if current is None or (row.attempt_number, row.id) > (current.attempt_number, current.id):
            latest_submission[row.activity_id] = row
    usage = _rows_for_ids(
        db, task_ids, ResourceUsage, ResourceUsage.activity_id,
        ResourceUsage.is_voided == False,  # noqa: E712
    )
    usage_by_task: dict[int, list[ResourceUsage]] = defaultdict(list)
    for row in usage:
        usage_by_task[row.activity_id].append(row)

    event_holds = hold_context(db, tasks)
    groups: dict[int | None, dict[str, Any]] = {}
    details: list[dict[str, Any]] = []
    for task in tasks:
        employee_id = task.assigned_employee_id
        group = groups.setdefault(employee_id, {
            "employee_id": employee_id,
            "assigned_employee": employees.get(employee_id, "Unassigned"),
            "held": 0, "total_assigned": 0, "completed_approved": 0, "pending": 0, "in_progress": 0,
            "submitted_for_review": 0, "returned": 0, "overdue": 0, "voided": 0,
            "on_time_completed": 0, "evidence_available": 0, "actual_resource_usage_records": 0,
        })
        group["total_assigned"] += 1
        status = task.status or "Pending"
        held = task_hold_info(db, task, context=event_holds)["work_suspended"]
        if held: group["held"] += 1
        elif status in TERMINAL_APPROVED:
            group["completed_approved"] += 1
        elif status == "Pending": group["pending"] += 1
        elif status == "In Progress": group["in_progress"] += 1
        elif status == "Submitted for Review": group["submitted_for_review"] += 1
        elif status == "Returned for Correction": group["returned"] += 1
        elif status == "Voided": group["voided"] += 1
        if not held and status not in TERMINAL_APPROVED | {"Voided", "Archived"} and task.activity_date < farm_today():
            group["overdue"] += 1
        on_time = None
        if task.completed_at:
            due = datetime.combine(task.activity_date, task.end_time or time(23, 59, 59))
            on_time = task.completed_at <= due
            if on_time: group["on_time_completed"] += 1
        submission = latest_submission.get(task.id)
        evidence = bool(submission and submission.evidence_url)
        if evidence: group["evidence_available"] += 1
        actual_usage = usage_by_task.get(task.id, [])
        group["actual_resource_usage_records"] += len(actual_usage)
        details.append({
            "task_id": task.id,
            "task_code": task.activity_code,
            "task": task.name,
            "date": task.activity_date.isoformat(),
            "assigned_employee": employees.get(task.assigned_employee_id, "Unassigned"),
            "default_employee": employees.get(task.default_employee_id, "Not Recorded"),
            "assignment_source": task.assignment_source,
            "status": "Held for declaration review" if held else status,
            "on_time_completion": on_time if on_time is not None else "Not Recorded",
            "evidence_available": evidence,
            "actual_quantity": _display(submission.actual_quantity) if submission else "Not Recorded",
            "actual_unit": _display(submission.actual_unit) if submission else "Not Recorded",
            "resource_usage_records": len(actual_usage),
        })
    rows = []
    for group in groups.values():
        denominator = group["completed_approved"]
        group["on_time_completion_rate"] = round((group["on_time_completed"] / denominator) * 100.0, 2) if denominator else "No Data"
        rows.append(group)
    snapshot["operational_rows"] = rows
    snapshot["sections"] = {"task_details": details}
    snapshot["metrics"] = {
        "held": sum(r["held"] for r in rows),
        "total_assigned": len(tasks),
        "completed_approved": sum(r["completed_approved"] for r in rows),
        "pending": sum(r["pending"] for r in rows),
        "in_progress": sum(r["in_progress"] for r in rows),
        "submitted_for_review": sum(r["submitted_for_review"] for r in rows),
        "returned": sum(r["returned"] for r in rows),
        "overdue": sum(r["overdue"] for r in rows),
        "voided": sum(r["voided"] for r in rows),
    }
    return snapshot


def _build_coverage(db: Session, start: date, end: date, filters: dict[str, Any]) -> dict[str, Any]:
    snapshot = _base("Task Coverage and Reassignment", start, end, filters)
    history = list(db.scalars(select(TaskAssignmentHistory).where(
        TaskAssignmentHistory.changed_at >= datetime.combine(start, time.min),
        TaskAssignmentHistory.changed_at <= datetime.combine(end, time.max),
    ).order_by(TaskAssignmentHistory.changed_at)).all())
    employee_filter = _filter_id(filters, "employee_id")
    if employee_filter:
        history = [h for h in history if employee_filter in {h.old_employee_id, h.new_employee_id}]
    ids = {v for h in history for v in (h.old_employee_id, h.new_employee_id) if v}
    employees = {e.id: e.full_name for e in _rows_for_ids(db, ids, Employee, Employee.id)}
    task_ids = {h.activity_id for h in history}
    tasks = {t.id: t for t in _rows_for_ids(db, task_ids, FarmActivity, FarmActivity.id)}
    rows = []
    for h in history:
        if not _source_matches(filters, h.is_automatic):
            continue
        task = tasks.get(h.activity_id)
        if filters.get("status") and task and not _status_matches(filters, task.status):
            continue
        rows.append({
            "assignment_history_id": h.id,
            "task_id": h.activity_id,
            "task_code": task.activity_code if task else "Not Recorded",
            "task": task.name if task else "Not Recorded",
            "original_employee": employees.get(h.old_employee_id, "Unassigned"),
            "covering_employee": employees.get(h.new_employee_id, "Unassigned"),
            "coverage_date": _date(h.coverage_date) or _date(h.changed_at.date()),
            "reason": h.reason,
            "assignment_source": h.assignment_source,
            "source": "System" if h.is_automatic else "Manual",
            "task_status": task.status if task else "Not Recorded",
            "needs_coverage": bool(task and task.needs_reassignment),
            "changed_at": _dt(h.changed_at),
            "resolution_time": "Not Recorded",
        })
    snapshot["operational_rows"] = rows
    snapshot["metrics"] = {
        "coverage_events": len(rows),
        "leave": sum(1 for r in rows if "leave" in str(r["assignment_source"]).lower() or "leave" in str(r["reason"]).lower()),
        "rest_day": sum(1 for r in rows if "rest" in str(r["assignment_source"]).lower() or "rest" in str(r["reason"]).lower()),
        "attendance_absent_sick": sum(1 for r in rows if "attendance" in str(r["assignment_source"]).lower() or any(k in str(r["reason"]).lower() for k in ("absent", "sick"))),
        "manager_override": sum(1 for r in rows if "manager" in str(r["assignment_source"]).lower()),
        "still_needing_coverage": sum(1 for r in rows if r["needs_coverage"]),
    }
    return snapshot


def _care_category(task: FarmActivity) -> str:
    text = " ".join(str(v or "") for v in (task.category, task.name, task.source_type, task.planned_usage_type)).lower()
    for keyword, label in CARE_KEYWORDS.items():
        if keyword in text:
            return label
    return task.category or "Other Configured Care Step"


def _build_compliance(db: Session, start: date, end: date, filters: dict[str, Any]) -> dict[str, Any]:
    snapshot = _base("Care Protocol Compliance", start, end, filters)
    tasks = _activities(db, start, end, filters)
    tasks = [t for t in tasks if t.source_protocol_family_code or t.source_module in {"Crop", "Livestock"}]
    task_ids = [t.id for t in tasks]
    submissions = _rows_for_ids(
        db, task_ids, TaskSubmission, TaskSubmission.activity_id,
        TaskSubmission.review_status == "Approved",
    )
    approved_by_task: dict[int, TaskSubmission] = {}
    for s in submissions:
        if s.review_status == "Approved":
            current = approved_by_task.get(s.activity_id)
            if current is None or s.id > current.id: approved_by_task[s.activity_id] = s
    event_holds = hold_context(db, tasks)
    rows = []
    for task in tasks:
        submission = approved_by_task.get(task.id)
        status = task.status
        held = task_hold_info(db, task, context=event_holds)["work_suspended"]
        missed = not held and status not in TERMINAL_APPROVED | {"Voided"} and task.activity_date < farm_today()
        rows.append({
            "task_id": task.id, "task_code": task.activity_code, "care_step": task.name,
            "care_category": _care_category(task), "module": task.source_module or "Not Recorded",
            "date": task.activity_date.isoformat(), "status": "Held for declaration review" if held else "Missed/Overdue" if missed else status,
            "scheduled": True, "completed_approved": status in TERMINAL_APPROVED,
            "planned_quantity": _display(task.planned_quantity), "planned_unit": _display(task.planned_unit),
            "actual_approved_quantity": _display(submission.actual_quantity) if submission else "Not Recorded",
            "actual_unit": _display(submission.actual_unit) if submission else "Not Recorded",
            "protocol_family": _display(task.source_protocol_family_code), "protocol_version": _display(task.source_protocol_version),
        })
    snapshot["operational_rows"] = rows
    snapshot["metrics"] = {
        "scheduled": len(rows), "completed_approved": sum(1 for r in rows if r["completed_approved"]),
        "missed_overdue": sum(1 for r in rows if r["status"] == "Missed/Overdue"),
        "returned": sum(1 for r in rows if r["status"] == "Returned for Correction"),
        "voided": sum(1 for r in rows if r["status"] == "Voided"),
    }
    return snapshot


def _build_crop(db: Session, start: date, end: date, filters: dict[str, Any]) -> dict[str, Any]:
    snapshot = _base("Crop Yield and Input Usage", start, end, filters)
    crop_id = _filter_id(filters, "crop_id")
    crops_stmt = select(Crop)
    if crop_id: crops_stmt = crops_stmt.where(Crop.id == crop_id)
    if filters.get("field"): crops_stmt = crops_stmt.where(Crop.field == str(filters["field"]))
    crops = [
        crop for crop in db.scalars(crops_stmt.where(Crop.planting_date <= end)).all()
        if not crop.is_archived or not crop.updated_at or crop.updated_at.date() >= start
    ]
    period_status = crop_statuses_at_period_end(db, crops, end)
    ids = [c.id for c in crops]
    yields = _rows_for_ids(db, ids, CropYieldRecord, CropYieldRecord.crop_id,
                          CropYieldRecord.harvest_date >= start, CropYieldRecord.harvest_date <= end)
    usages = _rows_for_ids(db, ids, ResourceUsage, ResourceUsage.crop_id,
                          ResourceUsage.usage_date >= start, ResourceUsage.usage_date <= end,
                          ResourceUsage.is_voided == False)  # noqa: E712
    usage_by_crop: dict[int, list[ResourceUsage]] = defaultdict(list)
    for u in usages: usage_by_crop[u.crop_id].append(u)
    yield_by_crop: dict[int, list[CropYieldRecord]] = defaultdict(list)
    for y in yields: yield_by_crop[y.crop_id].append(y)
    rows = []
    for crop in crops:
        crop_yields = yield_by_crop.get(crop.id, [])
        actual = sum(_num(y.quantity_kg) for y in crop_yields) if crop_yields else None
        loss = sum(_num(y.damaged_quantity_kg) for y in crop_yields) if crop_yields else None
        use_records = usage_by_crop.get(crop.id, [])
        def usage_total(keyword: str):
            matched = [u for u in use_records if keyword in str(u.category_snapshot or u.usage_type or "").lower()]
            if not matched:
                return "Not Recorded"
            units = {str(u.unit or "").strip() for u in matched}
            if len(units) != 1:
                return "Mixed Units - See Detail"
            unit = next(iter(units)) or "unit"
            return f"{round(sum(_num(u.quantity) for u in matched), 3)} {unit}"
        partial_yields = [y for y in crop_yields if str(y.harvest_type or "").strip().lower() == "partial harvest"]
        final_yields = [y for y in crop_yields if str(y.harvest_type or "").strip().lower() == "final harvest"]
        rows.append({
            "crop_id": crop.id, "crop_code": crop.crop_code, "crop": crop.name, "variety": crop.variety,
            "field": crop.field, "planting_date": _date(crop.planting_date),
            "crop_cycle_status": period_status[crop.id],
            "first_harvest_date": _date(min((y.harvest_date for y in crop_yields), default=None)),
            "final_harvest_date": _date(max((y.harvest_date for y in final_yields), default=None)),
            "partial_harvest_count": len(partial_yields),
            "partial_harvest_kg": round(sum(_num(y.quantity_kg) for y in partial_yields), 3) if partial_yields else 0,
            "final_harvest_kg": round(sum(_num(y.quantity_kg) for y in final_yields), 3) if final_yields else "Not Recorded",
            "harvest_dates": ", ".join(y.harvest_date.isoformat() for y in crop_yields) if crop_yields else "Not Recorded",
            "area_hectares": _num(crop.area_hectares), "actual_harvest_kg": round(actual, 3) if actual is not None else "Not Recorded",
            "yield_kg_per_hectare": round(actual / _num(crop.area_hectares), 3) if actual is not None and _num(crop.area_hectares) > 0 else "Not Recorded",
            "crop_losses_kg": round(loss, 3) if loss is not None else "Not Recorded",
            "seed_usage": usage_total("seed"),
            "fertilizer_usage": usage_total("fert"),
            "pesticide_usage": usage_total("pest"),
            "water_usage": usage_total("water"),
            "related_inventory_usage_records": len(use_records),
        })
    snapshot["operational_rows"] = rows
    snapshot["sections"] = {"yield_records": [{"crop_id": y.crop_id, "harvest_date": y.harvest_date.isoformat(), "harvest_type": y.harvest_type, "quantity_kg": _num(y.quantity_kg), "damaged_quantity_kg": _num(y.damaged_quantity_kg), "related_task_id": y.related_task_id} for y in yields], "input_usage": [{"usage_id": u.id, "crop_id": u.crop_id, "item": u.item_name_snapshot, "category": u.category_snapshot, "quantity": _num(u.quantity), "unit": u.unit, "date": u.usage_date.isoformat(), "task_id": u.activity_id} for u in usages]}
    snapshot["metrics"] = {"crops": len(rows), "harvest_records": len(yields), "actual_harvest_kg": round(sum(_num(y.quantity_kg) for y in yields),3) if yields else "Not Recorded", "input_usage_records": len(usages)}
    return snapshot


def _build_livestock(db: Session, start: date, end: date, filters: dict[str, Any]) -> dict[str, Any]:
    snapshot = _base("Livestock Feeding, Growth, and Health", start, end, filters)
    livestock_id = _filter_id(filters, "livestock_id")
    pen_id = _filter_id(filters, "pen_id")
    stmt = select(Livestock)
    if livestock_id: stmt = stmt.where(Livestock.id == livestock_id)
    if pen_id: stmt = stmt.where(Livestock.pen_id == pen_id)
    animals = list(db.scalars(stmt).all())
    ids = [a.id for a in animals]
    pens = {p.id: p for p in _rows_for_ids(db, (a.pen_id for a in animals if a.pen_id), LivestockPen, LivestockPen.id)}
    growth = _rows_for_ids(db, ids, LivestockGrowthRecord, LivestockGrowthRecord.livestock_id,
                           LivestockGrowthRecord.measurement_date >= start, LivestockGrowthRecord.measurement_date <= end)
    vaccinations = _rows_for_ids(db, ids, LivestockVaccinationRecord, LivestockVaccinationRecord.livestock_id,
                                 LivestockVaccinationRecord.date_administered >= start, LivestockVaccinationRecord.date_administered <= end)
    transfers = _rows_for_ids(db, ids, LivestockTransaction, LivestockTransaction.livestock_id,
                              LivestockTransaction.event_date >= start, LivestockTransaction.event_date <= end)
    # Feeding totals intentionally use approved task-posted ResourceUsage rather than legacy direct feeding confirmation rows.
    usages = _rows_for_ids(db, ids, ResourceUsage, ResourceUsage.livestock_id,
                          ResourceUsage.usage_date >= start, ResourceUsage.usage_date <= end,
                          ResourceUsage.is_voided == False, ResourceUsage.task_posting_active == True)  # noqa: E712
    activity_ids = {u.activity_id for u in usages if u.activity_id}
    activities = {a.id: a for a in _rows_for_ids(db, activity_ids, FarmActivity, FarmActivity.id)}
    submission_ids = {u.task_submission_id for u in usages if u.task_submission_id}
    submissions = {row.id: row for row in _rows_for_ids(db, submission_ids, TaskSubmission, TaskSubmission.id)}
    feeding = [
        u for u in usages
        if activities.get(u.activity_id)
        and _care_category(activities[u.activity_id]) == "Feeding"
        and u.task_submission_id in submissions
        and submissions[u.task_submission_id].review_status == "Approved"
    ]
    inventory_ids = {u.inventory_item_id for u in feeding if u.inventory_item_id}
    inventory = {i.id: i for i in _rows_for_ids(db, inventory_ids, InventoryItem, InventoryItem.id)}
    health_tasks = list(db.scalars(select(FarmActivity).where(
        FarmActivity.source_module == "Livestock", FarmActivity.activity_date >= start, FarmActivity.activity_date <= end
    )).all())
    health_by: dict[int, list[FarmActivity]] = defaultdict(list)
    for task in health_tasks:
        if task.source_record_id in ids and _care_category(task) in {"Health Inspection", "Vaccination", "Vitamins"}:
            health_by[task.source_record_id].append(task)
    growth_by: dict[int,list] = defaultdict(list); vacc_by: dict[int,list] = defaultdict(list); feed_by: dict[int,list] = defaultdict(list); transfer_by: dict[int,list] = defaultdict(list)
    for x in growth: growth_by[x.livestock_id].append(x)
    for x in vaccinations: vacc_by[x.livestock_id].append(x)
    for x in feeding: feed_by[x.livestock_id].append(x)
    for x in transfers: transfer_by[x.livestock_id].append(x)
    rows=[]
    for animal in animals:
        frows=feed_by.get(animal.id,[]); grows=growth_by.get(animal.id,[]); vaccs=vacc_by.get(animal.id,[]); trans=transfer_by.get(animal.id,[]); health=health_by.get(animal.id,[])
        valid_cost = bool(frows) and all(inventory.get(u.inventory_item_id) is not None and inventory[u.inventory_item_id].cost is not None for u in frows)
        feed_cost = sum(_num(u.quantity) * _num(inventory[u.inventory_item_id].cost) for u in frows) if valid_cost else None
        planned_feed = sum(_num(activities[u.activity_id].planned_quantity) for u in frows if activities.get(u.activity_id) and activities[u.activity_id].planned_quantity is not None)
        rows.append({
            "livestock_id": animal.id, "record": animal.record_name, "species": animal.animal_type, "breed": animal.breed,
            "pen": pens.get(animal.pen_id).name if pens.get(animal.pen_id) else animal.pen_location,
            "animal_count": animal.quantity, "health_status": animal.health_status, "growth_stage": animal.growth_status,
            "planned_feed_quantity": round(planned_feed,3) if frows and planned_feed else "Not Recorded",
            "approved_actual_feed": round(sum(_num(u.quantity) for u in frows),3) if frows else "Not Recorded",
            "feed_cost": round(feed_cost,2) if feed_cost is not None else "Not Recorded",
            "weight_measurements": len(grows), "latest_weight_kg": _num(grows[-1].weight_kg) if grows else _display(animal.weight_kg),
            "vaccinations": len(vaccs), "treatments_or_health_tasks": len(health), "transfers": len(trans), "last_checkup": _display(animal.last_checkup),
            "illness_status": animal.health_status if animal.health_status and animal.health_status.lower() not in {"healthy", "normal"} else "No Recorded Illness in Current Status",
            "mortality": sum(abs(int(t.quantity or 0)) for t in trans if any(word in str(t.transaction_type).lower() for word in ("mortality", "death", "died"))) or "Not Recorded",
        })
    snapshot["operational_rows"] = rows
    snapshot["sections"] = {
        "approved_feeding_usage": [{"usage_id":u.id,"livestock_id":u.livestock_id,"task_id":u.activity_id,"date":u.usage_date.isoformat(),"feed_item":u.item_name_snapshot,"quantity":_num(u.quantity),"unit":u.unit} for u in feeding],
        "growth_history": [{"livestock_id":g.livestock_id,"date":g.measurement_date.isoformat(),"average_weight_kg":_display(g.weight_kg),"growth_stage":_display(g.expected_stage)} for g in growth],
        "vaccinations": [{"livestock_id":v.livestock_id,"date":v.date_administered.isoformat(),"vaccine":v.vaccine,"status":v.status} for v in vaccinations],
        "transfers": [{"livestock_id":t.livestock_id,"date":t.event_date.isoformat(),"type":t.transaction_type,"quantity":t.quantity,"reason":_display(t.reason)} for t in transfers],
    }
    snapshot["metrics"]={"livestock_records":len(rows),"approved_feeding_records":len(feeding),"approved_feed_quantity":round(sum(_num(u.quantity) for u in feeding),3) if feeding else "Not Recorded","growth_measurements":len(growth),"vaccinations":len(vaccinations),"transfers":len(transfers)}
    return snapshot


def _build_inventory(db: Session, start: date, end: date, filters: dict[str, Any]) -> dict[str, Any]:
    snapshot=_base("Inventory Movement and Resource Usage",start,end,filters)
    item_id=_filter_id(filters,"inventory_item_id")
    stmt=select(InventoryItem)
    if item_id: stmt=stmt.where(InventoryItem.id==item_id)
    items=list(db.scalars(stmt).all()); ids=[i.id for i in items]
    moves = _rows_for_ids(db, ids, InventoryStockRecord, InventoryStockRecord.inventory_item_id,
                          InventoryStockRecord.adjustment_date >= start, InventoryStockRecord.adjustment_date <= end)
    usages = _rows_for_ids(db, ids, ResourceUsage, ResourceUsage.inventory_item_id,
                           ResourceUsage.usage_date >= start, ResourceUsage.usage_date <= end)
    moves.sort(key=lambda m: (m.inventory_item_id, m.adjustment_date, m.id))
    usages.sort(key=lambda u: (u.inventory_item_id, u.usage_date, u.id))
    move_by=defaultdict(list); usage_by=defaultdict(list)
    for m in moves: move_by[m.inventory_item_id].append(m)
    for u in usages: usage_by[u.inventory_item_id].append(u)
    rows=[]
    for item in items:
        ms=move_by.get(item.id,[]); us=usage_by.get(item.id,[])
        opening=_num(ms[0].previous_quantity) if ms else "Not Recorded"
        closing=_num(ms[-1].new_quantity) if ms else _num(item.quantity)
        def q(types): return sum(abs(_num(m.quantity)) for m in ms if str(m.adjustment_type).lower() in types)
        approved_usage=sum(_num(u.quantity) for u in us if not u.is_voided and u.task_posting_active)
        rows.append({
            "inventory_item_id":item.id,"item":item.name,"category":item.category,"unit":item.unit,
            "opening_quantity":opening,"stock_received":round(q({"stock in","receive","received","purchase","addition"}),3),
            "approved_task_usage":round(approved_usage,3),"customer_sales":round(q({"sale"}),3),"sales_returns":round(q({"sale void","returned"}),3),"manual_adjustments":round(q({"adjustment","manual adjustment"}),3),
            "reversals":round(q({"reversal","void reversal"}),3),"waste":round(q({"waste","damaged"}),3),
            "expired_quantity":round(q({"expired","expiration"}),3),"closing_quantity":round(closing,3),
            "unit_cost":_num(item.cost) if item.cost is not None else "Not Recorded",
            "movement_records":len(ms),"resource_usage_records":len(us),
        })
    snapshot["operational_rows"]=rows
    snapshot["sections"]={"stock_movements":[{"record_id":m.id,"item_id":m.inventory_item_id,"date":m.adjustment_date.isoformat(),"type":m.adjustment_type,"quantity":_num(m.quantity),"previous":_num(m.previous_quantity),"new":_num(m.new_quantity),"reason":m.reason,"reference":_display(m.reference)} for m in moves],"approved_resource_usage":[{"usage_id":u.id,"item_id":u.inventory_item_id,"date":u.usage_date.isoformat(),"quantity":_num(u.quantity),"unit":u.unit,"module":u.module,"task_id":u.activity_id,"is_voided":u.is_voided} for u in usages if not u.is_voided and u.task_posting_active]}
    snapshot["metrics"]={"items":len(rows),"stock_movements":len(moves),"approved_task_usage_records":sum(1 for u in usages if not u.is_voided and u.task_posting_active),"voided_usage_records":sum(1 for u in usages if u.is_voided)}
    return snapshot


def _build_production_sales(db: Session,start:date,end:date,filters:dict[str,Any])->dict[str,Any]:
    snapshot=_base("Production and Sales Summary",start,end,filters)
    crop_id=_filter_id(filters,"crop_id"); livestock_id=_filter_id(filters,"livestock_id")
    production_stmt=select(LivestockProductionRecord).where(LivestockProductionRecord.record_date>=start,LivestockProductionRecord.record_date<=end)
    sales_stmt=select(LivestockSale).where(LivestockSale.sale_date>=start,LivestockSale.sale_date<=end)
    if crop_id:
        production_stmt=production_stmt.where(LivestockProductionRecord.crop_id==crop_id)
    if livestock_id:
        production_stmt=production_stmt.where(LivestockProductionRecord.livestock_id==livestock_id)
    production=list(db.scalars(production_stmt).all()); sales=list(db.scalars(sales_stmt).all())
    sale_ids=[s.id for s in sales]
    item_records = _rows_for_ids(db, sale_ids, LivestockSaleItem, LivestockSaleItem.sale_id)
    item_records.sort(key=lambda item: (item.sale_id, item.line_number))
    items_by_sale=defaultdict(list)
    for item in item_records: items_by_sale[item.sale_id].append(item)
    if crop_id:
        sales=[s for s in sales if s.crop_id==crop_id or any(i.crop_id==crop_id for i in items_by_sale.get(s.id,[]))]
    if livestock_id:
        sales=[s for s in sales if s.livestock_id==livestock_id or any(i.livestock_id==livestock_id for i in items_by_sale.get(s.id,[]))]
    source_ids = {p.crop_id for p in production if p.crop_id} | {s.crop_id for s in sales if s.crop_id} | {i.crop_id for s in sales for i in items_by_sale.get(s.id, []) if i.crop_id}
    crops = {c.id: c for c in _rows_for_ids(db, source_ids, Crop, Crop.id)}
    live_ids = {p.livestock_id for p in production if p.livestock_id} | {s.livestock_id for s in sales if s.livestock_id} | {i.livestock_id for s in sales for i in items_by_sale.get(s.id, []) if i.livestock_id}
    livestock = {animal.id: animal for animal in _rows_for_ids(db, live_ids, Livestock, Livestock.id)}
    inventory_ids = {i.inventory_item_id for s in sales for i in items_by_sale.get(s.id, []) if i.inventory_item_id}
    inventory = {i.id: i for i in _rows_for_ids(db, inventory_ids, InventoryItem, InventoryItem.id)}
    production_by_id={p.id:p for p in production}
    rows=[]
    for sale in sales:
        if not _status_matches(filters,"Voided" if sale.is_voided else sale.payment_status): continue
        invoice_items=items_by_sale.get(sale.id,[])
        if not invoice_items:
            source=(crops.get(sale.crop_id).name if sale.crop_id and crops.get(sale.crop_id) else livestock.get(sale.livestock_id).record_name if sale.livestock_id and livestock.get(sale.livestock_id) else sale.source_type)
            invoice_items=[type("LegacySaleLine",(),{"line_number":1,"product_type":sale.product_type,"source_name_snapshot":source,"source_type":sale.source_type,"quantity":sale.quantity,"unit":sale.unit,"unit_price":sale.unit_price,"line_total":sale.total_amount,"production_record_id":sale.production_record_id,"item_kind":sale.sale_type,"inventory_item_id":None})()]
        invoice_total=_num(sale.total_amount)
        for item in invoice_items:
            related=production_by_id.get(item.production_record_id) if item.production_record_id else None
            produced=_num(related.quantity) if related else None
            line_total=_num(item.line_total)
            paid_share=_num(sale.amount_paid)*(line_total/invoice_total) if invoice_total>0 else 0
            source=item.source_name_snapshot
            if item.inventory_item_id and item.inventory_item_id in inventory: source=inventory[item.inventory_item_id].name
            rows.append({"sale_id":sale.id,"sale_code":sale.sale_code,"line_number":item.line_number,"item_kind":item.item_kind,"product":item.product_type,"source":source,"source_type":item.source_type,"quantity_produced":produced if produced is not None else "Not Recorded","quantity_sold":_num(item.quantity),"remaining_quantity":round(produced-_num(item.quantity),3) if produced is not None else "Not Recorded","unit":item.unit,"buyer":_display(sale.buyer_name),"sale_date":sale.sale_date.isoformat(),"revenue":line_total,"amount_paid":round(paid_share,2),"payment_status":"Voided" if sale.is_voided else sale.payment_status})
    snapshot["operational_rows"]=rows
    snapshot["sections"]={"production_records":[{"production_id":p.id,"source_type":p.source_type,"crop_id":p.crop_id,"livestock_id":p.livestock_id,"product":p.output_type,"date":p.record_date.isoformat(),"quantity":_display(p.quantity),"unit":p.unit,"loss_quantity":_display(p.loss_quantity),"farm_use_quantity":_display(p.farm_use_quantity),"reserved_quantity":_display(p.reserved_quantity)} for p in production],"sales":[dict(r) for r in rows]}
    valid_sales=[s for s in sales if not s.is_voided]
    valid_sale_ids={s.id for s in valid_sales}
    valid_rows=[r for r in rows if r["sale_id"] in valid_sale_ids]
    snapshot["metrics"]={"production_records":len(production),"sales_records":len(valid_sales),"sale_line_items":len(valid_rows),"quantity_sold":round(sum(_num(r["quantity_sold"]) for r in valid_rows),3) if valid_rows else "No Data","revenue":round(sum(_num(s.total_amount) for s in valid_sales),2) if valid_sales else "No Data","outstanding":round(sum(_num(s.balance_due) for s in valid_sales),2) if valid_sales else "No Data","voided_records":sum(1 for s in sales if s.is_voided)}
    return snapshot


def _build_audit(db:Session,start:date,end:date,filters:dict[str,Any])->dict[str,Any]:
    snapshot=_base("Generated Report History and Audit Trail",start,end,filters)
    reports=list(db.scalars(select(FarmReport).where(FarmReport.generated_date>=start,FarmReport.generated_date<=end).order_by(FarmReport.created_at.desc())).all())
    audits=list(db.scalars(select(AuditLog).where(AuditLog.created_at>=datetime.combine(start,time.min),AuditLog.created_at<=datetime.combine(end,time.max)).order_by(AuditLog.created_at.desc())).all())
    report_rows=[]
    for r in reports:
        if not _source_matches(filters,r.is_automatic) or not _status_matches(filters,r.status): continue
        report_rows.append({"report_id":r.id,"report_code":r.report_code,"title":r.title,"report_type":r.report_type,"period":f"{r.start_date} to {r.end_date}","source":"System" if r.is_automatic else "Manual","status":r.status,"revision":r.revision_number,"generated_by":r.prepared_by,"generated_time":_dt(r.created_at),"updated_time":_dt(r.updated_at)})
    audit_rows=[{"audit_id":a.id,"module":a.module,"action":a.action,"record":_display(a.record_name),"entity_id":_display(a.entity_id),"actor":a.actor_name,"created_at":_dt(a.created_at),"details":_display(a.details)} for a in audits if a.module.lower() in {"report","reports","system"}]
    snapshot["operational_rows"]=report_rows
    snapshot["sections"]={"report_audit_events":audit_rows}
    snapshot["metrics"]={"reports_generated":len(report_rows),"system_reports":sum(1 for r in report_rows if r["source"]=="System"),"manual_reports":sum(1 for r in report_rows if r["source"]=="Manual"),"audit_events":len(audit_rows),"revisions":sum(1 for r in report_rows if r["revision"]>1)}
    return snapshot


def build_operational_report_snapshot(db:Session,report_type:str,start_date:date,end_date:date,filters:dict[str,Any]|None=None)->dict[str,Any]:
    filters={key:value for key,value in dict(filters or {}).items() if value not in (None,"")}
    if report_type=="Daily Attendance Report": snapshot=_build_daily_attendance(db,start_date,end_date,filters,False)
    elif report_type=="Weekly Attendance Summary": snapshot=_build_daily_attendance(db,start_date,end_date,filters,True)
    elif report_type=="Task Completion and Employee Performance": snapshot=_build_task_performance(db,start_date,end_date,filters)
    elif report_type=="Task Coverage and Reassignment": snapshot=_build_coverage(db,start_date,end_date,filters)
    elif report_type=="Care Protocol Compliance": snapshot=_build_compliance(db,start_date,end_date,filters)
    elif report_type=="Crop Yield and Input Usage": snapshot=_build_crop(db,start_date,end_date,filters)
    elif report_type=="Livestock Feeding, Growth, and Health": snapshot=_build_livestock(db,start_date,end_date,filters)
    elif report_type=="Inventory Movement and Resource Usage": snapshot=_build_inventory(db,start_date,end_date,filters)
    elif report_type=="Production and Sales Summary": snapshot=_build_production_sales(db,start_date,end_date,filters)
    elif report_type=="Generated Report History and Audit Trail": snapshot=_build_audit(db,start_date,end_date,filters)
    else: raise ValueError(f"Unsupported operational report type: {report_type}")
    snapshot["source_fingerprint"]=_fingerprint(snapshot)
    return snapshot
