import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
    DEFAULT_SCHEDULE_FILTER,
    DEFAULT_TASK_VIEW,
    TASK_VIEW_OPTIONS,
    apiViewForTaskView,
    canWorkTaskForView,
    filterAndSortMyTasks,
    isFutureTaskForView,
    scheduleForTaskViewChange,
} from "../src/views/MyTasks/taskView.js";
import {
    DEFAULT_MY_TASKS_TAB,
    normalizeMyTasksTab,
    searchWithMyTasksTab,
    tabFromSearch,
} from "../src/views/MyTasks/tabState.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const myTasksSource = fs.readFileSync(path.join(root, "src/views/MyTasks/MyTasks.jsx"), "utf8");
const myTasksCss = fs.readFileSync(path.join(root, "src/views/MyTasks/MyTasks.css"), "utf8");
const globalCss = fs.readFileSync(path.join(root, "src/index.css"), "utf8");
const workforceCss = fs.readFileSync(path.join(root, "src/styles/workforce-ui.css"), "utf8");
const workforceServiceSource = fs.readFileSync(path.join(root, "src/services/workforceService.js"), "utf8");
const sidebarSource = fs.readFileSync(path.join(root, "src/components/Sidebar/Sidebar.jsx"), "utf8");
const sidebarCss = fs.readFileSync(path.join(root, "src/components/Sidebar/Sidebar.css"), "utf8");

const todayKey = "2026-09-10";
const upcomingLimitKey = "2026-09-17";
const base = {
    activity_date: todayKey,
    start_time: "08:00",
    priority: "Medium",
    location: "Jorros Farm",
};
const task = (id, status, overrides = {}) => ({ id, name: `Task ${id}`, status, ...base, ...overrides });

function run(tasks, overrides = {}) {
    return filterAndSortMyTasks({
        tasks,
        taskView: DEFAULT_TASK_VIEW,
        searchTerm: "",
        priorityFilter: "all",
        scheduleFilter: DEFAULT_SCHEDULE_FILTER,
        selectedDateKey: null,
        todayKey,
        upcomingLimitKey,
        ...overrides,
    });
}

test("/my-tasks defaults to Assigned Tasks and normalizes direct tab URLs safely", () => {
    assert.equal(DEFAULT_MY_TASKS_TAB, "tasks");
    assert.equal(tabFromSearch(""), "tasks");
    assert.equal(tabFromSearch("?tab=tasks"), "tasks");
    assert.equal(tabFromSearch("?tab=schedule"), "schedule");
    assert.equal(tabFromSearch("?tab=leave"), "leave");
    assert.equal(tabFromSearch("?tab=unknown"), "tasks");
    assert.equal(normalizeMyTasksTab("LEAVE"), "leave");
    assert.equal(searchWithMyTasksTab("?foo=1", "schedule"), "?foo=1&tab=schedule");
    assert.match(myTasksSource, /Assigned Tasks/);
    assert.match(myTasksSource, /My Schedule/);
    assert.match(myTasksSource, /Leave Requests/);
    assert.ok(myTasksSource.indexOf('id: "tasks"') < myTasksSource.indexOf('id: "schedule"'));
    assert.ok(myTasksSource.indexOf('id: "schedule"') < myTasksSource.indexOf('id: "leave"'));
});

test("upcoming assignments stay visible but cannot be started or submitted early", () => {
    const future = task(90, "Pending", { activity_date: "2026-09-11" });
    const futureInProgress = task(91, "In Progress", { activity_date: "2026-09-11" });
    const today = task(92, "Pending", { activity_date: todayKey });

    assert.equal(isFutureTaskForView(future, todayKey), true);
    assert.equal(canWorkTaskForView(future, todayKey), false);
    assert.equal(canWorkTaskForView(futureInProgress, todayKey), false);
    assert.equal(canWorkTaskForView(today, todayKey), true);
    assert.deepEqual(run([future, today]).map((row) => row.id), [92, 90]);

    assert.match(myTasksSource, /Upcoming Task/);
    assert.match(myTasksSource, /canWorkTaskForView\(task, todayKey\)/);
    assert.match(myTasksSource, /futureTask[\s\S]*?Start and Submit Work will appear on that day/);
    assert.match(myTasksSource, /!futureTask && canWorkTask[\s\S]*?>Start<\/button>/);
    assert.match(myTasksSource, /!futureTask && canWorkTask[\s\S]*?>.*Submit Work.*<\/button>/);
    assert.match(myTasksSource, /futureTask \? "Upcoming"/);
});

