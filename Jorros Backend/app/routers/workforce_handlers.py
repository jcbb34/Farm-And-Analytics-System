from __future__ import annotations
from app.routers.archives import ArchiveRequest
from app.services.archive_service import change_archive_state, permanent_delete

from app.services.personal_details import apply_personal_details
from app.services.void_authorization import require_void_administrator

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated
import csv
import io
import json
import mimetypes
import re

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.resource_monitoring import monitoring_context, validate_task_observation, post_approved_observation, MONITORING_TYPES
from app.core.database import get_db
from app.services.vaccination_summary import lock_vaccination_parent, update_vaccination_summary
from app.core.config import settings
from app.core.farm_time import farm_now_naive, farm_today, farm_timezone_name
from app.core.dependencies import has_permission, is_task_only_user, require_permission
from app.core.security import hash_password
from app.models import (
    AuditLog,
    CareTemplate,
    CareTemplateStep,
    Crop,
    Employee,
    EmployeePosition,
    EmployeeWorkSchedule,
    EmployeeWorkScheduleDay,
    FarmPosition,
    FarmActivity,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    LivestockFeedingRecord,
    LivestockVaccinationRecord,
    ResourceUsage,
    Role,
    StaffAttendance,
    AttendanceSettings,
    StaffLeave,
    TaskLeaveCoverage,
    StaffShift,
    TaskAssignmentHistory,
    TaskSubmission,
    TaskEvidence,
    User,
)
from app.routers.auth import get_current_user
from app.schemas.workforce import (
    AttendanceResponse,
    AttendanceBulkResponse,
    AttendanceActionRequest,
    AttendanceCorrectionRequest,
    AttendanceSettingsResponse,
    AttendanceSettingsUpdate,
    AttendanceStatusRequest,
    AvailabilityDayResponse,
    AttendanceUpsert,
    CareTemplateCreate,
    CareTemplateUpdate,
    CareTemplateResponse,
    CareTemplateStepResponse,
    CareProtocolPublishRequest,
    CareProtocolCopyRequest,
    CareProtocolImportRequest,
    EmployeeArchiveRequest,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeSelfProfileResponse,
    EmployeeStatusUpdate,
    EmployeeWorkAssignmentsResponse,
    EmployeeUpdate,
    WeeklyScheduleInput,
    WeeklyScheduleResponse,
    FarmPositionResponse,
    GenerateCareTasksRequest,
    ResourceWorkScheduleCreate,
    LeaveCreate,
    LeaveDecisionRequest,
    LeaveCancelRequest,
    LeaveReviewResponse,
    LeaveCoveringCandidateResponse,
    LeaveRecalculationResponse,
    LeaveRequestCreate,
    LeaveResponse,
    ShiftCreate,
    ShiftResponse,
    ShiftUpdate,
    CalendarConfigResponse,
    TaskAssignmentHistoryResponse,
    MyTasksSummaryResponse,
    TaskAssignmentUpdate,
    TaskCreate,
    TaskResponse,
    TaskPageResponse,
    TaskReviewRequest,
    TaskReviewReportResponse,
    TaskReviewResourceResponse,
    TaskReviewMovementResponse,
    TaskVoidRequest,
    TaskStartRequest,
    TaskSubmitRequest,
    TaskSubmissionResponse,
    TaskEvidenceUploadResponse,
)
from app.services.db_concurrency import acquire_transaction_lock
from app.services.code_counter_service import next_record_code
from app.services.work_schedule_service import validate_roster_schedule_choice
from app.services.query_batching import scalar_rows_in_batches
from app.services.workforce.assignments import (
    assignment_is_protected,
    recalculate_employee_tasks,
    recalculate_task_reassignment,
    record_assignment_change,
)
from app.services.workforce.attendance_leave import (
    AttendanceError,
    COVERAGE_ACTIVE_STATUSES,
    COVERAGE_ASSIGNMENT_SOURCE,
    MANAGER_ASSISTED,
    REST_COVERAGE_SOURCE,
    SELF_SERVICE,
    affected_tasks_for_leave,
    apply_schedule_aware_assignment,
    approve_leave_with_coverage,
    attendance_response_dict,
    check_in as attendance_check_in,
    check_out as attendance_check_out,
    covering_employee_candidates,
    coverage_display,
    correct_attendance,
    current_schedule,
    employee_schedule_metadata,
    get_or_create_attendance_settings,
    leave_overlap_context,
    mark_leave_coverage_manager_override,
    reconcile_employee_future_tasks,
    reconcile_expired_leave_coverage,
    replace_employee_schedule,
    resolve_availability_range,
    resolve_employee_availability,
    schedule_response,
    set_confirmed_status,
)
from app.services.workforce.care_protocols import (
    generate_care_tasks_for_target,
    reconcile_same_template_future_schedule,
    resolve_future_pending_care_tasks,
    validate_care_template_for_target,
)
from app.services.workforce.employees import next_employee_code, next_user_code
from app.services.workforce.evidence import (
    EvidenceValidationError,
    create_task_evidence,
    evidence_thumbnail_url,
    evidence_url,
    get_evidence_storage,
)
from app.services.workforce.resource_posting import create_usage, update_usage, void_usage
from app.services.workforce.task_lifecycle import (
    normalize_idempotency_key,
    record_harvest,
    request_fingerprint,
    sanitize_shared_device_task_response,
)
from app.services.crop_harvest_service import harvest_approval_blocker

router = APIRouter(prefix="/api/v1/workforce", tags=["Workforce and Tasks"])




# Every workforce endpoint is listed here intentionally.  Endpoint functions call
# _require_workforce_access before loading private records so forbidden callers
# receive 403 without learning whether another employee record exists.
WORKFORCE_PERMISSION_MATRIX = {
    "upload_task_evidence": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "view_task_evidence": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "view_task_evidence_thumbnail": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "view_legacy_workforce_evidence": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "get_my_employee_profile": {"any_of": ("workforce:submit",)},
    "list_farm_positions": {"any_of": ("workforce:manage",)},
    "list_employees": {"any_of": ("workforce:manage",)},
    "repair_employee_account_links": {"any_of": ("workforce:manage",)},
    "get_employee_work_assignments": {"any_of": ("workforce:manage",)},
    "get_employee_work_schedule": {"any_of": ("workforce:manage",)},
    "update_employee_work_schedule": {"any_of": ("workforce:manage",)},
    "availability_range": {"any_of": ("workforce:attendance", "workforce:manage")},
    "create_employee": {"any_of": ("workforce:manage",)},
    "update_employee": {"any_of": ("workforce:manage",)},
    "change_employee_status": {"any_of": ("workforce:manage",)},
    "archive_employee": {"any_of": ("workforce:manage",)},
    "restore_employee": {"any_of": ("workforce:manage",)},
    "list_tasks": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "list_tasks_page": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "get_task_detail": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "task_management_summary": {"any_of": ("workforce:submit", "workforce:manage", "workforce:review")},
    "my_tasks_page": {"any_of": ("workforce:submit",)},
    "my_tasks": {"any_of": ("workforce:submit",)},
    "my_tasks_summary": {"any_of": ("workforce:submit",)},
    "create_task": {"any_of": ("workforce:manage",)},
    "schedule_resource_work": {"any_of": ("workforce:manage",)},
    "update_task_assignment": {"any_of": ("workforce:manage",)},
    "task_assignment_history": {"any_of": ("workforce:manage",)},
    "start_task": {"any_of": ("workforce:submit", "workforce:manage")},
    "submit_task": {"any_of": ("workforce:submit", "workforce:manage")},
    "get_task_review_report": {"any_of": ("workforce:review", "workforce:manage")},
    "review_task": {"any_of": ("workforce:review", "workforce:manage")},
    "void_task": {"administrator_only": True},
    "resolve_task": {"any_of": ("workforce:manage",)},
    "get_calendar_config": {"any_of": ("workforce:submit", "workforce:attendance", "workforce:manage")},
    "list_attendance": {"any_of": ("workforce:attendance", "workforce:manage")},
    "upsert_attendance": {"any_of": ("workforce:attendance", "workforce:manage")},
    "my_attendance_today": {"any_of": ("workforce:submit",)},
    "my_attendance_history": {"any_of": ("workforce:submit",)},
    "my_attendance_check_in": {"any_of": ("workforce:submit",)},
    "my_attendance_check_out": {"any_of": ("workforce:submit",)},
    "manager_attendance_check_in": {"any_of": ("workforce:attendance", "workforce:manage")},
    "manager_attendance_check_out": {"any_of": ("workforce:attendance", "workforce:manage")},
    "manager_attendance_status": {"any_of": ("workforce:attendance", "workforce:manage")},
    "manager_attendance_correction": {"any_of": ("workforce:attendance", "workforce:manage")},
    "bulk_mark_scheduled_present": {"any_of": ("workforce:attendance", "workforce:manage")},
    "get_attendance_settings": {"any_of": ("workforce:attendance", "workforce:manage")},
    "update_attendance_settings": {"any_of": ("workforce:manage",)},
    "list_leave": {"any_of": ("workforce:attendance", "workforce:manage")},
    "my_leave_requests": {"any_of": ("workforce:submit",)},
    "review_leave_request": {"any_of": ("workforce:attendance", "workforce:manage")},
    "create_leave": {"any_of": ("workforce:attendance", "workforce:manage")},
    "request_my_leave": {"any_of": ("workforce:submit",)},
    "decide_leave": {"any_of": ("workforce:attendance", "workforce:manage")},
    "cancel_leave": {"any_of": ("workforce:submit", "workforce:attendance", "workforce:manage")},
    "recalculate_leave_coverage": {"any_of": ("workforce:attendance", "workforce:manage")},
    "list_shifts": {"any_of": ("workforce:attendance", "workforce:manage")},
    "create_shift": {"any_of": ("workforce:attendance", "workforce:manage")},
    "update_shift": {"any_of": ("workforce:attendance", "workforce:manage")},
    "cancel_shift": {"any_of": ("workforce:attendance", "workforce:manage")},
    "staff_calendar": {"any_of": ("workforce:attendance", "workforce:manage")},
    "my_schedule": {"any_of": ("workforce:submit",)},
    "list_care_templates": {"any_of": ("workforce:manage",)},
    "create_care_template": {"administrator_only": True},
    "update_care_template": {"administrator_only": True},
    "publish_care_template": {"administrator_only": True},
    "copy_care_template": {"administrator_only": True},
    "deactivate_care_template": {"administrator_only": True},
    "import_care_protocols": {"administrator_only": True},
    "import_care_protocols_csv": {"administrator_only": True},
    "match_care_protocols": {"any_of": ("workforce:manage",)},
    "generate_care_tasks": {"any_of": ("workforce:manage",)},
}


def _require_workforce_access(current_user: User, endpoint_name: str) -> None:
    policy = WORKFORCE_PERMISSION_MATRIX[endpoint_name]
    if policy.get("administrator_only"):
        if not has_permission(current_user, "*"):
            raise HTTPException(status_code=403, detail="Administrator access is required.")
        return
    required = tuple(policy.get("any_of", ()))
    if required and not any(has_permission(current_user, permission) for permission in required):
        raise HTTPException(
            status_code=403,
            detail=f"Workforce permission required: {' or '.join(required)}.",
        )


def _can_view_all_tasks(current_user: User) -> bool:
    return (
        has_permission(current_user, "workforce:manage")
        or has_permission(current_user, "workforce:review")
        or has_permission(current_user, "*")
    )


LEGACY_EVIDENCE_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "workforce_evidence"
NEW_EVIDENCE_URL_RE = re.compile(r"^/workforce/evidence-assets/([0-9a-f]{32})$")


def _assert_evidence_task_access(db: Session, task: FarmActivity, current_user: User) -> Employee | None:
    if _manager(current_user) or _reviewer(current_user):
        return _employee_for_user(db, current_user)
    return _assert_task_access(db, task, current_user)


def _evidence_or_404(db: Session, public_id: str) -> TaskEvidence:
    evidence = db.scalar(select(TaskEvidence).where(TaskEvidence.public_id == public_id))
    if evidence is None or evidence.status == "Deleted":
        raise HTTPException(status_code=404, detail="Evidence photo not found.")
    return evidence


