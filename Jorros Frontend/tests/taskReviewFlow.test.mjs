import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const myTasks = read("src/views/MyTasks/MyTasks.jsx");
const taskManagement = [
    read("src/views/TaskManagement/TaskManagement.jsx"),
    read("src/views/TaskManagement/components/AssignmentsPanel.jsx"),
    read("src/views/TaskManagement/components/TaskManagementModals.jsx"),
].join("\n");
const workforceService = read("src/services/workforceService.js");
const httpClient = read("src/services/httpClient.js");

test("employee submission message and local state use the returned API task status", () => {
    assert.match(myTasks, /const updatedTask = await workforceService\.submitTask\(/);
    assert.match(myTasks, /updatedTask\?\.status === "Submitted for Review"/);
    assert.match(myTasks, /Work submitted for manager review\./);
    assert.doesNotMatch(myTasks, /notification\.success\(task\.requires_review/);
    assert.match(myTasks, /setTasks\(\(current\) => current\.map/);
    assert.match(myTasks, /"Submit for Review"/);
});

test("awaiting-review tasks cannot expose another employee submit action", () => {
    assert.match(myTasks, /\["Pending","In Progress","Returned"\]\.includes\(task\.status\).*Submit Work/s);
    assert.match(myTasks, /task\.status === "Submitted for Review".*Awaiting Manager Review/s);
});

test("inventory stays reserved until manager approval and review messages reflect the approval-only deduction", () => {
    assert.match(myTasks, /reserved and will be deducted only if approved/);
    assert.match(myTasks, /reserved; stock will be deducted only if the work is approved/);
    assert.match(taskManagement, /approved actual inventory quantity was deducted now/);
    assert.match(taskManagement, /pending inventory reservation was released; inventory was not deducted/);
    assert.doesNotMatch(taskManagement, /Inventory was not deducted again/);
    assert.doesNotMatch(taskManagement, /Existing inventory usage remains posted/);
});

test("Task Management counts real submitted-for-review rows and exposes review only through the report modal", () => {
    assert.match(taskManagement, /review:\s*tasks\.filter\(\(x\) => x\.status === "Submitted for Review"\)\.length/);
    assert.match(taskManagement, /task\.status === "Submitted for Review".*Review Submission/s);
    assert.match(taskManagement, /onOpenReview\(task\)/);
    assert.match(taskManagement, /onOpenReview=\{openReviewSubmission\}/);
    assert.doesNotMatch(taskManagement, /task\.status === "Submitted for Review".*review\(task,"Approve"\)/s);
    assert.doesNotMatch(taskManagement, /For Review[\s\S]{0,160}hardcod/i);
});

test("Task Management review row keeps only the compact submission summary", () => {
    assert.match(taskManagement, /Attempt \$\{task\.latest_submission\.attempt_number\}/);
    assert.match(taskManagement, /Performed by \$\{task\.latest_submission\.employee_name\}/);
    assert.match(taskManagement, /formatSubmissionDate\(task\.latest_submission\.submitted_at\)/);
    assert.match(taskManagement, /Evidence attached/);
    assert.doesNotMatch(taskManagement, /EvidenceViewButton/);
});

test("manager-assisted workflow keeps Approve Now explicit", () => {
    assert.match(taskManagement, /submitAssistedWork\(false\)/);
    assert.match(taskManagement, /Submit for Review/);
    assert.match(taskManagement, /submitAssistedWork\(true\)/);
    assert.match(taskManagement, /Submit & Approve/);
    assert.doesNotMatch(taskManagement, /Record & Complete/);
});

test("manager-assisted harvest hides instant approval and captures the review decision inputs", () => {
    assert.match(taskManagement, /assistedIsCropHarvest/);
    assert.match(taskManagement, /Actual Harvest Yield \(kg\) \*/);
    assert.match(taskManagement, /Reported Harvest Type \*/);
    assert.match(taskManagement, /Submit Harvest for Review/);
    assert.match(taskManagement, /!assistedIsCropHarvest && \([\s\S]*?Submit & Approve/);
});

test("task reloads bypass browser cache", () => {
    assert.match(workforceService, /getTasks:.*cache:\s*"no-store"/);
    assert.match(workforceService, /getMyTasks:[\s\S]*cache:\s*"no-store"/);
    assert.match(httpClient, /cache = "default"/);
    assert.match(httpClient, /const fetchOptions = \{[\s\S]*cache,/);
    assert.match(httpClient, /fetch\(requestUrl, fetchOptions\)/);
});
