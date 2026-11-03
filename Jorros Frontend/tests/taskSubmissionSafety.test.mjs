import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relativePath) => fs.readFile(path.join(projectRoot, relativePath), "utf8");

const workforceService = await read("src/services/workforceService.js");
const myTasks = await read("src/views/MyTasks/MyTasks.jsx");
const taskManagement = [
    await read("src/views/TaskManagement/TaskManagement.jsx"),
    await read("src/views/TaskManagement/components/TaskManagementModals.jsx"),
    await read("src/views/TaskManagement/taskManagementUtils.js"),
].join("\n");
const resourceUsagePanel = await read("src/components/ResourceUsagePanel/ResourceUsagePanel.jsx");
const livestockService = await read("src/services/livestockService.js");
const livestockPage = await read("src/views/Livestock/Livestock.jsx");
const idempotencySource = await read("src/services/idempotencyKey.js");
const idempotency = await import(
    `data:text/javascript;base64,${Buffer.from(idempotencySource).toString("base64")}`
);

test("stable submission keys are reused for an unchanged retry and replaced after payload changes", () => {
    const ref = { current: null };
    const payload = { actual_quantity: 2, actual_unit: "kg" };
    const first = idempotency.stableIdempotencyKey(ref, payload, "task-submit:12");
    const retry = idempotency.stableIdempotencyKey(ref, { ...payload }, "task-submit:12");
    assert.equal(retry, first);

    const changed = idempotency.stableIdempotencyKey(
        ref,
        { actual_quantity: 3, actual_unit: "kg" },
        "task-submit:12"
    );
    assert.notEqual(changed, first);
});

test("task submission service sends the idempotency key header and exposes explicit void", () => {
    assert.match(workforceService, /submitTask:\s*async\s*\(id, payload, idempotencyKey = null\)/);
    assert.match(workforceService, /"Idempotency-Key":\s*idempotencyKey/);
    assert.match(workforceService, /voidTask:\s*async\s*\(id, reason\)/);
    assert.match(workforceService, /\/workforce\/tasks\/\$\{id\}\/void/);
});

test("employee My Tasks uses a stable retry key and never exposes negative-stock override controls", () => {
    assert.match(myTasks, /stableIdempotencyKey\(/);
    assert.match(myTasks, /`task-submit:\$\{task\.id\}`/);
    assert.match(myTasks, /workforceService\.submitTask\(task\.id, payload, idempotencyKey\)/);
    assert.match(myTasks, /clearStableIdempotencyKey\(submitRequestRef\)/);
    assert.doesNotMatch(myTasks, /allow_negative_inventory/);
    assert.doesNotMatch(myTasks, /inventory_override_reason/);
});

test("manager-assisted submission exposes explicit override reason and stable retry behavior", () => {
    assert.match(taskManagement, /allow_negative_inventory:\s*false/);
    assert.match(taskManagement, /inventory_override_reason:\s*""/);
    assert.match(taskManagement, /Authorized negative-stock override/);
    assert.match(taskManagement, /payload\.allow_negative_inventory && !payload\.inventory_override_reason/);
    assert.match(taskManagement, /stableIdempotencyKey\(/);
    assert.match(taskManagement, /`assisted-task-submit:\$\{assistedTask\.id\}`/);
});

test("manager-assisted resource work requires confirmation of the actual quantity", () => {
    assert.match(taskManagement, /actual_quantity_confirmed:\s*false/);
    assert.match(taskManagement, /actual amount used, not only the planned amount/);
    assert.match(taskManagement, /actual_quantity_confirmed:\s*Boolean\(assistedForm\.actual_quantity_confirmed\)/);
    assert.match(taskManagement, /Required for a late manager-recorded entry/);
});

test("Livestock feeding keeps history without a duplicate manual confirmation action", () => {
    assert.match(livestockService, /async confirmFeeding\([\s\S]*idempotencyKey = null/);
    assert.match(livestockService, /"Idempotency-Key":\s*idempotencyKey/);
    assert.doesNotMatch(livestockPage, /FeedingConfirmationModal|title="Confirm feeding"|livestockService\.confirmFeeding\(/);
    assert.match(livestockPage, /title="View feeding history"/);
    assert.match(livestockPage, /<FeedingHistoryModal\s/);
    assert.match(livestockPage, /onClick=\{\(\) => setSelectedFeedingHistoryAnimal\(animal\)\}/);
    assert.match(livestockPage, /livestockService\.getLivestockRecord\(animal\.id\)/);
    assert.match(livestockPage, /Unable to load feeding history/);
});

test("manager review requests Owner/Admin authorization and Voided stays historical", () => {
    assert.match(taskManagement, /requestVoid\(\{ action: "task", recordId: task\.id, onStale: load \}\)/);
    assert.match(taskManagement, /Usage Reversal|posted inventory usage was reversed/);
    assert.match(taskManagement, /"Voided"/);
    assert.match(resourceUsagePanel, /"Voided"/);
});