def _evidence_file_response(evidence: TaskEvidence, *, thumbnail: bool = False):
    identifier = evidence.thumbnail_storage_identifier if thumbnail else evidence.storage_identifier
    try:
        target = get_evidence_storage().path_for_response(identifier)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Evidence photo not found.")
    response = FileResponse(
        target,
        media_type=evidence.content_type,
        filename="evidence-thumbnail" if thumbnail else "evidence-image",
        content_disposition_type="inline",
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.post(
    "/tasks/{task_id}/evidence",
    response_model=TaskEvidenceUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_task_evidence(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "upload_task_evidence")
    task = _task_or_404(db, task_id)
    _assert_evidence_task_access(db, task, current_user)
    if task.status not in {"Pending", "In Progress", "Returned"}:
        raise HTTPException(status_code=400, detail="Evidence can only be uploaded while the task is open for work submission.")

    payload = await file.read(settings.workforce_evidence_max_bytes + 1)
    try:
        acquire_transaction_lock(db, f"workforce:evidence:task:{task.id}")
        evidence = create_task_evidence(
            db,
            task_id=task.id,
            uploader_user_id=current_user.id,
            original_filename=file.filename,
            browser_content_type=file.content_type,
            payload=payload,
        )
        db.commit()
        db.refresh(evidence)
    except EvidenceValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return TaskEvidenceUploadResponse(
        evidence_id=evidence.public_id,
        evidence_url=evidence_url(evidence.public_id),
        thumbnail_url=evidence_thumbnail_url(evidence.public_id),
        file_name=evidence.original_display_name,
        content_type=evidence.content_type,
        size_bytes=evidence.size_bytes,
        width=evidence.width,
        height=evidence.height,
        expires_at=evidence.expires_at,
    )


@router.get("/evidence-assets/{public_id}")
def view_task_evidence(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "view_task_evidence")
    evidence = _evidence_or_404(db, public_id)
    task = _task_or_404(db, evidence.activity_id)
    _assert_evidence_task_access(db, task, current_user)
    return _evidence_file_response(evidence)


@router.get("/evidence-assets/{public_id}/thumbnail")
def view_task_evidence_thumbnail(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "view_task_evidence_thumbnail")
    evidence = _evidence_or_404(db, public_id)
    task = _task_or_404(db, evidence.activity_id)
    _assert_evidence_task_access(db, task, current_user)
    return _evidence_file_response(evidence, thumbnail=True)


@router.delete("/evidence-assets/{public_id}")
def delete_task_evidence(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "delete_task_evidence")
    evidence = _evidence_or_404(db, public_id)
    task = _task_or_404(db, evidence.activity_id)
    _assert_evidence_task_access(db, task, current_user)

    # Can only delete Temporary evidence that hasn't been submitted
    if evidence.submission_id is not None:
        raise HTTPException(status_code=400, detail="Cannot delete evidence that has already been submitted with a task.")
    if evidence.status != "Temporary":
        raise HTTPException(status_code=400, detail="Only temporary (unsubmitted) evidence can be deleted.")

    # Delete from storage
    from app.services.evidence_storage import get_evidence_storage
    storage = get_evidence_storage()
    storage.delete(evidence.storage_identifier)
    storage.delete(evidence.thumbnail_storage_identifier)

    # Mark as deleted in DB
    evidence.status = "Deleted"
    evidence.deleted_at = datetime.now()
    db.commit()

    return {"success": True, "message": "Evidence photo deleted."}


@router.get("/evidence/{filename}")
def view_legacy_workforce_evidence(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read-only compatibility for evidence already stored by older releases."""
    _require_workforce_access(current_user, "view_legacy_workforce_evidence")
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=404, detail="Evidence photo not found.")

    legacy_url = f"/workforce/evidence/{safe_name}"
    submission = db.scalar(
        select(TaskSubmission).where(TaskSubmission.evidence_url == legacy_url)
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Evidence photo not found.")
    task = _task_or_404(db, submission.activity_id)
    _assert_evidence_task_access(db, task, current_user)

    target = LEGACY_EVIDENCE_UPLOAD_DIR / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Evidence photo not found.")
    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    response = FileResponse(target, media_type=media_type, filename="legacy-evidence", content_disposition_type="inline")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _manager(current_user: User) -> bool:
    return has_permission(current_user, "workforce:manage") or has_permission(current_user, "*")


def _reviewer(current_user: User) -> bool:
    return has_permission(current_user, "workforce:review") or _manager(current_user)


def _require_manager(current_user: User) -> None:
    if not _manager(current_user):
        raise HTTPException(status_code=403, detail="Manager or administrator access is required.")


def _employee_for_user(db: Session, user: User) -> Employee | None:
    rows = list(
        db.scalars(
            select(Employee).where(
                Employee.login_user_id == user.id,
                Employee.is_archived == False,
                Employee.employment_status == "Active",
            ).order_by(Employee.id)
        ).all()
    )
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail="Account link problem: this login is linked to more than one active employee profile. Ask an administrator to repair the account link.",
        )
    return rows[0] if rows else None


def _employee_for_user_or_error(db: Session, user: User) -> Employee:
    employee = _employee_for_user(db, user)
    if employee is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Your login account is not linked to one active employee profile. "
                "Ask an administrator or manager to link the correct employee account before opening My Tasks."
            ),
        )
    return employee


def _employee_profile_for_user_or_error(db: Session, user: User) -> Employee:
    """Resolve a non-archived employee link even when employment is inactive.

    Employee-only task endpoints deliberately require an active profile, while
    workflows such as leave validation need the linked profile first so they can
    return the established inactive-employee validation message.
    """
    rows = list(
        db.scalars(
            select(Employee).where(
                Employee.login_user_id == user.id,
                Employee.is_archived == False,
            ).order_by(Employee.id)
        ).all()
    )
    if len(rows) > 1:
        raise HTTPException(
            status_code=409,
            detail="Account link problem: this login is linked to more than one employee profile.",
        )
    if not rows:
        raise HTTPException(
            status_code=409,
            detail="Your login account is not linked to an employee profile.",
        )
    return rows[0]


def _candidate_login_users_for_employee(db: Session, employee: Employee) -> list[User]:
    normalized_email = str(employee.email or "").strip().lower()
    if not normalized_email:
        return []
    users = list(
        db.scalars(
            select(User).where(func.lower(User.email) == normalized_email).order_by(User.id)
        ).all()
    )
    candidates: list[User] = []
    for user in users:
        other_link = db.scalar(
            select(Employee).where(
                Employee.login_user_id == user.id,
                Employee.id != employee.id,
                Employee.is_archived == False,
            )
        )
        if other_link is None:
            candidates.append(user)
    return candidates


def _employee_account_state(db: Session, employee: Employee) -> dict:
    if employee.login_user_id is None:
        candidates = _candidate_login_users_for_employee(db, employee)
        if len(candidates) > 1:
            return {
                "account_status": "Link Problem",
                "portal_assignment_ready": False,
                "account_repair_available": False,
                "account_issue": "Multiple login accounts match this employee email; an administrator must choose the correct account.",
                "login_user": None,
            }
        candidate = candidates[0] if len(candidates) == 1 else None
        if candidate is not None and (candidate.status != "Active" or candidate.role is None or not candidate.role.is_active):
            return {
                "account_status": "Inactive Account",
                "portal_assignment_ready": False,
                "account_repair_available": False,
                "account_issue": f"A matching login ({candidate.username}) exists but is inactive.",
                "login_user": None,
            }
        if candidate is not None and not is_task_only_user(candidate):
            return {
                "account_status": "Link Problem",
                "portal_assignment_ready": False,
                "account_repair_available": False,
                "account_issue": f"A matching login ({candidate.username}) exists but is not an Employee task account.",
                "login_user": None,
            }
        return {
            "account_status": "No Login Account",
            "portal_assignment_ready": False,
            "account_repair_available": bool(candidate),
            "account_issue": (
                f"A unique Employee login candidate ({candidate.username}) can be linked by the account repair action."
                if candidate else
                "Create or link an Employee login account before assigning portal-based work."
            ),
            "login_user": None,
        }

    login_user = db.get(User, employee.login_user_id)
    if login_user is None:
        return {
            "account_status": "Link Problem",
            "portal_assignment_ready": False,
            "account_repair_available": False,
            "account_issue": "The employee points to a login account that no longer exists.",
            "login_user": None,
        }

    active_links = list(
        db.scalars(
            select(Employee).where(
                Employee.login_user_id == login_user.id,
                Employee.is_archived == False,
            ).order_by(Employee.id)
        ).all()
    )
    if len(active_links) != 1 or active_links[0].id != employee.id:
        return {
            "account_status": "Link Problem",
            "portal_assignment_ready": False,
            "account_repair_available": False,
            "account_issue": "This login account is linked inconsistently to employee records.",
            "login_user": login_user,
        }

    if login_user.status != "Active" or login_user.role is None or not login_user.role.is_active:
        return {
            "account_status": "Inactive Account",
            "portal_assignment_ready": False,
            "account_repair_available": False,
            "account_issue": "The linked login account or its role is inactive.",
            "login_user": login_user,
        }

    if not has_permission(login_user, "workforce:submit"):
        return {
            "account_status": "Link Problem",
            "portal_assignment_ready": False,
            "account_repair_available": False,
            "account_issue": "The linked login account does not have Employee task permissions.",
            "login_user": login_user,
        }

    return {
        "account_status": "Account Linked",
        "portal_assignment_ready": True,
        "account_repair_available": False,
        "account_issue": None,
        "login_user": login_user,
    }


def _require_portal_assignment_account(db: Session, employee: Employee) -> None:
    state = _employee_account_state(db, employee)
    if state["portal_assignment_ready"]:
        return
    status_label = state["account_status"]
    detail = state["account_issue"] or "Link or create the employee login account first."
    raise HTTPException(
        status_code=409,
        detail=f"{employee.full_name} cannot receive portal-based work: {status_label}. {detail}",
    )


def _require_assignment_availability(
    db: Session,
    employee: Employee,
    work_date: date,
    *,
    allow_override: bool,
) -> None:
    availability = resolve_employee_availability(
        db, employee.id, work_date, allow_future_attendance=True
    )
    if availability.available or allow_override:
        return
    raise HTTPException(
        status_code=409,
        detail=(
            f"{employee.full_name} is unavailable on {work_date.isoformat()}: {availability.reason}. "
            "Review the availability warning and use an authorized override only when the manager intends to keep this assignment."
        ),
    )


def _employee_or_404(db: Session, employee_id: int, *, active_only: bool = True) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None or (active_only and employee.is_archived):
        raise HTTPException(status_code=404, detail="Employee profile not found.")
    return employee


def _assignable_employee_or_404(db: Session, employee_id: int) -> Employee:
    employee = _employee_or_404(db, employee_id)
    if employee.employment_status != "Active":
        raise HTTPException(
            status_code=400,
            detail=f"{employee.full_name} is {employee.employment_status.lower()} and cannot receive new assignments.",
        )
    return employee


def _task_or_404(db: Session, task_id: int) -> FarmActivity:
    task = db.get(FarmActivity, task_id)
    if task is None or task.is_archived:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


def _task_locked_or_404(db: Session, task_id: int) -> FarmActivity:
    statement = select(FarmActivity).where(FarmActivity.id == task_id)
    statement = statement.with_hint(
        FarmActivity,
        "WITH (UPDLOCK, ROWLOCK)",
        dialect_name="mssql",
    )
    try:
        statement = statement.with_for_update()
    except Exception:
        pass
    task = db.scalar(statement)
    if task is None or task.is_archived:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


def _active_task_resource_usage(db: Session, task_id: int) -> ResourceUsage | None:
    usage = db.scalar(
        select(ResourceUsage).where(
            ResourceUsage.activity_id == task_id,
            ResourceUsage.task_posting_active == True,
            ResourceUsage.is_voided == False,
        ).order_by(ResourceUsage.id.desc())
    )
    if usage is not None:
        return usage

    # Compatibility for task usage rows created before inventory posting. The migration
    # marks the newest active row, but this fallback keeps direct/test databases
    # safe if they contain a legacy row created without the migration data step.
    legacy = db.scalar(
        select(ResourceUsage).where(
            ResourceUsage.activity_id == task_id,
            ResourceUsage.is_voided == False,
        ).order_by(ResourceUsage.id.desc())
    )
    if legacy is not None:
        legacy.task_posting_active = True
        db.flush()
    return legacy


def _existing_idempotent_submission(
    db: Session,
    *,
    key: str | None,
    task_id: int,
    request_hash: str,
    user_id: int | None,
) -> TaskSubmission | None:
    if key is None:
        return None
    existing = db.scalar(
        select(TaskSubmission).where(TaskSubmission.idempotency_key == key)
    )
    if existing is None:
        return None
    if (
        existing.activity_id != task_id
        or existing.request_hash != request_hash
        or existing.recorded_by_user_id != user_id
    ):
        raise HTTPException(
            status_code=409,
            detail="This Idempotency-Key was already used for a different task submission.",
        )
    return existing


def _assert_task_access(db: Session, task: FarmActivity, current_user: User) -> Employee | None:
    if has_permission(current_user, "workforce:manage") or has_permission(current_user, "*"):
        return _employee_for_user(db, current_user)
    employee = _employee_for_user(db, current_user)
    if employee is None or task.assigned_employee_id != employee.id:
        # Do not reveal whether another employee's private task exists.
        raise HTTPException(status_code=404, detail="Task not found.")
    return employee


def _parse_clock(value: str | None, default: time | None = None) -> time | None:
    if not value:
        return default
    try:
        parts = [int(part) for part in str(value).split(":")[:2]]
        return time(parts[0], parts[1])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid task time. Use HH:MM.") from exc


def _next_code(db: Session, model, prefix: str) -> str:
    if prefix == "EMP":
        return next_employee_code(db)
    if prefix == "USR":
        return next_user_code(db)
    namespace_by_prefix = {
        "ACT": "activity",
        "CARE": "care-template",
        "PROT": "care-protocol-family",
    }
    code_column_by_prefix = {
        "ACT": FarmActivity.activity_code,
        "CARE": CareTemplate.template_code,
        "PROT": CareTemplate.protocol_family_code,
    }
    return next_record_code(
        db,
        namespace=namespace_by_prefix.get(prefix, prefix.lower()),
        prefix=prefix,
        seed_model=model,
        code_column=code_column_by_prefix.get(prefix),
    )


def _employee_role_or_404(db: Session) -> Role:
    role = db.scalar(select(Role).where(Role.name == "Employee"))
    if role is None or not role.is_active:
        raise HTTPException(status_code=400, detail="The Employee system role is missing or inactive.")
    return role


def _normalize_login_username(value: str) -> str:
    return str(value or "").strip().lower()


def _assert_employee_login_identity_available(
    db: Session,
    *,
    username: str | None = None,
    email: str | None = None,
    exclude_user_id: int | None = None,
) -> None:
    if username:
        stmt = select(User).where(func.lower(User.username) == _normalize_login_username(username))
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        if db.scalar(stmt):
            raise HTTPException(status_code=409, detail="Username already exists.")
    if email:
        normalized_email = str(email).strip().lower()
        stmt = select(User).where(func.lower(User.email) == normalized_email)
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        if db.scalar(stmt):
            raise HTTPException(status_code=409, detail="Email address already exists.")


def _create_employee_login_user(
    db: Session,
    *,
    full_name: str,
    username: str,
    password: str,
    email: str | None,
    contact_number: str | None,
    position: str | None,
    employment_status: str,
    personal_details: dict | None = None,
) -> User:
    normalized_username = _normalize_login_username(username)
    normalized_email = str(email).strip().lower() if email else None
    _assert_employee_login_identity_available(
        db, username=normalized_username, email=normalized_email
    )
    role = _employee_role_or_404(db)
    user = User(
        user_code=_next_code(db, User, "USR"),
        full_name=full_name.strip(),
        personal_details=personal_details,
        username=normalized_username,
        email=normalized_email,
        contact_number=contact_number,
        position=position,
        password_hash=hash_password(password),
        status="Active" if employment_status == "Active" else "Disabled",
        role_id=role.id,
    )
    db.add(user)
    db.flush()
    return user


def _sync_linked_employee_login(
    db: Session,
    employee: Employee,
    *,
    username: str | None = None,
    password: str | None = None,
) -> User | None:
    if not employee.login_user_id:
        return None
    user = db.get(User, employee.login_user_id)
    if user is None:
        employee.login_user_id = None
        return None
    # Elevated administrative/manager identities may also have an employee
    # profile for task assignment, but their system-account identity/status is
    # not governed by the employee HR record.
    if not is_task_only_user(user):
        return user
    if username is not None:
        normalized_username = _normalize_login_username(username)
        _assert_employee_login_identity_available(
            db, username=normalized_username, exclude_user_id=user.id
        )
        user.username = normalized_username
    normalized_email = str(employee.email).strip().lower() if employee.email else None
    _assert_employee_login_identity_available(
        db, email=normalized_email, exclude_user_id=user.id
    )
    user.personal_details = employee.personal_details
    user.full_name = employee.full_name
    user.email = normalized_email
    user.contact_number = employee.contact_number
    user.position = employee.position
    user.status = "Active" if employee.employment_status == "Active" and not employee.is_archived else "Disabled"
    if password:
        user.password_hash = hash_password(password)
        user.auth_version = int(user.auth_version or 0) + 1
    return user


def _latest_submission(
    db: Session,
    activity_id: int,
    context: dict | None = None,
) -> TaskSubmission | None:
    if context is not None:
        return context.get("latest_submissions", {}).get(activity_id)
    return db.scalar(
        select(TaskSubmission)
        .where(TaskSubmission.activity_id == activity_id)
        .order_by(TaskSubmission.attempt_number.desc(), TaskSubmission.id.desc())
    )


def _task_void_block_reason(task: FarmActivity, submission: TaskSubmission | None) -> str | None:
    if task.is_archived:
        return "Archived work cannot be voided."
    if task.status != "Completed" or submission is None or submission.review_status != "Approved":
        return "Only approved, completed work can be voided. Pending submissions must be approved or returned for correction."
    if task.source_type in MONITORING_TYPES:
        return "Approved measurements are immutable history. Record a new dated inspection instead of voiding completed monitoring."
    if task.source_module == "Crop" and task.source_type == "crop_harvest":
        return "Approved harvest work has linked yield and crop history. Correct it through the crop harvest workflow instead of voiding this task."
    return None


def _submission_response(
    db: Session,
    item: TaskSubmission | None,
    context: dict | None = None,
):
    if item is None:
        return None
    employee_map = context.get("employees", {}) if context else {}
    user_map = context.get("users", {}) if context else {}
    performer = employee_map.get(item.employee_id) if context else (db.get(Employee, item.employee_id) if item.employee_id else None)
    recorder = user_map.get(item.recorded_by_user_id) if context else (db.get(User, item.recorded_by_user_id) if item.recorded_by_user_id else None)
    reviewer = user_map.get(item.reviewed_by_user_id) if context else (db.get(User, item.reviewed_by_user_id) if item.reviewed_by_user_id else None)
    performer_login_id = performer.login_user_id if performer else None
    return TaskSubmissionResponse(
        monitoring=item.monitoring,
        id=item.id,
        activity_id=item.activity_id,
        employee_id=item.employee_id,
        employee_name=performer.full_name if performer else None,
        recorded_by_user_id=item.recorded_by_user_id,
        recorded_by_name=recorder.full_name if recorder else None,
        reviewed_by_name=reviewer.full_name if reviewer else None,
        is_assisted=bool(item.recorded_by_user_id and item.recorded_by_user_id != performer_login_id),
        attempt_number=item.attempt_number,
        actual_quantity=float(item.actual_quantity) if item.actual_quantity is not None else None,
        actual_unit=item.actual_unit,
        harvest_type_intent=item.harvest_type_intent,
        harvest_type_confirmed=item.harvest_type_confirmed,
        evidence_url=item.evidence_url,
        worker_notes=item.worker_notes,
        problem_report=item.problem_report,
        inventory_override_used=bool(item.inventory_override_used),
        inventory_override_reason=item.inventory_override_reason,
        review_status=item.review_status,
        review_feedback=item.review_feedback,
        reviewed_by_user_id=item.reviewed_by_user_id,
        reviewed_at=item.reviewed_at,
        submitted_at=item.submitted_at,
    )



def _normalize_resource_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").split())


def _same_unit(left: str | None, right: str | None) -> bool:
    aliases = {
        "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
        "g": "g", "gram": "g", "grams": "g",
        "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
        "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
        "pc": "pieces", "pcs": "pieces", "piece": "pieces", "pieces": "pieces",
        "dose": "doses", "doses": "doses",
        "bag": "bags", "bags": "bags", "pack": "packs", "packs": "packs",
        "bottle": "bottles", "bottles": "bottles", "vial": "vials", "vials": "vials",
    }
    def canon(value):
        key = _normalize_resource_text(value)
        return aliases.get(key, key)
    return bool(canon(left)) and canon(left) == canon(right)


def _infer_usage_type(module: str | None, item: InventoryItem | None, task: FarmActivity | None = None) -> str | None:
    if item is None or module not in {"Crop", "Livestock"}:
        return None
    category = _normalize_resource_text(item.category)
    task_text = _normalize_resource_text(" ".join([
        str(getattr(task, "name", "") or ""),
        str(getattr(task, "category", "") or ""),
        str(getattr(task, "instructions", "") or ""),
    ]))
    if module == "Crop":
        if category in {"seed", "seeds"}: return "Seed"
        if category in {"fertilizer", "fertilizers"}: return "Fertilizer"
        if category in {"pesticide", "pesticides"}: return "Pesticide"
        if category in {"herbicide", "herbicides"}: return "Herbicide"
        return "Other"
    if category in {"livestock feed", "animal feed", "feed", "feeds"}: return "Feed"
    if category in {"vaccine", "vaccines"}: return "Vaccine"
    if category in {"vitamin", "vitamins", "supplement", "supplements"}: return "Vitamin / Supplement"
    if category in {"medicine", "medicines", "animal medicine", "livestock medicine"}:
        return "Vaccine" if "vaccin" in task_text or "booster" in task_text else "Medicine"
    if category in {"cleaning supplies", "cleaning supply", "sanitation supply", "sanitation supplies"}:
        return "Disinfectant" if "disinfect" in task_text else "Sanitation Supply"
    if category in {"treatment supply", "treatment supplies", "medical supply", "medical supplies"}: return "Treatment Supply"
    if category in {"disinfectant", "disinfectants"}: return "Disinfectant"
    return "Other"



def _validate_task_resource_choice(
    *,
    module: str | None,
    item: InventoryItem,
    task_text: str | None = None,
) -> None:
    category = _normalize_resource_text(item.category)
    name = _normalize_resource_text(item.name)
    work = _normalize_resource_text(task_text)

    crop_seed_categories = {"seed", "seeds", "seedling", "seedlings", "planting material", "planting materials"}
    crop_only_categories = crop_seed_categories | {
        "fertilizer", "fertilizers", "pesticide", "pesticides",
        "herbicide", "herbicides", "fungicide", "fungicides",
    }
    livestock_categories = {
        "livestock feed", "animal feed", "feed", "feeds",
        "medicine", "medicines", "animal medicine", "livestock medicine",
        "vaccine", "vaccines", "vitamin", "vitamins",
        "supplement", "supplements", "disinfectant", "disinfectants",
        "cleaning supplies", "cleaning supply", "treatment supply", "treatment supplies",
    }

    if module == "Crop":
        if category in crop_seed_categories or "seed" in category:
            raise HTTPException(
                status_code=400,
                detail="Seed and planting-material usage must be recorded through Crops Management, not Task Management.",
            )
        if category in livestock_categories:
            raise HTTPException(status_code=400, detail="The selected Inventory item is intended for livestock work, not a crop task.")
        if "fertiliz" in work and "fertiliz" not in category:
            raise HTTPException(status_code=400, detail="A fertilizing task must use an Inventory item categorized as Fertilizer.")
        if any(term in work for term in ("pesticide", "pest control", "insecticide")) and not any(term in category for term in ("pesticide", "insecticide")):
            raise HTTPException(status_code=400, detail="A pesticide task must use an appropriate pesticide Inventory item.")
        if any(term in work for term in ("herbicide", "weed control")) and "herbicide" not in category:
            raise HTTPException(status_code=400, detail="A herbicide task must use an Inventory item categorized as Herbicide.")

    if module == "Livestock":
        if category in crop_only_categories:
            raise HTTPException(status_code=400, detail="Crop seeds, fertilizer, pesticides, and herbicides cannot be used as livestock task resources.")
        if any(term in work for term in ("feed", "feeding")) and category not in {"livestock feed", "animal feed", "feed", "feeds"}:
            raise HTTPException(status_code=400, detail="A livestock feeding task must use an Inventory item categorized as Livestock Feed or Animal Feed.")
        if any(term in work for term in ("vaccin", "booster")) and not (category in {"vaccine", "vaccines"} or "vaccine" in name):
            raise HTTPException(status_code=400, detail="A vaccination task must use an Inventory item categorized as Vaccine.")


def _task_resource_profile(db: Session, task: FarmActivity, context: dict | None = None) -> dict:
    # Scheduling a feed delivery or maintaining a feed dispenser consumes no
    # supplies. A delivery is posted explicitly through Inventory Stock Adjustment.
    from app.services.event_planning import NON_CONSUMING_INVENTORY_PLANS
    if task.source_module == "Inventory" and task.source_type in NON_CONSUMING_INVENTORY_PLANS:
        return {"module": None, "target_id": None, "item": None, "usage_type": None,
                "planned_quantity": float(task.planned_quantity) if task.planned_quantity is not None else None,
                "required": False, "linked": False}
    module = task.source_module if task.source_module in {"Crop", "Livestock"} else None
    inventory_item_id = task.planned_inventory_item_id
    usage_type = task.planned_usage_type

    planned_quantity = float(task.planned_quantity) if task.planned_quantity is not None else None

    if task.source_type == "livestock_feeding" and task.source_record_id:
        livestock = context.get("livestock", {}).get(task.source_record_id) if context else db.get(Livestock, task.source_record_id)
        if livestock is not None:
            module = "Livestock"
            inventory_item_id = inventory_item_id or livestock.feed_inventory_item_id
            usage_type = usage_type or "Feed"
            # Feeding tasks already know the livestock quantity, daily feed and
            # feeding frequency. Expose the calculated per-feeding plan so both
            # My Tasks and manager-assisted Record Work can prefill the actual
            # usage field without treating the plan as the final actual amount.
            if planned_quantity is None:
                calculated_plan = _planned_feed(task, livestock)
                planned_quantity = calculated_plan if calculated_plan > 0 else None

    if task.source_type == "livestock_vaccination" and task.source_record_id and not inventory_item_id:
        previous_vaccine = (
            context.get("vaccination_by_due", {}).get((task.source_record_id, task.activity_date))
            if context
            else db.scalar(
                select(LivestockVaccinationRecord).where(
                    LivestockVaccinationRecord.livestock_id == task.source_record_id,
                    LivestockVaccinationRecord.inventory_item_id.is_not(None),
                    LivestockVaccinationRecord.next_due == task.activity_date,
                ).order_by(LivestockVaccinationRecord.date_administered.desc(), LivestockVaccinationRecord.id.desc())
            )
        )
        if previous_vaccine is not None:
            module = "Livestock"
            inventory_item_id = previous_vaccine.inventory_item_id
            usage_type = "Vaccine"
            if planned_quantity is None and previous_vaccine.quantity_used is not None:
                planned_quantity = float(previous_vaccine.quantity_used)

    if not inventory_item_id and task.source_type == "care_template_step" and task.source_detail_id:
        step = context.get("care_steps", {}).get(task.source_detail_id) if context else db.get(CareTemplateStep, task.source_detail_id)
        if step is not None:
            inventory_item_id = step.inventory_item_id

    item = (context.get("inventory", {}).get(inventory_item_id) if context else db.get(InventoryItem, inventory_item_id)) if inventory_item_id else None
    if item is not None and not usage_type:
        usage_type = _infer_usage_type(module, item, task)

    resource_text = _normalize_resource_text(" ".join([
        str(task.name or ""), str(task.category or ""), str(task.source_type or ""),
    ]))
    inferred_required = any(term in resource_text for term in (
        "feed", "feeding", "fertiliz", "pesticide", "herbicide", "spray",
        "vaccin", "booster", "medication", "medicine", "deworm", "vitamin",
        "supplement", "seed", "planting material", "disinfect", "sanitize",
    ))
    linked = bool(item is not None and module and task.source_record_id)
    return {
        "module": module,
        "target_id": task.source_record_id if module else None,
        "item": item,
        "usage_type": usage_type,
        "planned_quantity": planned_quantity,
        "required": bool(linked or inferred_required or task.source_type == "livestock_feeding"),
        "linked": linked,
    }


def _lock_inventory_for_task_reservation(db: Session, item_id: int) -> InventoryItem:
    statement = select(InventoryItem).where(InventoryItem.id == item_id)
    statement = statement.with_hint(
        InventoryItem,
        "WITH (UPDLOCK, ROWLOCK)",
        dialect_name="mssql",
    )
    try:
        statement = statement.with_for_update()
    except Exception:
        pass
    item = db.scalar(statement)
    if item is None or item.is_archived:
        raise HTTPException(status_code=400, detail="The linked inventory item is missing or archived.")
    return item


def _pending_inventory_reserved_quantity(
    db: Session,
    *,
    inventory_item_id: int,
    exclude_task_id: int | None = None,
) -> float:
    # Reservations are logical rather than stock movements. Only the latest
    # still-pending submission for a task counts, so Return/Reject/Void releases
    # the reservation automatically without creating compensating inventory rows.
    pending_tasks = list(db.scalars(
        select(FarmActivity).where(
            FarmActivity.status == "Submitted for Review",
            FarmActivity.is_archived == False,
        )
    ).all())
    total = 0.0
    for pending_task in pending_tasks:
        if exclude_task_id is not None and pending_task.id == exclude_task_id:
            continue
        pending_submission = _latest_submission(db, pending_task.id)
        if pending_submission is None or pending_submission.review_status != "Submitted":
            continue
        if pending_submission.actual_quantity is None or float(pending_submission.actual_quantity) <= 0:
            continue
        profile = _task_resource_profile(db, pending_task)
        item = profile.get("item")
        if item is None or int(item.id) != int(inventory_item_id):
            continue
        total += float(pending_submission.actual_quantity)
    return round(total, 3)


def _validate_pending_inventory_reservation(
    db: Session,
    *,
    task: FarmActivity,
    item: InventoryItem,
    actual_quantity: float,
    allow_negative_inventory: bool,
) -> tuple[float, float]:
    # Serialize reservations per inventory item on SQL Server so two different
    # tasks cannot both reserve the same remaining stock at the same time.
    acquire_transaction_lock(db, f"inventory-task-reservation:{item.id}")
    locked_item = _lock_inventory_for_task_reservation(db, item.id)
    if locked_item.expiration_date and task.activity_date > locked_item.expiration_date:
        raise HTTPException(
            status_code=400,
            detail=f"{locked_item.name} expired on {locked_item.expiration_date.isoformat()} and cannot be reserved for this task.",
        )

    reserved_elsewhere = _pending_inventory_reserved_quantity(
        db,
        inventory_item_id=locked_item.id,
        exclude_task_id=task.id,
    )
    on_hand = float(locked_item.quantity or 0)
    unreserved = round(on_hand - reserved_elsewhere, 3)
    if not allow_negative_inventory and float(actual_quantity) > unreserved + 1e-9:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient unreserved stock. {on_hand:g} {locked_item.unit} of {locked_item.name} is on hand, "
                f"but {reserved_elsewhere:g} {locked_item.unit} is already reserved by work awaiting approval. "
                f"Only {max(unreserved, 0):g} {locked_item.unit} remains available for this submission."
            ),
        )
    return on_hand, reserved_elsewhere


def _task_response_base(db: Session, task: FarmActivity, context: dict | None = None) -> TaskResponse:
    employee_name = None
    employee_status = None
    employee_is_archived = False
    previous_employee_name = None
    reassignment_reason = None

    employee = None
    if task.assigned_employee_id:
        employee = context.get("employees", {}).get(task.assigned_employee_id) if context else db.get(Employee, task.assigned_employee_id)
        if employee:
            employee_name = employee.full_name
            employee_status = employee.employment_status
            employee_is_archived = bool(employee.is_archived)

    if task.needs_reassignment:
        if employee_is_archived:
            reassignment_reason = "Assigned employee is archived"
        elif employee_status and employee_status != "Active":
            reassignment_reason = f"Employee is {employee_status.lower()}"
        elif employee is not None:
            if context:
                attendance = context.get("attendance", {}).get((employee.id, task.activity_date))
                leave = next((
                    row for row in context.get("leaves", {}).get(employee.id, [])
                    if row.start_date <= task.activity_date <= row.end_date and row.status == "Approved"
                ), None)
            else:
                attendance = db.scalar(
                    select(StaffAttendance).where(
                        StaffAttendance.employee_id == employee.id,
                        StaffAttendance.attendance_date == task.activity_date,
                        StaffAttendance.status.in_(["Absent", "Sick", "Sick Leave", "Approved Leave", "Day Off"]),
                    )
                )
                leave = db.scalar(
                    select(StaffLeave).where(
                        StaffLeave.employee_id == employee.id,
                        StaffLeave.start_date <= task.activity_date,
                        StaffLeave.end_date >= task.activity_date,
                        StaffLeave.status == "Approved",
                    )
                )
            if attendance is not None:
                reassignment_reason = f"Employee unavailable: {attendance.status}"
            elif leave is not None:
                reassignment_reason = f"Employee on {leave.leave_type.lower()}"
            else:
                reassignment_reason = "Employee unavailable"
        else:
            snapshot = str(task.assigned_to or "").strip()
            if snapshot and snapshot.lower() != "unassigned":
                previous_employee_name = snapshot
            reassignment_reason = "No active employee is currently assigned"

    resource_profile = _task_resource_profile(db, task, context)
    resource_item = resource_profile["item"]
    latest_submission = _latest_submission(db, task.id, context)
    if context is not None:
        latest_approved_submission = context.get("latest_approved_submissions", {}).get(task.id)
    else:
        latest_approved_submission = db.scalar(
            select(TaskSubmission)
            .where(
                TaskSubmission.activity_id == task.id,
                TaskSubmission.review_status == "Approved",
            )
            .order_by(TaskSubmission.attempt_number.desc(), TaskSubmission.id.desc())
        )
    effective_completed_at = task.completed_at
    if effective_completed_at is None and latest_approved_submission is not None:
        effective_completed_at = latest_approved_submission.reviewed_at or latest_approved_submission.submitted_at
    has_performed_work_record = bool(
        latest_submission is not None
        and latest_submission.review_status in {"Submitted", "Approved", "Returned"}
    )
    submission_response = _submission_response(db, latest_submission, context)
    if has_performed_work_record:
        record_origin = "Assisted Submission" if submission_response and submission_response.is_assisted else "Employee Submission"
    elif task.status == "Completed":
        record_origin = "Legacy/System Record"
    elif task.status == "Resolved":
        record_origin = "Resolved Without Performed Work"
    elif task.status == "Cancelled":
        record_origin = "Cancelled Without Performed Work"
    else:
        record_origin = None

    if context is not None:
        coverage_row = context.get("coverage_rows", {}).get(task.id)
        if coverage_row is None:
            coverage = None
        else:
            leave = context.get("coverage_leaves", {}).get(coverage_row.leave_id)
            original = context.get("employees", {}).get(coverage_row.original_employee_id)
            covering = context.get("employees", {}).get(coverage_row.covering_employee_id) if coverage_row.covering_employee_id else None
            indicator = None
            today_value = farm_today()
            if coverage_row.status in COVERAGE_ACTIVE_STATUSES:
                if today_value > coverage_row.coverage_end_date:
                    indicator = "Coverage Ended"
                elif (coverage_row.coverage_end_date - today_value).days <= 1:
                    indicator = "Coverage Ending"
            coverage = {
                "coverage_id": coverage_row.id,
                "leave_id": coverage_row.leave_id,
                "status": coverage_row.status,
                "original_employee_id": coverage_row.original_employee_id,
                "original_employee_name": original.full_name if original else None,
                "covering_employee_id": coverage_row.covering_employee_id,
                "covering_employee_name": covering.full_name if covering else None,
                "coverage_start_date": coverage_row.coverage_start_date,
                "coverage_end_date": coverage_row.coverage_end_date,
                "coverage_reason": coverage_row.reason,
                "indicator": indicator,
                "leave_type": leave.leave_type if leave else None,
                "leave_status": leave.status if leave else None,
                "approved_at": coverage_row.approved_at,
                "returned_at": coverage_row.returned_at,
                "return_reason": coverage_row.return_reason,
            }
    else:
        coverage = coverage_display(db, task)

    return TaskResponse(
        monitoring_context=monitoring_context(db, task),
        id=task.id,
        activity_code=task.activity_code,
        name=task.name,
        category=task.category,
        related_to=task.related_to,
        location=task.location,
        description=task.description,
        instructions=task.instructions,
        activity_date=task.activity_date,
        start_time=task.start_time.strftime("%H:%M") if task.start_time else "",
        end_time=task.end_time.strftime("%H:%M") if task.end_time else None,
        assigned_by=task.assigned_by,
        assigned_to=task.assigned_to,
        assigned_employee_id=task.assigned_employee_id,
        assignment_source=task.assignment_source,
        employee_name=employee_name,
        employee_status=employee_status,
        employee_is_archived=employee_is_archived,
        is_archived=bool(task.is_archived),
        previous_employee_name=previous_employee_name,
        reassignment_reason=reassignment_reason,
        leave_coverage_id=coverage["coverage_id"] if coverage else None,
        related_leave_id=coverage["leave_id"] if coverage else None,
        original_employee_id=coverage["original_employee_id"] if coverage else None,
        original_employee_name=coverage["original_employee_name"] if coverage else None,
        covering_employee_id=coverage["covering_employee_id"] if coverage else None,
        covering_employee_name=coverage["covering_employee_name"] if coverage else None,
        coverage_start_date=coverage["coverage_start_date"] if coverage else None,
        coverage_end_date=coverage["coverage_end_date"] if coverage else None,
        coverage_reason=coverage["coverage_reason"] if coverage else None,
        coverage_status=coverage["status"] if coverage else None,
        coverage_indicator=coverage["indicator"] if coverage else None,
        status=task.status,
        priority=task.priority,
        completed_at=effective_completed_at,
        requires_review=bool(task.requires_review),
        requires_evidence=bool(task.requires_evidence),
        planned_quantity=resource_profile["planned_quantity"],
        planned_unit=(resource_item.unit if resource_item is not None else task.planned_unit),
        planned_inventory_item_id=resource_item.id if resource_item is not None else None,
        planned_inventory_item_code=resource_item.item_code if resource_item is not None else None,
        planned_inventory_item_name=resource_item.name if resource_item is not None else None,
        planned_inventory_category=resource_item.category if resource_item is not None else None,
        planned_inventory_available_quantity=float(resource_item.quantity or 0) if resource_item is not None else None,
        planned_inventory_unit=resource_item.unit if resource_item is not None else None,
        planned_usage_type=resource_profile["usage_type"],
        resource_required=bool(resource_profile["required"]),
        resource_linked=bool(resource_profile["linked"]),
        recurring_rule=task.recurring_rule,
        default_employee_id=task.default_employee_id,
        backup_employee_id=task.backup_employee_id,
        time_sensitive=bool(task.time_sensitive),
        controlled_rescheduling=bool(task.controlled_rescheduling),
        max_delay_minutes=task.max_delay_minutes,
        problem_report=task.problem_report,
        needs_reassignment=bool(task.needs_reassignment),
        source_module=task.source_module,
        source_type=task.source_type,
        source_record_id=task.source_record_id,
        source_protocol_family_code=task.source_protocol_family_code,
        source_protocol_version=task.source_protocol_version,
        source_path=task.source_path,
        is_automatic=bool(task.is_automatic),
        has_performed_work_record=has_performed_work_record,
        can_void=_task_void_block_reason(task, latest_submission) is None,
        void_block_reason=_task_void_block_reason(task, latest_submission),
        record_origin=record_origin,
        latest_submission=submission_response,
    )


def _build_task_serialization_context(db: Session, tasks: list[FarmActivity]) -> dict:
    """Bulk-load related task data to avoid N+1 queries on large task lists."""
    context = {
        "latest_submissions": {},
        "latest_approved_submissions": {},
        "employees": {},
        "users": {},
        "livestock": {},
        "care_steps": {},
        "vaccination_by_due": {},
        "inventory": {},
        "attendance": {},
        "leaves": {},
        "coverage_rows": {},
        "coverage_leaves": {},
    }
    if not tasks:
        return context

    task_ids = [task.id for task in tasks]

    coverage_rows = scalar_rows_in_batches(
        db,
        task_ids,
        lambda batch: select(TaskLeaveCoverage)
        .where(TaskLeaveCoverage.activity_id.in_(batch))
        .order_by(TaskLeaveCoverage.activity_id, TaskLeaveCoverage.id.desc()),
    )
    for row in coverage_rows:
        context["coverage_rows"].setdefault(row.activity_id, row)

    coverage_leave_ids = {int(row.leave_id) for row in context["coverage_rows"].values() if row.leave_id}
    if coverage_leave_ids:
        context["coverage_leaves"] = {
            row.id: row
            for row in scalar_rows_in_batches(
                db,
                coverage_leave_ids,
                lambda batch: select(StaffLeave).where(StaffLeave.id.in_(batch)),
            )
        }

    submission_rows = scalar_rows_in_batches(
        db,
        task_ids,
        lambda batch: select(TaskSubmission)
        .where(TaskSubmission.activity_id.in_(batch))
        .order_by(TaskSubmission.activity_id, TaskSubmission.attempt_number.desc(), TaskSubmission.id.desc()),
    )
    for row in submission_rows:
        context["latest_submissions"].setdefault(row.activity_id, row)
        if row.review_status == "Approved":
            context["latest_approved_submissions"].setdefault(row.activity_id, row)

    employee_ids = {
        int(task.assigned_employee_id) for task in tasks if task.assigned_employee_id
    }
    employee_ids.update(
        int(row.employee_id) for row in context["latest_submissions"].values() if row.employee_id
    )
    employee_ids.update(
        int(row.original_employee_id) for row in context["coverage_rows"].values() if row.original_employee_id
    )
    employee_ids.update(
        int(row.covering_employee_id) for row in context["coverage_rows"].values() if row.covering_employee_id
    )
    if employee_ids:
        context["employees"] = {
            row.id: row
            for row in scalar_rows_in_batches(
                db,
                employee_ids,
                lambda batch: select(Employee).where(Employee.id.in_(batch)),
            )
        }

    user_ids = set()
    for row in context["latest_submissions"].values():
        if row.recorded_by_user_id:
            user_ids.add(int(row.recorded_by_user_id))
        if row.reviewed_by_user_id:
            user_ids.add(int(row.reviewed_by_user_id))
    if user_ids:
        context["users"] = {
            row.id: row
            for row in scalar_rows_in_batches(
                db,
                user_ids,
                lambda batch: select(User).where(User.id.in_(batch)),
            )
        }

    livestock_ids = {
        int(task.source_record_id)
        for task in tasks
        if task.source_module == "Livestock" and task.source_record_id
    }
    if livestock_ids:
        context["livestock"] = {
            row.id: row
            for row in scalar_rows_in_batches(
                db,
                livestock_ids,
                lambda batch: select(Livestock).where(Livestock.id.in_(batch)),
            )
        }

    detail_ids = {int(task.source_detail_id) for task in tasks if task.source_detail_id}
    if detail_ids:
        context["care_steps"] = {
            row.id: row
            for row in scalar_rows_in_batches(
                db,
                detail_ids,
                lambda batch: select(CareTemplateStep).where(CareTemplateStep.id.in_(batch)),
            )
        }

    vaccination_livestock_ids = {
        int(task.source_record_id)
        for task in tasks
        if task.source_type == "livestock_vaccination" and task.source_record_id
    }
    if vaccination_livestock_ids:
        vaccine_rows = scalar_rows_in_batches(
            db,
            vaccination_livestock_ids,
            lambda batch: select(LivestockVaccinationRecord)
            .where(
                LivestockVaccinationRecord.livestock_id.in_(batch),
                LivestockVaccinationRecord.inventory_item_id.is_not(None),
                LivestockVaccinationRecord.next_due.is_not(None),
            )
            .order_by(
                LivestockVaccinationRecord.livestock_id,
                LivestockVaccinationRecord.next_due,
                LivestockVaccinationRecord.date_administered.desc(),
                LivestockVaccinationRecord.id.desc(),
            ),
        )
        for row in vaccine_rows:
            context["vaccination_by_due"].setdefault((row.livestock_id, row.next_due), row)

    inventory_ids = {int(task.planned_inventory_item_id) for task in tasks if task.planned_inventory_item_id}
    for task in tasks:
        if task.source_type == "livestock_feeding" and task.source_record_id:
            livestock = context["livestock"].get(task.source_record_id)
            if livestock and livestock.feed_inventory_item_id:
                inventory_ids.add(int(livestock.feed_inventory_item_id))
        if task.source_type == "livestock_vaccination" and task.source_record_id and not task.planned_inventory_item_id:
            previous = context["vaccination_by_due"].get((task.source_record_id, task.activity_date))
            if previous and previous.inventory_item_id:
                inventory_ids.add(int(previous.inventory_item_id))
        if task.source_type == "care_template_step" and task.source_detail_id and not task.planned_inventory_item_id:
            step = context["care_steps"].get(task.source_detail_id)
            if step and step.inventory_item_id:
                inventory_ids.add(int(step.inventory_item_id))
    if inventory_ids:
        context["inventory"] = {
            row.id: row
            for row in scalar_rows_in_batches(
                db,
                inventory_ids,
                lambda batch: select(InventoryItem).where(InventoryItem.id.in_(batch)),
            )
        }

    reassignment_tasks = [
        task for task in tasks if task.needs_reassignment and task.assigned_employee_id
    ]
    if reassignment_tasks:
        reassignment_employee_ids = {int(task.assigned_employee_id) for task in reassignment_tasks}
        min_date = min(task.activity_date for task in reassignment_tasks)
        max_date = max(task.activity_date for task in reassignment_tasks)
        attendance_rows = scalar_rows_in_batches(
            db,
            reassignment_employee_ids,
            lambda batch: select(StaffAttendance).where(
                StaffAttendance.employee_id.in_(batch),
                StaffAttendance.attendance_date >= min_date,
                StaffAttendance.attendance_date <= max_date,
                StaffAttendance.status.in_(["Absent", "Sick", "Sick Leave", "Approved Leave", "Day Off"]),
            ),
        )
        context["attendance"] = {(row.employee_id, row.attendance_date): row for row in attendance_rows}
        leave_rows = scalar_rows_in_batches(
            db,
            reassignment_employee_ids,
            lambda batch: select(StaffLeave).where(
                StaffLeave.employee_id.in_(batch),
                StaffLeave.start_date <= max_date,
                StaffLeave.end_date >= min_date,
                StaffLeave.status == "Approved",
            ),
        )
        for row in leave_rows:
            context["leaves"].setdefault(row.employee_id, []).append(row)

    return context


def _sanitize_task_response_for_user(item: TaskResponse, current_user: User | None) -> TaskResponse:
    if current_user is None or not is_task_only_user(current_user):
        return item
    return item.model_copy(update={
        "previous_employee_name": None,
        "reassignment_reason": None,
        "employee_status": None,
        "employee_is_archived": False,
    })


def _task_response(db: Session, task: FarmActivity, context: dict | None = None) -> TaskResponse:
    from app.services.farm_event_service import task_hold_info
    info = task_hold_info(db, task, context=context.get("farm_event_holds") if context else None)
    return _task_response_base(db, task, context).model_copy(update=info)


def _task_response_for_user(db: Session, task: FarmActivity, current_user: User) -> TaskResponse:
    return _sanitize_task_response_for_user(_task_response(db, task), current_user)


def _task_responses(db: Session, tasks: list[FarmActivity], current_user: User | None = None) -> list[TaskResponse]:
    from app.services.farm_event_service import hold_context
    context = _build_task_serialization_context(db, tasks)
    context["farm_event_holds"] = hold_context(db, tasks)
    return [
        _sanitize_task_response_for_user(_task_response(db, task, context), current_user)
        for task in tasks
    ]


def _feeding_slot(task: FarmActivity) -> str:
    name = (task.name or "").lower()
    for label in ("Morning", "Noon", "Afternoon", "Evening"):
        if label.lower() in name:
            return label
    return task.start_time.strftime("%H:%M") if task.start_time else "Feeding"


def _planned_feed(task: FarmActivity, livestock: Livestock) -> float:
    if task.planned_quantity is not None and float(task.planned_quantity) > 0:
        return round(float(task.planned_quantity), 3)
    daily = float(livestock.daily_feed_kg or 0) * int(livestock.quantity or 1)
    schedule = str(livestock.feed_times or "").lower()
    feedings = 1
    if "twice" in schedule or "2" in schedule:
        feedings = 2
    elif "three" in schedule or "3" in schedule:
        feedings = 3
    return round(daily / feedings, 3) if daily > 0 else 0.0


def _sync_feeding_usage(
    db: Session,
    *,
    task: FarmActivity,
    submission: TaskSubmission,
    actual_quantity: float,
    current_user: User,
    allow_negative_inventory: bool = False,
    override_reason: str | None = None,
    post_inventory: bool = True,
) -> ResourceUsage | None:
    if task.source_type != "livestock_feeding" or not task.source_record_id:
        return None

    livestock = db.get(Livestock, task.source_record_id)
    if livestock is None or livestock.is_archived:
        raise HTTPException(status_code=400, detail="Linked livestock record is missing or archived.")
    inventory_item_id = task.planned_inventory_item_id or livestock.feed_inventory_item_id
    if not inventory_item_id:
        raise HTTPException(status_code=400, detail="Link a feed inventory item to this livestock record first.")

    item = db.get(InventoryItem, inventory_item_id)
    if item is None or item.is_archived:
        raise HTTPException(status_code=400, detail="The linked feed inventory item is missing or archived.")
    if not _same_unit(item.unit, "kg"):
        raise HTTPException(status_code=400, detail="Livestock feed inventory must use kilograms (kg).")

    usage: ResourceUsage | None = None
    if post_inventory:
        previous_usage = _active_task_resource_usage(db, task.id)
        movement_reason = (
            f"Approved actual feed used for task {task.activity_code}, submission {submission.attempt_number}."
            + (f" Authorized negative-stock override: {override_reason}" if allow_negative_inventory else "")
        )
        if previous_usage is None:
            usage = create_usage(
                db,
                module="Livestock",
                target_id=livestock.id,
                inventory_item_id=item.id,
                usage_type="Feed",
                quantity=float(actual_quantity),
                usage_date=task.activity_date,
                notes=f"Approved actual feed used for task {task.activity_code}.",
                current_user=current_user,
                movement_type="Task Usage",
                allow_negative=allow_negative_inventory,
                movement_reason=movement_reason,
            )
            usage.activity_id = task.id
            usage.task_submission_id = submission.id
            usage.task_posting_active = True
            db.flush()
        else:
            usage = update_usage(
                db,
                usage=previous_usage,
                changes={
                    "inventory_item_id": item.id,
                    "usage_type": "Feed",
                    "quantity": float(actual_quantity),
                    "usage_date": task.activity_date,
                    "notes": f"Corrected approved feed used for task {task.activity_code}.",
                },
                current_user=current_user,
                movement_type="Usage Adjustment",
                allow_negative=allow_negative_inventory,
                movement_reason=movement_reason,
            )
            usage.activity_id = task.id
            usage.task_submission_id = submission.id
            usage.task_posting_active = True
            db.flush()

    # The feeding record describes the work the employee reported. It may exist
    # while the task is awaiting review, but inventory is not changed until the
    # manager approves the submission.
    slot = _feeding_slot(task)
    feeding = db.scalar(
        select(LivestockFeedingRecord).where(
            LivestockFeedingRecord.livestock_id == livestock.id,
            LivestockFeedingRecord.feeding_date == task.activity_date,
            LivestockFeedingRecord.feeding_slot == slot,
        )
    )
    planned = _planned_feed(task, livestock)
    note = (
        f"Approved from task {task.activity_code}; inventory deducted after manager approval."
        if post_inventory
        else f"Submitted from task {task.activity_code}; awaiting manager approval before inventory deduction."
    )
    if feeding is None:
        feeding = LivestockFeedingRecord(
            livestock_id=livestock.id,
            inventory_item_id=item.id,
            feeding_date=task.activity_date,
            feeding_slot=slot,
            scheduled_times=livestock.feed_times,
            feed_type=(livestock.feed_type or item.name),
            planned_quantity_kg=planned,
            actual_quantity_kg=actual_quantity,
            notes=note,
            recorded_by_user_id=current_user.id,
        )
        db.add(feeding)
    else:
        feeding.inventory_item_id = item.id
        feeding.actual_quantity_kg = actual_quantity
        feeding.planned_quantity_kg = planned
        feeding.recorded_by_user_id = current_user.id
        feeding.notes = note
    return usage

def _is_vaccination_task(task: FarmActivity) -> bool:
    text_value = _normalize_resource_text(" ".join([
        str(task.name or ""), str(task.category or ""), str(task.source_type or ""),
    ]))
    return task.source_module == "Livestock" and (
        task.source_type == "livestock_vaccination"
        or "vaccin" in text_value
        or "booster" in text_value
    )


def _next_vaccination_task_date(
    db: Session,
    livestock_id: int,
    *,
    after_date: date,
    exclude_task_id: int | None = None,
) -> date | None:
    stmt = select(FarmActivity).where(
        FarmActivity.source_module == "Livestock",
        FarmActivity.source_record_id == livestock_id,
        FarmActivity.is_archived == False,
        FarmActivity.activity_date > after_date,
        FarmActivity.status.notin_(["Completed", "Cancelled", "Resolved", "Voided"]),
    )
    if exclude_task_id:
        stmt = stmt.where(FarmActivity.id != exclude_task_id)
    rows = list(db.scalars(stmt.order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)).all())
    for row in rows:
        if _is_vaccination_task(row):
            return row.activity_date
    return None


def _sync_approved_vaccination_task(
    db: Session,
    *,
    task: FarmActivity,
    submission: TaskSubmission,
    current_user: User,
) -> None:
    if not _is_vaccination_task(task) or not task.source_record_id:
        return
    profile = _task_resource_profile(db, task)
    item = profile.get("item")
    if item is None or (profile.get("usage_type") or _infer_usage_type("Livestock", item, task)) != "Vaccine":
        return
    if submission.actual_quantity is None or float(submission.actual_quantity) <= 0:
        return
    _sync_vaccination_history_from_task(
        db,
        task=task,
        submission=submission,
        item=item,
        actual_quantity=float(submission.actual_quantity),
        current_user=current_user,
    )


def _sync_vaccination_history_from_task(
    db: Session,
    *,
    task: FarmActivity,
    submission: TaskSubmission,
    item: InventoryItem,
    actual_quantity: float,
    current_user: User,
) -> None:
    if task.source_module != "Livestock" or not task.source_record_id:
        return
    profile_usage_type = task.planned_usage_type or _infer_usage_type("Livestock", item, task)
    if profile_usage_type != "Vaccine":
        return

    livestock = db.get(Livestock, task.source_record_id)
    if livestock is None or livestock.is_archived:
        return
    livestock = lock_vaccination_parent(db, livestock.id)
    performer = db.get(Employee, submission.employee_id)
    task_note = f"Recorded from workforce task {task.activity_code}."
    existing = db.scalar(
        select(LivestockVaccinationRecord).where(
            LivestockVaccinationRecord.livestock_id == livestock.id,
            LivestockVaccinationRecord.date_administered == task.activity_date,
            LivestockVaccinationRecord.inventory_item_id == item.id,
            LivestockVaccinationRecord.notes == task_note,
        ).order_by(LivestockVaccinationRecord.id.desc())
    )
    if existing is None:
        existing = LivestockVaccinationRecord(
            livestock_id=livestock.id,
            vaccine=item.name,
            date_administered=task.activity_date,
            next_due=None,
            status="Up to Date",
            administered_by=performer.full_name if performer else None,
            inventory_item_id=item.id,
            quantity_used=actual_quantity,
            unit=item.unit,
            notes=task_note,
            recorded_by_user_id=current_user.id,
        )
        db.add(existing)
    else:
        existing.vaccine = item.name
        existing.quantity_used = actual_quantity
        existing.unit = item.unit
        existing.administered_by = performer.full_name if performer else existing.administered_by
        existing.recorded_by_user_id = current_user.id

    next_due = _next_vaccination_task_date(
        db, livestock.id, after_date=task.activity_date, exclude_task_id=task.id
    )
    existing.next_due = next_due
    update_vaccination_summary(db, livestock, existing, status="Scheduled" if next_due else "Up to Date", next_due=next_due)
    livestock.updated_at = datetime.now()


def _sync_task_resource_usage(
    db: Session,
    *,
    task: FarmActivity,
    submission: TaskSubmission,
    actual_quantity: float,
    actual_unit: str | None,
    current_user: User,
    allow_negative_inventory: bool = False,
    override_reason: str | None = None,
) -> ResourceUsage | None:
    if task.source_type == "livestock_feeding":
        return None

    profile = _task_resource_profile(db, task)
    if not profile["required"]:
        return None

    item: InventoryItem = profile["item"]
    module = profile["module"]
    target_id = int(profile["target_id"])
    usage_type = profile["usage_type"] or "Other"

    if actual_quantity <= 0:
        raise HTTPException(status_code=400, detail="Enter the actual resource quantity used before submitting.")
    if not actual_unit:
        raise HTTPException(status_code=400, detail=f"Enter the actual resource unit ({item.unit}).")
    if not _same_unit(actual_unit, item.unit):
        raise HTTPException(
            status_code=400,
            detail=f"Actual resource usage must be recorded in the inventory unit ({item.unit}).",
        )

    previous_usage = _active_task_resource_usage(db, task.id)
    movement_reason = (
        f"Actual {usage_type.lower()} usage for task {task.activity_code}, submission {submission.attempt_number}."
        + (f" Authorized negative-stock override: {override_reason}" if allow_negative_inventory else "")
    )
    if previous_usage is None:
        usage = create_usage(
            db,
            module=module,
            target_id=target_id,
            inventory_item_id=item.id,
            usage_type=usage_type,
            quantity=float(actual_quantity),
            usage_date=task.activity_date,
            notes=f"Actual {usage_type.lower()} usage for task {task.activity_code}.",
            current_user=current_user,
            movement_type="Task Usage",
            allow_negative=allow_negative_inventory,
            movement_reason=movement_reason,
        )
        usage.activity_id = task.id
        usage.task_submission_id = submission.id
        usage.task_posting_active = True
        db.flush()
        return usage

    usage = update_usage(
        db,
        usage=previous_usage,
        changes={
            "inventory_item_id": item.id,
            "usage_type": usage_type,
            "quantity": float(actual_quantity),
            "usage_date": task.activity_date,
            "notes": f"Corrected actual {usage_type.lower()} usage for task {task.activity_code}.",
        },
        current_user=current_user,
        movement_type="Usage Adjustment",
        allow_negative=allow_negative_inventory,
        movement_reason=movement_reason,
    )
    usage.activity_id = task.id
    usage.task_submission_id = submission.id
    usage.task_posting_active = True
    db.flush()
    return usage


def _post_submission_inventory_on_approval(
    db: Session,
    *,
    task: FarmActivity,
    submission: TaskSubmission,
    current_user: User,
) -> ResourceUsage | None:
    profile = _task_resource_profile(db, task)
    if not profile["required"]:
        return None
    if not profile["linked"] or profile.get("item") is None:
        raise HTTPException(
            status_code=400,
            detail="This task requires inventory usage but its linked inventory item is unavailable.",
        )
    if submission.actual_quantity is None or float(submission.actual_quantity) <= 0:
        raise HTTPException(status_code=400, detail="The submitted work has no valid actual inventory quantity.")

    item: InventoryItem = profile["item"]
    if not submission.actual_unit or not _same_unit(submission.actual_unit, item.unit):
        raise HTTPException(
            status_code=400,
            detail=f"The submitted inventory usage must use the inventory unit ({item.unit}) before approval.",
        )

    if task.source_type == "livestock_feeding":
        return _sync_feeding_usage(
            db,
            task=task,
            submission=submission,
            actual_quantity=float(submission.actual_quantity),
            current_user=current_user,
            allow_negative_inventory=bool(submission.inventory_override_used),
            override_reason=submission.inventory_override_reason,
            post_inventory=True,
        )

    return _sync_task_resource_usage(
        db,
        task=task,
        submission=submission,
        actual_quantity=float(submission.actual_quantity),
        actual_unit=submission.actual_unit,
        current_user=current_user,
        allow_negative_inventory=bool(submission.inventory_override_used),
        override_reason=submission.inventory_override_reason,
    )


def _reverse_task_resource_usage(
    db: Session,
    *,
    task: FarmActivity,
    current_user: User,
    reason: str,
) -> ResourceUsage | None:
    usage = _active_task_resource_usage(db, task.id)
    if usage is None:
        return None
    void_usage(
        db,
        usage=usage,
        reason=reason,
        current_user=current_user,
        movement_type="Usage Reversal",
    )
    usage.task_posting_active = False
    db.flush()
    return usage


def _flag_unavailable_tasks(db: Session, employee_id: int, start_date: date, end_date: date) -> int:
    # Kept as a compatibility wrapper for existing callers. Recalculate rather
    # than only setting True so Present/cancelled-leave changes can clear stale
    # flags when no other unavailability rule still applies.
    return recalculate_employee_tasks(db, employee_id, start_date, end_date)


def _employee_response(db: Session, employee: Employee) -> dict:
    links = list(
        db.scalars(
            select(EmployeePosition)
            .where(EmployeePosition.employee_id == employee.id)
            .order_by(EmployeePosition.is_primary.desc(), EmployeePosition.id)
        ).all()
    )
    positions = [
        {
            "id": link.position.id,
            "name": link.position.name,
            "category": link.position.category,
            "description": link.position.description,
            "is_primary": bool(link.is_primary),
        }
        for link in links
        if link.position is not None
    ]
    primary = next((item for item in positions if item["is_primary"]), None)
    archived_by = db.get(User, employee.archived_by_user_id) if employee.archived_by_user_id else None
    account_state = _employee_account_state(db, employee)
    login_user = account_state["login_user"]
    schedule_meta = employee_schedule_metadata(db, employee.id)
    return {
        "id": employee.id,
        "employee_code": employee.employee_code,
        "personal_details": employee.personal_details,
        "full_name": employee.full_name,
        "contact_number": employee.contact_number,
        "email": employee.email,
        "address": employee.address,
        "position": employee.position,
        "primary_position_id": primary["id"] if primary else None,
        "positions": positions,
        "date_hired": employee.date_hired,
        "employment_type": employee.employment_type,
        "assigned_area": employee.assigned_area,
        "skills": employee.skills,
        "employment_status": employee.employment_status,
        "emergency_contact_name": employee.emergency_contact_name,
        "emergency_contact_relationship": employee.emergency_contact_relationship,
        "emergency_contact_number": employee.emergency_contact_number,
        "login_user_id": employee.login_user_id,
        "login_username": login_user.username if login_user else None,
        "login_status": login_user.status if login_user else None,
        "account_status": account_state["account_status"],
        "portal_assignment_ready": bool(account_state["portal_assignment_ready"]),
        "account_repair_available": bool(account_state["account_repair_available"]),
        "account_issue": account_state["account_issue"],
        "notes": employee.notes,
        "is_archived": employee.is_archived,
        "archived_at": employee.archived_at,
        "archived_by_user_id": employee.archived_by_user_id,
        "archived_by_name": archived_by.full_name if archived_by else None,
        "archive_reason": employee.archive_reason,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
        "schedule_status": schedule_meta["schedule_status"],
        "weekly_schedule_summary": schedule_meta["weekly_schedule_summary"],
        "next_rest_day": schedule_meta["next_rest_day"],
        "weekly_schedule": schedule_meta["weekly_schedule"],
    }


def _set_employee_positions(
    db: Session,
    employee: Employee,
    *,
    primary_position_id: int | None,
    position_ids: list[int] | None,
) -> None:
    if position_ids is None:
        return
    normalized = list(dict.fromkeys(int(value) for value in position_ids if value))
    if primary_position_id and primary_position_id not in normalized:
        normalized.insert(0, primary_position_id)
    if len(normalized) > 5:
        raise HTTPException(status_code=400, detail="An employee can have a maximum of 5 active positions.")
    if normalized and primary_position_id is None:
        primary_position_id = normalized[0]

    positions = list(db.scalars(select(FarmPosition).where(FarmPosition.id.in_(normalized))).all()) if normalized else []
    by_id = {item.id: item for item in positions}
    missing = [position_id for position_id in normalized if position_id not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail="One or more selected farm positions do not exist.")
    inactive = [item.name for item in positions if not item.is_active]
    if inactive:
        raise HTTPException(status_code=400, detail=f"Inactive farm position selected: {', '.join(inactive)}")

    db.execute(delete(EmployeePosition).where(EmployeePosition.employee_id == employee.id))
    for position_id in normalized:
        db.add(EmployeePosition(
            employee_id=employee.id,
            position_id=position_id,
            is_primary=position_id == primary_position_id,
        ))
    employee.position = by_id[primary_position_id].name if primary_position_id in by_id else None


def _employee_work_assignments_response(
    db: Session,
    employee: Employee,
    *,
    include_available: bool = False,
) -> dict:
    crop_stmt = select(Crop).where(Crop.is_archived == False)
    livestock_stmt = select(Livestock).where(Livestock.is_archived == False)
    if not include_available:
        crop_stmt = crop_stmt.where(Crop.assigned_employee_id == employee.id)
        livestock_stmt = livestock_stmt.where(Livestock.assigned_employee_id == employee.id)

    crops = list(db.scalars(crop_stmt.order_by(Crop.field, Crop.name, Crop.id)).all())
    livestock_records = list(
        db.scalars(livestock_stmt.order_by(Livestock.pen_location, Livestock.record_name, Livestock.id)).all()
    )

    assigned_ids = {
        int(value)
        for value in [
            *(crop.assigned_employee_id for crop in crops),
            *(record.assigned_employee_id for record in livestock_records),
        ]
        if value
    }
    employees_by_id = {}
    if assigned_ids:
        employees_by_id = {
            item.id: item.full_name
            for item in db.scalars(select(Employee).where(Employee.id.in_(assigned_ids))).all()
        }

    return {
        "employee_id": employee.id,
        "employee_name": employee.full_name,
        "crops": [
            {
                "id": crop.id,
                "record_code": crop.crop_code,
                "name": crop.name,
                "category": "Crop",
                "location": crop.field,
                "detail": " • ".join(part for part in [crop.variety, crop.growth_stage] if part),
                "assigned_employee_id": crop.assigned_employee_id,
                "assigned_employee_name": employees_by_id.get(crop.assigned_employee_id),
                "is_assigned_to_employee": crop.assigned_employee_id == employee.id,
            }
            for crop in crops
        ],
        "livestock": [
            {
                "id": record.id,
                "record_code": record.animal_code,
                "name": record.record_name,
                "category": "Livestock",
                "location": record.pen_location,
                "detail": " • ".join(
                    part for part in [
                        record.animal_type,
                        record.breed,
                        f"{record.quantity} animal(s)" if record.quantity is not None else None,
                    ] if part
                ),
                "assigned_employee_id": record.assigned_employee_id,
                "assigned_employee_name": employees_by_id.get(record.assigned_employee_id),
                "is_assigned_to_employee": record.assigned_employee_id == employee.id,
            }
            for record in livestock_records
        ],
    }


def _sync_employee_work_assignments(
    db: Session,
    employee: Employee,
    *,
    crop_assignment_ids: list[int] | None,
    livestock_assignment_ids: list[int] | None,
) -> None:
    if crop_assignment_ids is None and livestock_assignment_ids is None:
        return

    requested_crop_ids = None if crop_assignment_ids is None else set(dict.fromkeys(int(value) for value in crop_assignment_ids))
    requested_livestock_ids = None if livestock_assignment_ids is None else set(dict.fromkeys(int(value) for value in livestock_assignment_ids))

    if requested_crop_ids is not None:
        requested_crops = list(
            db.scalars(
                select(Crop).where(Crop.id.in_(requested_crop_ids), Crop.is_archived == False)
            ).all()
        ) if requested_crop_ids else []
        if len(requested_crops) != len(requested_crop_ids):
            raise HTTPException(status_code=400, detail="One or more selected crop assignments are unavailable.")

        current_crops = list(
            db.scalars(select(Crop).where(Crop.assigned_employee_id == employee.id, Crop.is_archived == False)).all()
        )
        for crop in current_crops:
            if crop.id not in requested_crop_ids:
                crop.assigned_employee_id = None
        for crop in requested_crops:
            crop.assigned_employee_id = employee.id

    if requested_livestock_ids is not None:
        requested_livestock = list(
            db.scalars(
                select(Livestock).where(Livestock.id.in_(requested_livestock_ids), Livestock.is_archived == False)
            ).all()
        ) if requested_livestock_ids else []
        if len(requested_livestock) != len(requested_livestock_ids):
            raise HTTPException(status_code=400, detail="One or more selected livestock assignments are unavailable.")

        current_livestock = list(
            db.scalars(
                select(Livestock).where(
                    Livestock.assigned_employee_id == employee.id,
                    Livestock.is_archived == False,
                )
            ).all()
        )
        for record in current_livestock:
            if record.id not in requested_livestock_ids:
                record.assigned_employee_id = None
        for record in requested_livestock:
            record.assigned_employee_id = employee.id


def _flag_employee_open_tasks_for_reassignment(db: Session, employee_id: int) -> int:
    tasks = list(
        db.scalars(
            select(FarmActivity).where(
                FarmActivity.assigned_employee_id == employee_id,
                FarmActivity.status.in_(["Pending", "In Progress", "Returned"]),
                FarmActivity.is_archived == False,
            )
        ).all()
    )
    for task in tasks:
        task.needs_reassignment = True
    return len(tasks)


def _release_employee_current_farm_assignments(db: Session, employee_id: int) -> tuple[int, int]:
    """Release current Crop/Livestock responsibility when an employee is archived.

    Historical tasks/submissions remain linked to the employee; only current farm
    responsibility is cleared so future automatic work is not routed to an archived worker.
    """
    crops = list(
        db.scalars(
            select(Crop).where(
                Crop.assigned_employee_id == employee_id,
                Crop.is_archived == False,
            )
        ).all()
    )
    livestock_records = list(
        db.scalars(
            select(Livestock).where(
                Livestock.assigned_employee_id == employee_id,
                Livestock.is_archived == False,
            )
        ).all()
    )
    for crop in crops:
        crop.assigned_employee_id = None
    for record in livestock_records:
        record.assigned_employee_id = None
    return len(crops), len(livestock_records)


@router.get("/me/profile", response_model=EmployeeSelfProfileResponse)
def get_my_employee_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "get_my_employee_profile")
    employee = _employee_for_user_or_error(db, current_user)
    return EmployeeSelfProfileResponse(
        id=employee.id,
        employee_code=employee.employee_code,
        full_name=employee.full_name,
        username=current_user.username,
        contact_number=employee.contact_number,
        email=employee.email,
        position=employee.position,
        assigned_area=employee.assigned_area,
        employment_status=employee.employment_status,
    )


@router.get("/positions", response_model=list[FarmPositionResponse])
def list_farm_positions(
    include_inactive: bool = Query(False),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "list_farm_positions")
    stmt = select(FarmPosition)
    if not include_inactive:
        stmt = stmt.where(FarmPosition.is_active == True)
    if category:
        stmt = stmt.where(FarmPosition.category == category)
    stmt = stmt.order_by(FarmPosition.category, FarmPosition.sort_order, FarmPosition.name)
    return list(db.scalars(stmt).all())


@router.get("/employees", response_model=list[EmployeeResponse])
def list_employees(
    include_archived: bool = Query(False),
    archived_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "list_employees")
    stmt = select(Employee)
    if archived_only:
        stmt = stmt.where(Employee.is_archived == True).order_by(Employee.archived_at.desc(), Employee.full_name)
    elif not include_archived:
        stmt = stmt.where(Employee.is_archived == False).order_by(Employee.full_name)
    else:
        stmt = stmt.order_by(Employee.is_archived, Employee.full_name)
    return [_employee_response(db, employee) for employee in db.scalars(stmt).all()]


@router.post("/employees/account-links/repair")
def repair_employee_account_links(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "repair_employee_account_links")
    repaired: list[dict] = []
    skipped: list[dict] = []
    employees = list(
        db.scalars(
            select(Employee).where(
                Employee.is_archived == False,
                Employee.login_user_id.is_(None),
            ).order_by(Employee.id)
        ).all()
    )
    try:
        for employee in employees:
            candidates = _candidate_login_users_for_employee(db, employee)
            eligible = [
                user for user in candidates
                if user.status == "Active"
                and user.role is not None
                and user.role.is_active
                and is_task_only_user(user)
            ]
            if len(candidates) == 1 and len(eligible) == 1:
                user = eligible[0]
                employee.login_user_id = user.id
                repaired.append({
                    "employee_id": employee.id,
                    "employee_code": employee.employee_code,
                    "username": user.username,
                })
                _add_workforce_audit(
                    db,
                    current_user=current_user,
                    action="Employee account link repaired",
                    entity_id=f"employee:{employee.id}",
                    record_name=employee.full_name,
                    details=(
                        f"Linked employee {employee.employee_code} to existing Employee login {user.username} "
                        "using a unique normalized email match. No name-based matching was used."
                    ),
                    icon="link",
                )
            else:
                skipped.append({
                    "employee_id": employee.id,
                    "employee_code": employee.employee_code,
                    "account_status": _employee_account_state(db, employee)["account_status"],
                    "reason": (
                        "No deterministic unique Employee login match."
                        if not candidates else
                        "Ambiguous or ineligible login match; manual administrator review is required."
                    ),
                })
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"repaired": repaired, "skipped": skipped}


@router.get("/employees/{employee_id}/work-assignments", response_model=EmployeeWorkAssignmentsResponse)
def get_employee_work_assignments(
    employee_id: int,
    include_available: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "get_employee_work_assignments")
    employee = _employee_or_404(db, employee_id, active_only=False)
    return _employee_work_assignments_response(db, employee, include_available=include_available)


@router.get("/employees/{employee_id}/work-schedule", response_model=WeeklyScheduleResponse | None)
def get_employee_work_schedule(
    employee_id: int,
    on_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "get_employee_work_schedule")
    _employee_or_404(db, employee_id, active_only=False)
    target_date = on_date or farm_today()
    schedule = current_schedule(db, employee_id, target_date)
    if schedule is None:
        schedule = db.scalar(
            select(EmployeeWorkSchedule).where(
                EmployeeWorkSchedule.employee_id == employee_id,
                EmployeeWorkSchedule.status == "Active",
            ).order_by(EmployeeWorkSchedule.effective_from.desc(), EmployeeWorkSchedule.id.desc())
        )
    return schedule_response(db, schedule)


@router.put("/employees/{employee_id}/work-schedule", response_model=EmployeeResponse)
def update_employee_work_schedule(
    employee_id: int,
    payload: WeeklyScheduleInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "update_employee_work_schedule")
    employee = _employee_or_404(db, employee_id, active_only=False)
    if employee.is_archived:
        raise HTTPException(status_code=400, detail="Restore the employee before changing the work schedule.")
    acquire_transaction_lock(db, f"employee-work-schedule:{employee_id}")
    try:
        replace_employee_schedule(db, employee=employee, payload=payload, actor_user_id=current_user.id)
        reconcile_employee_future_tasks(
            db, employee.id, from_date=payload.effective_from,
            actor_user_id=current_user.id, actor_name=current_user.full_name,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(employee)
    return _employee_response(db, employee)


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "create_employee")

    linked_user = None
    if payload.login_user_id:
        linked_user = db.get(User, payload.login_user_id)
        if linked_user is None:
            raise HTTPException(status_code=400, detail="Selected login account does not exist.")
        if linked_user.role is None or not linked_user.role.is_active or linked_user.status != "Active":
            raise HTTPException(
                status_code=400,
                detail="Only an active system account with an active role can be linked to an employee profile.",
            )
        if db.scalar(select(Employee).where(Employee.login_user_id == payload.login_user_id)):
            raise HTTPException(status_code=409, detail="That login account is already linked to an employee.")

    employee = Employee(
        employee_code=_next_code(db, Employee, "EMP"),
        full_name=payload.full_name.strip(),
        contact_number=payload.contact_number,
        email=str(payload.email).strip().lower() if payload.email else None,
        address=payload.address,
        position=payload.position,
        date_hired=payload.date_hired,
        employment_type=payload.employment_type,
        assigned_area=payload.assigned_area,
        skills=payload.skills,
        employment_status=payload.employment_status,
        emergency_contact_name=payload.emergency_contact_name,
        emergency_contact_relationship=payload.emergency_contact_relationship,
        emergency_contact_number=payload.emergency_contact_number,
        login_user_id=payload.login_user_id,
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )

    apply_personal_details(employee, payload.model_dump(exclude_unset=True))
    try:
        db.add(employee)
        db.flush()

        if payload.position_ids or payload.primary_position_id:
            _set_employee_positions(
                db, employee,
                primary_position_id=payload.primary_position_id,
                position_ids=payload.position_ids,
            )
            db.flush()

        # Employee + weekly schedule are one transaction. A schedule validation
        # or persistence failure rolls back the employee and optional login too.
        replace_employee_schedule(
            db, employee=employee, payload=payload.weekly_schedule, actor_user_id=current_user.id
        )

        if payload.create_login_account:
            login_user = _create_employee_login_user(
                db,
                full_name=employee.full_name,
                personal_details=employee.personal_details,
                username=payload.login_username or "",
                password=payload.login_password or "",
                email=employee.email,
                contact_number=employee.contact_number,
                position=employee.position,
                employment_status=employee.employment_status,
            )
            employee.login_user_id = login_user.id
        elif linked_user is not None and is_task_only_user(linked_user):
            # Task-only login profiles mirror employee details. Elevated
            # administrative identities are linked for assignment only.
            linked_user.personal_details = employee.personal_details
            linked_user.full_name = employee.full_name
            linked_user.email = employee.email
            linked_user.contact_number = employee.contact_number
            linked_user.position = employee.position
            linked_user.status = "Active" if employee.employment_status == "Active" else "Disabled"

        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to create employee/login/schedule. Employee code, username, or email may already exist.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(employee)
    return _employee_response(db, employee)


@router.put("/employees/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "update_employee")
    employee = _employee_or_404(db, employee_id, active_only=False)
    if employee.is_archived:
        raise HTTPException(status_code=400, detail="Restore the employee before editing the profile.")

    changes = payload.model_dump(exclude_unset=True)
    had_structured_address = bool((employee.personal_details or {}).get("address"))
    apply_personal_details(employee, changes)
    if changes.get("personal_details") is not None and (changes["personal_details"].get("address") is not None or had_structured_address):
        changes.pop("address", None)  # The backend-derived address is authoritative.
    changes.pop("personal_details", None)
    requested_login_user_id = changes.pop("login_user_id", None) if "login_user_id" in changes else None
    create_login_account = bool(changes.pop("create_login_account", False))
    login_username = changes.pop("login_username", None)
    login_password = changes.pop("login_password", None)
    position_ids = changes.pop("position_ids", None)
    primary_position_id = changes.pop("primary_position_id", None)
    crop_assignment_ids = changes.pop("crop_assignment_ids", None)
    livestock_assignment_ids = changes.pop("livestock_assignment_ids", None)
    weekly_schedule = changes.pop("weekly_schedule", None)

    if requested_login_user_id is not None and requested_login_user_id != employee.login_user_id:
        linked_user = db.get(User, requested_login_user_id)
        if linked_user is None:
            raise HTTPException(status_code=400, detail="Selected login account does not exist.")
        if linked_user.role is None or not linked_user.role.is_active or linked_user.status != "Active":
            raise HTTPException(
                status_code=400,
                detail="Only an active system account with an active role can be linked to an employee profile.",
            )
        duplicate = db.scalar(
            select(Employee).where(
                Employee.login_user_id == requested_login_user_id,
                Employee.id != employee.id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="That login account is already linked to another employee.")
        employee.login_user_id = requested_login_user_id

    for key, value in changes.items():
        if key == "email":
            value = str(value).strip().lower() if value else None
        elif isinstance(value, str):
            value = value.strip()
        setattr(employee, key, value)

    if changes.get("employment_status") and changes["employment_status"] != "Active":
        _flag_employee_open_tasks_for_reassignment(db, employee.id)

    try:
        if position_ids is not None:
            _set_employee_positions(
                db, employee,
                primary_position_id=primary_position_id,
                position_ids=position_ids,
            )
            db.flush()

        _sync_employee_work_assignments(
            db, employee,
            crop_assignment_ids=crop_assignment_ids,
            livestock_assignment_ids=livestock_assignment_ids,
        )

        if weekly_schedule is not None:
            schedule_payload = WeeklyScheduleInput.model_validate(weekly_schedule)
            replace_employee_schedule(
                db, employee=employee, payload=schedule_payload, actor_user_id=current_user.id
            )
            reconcile_employee_future_tasks(
                db, employee.id, from_date=schedule_payload.effective_from,
                actor_user_id=current_user.id, actor_name=current_user.full_name,
            )

        if employee.login_user_id:
            _sync_linked_employee_login(
                db, employee, username=login_username, password=login_password
            )
        elif create_login_account:
            login_user = _create_employee_login_user(
                db,
                full_name=employee.full_name,
                personal_details=employee.personal_details,
                username=login_username or "",
                password=login_password or "",
                email=employee.email,
                contact_number=employee.contact_number,
                position=employee.position,
                employment_status=employee.employment_status,
            )
            employee.login_user_id = login_user.id

        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to update employee/login/schedule. Username or email may already exist.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(employee)
    return _employee_response(db, employee)


@router.post("/employees/{employee_id}/status", response_model=EmployeeResponse)
def change_employee_status(
    employee_id: int,
    payload: EmployeeStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "change_employee_status")
    employee = _employee_or_404(db, employee_id, active_only=False)
    if employee.is_archived:
        raise HTTPException(status_code=400, detail="Restore the employee before changing employment status.")
    employee.employment_status = payload.employment_status
    if payload.employment_status != "Active":
        _flag_employee_open_tasks_for_reassignment(db, employee.id)
    _sync_linked_employee_login(db, employee)
    db.commit()
    db.refresh(employee)
    return _employee_response(db, employee)


@router.post("/employees/{employee_id}/archive", response_model=EmployeeResponse)
def archive_employee(
    employee_id: int,
    payload: EmployeeArchiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "archive_employee")
    record = change_archive_state(db, "Employee", employee_id, current_user, archive=True, reason=payload.reason)
    db.commit()
    db.refresh(record)
    return _employee_response(db, record)


@router.post("/employees/{employee_id}/restore", response_model=EmployeeResponse)
def restore_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "restore_employee")
    record = change_archive_state(db, "Employee", employee_id, current_user, archive=False)
    db.commit()
    db.refresh(record)
    return _employee_response(db, record)


@router.get("/tasks/page", response_model=TaskPageResponse)
def list_tasks_page(
    offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
    employee_id: int | None = Query(None), task_status: str | None = Query(None, alias="status"),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    source_module: str | None = Query(None), source_record_id: int | None = Query(None),
    open_only: bool = Query(False), actionable_only: bool = Query(False),
    search: str | None = Query(None, max_length=120), priority: str | None = Query(None),
    assignment_state: str | None = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "list_tasks")
    stmt = select(FarmActivity).where(FarmActivity.is_archived == False)
    if not _can_view_all_tasks(current_user):
        own = _employee_for_user(db, current_user)
        if own is None:
            return {"items": [], "total": 0, "offset": offset, "limit": limit}
        stmt = stmt.where(FarmActivity.assigned_employee_id == own.id)
    elif employee_id:
        stmt = stmt.where(FarmActivity.assigned_employee_id == employee_id)
    if task_status == "Missed":
        stmt = stmt.where(FarmActivity.activity_date < farm_today(), FarmActivity.status.in_(
            ["Pending", "In Progress", "Returned", "Submitted for Review"]))
    elif task_status:
        stmt = stmt.where(FarmActivity.status == task_status)
    closed = ["Completed", "Cancelled", "Resolved", "Voided"]
    if actionable_only:
        today_key = farm_today()
        stmt = stmt.where(or_(
            (FarmActivity.activity_date <= today_key) & or_(FarmActivity.status.notin_(closed),
                                                             FarmActivity.activity_date == today_key),
            (FarmActivity.activity_date > today_key) & or_(FarmActivity.status.in_(["Submitted for Review", "Returned"]),
                                                            FarmActivity.needs_reassignment == True),
        ))
    elif open_only:
        stmt = stmt.where(FarmActivity.status.notin_(closed))
    if date_from:
        stmt = stmt.where(FarmActivity.activity_date >= date_from)
    if date_to:
        stmt = stmt.where(FarmActivity.activity_date <= date_to)
    if source_module:
        stmt = stmt.where(FarmActivity.source_module == source_module)
    if source_record_id:
        stmt = stmt.where(FarmActivity.source_record_id == source_record_id)
    if priority and priority != "All":
        stmt = stmt.where(FarmActivity.priority == priority)
    if assignment_state == "Unassigned":
        stmt = stmt.where(FarmActivity.assigned_employee_id.is_(None))
    elif assignment_state == "Needs Reassignment":
        stmt = stmt.where(FarmActivity.needs_reassignment == True)
    elif assignment_state == "No Reassignment":
        stmt = stmt.where(FarmActivity.needs_reassignment == False)
    elif assignment_state == "Leave Coverage":
        stmt = stmt.where(FarmActivity.assignment_source == "Leave Coverage")
    if search and search.strip():
        needle = f"%{search.strip()}%"
        stmt = stmt.where(or_(FarmActivity.name.ilike(needle), FarmActivity.activity_code.ilike(needle),
                              FarmActivity.category.ilike(needle), FarmActivity.location.ilike(needle),
                              FarmActivity.related_to.ilike(needle), FarmActivity.assigned_to.ilike(needle)))
    filtered = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(filtered)) or 0
    items = db.scalars(stmt.order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)
                       .offset(offset).limit(limit)).all()
    return {"items": _task_responses(db, list(items), current_user), "total": total,
            "offset": offset, "limit": limit}


def _held_flag_column(db: Session, activity_id, assigned_employee_id, status_column, statuses):
    """Per-row 1/0 "held by a farm-event declaration" column for an inner query.

    held_task_expression() is an EXISTS subquery. SQL Server rejects an aggregate over any expression that
    contains a subquery (error 130, "Cannot perform an aggregate function on an expression containing an
    aggregate or a subquery"), so SUM(CASE WHEN <held> ...) fails there even though SQLite accepts it.
    Select this column in an inner query and aggregate the plain ``is_held`` column in the outer query.
    """
    from app.services.farm_event_service import held_task_expression
    return case(
        (held_task_expression(db, activity_id, assigned_employee_id) & status_column.in_(statuses), 1),
        else_=0,
    ).label("is_held")


@router.get("/tasks/summary")
def task_management_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "list_tasks")
    stmt = select(FarmActivity).where(FarmActivity.is_archived == False)
    if not _can_view_all_tasks(current_user):
        own = _employee_for_user(db, current_user)
        if own is None:
            return {key: 0 for key in ("pending", "progress", "review", "overdue", "reassign")}
        stmt = stmt.where(FarmActivity.assigned_employee_id == own.id)
    base = stmt.subquery()
    today_key = farm_today()
    flagged = select(
        base.c.status, base.c.activity_date, base.c.needs_reassignment,
        _held_flag_column(db, base.c.id, base.c.assigned_employee_id, base.c.status, ["Pending", "In Progress", "Returned"]),
    ).subquery()
    held = flagged.c.is_held == 1
    row = db.execute(select(
        func.sum(case((~held & (flagged.c.status == "Pending") & (flagged.c.activity_date <= today_key), 1), else_=0)),
        func.sum(case((~held & (flagged.c.status == "In Progress") & (flagged.c.activity_date <= today_key), 1), else_=0)),
        func.sum(case((flagged.c.status == "Submitted for Review", 1), else_=0)),
        func.sum(case((~held & (flagged.c.activity_date < today_key) & flagged.c.status.notin_(["Completed", "Cancelled", "Resolved", "Voided"]), 1), else_=0)),
        func.sum(case(((~held & (flagged.c.needs_reassignment == True) & flagged.c.status.in_(["Pending", "In Progress", "Returned", "Submitted for Review"])), 1), else_=0)),
        func.sum(case((held, 1), else_=0)),
    )).one()
    return dict(zip(("pending", "progress", "review", "overdue", "reassign", "held"), [int(value or 0) for value in row]))


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    employee_id: int | None = Query(None),
    task_status: str | None = Query(None, alias="status"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    source_module: str | None = Query(None),
    source_record_id: int | None = Query(None, gt=0),
    open_only: bool = Query(False),
    actionable_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "list_tasks")
    stmt = select(FarmActivity).where(FarmActivity.is_archived == False)
    if not _can_view_all_tasks(current_user):
        own_employee = _employee_for_user(db, current_user)
        if own_employee is None:
            return []
        stmt = stmt.where(FarmActivity.assigned_employee_id == own_employee.id)
    elif employee_id:
        stmt = stmt.where(FarmActivity.assigned_employee_id == employee_id)
    if task_status:
        stmt = stmt.where(FarmActivity.status == task_status)
    closed_statuses = ["Completed", "Cancelled", "Resolved", "Voided"]
    if actionable_only:
        today_key = farm_today()
        stmt = stmt.where(
            FarmActivity.activity_date <= today_key,
            or_(
                FarmActivity.status.notin_(closed_statuses),
                FarmActivity.activity_date == today_key,
            ),
        )
    elif open_only:
        stmt = stmt.where(FarmActivity.status.notin_(closed_statuses))
    if date_from:
        stmt = stmt.where(FarmActivity.activity_date >= date_from)
    if date_to:
        stmt = stmt.where(FarmActivity.activity_date <= date_to)
    if source_module:
        stmt = stmt.where(FarmActivity.source_module == source_module)
    if source_record_id:
        stmt = stmt.where(FarmActivity.source_record_id == source_record_id)
    stmt = stmt.order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)
    tasks = list(db.scalars(stmt).all())
    return _task_responses(db, tasks, current_user)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task_detail(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "list_tasks")
    task = db.get(FarmActivity, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if not _can_view_all_tasks(current_user):
        employee = _employee_for_user_or_error(db, current_user)
        if task.assigned_employee_id != employee.id:
            raise HTTPException(status_code=404, detail="Task not found.")
    return _task_response_for_user(db, task, current_user)


@router.get("/my-tasks/page", response_model=TaskPageResponse)
def my_tasks_page(
    offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
    view: str = Query("active"), scope: str = Query("timeline"),
    status_filter: str | None = Query(None), priority: str | None = Query(None),
    missed_only: bool = Query(False),
    search: str | None = Query(None, max_length=120),
    date_from: date | None = Query(None), date_to: date | None = Query(None),
    shared_device: bool = Query(False),
    response: Response = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "my_tasks")
    employee = _employee_for_user_or_error(db, current_user)
    if view not in {"active", "completed", "history", "all"} or scope not in {"timeline", "all"}:
        raise HTTPException(status_code=400, detail="Invalid task view or scope.")
    if response is not None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Authorization"
    stmt = select(FarmActivity).where(FarmActivity.assigned_employee_id == employee.id)
    if view == "active":
        stmt = stmt.where(FarmActivity.is_archived == False,
                          FarmActivity.status.in_(["Pending", "In Progress", "Returned", "Submitted for Review"]))
        if scope == "timeline":
            stmt = stmt.where(FarmActivity.activity_date <= farm_today() + timedelta(days=7))
    elif view == "completed":
        stmt = stmt.where(FarmActivity.is_archived == False, FarmActivity.status == "Completed")
    elif view == "history":
        stmt = stmt.where(or_(FarmActivity.is_archived == True,
                              FarmActivity.status.in_(["Completed", "Approved", "Voided", "Cancelled", "Resolved"])))
    else:
        stmt = stmt.where(FarmActivity.is_archived == False)
    if status_filter:
        stmt = stmt.where(FarmActivity.status == status_filter)
    if missed_only:
        stmt = stmt.where(FarmActivity.activity_date < farm_today(),
                          FarmActivity.status.in_(["Pending", "In Progress", "Returned"]))
    if priority:
        stmt = stmt.where(FarmActivity.priority == priority)
    if date_from:
        stmt = stmt.where(FarmActivity.activity_date >= date_from)
    if date_to:
        stmt = stmt.where(FarmActivity.activity_date <= date_to)
    if search and search.strip():
        needle = f"%{search.strip()}%"
        stmt = stmt.where(or_(FarmActivity.name.ilike(needle), FarmActivity.activity_code.ilike(needle),
                              FarmActivity.location.ilike(needle), FarmActivity.description.ilike(needle),
                              FarmActivity.instructions.ilike(needle)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if view in {"completed", "history"}:
        stmt = stmt.order_by(FarmActivity.completed_at.desc(), FarmActivity.activity_date.desc(), FarmActivity.id.desc())
    else:
        stmt = stmt.order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)
    items = _task_responses(db, list(db.scalars(stmt.offset(offset).limit(limit)).all()), current_user)
    if shared_device:
        items = [sanitize_shared_device_task_response(item) for item in items]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/my-tasks", response_model=list[TaskResponse])
def my_tasks(
    include_completed: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    view: str | None = None,
    shared_device: bool = Query(False),
    response: Response = None,
    scope: str | None = None,
):
    _require_workforce_access(current_user, "my_tasks")
    employee = _employee_for_user_or_error(db, current_user)
    if response is not None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization"

    stmt = select(FarmActivity).where(
        FarmActivity.assigned_employee_id == employee.id,
    )
    horizon = farm_today() + timedelta(days=7)

    # New callers use an explicit task view. The old include_completed query is
    # intentionally retained only as a compatibility path for older clients.
    # history is additive and read-only: it lets an employee see their own
    # terminal or archived assignments without exposing archived work to action
    # endpoints, which continue to reject archived tasks.
    normalized_view = str(view or "").strip().lower() or None
    if normalized_view is not None and normalized_view not in {"active", "completed", "history", "all"}:
        raise HTTPException(status_code=400, detail="view must be one of: active, completed, history, all.")

    normalized_scope = str(scope or "").strip().lower() or "all"
    if normalized_scope not in {"timeline", "all"}:
        raise HTTPException(status_code=400, detail="scope must be one of: timeline, all.")

    explicit_view = normalized_view is not None
    if explicit_view:
        if normalized_view == "active":
            stmt = stmt.where(
                FarmActivity.is_archived == False,
                FarmActivity.status.in_(["Pending", "In Progress", "Returned", "Submitted for Review"]),
            )
            # My Tasks uses the lightweight timeline scope for its initial screen:
            # every overdue/current assignment plus the next seven days.  Far-future
            # recurring occurrences remain discoverable through scope=all without
            # forcing the employee to serialize the entire recurring schedule on load.
            if normalized_scope == "timeline":
                stmt = stmt.where(FarmActivity.activity_date <= horizon)
        elif normalized_view == "completed":
            stmt = stmt.where(
                FarmActivity.is_archived == False,
                FarmActivity.status == "Completed",
            )
        elif normalized_view == "history":
            stmt = stmt.where(
                or_(
                    FarmActivity.is_archived == True,
                    FarmActivity.status.in_(["Completed", "Approved", "Voided", "Cancelled", "Resolved"]),
                )
            )
        elif normalized_view == "all":
            # Preserve the pre-existing all-view contract: archived assignments
            # remain excluded here and are exposed only by view=history.
            stmt = stmt.where(FarmActivity.is_archived == False)
    elif include_completed:
        stmt = stmt.where(FarmActivity.is_archived == False)
        # Legacy behavior: include historical terminal rows plus the bounded
        # active/upcoming window.  New UI code no longer uses this mixed mode.
        stmt = stmt.where(
            or_(
                FarmActivity.status.in_(["Completed", "Cancelled", "Resolved", "Voided"]),
                FarmActivity.activity_date <= horizon,
            )
        )
    else:
        stmt = stmt.where(
            FarmActivity.is_archived == False,
            FarmActivity.status.notin_(["Completed", "Cancelled", "Resolved", "Voided"]),
            FarmActivity.activity_date <= horizon,
        )

    stmt = stmt.order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)
    tasks = list(db.scalars(stmt).all())
    responses = _task_responses(db, tasks, current_user)
    if shared_device:
        responses = [sanitize_shared_device_task_response(item) for item in responses]
    if explicit_view and normalized_view in {"completed", "history"}:
        responses.sort(
            key=lambda item: (
                item.completed_at or datetime.min,
                item.activity_date,
                item.id,
            ),
            reverse=True,
        )
    return responses


@router.get("/my-tasks/summary", response_model=MyTasksSummaryResponse)
def my_tasks_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    """Return lightweight active-assignment counts without serializing task cards."""
    _require_workforce_access(current_user, "my_tasks")
    employee = _employee_for_user_or_error(db, current_user)
    if response is not None:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization"

    today_key = farm_today()
    horizon = today_key + timedelta(days=7)
    active_statuses = ["Pending", "In Progress", "Returned", "Submitted for Review"]
    missed_statuses = ["Pending", "In Progress", "Returned"]
    flagged = select(
        FarmActivity.id, FarmActivity.status, FarmActivity.activity_date,
        _held_flag_column(db, FarmActivity.id, FarmActivity.assigned_employee_id, FarmActivity.status, missed_statuses),
    ).where(
        FarmActivity.assigned_employee_id == employee.id,
        FarmActivity.is_archived == False,
        FarmActivity.status.in_(active_statuses),
    ).subquery()
    held = flagged.c.is_held == 1
    row = db.execute(
        select(
            func.count(flagged.c.id),
            func.sum(case((flagged.c.activity_date == today_key, 1), else_=0)),
            func.sum(case((
                ~held & (flagged.c.activity_date < today_key)
                & flagged.c.status.in_(missed_statuses),
                1,
            ), else_=0)),
            func.sum(case((~held & (flagged.c.status == "In Progress"), 1), else_=0)),
            func.sum(case((~held & (flagged.c.status == "Returned"), 1), else_=0)),
            func.sum(case((flagged.c.status == "Submitted for Review", 1), else_=0)),
            func.sum(case((
                (flagged.c.activity_date > today_key)
                & (flagged.c.activity_date <= horizon),
                1,
            ), else_=0)),
            func.sum(case((held, 1), else_=0)),
        )
    ).one()

    values = [int(value or 0) for value in row]
    return MyTasksSummaryResponse(
        total=values[0],
        today=values[1],
        missed=values[2],
        in_progress=values[3],
        returned=values[4],
        for_review=values[5],
        upcoming=values[6],
        held=values[7],
    )


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "create_task")
    employee = _assignable_employee_or_404(db, payload.employee_id) if payload.employee_id else None
    backup_employee = _assignable_employee_or_404(db, payload.backup_employee_id) if payload.backup_employee_id else None
    if employee is not None:
        _require_portal_assignment_account(db, employee)
        _require_assignment_availability(
            db, employee, payload.activity_date,
            allow_override=bool(payload.allow_unavailable_override),
        )
    if backup_employee is not None:
        _require_portal_assignment_account(db, backup_employee)
    if employee is not None and backup_employee is not None and employee.id == backup_employee.id:
        raise HTTPException(status_code=400, detail="Backup employee must be different from the default employee.")
    resource_item = None
    planned_usage_type = payload.planned_usage_type
    planned_unit = payload.planned_unit
    if payload.planned_inventory_item_id:
        resource_item = db.get(InventoryItem, payload.planned_inventory_item_id)
        if resource_item is None or resource_item.is_archived:
            raise HTTPException(status_code=400, detail="Selected inventory resource is missing or archived.")
        _validate_task_resource_choice(
            module=payload.source_module,
            item=resource_item,
            task_text=" ".join([payload.name, payload.category, payload.instructions or ""]),
        )
        if payload.source_module not in {"Crop", "Livestock"} or not payload.source_record_id:
            raise HTTPException(
                status_code=400,
                detail="A task-linked inventory resource requires a Crop or Livestock source record.",
            )
        planned_unit = resource_item.unit
        planned_usage_type = planned_usage_type or _infer_usage_type(payload.source_module, resource_item)

        # Prevent creating a resource task that is impossible with the stock
        # available at assignment time. My Tasks keeps its own final stock
        # check because stock may still change between assignment and execution.
        planned_amount = float(payload.planned_quantity or 0)
        available_amount = float(resource_item.quantity or 0)
        if planned_amount > available_amount + 0.0000001:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient stock for assignment. Planned {planned_amount:g} {resource_item.unit}, "
                    f"but only {available_amount:g} {resource_item.unit} of {resource_item.name} is available."
                ),
            )
    task = FarmActivity(
        activity_code=_next_code(db, FarmActivity, "ACT"),
        name=payload.name.strip(),
        category=payload.category.strip(),
        related_to=payload.related_to.strip(),
        location=payload.location.strip(),
        description=(payload.description or "").strip() or None,
        instructions=(payload.instructions or "").strip() or None,
        activity_date=payload.activity_date,
        start_time=_parse_clock(payload.start_time, time(8, 0)),
        end_time=_parse_clock(payload.end_time),
        assigned_by=current_user.full_name,
        assigned_to=employee.full_name if employee else "Unassigned",
        assigned_employee_id=employee.id if employee else None,
        status="Pending",
        priority=payload.priority,
        # Any manual task assigned to a real employee enters the review workflow.
        # Unassigned reminders may still opt out and use Resolve instead.
        requires_review=True if employee is not None else payload.requires_review,
        requires_evidence=payload.requires_evidence,
        planned_quantity=payload.planned_quantity,
        planned_unit=planned_unit,
        planned_inventory_item_id=resource_item.id if resource_item else None,
        planned_usage_type=planned_usage_type,
        recurring_rule=(payload.recurring_rule or "").strip() or None,
        default_employee_id=employee.id if employee else None,
        backup_employee_id=payload.backup_employee_id,
        time_sensitive=bool(payload.time_sensitive),
        controlled_rescheduling=bool(payload.controlled_rescheduling),
        max_delay_minutes=payload.max_delay_minutes,
        source_module=payload.source_module,
        source_type=payload.source_type,
        source_record_id=payload.source_record_id,
        source_path=payload.source_path,
        is_automatic=False,
        created_by_user_id=current_user.id,
    )
    db.add(task)
    db.flush()
    recalculate_task_reassignment(db, task)
    from app.services.farm_event_service import reconcile_event_holds
    db.flush()
    reconcile_event_holds(db, tasks=[task])
    db.commit()
    db.refresh(task)
    return _task_response(db, task)


def _scheduled_resource_task_name(module: str, usage_type: str, target_name: str) -> tuple[str, str]:
    if module == "Crop":
        names = {
            "Fertilizer": (f"Apply Fertilizer — {target_name}", "Crop Fertilizing"),
            "Pesticide": (f"Apply Pesticide — {target_name}", "Crop Treatment"),
            "Herbicide": (f"Apply Herbicide — {target_name}", "Crop Treatment"),
            "Other": (f"Crop Resource Work — {target_name}", "Crop Care"),
        }
    else:
        names = {
            "Medicine": (f"Administer Medicine — {target_name}", "Livestock Treatment"),
            "Vitamin / Supplement": (f"Give Supplement — {target_name}", "Livestock Care"),
            "Disinfectant": (f"Disinfect Area — {target_name}", "Livestock Sanitation"),
            "Treatment Supply": (f"Treatment Care — {target_name}", "Livestock Treatment"),
            "Sanitation Supply": (f"Sanitation Care — {target_name}", "Livestock Sanitation"),
            "Other": (f"Livestock Resource Work — {target_name}", "Livestock Care"),
        }
    return names[usage_type]


@router.post("/tasks/schedule-resource-work", response_model=TaskResponse, status_code=201)
def schedule_resource_work(
    payload: ResourceWorkScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Schedule consumable crop/livestock work without deducting stock yet.

    The assigned employee receives the task in My Tasks. The reported actual
    quantity is reserved at submission and deducted only after manager approval.
    """
    _require_workforce_access(current_user, "schedule_resource_work")

    if payload.module == "Crop":
        target = db.get(Crop, payload.target_id)
        if target is None or target.is_archived:
            raise HTTPException(status_code=404, detail="Active crop record not found.")
        if str(target.status or "") in {"Harvested", "Failed"}:
            raise HTTPException(status_code=400, detail=f"Resource work cannot be scheduled for a {str(target.status).lower()} crop cycle.")
        target_name = target.name
        location = target.field
        related_to = f"{target.name} — {target.field}"
        source_code = target.crop_code
        source_path = "/crops"
    else:
        target = db.get(Livestock, payload.target_id)
        if target is None or target.is_archived:
            raise HTTPException(status_code=404, detail="Active livestock record not found.")
        target_name = target.record_name
        location = target.pen_location or "Jorros Farm"
        related_to = f"{target.record_name} — {location}"
        source_code = target.animal_code
        source_path = "/livestock"

    employee_id = getattr(target, "assigned_employee_id", None)
    if not employee_id:
        raise HTTPException(
            status_code=400,
            detail=f"Assign an active employee to this {payload.module.lower()} record before scheduling work.",
        )
    employee = _assignable_employee_or_404(db, int(employee_id))
    _require_portal_assignment_account(db, employee)

    item = db.get(InventoryItem, payload.inventory_item_id)
    if item is None or item.is_archived:
        raise HTTPException(status_code=400, detail="Selected inventory resource is missing or archived.")

    name, category = _scheduled_resource_task_name(payload.module, payload.usage_type, target_name)
    _validate_task_resource_choice(
        module=payload.module,
        item=item,
        task_text=" ".join([name, category, payload.instructions or "", payload.usage_type]),
    )

    inferred_usage_type = _infer_usage_type(payload.module, item) or "Other"
    if payload.usage_type != "Other" and inferred_usage_type != payload.usage_type:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{item.name} is categorized for {inferred_usage_type}, not {payload.usage_type}. "
                "Choose the matching work type or Inventory item."
            ),
        )
    if payload.usage_type == "Other" and inferred_usage_type != "Other":
        raise HTTPException(
            status_code=400,
            detail=(
                f"{item.name} belongs to the {inferred_usage_type} workflow. "
                "Use that work type instead of Other."
            ),
        )
    planned_usage_type = payload.usage_type

    available = float(item.quantity or 0)
    planned = float(payload.planned_quantity)
    if planned > available + 0.0000001:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for assignment. Planned {planned:g} {item.unit}, "
                f"but only {available:g} {item.unit} of {item.name} is available."
            ),
        )

    task = FarmActivity(
        activity_code=_next_code(db, FarmActivity, "ACT"),
        name=name,
        category=category,
        related_to=related_to,
        location=location,
        description=(
            f"Scheduled {payload.usage_type.lower()} work for {related_to}. "
            "The employee's actual quantity is reserved at submission and deducted only after manager approval."
        ),
        instructions=(payload.instructions or "").strip() or None,
        activity_date=payload.activity_date,
        start_time=_parse_clock(payload.start_time, time(8, 0)),
        assigned_by=current_user.full_name,
        assigned_to=employee.full_name,
        assigned_employee_id=employee.id,
        status="Pending",
        priority=payload.priority,
        requires_review=True,
        requires_evidence=payload.requires_evidence,
        planned_quantity=planned,
        planned_unit=item.unit,
        planned_inventory_item_id=item.id,
        planned_usage_type=planned_usage_type,
        source_module=payload.module,
        source_type="scheduled_resource_work",
        source_record_id=target.id,
        source_code=source_code,
        source_path=source_path,
        is_automatic=False,
        created_by_user_id=current_user.id,
    )
    db.add(task)
    db.flush()
    recalculate_task_reassignment(db, task)
    db.commit()
    db.refresh(task)
    return _task_response(db, task)


