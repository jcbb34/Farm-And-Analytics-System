import { useAuth } from "../../../context/AuthContext.jsx";
import { farmDateKey } from "../../../utils/farmCalendar.js";
import AssignmentFilters from "./AssignmentFilters.jsx";


export const OPEN_TASK_STATUSES = new Set(["Pending", "In Progress", "Submitted for Review", "Returned"]);
export const REASSIGNABLE_TASK_STATUSES = new Set(["Pending", "In Progress", "Returned"]);
export const HISTORICAL_TASK_STATUSES = new Set(["Completed", "Resolved", "Cancelled", "Voided"]);
const MISSED_TASK_STATUSES = new Set(["Pending", "In Progress", "Returned"]);

export const statusClass = (value) => String(value || "").toLowerCase().replaceAll(" ", "-");

export const formatSubmissionDate = (value) => {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
};

export const isMissedAssignment = (task) => Boolean(
    !task?.work_suspended
    && task?.activity_date
    && task.activity_date < farmDateKey()
    && MISSED_TASK_STATUSES.has(task?.status),
);

export const taskDisplayPriority = (task) => {
    if (task?.needs_reassignment && OPEN_TASK_STATUSES.has(task?.status)) return 0;
    if (isMissedAssignment(task)) return 1;
    if (task?.status === "Submitted for Review") return 2;
    if (task?.status === "Returned") return 3;
    if (task?.status === "In Progress") return 4;
    if (task?.status === "Pending") return 5;
    if (HISTORICAL_TASK_STATUSES.has(task?.status)) return 20;
    return 10;
};


