import { attendanceStatusForSchedule } from "../../utils/attendanceSchedule.js";
import { attendanceDisplayState, isActiveCalendarTask, isScheduledCalendarRow, leaveForEmployeeDate, taskNeedsCoverage } from "./staffCalendarView.js";

const PRESENT = new Set(["Present", "On Time", "Late", "Checked Out", "Early Departure", "Missing Check Out"]);
const EXCUSED = new Set(["Rest Day", "Special Day Off", "On Leave", "Approved Leave", "Work Suspended", "Authorized Day Off"]);

export function indexStaffCalendar(data = {}) {
    const index = { tasks: new Map(), attendance: new Map(), shifts: new Map(), availability: new Map(), leave: data.leave || [] };
    for (const task of data.tasks || []) {
        if (!index.tasks.has(task.activity_date)) index.tasks.set(task.activity_date, []);
        index.tasks.get(task.activity_date).push(task);
    }
    for (const record of data.attendance || []) index.attendance.set(`${record.employee_id}:${record.attendance_date}`, record);
    for (const shift of data.shifts || []) if (shift.status !== "Cancelled") index.shifts.set(`${shift.employee_id}:${shift.work_date}`, shift);
    for (const day of data.availability || []) index.availability.set(`${day.employee_id}:${day.work_date}`, day);
    return index;
}

export function staffDayRow(index, employee, dateKey, todayKey) {
    const key = `${employee.id}:${dateKey}`;
    const tasks = (index.tasks.get(dateKey) || []).filter((task) => [task.assigned_employee_id, task.original_employee_id, task.covering_employee_id].some((id) => Number(id) === Number(employee.id)));
    const assignedTasks = tasks.filter((task) => Number(task.assigned_employee_id) === Number(employee.id) && isActiveCalendarTask(task));
    const attendance = index.attendance.get(key) || null;
    const shift = index.shifts.get(key) || null;
    const availability = index.availability.get(key) || null;
    const leave = leaveForEmployeeDate(index.leave, employee.id, dateKey);
    const approvedLeave = leave.find((item) => item.status === "Approved") || null;
    const state = attendanceDisplayState({ dateKey, todayKey, attendance, approvedLeave, shift, employee, availability, activeTaskCount: assignedTasks.length });
    return { employee, dateKey, tasks, assignedTasks, attendance, shift, availability, leave, approvedLeave, state };
}

export function staffAttendanceLabel(row, todayKey) {
    if (row.dateKey > todayKey || EXCUSED.has(row.state)) return row.state;
    const status = attendanceStatusForSchedule(row.attendance, row.availability);
    if (row.state === "Possible Absence") return row.state;
    if (status && !["Not Checked In", "Rest Day"].includes(status)) return status;
    if (isScheduledCalendarRow(row)) return "Not Checked In";
    return row.state;
}

export function isNotCheckedIn(row, todayKey) {
    if (row.dateKey > todayKey || EXCUSED.has(row.state) || row.approvedLeave || row.availability?.attendance_suspended_now || !isScheduledCalendarRow(row)) return false;
    return ["Not Checked In", "Possible Absence"].includes(staffAttendanceLabel(row, todayKey));
}

export function attendanceReviewReasons(row, todayKey) {
    if (row.dateKey > todayKey) return [];
    const label = staffAttendanceLabel(row, todayKey);
    return [
        ...(label === "Possible Absence" ? ["Possible absence — verify before marking absent"] : []),
        ...(label === "Missing Check Out" ? ["Missing check-out"] : []),
    ];
}

export function summarizeStaffAttendance(rows, tasks, todayKey) {
    return {
        present: rows.filter((row) => row.dateKey <= todayKey && PRESENT.has(staffAttendanceLabel(row, todayKey))).length,
        notCheckedIn: rows.filter((row) => isNotCheckedIn(row, todayKey)).length,
        leave: rows.filter((row) => ["On Leave", "Approved Leave"].includes(row.state)).length,
        reviewRows: rows.filter((row) => attendanceReviewReasons(row, todayKey).length),
        coverageTasks: (tasks || []).filter(taskNeedsCoverage),
    };
}

export function matchesAttendanceFilter(row, filter, todayKey) {
    const label = staffAttendanceLabel(row, todayKey);
    if (filter === "present") return row.dateKey <= todayKey && PRESENT.has(label);
    if (filter === "not-checked-in") return isNotCheckedIn(row, todayKey);
    if (filter === "needs-review") return attendanceReviewReasons(row, todayKey).length > 0 || row.tasks.some(taskNeedsCoverage);
    if (filter === "absent") return label === "Absent";
    if (filter === "not-scheduled") return ["Rest Day", "Special Day Off", "Work Suspended", "Authorized Day Off"].includes(row.state);
    return true;
}

export function formatStaffTime(value, timeZone = "Asia/Manila") {
    if (!value) return "—";
    // Naive SQL timestamps are already farm-local, not browser-local.
    const naive = String(value).match(/^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?$/);
    if (naive) return naive[1];
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
}

export function validateStaffCalendarPayload(value) {
    if (!value || Array.isArray(value) || ["tasks", "attendance", "leave", "shifts", "availability"].some((key) => !Array.isArray(value[key]))) {
        throw new Error("Attendance information is incomplete. Refresh to try again.");
    }
    return value;
}
