import {
    addCalendarDays,
    monthRange,
    parseDateKey,
    startOfWeekKey,
} from "../../utils/farmCalendar.js";

export const CALENDAR_VIEWS = ["month", "week", "day"];
export const AVAILABILITY_FILTERS = ["all", "scheduled", "possible-absence", "leave", "coverage"];
export const TERMINAL_TASK_STATUSES = new Set([
    "Completed",
    "Approved",
    "Resolved",
    "Cancelled",
    "Voided",
    "Archived",
]);

export function normalizeCalendarView(value) {
    return CALENDAR_VIEWS.includes(String(value || "").toLowerCase())
        ? String(value).toLowerCase()
        : "month";
}

export function normalizeAvailabilityFilter(value) {
    return AVAILABILITY_FILTERS.includes(String(value || "").toLowerCase())
        ? String(value).toLowerCase()
        : "all";
}

export function monthGridRange(anchor) {
    const [monthStart, monthEnd] = monthRange(anchor);
    const gridStart = startOfWeekKey(monthStart);
    const endWeekStart = startOfWeekKey(monthEnd);
    return [gridStart, addCalendarDays(endWeekStart, 6)];
}

export function calendarDisplayRange(anchor, view) {
    if (view === "month") return monthGridRange(anchor);
    if (view === "week") {
        const start = startOfWeekKey(anchor);
        return [start, addCalendarDays(start, 6)];
    }
    return [anchor, anchor];
}

export function sameCalendarMonth(dateKey, anchor) {
    const dateValue = parseDateKey(dateKey);
    const anchorValue = parseDateKey(anchor);
    return Boolean(
        dateValue && anchorValue
        && dateValue.year === anchorValue.year
        && dateValue.month === anchorValue.month
    );
}

export function isActiveCalendarTask(task) {
    return Boolean(task) && !task.work_suspended && !task.is_archived && !TERMINAL_TASK_STATUSES.has(String(task.status || ""));
}

export function isTemporarilyCoveredTask(task) {
    if (!isActiveCalendarTask(task)) return false;
    return Boolean(
        task.covering_employee_id
        && ["leave coverage", "rest-day coverage"].includes(String(task.assignment_source || "").toLowerCase())
        && !["Returned", "Resolved", "Cancelled"].includes(String(task.coverage_status || ""))
    );
}

export function taskNeedsCoverage(task) {
    if (!isActiveCalendarTask(task)) return false;
    if (isTemporarilyCoveredTask(task)) return false;
    return Boolean(task.needs_reassignment || !task.assigned_employee_id);
}

export function coverageState(task) {
    if (taskNeedsCoverage(task)) return "Needs Coverage";
    if (isTemporarilyCoveredTask(task)) return "Temporarily Covered";
    if (
        task.coverage_status
        && ["Returned", "Resolved", "Completed"].includes(String(task.coverage_status))
    ) return "Coverage Resolved";
    return "";
}

export function leaveForEmployeeDate(leaveRows, employeeId, dateKey, statuses = ["Pending", "Approved"]) {
    return (leaveRows || []).filter((row) => (
        Number(row.employee_id) === Number(employeeId)
        && row.start_date <= dateKey
        && row.end_date >= dateKey
        && statuses.includes(row.status)
    ));
}