test("Assigned Tasks opens a bounded active timeline while All Active Dates remains discoverable", () => {
    assert.equal(DEFAULT_TASK_VIEW, "active");
    assert.equal(DEFAULT_SCHEDULE_FILTER, "timeline");
    assert.deepEqual(TASK_VIEW_OPTIONS.map(([, label]) => label), [
        "Active Tasks", "Pending", "In Progress", "Returned", "For Review", "Completed History", "Task History", "All Tasks",
    ]);
    const source = [
        task(1, "Pending", { activity_date: "2026-09-11" }),
        task(2, "Pending", { activity_date: "2026-10-01" }),
        task(3, "Completed", { activity_date: todayKey }),
    ];
    assert.deepEqual(run(source).map((row) => row.id), [1]);
    assert.deepEqual(run(source, { scheduleFilter: "all" }).map((row) => row.id), [1, 2]);
    assert.match(myTasksSource, /<option value="timeline">Active Timeline \(Missed, Today & Next 7 Days\)<\/option>/);
    assert.match(myTasksSource, /<option value="all">All Active Dates<\/option>/);
});

test("default active work sorts returned, overdue, today, in-progress, review, then upcoming", () => {
    const rows = run([
        task(1, "Pending", { activity_date: "2026-09-12" }),
        task(2, "In Progress", { activity_date: "2026-09-14" }),
        task(3, "Pending", { activity_date: todayKey }),
        task(4, "Pending", { activity_date: "2026-09-09" }),
        task(5, "Returned", { activity_date: "2026-09-09" }),
        task(6, "Submitted for Review", { activity_date: "2026-09-09" }),
    ]);
    assert.deepEqual(rows.map((row) => row.id), [5, 4, 3, 2, 6, 1]);
});

test("completed and terminal history stay outside the default Active Tasks view", () => {
    const active = run([
        task(1, "Pending"),
        task(2, "Completed"),
        task(3, "Voided"),
        task(4, "Approved"),
        task(5, "Completed", { is_archived: true }),
    ]);
    assert.deepEqual(active.map((row) => row.id), [1]);

    const completed = run([
        task(2, "Completed"),
        task(5, "Completed", { is_archived: true }),
    ], { taskView: "completed", scheduleFilter: "all" });
    assert.deepEqual(completed.map((row) => row.id), [2]);

    const history = run([
        task(2, "Completed"),
        task(3, "Voided"),
        task(4, "Approved"),
        task(5, "Completed", { is_archived: true }),
        task(6, "Pending"),
    ], { taskView: "history", scheduleFilter: "all" });
    assert.deepEqual(new Set(history.map((row) => row.id)), new Set([2, 3, 4, 5]));
});

test("schedule, priority, search, and selected-day filters intersect correctly", () => {
    const rows = run([
        task(1, "Pending", { name: "Feed Goats", priority: "High", activity_date: todayKey }),
        task(2, "Pending", { name: "Feed Chickens", priority: "Low", activity_date: todayKey }),
        task(3, "Pending", { name: "Feed Goats Tomorrow", priority: "High", activity_date: "2026-09-11" }),
    ], {
        taskView: "pending",
        searchTerm: "goats",
        priorityFilter: "High",
        scheduleFilter: "today",
    });
    assert.deepEqual(rows.map((row) => row.id), [1]);

    const selectedDay = run([
        task(4, "Pending", { activity_date: "2026-09-12" }),
        task(5, "Pending", { activity_date: "2026-09-13" }),
    ], { scheduleFilter: "date", selectedDateKey: "2026-09-13" });
    assert.deepEqual(selectedDay.map((row) => row.id), [5]);
});

