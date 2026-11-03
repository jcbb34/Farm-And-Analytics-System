import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relativePath) => fs.readFile(path.join(projectRoot, relativePath), "utf8");

async function cssFiles(dir) {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) files.push(...await cssFiles(full));
        else if (entry.isFile() && entry.name.endsWith(".css")) files.push(full);
    }
    return files;
}

function rootLayerVariables(globalCss) {
    const variables = new Map();
    for (const match of globalCss.matchAll(/--([a-z0-9-]+):\s*(\d+)\s*;/gi)) {
        variables.set(`--${match[1]}`, Number(match[2]));
    }
    return variables;
}

function resolveLayer(value, variables) {
    const raw = value.trim();
    if (/^\d+$/.test(raw)) return Number(raw);

    const variable = raw.match(/^var\(\s*(--[a-z0-9-]+)\s*(?:,\s*(\d+)\s*)?\)$/i);
    if (!variable) return null;

    if (variables.has(variable[1])) return variables.get(variable[1]);
    return variable[2] ? Number(variable[2]) : null;
}

function modalLikeLayers(css, variables) {
    const layers = [];
    for (const block of css.matchAll(/([^{}]+)\{([^{}]*)\}/gs)) {
        const selector = block[1].replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\s+/g, " ").trim();
        if (!/(modal|overlay|dialog)/i.test(selector)) continue;

        const zIndex = block[2].match(/z-index:\s*([^;]+)/i)?.[1];
        if (!zIndex) continue;

        const resolved = resolveLayer(zIndex, variables);
        layers.push({ selector, raw: zIndex.trim(), resolved });
    }
    return layers;
}

test("system confirmation dialogs render above My Tasks and every feature-modal layer", async () => {
    const globalCss = await read("src/index.css");
    const notificationCss = await read("src/components/AppNotification/AppNotification.css");
    const myTasksCss = await read("src/views/MyTasks/MyTasks.css");
    const unsavedSource = await read("src/context/UnsavedChangesContext.jsx");

    const dialogLayer = Number(globalCss.match(/--layer-system-dialog:\s*(\d+)/)?.[1]);
    assert.ok(Number.isFinite(dialogLayer), "global system dialog layer must be defined");
    assert.match(notificationCss, /\.app-dialog-overlay[\s\S]*?z-index:\s*var\(--layer-system-dialog,\s*100000\)/);
    assert.match(myTasksCss, /\.my-task-submit-overlay[\s\S]*?z-index:\s*12000/);
    assert.match(unsavedSource, /buttonLabel\.includes\("close"\)/);
    assert.match(unsavedSource, /confirmDiscard\(\s*"This form has unsaved changes\. Close it without saving\?"/);

    const variables = rootLayerVariables(globalCss);
    const featureLayers = [];
    for (const file of await cssFiles(path.join(projectRoot, "src"))) {
        if (file.endsWith(path.join("AppNotification", "AppNotification.css"))) continue;
        const css = await fs.readFile(file, "utf8");
        featureLayers.push(...modalLikeLayers(css, variables).map((entry) => ({ ...entry, file })));
    }

    assert.ok(featureLayers.length >= 20, `expected a system-wide modal audit, found only ${featureLayers.length} modal/dialog layers`);
    const unresolved = featureLayers.filter((entry) => entry.resolved == null);
    assert.deepEqual(unresolved, [], `all modal/dialog z-index values must be auditable: ${JSON.stringify(unresolved)}`);

    const highestFeatureLayer = Math.max(...featureLayers.map((entry) => entry.resolved));
    assert.ok(dialogLayer > highestFeatureLayer, `system dialog layer ${dialogLayer} must be above feature modal layer ${highestFeatureLayer}`);
});

test("validation and status toasts render above every modal in the system but below system dialogs", async () => {
    const globalCss = await read("src/index.css");
    const notificationCss = await read("src/components/AppNotification/AppNotification.css");
    const notificationSource = await read("src/context/NotificationContext.jsx");
    const taskManagementSource = await read("src/views/TaskManagement/TaskManagement.jsx");
    const myTasksSource = await read("src/views/MyTasks/MyTasks.jsx");

    const toastLayer = Number(globalCss.match(/--layer-critical-toast:\s*(\d+)/)?.[1]);
    const dialogLayer = Number(globalCss.match(/--layer-system-dialog:\s*(\d+)/)?.[1]);
    const variables = rootLayerVariables(globalCss);

    assert.ok(Number.isFinite(toastLayer), "global critical toast layer must be defined");
    assert.ok(Number.isFinite(dialogLayer), "global system dialog layer must be defined");
    assert.match(notificationCss, /\.app-toast-stack[\s\S]*?z-index:\s*var\(--layer-critical-toast,\s*90000\)/);

    // Render global notices directly under document.body so no feature stacking context,
    // transform, isolation, or overflow container can trap a warning behind a modal.
    assert.match(notificationSource, /import\s*\{\s*createPortal\s*\}\s*from\s*"react-dom"/);
    assert.match(notificationSource, /overlayPortalReady\s*&&\s*createPortal\(/);
    assert.match(notificationSource, /document\.body/);

    // Representative required-evidence validations from both employee and manager/admin flows.
    assert.match(taskManagementSource, /Evidence is required for this task\./);
    assert.match(myTasksSource, /Upload an evidence photo before submitting\./);

    const featureLayers = [];
    for (const file of await cssFiles(path.join(projectRoot, "src"))) {
        if (file.endsWith(path.join("AppNotification", "AppNotification.css"))) continue;
        const css = await fs.readFile(file, "utf8");
        featureLayers.push(...modalLikeLayers(css, variables).map((entry) => ({ ...entry, file })));
    }

    assert.ok(featureLayers.length >= 20, `expected a system-wide modal audit, found only ${featureLayers.length} modal/dialog layers`);
    for (const entry of featureLayers) {
        assert.ok(
            entry.resolved < toastLayer,
            `feature modal/dialog must stay below global toast layer: ${entry.file} ${entry.selector} (${entry.raw})`
        );
    }

    assert.ok(dialogLayer > toastLayer, `system dialog layer ${dialogLayer} must remain above toast layer ${toastLayer}`);
});