function TaskRow({
    allEmployeesById,
    focusedTaskId,
    onCorrectUsage,
    onOpenReview,
    onReassign,
    onRecordWork,
    onVoidUsage,
    task,
}) {
    const { hasPermission } = useAuth();
    const employee = task.assigned_employee_id
        ? allEmployeesById.get(Number(task.assigned_employee_id))
        : null;
    const employeeName = task.employee_name || employee?.full_name || null;
    const employeeStatus = task.employee_is_archived
        ? "Archived"
        : task.employee_status || employee?.employment_status || null;
    const previousEmployeeName = task.previous_employee_name
        || (!task.assigned_employee_id && task.assigned_to && task.assigned_to !== "Unassigned"
            ? task.assigned_to
            : null);
    const reassignmentReason = task.reassignment_reason
        || (task.needs_reassignment ? "Employee unavailable — replacement required" : null);
    const isFocused = String(task.id) === String(focusedTaskId);
    const recordWorkUnavailable = Boolean(task.work_suspended || task.needs_reassignment || !task.assigned_employee_id);

    return (
        <tr
            id={`task-row-${task.id}`}
            tabIndex={isFocused ? -1 : undefined}
            className={`${task.needs_reassignment ? "task-row-needs-reassignment " : ""}${isFocused ? "task-row-deep-link" : ""}`.trim()}
        >
            <td>
                <strong>{task.name}</strong>
                <div className="task-meta"><span>{task.activity_code}</span><span>{task.related_to}</span></div>
                {task.work_suspended && <div className="farm-task-held"><strong>Held for declaration review</strong>{task.suspension_holds?.map((x) => <a key={x.event_id} href={`/staff-calendar?date=${task.activity_date}&eventId=${x.event_id}`}>{x.title} · {x.state}</a>)}</div>}
                {task.problem_report && <div className="task-note">Problem: {task.problem_report}</div>}
            </td>
            <td>
                <div className="assignment-employee-cell">
                    <strong>{employeeName || "Unassigned"}</strong>
                    {employeeStatus && employeeStatus !== "Active" && (
                        <span className={`employee-availability-badge ${statusClass(employeeStatus)}`}>
                            {employeeStatus}
                        </span>
                    )}
                </div>
                {!employeeName && previousEmployeeName && (
                    <div className="assignment-previous">Previous: {previousEmployeeName}</div>
                )}
                {task.assignment_source === "Leave Coverage" && (
                    <div className="leave-coverage-assignment-card">
                        <div className="leave-coverage-assignment-title">
                            <span className="material-symbols-outlined" aria-hidden="true">swap_horiz</span>
                            <strong>Leave Coverage</strong>
                            {task.coverage_indicator && (
                                <span
                                    className={`coverage-end-indicator ${String(task.coverage_indicator).toLowerCase().replaceAll(" ", "-")}`}
                                >
                                    {task.coverage_indicator}
                                </span>
                            )}
                        </div>
                        <span>Original: {task.original_employee_name || "Unknown employee"}</span>
                        <span>Covering: {task.covering_employee_name || employeeName || "Needs Reassignment"}</span>
                        {task.coverage_end_date && <span>Coverage ends: {task.coverage_end_date}</span>}
                    </div>
                )}
                {task.needs_reassignment && (
                    <div className="assignment-warning">
                        <span className="material-symbols-outlined">warning</span>
                        <div><strong>Needs Reassignment</strong><span>{reassignmentReason}</span></div>
                    </div>
                )}
            </td>
            <td>{task.activity_date}<br /><small>{task.start_time}</small></td>
            <td>
                <span className={`task-status ${statusClass(task.status)}`}>{task.status}</span>
                {isMissedAssignment(task) && (
                    <span className="task-missed-status">
                        <span className="material-symbols-outlined">schedule</span>Missed
                    </span>
                )}
                {task.assignment_source === "Leave Coverage" && (
                    <span className="task-coverage-badge">Leave Coverage</span>
                )}
                {task.needs_reassignment && OPEN_TASK_STATUSES.has(task.status) && (
                    <span className="task-reassignment-badge">Reassignment Required</span>
                )}
            </td>
            <td>{task.priority}</td>
            <td>
                {task.latest_submission ? (
                    <div className="submission-summary">
                        <strong>{`Attempt ${task.latest_submission.attempt_number}`}</strong>
                        <small>
                            {task.latest_submission.employee_name
                                ? `Performed by ${task.latest_submission.employee_name}`
                                : task.latest_submission.review_status}
                        </small>
                        {task.latest_submission.is_assisted && <small>Manager-assisted submission</small>}
                        <small>Submitted {formatSubmissionDate(task.latest_submission.submitted_at)}</small>
                        {task.latest_submission.recorded_by_name && task.latest_submission.is_assisted && (
                            <small>Recorded by {task.latest_submission.recorded_by_name}</small>
                        )}
                        {task.latest_submission.evidence_url ? (
                            <small className="submission-evidence-indicator">
                                <span className="material-symbols-outlined" aria-hidden="true">attachment</span>
                                Evidence attached
                            </small>
                        ) : <small>No evidence attachment</small>}
                    </div>
                ) : task.record_origin ? <span className="record-origin-label">{task.record_origin}</span> : "—"}
            </td>
            <td>
                <div className="task-actions">
                    {task.status === "Submitted for Review" && (
                        <button
                            type="button"
                            className="workforce-button review-submission-button"
                            onClick={() => onOpenReview(task)}
                        >
                            <span className="material-symbols-outlined" aria-hidden="true">fact_check</span>
                            Review Submission
                        </button>
                    )}
                    {REASSIGNABLE_TASK_STATUSES.has(task.status) && task.activity_date <= farmDateKey() && (
                        <button
                            type="button"
                            className="workforce-button record-work"
                            onClick={() => onRecordWork(task)}
                            disabled={recordWorkUnavailable}
                            title={recordWorkUnavailable
                                ? (task.work_suspended ? "Owner/Admin must review the declaration before work can be recorded." : "Reassign this task to an available employee before recording work.")
                                : "Record work on behalf of the assigned employee."}
                            aria-label={recordWorkUnavailable
                                ? "Record Work unavailable — task must be reassigned first"
                                : "Record Work"}
                        >
                            <span className="material-symbols-outlined">fact_check</span>Record Work
                        </button>
                    )}
                    {!task.work_suspended && REASSIGNABLE_TASK_STATUSES.has(task.status) && (
                        <button
                            className={`workforce-button task-reassign-button ${task.needs_reassignment ? "reassign-needed" : "secondary"}`}
                            onClick={() => onReassign(task)}
                        >
                            <span className="material-symbols-outlined">assignment_ind</span>Reassign
                        </button>
                    )}
                    {task.status === "Completed"
                        && task.resource_required
                        && task.resource_linked
                        && task.has_performed_work_record && (
                        <>
                            <button
                                className="workforce-button secondary task-correct-usage-button"
                                onClick={() => onCorrectUsage(task)}
                            >
                                <span className="material-symbols-outlined">sync_alt</span>Correct Usage
                            </button>
                        </>
                    )}
                    {task.status === "Completed" && task.latest_submission?.review_status === "Approved" && task.can_void && (
                        <button type="button" className="workforce-button danger" onClick={() => onVoidUsage(task)}>
                            <span className="material-symbols-outlined" aria-hidden="true">undo</span>{hasPermission("*") ? "Void Work" : "Request Void"}
                        </button>
                    )}
                    {HISTORICAL_TASK_STATUSES.has(task.status) && (
                        <span className="task-history-locked">Historical</span>
                    )}
                </div>
            </td>
        </tr>
    );
}