@router.put("/tasks/{task_id}/assignment", response_model=TaskResponse)
def update_task_assignment(
    task_id: int,
    payload: TaskAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "update_task_assignment")
    task = _task_locked_or_404(db, task_id)
    from app.services.farm_event_service import assert_task_available
    assert_task_available(db, task)
    if assignment_is_protected(task):
        raise HTTPException(
            status_code=400,
            detail="Submitted, completed, approved/voided, resolved, cancelled, or archived tasks cannot be reassigned.",
        )

    changes = payload.model_dump(exclude_unset=True)
    reason = (changes.pop("reason", None) or "").strip()
    allow_unavailable_override = bool(changes.pop("allow_unavailable_override", False))
    old_employee_id = task.assigned_employee_id
    old_assignment_source = task.assignment_source
    active_coverage = coverage_display(db, task)
    old_employee = db.get(Employee, old_employee_id) if old_employee_id else None
    old_employee_name = old_employee.full_name if old_employee else "Unassigned"
    was_needing_reassignment = bool(task.needs_reassignment)

    if "employee_id" in changes:
        employee = _assignable_employee_or_404(db, changes["employee_id"]) if changes["employee_id"] else None
        new_employee_id = employee.id if employee else None
        if employee is not None:
            _require_portal_assignment_account(db, employee)
            _require_assignment_availability(
                db, employee, changes.get("activity_date") or task.activity_date,
                allow_override=allow_unavailable_override,
            )
        if new_employee_id != old_employee_id:
            if task.default_employee_id is None and old_employee_id is not None:
                task.default_employee_id = old_employee_id
            assignment_source = "reassignment" if was_needing_reassignment else "manager_override"
            task.assigned_employee_id = new_employee_id
            task.assigned_to = employee.full_name if employee else "Unassigned"
            task.assigned_by = current_user.full_name
            task.assignment_source = assignment_source
            record_assignment_change(
                db,
                task,
                old_employee_id=old_employee_id,
                new_employee_id=new_employee_id,
                assignment_source=assignment_source,
                actor_user_id=current_user.id,
                actor_name=current_user.full_name,
                reason=reason or (
                    "Manager reassigned task because the previous assignee was unavailable."
                    if was_needing_reassignment
                    else "Manager changed the task assignment."
                ),
                leave_id=active_coverage["leave_id"] if active_coverage else None,
                old_assignment_source=old_assignment_source,
                new_assignment_source=assignment_source,
                is_automatic=False,
            )
            if active_coverage:
                mark_leave_coverage_manager_override(
                    db,
                    task=task,
                    actor_user_id=current_user.id,
                )
            _add_workforce_audit(
                db,
                current_user=current_user,
                action="Task reassigned" if old_employee_id is not None and new_employee_id is not None else "Task assignment changed",
                entity_id=str(task.id),
                record_name=f"{task.activity_code} — {task.name}",
                details=(
                    f"Assignment changed from {old_employee_name} (ID: {old_employee_id or 'none'}) "
                    f"to {employee.full_name if employee else 'Unassigned'} (ID: {new_employee_id or 'none'}). "
                    f"Source: {'Manager Reassignment' if assignment_source == 'manager_override' else 'Reassignment' if assignment_source == 'reassignment' else assignment_source}. "
                    f"Reason: {reason or 'Manager changed the task assignment.'}"
                ),
                icon="assignment_ind",
            )

    if "activity_date" in changes and "employee_id" not in changes and task.assigned_employee_id is not None:
        current_employee = _assignable_employee_or_404(db, task.assigned_employee_id)
        _require_portal_assignment_account(db, current_employee)
        _require_assignment_availability(
            db, current_employee, changes["activity_date"],
            allow_override=allow_unavailable_override,
        )

    for key in ("activity_date", "priority", "instructions", "requires_review", "requires_evidence"):
        if key in changes:
            setattr(task, key, changes[key])

    # Employee-performed work must always go through manager/reviewer approval.
    # A manager cannot accidentally disable review on an open assigned task.
    if task.assigned_employee_id is not None:
        task.requires_review = True

    # Never blindly clear the flag. The replacement assignee and/or changed
    # task date may also be unavailable.
    try:
        recalculate_task_reassignment(db, task)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(task)
    return _task_response(db, task)


