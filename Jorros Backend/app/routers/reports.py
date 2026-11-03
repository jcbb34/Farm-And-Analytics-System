from app.routers.archives import ArchiveRequest
from app.services.archive_service import change_archive_state, permanent_delete
from datetime import date, datetime
from io import BytesIO
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import (
    FileResponse,
    Response,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.farm_time import farm_today
from app.core.dependencies import has_permission, require_permission
from app.models import (
    FarmReport,
    User,
)
from app.routers.auth import (
    get_current_user,
)
from app.schemas.reports import (
    ReportAutomationRunResponse,
    ReportAutomationSettingsResponse,
    ReportAutomationSettingsUpdate,
    ReportAutomationStatusResponse,
    ReportCreate,
    ReportResponse,
    ReportUpdate,
    ReportVersionHistoryResponse,
)
from app.services.report_csv import (
    build_report_csv,
)
from app.services.report_generation_service import (
    create_report_record,
    create_revision,
)
from app.services.report_query import build_report_list_statement, report_list_summary
from app.services.report_pdf import (
    REPORT_DIRECTORY,
    generate_report_pdf,
    is_current_pdf_filename,
    resolve_report_pdf_path,
)
from app.services.report_scheduler import (
    get_automation_status,
    get_or_create_automation_settings,
    run_due_report_automation,
)


router = APIRouter(
    prefix="/api/v1/reports",
    dependencies=[Depends(require_permission("reports:view"))],
    tags=["Reports"],
)

def require_report_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "reports:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to generate or manage reports.",
        )
    return current_user



def require_report_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a System Administrator can approve reports or change automatic report schedules.",
        )
    return current_user



def _current_user_name(
    current_user: User,
) -> str:
    return (
        str(
            getattr(
                current_user,
                "full_name",
                "",
            )
            or getattr(
                current_user,
                "username",
                "",
            )
            or "Farm Personnel"
        ).strip()
        or "Farm Personnel"
    )


def _sync_report_prepared_by(
    db: Session,
    report: FarmReport,
    current_user: User,
) -> bool:
    prepared_by = report.prepared_by

    if (
        not report.is_automatic
        and report.generated_by_user_id
    ):
        author = db.get(
            User,
            report.generated_by_user_id,
        )
        if author is not None:
            prepared_by = _current_user_name(
                author
            )
    elif not report.is_automatic:
        prepared_by = _current_user_name(
            current_user
        )
    elif (
        not prepared_by
        or prepared_by.strip().lower()
        in {
            "juan dela cruz",
            "system generated",
        }
    ):
        settings = get_or_create_automation_settings(
            db
        )
        prepared_by = (
            settings.prepared_by
            or _current_user_name(
                current_user
            )
        )

    prepared_by = (
        prepared_by.strip()
        if prepared_by
        else _current_user_name(
            current_user
        )
    )

    if report.prepared_by != prepared_by:
        report.prepared_by = prepared_by
        report.updated_at = datetime.now()
        return True

    return False


def get_report_or_404(
    report_id: int,
    db: Session,
) -> FarmReport:
    report = db.get(
        FarmReport,
        report_id,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Report record not found."
            ),
        )

    return report


def _regenerate_pdf_safely(
    db: Session,
    report: FarmReport,
):
    try:
        pdf_path = (
            generate_report_pdf(
                report
            )
        )

        report.pdf_filename = (
            pdf_path.name
        )

        db.commit()
        db.refresh(
            report
        )
    except Exception as error:
        db.rollback()
        logging.getLogger("joross.reports").exception("Report PDF regeneration failed: %s", error)


@router.get(
    "/automation/settings",
    response_model=ReportAutomationSettingsResponse,
)
def get_automation_settings(
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        get_current_user
    ),
):
    settings = get_or_create_automation_settings(
        db
    )
    current_name = _current_user_name(
        current_user
    )

    if (
        not settings.prepared_by
        or settings.prepared_by.strip().lower()
        in {
            "juan dela cruz",
            "system generated",
        }
    ):
        settings.prepared_by = current_name
        settings.updated_at = datetime.now()
        db.commit()
        db.refresh(
            settings
        )

    return settings


@router.put(
    "/automation/settings",
    response_model=ReportAutomationSettingsResponse,
)
def update_automation_settings(
    payload: ReportAutomationSettingsUpdate,
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        require_report_admin
    ),
):
    settings = (
        get_or_create_automation_settings(
            db
        )
    )

    for (
        field_name,
        value,
    ) in payload.model_dump().items():
        if field_name == "prepared_by":
            continue
        setattr(
            settings,
            field_name,
            value,
        )

    settings.prepared_by = _current_user_name(
        current_user
    )

    settings.updated_at = (
        datetime.now()
    )

    db.commit()
    db.refresh(
        settings
    )

    return settings