export default function AssignmentsPanel({
    allEmployeesById,
    filteredTasks,
    filterProps,
    focusedTaskId,
    loading,
    onAssignTask,
    onCorrectUsage,
    onLoadMore,
    onOpenReview,
    onReassign,
    onRecordWork,
    onRefresh,
    onVoidUsage,
    refreshing,
    stats,
    tasks,
    taskTotal,
    visibleTasks,
}) {
    return (
        <section className="workforce-card">
            <div className="workforce-card-header">
                <div>
                    <h2>Assignments</h2>
                    <p className="workforce-card-subtitle">
                        Assign employees, monitor task progress, and review submitted work.
                    </p>
                </div>
                <div className="assignment-card-actions">
                    <button className="workforce-button" type="button" onClick={onAssignTask}>
                        <span className="material-symbols-outlined" aria-hidden="true">add</span>
                        Assign Task
                    </button>
                    
                </div>
            </div>

            <AssignmentFilters {...filterProps} />

            <div className="assignment-results-summary">
                Showing <strong>{visibleTasks.length}</strong> of <strong>{taskTotal}</strong> matching assignments
                {stats.reassign > 0 && (
                    <span className="assignment-reassign-summary">
                        <span className="material-symbols-outlined">assignment_ind</span>
                        {stats.reassign} require reassignment
                    </span>
                )}
            </div>

            {loading ? <div className="workforce-empty">Loading tasks…</div> : (
                <div className="workforce-table-wrap">
                    <table className="workforce-table">
                        <thead>
                            <tr>
                                <th>Task</th><th>Employee</th><th>Date</th><th>Status</th>
                                <th>Priority</th><th>Submission</th><th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {visibleTasks.length > 0 ? visibleTasks.map((task) => (
                                <TaskRow
                                    key={task.id}
                                    allEmployeesById={allEmployeesById}
                                    focusedTaskId={focusedTaskId}
                                    onCorrectUsage={onCorrectUsage}
                                    onOpenReview={onOpenReview}
                                    onReassign={onReassign}
                                    onRecordWork={onRecordWork}
                                    onVoidUsage={onVoidUsage}
                                    task={task}
                                />
                            )) : (
                                <tr>
                                    <td colSpan="7">
                                        <div className="workforce-empty assignment-empty">
                                            <span className="material-symbols-outlined">search_off</span>
                                            <strong>No assignments match the selected filters.</strong>
                                            <span>Try changing the search or clearing one of the filters.</span>
                                        </div>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}
            {!loading && tasks.length < taskTotal && (
                <div className="assignment-load-more">
                    <button type="button" className="workforce-button secondary" onClick={onLoadMore}>
                        <span className="material-symbols-outlined">expand_more</span>
                        Load 25 More
                    </button>
                    <span>{taskTotal - tasks.length} more matching assignments</span>
                </div>
            )}
        </section>
    );
}