@router.get(
    "/tasks/{task_id}/assignment-history",
    response_model=list[TaskAssignmentHistoryResponse],
)
def task_assignment_history(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "task_assignment_history")
    task = db.get(FarmActivity, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    rows = list(
        db.scalars(
            select(TaskAssignmentHistory)
            .where(TaskAssignmentHistory.activity_id == task_id)
            .order_by(TaskAssignmentHistory.changed_at, TaskAssignmentHistory.id)
        ).all()
    )
    employee_ids = {
        employee_id
        for row in rows
        for employee_id in (row.old_employee_id, row.new_employee_id)
        if employee_id
    }
    names = (
        {employee.id: employee.full_name for employee in db.scalars(select(Employee).where(Employee.id.in_(employee_ids))).all()}
        if employee_ids
        else {}
    )
    return [
        TaskAssignmentHistoryResponse(
            id=row.id,
            activity_id=row.activity_id,
            old_employee_id=row.old_employee_id,
            new_employee_id=row.new_employee_id,
            old_employee_name=names.get(row.old_employee_id),
            new_employee_name=names.get(row.new_employee_id),
            assignment_source=row.assignment_source,
            leave_id=row.leave_id,
            old_assignment_source=row.old_assignment_source,
            new_assignment_source=row.new_assignment_source,
            is_automatic=bool(row.is_automatic),
            actor_user_id=row.actor_user_id,
            actor_name=row.actor_name,
            reason=row.reason,
            changed_at=row.changed_at,
        )
        for row in rows
    ]


def _resolve_submission_evidence(
    db: Session,
    *,
    task: FarmActivity,
    payload: TaskSubmitRequest,
) -> list[TaskEvidence]:
    public_ids = [str(value).strip().lower() for value in payload.evidence_ids if str(value).strip()]
    if payload.evidence_url:
        match = NEW_EVIDENCE_URL_RE.fullmatch(str(payload.evidence_url).strip())
        if match is None:
            raise HTTPException(
                status_code=400,
                detail="External evidence URLs are disabled. Upload the photo directly to this task.",
            )
        public_ids.append(match.group(1))

    public_ids = list(dict.fromkeys(public_ids))
    if len(public_ids) > settings.workforce_evidence_max_files_per_submission:
        raise HTTPException(
            status_code=400,
            detail=f"A task submission may contain at most {settings.workforce_evidence_max_files_per_submission} evidence photos.",
        )
    if not public_ids:
        return []

    assets = list(db.scalars(select(TaskEvidence).where(TaskEvidence.public_id.in_(public_ids))).all())
    by_id = {item.public_id: item for item in assets}
    ordered: list[TaskEvidence] = []
    for public_id in public_ids:
        item = by_id.get(public_id)
        # 404 avoids confirming that a random opaque evidence id belongs to a
        # different employee/task.
        if item is None or item.activity_id != task.id or item.status == "Deleted":
            raise HTTPException(status_code=404, detail="Evidence photo not found.")
        if item.submission_id is not None or item.status != "Temporary":
            raise HTTPException(status_code=400, detail="This evidence photo is already attached to a submission.")
        if item.expires_at is not None and item.expires_at <= datetime.now():
            raise HTTPException(status_code=400, detail="This temporary evidence photo has expired. Upload it again.")
        ordered.append(item)

    total_bytes = sum(int(item.size_bytes or 0) for item in ordered)
    if total_bytes > settings.workforce_evidence_max_total_bytes_per_submission:
        raise HTTPException(
            status_code=400,
            detail=f"Total evidence for one submission must be {settings.workforce_evidence_max_total_bytes_per_submission // (1024 * 1024)} MB or smaller.",
        )
    return ordered


@router.post("/tasks/{task_id}/start", response_model=TaskResponse)
def start_task(
    task_id: int,
    payload: TaskStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "start_task")
    task = _task_locked_or_404(db, task_id)
    _assert_task_access(db, task, current_user)
    from app.services.farm_event_service import assert_task_available
    assert_task_available(db, task)
    if task.activity_date > farm_today():
        raise HTTPException(status_code=400, detail="A future task cannot be started yet.")
    if task.status not in {"Pending", "Returned"}:
        raise HTTPException(status_code=400, detail="Only pending or returned tasks can be started.")
    latest_submission = _latest_submission(db, task.id)
    if (latest_submission and latest_submission.review_status in {"Submitted", "Approved"}) or _active_task_resource_usage(db, task.id):
        raise HTTPException(400, "Submitted or approved work must use the review or authorized correction workflow.")
    task.status = "In Progress"
    if payload.notes:
        task.problem_report = None
    db.commit()
    db.refresh(task)
    return _task_response_for_user(db, task, current_user)


@router.post("/tasks/{task_id}/submit", response_model=TaskResponse)
def submit_task(
    task_id: int,
    payload: TaskSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    _require_workforce_access(current_user, "submit_task")
    key = normalize_idempotency_key(idempotency_key)
    payload_hash = request_fingerprint(payload)

    # Serialize the complete task lifecycle transaction. On SQL Server this is
    # an application lock owned by the current DB transaction; the row itself
    # is also loaded with an update lock below.
    acquire_transaction_lock(db, f"workforce-task-lifecycle:{task_id}")
    task = _task_locked_or_404(db, task_id)
    own_employee = _assert_task_access(db, task, current_user)

    existing_retry = _existing_idempotent_submission(
        db,
        key=key,
        task_id=task.id,
        request_hash=payload_hash,
        user_id=current_user.id,
    )
    if existing_retry is not None:
        return _task_response_for_user(db, task, current_user)

    if task.status in {"Pending", "In Progress", "Returned"}:
        from app.services.farm_event_service import assert_task_available
        assert_task_available(db, task)

    if task.activity_date > farm_today():
        raise HTTPException(status_code=400, detail="A future task cannot be submitted yet.")

    correction_only = bool(payload.correction_only)
    if correction_only:
        if not _manager(current_user):
            raise HTTPException(status_code=403, detail="Only managers can correct completed task resource usage.")
        if task.status != "Completed":
            raise HTTPException(status_code=400, detail="Usage correction is only available for completed tasks.")
        prior_submission = _latest_submission(db, task.id)
        if prior_submission is None or prior_submission.review_status != "Approved":
            raise HTTPException(status_code=400, detail="This completed task has no approved performed-work submission to correct.")
    elif task.status not in {"Pending", "In Progress", "Returned"}:
        raise HTTPException(status_code=400, detail="This task is not currently open for submission.")

    assisted_submission = payload.performed_by_employee_id is not None
    if payload.approve_now and not (assisted_submission and _manager(current_user)):
        raise HTTPException(status_code=403, detail="Only a manager-assisted submission can be approved immediately.")
    if payload.approve_now and task.source_module == "Crop" and task.source_type == "crop_harvest":
        raise HTTPException(
            status_code=400,
            detail="Harvest tasks must be reviewed in Task Management so the manager can confirm Partial Harvest or Final Harvest before the crop lifecycle is changed.",
        )
    if correction_only and not assisted_submission:
        raise HTTPException(status_code=400, detail="A completed usage correction must identify the employee who performed the original work.")
    if assisted_submission:
        if not _manager(current_user):
            raise HTTPException(status_code=403, detail="Only managers can use assisted submission.")
        if not correction_only and (task.needs_reassignment or task.assigned_employee_id is None):
            raise HTTPException(
                status_code=400,
                detail="Reassign this task to an available employee before recording work on their behalf.",
            )
        performer = _employee_or_404(db, payload.performed_by_employee_id, active_only=False)
        if not str(payload.assisted_reason or "").strip():
            raise HTTPException(status_code=400, detail="Enter why the manager is recording this work on behalf of the employee.")
    else:
        performer = own_employee
        if performer is None and _manager(current_user):
            if task.assigned_employee_id:
                performer = _employee_or_404(db, task.assigned_employee_id)
            else:
                raise HTTPException(status_code=400, detail="Assign an employee before submitting this task.")
    if performer is None:
        raise HTTPException(status_code=400, detail="No employee profile is linked to this submission.")
    if task.assigned_employee_id and performer.id != task.assigned_employee_id and not _manager(current_user):
        raise HTTPException(status_code=403, detail="This task is assigned to another employee.")

    observation = validate_task_observation(db, task, payload.monitoring)
    if observation is None and task.source_type in MONITORING_TYPES:
        raise HTTPException(400, "This monitoring task is missing its resource context. Verify source_type and source_record_id.")

    if observation is not None and (payload.approve_now or correction_only):
        raise HTTPException(400, "Monitoring observations require explicit review. Submit for review instead of Approve Now or usage correction.")
    evidence_assets = _resolve_submission_evidence(db, task=task, payload=payload)
    if (task.requires_evidence or observation is not None) and not correction_only and not evidence_assets:
        raise HTTPException(status_code=400, detail="Evidence is required for this task. Upload a task photo first.")

    if task.source_module == "Crop" and task.source_type == "crop_harvest":
        if payload.actual_quantity is None or float(payload.actual_quantity) <= 0:
            raise HTTPException(status_code=400, detail="Enter the actual harvested quantity before submitting this harvest task.")
        if assisted_submission and not payload.actual_quantity_confirmed:
            raise HTTPException(
                status_code=400,
                detail="Confirm that the entered kg is the employee's actual harvested yield.",
            )
        if str(payload.actual_unit or "").strip().lower() not in {"kg", "kilogram", "kilograms"}:
            raise HTTPException(status_code=400, detail="Crop harvest task yield must be submitted in kg.")
        if payload.harvest_type_intent not in {"Partial Harvest", "Final Harvest"}:
            raise HTTPException(status_code=400, detail="Choose whether this occurrence is a Partial Harvest or Final Harvest before submitting it for manager confirmation.")

    resource_profile = _task_resource_profile(db, task)
    if payload.inventory_item_id is not None:
        if not (assisted_submission and _manager(current_user)):
            raise HTTPException(status_code=403, detail="Only a manager-assisted submission can link an inventory resource to a task.")
        if task.source_module not in {"Crop", "Livestock"} or not task.source_record_id:
            raise HTTPException(status_code=400, detail="This task is not linked to a Crop or Livestock record, so inventory usage cannot be attached safely.")
        selected_item = db.get(InventoryItem, payload.inventory_item_id)
        if selected_item is None or selected_item.is_archived:
            raise HTTPException(status_code=400, detail="Selected inventory resource is missing or archived.")
        _validate_task_resource_choice(
            module=task.source_module,
            item=selected_item,
            task_text=" ".join([task.name, task.category, task.instructions or ""]),
        )
        if task.source_type == "livestock_feeding":
            if _normalize_resource_text(selected_item.category) not in {"livestock feed", "animal feed", "feed", "feeds"}:
                raise HTTPException(status_code=400, detail="A livestock feeding task must use an inventory item categorized as Livestock Feed or Animal Feed.")
            livestock = db.get(Livestock, task.source_record_id)
            if livestock is None or livestock.is_archived:
                raise HTTPException(status_code=400, detail="Linked livestock record is unavailable.")
            livestock.feed_inventory_item_id = selected_item.id
        task.planned_inventory_item_id = selected_item.id
        task.planned_unit = selected_item.unit
        task.planned_usage_type = _infer_usage_type(task.source_module, selected_item, task)
        resource_profile = _task_resource_profile(db, task)

    if resource_profile["required"] and not resource_profile["linked"]:
        raise HTTPException(
            status_code=400,
            detail="This task uses a tracked resource but no inventory item is linked. A manager must link the correct inventory resource first.",
        )

    if resource_profile["required"]:
        item = resource_profile["item"]
        if payload.actual_quantity is None or float(payload.actual_quantity) <= 0:
            label = "feed" if task.source_type == "livestock_feeding" else "resource"
            raise HTTPException(status_code=400, detail=f"Enter the actual {label} quantity used before submitting.")
        if assisted_submission and not payload.actual_quantity_confirmed:
            raise HTTPException(
                status_code=400,
                detail="Confirm that the entered quantity is the actual amount used, not only the planned amount.",
            )
        if not str(payload.actual_unit or "").strip():
            raise HTTPException(status_code=400, detail=f"Enter the actual resource unit ({item.unit}).")
        if not _same_unit(payload.actual_unit, item.unit):
            raise HTTPException(
                status_code=400,
                detail=f"Actual resource usage must use the inventory unit ({item.unit}).",
            )
        # Persist the exact inventory item resolved for this occurrence. This
        # makes pending reservations and later approval deterministic even for
        # feeding/vaccination tasks whose item was inherited from the source record.
        task.planned_inventory_item_id = item.id
        task.planned_unit = item.unit
        task.planned_usage_type = resource_profile.get("usage_type") or _infer_usage_type(task.source_module, item, task)

    override_reason = str(payload.inventory_override_reason or "").strip() or None
    allow_negative_inventory = bool(payload.allow_negative_inventory)
    if allow_negative_inventory:
        if not _manager(current_user):
            raise HTTPException(status_code=403, detail="Only an authorized manager/administrator can allow negative inventory.")
        if not resource_profile["required"]:
            raise HTTPException(status_code=400, detail="Negative-inventory override applies only to resource-linked tasks.")
        if not override_reason:
            raise HTTPException(status_code=400, detail="Enter a reason for the negative-inventory override.")
    elif override_reason:
        raise HTTPException(status_code=400, detail="Enable the negative-inventory override before entering an override reason.")

    # Normal submissions only reserve/check inventory. They do not create a
    # stock movement until an Admin/Manager approves the submission. Assisted
    # Submit & Approve and manager corrections are already approved actions, so
    # they post inventory immediately in the approval branch below.
    waits_for_review = not correction_only and not (assisted_submission and payload.approve_now)
    if resource_profile["required"] and waits_for_review:
        _validate_pending_inventory_reservation(
            db,
            task=task,
            item=resource_profile["item"],
            actual_quantity=float(payload.actual_quantity),
            allow_negative_inventory=allow_negative_inventory,
        )

    worker_notes = (payload.worker_notes or "").strip() or None
    if assisted_submission:
        note_label = "Usage correction reason" if correction_only else "Assisted submission reason"
        assisted_note = f"{note_label}: {str(payload.assisted_reason).strip()}"
        audit_notes = [assisted_note]
        if not correction_only and task.assigned_employee_id is None:
            audit_notes.append("Original assignment: Unassigned")
            task.assigned_employee_id = performer.id
            task.assigned_to = performer.full_name
            task.assignment_source = "manager_override"
            record_assignment_change(
                db,
                task,
                old_employee_id=None,
                new_employee_id=performer.id,
                assignment_source="manager_override",
                actor_user_id=current_user.id,
                actor_name=current_user.full_name,
                reason="Manager assigned the previously unassigned task during assisted submission.",
            )
        audit_note = "\n".join(audit_notes)
        worker_notes = f"{audit_note}\n{worker_notes}" if worker_notes else audit_note

    previous = _latest_submission(db, task.id)
    attempt = (previous.attempt_number if previous else 0) + 1
    submission = TaskSubmission(
        monitoring_data_json=json.dumps(observation.model_dump(mode="json")) if observation else None,
        activity_id=task.id,
        employee_id=performer.id,
        recorded_by_user_id=current_user.id,
        attempt_number=attempt,
        idempotency_key=key,
        request_hash=payload_hash if key else None,
        actual_quantity=payload.actual_quantity,
        actual_unit=(resource_profile["item"].unit if resource_profile["required"] else (payload.actual_unit or None)),
        harvest_type_intent=(payload.harvest_type_intent if task.source_module == "Crop" and task.source_type == "crop_harvest" else None),
        evidence_url=evidence_url(evidence_assets[0].public_id) if evidence_assets else None,
        worker_notes=worker_notes,
        problem_report=(payload.problem_report or "").strip() or None,
        inventory_override_used=allow_negative_inventory,
        inventory_override_reason=override_reason,
        review_status="Approved" if correction_only else "Submitted",
    )
    db.add(submission)
    try:
        # Flush the attempt/idempotency constraints before any stock movement.
        # A racing duplicate can therefore never reach the deduction section.
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if key:
            existing = _existing_idempotent_submission(
                db,
                key=key,
                task_id=task_id,
                request_hash=payload_hash,
                user_id=current_user.id,
            )
            if existing is not None:
                retry_task = _task_or_404(db, task_id)
                return _task_response_for_user(db, retry_task, current_user)
        raise HTTPException(
            status_code=409,
            detail="Another submission for this task was recorded at the same time. Refresh the task before retrying.",
        ) from exc

    attached_at = datetime.now()
    for evidence in evidence_assets:
        evidence.submission_id = submission.id
        evidence.status = "Attached"
        evidence.attached_at = attached_at
        evidence.expires_at = None

    immediate_approval = correction_only or (assisted_submission and payload.approve_now)
    if immediate_approval and resource_profile["required"]:
        _post_submission_inventory_on_approval(
            db,
            task=task,
            submission=submission,
            current_user=current_user,
        )
    elif task.source_type == "livestock_feeding":
        # Keep the reported feeding details available to the Livestock page,
        # but do not deduct feed while the submission is waiting for review.
        _sync_feeding_usage(
            db,
            task=task,
            submission=submission,
            actual_quantity=float(payload.actual_quantity),
            current_user=current_user,
            allow_negative_inventory=allow_negative_inventory,
            override_reason=override_reason,
            post_inventory=False,
        )

    task.problem_report = submission.problem_report
    task.needs_reassignment = False
    if correction_only:
        submission.review_status = "Approved"
        submission.reviewed_by_user_id = current_user.id
        submission.reviewed_at = datetime.now()
        submission.review_feedback = "Completed-task resource usage corrected by manager/administrator."
        task.status = "Completed"
        _sync_approved_vaccination_task(db, task=task, submission=submission, current_user=current_user)
    elif assisted_submission and payload.approve_now:
        # This is the only immediate-completion path: an authorized manager is
        # explicitly recording work on behalf of the employee and choosing
        # Approve Now. Normal employee submissions never self-approve.
        submission.review_status = "Approved"
        submission.reviewed_by_user_id = current_user.id
        submission.reviewed_at = datetime.now()
        submission.review_feedback = "Approved during assisted submission by manager/administrator."
        task.status = "Completed"
        task.completed_at = datetime.now()
        task.requires_review = True
        _sync_approved_vaccination_task(db, task=task, submission=submission, current_user=current_user)
    else:
        # Submission, evidence attachment, inventory reservation, and the
        # status transition are committed together below. Actual inventory
        # deduction waits for Admin/Manager approval. requires_review is
        # normalized here as a safety net for legacy/automatic tasks that were
        # stored with the old false default.
        submission.review_status = "Submitted"
        task.requires_review = True
        task.status = "Submitted for Review"
        task.completed_at = None
    db.commit()
    db.refresh(task)
    return _task_response_for_user(db, task, current_user)


@router.get("/tasks/{task_id}/review-report", response_model=TaskReviewReportResponse)
def get_task_review_report(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "get_task_review_report")
    task = _task_or_404(db, task_id)
    submissions = list(
        db.scalars(
            select(TaskSubmission)
            .where(TaskSubmission.activity_id == task.id)
            .order_by(TaskSubmission.attempt_number.desc(), TaskSubmission.id.desc())
        ).all()
    )
    current_submission = submissions[0] if submissions else None
    if (
        task.status != "Submitted for Review"
        or current_submission is None
        or current_submission.review_status != "Submitted"
    ):
        raise HTTPException(
            status_code=409,
            detail="This submission is no longer awaiting review. Refresh Task Management to see the latest status.",
        )

    task_response = _task_response(db, task)
    current_response = _submission_response(db, current_submission)
    previous_responses = [
        _submission_response(db, row) for row in submissions[1:]
    ]

    usage = db.scalar(
        select(ResourceUsage)
        .where(ResourceUsage.activity_id == task.id)
        .order_by(ResourceUsage.id.desc())
    )
    movements = []
    movement_reference = None
    if usage is not None:
        movement_rows = list(
            db.scalars(
                select(InventoryStockRecord)
                .where(InventoryStockRecord.resource_usage_id == usage.id)
                .order_by(InventoryStockRecord.id)
            ).all()
        )
        movement_user_ids = {
            int(row.recorded_by_user_id)
            for row in movement_rows
            if row.recorded_by_user_id
        }
        movement_users = (
            {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(movement_user_ids))).all()}
            if movement_user_ids else {}
        )
        movements = [
            TaskReviewMovementResponse(
                id=row.id,
                movement_type=row.adjustment_type,
                quantity=float(row.quantity),
                previous_quantity=float(row.previous_quantity),
                new_quantity=float(row.new_quantity),
                movement_date=row.adjustment_date,
                reference=row.reference,
                recorded_by_name=movement_users.get(row.recorded_by_user_id),
                created_at=row.created_at,
            )
            for row in movement_rows
        ]
        if movement_rows:
            latest_movement = movement_rows[-1]
            movement_reference = (
                f"{latest_movement.reference} · Stock movement #{latest_movement.id}"
                if latest_movement.reference else f"Stock movement #{latest_movement.id}"
            )

    resource_item = db.get(InventoryItem, usage.inventory_item_id) if usage is not None else None
    planned_quantity = task_response.planned_quantity
    actual_quantity = current_response.actual_quantity if current_response else None
    quantity_difference = (
        round(float(actual_quantity) - float(planned_quantity), 3)
        if actual_quantity is not None and planned_quantity is not None else None
    )
    tracked = bool(task_response.resource_linked or usage is not None)
    if usage is None:
        if not tracked:
            deduction_status = "Not Required"
        elif task.status == "Submitted for Review" and current_submission is not None and current_submission.review_status == "Submitted":
            deduction_status = "Reserved - Awaiting Approval"
        elif task.status == "Returned":
            deduction_status = "Not Deducted - Returned"
        elif task.status == "Voided":
            deduction_status = "Not Deducted - Voided"
        else:
            deduction_status = "Not Deducted"
    elif usage.is_voided:
        deduction_status = "Reversed"
    elif usage.task_posting_active:
        deduction_status = "Deducted on Approval"
    else:
        deduction_status = "Posted"

    harvest_crop = (
        db.get(Crop, task.source_record_id)
        if task.source_module == "Crop" and task.source_type == "crop_harvest" and task.source_record_id else None
    )
    return TaskReviewReportResponse(
        task=task_response,
        current_submission=current_response,
        previous_submissions=[item for item in previous_responses if item is not None],
        crop_status=harvest_crop.status if harvest_crop else None,
        harvest_approval_blocker=(
            harvest_approval_blocker(
                db, crop=harvest_crop, harvest_date=task.activity_date, related_task_id=task.id,
            ) if harvest_crop else "The crop linked to this harvest task is unavailable."
            if task.source_module == "Crop" and task.source_type == "crop_harvest" else None
        ),
        resource_usage=TaskReviewResourceResponse(
            tracked=tracked,
            inventory_item_id=(resource_item.id if resource_item else task_response.planned_inventory_item_id),
            inventory_item_code=(resource_item.item_code if resource_item else task_response.planned_inventory_item_code),
            inventory_item_name=(resource_item.name if resource_item else task_response.planned_inventory_item_name),
            inventory_category=(resource_item.category if resource_item else task_response.planned_inventory_category),
            planned_quantity=planned_quantity,
            planned_unit=task_response.planned_unit,
            actual_quantity=actual_quantity,
            actual_unit=current_response.actual_unit if current_response else None,
            quantity_difference=quantity_difference,
            deduction_status=deduction_status,
            resource_usage_id=usage.id if usage is not None else None,
            movement_reference=movement_reference,
            movements=movements,
        ),
    )


