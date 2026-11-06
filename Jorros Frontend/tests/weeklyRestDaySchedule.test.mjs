import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
    applyWeeklyScheduleTemplate,
    makeWeeklySchedule,
    normalizeWeeklySchedule,
    validateWeeklySchedule,
} from "../src/components/WeeklyScheduleEditor/weeklySchedule.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = (relative) => fs.readFileSync(path.join(here, "..", relative), "utf8");

test("default weekly schedule explicitly configures all seven days with Sunday rest", () => {
    const schedule = makeWeeklySchedule("2026-09-13");
    assert.equal(schedule.days.length, 7);
    assert.deepEqual(schedule.days.map((day) => day.day_of_week), [0,1,2,3,4,5,6]);
    assert.equal(schedule.days[6].state, "Rest Day");
    assert.equal(schedule.days[6].start_time, null);
    assert.equal(validateWeeklySchedule(schedule), "");
});

test("quick templates produce Sunday-only and weekend rest schedules without carrying shift hours", () => {
    const base = makeWeeklySchedule("2026-09-13");
    const monSat = applyWeeklyScheduleTemplate(base, "mon-sat");
    const monFri = applyWeeklyScheduleTemplate(base, "mon-fri");
    assert.deepEqual(monSat.days.filter((d) => d.state === "Rest Day").map((d) => d.day_of_week), [6]);
    assert.deepEqual(monFri.days.filter((d) => d.state === "Rest Day").map((d) => d.day_of_week), [5,6]);
    assert.ok(monFri.days.filter((d) => d.state === "Rest Day").every((d) => d.start_time === null && d.end_time === null));
});

test("rotating template keeps seven explicit working baselines and explains dated exceptions", () => {
    const schedule = applyWeeklyScheduleTemplate(makeWeeklySchedule("2026-09-13"), "rotating");
    assert.equal(schedule.schedule_type, "Rotating / No Fixed Rest Day");
    assert.ok(schedule.days.every((day) => day.state === "Working Day"));
    assert.equal(validateWeeklySchedule(schedule), "");
    assert.match(src("src/components/WeeklyScheduleEditor/WeeklyScheduleEditor.jsx"), /dated Working Day \/ Rest Day exceptions in Staff Calendar/);
});

test("shift and break validation rejects invalid working-day ranges", () => {
    const endBeforeStart = makeWeeklySchedule("2026-09-13");
    endBeforeStart.days[0].end_time = "07:00";
    assert.match(validateWeeklySchedule(endBeforeStart), /end time must be after start time/);
    const invalidBreak = makeWeeklySchedule("2026-09-13");
    invalidBreak.days[0].break_start_time = "06:00";
    assert.match(validateWeeklySchedule(invalidBreak), /break must be inside the shift/);
});

test("normalization preserves backend Rest Days and clears their shift times", () => {
    const normalized = normalizeWeeklySchedule({
        effective_from: "2026-09-13",
        schedule_type: "Fixed",
        timezone: "Asia/Manila",
        days: Array.from({ length: 7 }, (_, day_of_week) => ({
            day_of_week,
            is_working_day: day_of_week !== 6,
            start_time: "08:00:00",
            end_time: "17:00:00",
        })),
    });
    assert.equal(normalized.days[6].state, "Rest Day");
    assert.equal(normalized.days[6].start_time, null);
    assert.equal(normalized.days[0].start_time, "08:00");
});

test("employee create/edit and task recurrence UI are wired to schedule and coverage policy", () => {
    const taskManagement = src("src/views/TaskManagement/TaskManagement.jsx");
    const editor = src("src/components/WeeklyScheduleEditor/WeeklyScheduleEditor.jsx");
    assert.match(taskManagement, /WeeklyScheduleEditor/);
    assert.match(editor, /Schedule setup required/);
    assert.match(taskManagement, /backup_employee_id/);
    assert.match(taskManagement, /time_sensitive/);
    assert.match(taskManagement, /controlled_rescheduling/);
    assert.match(taskManagement, /max_delay_minutes/);
});

test("Staff Calendar and My Schedule consume backend availability and expose one-day exceptions read-only to employees", () => {
    const calendar = [
        src("src/views/StaffCalendar/StaffCalendar.jsx"),
        src("src/views/StaffCalendar/StaffCalendarDetailsModal.jsx"),
        src("src/views/StaffCalendar/StaffCalendarToolbar.jsx"),
        src("src/views/StaffCalendar/StaffCalendarViews.jsx"),
        src("src/views/StaffCalendar/staffAttendance.js"),
    ].join("\n");
    const myTasks = src("src/views/MyTasks/MyTasks.jsx");
    assert.match(calendar, /data\.availability/);
    assert.match(calendar, /Working Day Override/);
    assert.match(calendar, /Rest Day Override/);
    assert.match(calendar, /Special Day Off/);
    assert.match(calendar, /Changed Shift/);
    assert.match(myTasks, /scheduleData\.availability/);
    assert.doesNotMatch(myTasks, /updateEmployeeWorkSchedule/);
});
