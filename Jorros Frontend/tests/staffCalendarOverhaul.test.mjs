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
const view = await import(pathToFileURL(path.join(root, "src/views/StaffCalendar/staffCalendarView.js")).href);
const navigation = await import(pathToFileURL(path.join(root, "src/views/TaskManagement/taskManagementNavigation.js")).href);

test("future staffing semantics never report Present or Absent", () => {
    const base = { dateKey: "2026-09-20", todayKey: "2026-09-12", employee: { employment_status: "Active" } };
    assert.equal(view.attendanceDisplayState({ ...base, attendance: { status: "Present" }, shift: { status: "Scheduled" } }), "Scheduled");
    assert.equal(view.attendanceDisplayState({ ...base, attendance: { status: "Absent" }, activeTaskCount: 1 }), "Scheduled");
    assert.equal(view.attendanceDisplayState({ ...base, approvedLeave: { status: "Approved" } }), "On Leave");
    assert.equal(view.attendanceDisplayState({ ...base }), "Unavailable");
});

test("pending leave does not alter availability while approved leave does", () => {
    const leaves = [
        { id: 1, employee_id: 7, start_date: "2026-09-20", end_date: "2026-09-21", status: "Pending" },
        { id: 2, employee_id: 7, start_date: "2026-09-22", end_date: "2026-09-23", status: "Approved" },
    ];
    assert.equal(view.leaveForEmployeeDate(leaves, 7, "2026-09-20", ["Approved"]).length, 0);
    assert.equal(view.leaveForEmployeeDate(leaves, 7, "2026-09-22", ["Approved"]).length, 1);
});

test("recorded attendance states and possible-absence filtering are explicit", () => {
    const base = { dateKey: "2026-09-12", todayKey: "2026-09-12", employee: { employment_status: "Active" } };
    assert.equal(view.attendanceDisplayState({ ...base, attendance: { status: "On Time" } }), "Present");
    assert.equal(view.attendanceDisplayState({ ...base, attendance: { status: "Checked Out" } }), "Present");
    assert.equal(view.attendanceDisplayState({ ...base, attendance: { status: "Sick" } }), "Sick");
    assert.equal(view.employeeMatchesAvailabilityFilter({ filter: "possible-absence", state: "Possible Absence", tasks: [] }), true);
    assert.equal(view.employeeMatchesAvailabilityFilter({ filter: "possible-absence", state: "Working Day", tasks: [] }), false);
});

test("coverage warnings exclude covered and terminal work", () => {
    assert.equal(view.taskNeedsCoverage({ status: "Pending", needs_reassignment: true }), true);
    assert.equal(view.taskNeedsCoverage({ status: "Completed", needs_reassignment: true }), false);
    assert.equal(view.taskNeedsCoverage({ status: "Approved", needs_reassignment: true }), false);
    assert.equal(view.taskNeedsCoverage({ status: "Voided", needs_reassignment: true }), false);
    assert.equal(view.taskNeedsCoverage({ status: "Archived", needs_reassignment: true, is_archived: true }), false);
    assert.equal(view.taskNeedsCoverage({ status: "Pending", needs_reassignment: true, covering_employee_id: 9, assignment_source: "Leave Coverage", coverage_status: "Active" }), false);
    assert.equal(view.coverageState({ status: "Pending", covering_employee_id: 9, assignment_source: "Leave Coverage", coverage_status: "Active" }), "Temporarily Covered");
});

