import { formatStaffTime, matchesAttendanceFilter, staffAttendanceLabel } from "./staffAttendance.js";
import { CalendarEventBands } from "../../components/FarmEvents/FarmEvents.jsx";
import { formatDateKey } from "../../utils/farmCalendar.js";
import {
    calendarShiftLabel,
    employeeMatchesAvailabilityFilter,
    sameCalendarMonth,
} from "./staffCalendarView.js";


const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const statusClass = (value) => String(value || "")
    .toLowerCase()
    .replaceAll(" ", "-")
    .replaceAll("/", "-");


function MonthView({
    events, timezone, openEvent,
    anchor,
    days,
    employeeNames,
    goToCoverage,
    goToLeave,
    goToTask,
    openDate,
    summaryForDate,
    todayKey,
}) {
    return (
        <div className="staff-month-calendar" aria-label="Monthly staff calendar">
            <div className="staff-month-weekdays" aria-hidden="true">
                {WEEKDAY_LABELS.map((label) => <span key={label}>{label}</span>)}
            </div>
            <div className="staff-month-grid">
                {days.map((dateKey) => {
                    const summary = summaryForDate(dateKey);
                    const outside = !sameCalendarMonth(dateKey, anchor);
                    const isToday = dateKey === todayKey;
                    const leaves = [...summary.pendingLeaves, ...summary.approvedLeaves].slice(0, 2);
                    const firstTask = summary.activeTasks[0];

                    return (
                        <article
                            key={dateKey}
                            className={`staff-month-cell ${outside ? "outside-month" : ""} ${isToday ? "today" : ""}`}
                        >
                            <button
                                type="button"
                                className="staff-month-cell-hitbox"
                                onClick={() => openDate(dateKey)}
                                aria-label={`Open day view for ${formatDateKey(dateKey, {
                                    month: "long",
                                    day: "numeric",
                                    year: "numeric",
                                })}`}
                            />
                            <div className="staff-month-cell-main" aria-hidden="true">
                                <span className="staff-month-date">
                                    <strong>{formatDateKey(dateKey, { day: "numeric" })}</strong>
                                    {isToday && <em>Today</em>}
                                </span>
                                <span className="staff-month-badges">
                                    <span className="calendar-summary-chip scheduled"><b>{summary.scheduled}</b> Scheduled</span>
                                    {dateKey <= todayKey && summary.present > 0 && <span className="calendar-summary-chip present"><b>{summary.present}</b> Present</span>}
                                    {dateKey <= todayKey && summary.possibleAbsence > 0 && (
                                        <span className="calendar-summary-chip possible-absence">
                                            <b>{summary.possibleAbsence}</b> Possible Absence
                                        </span>
                                    )}
                                    {dateKey <= todayKey && summary.absent > 0 && <span className="calendar-summary-chip absent"><b>{summary.absent}</b> Absent</span>}
                                    {dateKey <= todayKey && summary.late > 0 && <span className="calendar-summary-chip late"><b>{summary.late}</b> Late</span>}
                                    {summary.leave > 0 && <span className="calendar-summary-chip leave"><b>{summary.leave}</b> On Leave</span>}
                                    {summary.rest > 0 && <span className="calendar-summary-chip rest"><b>{summary.rest}</b> Rest Day</span>}
                                    {summary.needsCoverage > 0 && <span className="calendar-summary-chip coverage-needed"><b>{summary.needsCoverage}</b> Needs Coverage</span>}
                                    {summary.covered > 0 && <span className="calendar-summary-chip coverage-covered"><b>{summary.covered}</b> Covered</span>}
                                </span>
                            </div>
                            <div className="staff-month-cell-links">
                                <CalendarEventBands events={events} date={dateKey} timezone={timezone} onOpen={openEvent} />
                                {leaves.map((leave) => (
                                    <button
                                        type="button"
                                        key={`leave-${leave.id}`}
                                        className={`calendar-mini-link leave-${String(leave.status).toLowerCase()}`}
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            goToLeave(leave);
                                        }}
                                        title={`${leave.employee_name || employeeNames.get(Number(leave.employee_id)) || "Employee"} · ${leave.leave_type} · ${leave.status}`}
                                    >
                                        <span className="material-symbols-outlined" aria-hidden="true">event_busy</span>
                                        <span>
                                            {leave.status === "Pending" ? "Pending Leave" : "On Leave"}
                                            {` · ${leave.employee_name || employeeNames.get(Number(leave.employee_id)) || "Employee"}`}
                                        </span>
                                    </button>
                                ))}
                                {summary.needsCoverage > 0 ? (
                                    <button
                                        type="button"
                                        className="calendar-mini-link needs-coverage"
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            goToCoverage(dateKey);
                                        }}
                                    >
                                        <span className="material-symbols-outlined" aria-hidden="true">assignment_late</span>
                                        <span>Needs Coverage</span>
                                    </button>
                                ) : firstTask ? (
                                    <button
                                        type="button"
                                        className="calendar-mini-link task"
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            goToTask(firstTask);
                                        }}
                                        title={`${firstTask.name} — ${firstTask.employee_name || "Unassigned"}`}
                                    >
                                        <span className="material-symbols-outlined" aria-hidden="true">task_alt</span>
                                        <span>{firstTask.name}</span>
                                    </button>
                                ) : null}
                            </div>
                        </article>
                    );
                })}
            </div>
        </div>
    );
}


