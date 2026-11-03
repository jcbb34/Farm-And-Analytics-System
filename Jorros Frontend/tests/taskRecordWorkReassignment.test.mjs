import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const source = [
    "src/views/TaskManagement/TaskManagement.jsx",
    "src/views/TaskManagement/components/AssignmentsPanel.jsx",
].map((relative) => fs.readFileSync(path.join(root, relative), "utf8")).join("\n");
const workforceCss = fs.readFileSync(path.join(root, "src/styles/workforce-ui.css"), "utf8");

test("Record Work is disabled until a task that needs reassignment has a valid assignee", () => {
    assert.match(source, /const recordWorkUnavailable = Boolean\(task\.work_suspended \|\| task\.needs_reassignment \|\| !task\.assigned_employee_id\)/);
    assert.match(source, /disabled=\{recordWorkUnavailable\}/);
    assert.match(source, /Reassign this task to an available employee before recording work/);
    assert.match(source, /task\.needs_reassignment\s*\|\|\s*!task\.assigned_employee_id/);
});

test("direct assisted-submission opening is also blocked while reassignment is unresolved", () => {
    assert.match(source, /!correctionMode && \(task\?\.needs_reassignment \|\| !task\?\.assigned_employee_id \|\| task\?\.work_suspended\)/);
    assert.match(source, /navigation\.action !== "assisted-submission"/);
    assert.match(source, /\|\| task\.needs_reassignment\s*\|\| !task\.assigned_employee_id/);
});

test("disabled workforce buttons use the shared greyed-out state", () => {
    assert.match(workforceCss, /\.workforce-button,[\s\S]*?\):disabled\s*\{[\s\S]*?background:\s*var\(--workforce-disabled-bg\)/);
    assert.match(workforceCss, /cursor:\s*not-allowed/);
});
