import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
    activityRequiresTaskWorkflow,
    buildMyTasksPath,
    buildTaskManagementPath,
    resolveDashboardActivityActions,
} from "../src/components/DashboardActivity/dashboardActivityWorkflow.js";
import { parseTaskManagementNavigation } from "../src/views/TaskManagement/taskManagementNavigation.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const dashboardSource = read("src/components/DashboardActivity/DashboardActivity.jsx");
const activityServiceSource = read("src/services/activityService.js");
const httpClientSource = read("src/services/httpClient.js");
const taskManagementSource = [
    read("src/views/TaskManagement/TaskManagement.jsx"),
    read("src/views/TaskManagement/components/AssignmentsPanel.jsx"),
].join("\n");
const myTasksSource = read("src/views/MyTasks/MyTasks.jsx");
const appHeaderSource = read("src/context/AppHeaderContext.jsx");

const workforceActivity = {
    id: 529,
    name: "Feed Pen A",
    workflowType: "workforce_task",
    linkedTaskId: 529,
    canCompleteDirectly: false,
    availableActions: ["open_task", "assisted_submission"],
};

test("workforce Dashboard activities do not expose direct Complete and Open Task targets the exact record", () => {
    const actions = resolveDashboardActivityActions(workforceActivity);
    assert.deepEqual(actions.map((action) => action.code), ["open_task", "assisted_submission"]);
    assert.equal(actions.some((action) => action.kind === "complete"), false);
    assert.match(actions[0].path, /^\/task-management\?/);
    const url = new URL(`http://local${actions[0].path}`);
    assert.equal(url.searchParams.get("tab"), "tasks");
    assert.equal(url.searchParams.get("taskId"), "529");
    assert.equal(url.searchParams.get("from"), "dashboard");
    assert.equal(url.searchParams.get("returnTo"), "/dashboard");
});

test("manager review, returned, reassignment, and report actions use Task Management deep links", () => {
    const cases = [
        ["review_submission", "Review Submission"],
        ["view_returned_task", "View Returned Task"],
        ["resolve_assignment", "Resolve Assignment"],
        ["view_report", "View Report"],
    ];
    for (const [code, label] of cases) {
        const [action] = resolveDashboardActivityActions({ ...workforceActivity, availableActions: [code] });
        assert.equal(action.label, label);
        const url = new URL(`http://local${action.path}`);
        assert.equal(url.pathname, "/task-management");
        assert.equal(url.searchParams.get("taskId"), "529");
        if (code === "resolve_assignment") assert.equal(url.searchParams.get("assignmentState"), "needs-reassignment");
    }
});

test("employee Dashboard actions open the exact assignment in My Tasks with the needed view", () => {
    const cases = [
        ["open_my_tasks", "active"],
        ["correct_submission", "returned"],
        ["view_submission", "review"],
        ["view_history", "history"],
    ];
    for (const [code, view] of cases) {
        const [action] = resolveDashboardActivityActions({ ...workforceActivity, availableActions: [code] });
        const url = new URL(`http://local${action.path}`);
        assert.equal(url.pathname, "/my-tasks");
        assert.equal(url.searchParams.get("tab"), "tasks");
        assert.equal(url.searchParams.get("taskId"), "529");
        assert.equal(url.searchParams.get("view"), view);
        assert.equal(url.searchParams.get("schedule"), "all");
        assert.equal(url.searchParams.get("returnTo"), "/dashboard");
    }
});

test("Assisted Submission is reached through Task Management rather than a direct Dashboard completion", () => {
    const path = buildTaskManagementPath(workforceActivity, "assisted_submission");
    const url = new URL(`http://local${path}`);
    assert.equal(url.pathname, "/task-management");
    assert.equal(url.searchParams.get("taskId"), "529");
    assert.equal(url.searchParams.get("action"), "assisted-submission");
    assert.match(taskManagementSource, /navigation\.action !== "assisted-submission"/);
    assert.match(taskManagementSource, /openAssistedSubmission\(task\)/);
});

test("standalone activities retain direct completion only when the backend permits it", () => {
    const allowed = resolveDashboardActivityActions({
        id: 10,
        name: "Office checklist",
        workflowType: "standalone_activity",
        canCompleteDirectly: true,
        availableActions: ["complete_directly"],
    });
    assert.equal(allowed[0].kind, "complete");

    const notAllowed = resolveDashboardActivityActions({
        id: 11,
        workflowType: "standalone_activity",
        canCompleteDirectly: true,
        availableActions: [],
    });
    assert.deepEqual(notAllowed, []);
});