@router.post("/tasks/{task_id}/review", response_model=TaskResponse)
def review_task(
    task_id: int,
    payload: TaskReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "review_task")
    acquire_transaction_lock(db, f"workforce-task-lifecycle:{task_id}")
    task = _task_locked_or_404(db, task_id)
    if payload.decision not in {"Approve", "Return"}:
        raise HTTPException(400, "Pending submissions can only be approved or returned for correction. Use Void Work on eligible approved, completed tasks.")
    submission = _latest_submission(db, task.id)
    if submission is None or task.status != "Submitted for Review" or submission.review_status != "Submitted":
        raise HTTPException(
            status_code=409,
            detail="This submission is no longer awaiting review. Refresh Task Management to see the latest status.",
        )

    if payload.decision == "Approve" and task.source_module == "Crop" and task.source_type == "crop_harvest":
        if submission.actual_quantity is None or float(submission.actual_quantity) <= 0:
            raise HTTPException(status_code=400, detail="The harvest submission has no valid actual yield quantity.")
        if str(submission.actual_unit or "").strip().lower() not in {"kg", "kilogram", "kilograms"}:
            raise HTTPException(status_code=400, detail="The submitted crop yield must use kg before approval.")
        if payload.harvest_type is None:
            raise HTTPException(status_code=400, detail="Choose Partial Harvest or Final Harvest before approving this harvest task.")
        reported_type = str(submission.harvest_type_intent or "").strip() or None
        if reported_type and payload.harvest_type != reported_type and not str(payload.feedback or "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The employee submitted this as {reported_type}. Enter reviewer feedback explaining why it is being confirmed as {payload.harvest_type}."
                ),
            )
        crop = db.get(Crop, task.source_record_id) if task.source_record_id else None
        if crop is None:
            raise HTTPException(status_code=400, detail="The crop linked to this harvest task is unavailable.")
        record_harvest(
            db,
            crop=crop,
            harvest_date=task.activity_date,
            quantity_kg=float(submission.actual_quantity),
            harvest_type=payload.harvest_type,
            actor=current_user,
            performed_by_employee_id=submission.employee_id,
            related_task_id=task.id,
            manual_reason=None,
            notes=submission.worker_notes,
            evidence_url=submission.evidence_url,
            final_harvest_confirmed=payload.final_harvest_confirmed,
            allow_completed_crop_for_linked_review=True,
        )
        submission.harvest_type_confirmed = payload.harvest_type

    if payload.decision == "Approve":
        post_approved_observation(db, task, submission, payload, current_user)

    submission.reviewed_by_user_id = current_user.id
    submission.reviewed_at = datetime.now()
    submission.review_feedback = (payload.feedback or "").strip() or None
    if payload.decision == "Approve":
        # Approval is the authoritative inventory-posting point. create/update
        # usage locks and rechecks the inventory row before deducting, so stock
        # cannot silently go negative if availability changed after submission.
        _post_submission_inventory_on_approval(
            db,
            task=task,
            submission=submission,
            current_user=current_user,
        )
        submission.review_status = "Approved"
        task.status = "Completed"
        task.completed_at = datetime.now()
        task.problem_report = None
        _sync_approved_vaccination_task(db, task=task, submission=submission, current_user=current_user)
    elif payload.decision == "Return":
        # Returning a pending submission releases its logical reservation. No
        # stock movement exists yet, so the employee can correct and resubmit.
        submission.review_status = "Returned"
        task.status = "Returned"
        task.completed_at = None
    db.commit()
    db.refresh(task)
    return _task_response(db, task)