test("Task Management deep links select exact records and reject external return URLs", () => {
    const params = new URLSearchParams("tab=tasks&taskId=456&employeeId=12&date=2026-09-12&assignmentState=needs-reassignment&from=staff-calendar&returnTo=%2Fstaff-calendar%3Fview%3Dweek%26date%3D2026-09-12");
    const parsed = navigation.parseTaskManagementNavigation(params);
    assert.deepEqual(parsed, {
        tab: "tasks",
        taskId: "456",
        employeeId: "12",
        date: "2026-09-12",
        leaveRequestId: "",
        assignmentState: "Needs Reassignment",
        fromStaffCalendar: true,
        returnTo: "/staff-calendar?view=week&date=2026-09-12",
    });
    assert.equal(navigation.normalizeTaskManagementTab("leave-requests"), "leave");
    assert.equal(navigation.safeInternalReturnPath("https://evil.example/staff-calendar"), "");
    assert.equal(navigation.safeInternalReturnPath("//evil.example/staff-calendar"), "");
    assert.equal(navigation.safeInternalReturnPath("/staff-calendar-evil"), "");
});

test("calendar source uses one range request, semantic inner actions, focused editors, and connected navigation", () => {
    const page = readStaffCalendarSource();
    const taskPage = [
        read("src/views/TaskManagement/TaskManagement.jsx"),
        read("src/views/TaskManagement/components/AssignmentsPanel.jsx"),
    ].join("\n");
    const leavePanel = read("src/views/TaskManagement/LeaveRequestsPanel.jsx");
    const calls = page.match(/workforceService\.getCalendar\(/g) || [];
    assert.equal(calls.length, 1, "Staff Calendar should make one range API request per load, not one per date/employee/task");
    assert.match(page, /event\.stopPropagation\(\)/);
    assert.match(page, /staff-month-cell-hitbox/);
    assert.match(page, /aria-label={`Open day view/);
    assert.match(page, /calendar-details-modal/);
    assert.match(page, /calendar-modal-backdrop/);
    assert.match(page, /detailsModalRef/);
    assert.match(page, /event.key === \"Escape\"/);
    assert.match(page, /role="dialog"/);
    assert.doesNotMatch(page, /Leave decisions and task reassignment stay in/);
    assert.match(page, /taskId/);
    assert.match(page, /leaveRequestId/);
    assert.match(page, /assignmentState/);
    assert.match(page, /employeeId/);
    assert.match(page, /goToLeave\(leave\)/);
    assert.match(taskPage, /Back to Staff Calendar/);
    assert.match(taskPage, /task-row-deep-link/);
    assert.match(leavePanel, /initialLeaveRequestId/);
    assert.match(leavePanel, /leave-row-deep-link/);
});

test("calendar URL state preserves view, date, selected date, and filters", () => {
    const pathValue = view.buildCalendarReturnPath({
        view: "week",
        anchor: "2026-09-12",
        employeeId: 12,
        availability: "coverage",
        selectedDate: "2026-09-13",
    });
    assert.equal(pathValue, "/staff-calendar?view=week&date=2026-09-12&employeeId=12&availability=coverage&selectedDate=2026-09-13");
    assert.equal(view.safeStaffCalendarReturnPath(pathValue), pathValue);
    assert.equal(view.safeStaffCalendarReturnPath("/staff-calendar-evil"), "");
});

test("calendar toolbar uses balanced action and filter rows", () => {
    const page = readStaffCalendarSource();
    const css = read("src/views/StaffCalendar/StaffCalendar.css");

    assert.match(page, /className="staff-calendar-toolbar-primary"/);
    assert.match(page, /className="staff-calendar-toolbar-actions"/);
    assert.match(page, /className="staff-calendar-toolbar-filters"/);
    assert.doesNotMatch(page, /className="workforce-button secondary staff-calendar-refresh"/);
    assert.match(read("src/hooks/useFarmModuleUpdates.js"), /window\.addEventListener\("focus", queue\)/);
    assert.doesNotMatch(page, /staff-calendar-bulk-action/);
    assert.match(css, /\.staff-calendar-toolbar\s*\{[\s\S]*display:\s*flex;[\s\S]*flex-direction:\s*column;/);
    assert.match(css, /\.staff-calendar-toolbar-filters\s*\{[\s\S]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/);
    assert.match(css, /@media \(max-width:\s*720px\)[\s\S]*\.staff-calendar-toolbar-filters\s*\{\s*grid-template-columns:\s*1fr/);
});

test("calendar editor portal owns modal layering, focus, typography, and mobile containment", () => {
    const page = readStaffCalendarSource();
    const css = read("src/views/StaffCalendar/StaffCalendar.css");
    const globals = read("src/index.css");
    const workforce = read("src/styles/workforce-ui.css");
    const header = read("src/components/AppHeaderActions/AppHeaderActions.jsx");
    const headerCss = read("src/components/AppHeaderActions/AppHeaderActions.css");
    const sidebarCss = read("src/components/Sidebar/Sidebar.css");
    const toastCss = read("src/components/AppNotification/AppNotification.css");

    assert.match(page, /import \{ createPortal \} from "react-dom"/);
    assert.match(page, /createPortal\([\s\S]*<div className="calendar-modal-portal workforce-layout">/);
    assert.match(page, /document\.body[,)]/);
    assert.match(page, /joross:modal-open/);
    assert.match(page, /event\.key !== "Tab"/);
    assert.match(page, /modal\.querySelectorAll/);
    assert.match(page, /document\.body\.style\.position = "fixed"/);
    assert.match(page, /window\.scrollTo\(0, scrollY\)/);
    assert.match(page, /previousFocus\?\.isConnected/);
    assert.match(page, /taskNeedsCoverage\(task\) \? goToCoverage\(editor\.dateKey\) : goToTask\(task\)/);
    assert.match(header, /joross:modal-open/);

    assert.match(globals, /--layer-sticky-navigation:\s*100/);
    assert.match(globals, /--layer-dropdown:\s*300/);
    assert.match(globals, /--layer-modal-backdrop:\s*1000/);
    assert.match(globals, /--layer-modal:\s*1100/);
    assert.match(globals, /--layer-critical-toast:\s*90000/);
    assert.match(headerCss, /z-index:\s*var\(--layer-dropdown, 300\)/);
    assert.match(sidebarCss, /z-index:\s*var\(--layer-sticky-navigation, 100\)/);
    assert.match(toastCss, /z-index:\s*var\(--layer-critical-toast, 90000\)/);
    assert.match(css, /\.calendar-modal-portal\.workforce-layout[^{]*\{[\s\S]*z-index:\s*var\(--layer-modal-backdrop, 1000\)/);
    assert.match(css, /\.calendar-modal-backdrop[^{]*\{[\s\S]*inset:\s*0/);
    assert.match(css, /\.calendar-details-modal[^{]*\{[\s\S]*z-index:\s*var\(--layer-modal, 1100\)/);
    assert.match(css, /\.calendar-details-modal[^{]*\{[\s\S]*font:\s*inherit/);
    assert.match(css, /\.calendar-details-body[^{]*\{[\s\S]*overflow-y:\s*auto[\s\S]*overscroll-behavior:\s*contain/);
    assert.match(workforce, /--workforce-modal-title-size:\s*1\.35rem/);
    assert.match(workforce, /--workforce-control-font-size:\s*0\.875rem/);
    assert.match(css, /@media \(max-width:\s*720px\)[\s\S]*\.calendar-details-modal\s*\{[\s\S]*inset:\s*0[\s\S]*height:\s*100dvh[\s\S]*transform:\s*none/);
    assert.match(css, /\.staff-calendar-page[^{]*\{[^}]*overflow-x:\s*hidden/);
    assert.match(css, /min-width:\s*760px/);
});


test("Task Management accepts a safe Crops return path for harvest blockers", () => {
    const parsed = navigation.parseTaskManagementNavigation(
        new URLSearchParams("tab=tasks&taskId=1659&from=crops&returnTo=%2Fcrops%3FcropId%3D1%26addYield%3D1")
    );
    assert.equal(parsed.tab, "tasks");
    assert.equal(parsed.taskId, "1659");
    assert.equal(parsed.fromCrops, true);
    assert.equal(parsed.returnTo, "/crops?cropId=1&addYield=1");
});
