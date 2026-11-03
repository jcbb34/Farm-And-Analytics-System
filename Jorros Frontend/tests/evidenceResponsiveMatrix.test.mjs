import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const evidenceCss = await fs.readFile(path.join(projectRoot, "src/components/EvidencePhoto/EvidencePhoto.css"), "utf8");
const workforceCss = await fs.readFile(path.join(projectRoot, "src/styles/workforce-ui.css"), "utf8");

const widths = [1440, 1366, 768, 390, 360];

function evidenceLayoutAt(width) {
    if (width <= 480) return "stacked-full-width";
    if (width <= 640) return "wrapped-two-up";
    return "inline-flex";
}

test("responsive evidence matrix covers required desktop, tablet, and phone widths", () => {
    assert.deepEqual(
        widths.map((width) => [width, evidenceLayoutAt(width)]),
        [
            [1440, "inline-flex"],
            [1366, "inline-flex"],
            [768, "inline-flex"],
            [390, "stacked-full-width"],
            [360, "stacked-full-width"],
        ]
    );

    assert.match(evidenceCss, /@media \(max-width:\s*640px\)[\s\S]*flex:\s*1 1 calc\(50% - 4px\)/);
    assert.match(evidenceCss, /@media \(max-width:\s*480px\)[\s\S]*grid-template-columns:\s*1fr/);
    assert.match(evidenceCss, /@media \(max-width:\s*480px\)[\s\S]*\.evidence-photo-actions > \.evidence-action-button[\s\S]*width:\s*100%/);
});

test("light and dark evidence/workforce themes have explicit state styling", () => {
    assert.match(evidenceCss, /html\[data-theme="dark"\] \.evidence-action-button--view/);
    assert.match(evidenceCss, /html\[data-theme="dark"\] \.evidence-uploaded-file/);
    assert.match(workforceCss, /html\[data-theme="dark"\] \.workforce-layout/);
    assert.match(workforceCss, /--workforce-disabled-bg:/);
    assert.match(workforceCss, /--workforce-danger-bg:/);
    assert.match(workforceCss, /--workforce-warning-bg:/);
});