@router.post("/tasks/{task_id}/void", response_model=TaskResponse)
def void_task(
    task_id: int,
    payload: TaskVoidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_void_administrator(current_user)
    try:
        task = _void_approved_task(db, task_id, payload.reason, current_user)
        db.commit()
        db.refresh(task)
        return _task_response(db, task)
    except Exception:
        db.rollback()
        raise


def _void_approved_task(db, task_id, reason, current_user):
    acquire_transaction_lock(db, f"workforce-task-lifecycle:{task_id}")
    task = _task_locked_or_404(db, task_id)
    submission = _latest_submission(db, task.id)
    blocker = _task_void_block_reason(task, submission)
    if blocker:
        raise HTTPException(status_code=409, detail=blocker)

    reason = reason.strip()
    approved_by = submission.reviewed_by_user_id
    approved_at = submission.reviewed_at
    approval_feedback = submission.review_feedback
    reversed_usage = _reverse_task_resource_usage(db, task=task, current_user=current_user, reason=reason)
    _add_workforce_audit(
        db, current_user=current_user, action="Voided approved work",
        entity_id=task.activity_code, record_name=task.name,
        details=(f"Submission {submission.id}; approved by user {approved_by or 'Not recorded'} at {approved_at or 'Not recorded'}. "
                 f"Original approval feedback: {approval_feedback or 'None'}. Reason: {reason}. "
                 f"Inventory usage reversed: {reversed_usage.id if reversed_usage else 'None required'}."),
    )
    submission.review_status = "Voided"
    submission.reviewed_by_user_id = current_user.id
    submission.reviewed_at = datetime.now()
    submission.review_feedback = reason
    task.status = "Voided"
    task.completed_at = None
    return task


@router.post("/tasks/{task_id}/resolve", response_model=TaskResponse)
def resolve_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "resolve_task")
    task = _task_locked_or_404(db, task_id)
    from app.services.farm_event_service import assert_task_available
    assert_task_available(db, task)
    if (task.status not in {"Pending", "In Progress", "Returned"}
        or _latest_submission(db, task.id) is not None
        or db.scalar(select(ResourceUsage.id).where(ResourceUsage.activity_id == task.id).limit(1)) is not None):
        raise HTTPException(400, "Submitted, completed or posted work cannot be converted to a resolved reminder. Use task review, authorized correction or Owner/Admin void.")
    task.status = "Resolved"
    task.completed_at = None
    db.commit()
    db.refresh(task)
    return _task_response(db, task)


def _add_workforce_audit(
    db: Session,
    *,
    current_user: User,
    action: str,
    entity_id: str,
    record_name: str,
    details: str,
    icon: str = "calendar_month",
) -> None:
    common = {
        "action": action,
        "module": "Workforce",
        "record_name": record_name,
        "entity_id": entity_id,
        "details": details,
        "icon": icon,
        "actor_user_id": current_user.id,
        "actor_name": current_user.full_name,
    }
    db.add(AuditLog(event_type="audit", **common))
    db.add(AuditLog(event_type="timeline", **common))


@router.get("/calendar/config", response_model=CalendarConfigResponse)
def get_calendar_config(
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "get_calendar_config")
    return CalendarConfigResponse(timezone=farm_timezone_name(), today=farm_today())


def _leave_overlap(
    db: Session,
    *,
    employee_id: int,
    start_date: date,
    end_date: date,
    exclude_leave_id: int | None = None,
) -> StaffLeave | None:
    stmt = select(StaffLeave).where(
        StaffLeave.employee_id == employee_id,
        StaffLeave.start_date <= end_date,
        StaffLeave.end_date >= start_date,
        StaffLeave.status.in_(["Pending", "Approved"]),
    )
    if exclude_leave_id is not None:
        stmt = stmt.where(StaffLeave.id != exclude_leave_id)
    return db.scalar(stmt.order_by(StaffLeave.start_date, StaffLeave.id))


def _leave_shift_conflicts(
    db: Session,
    *,
    employee_id: int,
    start_date: date,
    end_date: date,
    exclude_shift_id: int | None = None,
) -> list[StaffShift]:
    stmt = select(StaffShift).where(
        StaffShift.employee_id == employee_id,
        StaffShift.work_date >= start_date,
        StaffShift.work_date <= end_date,
        StaffShift.status != "Cancelled",
    )
    if exclude_shift_id is not None:
        stmt = stmt.where(StaffShift.id != exclude_shift_id)
    return list(db.scalars(stmt.order_by(StaffShift.work_date, StaffShift.id)).all())


