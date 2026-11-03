import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relative) => fs.readFile(path.join(root, relative), "utf8");

const taskManagement = (await Promise.all([
    "src/views/TaskManagement/TaskManagement.jsx",
    "src/views/TaskManagement/components/AssignmentsPanel.jsx",
].map(read))).join("\n");
const modal = await read("src/views/TaskManagement/WorkSubmissionReviewModal.jsx");
const modalCss = await read("src/views/TaskManagement/WorkSubmissionReviewModal.css");
const evidence = await read("src/components/EvidencePhoto/EvidencePhoto.jsx");
const service = await read("src/services/workforceService.js");

test("submitted-for-review table rows are compact and open one review modal", () => {
    assert.match(taskManagement, /task\.status === "Submitted for Review".*Review Submission/s);
    assert.match(taskManagement, /Attempt \$\{task\.latest_submission\.attempt_number\}/);
    assert.match(taskManagement, /Performed by \$\{task\.latest_submission\.employee_name\}/);
    assert.match(taskManagement, /Evidence attached/);
    assert.doesNotMatch(taskManagement, /task\.status === "Submitted for Review".*review\(task,"Approve"\)/s);
    assert.doesNotMatch(taskManagement, /EvidenceViewButton/);
});

test("review modal contains all required report sections and current attempt separation", () => {
    for (const heading of [
        "Work Submission Report",
        "Task Information",
        "Employee Work Submission",
        "Resource and Inventory Usage",
        "Evidence",
        "Previous Review History",
    ]) assert.match(modal, new RegExp(heading));
    assert.match(modal, /Current pending attempt/);
    assert.match(modal, /No tracked inventory resource required/);
    assert.match(modal, /Inventory remains reserved until approval/i);
});

test("return requires trimmed feedback without native browser prompts", () => {
    assert.match(modal, /const trimmed = feedback\.trim\(\)/);
    assert.match(modal, /Feedback is required before returning this work for correction/);
    assert.doesNotMatch(modal, /window\.prompt|window\.confirm/);
});

test("review actions are guarded against double clicks and stale decisions refresh the table", () => {
    assert.match(taskManagement, /reviewActionInFlightRef\.current/);
    assert.match(taskManagement, /if \(!reviewModalTaskId \|\| reviewActionInFlightRef\.current\) return false/);
    assert.match(taskManagement, /err\?\.status === 409/);
    assert.match(taskManagement, /already reviewed by another user/);
    assert.match(taskManagement, /await load\(\)/);
});

test("review decisions and completed-work void keep their existing API routes", () => {
    assert.match(service, /getTaskReviewReport:[\s\S]*\/review-report/);
    assert.match(taskManagement, /workforceService\.reviewTask\(reviewModalTaskId, decision, feedback, options\)/);
    assert.match(taskManagement, /performReviewAction\("Approve"/);
    assert.match(taskManagement, /performReviewAction\("Return"/);
    assert.match(service, /voidTask:[\s\S]*\/void/);
});

test("evidence is loaded through the secure evidence service and supports an enlarged preview", () => {
    assert.match(modal, /EvidenceInlinePreview/);
    assert.match(evidence, /workforceService\.downloadEvidencePhoto\(evidenceUrl\)/);
    assert.match(evidence, /Open larger evidence photo preview/);
    assert.match(evidence, /External evidence links are disabled/);
});

test("modal supports keyboard escape, focus trapping, backdrop close, and internal scrolling", () => {
    assert.match(modal, /event\.key === "Escape"/);
    assert.match(modal, /event\.key !== "Tab"/);
    assert.match(modal, /querySelectorAll\(focusableSelector\)/);
    assert.match(modal, /event\.target === event\.currentTarget/);
    assert.match(modalCss, /\.work-review-body[\s\S]*overflow-y:\s*auto/);
    assert.match(modalCss, /@media \(max-width: 768px\)/);
    assert.match(modalCss, /@media \(max-width: 480px\)/);
});


test("Review Submission action reserves enough width for its full label and icon", async () => {
    const taskCss = await read("src/views/TaskManagement/TaskManagement.css");
    assert.match(taskCss, /\.workforce-table \.task-actions > \.review-submission-button\s*\{[\s\S]*flex:\s*0 0 auto[\s\S]*min-width:\s*190px[\s\S]*white-space:\s*nowrap/);
    assert.match(taskCss, /@media \(max-width: 760px\)[\s\S]*\.review-submission-button[\s\S]*min-width:\s*190px/);
});