@router.get(
    "/automation/status",
    response_model=ReportAutomationStatusResponse,
)
def automation_status(
    db: Session = Depends(
        get_db
    ),
    _: User = Depends(
        get_current_user
    ),
):
    return {
        "items": (
            get_automation_status(
                db
            )
        )
    }


@router.post(
    "/automation/run-now",
    response_model=ReportAutomationRunResponse,
)
def run_automation_now(
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        require_report_admin
    ),
):
    settings = get_or_create_automation_settings(
        db
    )
    current_name = _current_user_name(
        current_user
    )
    if settings.prepared_by != current_name:
        settings.prepared_by = current_name
        settings.updated_at = datetime.now()
        db.commit()

    generated = (
        run_due_report_automation(
            db,
            force=True,
        )
    )

    return {
        "generated_count": len(
            generated
        ),
        "generated_reports": generated,
        "message": (
            f"Generated {len(generated)} missing automatic report(s)."
            if generated
            else (
                "All enabled automatic report periods are already up to date."
            )
        ),
    }


@router.get("/summary", response_model=dict[str, int])
def get_report_list_summary(
    search: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=40),
    report_status: str | None = Query(default=None, alias="status", max_length=30),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source: str | None = Query(default=None, max_length=20),
    tab: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return report_list_summary(
        db,
        search=search,
        category=category,
        report_status=report_status,
        start_date=start_date,
        end_date=end_date,
        source=source,
        tab=tab,
    )


@router.get(
    "",
    response_model=list[
        ReportResponse
    ],
)
def list_reports(
    include_archived: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=40),
    report_status: str | None = Query(default=None, alias="status", max_length=30),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source: str | None = Query(default=None, max_length=20),
    tab: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    statement = build_report_list_statement(
        include_archived=include_archived,
        offset=offset,
        limit=limit,
        search=search,
        category=category,
        report_status=report_status,
        start_date=start_date,
        end_date=end_date,
        source=source,
        tab=tab,
    )
    records = list(db.scalars(statement).all())

    # Historical snapshots are immutable on a list read.
    return records


@router.post(
    "",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_report(
    payload: ReportCreate,
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        require_report_editor
    ),
):
    return create_report_record(
        db,
        title=payload.title,
        category=payload.category,
        report_type=payload.report_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        prepared_by=_current_user_name(
            current_user
        ),
        status=(
            "In Progress"
            if payload.report_type == "Daily Attendance Report"
            and payload.start_date <= farm_today() <= payload.end_date
            else payload.status
        ),
        summary=payload.summary,
        generated_by_user_id=current_user.id,
        generate_pdf=True,
        included_sections=payload.included_sections,
        filters=payload.filters,
    )