def _approved_leave_for_date(
    db: Session,
    *,
    employee_id: int,
    work_date: date,
) -> StaffLeave | None:
    return db.scalar(
        select(StaffLeave).where(
            StaffLeave.employee_id == employee_id,
            StaffLeave.start_date <= work_date,
            StaffLeave.end_date >= work_date,
            StaffLeave.status == "Approved",
        )
    )


def _leave_response(db: Session, record: StaffLeave) -> LeaveResponse:
    employee = db.get(Employee, record.employee_id)
    requested_by = db.get(User, record.requested_by_user_id) if record.requested_by_user_id else None
    reviewed_by = db.get(User, record.decided_by_user_id) if record.decided_by_user_id else None
    cancelled_by = db.get(User, record.cancelled_by_user_id) if record.cancelled_by_user_id else None
    default_cover = db.get(Employee, record.default_covering_employee_id) if record.default_covering_employee_id else None
    affected_count = int(
        db.scalar(
            select(func.count(FarmActivity.id)).where(
                FarmActivity.assigned_employee_id == record.employee_id,
                FarmActivity.activity_date >= record.start_date,
                FarmActivity.activity_date <= record.end_date,
                FarmActivity.is_archived == False,
            )
        ) or 0
    )
    return LeaveResponse(
        id=record.id,
        employee_id=record.employee_id,
        employee_name=employee.full_name if employee else None,
        leave_type=record.leave_type,
        start_date=record.start_date,
        end_date=record.end_date,
        request_date=record.created_at,
        status=record.status,
        reason=record.reason,
        recorded_by_user_id=record.recorded_by_user_id,
        requested_by_user_id=record.requested_by_user_id,
        requested_by_name=requested_by.full_name if requested_by else None,
        decided_by_user_id=record.decided_by_user_id,
        reviewed_by_name=reviewed_by.full_name if reviewed_by else None,
        decided_at=record.decided_at,
        decision_notes=record.decision_notes,
        default_covering_employee_id=record.default_covering_employee_id,
        default_covering_employee_name=default_cover.full_name if default_cover else None,
        coverage_reason=record.coverage_reason,
        affected_task_count=affected_count,
        cancelled_by_user_id=record.cancelled_by_user_id,
        cancelled_by_name=cancelled_by.full_name if cancelled_by else None,
        cancelled_at=record.cancelled_at,
        cancellation_reason=record.cancellation_reason,
    )


def _calendar_leave_responses(
    db: Session,
    leave_rows: list[StaffLeave],
    task_rows: list[FarmActivity],
) -> list[LeaveResponse]:
    """Serialize calendar leave rows with fixed-count bulk lookups.

    The generic leave serializer intentionally resolves related users and task
    counts record-by-record because it is also used for individual review
    operations. The range calendar can contain many leave rows, so it uses
    this scoped serializer to avoid N+1 database queries.
    """
    if not leave_rows:
        return []

    employee_ids = {int(row.employee_id) for row in leave_rows if row.employee_id}
    employee_ids.update(
        int(row.default_covering_employee_id)
        for row in leave_rows
        if row.default_covering_employee_id
    )
    employees = {
        row.id: row
        for row in db.scalars(select(Employee).where(Employee.id.in_(employee_ids))).all()
    } if employee_ids else {}

    user_ids: set[int] = set()
    for row in leave_rows:
        for user_id in (row.requested_by_user_id, row.decided_by_user_id, row.cancelled_by_user_id):
            if user_id:
                user_ids.add(int(user_id))
    users = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}

    result: list[LeaveResponse] = []
    for record in leave_rows:
        employee = employees.get(record.employee_id)
        requested_by = users.get(record.requested_by_user_id)
        reviewed_by = users.get(record.decided_by_user_id)
        cancelled_by = users.get(record.cancelled_by_user_id)
        default_cover = employees.get(record.default_covering_employee_id)
        affected_count = sum(
            1
            for task in task_rows
            if not task.is_archived
            and task.assigned_employee_id == record.employee_id
            and record.start_date <= task.activity_date <= record.end_date
        )
        result.append(LeaveResponse(
            id=record.id,
            employee_id=record.employee_id,
            employee_name=employee.full_name if employee else None,
            leave_type=record.leave_type,
            start_date=record.start_date,
            end_date=record.end_date,
            request_date=record.created_at,
            status=record.status,
            reason=record.reason,
            recorded_by_user_id=record.recorded_by_user_id,
            requested_by_user_id=record.requested_by_user_id,
            requested_by_name=requested_by.full_name if requested_by else None,
            decided_by_user_id=record.decided_by_user_id,
            reviewed_by_name=reviewed_by.full_name if reviewed_by else None,
            decided_at=record.decided_at,
            decision_notes=record.decision_notes,
            default_covering_employee_id=record.default_covering_employee_id,
            default_covering_employee_name=default_cover.full_name if default_cover else None,
            coverage_reason=record.coverage_reason,
            affected_task_count=affected_count,
            cancelled_by_user_id=record.cancelled_by_user_id,
            cancelled_by_name=cancelled_by.full_name if cancelled_by else None,
            cancelled_at=record.cancelled_at,
            cancellation_reason=record.cancellation_reason,
        ))
    return result


def _calendar_payload(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    employee_id: int | None,
    current_user: User,
) -> dict:
    task_stmt = select(FarmActivity).where(
        FarmActivity.activity_date >= date_from,
        FarmActivity.activity_date <= date_to,
        FarmActivity.is_archived == False,
    )
    att_stmt = select(StaffAttendance).where(
        StaffAttendance.attendance_date >= date_from,
        StaffAttendance.attendance_date <= date_to,
    )
    leave_stmt = select(StaffLeave).where(
        StaffLeave.start_date <= date_to,
        StaffLeave.end_date >= date_from,
    )
    shift_stmt = select(StaffShift).where(
        StaffShift.work_date >= date_from,
        StaffShift.work_date <= date_to,
    )
    if employee_id:
        task_stmt = task_stmt.where(FarmActivity.assigned_employee_id == employee_id)
        att_stmt = att_stmt.where(StaffAttendance.employee_id == employee_id)
        leave_stmt = leave_stmt.where(StaffLeave.employee_id == employee_id)
        shift_stmt = shift_stmt.where(StaffShift.employee_id == employee_id)
    task_rows = list(db.scalars(task_stmt.order_by(FarmActivity.activity_date, FarmActivity.start_time, FarmActivity.id)).all())
    attendance_rows = list(db.scalars(att_stmt.order_by(StaffAttendance.attendance_date, StaffAttendance.id)).all())
    leave_rows = list(db.scalars(leave_stmt.order_by(StaffLeave.start_date, StaffLeave.id)).all())
    shift_rows = list(db.scalars(shift_stmt.order_by(StaffShift.work_date, StaffShift.start_time, StaffShift.id)).all())
    if employee_id:
        availability_employee_ids = [employee_id]
    else:
        availability_employee_ids = [row.id for row in db.scalars(select(Employee).where(Employee.is_archived == False)).all()]
    availability_rows = resolve_availability_range(db, availability_employee_ids, date_from, date_to)
    from app.routers.farm_events import calendar_events
    return {
        "timezone": farm_timezone_name(),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "tasks": [row.model_dump(mode="json") for row in _task_responses(db, task_rows, current_user)],
        "attendance": [AttendanceResponse.model_validate(x).model_dump(mode="json") for x in attendance_rows],
        "leave": [row.model_dump(mode="json") for row in _calendar_leave_responses(db, leave_rows, task_rows)],
        "shifts": [ShiftResponse.model_validate(x).model_dump(mode="json") for x in shift_rows],
        "availability": [AvailabilityDayResponse(**row.as_dict()).model_dump(mode="json") for row in availability_rows],
        "farm_events": calendar_events(db, date_from, date_to, current_user, employee_id=employee_id),
    }


@router.get("/availability", response_model=list[AvailabilityDayResponse])
def availability_range(
    date_from: date,
    date_to: date,
    employee_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "availability_range")
    if date_to < date_from or (date_to - date_from).days > 93:
        raise HTTPException(status_code=400, detail="Availability range must be between 1 and 94 days.")
    ids = [employee_id] if employee_id else [row.id for row in db.scalars(select(Employee).where(Employee.is_archived == False)).all()]
    return [AvailabilityDayResponse(**row.as_dict()) for row in resolve_availability_range(db, ids, date_from, date_to)]


@router.get("/attendance", response_model=list[AttendanceResponse])
def list_attendance(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    employee_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "list_attendance")
    stmt = select(StaffAttendance).order_by(StaffAttendance.attendance_date.desc(), StaffAttendance.id.desc())
    if employee_id:
        stmt = stmt.where(StaffAttendance.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(StaffAttendance.attendance_date >= date_from)
    if date_to:
        stmt = stmt.where(StaffAttendance.attendance_date <= date_to)
    rows = list(db.scalars(stmt).all())
    return [AttendanceResponse(**attendance_response_dict(db, row)) for row in rows]


@router.get("/my-attendance/today", response_model=AttendanceResponse | None)
def my_attendance_today(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "my_attendance_today")
    employee = _employee_for_user_or_error(db, current_user)
    today = farm_today()
    row = db.scalar(select(StaffAttendance).where(
        StaffAttendance.employee_id == employee.id,
        StaffAttendance.attendance_date == today,
    ))
    if row is None:
        return None
    return AttendanceResponse(**attendance_response_dict(db, row))


@router.get("/my-attendance/history", response_model=list[AttendanceResponse])
def my_attendance_history(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "my_attendance_history")
    employee = _employee_for_user_or_error(db, current_user)
    stmt = select(StaffAttendance).where(StaffAttendance.employee_id == employee.id)
    if date_from:
        stmt = stmt.where(StaffAttendance.attendance_date >= date_from)
    if date_to:
        stmt = stmt.where(StaffAttendance.attendance_date <= date_to)
    rows = list(db.scalars(stmt.order_by(StaffAttendance.attendance_date.desc(), StaffAttendance.id.desc())).all())
    return [AttendanceResponse(**attendance_response_dict(db, row)) for row in rows]


def _attendance_error(error: AttendanceError):
    raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/my-attendance/check-in", response_model=AttendanceResponse)
def my_attendance_check_in(
    payload: AttendanceActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "my_attendance_check_in")
    employee = _employee_for_user_or_error(db, current_user)
    try:
        record = attendance_check_in(
            db, employee.id, actor_user_id=current_user.id, actor_name=current_user.full_name,
            source=SELF_SERVICE, notes=payload.notes,
        )
        db.commit(); db.refresh(record)
        return AttendanceResponse(**attendance_response_dict(db, record))
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.post("/my-attendance/check-out", response_model=AttendanceResponse)
def my_attendance_check_out(
    payload: AttendanceActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "my_attendance_check_out")
    employee = _employee_for_user_or_error(db, current_user)
    try:
        record = attendance_check_out(
            db, employee.id, actor_user_id=current_user.id, actor_name=current_user.full_name,
            source=SELF_SERVICE, notes=payload.notes,
        )
        db.commit(); db.refresh(record)
        return AttendanceResponse(**attendance_response_dict(db, record))
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.post("/attendance/{employee_id}/assisted-check-in", response_model=AttendanceResponse)
def manager_attendance_check_in(
    employee_id: int,
    payload: AttendanceActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "manager_attendance_check_in")
    _employee_or_404(db, employee_id)
    try:
        record = attendance_check_in(
            db, employee_id, actor_user_id=current_user.id, actor_name=current_user.full_name,
            source=MANAGER_ASSISTED, notes=payload.notes,
        )
        db.commit(); db.refresh(record)
        return AttendanceResponse(**attendance_response_dict(db, record))
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.post("/attendance/{employee_id}/assisted-check-out", response_model=AttendanceResponse)
def manager_attendance_check_out(
    employee_id: int,
    payload: AttendanceActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "manager_attendance_check_out")
    _employee_or_404(db, employee_id)
    try:
        record = attendance_check_out(
            db, employee_id, actor_user_id=current_user.id, actor_name=current_user.full_name,
            source=MANAGER_ASSISTED, notes=payload.notes,
        )
        db.commit(); db.refresh(record)
        return AttendanceResponse(**attendance_response_dict(db, record))
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.post("/attendance/{employee_id}/{work_date}/status", response_model=AttendanceResponse)
def manager_attendance_status(
    employee_id: int,
    work_date: date,
    payload: AttendanceStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "manager_attendance_status")
    _employee_or_404(db, employee_id)
    try:
        record, _coverage = set_confirmed_status(
            db, employee_id, work_date, status=payload.status, actor_user_id=current_user.id,
            actor_name=current_user.full_name, notes=payload.notes,
        )
        db.commit(); db.refresh(record)
        return AttendanceResponse(**attendance_response_dict(db, record))
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.put("/attendance/{employee_id}/{work_date}/correction", response_model=AttendanceResponse)
def manager_attendance_correction(
    employee_id: int,
    work_date: date,
    payload: AttendanceCorrectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "manager_attendance_correction")
    _employee_or_404(db, employee_id)
    try:
        record, _coverage = correct_attendance(
            db, employee_id, work_date, actor_user_id=current_user.id, actor_name=current_user.full_name,
            reason=payload.correction_reason, status=payload.status,
            **payload.model_dump(include={"check_in_at", "check_out_at"}, exclude_unset=True),
            notes=payload.notes,
        )
        db.commit(); db.refresh(record)
        return AttendanceResponse(**attendance_response_dict(db, record))
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.post("/attendance/bulk-present", response_model=AttendanceBulkResponse)
def bulk_mark_scheduled_present(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "bulk_mark_scheduled_present")
    work_date = farm_today()
    employees = list(db.scalars(select(Employee).where(Employee.is_archived == False, Employee.employment_status == "Active")).all())
    recorded = []; preserved = 0; skipped = 0; scheduled = 0
    skipped_reasons: dict[str, int] = {}
    try:
        for employee in employees:
            availability = resolve_employee_availability(db, employee.id, work_date)
            if not availability.available or availability.is_working_day is False or availability.status == "Schedule Needs Setup":
                skipped += 1
                reason = availability.status if availability.status in {"On Leave", "Rest Day", "Special Day Off", "Schedule Needs Setup"} else "Not Available"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                continue
            scheduled += 1
            existing = db.scalar(select(StaffAttendance).where(
                StaffAttendance.employee_id == employee.id,
                StaffAttendance.attendance_date == work_date,
            ))
            if existing is not None:
                preserved += 1
                continue
            row = attendance_check_in(
                db, employee.id, actor_user_id=current_user.id, actor_name=current_user.full_name,
                source=MANAGER_ASSISTED, notes="Bulk manager attendance confirmation",
            )
            # Bulk Present is factual attendance; retain server check-in time but use the neutral status.
            row.status = "Present"
            recorded.append(row)
        db.commit()
        for row in recorded: db.refresh(row)
        return AttendanceBulkResponse(
            work_date=work_date, scheduled_count=scheduled, recorded_count=len(recorded),
            preserved_count=preserved, skipped_count=skipped, skipped_reasons=skipped_reasons,
            records=[AttendanceResponse(**attendance_response_dict(db, row)) for row in recorded],
        )
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.get("/attendance/settings", response_model=AttendanceSettingsResponse)
def get_attendance_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "get_attendance_settings")
    row = get_or_create_attendance_settings(db)
    db.commit(); db.refresh(row)
    return row


@router.put("/attendance/settings", response_model=AttendanceSettingsResponse)
def update_attendance_settings(
    payload: AttendanceSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "update_attendance_settings")
    if not _manager(current_user):
        raise HTTPException(status_code=403, detail="Manager or administrator access is required to change attendance settings.")
    row = get_or_create_attendance_settings(db)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_by_user_id = current_user.id
    db.commit(); db.refresh(row)
    return row


