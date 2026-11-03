import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relativePath) => fs.readFile(path.join(projectRoot, relativePath), "utf8");
const blockFor = (css, selector) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const matcher = new RegExp(`${escaped}\\s*\\{`, "g");
    let match = null;
    let current = null;
    while ((current = matcher.exec(css)) !== null) match = current;
    if (!match) return "";
    const start = match.index;
    const end = css.indexOf("}", start);
    return end < 0 ? css.slice(start) : css.slice(start, end + 1);
};

const globalCss = await read("src/index.css");
const pages = [
    ["Crops", "src/views/Crops/Crops.css", ".crop-summary-card"],
    ["Livestock", "src/views/Livestock/Livestock.css", ".livestock-summary-card"],
    ["Inventory", "src/views/Inventory/Inventory.css", ".inventory-page-summary-card"],
    ["Alerts", "src/views/Alerts/Alerts.css", ".alerts-page-summary-card"],
    ["Reports", "src/views/Reports/Reports.css", ".reports-page-summary-card"],
    ["Dashboard", "src/views/Dashboard/Dashboard.css", ".summary-card"],
    ["Production & Sales", "src/views/ProductionSales/ProductionSales.css", ".ps-summary-grid article"],
    ["Settings", "src/views/Settings/Settings.css", ".settings-page-summary-card"],
];

test("system summary cards share the compact My Tasks sizing tokens", async () => {
    assert.match(globalCss, /--summary-card-compact-height:\s*78px/);
    assert.match(globalCss, /--summary-card-compact-icon:\s*36px/);
    assert.match(globalCss, /--summary-card-compact-accent:\s*3px/);

    for (const [name, file, selector] of pages) {
        const css = await read(file);
        const block = blockFor(css, selector);
        assert.ok(block, `${name} summary-card block should exist`);
        assert.match(block, /height:\s*var\(--summary-card-compact-height\)/, `${name} should use the exact My Tasks height`);
        assert.match(block, /min-height:\s*var\(--summary-card-compact-height\)/, `${name} should preserve the compact minimum height`);
        assert.match(block, /max-height:\s*var\(--summary-card-compact-height\)/, `${name} should not grow taller than My Tasks`);
        assert.match(block, /padding:\s*var\(--summary-card-compact-padding-y\) var\(--summary-card-compact-padding-x\)/, `${name} should use compact padding`);
    }
});

test("icon-based summary cards share the same compact icon scale", async () => {
    const iconPages = [
        ["Crops", "src/views/Crops/Crops.css", ".crop-summary-icon"],
        ["Livestock", "src/views/Livestock/Livestock.css", ".livestock-summary-icon"],
        ["Inventory", "src/views/Inventory/Inventory.css", ".inventory-page-summary-icon"],
        ["Alerts", "src/views/Alerts/Alerts.css", ".alerts-page-summary-icon"],
        ["Reports", "src/views/Reports/Reports.css", ".reports-page-summary-icon"],
        ["Production & Sales", "src/views/ProductionSales/ProductionSales.css", ".ps-summary-grid article > .material-symbols-outlined"],
        ["Settings", "src/views/Settings/Settings.css", ".settings-page-summary-card\n    > span"],
    ];

    for (const [name, file, selector] of iconPages) {
        const css = await read(file);
        const block = blockFor(css, selector);
        assert.ok(block, `${name} summary icon block should exist`);
        assert.match(block, /width:\s*var\(--summary-card-compact-icon\)/, `${name} icon should use compact width`);
        assert.match(block, /height:\s*var\(--summary-card-compact-icon\)/, `${name} icon should use compact height`);
    }
});


test("summary cards share the exact My Tasks typography scale", async () => {
    assert.match(globalCss, /--summary-card-compact-label:\s*0\.72rem/);
    assert.match(globalCss, /--summary-card-compact-label-weight:\s*600/);
    assert.match(globalCss, /--summary-card-compact-value:\s*1\.28rem/);
    assert.match(globalCss, /--summary-card-compact-value-weight:\s*700/);

    const typographyPages = [
        ["My Tasks", "src/views/MyTasks/MyTasks.css", ".my-tasks-page .my-tasks-compact-stats .workforce-stat-label", ".my-tasks-page .my-tasks-compact-stats .workforce-stat-copy strong"],
        ["Task Management", "src/views/TaskManagement/TaskManagement.css", ".task-management-compact-stats .workforce-stat-label", ".task-management-compact-stats .workforce-stat-copy strong"],
        ["Crops", "src/views/Crops/Crops.css", ".crop-summary-card p", ".crop-summary-card h2"],
        ["Livestock", "src/views/Livestock/Livestock.css", ".livestock-summary-card p", ".livestock-summary-card h2"],
        ["Inventory", "src/views/Inventory/Inventory.css", ".inventory-page-summary-card p", ".inventory-page-summary-card h2"],
        ["Alerts", "src/views/Alerts/Alerts.css", ".alerts-page-summary-card p", ".alerts-page-summary-card h2"],
        ["Reports", "src/views/Reports/Reports.css", ".reports-page-summary-card p", ".reports-page-summary-card h2"],
        ["Dashboard", "src/views/Dashboard/Dashboard.css", ".summary-card h3", ".summary-card h2"],
        ["Production & Sales", "src/views/ProductionSales/ProductionSales.css", ".ps-summary-grid small", ".ps-summary-grid strong"],
    ];

    for (const [name, file, labelSelector, valueSelector] of typographyPages) {
        const css = await read(file);
        const labelBlock = blockFor(css, labelSelector);
        const valueBlock = blockFor(css, valueSelector);
        assert.ok(labelBlock, `${name} label block should exist`);
        assert.ok(valueBlock, `${name} value block should exist`);
        assert.match(labelBlock, /font-size:\s*var\(--summary-card-compact-label\)/, `${name} label should use My Tasks label size`);
        assert.match(valueBlock, /font-size:\s*var\(--summary-card-compact-value\)/, `${name} value should use My Tasks value size`);
    }
});

test("Reports frontend source remains included in the complete project", async () => {
    const route = await read("src/app/(protected)/reports/page.jsx");
    const view = await read("src/views/Reports/Reports.jsx");
    assert.match(route, /Reports/);
    assert.match(view, /Reports/);
});


test("description text cannot make Reports or Alerts summary cards taller than My Tasks", async () => {
    for (const [name, file, selector] of [
        ["Alerts", "src/views/Alerts/Alerts.css", ".alerts-page-summary-card"],
        ["Reports", "src/views/Reports/Reports.css", ".reports-page-summary-card"],
    ]) {
        const css = await read(file);
        const block = blockFor(css, selector);
        assert.match(block, /height:\s*var\(--summary-card-compact-height\)/, `${name} should have fixed compact height`);
        assert.match(block, /max-height:\s*var\(--summary-card-compact-height\)/, `${name} descriptions must not expand the card`);
    }
});
