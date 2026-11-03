import test from "node:test";
import assert from "node:assert/strict";
import { attendanceStatusForSchedule } from "../src/utils/attendanceSchedule.js";
import { attendanceDisplayState, calendarShiftLabel, isScheduledCalendarRow } from "../src/views/StaffCalendar/staffCalendarView.js";

const base = { dateKey: "2026-11-01", todayKey: "2026-11-01", employee: { employment_status: "Active" } };
const working = { status: "Working Day", is_working_day: true, exception_type: "Working Day Override", attendance_status: null, start_time: "08:00:00", end_time: "17:00:00" };
const off = { status: "Rest Day", is_working_day: false };
const oldDayOff = { status: "Day Off", check_in_at: null, check_out_at: null };

test("saved working availability wins over an old rest-day marker without marking Present", () => {
    assert.equal(attendanceDisplayState({ ...base, attendance: oldDayOff, availability: working }), "Working Day");
    assert.equal(attendanceStatusForSchedule(oldDayOff, working), "Not Checked In");
    assert.equal(oldDayOff.status, "Day Off");
    assert.equal(attendanceDisplayState({ ...base, availability: { ...working, attendance_status: "Not Checked In" } }), "Working Day");
});

test("effective attendance, approved leave and future dates retain their own meaning", () => {
    assert.equal(attendanceDisplayState({ ...base, availability: { ...working, attendance_status: "On Time" } }), "Present");
    assert.equal(attendanceDisplayState({ ...base, availability: { ...working, attendance_status: "Late" } }), "Late");
    assert.equal(attendanceDisplayState({ ...base, availability: { ...working, status: "Unavailable", attendance_status: "Sick" } }), "Sick");
    assert.equal(attendanceDisplayState({ ...base, attendance: { status: "Present" }, availability: off }), "Rest Day");
    assert.equal(attendanceDisplayState({ ...base, availability: { status: "On Leave" } }), "On Leave");
    assert.equal(attendanceDisplayState({ ...base, dateKey: "2026-11-08", availability: { ...working, attendance_status: "Present" } }), "Working Day");
    assert.equal(attendanceDisplayState({ ...base, availability: { ...working, status: "Possible Absence" } }), "Possible Absence");
});

test("historical attendance is only superseded for an unclocked Day Off with a saved working exception", () => {
    assert.equal(attendanceStatusForSchedule(oldDayOff, off), "Rest Day");
    assert.equal(attendanceStatusForSchedule(oldDayOff, { ...working, exception_type: null }), "Rest Day");
    assert.equal(attendanceStatusForSchedule({ ...oldDayOff, check_in_at: "2026-11-01T08:00:00" }, working), "Rest Day");
    assert.equal(attendanceStatusForSchedule({ status: "Absent" }, working), "Absent");
    assert.equal(attendanceStatusForSchedule({ status: "Sick" }, working), "Sick");
    assert.equal(attendanceStatusForSchedule(oldDayOff, { ...working, exception_type: "Changed Shift" }), "Not Checked In");
});

test("staff totals count working dates and exclude rest exceptions and approved leave", () => {
    const rows = [
        { availability: working, state: "Working Day" },
        { availability: { ...working, status: "Possible Absence" }, state: "Possible Absence" },
        { availability: off, shift: { status: "Scheduled" }, state: "Rest Day" },
        { availability: { status: "On Leave", is_working_day: null }, shift: { status: "Scheduled" }, state: "On Leave" },
    ];
    assert.equal(rows.filter(isScheduledCalendarRow).length, 2);
    assert.equal(isScheduledCalendarRow({ state: "Scheduled", shift: { status: "Scheduled" } }), true);
});

test("Day and Week shift labels use effective hours and do not show a stale off-day shift", () => {
    assert.equal(calendarShiftLabel(null, working), "08:00–17:00");
    assert.equal(calendarShiftLabel({ start_time: "06:00", end_time: "14:00", status: "Scheduled", assigned_area: "Pen A" }, working), "08:00–17:00 · Pen A");
    assert.equal(calendarShiftLabel({ status: "Scheduled", start_time: "08:00" }, off), "No shift — scheduled day off");
    assert.equal(calendarShiftLabel(null, { status: "On Leave" }), "No shift — approved leave");
});
