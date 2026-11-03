import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const myTasksSource = read("src/views/MyTasks/MyTasks.jsx");
const liveUpdatesSource = read("src/hooks/useFarmModuleUpdates.js");
const taskManagementSource = [
    read("src/views/TaskManagement/TaskManagement.jsx"),
    read("src/views/TaskManagement/components/AssignmentsPanel.jsx"),
    read("src/views/TaskManagement/components/EmployeePanels.jsx"),
    read("src/views/TaskManagement/components/TaskManagementModals.jsx"),
].join("\n");
const workforceServiceSource = read("src/services/workforceService.js");
const authContextSource = read("src/context/AuthContext.jsx");

test("My Tasks cache and in-flight requests are scoped to the authenticated identity", () => {
    assert.match(myTasksSource, /const identityKey = useMemo/);
    assert.match(myTasksSource, /user\?\.id[\s\S]*?user\?\.userCode[\s\S]*?user\?\.username/);
    assert.match(myTasksSource, /const cacheKey = `\$\{identityKey\}:\$\{JSON\.stringify\(query\)\}`/);
    assert.match(myTasksSource, /workforceService\.getMyTasksPage\(query, \{ signal: controller\.signal \}\)/);
    assert.match(myTasksSource, /taskRequestRef\.current\?\.abort\(\)/);
    assert.match(myTasksSource, /new AbortController\(\)/);
    assert.match(workforceServiceSource, /getMyTasks:[\s\S]*?signal[\s\S]*?cache: "no-store"/);
    assert.match(myTasksSource, /taskCacheRef\.current\.clear\(\)[\s\S]*?setTasks\(\[\]\)/);
});

test("login/logout and account switching clear identity state instead of reusing another employee response", () => {
    assert.match(authContextSource, /new CustomEvent\("joross:auth-changed"/);
    assert.match(authContextSource, /function clearSession\(\)[\s\S]*?joross:auth-changed/);
    assert.match(myTasksSource, /\}, \[identityKey\]\);/);
    assert.match(liveUpdatesSource, /window\.addEventListener\("joross:auth-changed", queue\)/);
    assert.match(liveUpdatesSource, /window\.addEventListener\("focus", queue\)/);
    assert.match(liveUpdatesSource, /document\.addEventListener\("visibilitychange", queue\)/);
    assert.match(liveUpdatesSource, /window\.addEventListener\("joross:activities-updated", queue\)/);
});

test("assignment events refetch employee tasks and manager success waits for persisted API response", () => {
    assert.match(workforceServiceSource, /updateAssignment: async[\s\S]*?await httpClient\.put[\s\S]*?notifyWorkforceResourceChanged\(\)[\s\S]*?return response/);
    assert.match(workforceServiceSource, /notifyWorkforceResourceChanged[\s\S]*?joross:activities-updated/);
    assert.match(taskManagementSource, /await workforceService\.updateAssignment/);
    assert.match(liveUpdatesSource, /joross:activities-updated/);
});

test("manager assignment UI blocks unlinked accounts and explicitly confirms unavailable overrides", () => {
    assert.match(taskManagementSource, /portal_assignment_ready/);
    assert.match(taskManagementSource, /account_status \|\| "No Login Account"/);
    assert.match(taskManagementSource, /Repair Account Links/);
    assert.match(taskManagementSource, /workforceService\.repairEmployeeAccountLinks\(\)/);
    assert.match(taskManagementSource, /workforceService\.getAvailability\(taskForm\.activity_date/);
    assert.match(taskManagementSource, /confirmAction\(/);
    assert.match(taskManagementSource, /allow_unavailable_override: allowUnavailableOverride/);
    assert.match(taskManagementSource, /disabled=\{!candidate\.employee\.portal_assignment_ready\}/);
});

test("employee account health and linked username are visible in Task Management", () => {
    assert.match(taskManagementSource, /Account Linked|account_status/);
    assert.match(taskManagementSource, /login_username/);
    assert.match(taskManagementSource, /account_issue/);
});

test("My Tasks exposes full active timeline, coverage warnings, counts, and distinct empty/error states", () => {
    for (const label of ["Total Assigned", "Today", "Missed", "In Progress", "Returned", "For Review", "Upcoming (7 Days)"]) {
        assert.match(myTasksSource, new RegExp(label.replace(/[()]/g, "\\$&")));
    }
    assert.match(myTasksSource, /Active Timeline \(Missed, Today & Next 7 Days\)/);
    assert.match(myTasksSource, /All Active Dates/);
    assert.match(myTasksSource, /assignment_source === "Leave Coverage"/);
    assert.match(myTasksSource, /assignment_source === "Rest-Day Coverage"/);
    assert.match(myTasksSource, /task\.needs_reassignment/);
    assert.match(myTasksSource, /No active assignments/);
    assert.match(myTasksSource, /Assignments exist, but the current filters hide them/);
    assert.match(myTasksSource, /Account is not linked to an employee/);
    assert.match(myTasksSource, /Assignments could not be loaded/);
});
