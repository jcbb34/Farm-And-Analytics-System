import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const read = (...parts) => readFileSync(join(root, ...parts), "utf8");

const calendar = read("src", "views", "StaffCalendar", "StaffCalendar.jsx");
const leavePanel = read("src", "views", "TaskManagement", "LeaveRequestsPanel.jsx");
const myTasks = read("src", "views", "MyTasks", "MyTasks.jsx");
const taskManagement = [
    read("src", "views", "TaskManagement", "TaskManagement.jsx"),
    read("src", "views", "TaskManagement", "components", "AssignmentsPanel.jsx"),
    read("src", "views", "TaskManagement", "components", "AssignmentFilters.jsx"),
    read("src", "views", "TaskManagement", "components", "TaskManagementTabs.jsx"),
].join("\n");
const leavePanelCss = read("src", "views", "TaskManagement", "LeaveRequestsPanel.css");
const reviewModal = read("src", "views", "TaskManagement", "WorkSubmissionReviewModal.jsx");
const service = read("src", "services", "workforceService.js");
const staffCalendarPage = read("src", "app", "(protected)", "staff-calendar", "page.jsx");
const protectedRoute = read("src", "components", "Auth", "ProtectedRoute.jsx");

test("Task Management owns the Leave Requests review workflow", () => {
    assert.match(taskManagement, /import LeaveRequestsPanel/);
    assert.match(taskManagement, /\{ id: "leave", label: "Leave Requests", icon: "event_busy" \}/);
    assert.match(taskManagement, /<LeaveRequestsPanel employees=\{employees\} onChanged=\{load\}/);
    assert.ok(!calendar.includes("import LeaveRequestsPanel"));
    assert.ok(!calendar.includes("Leave decisions and task reassignment stay in"));
    assert.match(calendar, /goToLeave|goToTask|goToCoverage/);
    assert.ok(!calendar.includes("Record Leave"));
});

test("leave approval UI renders status queues, review details, affected tasks, and coverage selectors", () => {
    for (const text of ["Pending", "Approved", "Rejected", "Cancelled", "Review Leave Request", "Affected Tasks & Temporary Coverage", "Cover all eligible tasks", "Covering Employee Availability", "Approve Leave", "Cancel Approved Leave"]) {
        assert.ok(leavePanel.includes(text), `Missing leave UI text: ${text}`);
    }
    assert.match(leavePanel, /taskCoverIds/);
    assert.match(leavePanel, /candidate\.blockers/);
    assert.match(leavePanel, /candidate\.warnings/);
});


test("Leave Requests uses the shared Task Management typography and workforce design tokens", () => {
    assert.match(leavePanel, /Task Management<\/span><h2 id="leave-review-title">Review Leave Request/);
    assert.match(leavePanelCss, /font-family:\s*"Inter",\s*Arial,\s*sans-serif/);
    assert.match(leavePanelCss, /var\(--workforce-green-text/);
    assert.match(leavePanelCss, /var\(--workforce-control-height/);
    assert.match(leavePanelCss, /var\(--workforce-border/);
    assert.match(leavePanelCss, /data-theme="dark"/);
});

test("workforce service exposes employee leave and manager coverage endpoints", () => {
    assert.match(service, /getMyLeave/);
    assert.match(service, /leave\/my/);
    assert.match(service, /getLeaveReview/);
    assert.match(service, /recalculateLeaveCoverage/);
    assert.match(leavePanel, /task_coverages/);
});

test("employee view shows leave history and a clear coverage-task badge", () => {
    assert.ok(myTasks.includes("My Leave Requests"));
    assert.ok(myTasks.includes("Cancel Pending Request"));
    assert.ok(myTasks.includes("Coverage Task — originally assigned to"));
    assert.match(myTasks, /coverage_start_date/);
    assert.match(myTasks, /coverage_reason/);
});

test("Task Management can filter and monitor Leave Coverage assignments", () => {
    assert.ok(taskManagement.includes('<option value="Leave Coverage">Leave Coverage</option>'));
    assert.match(taskManagement, /task\.assignment_source !== "Leave Coverage"/);
    assert.ok(taskManagement.includes("Original:"));
    assert.ok(taskManagement.includes("Covering:"));
    assert.ok(taskManagement.includes("Coverage ends:"));
    assert.ok(taskManagement.includes("coverage_indicator"));
});

test("submission review preserves original, temporary, and actual performer identities", () => {
    assert.ok(reviewModal.includes('label="Originally assigned to"'));
    assert.ok(reviewModal.includes('label="Temporarily assigned to"'));
    assert.ok(reviewModal.includes('label="Actually performed by"'));
    assert.ok(reviewModal.includes('label="Related approved leave"'));
    assert.ok(reviewModal.includes('label="Coverage reason"'));
});

test("authorized manager or attendance roles can reach Staff Calendar while leave approvals stay in Task Management", () => {
    assert.match(staffCalendarPage, /permission=\{\["workforce:attendance",\s*"workforce:manage"\]\}/);
    assert.match(protectedRoute, /Array\.isArray\(permission\)/);
    assert.match(protectedRoute, /permission\.some/);
});
