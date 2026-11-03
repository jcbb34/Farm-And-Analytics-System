import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relativePath) => fs.readFile(path.join(projectRoot, relativePath), "utf8");

const component = await read("src/components/EvidencePhoto/EvidencePhoto.jsx");
const evidenceCss = await read("src/components/EvidencePhoto/EvidencePhoto.css");
const workforceCss = await read("src/styles/workforce-ui.css");
const myTasks = await read("src/views/MyTasks/MyTasks.jsx");
const taskManagement = [
    await read("src/views/TaskManagement/TaskManagement.jsx"),
    await read("src/views/TaskManagement/components/TaskManagementModals.jsx"),
].join("\n");
const reviewModal = await read("src/views/TaskManagement/WorkSubmissionReviewModal.jsx");
const layout = await read("src/app/layout.jsx");

test("evidence workflow uses one reusable component in employee, assisted, and review surfaces", () => {
    assert.match(myTasks, /<EvidencePhotoField/);
    assert.match(myTasks, /<EvidenceViewButton/);
    assert.match(taskManagement, /<EvidencePhotoField/);
    assert.match(reviewModal, /<EvidenceInlinePreview/);
    assert.doesNotMatch(myTasks, /uploadEvidencePhoto\s*\(/);
    assert.doesNotMatch(taskManagement, /uploadEvidencePhoto\s*\(/);
});

test("evidence button states include upload, replace, uploading, view, remove, success, error, and disabled behavior", () => {
    assert.match(component, /hasEvidence \? "Replace Photo" : "Upload Photo"/);
    assert.match(component, /uploading \? "Uploading…"/);
    assert.match(component, /Opening…/);
    assert.match(component, />Remove</);
    assert.match(component, /type: "success"/);
    assert.match(component, /type: "error"/);
    assert.match(component, /disabled=\{blocked\}/);
    assert.match(component, /disabled=\{disabled \|\| loading\}/);
    assert.match(component, /data-evidence-state=/);
    assert.match(component, /aria-live="polite"/);
});

test("evidence actions are real buttons with decorative icons hidden from assistive technology", () => {
    const typeButtonCount = (component.match(/type="button"/g) || []).length;
    const ariaHiddenIconCount = (component.match(/aria-hidden="true"/g) || []).length;
    assert.ok(typeButtonCount >= 4, `expected at least 4 type=button controls, found ${typeButtonCount}`);
    assert.ok(ariaHiddenIconCount >= 6, `expected decorative icons to be aria-hidden, found ${ariaHiddenIconCount}`);
    assert.match(component, /role="group"/);
    assert.match(component, /aria-busy=\{uploading\}/);
});

test("shared workforce control tokens enforce 44px touch targets and consistent typography", () => {
    assert.match(workforceCss, /--workforce-control-height:\s*44px/);
    assert.match(workforceCss, /--workforce-control-radius:\s*10px/);
    assert.match(workforceCss, /--workforce-control-font-size:\s*0\.875rem/);
    assert.match(workforceCss, /--workforce-control-icon-size:\s*20px/);
    assert.match(evidenceCss, /min-height:\s*var\(--workforce-control-height, 44px\)/);
    assert.match(evidenceCss, /font-size:\s*var\(--workforce-control-font-size, 0\.875rem\)/);
    assert.match(evidenceCss, /font-size:\s*var\(--workforce-control-icon-size, 20px\)/);
});

test("evidence semantic colors and disabled/focus states are explicit", () => {
    assert.match(evidenceCss, /\.evidence-action-button--upload[\s\S]*background:\s*var\(--workforce-green/);
    assert.match(evidenceCss, /\.evidence-action-button--upload[\s\S]*color:\s*#ffffff/);
    assert.match(evidenceCss, /\.evidence-action-button--view[\s\S]*border-color:\s*var\(--workforce-green/);
    assert.match(evidenceCss, /\.evidence-action-button--remove[\s\S]*var\(--workforce-danger/);
    assert.match(evidenceCss, /\.evidence-action-button:disabled[\s\S]*var\(--workforce-disabled-bg/);
    assert.match(evidenceCss, /\.evidence-action-button:focus-visible/);
    assert.match(workforceCss, /--workforce-focus-ring:/);
});

test("long filenames are safe and retain their full accessible value", () => {
    assert.match(component, /title=\{displayedName\}/);
    assert.match(component, /aria-label=\{`Selected evidence file: \$\{displayedName\}`\}/);
    assert.match(evidenceCss, /\.evidence-file-name[\s\S]*text-overflow:\s*ellipsis/);
    assert.match(evidenceCss, /@media \(max-width:\s*480px\)[\s\S]*overflow-wrap:\s*anywhere/);
});

test("phone and tablet styles wrap or stack evidence controls without shrinking touch height", () => {
    assert.match(evidenceCss, /@media \(max-width:\s*640px\)/);
    assert.match(evidenceCss, /flex:\s*1 1 calc\(50% - 4px\)/);
    assert.match(evidenceCss, /@media \(max-width:\s*480px\)/);
    assert.match(evidenceCss, /grid-template-columns:\s*1fr/);
    assert.match(evidenceCss, /width:\s*100%/);
});

test("workforce shared styles cover buttons, modals, fields, tabs, filters, tables, empty states, and dark theme", () => {
    for (const requiredSelector of [
        ".workforce-button",
        ".workforce-task-modal",
        ".workforce-field label",
        ".workforce-tab",
        ".assignment-filters",
        ".workforce-table",
        ".workforce-empty",
        'html[data-theme="dark"]',
    ]) {
        assert.ok(workforceCss.includes(requiredSelector), `missing shared style for ${requiredSelector}`);
    }
    assert.match(layout, /workforce-ui\.css/);
});