test("history views use All Dates and returning to active restores Active Timeline", () => {
    assert.equal(scheduleForTaskViewChange("active", "completed", "timeline"), "all");
    assert.equal(scheduleForTaskViewChange("active", "history", "timeline"), "all");
    assert.equal(scheduleForTaskViewChange("active", "all", "timeline"), "all");
    assert.equal(scheduleForTaskViewChange("history", "active", "all"), "timeline");
    assert.match(myTasksSource, /setScheduleFilter\(DEFAULT_SCHEDULE_FILTER\)/);
    assert.match(myTasksSource, /setSelectedTaskDate\(null\)/);
});

test("summary counts are compact clickable filters and Assigned Work reports the active total", () => {
    for (const kind of ["total", "today", "missed", "progress", "returned", "review", "upcoming"]) {
        assert.match(myTasksSource, new RegExp(`applySummaryFilter\\(\\"${kind}\\"\\)`));
    }
    assert.match(myTasksSource, /active assignment/);
    assert.match(myTasksCss, /my-tasks-compact-stats/);
    assert.match(globalCss, /--summary-card-compact-height:\s*78px/);
    assert.match(myTasksCss, /min-height:\s*var\(--summary-card-compact-height\)/);
});

test("schedule is isolated in its own tab with week navigation and task-date navigation", () => {
    assert.match(myTasksSource, /activeTab === "schedule"/);
    assert.match(myTasksSource, />Previous<\/button>/);
    assert.match(myTasksSource, />This Week<\/button>/);
    assert.match(myTasksSource, />Next<\/button>/);
    assert.match(myTasksSource, /Approved leave:/);
    assert.match(myTasksSource, /active assignment/);
    assert.match(myTasksSource, /Open Assigned Tasks for this day/);
    assert.match(myTasksSource, /openTasksForDate\(key\)/);
});

test("leave request form and full employee leave history live only in the Leave Requests tab", () => {
    assert.match(myTasksSource, /activeTab === "leave"/);
    assert.match(myTasksSource, /<h2>Request Leave<\/h2>/);
    assert.match(myTasksSource, /<h2>My Leave Requests<\/h2>/);
    assert.match(myTasksSource, /Submitted:/);
    assert.match(myTasksSource, /Reviewer:/);
    assert.match(myTasksSource, /Manager feedback:/);
    assert.match(myTasksSource, /Coverage impact:/);
    assert.match(myTasksSource, /Coverage information:/);
    assert.match(myTasksSource, /item\.status === "Pending".*Cancel Pending Request/s);
    assert.doesNotMatch(myTasksSource, /activeTab === "schedule"[\s\S]*?<form className="my-leave-request"/);
});

test("task filters survive tab switches and each tab loads only its own dataset", () => {
    const changeTabBody = myTasksSource.match(/const changeTab = useCallback\([\s\S]*?\}, \[\]\);/)?.[0] || "";
    assert.doesNotMatch(changeTabBody, /clearFilters|setTaskView|setPriorityFilter|setScheduleFilter/);
    assert.match(myTasksSource, /activeTab !== "tasks"\) return/);
    assert.match(myTasksSource, /loadTasks\(backendTaskView, \{ force: true, sharedDevice: sharedDeviceMode, scope: backendTaskScope \}\)/);
    assert.match(myTasksSource, /activeTab === "schedule" && scheduleLoadedRange !== scheduleRangeKey/);
    assert.match(myTasksSource, /activeTab === "leave" && !leaveLoaded/);
});

test("Start, correction submission, evidence/report access, and read-only history remain available", () => {
    assert.match(myTasksSource, />Start<\/button>/);
    assert.match(myTasksSource, /Correct & Submit/);
    assert.match(myTasksSource, /Submit Work/);
    assert.match(myTasksSource, /View Report/);
    assert.match(myTasksSource, /EvidenceViewButton/);
    assert.match(myTasksSource, /Leave Coverage — originally assigned to/);
    assert.match(myTasksSource, /Archived<\/span>/);
});

