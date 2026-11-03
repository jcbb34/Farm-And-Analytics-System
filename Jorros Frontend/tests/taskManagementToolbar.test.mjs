import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { buildTaskManagementQuery } from "../src/views/TaskManagement/taskManagementQuery.js";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relativePath) => fs.readFile(path.join(projectRoot, relativePath), "utf8");

const taskManagement = (await Promise.all([
    "src/views/TaskManagement/TaskManagement.jsx",
    "src/views/TaskManagement/components/AssignmentsPanel.jsx",
    "src/views/TaskManagement/components/AssignmentFilters.jsx",
    "src/views/TaskManagement/components/TaskManagementTabs.jsx",
    "src/views/TaskManagement/components/TaskSummaryCards.jsx",
    "src/views/TaskManagement/hooks/useTaskManagementData.js",
].map(read))).join("\n");
const taskCss = await read("src/views/TaskManagement/TaskManagement.css");
const globalCss = await read("src/index.css");

const widths = [1920, 1440, 1366, 768, 390, 360];
const filterColumnsAt = (width) => {
    if (width <= 620) return 1;
    if (width <= 900) return 2;
    if (width <= 1280) return 3;
    return 5;
};

test("page header no longer exposes Task Management refresh as a global action", () => {
    const header = taskManagement.match(/<header className="workforce-header">[\s\S]*?<\/header>/)?.[0] || "";
    assert.ok(header, "workforce header should exist");
    assert.doesNotMatch(header, />\s*Refresh\s*</);
    assert.doesNotMatch(header, /onClick=\{(?:refreshAll|handleManualRefresh)\}/);
    assert.match(header, /<AppHeaderActions\s*\/>/);
});

test("Assignments retains Assign Task and uses automatic updates without a Refresh button", () => {
    assert.match(taskManagement, /className="assignment-card-actions"/);
    assert.match(taskManagement, /onClick=\{onAssignTask\}/);
    assert.doesNotMatch(taskManagement, /className="workforce-button secondary assignment-refresh-button"/);
    assert.match(taskManagement, /useFarmModuleUpdates/);
});

test("filter toolbar is intentionally split into search/actions and five labeled selects", () => {
    assert.match(taskManagement, /className="assignment-filter-primary-row"/);
    assert.match(taskManagement, /className="assignment-filter-select-row"/);
    assert.equal((taskManagement.match(/className="assignment-filter-field"/g) || []).length, 5);
    for (const label of ["Schedule", "Status", "Priority", "Employee", "Assignment State"]) {
        assert.match(taskManagement, new RegExp(`<span>${label}<\\/span>`));
    }
    assert.match(taskManagement, />\s*Clear Filters\s*</);
    assert.match(taskManagement, /disabled=\{filtersAreDefault\}/);
    assert.match(taskManagement, /aria-label="Search assignments"/);
});

test("completed status and selected employee are sent to the workforce API", () => {
    assert.deepEqual(
        buildTaskManagementQuery({
            taskDateFilter: "",
            taskScheduleFilter: "All Scheduled",
            taskStatusFilter: "Completed",
            taskEmployeeFilter: "42",
            todayKey: "2026-09-25",
        }),
        { status: "Completed", employee_id: 42 },
    );
    assert.match(taskManagement, /taskStatusFilter,[\s\S]*taskEmployeeFilter,[\s\S]*todayKey/);
    assert.match(taskManagement, /requestId !== loadRequestIdRef\.current/);
});

test("derived and non-employee filters do not send invalid API parameters", () => {
    assert.deepEqual(
        buildTaskManagementQuery({
            taskDateFilter: "",
            taskScheduleFilter: "Missed / Overdue",
            taskStatusFilter: "Missed",
            taskEmployeeFilter: "Unassigned",
            todayKey: "2026-09-25",
        }),
        { date_to: "2026-09-24", open_only: true, assignment_state: "Unassigned" },
    );
});

test("Clear Filters restores the existing intended defaults and is disabled at defaults", () => {
    assert.match(taskManagement, /setTaskSearch\(""\)/);
    assert.match(taskManagement, /setTaskStatusFilter\("All"\)/);
    assert.match(taskManagement, /setTaskScheduleFilter\("Actionable Now"\)/);
    assert.match(taskManagement, /setTaskPriorityFilter\("All"\)/);
    assert.match(taskManagement, /setTaskEmployeeFilter\("All"\)/);
    assert.match(taskManagement, /setTaskReassignmentFilter\("All"\)/);
    assert.match(taskManagement, /taskSearch === ""[\s\S]*taskScheduleFilter === "Actionable Now"[\s\S]*taskReassignmentFilter === "All"/);
});

