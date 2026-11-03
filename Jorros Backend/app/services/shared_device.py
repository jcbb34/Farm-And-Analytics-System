"""Privacy minimization helpers for employee shared-device responses."""

from app.schemas.workforce import TaskResponse


def sanitize_shared_device_task_response(item: TaskResponse) -> TaskResponse:
    """Remove manager/other-employee identity data from a shared-device task.

    The employee's own task and correction state stays available, while names,
    user IDs, leave identifiers, and coverage details belonging to other staff
    are not sent to the kiosk client. Normal desktop My Tasks responses do not
    use this sanitizer.
    """
    latest_submission = item.latest_submission
    if latest_submission is not None:
        latest_submission = latest_submission.model_copy(update={
            "recorded_by_user_id": None,
            "recorded_by_name": None,
            "reviewed_by_user_id": None,
            "reviewed_by_name": None,
        })

    return item.model_copy(update={
        "assigned_by": "Farm Manager" if item.assigned_by else "",
        "previous_employee_name": None,
        "reassignment_reason": None,
        "leave_coverage_id": None,
        "related_leave_id": None,
        "original_employee_id": None,
        "original_employee_name": None,
        "covering_employee_id": None,
        "covering_employee_name": None,
        "coverage_start_date": None,
        "coverage_end_date": None,
        "coverage_reason": None,
        "coverage_status": None,
        "coverage_indicator": None,
        "latest_submission": latest_submission,
    })
