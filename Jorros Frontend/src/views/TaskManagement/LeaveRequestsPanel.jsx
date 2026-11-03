"use client";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { workforceService } from "../../services/workforceService.js";
import { useNotification } from "../../context/NotificationContext.jsx";
import "./LeaveRequestsPanel.css";

const STATUSES = ["Pending", "Approved", "Rejected", "Cancelled"];
const statusClass = (value) => String(value || "").toLowerCase().replaceAll(" ", "-");

const formatDateTime = (value) => {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
};

function LeaveRequestsPanel({ employees = [], onChanged, initialLeaveRequestId = "", onDismissDeepLink }) {
    const notification = useNotification();
    const [rows, setRows] = useState([]);
    const [filter, setFilter] = useState("Pending");
    const [loading, setLoading] = useState(true);
    const [reviewLoading, setReviewLoading] = useState(false);
    const [review, setReview] = useState(null);
    const [selectedId, setSelectedId] = useState(null);
    const [notes, setNotes] = useState("");
    const [defaultCoverId, setDefaultCoverId] = useState("");
    const [taskCoverIds, setTaskCoverIds] = useState({});
    const [cancelReason, setCancelReason] = useState("");
    const [action, setAction] = useState("");
    const openedDeepLinkRef = useRef("");
    const reviewRequestRef = useRef(0);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            setRows(await workforceService.getLeave() || []);
        } catch (err) {
            notification.error(err?.message || "Unable to load leave requests.", "Leave Requests");
        } finally {
            setLoading(false);
        }
    }, [notification]);

    useEffect(() => { load(); }, [load]);
    useFarmModuleUpdates(["calendar", "tasks"], load);

    const counts = useMemo(() => Object.fromEntries(
        STATUSES.map((status) => [status, rows.filter((item) => item.status === status).length]),
    ), [rows]);

    const visibleRows = useMemo(
        () => rows.filter((item) => filter === "All" || item.status === filter),
        [rows, filter],
    );

    const openReview = async (record) => {
        const requestId = ++reviewRequestRef.current;
        setSelectedId(record.id);
        setReview(null);
        setReviewLoading(true);
        setNotes(record.decision_notes || "");
        setDefaultCoverId(record.default_covering_employee_id ? String(record.default_covering_employee_id) : "");
        setTaskCoverIds({});
        setCancelReason("");
        try {
            const payload = await workforceService.getLeaveReview(record.id);
            if (requestId !== reviewRequestRef.current) return;
            setReview(payload);
            if (payload?.leave?.default_covering_employee_id) {
                setDefaultCoverId(String(payload.leave.default_covering_employee_id));
            }
        } catch (err) {
            if (requestId !== reviewRequestRef.current) return;
            notification.error(err?.message || "Unable to open leave review.", "Leave Review");
            setSelectedId(null);
        } finally {
            if (requestId === reviewRequestRef.current) setReviewLoading(false);
        }
    };

    useEffect(() => {
        if (!initialLeaveRequestId) {
            openedDeepLinkRef.current = "";
            return;
        }
        if (loading || selectedId || openedDeepLinkRef.current === String(initialLeaveRequestId)) return;
        const record = rows.find((item) => String(item.id) === String(initialLeaveRequestId));
        if (!record) return;
        openedDeepLinkRef.current = String(initialLeaveRequestId);
        setFilter(record.status || "All");
        void openReview(record);
    }, [initialLeaveRequestId, loading, rows, selectedId]);


    const closeReview = useCallback(() => {
        if (action) return;
        reviewRequestRef.current += 1;
        setSelectedId(null);
        setReview(null);
        setReviewLoading(false);
        setTaskCoverIds({});
        setDefaultCoverId("");
        setNotes("");
        setCancelReason("");
        onDismissDeepLink?.();
    }, [action, onDismissDeepLink]);

    useEffect(() => {
        if (!selectedId) return undefined;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const onKeyDown = (event) => {
            if (event.key === "Escape") closeReview();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("keydown", onKeyDown);
        };
    }, [selectedId, closeReview]);

    const refreshAfterAction = async () => {
        await Promise.all([load(), onChanged?.()]);
        if (selectedId) {
            try {
                setReview(await workforceService.getLeaveReview(selectedId));
            } catch {
                setReview(null);
            }
        }
    };

    const approve = async () => {
        if (!review?.leave || action) return;
        setAction("approve");
        try {
            const task_coverages = Object.entries(taskCoverIds)
                .filter(([, value]) => value !== undefined)
                .map(([taskId, value]) => ({
                    task_id: Number(taskId),
                    covering_employee_id: value ? Number(value) : null,
                }));
            await workforceService.decideLeave(review.leave.id, {
                decision: "Approved",
                notes: notes.trim() || null,
                default_covering_employee_id: defaultCoverId ? Number(defaultCoverId) : null,
                task_coverages,
            });
            notification.success("Leave approved and temporary coverage applied.", "Leave Approved");
            await refreshAfterAction();
        } catch (err) {
            notification.error(err?.message || "Unable to approve leave.", "Leave Review");
        } finally {
            setAction("");
        }
    };

    const reject = async () => {
        if (!review?.leave || action) return;
        setAction("reject");
        try {
            await workforceService.decideLeave(review.leave.id, {
                decision: "Rejected",
                notes: notes.trim() || null,
            });
            notification.success("Leave request rejected. No task assignments were changed.", "Leave Rejected");
            await refreshAfterAction();
        } catch (err) {
            notification.error(err?.message || "Unable to reject leave.", "Leave Review");
        } finally {
            setAction("");
        }
    };

    const cancel = async () => {
        if (!review?.leave || action) return;
        if (review.leave.status === "Approved" && !cancelReason.trim()) {
            notification.error("Enter a reason before cancelling approved leave.", "Leave Cancellation");
            return;
        }
        setAction("cancel");
        try {
            await workforceService.cancelLeave(review.leave.id, cancelReason.trim() || null);
            notification.success("Leave cancelled and eligible future coverage was recalculated.", "Leave Cancelled");
            await refreshAfterAction();
        } catch (err) {
            notification.error(err?.message || "Unable to cancel leave.", "Leave Cancellation");
        } finally {
            setAction("");
        }
    };

    const candidateById = useMemo(
        () => new Map((review?.covering_candidates || []).map((item) => [String(item.employee_id), item])),
        [review],
    );

    const optionForTask = (candidate, taskId) => candidate?.task_availability?.[String(taskId)] || null;

    return (
        <section className="workforce-card leave-approval-workspace">
            <div className="leave-approval-header">
                <div>
                    <h2>Leave Requests</h2>
                    <p className="workforce-card-subtitle">Review requests, plan temporary coverage, and preserve task assignment history.</p>
                </div>
                <div className="leave-pending-count"><strong>{counts.Pending || 0}</strong><span>Pending</span></div>
            </div>

            <div className="leave-status-tabs" role="tablist" aria-label="Leave request status">
                {["Pending", "Approved", "Rejected", "Cancelled", "All"].map((status) => (
                    <button
                        type="button"
                        key={status}
                        className={`workforce-tab ${filter === status ? "active" : ""}`}
                        onClick={() => setFilter(status)}
                    >
                        {status}{status !== "All" ? ` (${counts[status] || 0})` : ` (${rows.length})`}
                    </button>
                ))}
            </div>

            <div className="workforce-table-wrap">
                <table className="workforce-table leave-request-table">
                    <thead>
                        <tr><th>Employee</th><th>Leave</th><th>Affected Tasks</th><th>Reason</th><th>Status</th><th>Requested / Reviewed</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        {loading ? <tr><td colSpan="7"><div className="workforce-empty">Loading leave requests…</div></td></tr> :
                            visibleRows.length === 0 ? <tr><td colSpan="7"><div className="workforce-empty">No {filter === "All" ? "" : filter.toLowerCase()} leave requests.</div></td></tr> :
                                visibleRows.map((item) => (
                                    <tr key={item.id} className={String(item.id) === String(initialLeaveRequestId) ? "leave-row-deep-link" : ""}>
                                        <td><strong>{item.employee_name || `Employee #${item.employee_id}`}</strong></td>
                                        <td><strong>{item.leave_type}</strong><br/><small>{item.start_date} to {item.end_date}</small></td>
                                        <td><strong>{item.affected_task_count || 0}</strong></td>
                                        <td>{item.reason || "—"}</td>
                                        <td><span className={`leave-status-badge ${statusClass(item.status)}`}>{item.status}</span></td>
                                        <td>
                                            <small>Requested: {formatDateTime(item.request_date)}</small>
                                            {item.reviewed_by_name && <><br/><small>Reviewed: {item.reviewed_by_name} · {formatDateTime(item.decided_at)}</small></>}
                                        </td>
                                        <td><button type="button" className="workforce-button secondary" onClick={() => openReview(item)}>Review Request</button></td>
                                    </tr>
                                ))
                        }
                    </tbody>
                </table>
            </div>

            {selectedId && (
                <div className="workforce-modal-overlay leave-review-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) closeReview(); }}>
                    <div className="leave-review-modal" role="dialog" aria-modal="true" aria-labelledby="leave-review-title" onMouseDown={(event) => event.stopPropagation()}>
                        <header className="leave-review-modal-header">
                            <div><span className="work-review-eyebrow">Task Management</span><h2 id="leave-review-title">Review Leave Request</h2></div>
                            <button type="button" className="workforce-modal-close" onClick={closeReview} disabled={Boolean(action)} aria-label="Close leave review"><span className="material-symbols-outlined">close</span></button>
                        </header>

                        <div className="leave-review-modal-body">
                            {reviewLoading ? <div className="workforce-empty">Loading leave details…</div> : review && <>
                                <section className="leave-review-section">
                                    <h3>Request Information</h3>
                                    <div className="leave-review-detail-grid">
                                        <div><span>Employee</span><strong>{review.leave.employee_name}</strong></div>
                                        <div><span>Availability</span><strong>{review.employee_availability}</strong></div>
                                        <div><span>Leave type</span><strong>{review.leave.leave_type}</strong></div>
                                        <div><span>Dates</span><strong>{review.leave.start_date} to {review.leave.end_date}</strong></div>
                                        <div><span>Requested</span><strong>{formatDateTime(review.leave.request_date)}</strong></div>
                                        <div><span>Status</span><strong>{review.leave.status}</strong></div>
                                        <div className="full"><span>Reason</span><strong>{review.leave.reason || "No reason provided."}</strong></div>
                                        {review.leave.reviewed_by_name && <div className="full"><span>Review</span><strong>{review.leave.reviewed_by_name} · {formatDateTime(review.leave.decided_at)}{review.leave.decision_notes ? ` · ${review.leave.decision_notes}` : ""}</strong></div>}
                                    </div>
                                </section>

                                <section className="leave-review-section">
                                    <h3>Overlapping Schedule / Availability</h3>
                                    <div className="leave-overlap-grid">
                                        <div><strong>Attendance</strong>{review.attendance?.length ? review.attendance.map((row) => <span key={row.id}>{row.attendance_date}: {row.status}</span>) : <span>No attendance conflicts recorded.</span>}</div>
                                        <div><strong>Roster shifts</strong>{review.shifts?.length ? review.shifts.map((row) => <span key={row.id}>{row.work_date}: {row.status}{row.assigned_area ? ` · ${row.assigned_area}` : ""}</span>) : <span>No active shifts recorded.</span>}</div>
                                        <div><strong>Other leave</strong>{review.overlapping_leave?.length ? review.overlapping_leave.map((row) => <span key={row.id}>{row.leave_type}: {row.start_date} to {row.end_date}</span>) : <span>No overlapping Pending/Approved leave.</span>}</div>
                                    </div>
                                </section>

                                <section className="leave-review-section">
                                    <div className="leave-review-section-heading">
                                        <div><h3>Affected Tasks & Temporary Coverage</h3><p>Only Pending, unstarted tasks are transferred automatically. In Progress and protected statuses remain untouched.</p></div>
                                        {review.leave.status === "Pending" && <label className="leave-default-cover"><span>Cover all eligible tasks</span><select value={defaultCoverId} onChange={(event) => setDefaultCoverId(event.target.value)}><option value="">No cover — Needs Reassignment</option>{(review.covering_candidates || []).map((candidate) => <option key={candidate.employee_id} value={candidate.employee_id} disabled={!candidate.available_for_all}>{candidate.employee_name}{candidate.available_for_all ? "" : " — unavailable for one or more tasks"}</option>)}</select></label>}
                                    </div>
                                    <div className="workforce-table-wrap">
                                        <table className="workforce-table leave-affected-task-table">
                                            <thead><tr><th>Task</th><th>Date</th><th>Status</th><th>Location / Source</th><th>Coverage</th></tr></thead>
                                            <tbody>
                                                {(review.affected_tasks || []).length === 0 ? <tr><td colSpan="5"><div className="workforce-empty compact">No assigned tasks fall inside this leave period.</div></td></tr> :
                                                    review.affected_tasks.map((task) => (
                                                        <tr key={task.id}>
                                                            <td><strong>{task.name}</strong><br/><small>{task.activity_code}</small></td>
                                                            <td>{task.activity_date}<br/><small>{task.start_time}</small></td>
                                                            <td><span className={`task-status ${statusClass(task.status)}`}>{task.status}</span>{task.needs_reassignment && <><br/><span className="task-reassignment-badge">Needs Reassignment</span></>}</td>
                                                            <td>{task.location}<br/><small>{task.source_module || "Manual"} · {task.source_type || "task"}</small></td>
                                                            <td>
                                                                {review.leave.status === "Pending" && task.status === "Pending" ? (
                                                                    <select
                                                                        value={taskCoverIds[String(task.id)] ?? ""}
                                                                        onChange={(event) => setTaskCoverIds((current) => ({ ...current, [String(task.id)]: event.target.value }))}
                                                                        aria-label={`Coverage for ${task.name}`}
                                                                    >
                                                                        <option value="">Use default / no cover</option>
                                                                        {(review.covering_candidates || []).map((candidate) => {
                                                                            const availability = optionForTask(candidate, task.id);
                                                                            return <option key={candidate.employee_id} value={candidate.employee_id} disabled={!availability?.available}>{candidate.employee_name}{availability?.available ? "" : " — unavailable"}</option>;
                                                                        })}
                                                                    </select>
                                                                ) : task.assignment_source === "Leave Coverage" ? (
                                                                    <div className="leave-coverage-summary"><strong>{task.covering_employee_name || "Needs Reassignment"}</strong><span>Originally {task.original_employee_name || review.leave.employee_name}</span>{task.coverage_indicator && <span>{task.coverage_indicator}</span>}</div>
                                                                ) : <span>Assignment preserved</span>}
                                                            </td>
                                                        </tr>
                                                    ))
                                                }
                                            </tbody>
                                        </table>
                                    </div>
                                </section>

                                <section className="leave-review-section">
                                    <h3>Covering Employee Availability</h3>
                                    <div className="leave-candidate-grid">
                                        {(review.covering_candidates || []).map((candidate) => (
                                            <article key={candidate.employee_id} className={`leave-candidate-card ${candidate.available_for_all ? "available" : "warning"}`}>
                                                <strong>{candidate.employee_name}</strong>
                                                <span>{candidate.position || "No position recorded"}{candidate.assigned_area ? ` · ${candidate.assigned_area}` : ""}</span>
                                                {candidate.blockers?.map((message) => <small className="blocker" key={message}>{message}</small>)}
                                                {candidate.warnings?.map((message) => <small key={message}>{message}</small>)}
                                                {!candidate.blockers?.length && !candidate.warnings?.length && <small>Available for all affected task dates.</small>}
                                            </article>
                                        ))}
                                    </div>
                                </section>

                                <section className="leave-review-section">
                                    <h3>Review Notes</h3>
                                    <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows="3" placeholder="Approval/rejection notes and coverage reason…" disabled={review.leave.status !== "Pending" || Boolean(action)} />
                                    {(review.leave.status === "Pending" || review.leave.status === "Approved") && <div className="leave-cancel-reason"><label>Cancellation reason {review.leave.status === "Approved" ? "*" : "(optional)"}</label><textarea value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} rows="2" placeholder="Reason for cancelling this leave request…" /></div>}
                                </section>
                            </>}
                        </div>

                        <footer className="leave-review-modal-footer">
                            <div>
                                {review?.leave?.status === "Pending" && <button type="button" className="workforce-button danger" onClick={cancel} disabled={Boolean(action)}>Cancel Request</button>}
                                {review?.leave?.status === "Approved" && <button type="button" className="workforce-button danger" onClick={cancel} disabled={Boolean(action)}>Cancel Approved Leave</button>}
                            </div>
                            <div className="leave-review-primary-actions">
                                <button type="button" className="workforce-button secondary" onClick={closeReview} disabled={Boolean(action)}>Close</button>
                                {review?.leave?.status === "Pending" && <>
                                    <button type="button" className="workforce-button warn" onClick={reject} disabled={Boolean(action)}>{action === "reject" ? "Rejecting…" : "Reject"}</button>
                                    <button type="button" className="workforce-button" onClick={approve} disabled={Boolean(action)}>{action === "approve" ? "Approving…" : "Approve Leave"}</button>
                                </>}
                            </div>
                        </footer>
                    </div>
                </div>
            )}
        </section>
    );
}

export default LeaveRequestsPanel;