@router.get(
    "/{report_id}/versions",
    response_model=ReportVersionHistoryResponse,
)
def get_report_versions(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    _: User = Depends(
        get_current_user
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    series_code = (
        report.revision_group_code
        or report.report_code
    )

    versions = list(
        db.scalars(
            select(
                FarmReport
            )
            .where(
                FarmReport.revision_group_code
                == series_code
            )
            .order_by(
                FarmReport.revision_number.asc(),
                FarmReport.id.asc(),
            )
        ).all()
    )

    return {
        "series_code": series_code,
        "versions": versions,
    }


@router.post(
    "/{report_id}/submit",
    response_model=ReportResponse,
)
def submit_for_review(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    _: User = Depends(
        require_report_editor
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    if report.status != "Draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only Draft reports can be submitted for review."
            ),
        )

    report.status = (
        "For Review"
    )
    report.submitted_at = (
        datetime.now()
    )
    report.updated_at = (
        datetime.now()
    )

    db.commit()
    db.refresh(
        report
    )

    _regenerate_pdf_safely(
        db,
        report,
    )

    return report


@router.post(
    "/{report_id}/approve",
    response_model=ReportResponse,
)
def approve_report(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        require_report_admin
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    if (
        report.status
        != "For Review"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only reports that are For Review can be approved."
            ),
        )

    report.status = (
        "Approved"
    )
    report.reviewed_by_user_id = (
        current_user.id
    )
    report.reviewed_by_name = (
        current_user.full_name
    )
    report.approved_at = (
        datetime.now()
    )
    report.updated_at = (
        datetime.now()
    )

    db.commit()
    db.refresh(
        report
    )

    _regenerate_pdf_safely(
        db,
        report,
    )

    return report


@router.post(
    "/{report_id}/revision",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_report_revision(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        require_report_editor
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    if report.status not in {"Approved", "Final", "Needs Review", "Revised"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A revision can only be created from an Approved, Final, Needs Review, or Revised report."
            ),
        )

    return create_revision(
        db,
        report,
        current_user.id,
    )


@router.get(
    "/{report_id}/pdf",
)
def get_report_pdf(
    report_id: int,
    download: bool = Query(
        default=False
    ),
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        get_current_user
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    prepared_by_changed = _sync_report_prepared_by(
        db,
        report,
        current_user,
    )
    if prepared_by_changed:
        db.commit()
        db.refresh(
            report
        )

    pdf_path = None

    if (
        report.pdf_filename
        and is_current_pdf_filename(
            report.pdf_filename
        )
    ):
        candidate = resolve_report_pdf_path(
            report.pdf_filename,
            require_current=True,
        )

        if candidate is not None and candidate.exists():
            pdf_path = (
                candidate
            )

    if pdf_path is None:
        try:
            pdf_path = (
                generate_report_pdf(
                    report
                )
            )

            report.pdf_filename = (
                pdf_path.name
            )

            db.commit()
            db.refresh(
                report
            )
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "The report exists, but the PDF could not be generated: "
                    f"{error}"
                ),
            ) from error

    response = FileResponse(
        path=str(
            pdf_path
        ),
        media_type="application/pdf",
    )

    disposition = (
        "attachment"
        if download
        else "inline"
    )

    response.headers[
        "Content-Disposition"
    ] = (
        f'{disposition}; filename="{pdf_path.name}"'
    )

    return response


@router.get(
    "/{report_id}/data.csv",
)
def get_report_supporting_csv(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    _: User = Depends(
        get_current_user
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    content = build_report_csv(
        report
    )

    filename = (
        f"{report.report_code}_REV-{report.revision_number}_supporting-data.csv"
    )

    return Response(
        content=content,
        media_type=(
            "text/csv; charset=utf-8"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )


@router.post(
    "/{report_id}/pdf/regenerate",
    response_model=ReportResponse,
)
def regenerate_report_pdf(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        require_report_editor
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    _sync_report_prepared_by(
        db,
        report,
        current_user,
    )

    try:
        pdf_path = (
            generate_report_pdf(
                report
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Unable to regenerate report PDF: "
                f"{error}"
            ),
        ) from error

    report.pdf_filename = (
        pdf_path.name
    )
    report.updated_at = (
        datetime.now()
    )

    db.commit()
    db.refresh(
        report
    )

    return report


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
)
def get_report(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    _: User = Depends(
        get_current_user
    ),
):
    return get_report_or_404(
        report_id,
        db,
    )


@router.put(
    "/{report_id}",
    response_model=ReportResponse,
)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Session = Depends(
        get_db
    ),
    current_user: User = Depends(
        require_report_editor
    ),
):
    report = get_report_or_404(
        report_id,
        db,
    )

    if report.status != "Draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only Draft reports can be edited. Create a revision if an Approved report needs correction."
            ),
        )

    changes = payload.model_dump(
        exclude_unset=True
    )
    changes.pop(
        "prepared_by",
        None,
    )

    if not report.is_automatic:
        report.prepared_by = _current_user_name(
            current_user
        )

    for (
        field_name,
        value,
    ) in changes.items():
        if isinstance(
            value,
            str,
        ):
            value = (
                value.strip()
            )

        setattr(
            report,
            field_name,
            value,
        )

    report.updated_at = (
        datetime.now()
    )

    db.commit()
    db.refresh(
        report
    )

    _regenerate_pdf_safely(
        db,
        report,
    )

    return report


@router.post(
    "/{report_id}/archive",
    response_model=ReportResponse,
)
def archive_report(
    report_id: int,
    payload: ArchiveRequest,
    db: Session = Depends(
        get_db
    ),
    _: User = Depends(
        require_report_editor
    ),
):
    record = change_archive_state(db, "Report", report_id, _, archive=True, reason=payload.reason)
    db.commit()
    db.refresh(record)
    return record


@router.post(
    "/{report_id}/restore",
    response_model=ReportResponse,
)
def restore_report(
    report_id: int,
    db: Session = Depends(
        get_db
    ),
    _: User = Depends(
        require_report_editor
    ),
):
    record = change_archive_state(db, "Report", report_id, _, archive=False)
    db.commit()
    db.refresh(record)
    return record


@router.delete(
    "/{report_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
)
def permanently_delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_report_admin),
):
    permanent_delete(db, "Report", report_id, _)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