test("Dashboard respects backend-provided available_actions instead of title/category guesses", () => {
    const actions = resolveDashboardActivityActions({
        id: 12,
        name: "Feed anything",
        category: "Livestock Feeding",
        linkedTaskId: 12,
        canCompleteDirectly: true,
        availableActions: ["open_task"],
    });
    assert.deepEqual(actions.map((item) => item.code), ["open_task"]);
    assert.doesNotMatch(dashboardSource, /Mark activity completed/);
    assert.match(dashboardSource, /resolveDashboardActivityActions\(activity\)/);
});


test("stale Dashboard metadata cannot re-enable direct Complete for an employee task", () => {
    const staleTaskPayload = {
        id: 529,
        name: "Feed Pen A",
        workflowType: "standalone_activity",
        assignedEmployeeId: 22,
        requiresReview: true,
        canCompleteDirectly: true,
        availableActions: ["complete_directly"],
    };
    assert.equal(activityRequiresTaskWorkflow(staleTaskPayload), true);
    assert.deepEqual(resolveDashboardActivityActions(staleTaskPayload), []);
    assert.match(dashboardSource, /activityRequiresTaskWorkflow\(sourceActivity\)/);
    assert.match(dashboardSource, /must be completed through My Tasks and Task Management review/);
});

test("double-clicks are guarded in both component and service with one in-flight mutation per activity", () => {
    assert.match(dashboardSource, /activityMutationRef\.current\.has\(activityId\)/);
    assert.match(dashboardSource, /disabled=\{busy\}/);
    assert.match(activityServiceSource, /const inFlightActivityMutations = new Map\(\)/);
    assert.match(activityServiceSource, /const existing = inFlightActivityMutations\.get\(mutationKey\)/);
    assert.match(activityServiceSource, /if \(existing\) return existing/);
});

test("successful mutation reconciles from the server response before any success state and cannot replay stale Complete UI", () => {
    const awaitIndex = dashboardSource.indexOf("await activityService.updateActivity");
    const stateIndex = dashboardSource.indexOf("setActivities((currentActivities)", awaitIndex);
    assert.ok(awaitIndex >= 0 && stateIndex > awaitIndex, "server response must arrive before UI status changes");
    assert.match(dashboardSource, /updatedActivity\.isArchived/);
    assert.match(dashboardSource, /notification\.success/);
    assert.match(activityServiceSource, /finally \{[\s\S]*inFlightActivityMutations\.delete\(mutationKey\)/);
});

test("validation failures are not retried or shown optimistically and safe backend messages appear once", () => {
    const updateStart = activityServiceSource.indexOf("async updateActivity(activityId, data)");
    const updateEnd = activityServiceSource.indexOf("async archiveActivity", updateStart);
    const updateBody = activityServiceSource.slice(updateStart, updateEnd);
    assert.equal((updateBody.match(/httpClient\.put/g) || []).length, 1);
    assert.doesNotMatch(updateBody, /retry|setTimeout|while\s*\(/i);
    assert.match(dashboardSource, /notification\.error\(message, "Task Workflow Required"\)/);
    assert.match(dashboardSource, /actionLabel: "Open Task"/);
    assert.ok(httpClientSource.includes("if (!response.ok)"), "HTTP 400 responses should reject normally");
});

test("Task Management and My Tasks preserve an authorized Back to Dashboard deep link and highlight the exact task", () => {
    const parsed = parseTaskManagementNavigation(new URLSearchParams("tab=tasks&taskId=529&from=dashboard&returnTo=%2Fdashboard"));
    assert.equal(parsed.taskId, "529");
    assert.equal(parsed.fromDashboard, true);
    assert.equal(parsed.returnTo, "/dashboard");
    assert.match(taskManagementSource, /Back to Dashboard/);
    assert.match(taskManagementSource, /task-row-deep-link/);
    assert.match(myTasksSource, /my-task-\$\{focusedTaskId\}/);
    assert.match(myTasksSource, /task-card-deep-link/);
    assert.match(myTasksSource, /Back to Dashboard/);
    assert.match(buildMyTasksPath(workforceActivity, "open_my_tasks"), /taskId=529/);
});

test("alert polling remains owned by one application-session provider interval", () => {
    assert.equal((appHeaderSource.match(/window\.setInterval\(/g) || []).length, 1);
    assert.equal((appHeaderSource.match(/window\.clearInterval\(/g) || []).length, 1);
    assert.match(appHeaderSource, /return \(\) => \{[\s\S]*window\.clearInterval\(refreshTimer\)/);
});


test("transient network retry is GET-only and never retries validation responses or writes", () => {
    assert.match(httpClientSource, /mayRetryTransientGet = String\(method\)\.toUpperCase\(\) === "GET"/);
    assert.match(httpClientSource, /if \(!mayRetryTransientGet\) throw fetchError/);
    assert.match(httpClientSource, /if \(!response\.ok\)/);
    assert.doesNotMatch(httpClientSource, /response\.status === 400[\s\S]*retry/i);
});
