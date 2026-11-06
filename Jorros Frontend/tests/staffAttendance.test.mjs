import test from "node:test";
import assert from "node:assert/strict";
import { indexStaffCalendar, staffDayRow, staffAttendanceLabel, isNotCheckedIn, attendanceReviewReasons, summarizeStaffAttendance, matchesAttendanceFilter, formatStaffTime, validateStaffCalendarPayload } from "../src/views/StaffCalendar/staffAttendance.js";
const today = "2026-11-05";
const employee = { id: 1, full_name: "Test Worker", employment_status: "Active" };
const row = (changes = {}) => ({ employee, dateKey: today, state: "Working Day", tasks: [], assignedTasks: [], attendance: null, availability: { is_working_day: true, status: "Working Day" }, ...changes });
test("not checked in excludes excused time, rest, leave, confirmed absence, sick and unknown schedules", () => {
    assert.equal(isNotCheckedIn(row(), today), true);
    for (const state of ["Rest Day", "Special Day Off", "On Leave", "Approved Leave", "Work Suspended", "Authorized Day Off", "Absent", "Sick"]) assert.equal(isNotCheckedIn(row({ state, attendance: { status: state }, availability: { status: state, is_working_day: true } }), today), false, state);
    assert.equal(isNotCheckedIn(row({ availability: { is_working_day: true, attendance_suspended_now: true } }), today), false);
    assert.equal(isNotCheckedIn(row({ state: "Schedule Needs Setup", availability: { is_working_day: null } }), today), false);
});
test("present totals include late arrivals and checkouts while possible absence remains unconfirmed", () => {
    const rows = ["Present", "On Time", "Late", "Checked Out", "Early Departure", "Missing Check Out"].map((status) => row({ attendance: { status } }));
    rows.push(row(), row({ state: "Possible Absence" }), row({ state: "On Leave" }));
    const summary = summarizeStaffAttendance(rows, [], today);
    assert.equal(summary.present, 6); assert.equal(summary.notCheckedIn, 2); assert.equal(summary.leave, 1); assert.equal(summary.reviewRows.length, 2);
});
test("review warnings rely on server statuses rather than inventing absence or checkout deadlines", () => {
    assert.deepEqual(attendanceReviewReasons(row({ attendance: { status: "On Time", check_in_at: `${today}T08:00:00` }, shift: { end_time: "09:00" } }), today), []);
    assert.deepEqual(attendanceReviewReasons(row({ attendance: { status: "Missing Check Out" } }), today), ["Missing check-out"]);
    assert.match(attendanceReviewReasons(row({ state: "Possible Absence" }), today)[0], /verify before marking absent/);
});
test("a working exception supersedes an old unclocked rest-day record", () => {
    const current = row({ attendance: { status: "Day Off" }, availability: { is_working_day: true, exception_type: "Working Day Override", status: "Working Day", attendance_status: null } });
    assert.equal(staffAttendanceLabel(current, today), "Not Checked In"); assert.equal(isNotCheckedIn(current, today), true);
});
test("future dates show schedules without actual attendance totals or review warnings", () => {
    const current = row({ dateKey: "2026-11-06", state: "Scheduled", attendance: { status: "Missing Check Out" } });
    assert.equal(staffAttendanceLabel(current, today), "Scheduled"); assert.equal(isNotCheckedIn(current, today), false); assert.deepEqual(attendanceReviewReasons(current, today), []); assert.equal(summarizeStaffAttendance([current], [], today).present, 0);
});
test("row indexing isolates the exact employee/date and ignores cancelled shifts and pending leave", () => {
    const index = indexStaffCalendar({ tasks: [{ id: 1, activity_date: today, assigned_employee_id: 1, status: "Pending" }, { id: 2, activity_date: today, assigned_employee_id: 2, status: "Pending" }], attendance: [{ employee_id: 1, attendance_date: today, status: "On Time" }], shifts: [{ employee_id: 1, work_date: today, status: "Cancelled" }], leave: [{ employee_id: 1, start_date: today, end_date: today, status: "Pending" }] });
    const current = staffDayRow(index, employee, today, today);
    assert.equal(current.tasks.length, 1); assert.equal(current.shift, null); assert.equal(current.approvedLeave, null); assert.equal(staffAttendanceLabel(current, today), "On Time"); assert.equal(staffDayRow(index, employee, "2026-11-04", today).attendance, null);
});
test("filters distinguish missing check-in, present, confirmed absence and review issues", () => {
    assert.equal(matchesAttendanceFilter(row(), "not-checked-in", today), true); assert.equal(matchesAttendanceFilter(row({ attendance: { status: "Late" } }), "present", today), true); assert.equal(matchesAttendanceFilter(row({ attendance: { status: "Absent" } }), "absent", today), true); assert.equal(matchesAttendanceFilter(row({ state: "Possible Absence" }), "absent", today), false); assert.equal(matchesAttendanceFilter(row({ tasks: [{ status: "Pending", needs_reassignment: true }] }), "needs-review", today), true);
});
test("coverage includes unassigned active work but excludes completed and covered tasks", () => {
    const tasks = [{ id: 1, status: "Pending" }, { id: 2, status: "Completed" }, { id: 3, status: "Pending", assigned_employee_id: 2, covering_employee_id: 2, assignment_source: "Leave Coverage", coverage_status: "Active" }];
    assert.deepEqual(summarizeStaffAttendance([], tasks, today).coverageTasks.map((task) => task.id), [1]);
});
test("SQL farm-local timestamps and UTC instants display the same Manila clock time", () => {
    assert.equal(formatStaffTime("2026-11-05T08:05:12"), "08:05"); assert.equal(formatStaffTime("2026-11-05T00:05:12Z"), "08:05"); assert.equal(formatStaffTime("2026-11-05T08:05:12+08:00"), "08:05"); assert.equal(formatStaffTime(null), "—"); assert.equal(formatStaffTime("invalid"), "—");
});
test("invalid calendar responses are errors rather than successful zero counts", () => {
    for (const value of [null, [], {}, { attendance: [] }]) assert.throws(() => validateStaffCalendarPayload(value), /incomplete/);
    const valid = { tasks: [], attendance: [], leave: [], shifts: [], availability: [] }; assert.equal(validateStaffCalendarPayload(valid), valid);
});
