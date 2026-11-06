import { useLayoutEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { formatDateKey } from "../../utils/farmCalendar.js";
import { attendanceStatusForSchedule } from "../../utils/attendanceSchedule.js";
import { formatStaffTime, staffAttendanceLabel } from "./staffAttendance.js";
import { calendarShiftLabel, coverageState, isTemporarilyCoveredTask, taskNeedsCoverage } from "./staffCalendarView.js";



const ATTENDANCE_OPTIONS = [
    "Present",
    "On Time",
    "Late",
    "Checked Out",
    "Early Departure",
    "Missing Check Out",
    "Absent",
    "Sick",
];
const SHIFT_STATUSES = ["Scheduled", "Confirmed", "Completed", "Cancelled"];
const SCHEDULE_EXCEPTION_TYPES = [
    "",
    "Working Day Override",
    "Rest Day Override",
    "Special Day Off",
    "Changed Shift",
];

function AttendanceEditor({
    attendance,
    attendanceBusy,
    attendanceForm,
    availability,
    editor,
    employee,
    onCancel,
    onRequestWorkingDayOverride,
    runAttendanceAction,
    saveAttendance,
    setAttendanceForm,
    todayKey,
    farmTimezone,
}) {
    const isToday = editor.dateKey === todayKey;
    const needsWorkingDayOverride = ["Rest Day", "Special Day Off"].includes(availability?.status);
    const attendanceBlocked = needsWorkingDayOverride || availability?.status === "On Leave" || availability?.attendance_suspended_now;
    const scheduledShift = availability?.start_time && availability?.end_time
        ? `${String(availability.start_time).slice(0, 5)}–${String(availability.end_time).slice(0, 5)}`
        : availability?.status || "Schedule Needs Setup";
    const currentStatus = attendanceStatusForSchedule(attendance, availability)
        || (availability?.status === "Possible Absence" ? "Possible Absence" : "Not Checked In");

    return (
        <section className="calendar-drawer-section calendar-inline-editor attendance-editor">
            <fieldset className="calendar-editor-lock" disabled={Boolean(attendanceBusy)}>
            <div className="calendar-section-heading">
                <div>
                    <h3>Review Attendance</h3>
                    <p>Check-ins are recorded automatically when employees check in. Use this only for absence review or an authorized correction.</p>
                </div>
                <strong>{employee?.full_name || "Employee"}</strong>
            </div>
            <div className="attendance-detail-grid">
                <div><span>Date</span><strong>{editor.dateKey}</strong></div>
                <div><span>Scheduled Shift</span><strong>{scheduledShift}</strong></div>
                <div><span>Current Attendance</span><strong>{currentStatus}</strong></div>
                <div><span>Source</span><strong>{attendance?.attendance_source || "Not recorded"}</strong></div>
                <div>
                    <span>Check In</span>
                    <strong>{attendance?.check_in_at ? formatStaffTime(attendance.check_in_at, farmTimezone) : "Not recorded"}</strong>
                </div>
                <div>
                    <span>Check Out</span>
                    <strong>{attendance?.check_out_at ? formatStaffTime(attendance.check_out_at, farmTimezone) : "Not recorded"}</strong>
                </div>
            </div>
            {availability?.status === "Possible Absence" && (
                <p className="calendar-attendance-warning">
                    No check-in was detected after the scheduled start and grace window. Verify the employee first,
                    then mark Absent or Sick to trigger coverage.
                </p>
            )}
            {needsWorkingDayOverride && <div className="calendar-attendance-warning" role="note">
                <p>Working Day Override required. This employee is scheduled off on this date.</p>
                {onRequestWorkingDayOverride && <button type="button" className="workforce-button secondary" disabled={Boolean(attendanceBusy)} onClick={onRequestWorkingDayOverride}>Create Working Day Override</button>}
            </div>}
            {availability?.status === "On Leave" && <p className="calendar-attendance-warning">Approved leave blocks attendance. Review the approved leave before recording work.</p>}
            {availability?.suspensions?.length > 0 && <p className="calendar-attendance-warning">{availability.suspensions.map((x) => x.title).join("; ")}. Attendance is excused during affected hours. Owner/Admin must authorize essential duty before assisted check-in.</p>}
            <div className="calendar-editor-form attendance-notes">
                <label className="full">
                    <span>Notes</span>
                    <textarea rows={3} placeholder="Optional notes about this attendance action"
                        value={attendanceForm.notes}
                        onChange={(event) => setAttendanceForm({ ...attendanceForm, notes: event.target.value })}
                    />
                </label>
            </div>
            <div className="calendar-editor-actions attendance-action-row">
                {isToday && !attendance?.check_in_at && (
                    <button
                        type="button"
                        className="workforce-button"
                        disabled={Boolean(attendanceBusy) || attendanceBlocked}
                        onClick={() => runAttendanceAction("check-in")}
                    >
                        Assisted Check In
                    </button>
                )}
                {isToday && attendance?.check_in_at && !attendance?.check_out_at && (
                    <button
                        type="button"
                        className="workforce-button"
                        disabled={Boolean(attendanceBusy) || attendanceBlocked}
                        onClick={() => runAttendanceAction("check-out")}
                    >
                        Assisted Check Out
                    </button>
                )}
                <button
                    type="button"
                    className="workforce-button secondary"
                    disabled={Boolean(attendanceBusy) || attendanceBlocked}
                    onClick={() => runAttendanceAction("absent")}
                >
                    Mark Absent
                </button>
                <button
                    type="button"
                    className="workforce-button secondary"
                    disabled={Boolean(attendanceBusy) || attendanceBlocked}
                    onClick={() => runAttendanceAction("sick")}
                >
                    Mark Sick
                </button>
            </div>
            <form className="calendar-editor-form attendance-correction-form" onSubmit={saveAttendance}>
                <h4>Authorized Correction</h4>
                <label>
                    <span>Corrected Status</span>
                    <select
                        value={attendanceForm.status}
                        onChange={(event) => setAttendanceForm({ ...attendanceForm, status: event.target.value })}
                    >
                        {ATTENDANCE_OPTIONS.map((status) => <option value={status} key={status}>{status}</option>)}
                    </select>
                </label>
                <label className="full">
                    <span>Correction Reason *</span>
                    <textarea
                        required
                        value={attendanceForm.correction_reason}
                        onChange={(event) => setAttendanceForm({ ...attendanceForm, correction_reason: event.target.value })}
                    />
                </label>
                <div className="calendar-editor-actions">
                    <button type="button" className="workforce-button secondary" disabled={Boolean(attendanceBusy)} onClick={onCancel}>Cancel</button>
                    <button className="workforce-button" disabled={Boolean(attendanceBusy)}>
                        {attendanceBusy === "correction" ? "Saving…" : "Save Correction"}
                    </button>
                </div>
            </form>
            {attendance?.audit?.length > 0 && (
                <div className="attendance-audit-list">
                    <strong>Audit History</strong>
                    {attendance.audit.slice(-4).map((item) => (
                        <span key={item.id}>
                            {item.action} · {item.actor_name} · {new Date(item.created_at).toLocaleString()}
                            {item.reason ? ` · ${item.reason}` : ""}
                        </span>
                    ))}
                </div>
            )}
            </fieldset>
        </section>
    );
}


function ShiftEditor({ employee, onCancel, saveShift, setShiftForm, shiftForm, attendanceBusy }) {
    const dayOff = ["Rest Day Override", "Special Day Off"].includes(shiftForm.exception_type);
    return (
        <section className="calendar-drawer-section calendar-inline-editor">
            <fieldset className="calendar-editor-lock" disabled={Boolean(attendanceBusy)}>
            <div className="calendar-section-heading">
                <h3>{shiftForm.id ? "Edit Shift / Schedule Exception" : "Add Shift / Schedule Exception"}</h3>
                <strong>{employee?.full_name || "Selected employee"}</strong>
            </div>
            <form className="calendar-editor-form" onSubmit={saveShift}>
                <label>
                    <span id="calendar-exception-label">Schedule exception</span>
                    <select
                        aria-labelledby="calendar-exception-label"
                        aria-describedby="calendar-exception-help"
                        value={shiftForm.exception_type}
                        onChange={(event) => {
                            const exceptionType = event.target.value;
                            const clearsHours = ["Rest Day Override", "Special Day Off"].includes(exceptionType);
                            setShiftForm({
                                ...shiftForm,
                                exception_type: exceptionType,
                                start_time: clearsHours ? "" : shiftForm.start_time,
                                end_time: clearsHours ? "" : shiftForm.end_time,
                            });
                        }}
                    >
                        {SCHEDULE_EXCEPTION_TYPES.map((type) => (
                            <option key={type || "none"} value={type}>{type || "Use weekly schedule"}</option>
                        ))}
                    </select>
                    <small id="calendar-exception-help" className="workforce-help-text">Use Working Day Override to schedule work on a rest day.</small>
                </label>
                <label>
                    <span>Status</span>
                    <select
                        value={shiftForm.status}
                        onChange={(event) => setShiftForm({ ...shiftForm, status: event.target.value })}
                    >
                        {SHIFT_STATUSES.map((status) => <option key={status}>{status}</option>)}
                    </select>
                </label>
                <label>
                    <span>Start</span>
                    <input
                        type="time"
                        value={shiftForm.start_time}
                        disabled={dayOff}
                        onChange={(event) => setShiftForm({ ...shiftForm, start_time: event.target.value })}
                    />
                </label>
                <label>
                    <span>End</span>
                    <input
                        type="time"
                        value={shiftForm.end_time}
                        disabled={dayOff}
                        onChange={(event) => setShiftForm({ ...shiftForm, end_time: event.target.value })}
                    />
                </label>
                <label>
                    <span>Assigned Area</span>
                    <input
                        value={shiftForm.assigned_area}
                        onChange={(event) => setShiftForm({ ...shiftForm, assigned_area: event.target.value })}
                    />
                </label>
                <label className="full">
                    <span>Exception reason</span>
                    <input
                        value={shiftForm.exception_reason}
                        placeholder="Optional reason for this date only"
                        onChange={(event) => setShiftForm({ ...shiftForm, exception_reason: event.target.value })}
                    />
                </label>
                <label className="full">
                    <span>Notes</span>
                    <textarea
                        value={shiftForm.notes}
                        onChange={(event) => setShiftForm({ ...shiftForm, notes: event.target.value })}
                    />
                </label>
                <div className="calendar-editor-actions">
                    <button type="button" className="workforce-button secondary" disabled={Boolean(attendanceBusy)} onClick={onCancel}>Cancel</button>
                    <button className="workforce-button" disabled={Boolean(attendanceBusy)}>{shiftForm.id ? "Update Shift" : "Add Shift"}</button>
                </div>
            </form>
            </fieldset>
        </section>
    );
}


export default function StaffCalendarDetailsModal({
    attendanceBusy, attendanceByEmployeeDate, attendanceForm, availabilityByEmployeeDate,
    closeDateDetails, detailsModalRef, editor, employees, onRequestWorkingDayOverride,
    portalReady, runAttendanceAction, saveAttendance, saveShift, selectedDate,
    setAttendanceForm, setShiftForm, shiftForm, todayKey,
    actionError, canManage, row, onReviewAttendance, farmTimezone,
    goToCoverage, goToLeave, goToTask, goToTasksForDate,
}) {
    const bodyRef = useRef(null);
    const editorKey = editor ? `${editor.type}:${editor.employeeId}:${editor.dateKey}` : "";

    useLayoutEffect(() => {
        if (!portalReady || !selectedDate || !editorKey) return;
        const body = bodyRef.current;
        if (!body) return;
        body.scrollTop = 0;
        body.querySelector('input:not([disabled]), select:not([disabled]), textarea:not([disabled])')?.focus({ preventScroll: true });
    }, [editorKey, portalReady, selectedDate]);

    if (!portalReady || !selectedDate || !editor) return null;

    const attendance = attendanceByEmployeeDate.get(`${editor.employeeId}:${editor.dateKey}`) || null;
    const availability = availabilityByEmployeeDate.get(`${editor.employeeId}:${editor.dateKey}`) || null;
    const employee = employees.find((item) => Number(item.id) === Number(editor.employeeId));
    const relevantLeave = (row?.leave || []).filter((leave) => ["Pending", "Approved"].includes(leave.status));
    const coverage = (row?.tasks || []).filter((task) => taskNeedsCoverage(task) || isTemporarilyCoveredTask(task));

    return createPortal(
        <div className="calendar-modal-portal workforce-layout">
            <div className="calendar-modal-backdrop" onMouseDown={closeDateDetails} aria-hidden="true" />
            <section ref={detailsModalRef} tabIndex={-1} className="calendar-details-modal"
                role="dialog" aria-modal="true" aria-labelledby="calendar-details-title">
                <header>
                    <div>
                        <span className="calendar-drawer-kicker">{editor.type === "shift" ? "Schedule Exception" : "Attendance"}</span>
                        <h2 id="calendar-details-title">{formatDateKey(selectedDate, {
                            weekday: "long", month: "long", day: "numeric", year: "numeric",
                        })}</h2>
                    </div>
                    <button type="button" className="calendar-drawer-close" onClick={closeDateDetails} disabled={Boolean(attendanceBusy)} aria-label="Close calendar editor">
                        <span className="material-symbols-outlined" aria-hidden="true">close</span>
                    </button>
                </header>
                <div className="calendar-details-body" ref={bodyRef}>
                    {actionError && <div className="workforce-error" role="alert">{actionError}</div>}
                    {editor.type === "view" && row && <section className="calendar-drawer-section staff-attendance-readonly">
                        <h3>{employee?.full_name || "Employee"}</h3><p>Read-only attendance details · {farmTimezone}</p>
                        <div className="attendance-detail-grid">
                            <div><span>Scheduled Shift</span><strong>{calendarShiftLabel(row.shift, row.availability)}</strong></div>
                            <div><span>Attendance</span><strong>{staffAttendanceLabel(row, todayKey)}</strong></div>
                            <div><span>Source</span><strong>{attendance?.attendance_source || "Not recorded"}</strong></div>
                            <div><span>Check In</span><strong>{editor.dateKey <= todayKey ? formatStaffTime(attendance?.check_in_at, farmTimezone) : "—"}</strong></div>
                            <div><span>Check Out</span><strong>{editor.dateKey <= todayKey ? formatStaffTime(attendance?.check_out_at, farmTimezone) : "—"}</strong></div>
                        </div>
                        <div className="staff-attendance-related">
                            <h4>Tasks &amp; Coverage</h4>
                            <div className="staff-row-details-content">
                                <button type="button" className="calendar-inline-record" onClick={() => goToTasksForDate(editor.dateKey, row.employee.id)}>Active tasks: {row.assignedTasks.length}</button>
                                {relevantLeave.map((leave) => <button type="button" className="calendar-inline-record" key={leave.id} onClick={() => goToLeave(leave)}>{leave.status === "Pending" ? "Pending Leave" : "On Leave"}</button>)}
                                {coverage.map((task) => <button type="button" className="calendar-inline-record" key={task.id} onClick={() => taskNeedsCoverage(task) ? goToCoverage(editor.dateKey) : goToTask(task)}>{coverageState(task)} · {task.name}</button>)}
                                {!coverage.length && <span>No coverage issue</span>}
                            </div>
                        </div>
                        <details className="staff-row-details"><summary>Notes and correction history</summary>
                            <p>{attendance?.notes || "No attendance notes recorded."}</p>
                            {attendance?.audit?.length ? <ul>{attendance.audit.map((item) => <li key={item.id}>{item.action} · {item.actor_name || "System"} · {item.created_at?.replace("T", " ")}{item.reason ? ` · ${item.reason}` : ""}</li>)}</ul> : <p>No correction history recorded.</p>}
                        </details>
                        {canManage && <button type="button" className="workforce-button" disabled={editor.dateKey > todayKey} onClick={() => onReviewAttendance(row)}>Review / Correct Attendance</button>}
                        {editor.dateKey > todayKey && <p>Attendance can be reviewed on or after this date.</p>}
                    </section>}
                    {editor.type === "attendance" && <AttendanceEditor
                        attendance={attendance} attendanceBusy={attendanceBusy} attendanceForm={attendanceForm}
                        availability={availability} editor={editor} employee={employee}
                        onCancel={closeDateDetails} onRequestWorkingDayOverride={onRequestWorkingDayOverride}
                        runAttendanceAction={runAttendanceAction} saveAttendance={saveAttendance}
                        setAttendanceForm={setAttendanceForm} todayKey={todayKey} farmTimezone={farmTimezone}
                    />}
                    {editor.type === "shift" && <ShiftEditor employee={employee} onCancel={closeDateDetails}
                        saveShift={saveShift} setShiftForm={setShiftForm} shiftForm={shiftForm} attendanceBusy={attendanceBusy}
                    />}
                </div>
            </section>
        </div>,
        document.body,
    );
}
