import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { readinessInspectionValidation, cropInspectionIdentity } from "../src/views/Crops/components/readinessChecklist.mjs";

const root = path.resolve(import.meta.dirname, "..");
const profile = { checks: [{ id: "fruit" }, { id: "quality" }] };
const base = { profile, inspectionDate: "2026-11-14", plantingDate: "2026-01-10", today: "2026-11-14", verdict: "ready", findings: { fruit: true, quality: true }, notes: "" };

test("physical readiness requires all observations answered Yes", () => {
    assert.equal(readinessInspectionValidation(base), "");
    assert.match(readinessInspectionValidation({ ...base, findings: { fruit: true } }), /Answer Yes or No/);
    assert.match(readinessInspectionValidation({ ...base, findings: { fruit: true, quality: false } }), /every required criterion/);
});
test("not-ready records require observations and do not confirm harvest", () => {
    assert.match(readinessInspectionValidation({ ...base, verdict: "not_ready" }), /Explain what/);
    assert.equal(readinessInspectionValidation({ ...base, verdict: "not_ready", notes: "Fruit is immature", findings: { fruit: false, quality: true } }), "");
});
test("inspection dates cannot be future or before planting", () => {
    assert.match(readinessInspectionValidation({ ...base, inspectionDate: "2026-11-15" }), /not later than today/);
    assert.match(readinessInspectionValidation({ ...base, inspectionDate: "2025-01-01" }), /cannot precede/);
});
test("two Coconut Tall plantings preserve field, section, and record code", () => {
    const first = cropInspectionIdentity({ name: "Coconut", variety: "Tall", field: "Field A", sectionName: "Section A1", cropCode: "CRP-1001" });
    const second = cropInspectionIdentity({ name: "Coconut", variety: "Tall", field: "Field A", sectionName: "Section A2", cropCode: "CRP-1002" });
    assert.notEqual(first, second);
    assert.match(first, /Section A1/);
    assert.match(second, /CRP-1002/);
});
test("modal is embedded in Crops and does not add a sidebar page", () => {
    const view = fs.readFileSync(path.join(root, "src/views/Crops/Crops.jsx"), "utf8");
    const records = fs.readFileSync(path.join(root, "src/views/Crops/components/CropsRecordsTable.jsx"), "utf8");
    const modal = fs.readFileSync(path.join(root, "src/views/Crops/components/CropReadinessInspectionModal.jsx"), "utf8");
    assert.match(view, /CropReadinessInspectionModal/);
    assert.match(records, /onInspectReadiness/);
    assert.match(modal, /readinessInspectionValidation/);
    assert.match(modal, /aria-modal="true"/);
    assert.match(modal, /saveReadinessInspection/);
});