test("responsive filter matrix keeps five balanced desktop columns and stacks safely on phones", () => {
    assert.deepEqual(
        widths.map((width) => [width, filterColumnsAt(width)]),
        [
            [1920, 5],
            [1440, 5],
            [1366, 5],
            [768, 2],
            [390, 1],
            [360, 1],
        ],
    );
    assert.match(taskCss, /\.assignment-filter-select-row\s*\{[\s\S]*grid-template-columns:\s*repeat\(5, minmax\(0, 1fr\)\)/);
    assert.match(taskCss, /@media \(max-width:\s*1280px\)[\s\S]*repeat\(3, minmax\(0, 1fr\)\)/);
    assert.match(taskCss, /@media \(max-width:\s*900px\)[\s\S]*repeat\(2, minmax\(0, 1fr\)\)/);
    assert.match(taskCss, /@media \(max-width:\s*620px\)[\s\S]*grid-template-columns:\s*1fr/);
    assert.match(taskCss, /@media \(max-width:\s*620px\)[\s\S]*\.assignment-card-actions \.workforce-button,[\s\S]*\.assignment-clear,[\s\S]*\.assignment-search,[\s\S]*\.assignment-filter-field[\s\S]*width:\s*100%/);
});

test("toolbar controls use the shared 44px workforce control language and focus states", () => {
    assert.match(taskCss, /\.assignment-search\s*\{[\s\S]*min-height:\s*44px/);
    assert.match(taskCss, /\.assignment-filter-field select\s*\{[\s\S]*min-height:\s*44px/);
    assert.match(taskCss, /\.assignment-clear\s*\{[\s\S]*min-height:\s*44px/);
    assert.match(taskCss, /\.assignment-search:focus-within[\s\S]*--workforce-focus-ring/);
    assert.match(taskCss, /\.assignment-filter-field select:focus[\s\S]*--workforce-focus-ring/);
    assert.match(taskCss, /\.assignment-clear:disabled[\s\S]*--workforce-disabled-bg/);
    assert.match(taskCss, /\.assignment-refresh-icon-spinning[\s\S]*animation:/);
});

test("Task Management primary tabs mirror the Farm Intelligence icon-and-pill navigation", () => {
    assert.match(taskManagement, /className="workforce-tabs workforce-primary-tabs"/);
    for (const icon of ["task_alt", "groups", "event_busy", "clinical_notes", "archive"]) {
        assert.match(taskManagement, new RegExp(`icon: "${icon}"`));
    }
    assert.match(taskManagement, /className=\{`workforce-tab workforce-primary-tab/);
    assert.match(taskManagement, /aria-current=\{activeTab === id \? "page" : undefined\}/);
    assert.match(taskCss, /\.workforce-tabs\.workforce-primary-tabs\s*\{[\s\S]*border-radius:\s*13px[\s\S]*box-shadow:\s*0 4px 14px/);
    assert.match(taskCss, /\.workforce-primary-tabs \.workforce-primary-tab\.active\s*\{[\s\S]*background:\s*#e8f5e9[\s\S]*box-shadow:\s*inset 0 -2px 0 #22a447/);
    assert.match(taskCss, /@media \(max-width:\s*720px\)[\s\S]*\.workforce-tabs\.workforce-primary-tabs[\s\S]*overflow-x:\s*auto/);
});

test("Task Management summary cards use the same compact scale as My Tasks", () => {
    assert.match(taskManagement, /className="workforce-stats task-management-compact-stats"/);
    for (const token of [
        "--summary-card-compact-height: 78px",
        "--summary-card-compact-gap: 10px",
        "--summary-card-compact-padding-y: 11px",
        "--summary-card-compact-padding-x: 13px",
        "--summary-card-compact-icon: 36px",
        "--summary-card-compact-value: 1.28rem",
    ]) assert.ok(globalCss.includes(token), `missing shared summary-card token: ${token}`);
    assert.match(taskCss, /\.task-management-compact-stats\s*\{[\s\S]*gap:\s*var\(--summary-card-compact-gap\)[\s\S]*margin-bottom:\s*12px/);
    assert.match(taskCss, /\.task-management-compact-stats \.workforce-stat\s*\{[\s\S]*min-height:\s*var\(--summary-card-compact-height\)[\s\S]*padding:\s*var\(--summary-card-compact-padding-y\) var\(--summary-card-compact-padding-x\)[\s\S]*border-top-width:\s*var\(--summary-card-compact-accent\)/);
    assert.match(taskCss, /\.task-management-compact-stats \.workforce-stat-icon\s*\{[\s\S]*width:\s*var\(--summary-card-compact-icon\)[\s\S]*height:\s*var\(--summary-card-compact-icon\)/);
    assert.match(taskCss, /\.task-management-compact-stats \.workforce-stat-copy strong\s*\{[\s\S]*font-size:\s*var\(--summary-card-compact-value\)/);
});
