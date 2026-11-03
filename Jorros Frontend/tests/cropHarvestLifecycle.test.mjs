import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
    matchesCropLifecycleFilter,
    sortCropsByHarvestPriority,
} from "../src/views/Crops/cropLifecycle.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const cropsSource = read("src/views/Crops/Crops.jsx");
const cropsPageSource = read("src/views/Crops/hooks/useCropsPage.js");
const tableSource = read("src/views/Crops/components/CropsRecordsTable.jsx");
const modalSource = read("src/components/CropActionModals/CropActionModals.jsx");
const myTasksSource = read("src/views/MyTasks/MyTasks.jsx");
const taskManagementSource = [
    read("src/views/TaskManagement/TaskManagement.jsx"),
    read("src/views/TaskManagement/components/TaskManagementModals.jsx"),
].join("\n");
const reviewSource = read("src/views/TaskManagement/WorkSubmissionReviewModal.jsx");
const cropServiceSource = read("src/services/cropService.js");
const reopenModalSource = read("src/views/Crops/components/ReopenCropModal.jsx");

const rows = [
    { id: 1, name: "Tomato", status: "Growing", estimatedHarvest: "2026-09-20", isArchived: false },
    { id: 2, name: "Okra", status: "Ready for Harvest", estimatedHarvest: "2026-09-15", isArchived: false },
    { id: 3, name: "Eggplant", status: "Ready for Harvest", estimatedHarvest: "2026-09-10", isArchived: false },
    { id: 4, name: "Pepper", status: "Harvesting", estimatedHarvest: "2026-09-12", isArchived: false },
    { id: 5, name: "Corn", status: "Harvested", isArchived: false },
    { id: 6, name: "Old Crop", status: "Harvested", isArchived: true },
];

test("default active lifecycle excludes completed/archived crops and prioritizes overdue Ready rows", () => {
    const active = rows.filter((crop) => matchesCropLifecycleFilter(crop, "Active Crops"));
    const sorted = sortCropsByHarvestPriority(active);
    assert.deepEqual(sorted.map((crop) => crop.id), [3, 2, 4, 1]);
    assert.equal(active.some((crop) => crop.id === 5 || crop.id === 6), false);
});

test("completed and archived lifecycle filters remain separate", () => {
    assert.deepEqual(rows.filter((crop) => matchesCropLifecycleFilter(crop, "Fully Harvested/Completed")).map((crop) => crop.id), [5]);
    assert.deepEqual(rows.filter((crop) => matchesCropLifecycleFilter(crop, "Archived")).map((crop) => crop.id), [6]);
});

test("Crops UI exposes a compact Ready priority filter and visibly separates estimated vs confirmed readiness", () => {
    assert.match(cropsSource, /Ready for Harvest \(\{page\.readyForHarvestCount\}\)/);
    assert.match(tableSource, /crop\.readinessStatus === "Confirmed Ready"/);
    assert.match(tableSource, /"Estimated Ready"/);
    assert.match(tableSource, /Record harvest/);
});

test("manual harvest requires performer, reason, idempotency, explicit Final confirmation, and one in-flight submit", () => {
    assert.match(modalSource, /Performed By/);
    assert.match(modalSource, /Reason for Manual \/ Assisted Recording/);
    assert.match(modalSource, /Final Harvest will close this crop cycle and stop future care tasks/);
    assert.match(modalSource, /name="finalHarvestConfirmed"[\s\S]*?required[\s\S]*?aria-required="true"/);
    assert.match(modalSource, /The manager must check this confirmation before Final Harvest can be saved/);
    assert.match(modalSource, /if \(name === "harvestType" \|\| name === "cropId" \|\| name === "harvestDate"\)[\s\S]*?finalHarvestConfirmed = false/);
    assert.match(modalSource, /finalHarvestPrecheckBlocked/);
    assert.match(modalSource, /disabled=\{crops\.length === 0 \|\| submitting \|\| finalHarvestPrecheckBlocked\}/);
    assert.match(modalSource, /submitting/);
    assert.match(modalSource, /Saving Harvest\.\.\./);
    assert.match(cropServiceSource, /"Idempotency-Key"/);
    assert.match(cropServiceSource, /performed_by_employee_id/);
    assert.match(cropServiceSource, /manual_reason/);
    assert.match(cropServiceSource, /evidence_url/);
    assert.match(cropServiceSource, /final_harvest_confirmed/);
});