test("frontend uses explicit active/completed/history/all API views without breaking boolean compatibility", () => {
    assert.equal(apiViewForTaskView("active"), "active");
    assert.equal(apiViewForTaskView("pending"), "active");
    assert.equal(apiViewForTaskView("review"), "active");
    assert.equal(apiViewForTaskView("completed"), "completed");
    assert.equal(apiViewForTaskView("history"), "history");
    assert.equal(apiViewForTaskView("all"), "all");
    assert.match(workforceServiceSource, /typeof viewOrIncludeCompleted === "boolean"/);
    assert.match(workforceServiceSource, /\{ include_completed: viewOrIncludeCompleted \}/);
    assert.match(myTasksSource, /workforceService\.getMyTasksPage\(query, \{ signal: controller\.signal \}\)/);
    assert.match(workforceServiceSource, /getMyTasksPage:[\s\S]*?\/workforce\/my-tasks\/page/);
});


test("My Tasks initial load does not self-abort and uses timeline scope plus lightweight summary counts", () => {
    const resetIndex = myTasksSource.indexOf("This reset must run before the task-loading effect");
    const loaderIndex = myTasksSource.indexOf("const loadTasks = useCallback");
    assert.ok(resetIndex >= 0 && loaderIndex > resetIndex);
    assert.match(myTasksSource, /scope: backendTaskScope/);
    assert.match(workforceServiceSource, /getMyTaskSummary:[\s\S]*?\/workforce\/my-tasks\/summary/);
    assert.match(myTasksSource, /loadTasks\(backendTaskView, \{ force: false/);
    assert.match(myTasksSource, /taskSummary\?\.total/);
});

test("primary tabs reuse workforce styling and remain horizontally usable on mobile", () => {
    assert.match(myTasksSource, /workforce-tabs workforce-primary-tabs my-tasks-primary-tabs/);
    assert.match(workforceCss, /workforce-tabs\.workforce-primary-tabs/);
    assert.match(workforceCss, /@media \(max-width: 720px\)[\s\S]*?overflow-x:\s*auto/);
    assert.match(workforceCss, /min-height:\s*46px/);
    assert.match(myTasksCss, /@media screen and \(max-width: 720px\)/);
});

test("Assigned Work typography reuses the shared Inter type and system control scale", () => {
    assert.match(myTasksCss, /my-assigned-work-card \{[\s\S]*?font-family:\s*"Inter",\s*Arial,\s*sans-serif/);
    assert.match(myTasksCss, /my-assigned-work-card :is\(\.my-tasks-search input, \.my-tasks-filters select\)[\s\S]*?var\(--workforce-control-font-size/);
    assert.match(myTasksCss, /my-assigned-work-card \.task-card h3[\s\S]*?var\(--ui-body-size[\s\S]*?font-weight:\s*600/);
    assert.match(myTasksCss, /my-assigned-work-card \.task-meta[\s\S]*?var\(--ui-small-size/);
    assert.match(myTasksCss, /my-assigned-work-card \.coverage-task-banner strong[\s\S]*?font-weight:\s*600/);
});



test("task-only employee navigation and My Tasks fit narrow mobile screens", () => {
    assert.match(sidebarSource, /sidebar-task-only/);
    assert.match(sidebarCss, /@media screen and \(max-width: 720px\)[\s\S]*?sidebar\.sidebar-task-only[\s\S]*?bottom:\s*0/);
    assert.match(sidebarCss, /sidebar\.sidebar-task-only:hover[\s\S]*?width:\s*100%/);
    assert.match(myTasksCss, /my-tasks-primary-tabs[\s\S]*?overflow-x:\s*auto/);
    assert.match(myTasksCss, /my-tasks-compact-stats[\s\S]*?grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
    assert.match(myTasksCss, /my-tasks-page[\s\S]*?max-width:\s*100vw[\s\S]*?overflow-x:\s*hidden/);
});