@router.post("/attendance", response_model=AttendanceResponse)
def upsert_attendance(
    payload: AttendanceUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compatibility endpoint for older Staff Calendar clients.

    New clients use explicit assisted Check In/Out, status confirmation, and correction endpoints.
    """
    _require_workforce_access(current_user, "upsert_attendance")
    employee = _employee_or_404(db, payload.employee_id)
    existing = db.scalar(select(StaffAttendance).where(
        StaffAttendance.employee_id == payload.employee_id,
        StaffAttendance.attendance_date == payload.attendance_date,
    ))
    old_status = existing.status if existing is not None else None
    try:
        if payload.status in {"Absent", "Sick"}:
            record, _ = set_confirmed_status(
                db, payload.employee_id, payload.attendance_date, status=payload.status,
                actor_user_id=current_user.id, actor_name=current_user.full_name, notes=payload.notes,
            )
        else:
            record, _ = correct_attendance(
                db, payload.employee_id, payload.attendance_date, status=payload.status,
                actor_user_id=current_user.id, actor_name=current_user.full_name,
                reason="Legacy manager attendance update", notes=payload.notes,
            )
        _add_workforce_audit(
            db, current_user=current_user,
            action="Attendance recorded" if old_status is None else "Attendance updated",
            entity_id=f"attendance:{payload.employee_id}:{payload.attendance_date.isoformat()}",
            record_name=employee.full_name,
            details=(f"{payload.attendance_date.isoformat()}: {old_status or 'Not recorded'} -> {record.status}."
                     + (f" Notes: {record.notes}" if record.notes else "")),
            icon="event_available",
        )
        db.commit(); db.refresh(record)
        return AttendanceResponse(**attendance_response_dict(db, record))
    except AttendanceError as error:
        db.rollback(); _attendance_error(error)
    except Exception:
        db.rollback(); raise


@router.get("/leave", response_model=list[LeaveResponse])
def list_leave(
    employee_id: int | None = Query(None),
    leave_status: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "list_leave")
    stmt = select(StaffLeave).order_by(StaffLeave.created_at.desc(), StaffLeave.id.desc())
    if employee_id:
        stmt = stmt.where(StaffLeave.employee_id == employee_id)
    if leave_status:
        if leave_status not in {"Pending", "Approved", "Rejected", "Cancelled"}:
            raise HTTPException(status_code=400, detail="Invalid leave status.")
        stmt = stmt.where(StaffLeave.status == leave_status)
    return [_leave_response(db, row) for row in db.scalars(stmt).all()]


@router.get("/leave/my", response_model=list[LeaveResponse])
def my_leave_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "my_leave_requests")
    employee = _employee_for_user_or_error(db, current_user)
    rows = list(
        db.scalars(
            select(StaffLeave)
            .where(StaffLeave.employee_id == employee.id)
            .order_by(StaffLeave.created_at.desc(), StaffLeave.id.desc())
        ).all()
    )
    return [_leave_response(db, row) for row in rows]


@router.get("/leave/{leave_id}/review", response_model=LeaveReviewResponse)
def review_leave_request(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "review_leave_request")
    record = db.get(StaffLeave, leave_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Leave record not found.")

    employee = _employee_or_404(db, record.employee_id, active_only=False)
    tasks = affected_tasks_for_leave(db, record)
    overlaps = leave_overlap_context(db, record)
    candidates = covering_employee_candidates(db, leave=record, tasks=tasks)
    candidate_rows = [
        LeaveCoveringCandidateResponse(
            employee_id=row["employee"].id,
            employee_name=row["employee"].full_name,
            position=row["employee"].position,
            assigned_area=row["employee"].assigned_area,
            skills=row["employee"].skills,
            available_for_all=row["available_for_all"],
            blockers=row["blockers"],
            warnings=row["warnings"],
            task_availability=row["task_availability"],
        )
        for row in candidates
    ]
    coverage_rows = list(
        db.scalars(select(TaskLeaveCoverage).where(TaskLeaveCoverage.leave_id == record.id)).all()
    )
    assignment_summary: dict[str, int] = {}
    for row in coverage_rows:
        assignment_summary[row.status] = assignment_summary.get(row.status, 0) + 1

    availability = "Active and available for review"
    if employee.is_archived:
        availability = "Archived"
    elif employee.employment_status != "Active":
        availability = employee.employment_status
    elif record.status == "Approved":
        availability = f"Approved {record.leave_type}"

    return LeaveReviewResponse(
        leave=_leave_response(db, record),
        employee_availability=availability,
        attendance=[AttendanceResponse.model_validate(row) for row in overlaps["attendance"]],
        shifts=[
            {
                "id": row.id,
                "employee_id": row.employee_id,
                "work_date": row.work_date,
                "start_time": row.start_time,
                "end_time": row.end_time,
                "assigned_area": row.assigned_area,
                "status": row.status,
                "notes": row.notes,
            }
            for row in overlaps["shifts"]
        ],
        overlapping_leave=[_leave_response(db, row) for row in overlaps["leave"]],
        affected_tasks=_task_responses(db, tasks, current_user),
        covering_candidates=candidate_rows,
        assignment_summary=assignment_summary,
    )


@router.post("/leave", response_model=LeaveResponse, status_code=201)
def create_leave(
    payload: LeaveCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "create_leave")
    employee = _assignable_employee_or_404(db, payload.employee_id)
    acquire_transaction_lock(db, f"staff-leave:{payload.employee_id}")
    overlap = _leave_overlap(
        db,
        employee_id=payload.employee_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    if overlap is not None:
        raise HTTPException(status_code=409, detail="This employee already has overlapping pending or approved leave.")

    now = farm_now_naive()
    record = StaffLeave(
        employee_id=payload.employee_id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=payload.status,
        reason=(payload.reason or "").strip() or None,
        recorded_by_user_id=current_user.id,
        requested_by_user_id=current_user.id,
        decided_by_user_id=current_user.id if payload.status == "Approved" else None,
        decided_at=now if payload.status == "Approved" else None,
        coverage_reason="Management-recorded approved leave" if payload.status == "Approved" else None,
    )
    db.add(record)
    db.flush()
    _add_workforce_audit(
        db,
        current_user=current_user,
        action="Leave recorded",
        entity_id=f"leave:{record.id}",
        record_name=employee.full_name,
        details=f"{record.leave_type} {record.start_date.isoformat()} to {record.end_date.isoformat()} created as {record.status}.",
        icon="event_busy",
    )
    if record.status == "Approved":
        try:
            approve_leave_with_coverage(
                db,
                leave=record,
                actor_user_id=current_user.id,
                actor_name=current_user.full_name,
                default_covering_employee_id=None,
                task_covering_employee_ids={},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _flag_unavailable_tasks(db, record.employee_id, record.start_date, record.end_date)
    db.commit()
    db.refresh(record)
    return _leave_response(db, record)


@router.post("/leave/request", response_model=LeaveResponse, status_code=201)
def request_my_leave(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "request_my_leave")
    linked_employee = _employee_profile_for_user_or_error(db, current_user)
    if linked_employee.is_archived or linked_employee.employment_status != "Active":
        raise HTTPException(status_code=400, detail="Inactive or archived employees cannot create new leave requests.")
    employee = linked_employee
    acquire_transaction_lock(db, f"staff-leave:{employee.id}")
    overlap = _leave_overlap(
        db,
        employee_id=employee.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    if overlap is not None:
        raise HTTPException(status_code=409, detail="You already have overlapping pending or approved leave.")
    record = StaffLeave(
        employee_id=employee.id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="Pending",
        reason=(payload.reason or "").strip() or None,
        recorded_by_user_id=current_user.id,
        requested_by_user_id=current_user.id,
    )
    db.add(record)
    db.flush()
    _add_workforce_audit(
        db,
        current_user=current_user,
        action="Leave requested",
        entity_id=f"leave:{record.id}",
        record_name=employee.full_name,
        details=f"{record.leave_type} {record.start_date.isoformat()} to {record.end_date.isoformat()} requested; status Pending.",
        icon="event_busy",
    )
    db.commit()
    db.refresh(record)
    return _leave_response(db, record)


@router.post("/leave/{leave_id}/decision", response_model=LeaveResponse)
def decide_leave(
    leave_id: int,
    payload: LeaveDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "decide_leave")
    acquire_transaction_lock(db, f"staff-leave-record:{leave_id}")
    record = db.get(StaffLeave, leave_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Leave record not found.")
    if record.status != "Pending":
        raise HTTPException(status_code=409, detail="Only a pending leave request can be approved or rejected.")

    employee = _employee_or_404(db, record.employee_id, active_only=False)
    if payload.decision == "Approved":
        if record.requested_by_user_id == current_user.id or employee.login_user_id == current_user.id:
            raise HTTPException(status_code=403, detail="You cannot approve your own leave request.")

        affected_ids = {task.id for task in affected_tasks_for_leave(db, record)}
        unknown_ids = [row.task_id for row in payload.task_coverages if row.task_id not in affected_ids]
        if unknown_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Coverage selection contains task(s) outside this leave period: {', '.join(map(str, unknown_ids))}.",
            )

    record.status = payload.decision
    record.decided_by_user_id = current_user.id
    record.decided_at = farm_now_naive()
    record.decision_notes = (payload.notes or "").strip() or None
    record.coverage_reason = record.decision_notes if payload.decision == "Approved" else None

    coverage_summary = None
    if payload.decision == "Approved":
        selections = {row.task_id: row.covering_employee_id for row in payload.task_coverages}
        try:
            coverage_summary = approve_leave_with_coverage(
                db,
                leave=record,
                actor_user_id=current_user.id,
                actor_name=current_user.full_name,
                default_covering_employee_id=payload.default_covering_employee_id,
                task_covering_employee_ids=selections,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _flag_unavailable_tasks(db, record.employee_id, record.start_date, record.end_date)

    _add_workforce_audit(
        db,
        current_user=current_user,
        action=f"Leave {payload.decision.lower()}",
        entity_id=f"leave:{record.id}",
        record_name=employee.full_name,
        details=(
            f"{record.leave_type} {record.start_date.isoformat()} to {record.end_date.isoformat()} -> {payload.decision}."
            + (f" Decision notes: {record.decision_notes}" if record.decision_notes else "")
            + (
                f" Coverage: {coverage_summary['covered']} covered, "
                f"{coverage_summary['needs_reassignment']} need reassignment, "
                f"{coverage_summary['urgent_review']} urgent review."
                if coverage_summary else ""
            )
        ),
        icon="event_busy",
    )
    db.commit()
    db.refresh(record)
    return _leave_response(db, record)


@router.post("/leave/{leave_id}/cancel", response_model=LeaveResponse)
def cancel_leave(
    leave_id: int,
    payload: LeaveCancelRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Backward-compatible direct-call support for older internal tests and
    # integrations that called cancel_leave(leave_id, db, current_user).
    legacy_direct_call = isinstance(payload, Session)
    if legacy_direct_call:
        current_user = db
        db = payload
        payload = None

    _require_workforce_access(current_user, "cancel_leave")
    acquire_transaction_lock(db, f"staff-leave-record:{leave_id}")
    record = db.get(StaffLeave, leave_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Leave record not found.")

    can_review = (
        has_permission(current_user, "workforce:attendance")
        or has_permission(current_user, "workforce:manage")
        or has_permission(current_user, "*")
    )
    employee = db.scalar(select(Employee).where(Employee.login_user_id == current_user.id))
    is_own = employee is not None and employee.id == record.employee_id

    if not can_review:
        if not is_own:
            raise HTTPException(status_code=404, detail="Leave record not found.")
        if record.status != "Pending":
            raise HTTPException(status_code=409, detail="Employees can cancel only their own Pending leave request.")
    elif record.status not in {"Pending", "Approved", "Cancelled"}:
        raise HTTPException(status_code=409, detail="Only Pending or Approved leave can be cancelled.")

    if record.status != "Cancelled":
        previous_status = record.status
        reason = (payload.reason or "").strip() if payload else ""
        if previous_status == "Approved" and can_review and not reason and not legacy_direct_call:
            raise HTTPException(status_code=400, detail="A cancellation reason is required for approved leave.")
        if not reason:
            reason = (
                "Legacy manager cancellation; no reason was supplied."
                if legacy_direct_call
                else "Employee cancelled pending leave request."
                if is_own
                else "Leave cancelled by authorized reviewer."
            )

        record.status = "Cancelled"
        record.cancelled_by_user_id = current_user.id
        record.cancelled_at = farm_now_naive()
        record.cancellation_reason = reason
        leave_employee = _employee_or_404(db, record.employee_id, active_only=False)
        _add_workforce_audit(
            db,
            current_user=current_user,
            action="Leave cancelled",
            entity_id=f"leave:{record.id}",
            record_name=leave_employee.full_name,
            details=(
                f"{record.leave_type} {record.start_date.isoformat()} to {record.end_date.isoformat()}: "
                f"{previous_status} -> Cancelled. Reason: {reason}"
            ),
            icon="event_busy",
        )
        db.flush()

    _flag_unavailable_tasks(db, record.employee_id, record.start_date, record.end_date)
    reconcile_expired_leave_coverage(
        db,
        leave_id=record.id,
        actor_user_id=current_user.id,
        actor_name=current_user.full_name,
    )
    db.commit()
    db.refresh(record)
    return _leave_response(db, record)


@router.post("/leave/recalculate-coverage", response_model=LeaveRecalculationResponse)
def recalculate_leave_coverage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "recalculate_leave_coverage")
    acquire_transaction_lock(db, "leave-coverage:recalculate")
    summary = reconcile_expired_leave_coverage(
        db,
        actor_user_id=current_user.id,
        actor_name=current_user.full_name,
    )
    db.commit()
    return LeaveRecalculationResponse(**summary)


@router.get("/shifts", response_model=list[ShiftResponse])
def list_shifts(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    employee_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "list_shifts")
    stmt = select(StaffShift).order_by(StaffShift.work_date.desc(), StaffShift.start_time, StaffShift.id)
    if employee_id:
        stmt = stmt.where(StaffShift.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(StaffShift.work_date >= date_from)
    if date_to:
        stmt = stmt.where(StaffShift.work_date <= date_to)
    return list(db.scalars(stmt).all())


@router.post("/shifts", response_model=ShiftResponse, status_code=201)
def create_shift(
    payload: ShiftCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "create_shift")
    employee = _employee_or_404(db, payload.employee_id)
    acquire_transaction_lock(db, f"staff-shift:{payload.employee_id}:{payload.work_date.isoformat()}")
    existing = db.scalar(
        select(StaffShift).where(
            StaffShift.employee_id == payload.employee_id,
            StaffShift.work_date == payload.work_date,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This employee already has a roster record for that work date.")
    leave = _approved_leave_for_date(db, employee_id=payload.employee_id, work_date=payload.work_date)
    if leave is not None and payload.status != "Cancelled":
        raise HTTPException(status_code=409, detail="A roster shift cannot overlap approved leave.")
    try:
        validate_roster_schedule_choice(db, employee.id, payload.work_date, payload.status, payload.exception_type)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record = StaffShift(
        employee_id=payload.employee_id,
        work_date=payload.work_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        assigned_area=(payload.assigned_area or employee.assigned_area or "").strip() or None,
        status=payload.status,
        notes=(payload.notes or "").strip() or None,
        exception_type=payload.exception_type,
        exception_reason=(payload.exception_reason or "").strip() or None,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(record)
    db.flush()
    if record.exception_type in {"Working Day Override", "Rest Day Override", "Special Day Off", "Changed Shift"}:
        reconcile_employee_future_tasks(
            db, record.employee_id, from_date=record.work_date,
            actor_user_id=current_user.id, actor_name=current_user.full_name,
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This employee already has a roster record for that work date.") from exc
    db.refresh(record)
    return record


@router.put("/shifts/{shift_id}", response_model=ShiftResponse)
def update_shift(
    shift_id: int,
    payload: ShiftUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "update_shift")
    acquire_transaction_lock(db, f"staff-shift-record:{shift_id}")
    record = db.get(StaffShift, shift_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Roster shift not found.")
    changes = payload.model_dump(exclude_unset=True)
    next_date = changes.get("work_date", record.work_date)
    next_status = changes.get("status", record.status)
    next_start = changes.get("start_time", record.start_time)
    next_end = changes.get("end_time", record.end_time)
    if next_start and next_end and next_end <= next_start:
        raise HTTPException(status_code=400, detail="Shift end time must be after the start time.")
    duplicate = db.scalar(
        select(StaffShift).where(
            StaffShift.employee_id == record.employee_id,
            StaffShift.work_date == next_date,
            StaffShift.id != record.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="This employee already has a roster record for that work date.")
    if next_status != "Cancelled":
        leave = _approved_leave_for_date(db, employee_id=record.employee_id, work_date=next_date)
        if leave is not None:
            raise HTTPException(status_code=409, detail="A roster shift cannot overlap approved leave.")
    try:
        validate_roster_schedule_choice(
            db, record.employee_id, next_date, next_status, changes.get("exception_type", record.exception_type),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    for field in ("work_date", "start_time", "end_time", "assigned_area", "status", "notes", "exception_type", "exception_reason"):
        if field in changes:
            value = changes[field]
            if field in {"assigned_area", "notes", "exception_reason"} and isinstance(value, str):
                value = value.strip() or None
            setattr(record, field, value)
    record.updated_by_user_id = current_user.id
    db.flush()
    if record.exception_type in {"Working Day Override", "Rest Day Override", "Special Day Off", "Changed Shift"}:
        reconcile_employee_future_tasks(
            db, record.employee_id, from_date=record.work_date,
            actor_user_id=current_user.id, actor_name=current_user.full_name,
        )
    db.commit()
    db.refresh(record)
    return record


@router.post("/shifts/{shift_id}/cancel", response_model=ShiftResponse)
def cancel_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "cancel_shift")
    record = db.get(StaffShift, shift_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Roster shift not found.")
    record.status = "Cancelled"
    record.updated_by_user_id = current_user.id
    db.commit()
    db.refresh(record)
    return record


@router.get("/calendar")
def staff_calendar(
    date_from: date,
    date_to: date,
    employee_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "staff_calendar")
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="Calendar end date cannot be before start date.")
    if (date_to - date_from).days > 93:
        raise HTTPException(status_code=400, detail="Calendar range cannot exceed 94 days.")
    return _calendar_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        employee_id=employee_id,
        current_user=current_user,
    )


@router.get("/my-schedule")
def my_schedule(
    date_from: date,
    date_to: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "my_schedule")
    employee = _employee_for_user_or_error(db, current_user)
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="Schedule end date cannot be before start date.")
    if (date_to - date_from).days > 93:
        raise HTTPException(status_code=400, detail="Schedule range cannot exceed 94 days.")
    return _calendar_payload(
        db,
        date_from=date_from,
        date_to=date_to,
        employee_id=employee.id,
        current_user=current_user,
    )


def _protocol_citations(template: CareTemplate) -> list[str]:
    try:
        value = json.loads(template.citations_json or "[]")
        return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def _care_template_response(db: Session, template_id: int) -> CareTemplateResponse:
    template = db.get(CareTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Care protocol not found.")
    steps = list(db.scalars(
        select(CareTemplateStep).where(CareTemplateStep.template_id == template.id)
        .order_by(CareTemplateStep.sequence_number)
    ).all())
    return CareTemplateResponse(
        id=template.id,
        template_code=template.template_code,
        protocol_family_code=template.protocol_family_code,
        version=template.version,
        name=template.name,
        module=template.module,
        target_type=template.target_type,
        target_breed=template.target_breed,
        target_variety=template.target_variety,
        production_purpose=template.production_purpose,
        growth_stage=template.growth_stage,
        description=template.description,
        effective_from=template.effective_from,
        effective_to=template.effective_to,
        status=template.status,
        approval_status=template.approval_status,
        source_title=template.source_title,
        source_url=template.source_url,
        citations=_protocol_citations(template),
        last_reviewed_date=template.last_reviewed_date,
        supersedes_template_id=template.supersedes_template_id,
        copied_from_template_id=template.copied_from_template_id,
        published_at=template.published_at,
        is_active=template.is_active,
        steps=[CareTemplateStepResponse.model_validate(step) for step in steps],
    )


def _clean_protocol_fields(data: dict) -> dict:
    result = dict(data)
    if "citations" in result:
        result["citations_json"] = json.dumps(result.pop("citations") or [])
    for key in (
        "name", "target_type", "target_breed", "target_variety", "production_purpose",
        "growth_stage", "description", "source_title", "source_url",
    ):
        if key in result and isinstance(result[key], str):
            result[key] = result[key].strip() or None
    return result


def _add_protocol_steps(db: Session, template: CareTemplate, steps) -> None:
    seen: set[int] = set()
    for step_input in steps:
        step_data = step_input.model_dump() if hasattr(step_input, "model_dump") else dict(step_input)
        sequence = int(step_data["sequence_number"])
        if sequence in seen:
            raise HTTPException(status_code=409, detail="Care-protocol step sequence numbers must be unique.")
        seen.add(sequence)
        # New reusable protocols resolve current lots at task-generation time.
        # inventory_item_id is retained only for migrated/legacy compatibility.
        if step_data.get("inventory_item_id"):
            item = db.get(InventoryItem, step_data["inventory_item_id"])
            if item is None or item.is_archived:
                raise HTTPException(status_code=400, detail=f"Legacy Inventory resource for care step '{step_data['title']}' is missing or archived.")
            _validate_task_resource_choice(module=template.module, item=item, task_text=" ".join([step_data["title"], step_data["category"], step_data.get("instructions") or ""]))
            step_data["planned_unit"] = item.unit
        db.add(CareTemplateStep(template_id=template.id, **step_data))


def _clone_protocol_version(db: Session, source: CareTemplate, current_user: User, *, new_family: bool = False, name: str | None = None) -> CareTemplate:
    family = _next_code(db, CareTemplate, "PROT") if new_family else source.protocol_family_code
    acquire_transaction_lock(db, f"care-protocol-version:{family}")
    next_version = 1 if new_family else int(db.scalar(select(func.max(CareTemplate.version)).where(CareTemplate.protocol_family_code == family)) or 0) + 1
    clone = CareTemplate(
        template_code=_next_code(db, CareTemplate, "CARE"), protocol_family_code=family, version=next_version,
        name=(name or source.name).strip(), module=source.module, target_type=source.target_type,
        target_breed=source.target_breed, target_variety=source.target_variety,
        production_purpose=source.production_purpose, growth_stage=source.growth_stage,
        description=source.description, effective_from=source.effective_from, effective_to=source.effective_to,
        status="Draft", approval_status="Draft - Needs Veterinarian/Agriculturist Approval",
        source_title=source.source_title, source_url=source.source_url, citations_json=source.citations_json,
        last_reviewed_date=source.last_reviewed_date,
        supersedes_template_id=None if new_family else source.id,
        copied_from_template_id=source.id if new_family else source.copied_from_template_id,
        is_active=True, created_by_user_id=current_user.id,
    )
    db.add(clone); db.flush()
    source_steps = list(db.scalars(select(CareTemplateStep).where(CareTemplateStep.template_id == source.id).order_by(CareTemplateStep.sequence_number)).all())
    for step in source_steps:
        data = {c.name: getattr(step, c.name) for c in CareTemplateStep.__table__.columns if c.name not in {"id", "template_id", "created_at"}}
        db.add(CareTemplateStep(template_id=clone.id, **data))
    db.flush()
    return clone


@router.get("/care-templates", response_model=list[CareTemplateResponse])
def list_care_templates(
    module: str | None = Query(None),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_all_versions: bool = Query(False),
):
    _require_workforce_access(current_user, "list_care_templates")
    stmt = select(CareTemplate)
    if module:
        stmt = stmt.where(CareTemplate.module == module)
    if not include_inactive:
        stmt = stmt.where(CareTemplate.is_active == True)
    if not include_all_versions:
        # Operational selectors receive only published versions; draft presets
        # stay in the protocol library until expert-approved and published.
        stmt = stmt.where(CareTemplate.status == "Published")
    templates = list(db.scalars(stmt.order_by(CareTemplate.name, CareTemplate.protocol_family_code, CareTemplate.version.desc())).all())
    if not include_all_versions:
        latest = {}
        for template in templates:
            latest.setdefault(template.protocol_family_code, template)
        templates = list(latest.values())
    return [_care_template_response(db, row.id) for row in templates]


@router.post("/care-templates", response_model=CareTemplateResponse, status_code=201)
def create_care_template(payload: CareTemplateCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "create_care_template")
    family = _next_code(db, CareTemplate, "PROT")
    data = _clean_protocol_fields(payload.model_dump(exclude={"steps"}))
    template = CareTemplate(
        template_code=_next_code(db, CareTemplate, "CARE"), protocol_family_code=family, version=1,
        status="Draft", is_active=True, created_by_user_id=current_user.id, **data,
    )
    db.add(template); db.flush()
    _add_protocol_steps(db, template, payload.steps)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail="Care-protocol version or step sequence already exists.") from exc
    return _care_template_response(db, template.id)


@router.put("/care-templates/{template_id}", response_model=CareTemplateResponse)
def update_care_template(template_id: int, payload: CareTemplateUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "update_care_template")
    template = db.get(CareTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Care protocol not found.")
    changes = _clean_protocol_fields(payload.model_dump(exclude_unset=True))
    future_task_action = changes.pop("future_task_action", None)
    requested_steps = changes.pop("steps", None)
    if changes.get("is_active") is False:
        if future_task_action not in {"keep", "resolve"}:
            raise HTTPException(status_code=400, detail="Deactivation requires future_task_action='keep' or 'resolve'.")
        return deactivate_care_template(template_id, future_task_action, db, current_user)

    try:
        target = template
        if template.status in {"Published", "Superseded"}:
            target = _clone_protocol_version(db, template, current_user)
        editable_fields = {
            "name", "target_type", "target_breed", "target_variety", "production_purpose", "growth_stage",
            "description", "effective_from", "effective_to", "approval_status", "source_title", "source_url",
            "citations_json", "last_reviewed_date",
        }
        for field, value in changes.items():
            if field in editable_fields:
                setattr(target, field, value)
        if requested_steps is not None:
            for row in list(db.scalars(select(CareTemplateStep).where(CareTemplateStep.template_id == target.id)).all()):
                db.delete(row)
            db.flush()
            _add_protocol_steps(db, target, requested_steps)
        db.commit()
        return _care_template_response(db, target.id)
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail="Care-protocol version or step sequence already exists.") from exc
    except Exception:
        db.rollback(); raise


@router.post("/care-templates/{template_id}/copy", response_model=CareTemplateResponse, status_code=201)
def copy_care_template(template_id: int, payload: CareProtocolCopyRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "copy_care_template")
    source = db.get(CareTemplate, template_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Care protocol not found.")
    try:
        clone = _clone_protocol_version(db, source, current_user, new_family=True, name=payload.name or f"{source.name} Copy")
        db.commit(); return _care_template_response(db, clone.id)
    except Exception:
        db.rollback(); raise


@router.post("/care-templates/{template_id}/publish", response_model=CareTemplateResponse)
def publish_care_template(template_id: int, payload: CareProtocolPublishRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "publish_care_template")
    template = db.get(CareTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Care protocol not found.")
    if template.status != "Draft":
        raise HTTPException(status_code=409, detail="Only a Draft protocol version can be published.")
    if template.approval_status != "Approved":
        raise HTTPException(status_code=400, detail="Protocol must be approved by the veterinarian/agriculturist before publication.")
    if not template.source_title or not template.source_url or not template.last_reviewed_date:
        raise HTTPException(status_code=400, detail="Published protocols require source title, source URL, and last-reviewed date.")
    if not db.scalar(select(CareTemplateStep.id).where(CareTemplateStep.template_id == template.id).limit(1)):
        raise HTTPException(status_code=400, detail="A protocol must contain at least one step before publication.")
    acquire_transaction_lock(db, f"care-protocol-publish:{template.protocol_family_code}")
    prior = list(db.scalars(select(CareTemplate).where(
        CareTemplate.protocol_family_code == template.protocol_family_code,
        CareTemplate.id != template.id,
        CareTemplate.status == "Published",
    )).all())
    try:
        template.status="Published"; template.published_at=farm_now_naive(); template.published_by_user_id=current_user.id; template.is_active=True
        for old in prior:
            old.status="Superseded"
            if not payload.apply_to_assigned_targets:
                continue
            targets = list(db.scalars(select(Crop if template.module == "Crop" else Livestock).where((Crop if template.module == "Crop" else Livestock).care_template_id == old.id)).all())
            for target in targets:
                if payload.future_task_action == "resolve":
                    resolve_future_pending_care_tasks(db, module=template.module, target_id=target.id, template_id=old.id)
                target.care_template_id = template.id
                validate_care_template_for_target(db, template_id=template.id, module=template.module, target=target)
                generate_care_tasks_for_target(db, module=template.module, target=target, template=template, current_user=current_user, future_only=True)
        db.commit(); return _care_template_response(db, template.id)
    except Exception:
        db.rollback(); raise


@router.post("/care-templates/{template_id}/deactivate", response_model=CareTemplateResponse)
def deactivate_care_template(template_id: int, future_task_action: str = Query(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "deactivate_care_template")
    if future_task_action not in {"keep", "resolve"}:
        raise HTTPException(status_code=400, detail="future_task_action must be 'keep' or 'resolve'.")
    template = db.get(CareTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Care protocol not found.")
    model = Crop if template.module == "Crop" else Livestock
    targets = list(db.scalars(select(model).where(model.care_template_id == template.id)).all())
    try:
        for target in targets:
            if future_task_action == "resolve":
                resolve_future_pending_care_tasks(db, module=template.module, target_id=target.id, template_id=template.id)
            target.care_template_id = None
        template.status="Inactive"; template.is_active=False
        db.commit(); return _care_template_response(db, template.id)
    except Exception:
        db.rollback(); raise


@router.post("/care-templates/import", response_model=list[CareTemplateResponse], status_code=201)
def import_care_protocols(payload: CareProtocolImportRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "import_care_protocols")
    created=[]
    try:
        for protocol in payload.protocols:
            family = _next_code(db, CareTemplate, "PROT")
            data = _clean_protocol_fields(protocol.model_dump(exclude={"steps"}))
            row=CareTemplate(template_code=_next_code(db, CareTemplate, "CARE"), protocol_family_code=family, version=1, status="Draft", is_active=True, created_by_user_id=current_user.id, **data)
            db.add(row); db.flush(); _add_protocol_steps(db,row,protocol.steps); created.append(row.id)
        db.commit(); return [_care_template_response(db, i) for i in created]
    except Exception:
        db.rollback(); raise


@router.post("/care-templates/import-csv", response_model=list[CareTemplateResponse], status_code=201)
async def import_care_protocols_csv(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "import_care_protocols_csv")
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="Protocol CSV is too large.")
    try:
        text = raw.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid UTF-8 CSV protocol file.") from exc
    grouped: dict[str, dict] = {}
    for row in rows:
        name = (row.get("protocol_name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Each CSV row requires protocol_name.")
        protocol = grouped.setdefault(name, {
            "name": name, "module": (row.get("module") or "").strip(), "target_type": (row.get("target_type") or "").strip() or None,
            "target_breed": (row.get("target_breed") or "").strip() or None, "target_variety": (row.get("target_variety") or "").strip() or None,
            "production_purpose": (row.get("production_purpose") or "").strip() or None, "growth_stage": (row.get("growth_stage") or "").strip() or None,
            "effective_from": (row.get("effective_from") or "").strip() or None, "effective_to": (row.get("effective_to") or "").strip() or None,
            "approval_status": (row.get("approval_status") or "Draft - Needs Veterinarian/Agriculturist Approval").strip(),
            "source_title": (row.get("source_title") or "").strip() or None, "source_url": (row.get("source_url") or "").strip() or None,
            "last_reviewed_date": (row.get("last_reviewed_date") or "").strip() or None,
            "citations": [(row.get("source_citation") or row.get("source_url") or "").strip()] if (row.get("source_citation") or row.get("source_url")) else [],
            "steps": [],
        })
        def _int(name, default=None):
            value=(row.get(name) or "").strip(); return int(value) if value else default
        def _float(name):
            value=(row.get(name) or "").strip(); return float(value) if value else None
        def _bool(name, default=False):
            value=(row.get(name) or "").strip().lower()
            return default if not value else value in {"1","true","yes","y"}
        protocol["steps"].append({
            "sequence_number": _int("step_sequence", 1), "title": (row.get("step_name") or "").strip(), "category": (row.get("category") or "general care").strip(),
            "timing_anchor": (row.get("timing_anchor") or "base_date").strip(), "offset_days": _int("offset_days", 0),
            "age_start_days": _int("age_start_days"), "age_end_days": _int("age_end_days"), "previous_step_sequence": _int("previous_step_sequence"),
            "recurrence_interval_days": _int("recurrence_interval_days"), "recurrence_occurrences": _int("recurrence_occurrences", 1),
            "instructions": (row.get("instructions") or "").strip() or None, "priority": (row.get("priority") or "Medium").strip(),
            "requires_review": _bool("requires_review", True), "requires_evidence": _bool("requires_evidence", False),
            "planned_quantity": _float("planned_quantity"), "planned_unit": (row.get("unit") or "").strip() or None,
            "dose_basis": (row.get("dose_basis") or "").strip() or None, "resource_product_name": (row.get("resource_product_name") or "").strip() or None,
            "resource_category": (row.get("resource_category") or "").strip() or None, "safety_notes": (row.get("safety_notes") or "").strip() or None,
            "withdrawal_interval_days": _int("withdrawal_interval_days"), "preharvest_interval_days": _int("preharvest_interval_days"),
            "source_citation": (row.get("source_citation") or "").strip() or None,
        })
    try:
        payload = CareProtocolImportRequest(protocols=[CareTemplateCreate.model_validate(value) for value in grouped.values()])
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid protocol CSV: {exc}") from exc
    return import_care_protocols(payload, db, current_user)


@router.get("/care-templates/match", response_model=list[CareTemplateResponse])
def match_care_protocols(module: str = Query(...), target_id: int = Query(..., gt=0), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_workforce_access(current_user, "match_care_protocols")
    model = Crop if module == "Crop" else Livestock if module == "Livestock" else None
    if model is None:
        raise HTTPException(status_code=400, detail="Module must be Crop or Livestock.")
    target = db.get(model, target_id)
    if target is None or target.is_archived:
        raise HTTPException(status_code=404, detail=f"{module} record not found.")
    candidates = list(db.scalars(select(CareTemplate).where(CareTemplate.module == module, CareTemplate.is_active == True, CareTemplate.status == "Published").order_by(CareTemplate.version.desc())).all())
    matched=[]; seen=set()
    for row in candidates:
        if row.protocol_family_code in seen:
            continue
        try:
            validate_care_template_for_target(db, template_id=row.id, module=module, target=target)
        except HTTPException:
            continue
        matched.append(_care_template_response(db,row.id)); seen.add(row.protocol_family_code)
    return matched


@router.post("/care-templates/generate", response_model=list[TaskResponse])
def generate_care_tasks(
    payload: GenerateCareTasksRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workforce_access(current_user, "generate_care_tasks")
    try:
        if payload.module == "Crop":
            target = db.get(Crop, payload.target_id)
            if target is None or target.is_archived:
                raise HTTPException(status_code=404, detail="Crop record not found.")
        elif payload.module == "Livestock":
            target = db.get(Livestock, payload.target_id)
            if target is None or target.is_archived:
                raise HTTPException(status_code=404, detail="Livestock record not found.")
        else:
            raise HTTPException(status_code=400, detail="Module must be Crop or Livestock.")

        template = validate_care_template_for_target(
            db,
            template_id=payload.template_id,
            module=payload.module,
            target=target,
        )
        if payload.employee_id is not None:
            target.assigned_employee_id = payload.employee_id
        target.care_template_id = template.id

        if payload.backup_employee_id is not None:
            backup = _assignable_employee_or_404(db, payload.backup_employee_id)
            if payload.employee_id is not None and backup.id == payload.employee_id:
                raise HTTPException(status_code=400, detail="Backup employee must be different from the default employee.")
        generated = generate_care_tasks_for_target(
            db,
            module=payload.module,
            target=target,
            template=template,
            current_user=current_user,
            base_date=payload.base_date,
            employee_id=payload.employee_id,
            backup_employee_id=payload.backup_employee_id,
            time_sensitive=payload.time_sensitive,
            controlled_rescheduling=payload.controlled_rescheduling,
            max_delay_minutes=payload.max_delay_minutes,
        )
        db.commit()
        return [_task_response(db, task) for task in generated]
    except Exception:
        db.rollback()
        raise