test("Final Harvest checks same-day tasks only after manager confirmation and deep-links blockers", () => {
    assert.match(modalSource, /form\.harvestType !== "Final Harvest"[\s\S]*?!form\.finalHarvestConfirmed/);
    assert.match(modalSource, /workforceService[\s\S]*?\.getTasks\(\{[\s\S]*?source_module: "Crop"[\s\S]*?source_record_id/);
    assert.match(modalSource, /\["Pending", "In Progress", "Submitted for Review", "Returned"\]\.includes\(task\.status\)/);
    assert.match(modalSource, /Resolve same-day crop tasks before closing this crop cycle/);
    assert.match(modalSource, /Final Harvest remains disabled until these tasks are resolved/);
    assert.match(modalSource, /Open Task/);
    assert.match(modalSource, /taskId: String\(task\.id\)/);
    assert.match(modalSource, /from: "crops"/);
    assert.match(modalSource, /returnTo/);
});


test("crop harvest page prevents repeated mutations while the first request is in flight", () => {
    assert.match(cropsPageSource, /cropHarvestInFlightRef/);
    assert.match(cropsPageSource, /if \(cropHarvestInFlightRef\.current\)/);
    assert.match(cropsPageSource, /cropHarvestInFlightRef\.current = true/);
    assert.match(cropsPageSource, /cropHarvestInFlightRef\.current = false/);
});

test("reopening uses a reasoned accessible dialog and keeps errors next to its actions", () => {
    assert.doesNotMatch(cropsPageSource, /window\.prompt\(/);
    assert.match(cropsSource, /<ReopenCropModal/);
    assert.match(reopenModalSource, /role="dialog" aria-modal="true"/);
    assert.match(reopenModalSource, /Reason for reopening/);
    assert.match(reopenModalSource, /onSave\(\{ reason: cleaned, newStatus \}\)/);
    assert.match(reopenModalSource, /role="alert"/);
    assert.match(reopenModalSource, /busyRef\.current/);
    assert.match(reopenModalSource, /document\.body\.style\.overflow = previousOverflow/);
});

test("crop harvest task submission collects occurrence yield in kg instead of inventing a separate Crop record", () => {
    assert.match(myTasksSource, /isCropHarvestTask/);
    assert.match(myTasksSource, /Actual Harvest Yield \*/);
    assert.match(myTasksSource, /reported Partial\/Final type waits for manager confirmation/);
    assert.match(myTasksSource, /\? "kg"/);
});

test("manager-assisted harvest records the employee's actual kg and always waits for review", () => {
    assert.match(taskManagementSource, /assistedIsCropHarvest/);
    assert.match(taskManagementSource, /Actual Harvest Yield \(kg\) \*/);
    assert.match(taskManagementSource, /Reported Harvest Type \*/);
    assert.match(taskManagementSource, /I confirm the entered kg is the employee's actual harvested yield/);
    assert.match(taskManagementSource, /harvest_type_intent:\s*assistedIsCropHarvest/);
    assert.match(taskManagementSource, /Submit Harvest for Review/);
    assert.match(taskManagementSource, /!assistedIsCropHarvest && \(/);
    assert.match(taskManagementSource, /can only be submitted for review/);
});


test("task-linked harvest intent waits in Crops until Task Management confirms it", () => {
    assert.match(myTasksSource, /Harvest Type \*/);
    assert.match(myTasksSource, /harvest_type_intent/);
    assert.match(myTasksSource, /crop will stay unchanged until the manager confirms it in Task Management/);
    assert.match(reviewSource, /Employee reported harvest type/);
    assert.match(reviewSource, /submission\?\.harvest_type_intent/);
    assert.match(reviewSource, /changing the employee-reported harvest type/);
    assert.match(cropServiceSource, /pendingHarvestTaskId/);
    assert.match(cropServiceSource, /pendingHarvestMessage/);
    assert.match(tableSource, /crop\.pendingHarvestMessage/);
    assert.match(tableSource, /onOpenHarvestTask/);
    assert.match(tableSource, /assignment/);
    assert.match(cropsPageSource, /!crop\.pendingHarvestTaskId/);
    assert.match(cropsPageSource, /taskId: String\(crop\.pendingHarvestTaskId\)/);
});

test("manager review must choose Partial or Final Harvest and explicitly confirm final closure", () => {
    assert.match(reviewSource, /Harvest Lifecycle Decision/);
    assert.match(reviewSource, /Partial Harvest/);
    assert.match(reviewSource, /Final\/Fully Harvested/);
    assert.match(reviewSource, /final_harvest_confirmed/);
    assert.match(reviewSource, /Confirm the Final Harvest consequence before approval/);
    assert.match(reviewSource, /report\?\.crop_status === "Harvested"/);
    assert.match(reviewSource, /report\?\.harvest_approval_blocker/);
    assert.match(reviewSource, /work-review-footer-error/);
    assert.match(reviewSource, /disabled=\{busy \|\| loading \|\| !canReview \|\| Boolean\(approvalBlocker\)\}/);
    assert.match(taskManagementSource, /const stale = err\?\.status === 409 && \/no longer awaiting review\/i\.test/);
});