function WeekView({
    availabilityFilter,
    days,
    employeeDayRow,
    goToEmployee,
    goToLeave,
    goToTasksForDate,
    openDate,
    selectedEmployees,
    todayKey,
}) {
    return (
        <div className="staff-week-wrap">
            <table className="staff-week-table">
                <thead>
                    <tr>
                        <th>Employee</th>
                        {days.map((dateKey) => (
                            <th key={dateKey}>
                                <button type="button" className="calendar-week-date" onClick={() => openDate(dateKey)}
                                    aria-label={`Open day view for ${formatDateKey(dateKey, { month: "long", day: "numeric", year: "numeric" })}`}>
                                    <span>{formatDateKey(dateKey, { weekday: "short" })}</span>
                                    <strong>{formatDateKey(dateKey, { month: "short", day: "numeric" })}</strong>
                                </button>
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {selectedEmployees.map((employee) => (
                        <tr key={employee.id}>
                            <th scope="row">
                                <button type="button" className="calendar-employee-link" onClick={() => goToEmployee(employee)}>
                                    {employee.full_name}
                                </button>
                                <small>{employee.position || "Employee"}</small>
                            </th>
                            {days.map((dateKey) => {
                                const row = employeeDayRow(employee, dateKey);
                                const visible = employeeMatchesAvailabilityFilter({
                                    filter: availabilityFilter,
                                    state: row.state,
                                    tasks: row.tasks,
                                }) && matchesAttendanceFilter(row, availabilityFilter, todayKey);
                                if (!visible) return <td key={dateKey} className="filtered-cell">—</td>;

                                return (
                                    <td key={dateKey}>
                                        <span className={`calendar-state-badge ${statusClass(row.state)}`}>{row.state}</span>
                                        <small>{calendarShiftLabel(row.shift, row.availability)}</small>
                                        {row.leave
                                            .filter((leave) => ["Pending", "Approved"].includes(leave.status))
                                            .slice(0, 1)
                                            .map((leave) => (
                                                <button
                                                    type="button"
                                                    className={`calendar-week-link leave-${leave.status.toLowerCase()}`}
                                                    key={leave.id}
                                                    onClick={() => goToLeave(leave)}
                                                >
                                                    {leave.status === "Pending" ? "Pending Leave" : "On Leave"}
                                                </button>
                                            ))}
                                        <button
                                            type="button"
                                            className="calendar-week-link tasks"
                                            onClick={() => goToTasksForDate(dateKey, employee.id)}
                                        >
                                            {row.assignedTasks.length} active task{row.assignedTasks.length === 1 ? "" : "s"}
                                        </button>
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}


function DayView({ anchor, beginAttendanceView, beginShiftEdit, canManageSchedule, rows, todayKey, timezone }) {
    return <div className="staff-day-wrap staff-attendance-day-wrap">
        <p className="staff-day-time-note">Times use {timezone}. Future dates show the schedule only.</p>
        <table className="staff-day-table staff-attendance-table">
            <thead><tr><th scope="col">Employee</th><th scope="col">Shift</th><th scope="col">Attendance</th><th scope="col">Check In / Out</th><th scope="col">Actions</th></tr></thead>
            <tbody>{rows.length ? rows.map((row) => {
                const label = staffAttendanceLabel(row, todayKey);
                return <tr key={row.employee.id}>
                    <td data-label="Employee"><button type="button" className="calendar-employee-link" onClick={() => beginAttendanceView(row)}>{row.employee.full_name}</button><small>{row.employee.position || "Employee"}</small></td>
                    <td data-label="Shift">{calendarShiftLabel(row.shift, row.availability)}{["Rest Day", "Special Day Off", "Authorized Day Off", "Work Suspended"].includes(row.state) && <small>Not scheduled to check in</small>}</td>
                    <td data-label="Attendance"><span className={`calendar-state-badge ${statusClass(label)}`}>{label}</span></td>
                    <td data-label="Check In / Out"><div className="staff-clock-times"><span>In <strong>{anchor <= todayKey ? formatStaffTime(row.attendance?.check_in_at, timezone) : "—"}</strong></span><span>Out <strong>{anchor <= todayKey ? formatStaffTime(row.attendance?.check_out_at, timezone) : "—"}</strong></span></div></td>
                    <td data-label="Actions"><div className="calendar-row-actions">
                        <button type="button" className="workforce-button secondary" aria-label={`View attendance for ${row.employee.full_name}`} onClick={() => beginAttendanceView(row)}>View Attendance</button>
                        {canManageSchedule && <button type="button" className="workforce-button secondary" onClick={() => beginShiftEdit(row)}>Day Exception</button>}
                    </div></td>
                </tr>;
            }) : <tr><td colSpan={5}><div className="workforce-empty">No employees match the selected filters.</div></td></tr>}</tbody>
        </table>
    </div>;
}


export default function StaffCalendarViews({ mode, rowsForDate, ...props }) {
    if (mode === "month") return <MonthView {...props} />;
    if (mode === "week") return <WeekView {...props} />;
    return <DayView {...props} rows={rowsForDate(props.anchor)} />;
}
