import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const readStaffCalendarSource = () => [
    "src/views/StaffCalendar/StaffCalendar.jsx",
    "src/views/StaffCalendar/StaffCalendarToolbar.jsx",
    "src/views/StaffCalendar/StaffCalendarViews.jsx",
    "src/views/StaffCalendar/StaffCalendarDetailsModal.jsx",
].map(read).join("\n");

const calendarModule = await import(pathToFileURL(path.join(root, "src/utils/farmCalendar.js")).href);
const viewModule = await import(pathToFileURL(path.join(root, "src/views/StaffCalendar/staffCalendarView.js")).href);

test("Asia/Manila farm date crosses midnight correctly without UTC date slicing", () => {
    const instant = new Date("2026-09-10T16:30:00.000Z");
    assert.equal(calendarModule.farmDateKey(instant, "Asia/Manila"), "2026-09-11");
    assert.equal(calendarModule.DEFAULT_FARM_TIMEZONE, "Asia/Manila");
});

test("month navigation uses calendar months and clamps month-end boundaries", () => {
    assert.equal(calendarModule.addCalendarMonths("2026-01-31", 1), "2026-02-28");
    assert.equal(calendarModule.moveCalendarAnchor("2026-01-31", "month", 1), "2026-02-28");
    assert.deepEqual(calendarModule.monthRange("2026-02-18"), ["2026-02-01", "2026-02-28"]);
    assert.deepEqual(calendarModule.monthRange("2028-02-18"), ["2028-02-01", "2028-02-29"]);
});

test("Staff Calendar defaults to Month and exposes Month, Week, Day navigation", () => {
    const source = readStaffCalendarSource();
    assert.equal(viewModule.normalizeCalendarView(""), "month");
    assert.equal(viewModule.normalizeCalendarView("invalid"), "month");
    assert.deepEqual(viewModule.monthGridRange("2026-09-12"), ["2026-08-31", "2026-10-04"]);
    assert.match(source, /id:\s*"month"[\s\S]*label:\s*"Month"/);
    assert.match(source, /id:\s*"week"[\s\S]*label:\s*"Week"/);
    assert.match(source, /id:\s*"day"[\s\S]*label:\s*"Day"/);
    assert.match(source, />\s*Previous\s*</);
    assert.match(source, />\s*Today\s*<\/button>/);
    assert.match(source, /Next/);
    assert.match(source, /type="month"/);
    assert.match(source, /getCalendarConfig\(/);
    assert.match(source, /farmTimezone/);
});

test("frontend source does not convert local calendar dates with toISOString slicing", () => {
    const srcRoot = path.join(root, "src");
    const stack = [srcRoot];
    const offending = [];
    while (stack.length) {
        const current = stack.pop();
        for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
            const full = path.join(current, entry.name);
            if (entry.isDirectory()) stack.push(full);
            else if (/\.(js|jsx)$/.test(entry.name)) {
                const text = fs.readFileSync(full, "utf8");
                if (/toISOString\(\)\s*\.\s*(slice\(\s*0\s*,\s*10\s*\)|split\(\s*["']T["']\s*\)\s*\[0\])/.test(text)) {
                    offending.push(path.relative(root, full));
                }
            }
        }
    }
    assert.deepEqual(offending, []);
});

test("staff calendar manages roster and attendance while leave decisions stay in Task Management", () => {
    const page = readStaffCalendarSource();
    const taskManagement = [
        read("src/views/TaskManagement/TaskManagement.jsx"),
        read("src/views/TaskManagement/components/TaskManagementTabs.jsx"),
    ].join("\n");
    const service = read("src/services/workforceService.js");
    assert.match(page, /saveAttendance/);
    assert.match(page, /saveShift/);
    assert.doesNotMatch(page, /Leave decisions and task reassignment stay in/);
    assert.doesNotMatch(page, /const decideLeave = async/);
    assert.doesNotMatch(page, /const cancelLeave = async/);
    assert.doesNotMatch(page, /Record Leave/);
    assert.match(taskManagement, /Leave Requests/);
    assert.match(service, /createShift:/);
    assert.match(service, /decideLeave:/);
    assert.match(service, /cancelLeave:/);
});

test("employee My Tasks contains own weekly schedule and self-service pending leave request only", () => {
    const page = read("src/views/MyTasks/MyTasks.jsx");
    assert.match(page, /<h2>My Schedule<\/h2>/);
    assert.match(page, /getMySchedule\(scheduleWeekStart, scheduleWeekEnd\)/);
    assert.match(page, /<h2>Request Leave<\/h2>/);
    assert.match(page, /requestMyLeave\(/);
    assert.match(page, /submitted as Pending/);
    assert.doesNotMatch(page, /decideLeave\(/);
});

test("staff and employee schedule layouts have tablet/mobile and dark-theme coverage", () => {
    const staffCss = read("src/views/StaffCalendar/StaffCalendar.css");
    const myCss = read("src/views/MyTasks/MyTasks.css");
    for (const css of [staffCss, myCss]) {
        assert.match(css, /@media screen and \(max-width:/);
        assert.match(css, /data-theme="dark"/);
    }
    assert.match(staffCss, /staff-month-grid/);
    assert.match(staffCss, /staff-week-table/);
    assert.match(staffCss, /staff-day-table/);
    assert.match(staffCss, /calendar-details-modal/);
    assert.match(myCss, /my-schedule-week/);
    assert.match(myCss, /my-leave-request/);
});