export function attendanceDisplayState({ dateKey, todayKey, attendance, approvedLeave, shift, employee, availability, activeTaskCount = 0 }) {
    const isFuture = dateKey > todayKey;
    const resolvedState = availability?.status;
    if (resolvedState && (isFuture || ["Rest Day", "Special Day Off", "On Leave", "Possible Absence"].includes(resolvedState))) return resolvedState;
    // Only effective attendance from the server may replace its schedule label.
    if (resolvedState && !availability.attendance_status) return resolvedState;
    const raw = String(resolvedState ? availability.attendance_status : attendance?.status || "");

    if (approvedLeave) return isFuture ? "On Leave" : "Approved Leave";
    if (raw === "Day Off") return "Rest Day";

    if (isFuture) {
        if (employee?.employment_status !== "Active") return "Unavailable";
        if (shift && shift.status !== "Cancelled") return "Scheduled";
        if (activeTaskCount > 0) return "Scheduled";
        return "Unavailable";
    }

    if (["Sick", "Sick Leave"].includes(raw)) return "Sick";
    if (raw === "Approved Leave") return "Approved Leave";
    if (raw === "Absent") return "Absent";
    if (raw === "Late") return "Late";
    if (["Present", "On Time", "Checked Out", "Early Departure", "Missing Check Out"].includes(raw)) return "Present";
    if (resolvedState) return resolvedState;
    if (shift && shift.status !== "Cancelled") return "Scheduled";
    if (activeTaskCount > 0) return "Scheduled";
    return employee?.employment_status === "Active" ? "Unavailable" : "Unavailable";
}

export function isScheduledCalendarRow(row) {
    if (typeof row.availability?.is_working_day === "boolean") return row.availability.is_working_day;
    if (["Rest Day", "Special Day Off", "On Leave", "Approved Leave", "Unavailable"].includes(row.state)) return false;
    return Boolean(row.shift && row.shift.status !== "Cancelled")
        || ["Scheduled", "Working Day", "Changed Shift", "Possible Absence", "Present", "Late"].includes(row.state);
}

export function calendarShiftLabel(shift, availability) {
    if (["Rest Day", "Special Day Off"].includes(availability?.status)) return "No shift — scheduled day off";
    if (availability?.status === "On Leave") return "No shift — approved leave";
    const activeShift = shift?.status !== "Cancelled" ? shift : null;
    const startTime = availability ? availability.start_time : activeShift?.start_time;
    const endTime = availability ? availability.end_time : activeShift?.end_time;
    if (!startTime && !activeShift && availability?.is_working_day !== true) return "No roster shift";
    const start = startTime ? String(startTime).slice(0, 5) : "All day";
    const end = endTime ? `–${String(endTime).slice(0, 5)}` : "";
    return `${start}${end}${activeShift?.assigned_area ? ` · ${activeShift.assigned_area}` : ""}`;
}

export function employeeMatchesAvailabilityFilter({ filter, state, tasks }) {
    if (!filter || filter === "all") return true;
    if (filter === "scheduled") return ["Scheduled", "Working Day", "Changed Shift", "Present", "Late", "Possible Absence"].includes(state);
    if (filter === "possible-absence") return state === "Possible Absence";
    if (filter === "leave") return state === "On Leave" || state === "Approved Leave";
    if (filter === "coverage") return (tasks || []).some((task) => taskNeedsCoverage(task) || isTemporarilyCoveredTask(task));
    return true;
}

export function buildCalendarReturnPath({ view = "month", anchor, employeeId = "", availability = "all", selectedDate = "" }) {
    const params = new URLSearchParams();
    params.set("view", normalizeCalendarView(view));
    if (anchor) params.set("date", anchor);
    if (employeeId) params.set("employeeId", String(employeeId));
    if (availability && availability !== "all") params.set("availability", normalizeAvailabilityFilter(availability));
    if (selectedDate) params.set("selectedDate", selectedDate);
    return `/staff-calendar?${params.toString()}`;
}

export function safeStaffCalendarReturnPath(value) {
    if (!value) return "";
    try {
        const decoded = decodeURIComponent(String(value));
        if (!(decoded === "/staff-calendar" || decoded.startsWith("/staff-calendar?") || decoded.startsWith("/staff-calendar#"))) return "";
        if (decoded.startsWith("//") || decoded.includes("://") || decoded.includes("\\")) return "";
        return decoded;
    } catch {
        return "";
    }
}

export function monthInputValue(anchor) {
    const parsed = parseDateKey(anchor);
    if (!parsed) return "";
    return `${parsed.year}-${String(parsed.month).padStart(2, "0")}`;
}

export function anchorFromMonthInput(value, fallback) {
    if (!/^\d{4}-\d{2}$/.test(String(value || ""))) return fallback;
    return `${value}-01`;
}
