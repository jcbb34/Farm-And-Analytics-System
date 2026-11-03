import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const source = async (path) => readFile(new URL(path, root), "utf8");

test("My Tasks keeps Assigned Tasks primary and adds compact self-service attendance", async () => {
    const text = await source("src/views/MyTasks/MyTasks.jsx");
    assert.match(text, /label: "Assigned Tasks"/);
    assert.match(text, /Today's Attendance/);
    assert.match(text, /getMyAttendanceToday\(\)/);
    assert.match(text, /workforceService\.checkIn\(\)/);
    assert.match(text, /workforceService\.checkOut\(\)/);
});

test("employee attendance actions are identity-bound and do not accept employee ids or browser timestamps", async () => {
    const text = await source("src/services/workforceService.js");
    assert.match(text, /checkIn: \(notes = null\) => httpClient\.post\("\/workforce\/my-attendance\/check-in", \{ notes \}\)/);
    assert.match(text, /checkOut: \(notes = null\) => httpClient\.post\("\/workforce\/my-attendance\/check-out", \{ notes \}\)/);
    assert.doesNotMatch(text, /checkIn: \(employeeId/);
});

test("attendance buttons prevent duplicate submissions while a mutation is active", async () => {
    const text = await source("src/views/MyTasks/MyTasks.jsx");
    assert.match(text, /if \(attendanceAction\) return/);
    assert.match(text, /disabled=\{Boolean\(attendanceAction\)\}/);
});

test("Staff Calendar exposes assisted attendance, confirmed absence and audited correction workflows", async () => {
    const text = (await Promise.all([
        "src/views/StaffCalendar/StaffCalendar.jsx",
        "src/views/StaffCalendar/StaffCalendarDetailsModal.jsx",
        "src/views/StaffCalendar/StaffCalendarToolbar.jsx",
    ].map(source))).join("\n");
    assert.match(text, /Assisted Check In/);
    assert.match(text, /Assisted Check Out/);
    assert.match(text, /Mark Absent/);
    assert.match(text, /Mark Sick/);
    assert.match(text, /Correction Reason \*/);
    assert.doesNotMatch(text, /Mark Scheduled Employees Present/);
    assert.doesNotMatch(text, /bulkMarkPresent/);
});

test("Staff Calendar does not send browser clock values for assisted clock actions", async () => {
    const text = await source("src/views/StaffCalendar/StaffCalendar.jsx");
    assert.match(text, /assistedCheckIn\(employee, attendanceForm\.notes/);
    assert.match(text, /assistedCheckOut\(employee, attendanceForm\.notes/);
    assert.doesNotMatch(text, /assistedCheckIn\([^\n]*Date/);
});

test("Staff Calendar surfaces missed check-ins as Possible Absence before confirmation", async () => {
    const page = (await Promise.all([
        "src/views/StaffCalendar/StaffCalendar.jsx",
        "src/views/StaffCalendar/StaffCalendarDetailsModal.jsx",
        "src/views/StaffCalendar/StaffCalendarToolbar.jsx",
        "src/views/StaffCalendar/StaffCalendarViews.jsx",
    ].map(source))).join("\n");
    const view = await source("src/views/StaffCalendar/staffCalendarView.js");
    assert.match(page, /Possible Absence/);
    assert.match(page, /Verify the employee first,\s*then mark Absent or Sick/);
    assert.match(page, /value="possible-absence"/);
    assert.match(view, /filter === "possible-absence"/);
});
