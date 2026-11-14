import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import path from "node:path";
import { sectionLabelForCrop } from "../src/views/Crops/components/cropRecordLocation.mjs";

const root = path.resolve(import.meta.dirname, "..");

test("coconut plantings in separate sections keep different location names", () => {
    assert.equal(sectionLabelForCrop({ section_id: 1, sectionName: "Section A1" }), "Section A1");
    assert.equal(sectionLabelForCrop({ section_id: 2, sectionName: "Section A2" }), "Section A2");
});
test("older API records retain their real section IDs, without inventing names", () => {
    assert.equal(sectionLabelForCrop({ section_id: 17 }), "Section ID 17");
    assert.equal(sectionLabelForCrop({ section_id: null }), null);
    assert.equal(sectionLabelForCrop({ section_id: null, sectionName: "" }), null);
    assert.equal(sectionLabelForCrop({ section_id: 0 }), null);
});
test("the record table shows field, section, and distinct crop code", () => {
    const source = fs.readFileSync(path.join(root, "src/views/Crops/components/CropsRecordsTable.jsx"), "utf8");
    const adapter = fs.readFileSync(path.join(root, "src/services/cropService.js"), "utf8");
    assert.match(source, /<th>Field \/ Section<\/th>/);
    assert.match(source, /sectionLabelForCrop\(crop\)/);
    assert.match(source, /crop\.cropCode/);
    assert.match(adapter, /sectionName: crop\.sectionName \?\? crop\.section_name \?\? null/);
});
