import test from "node:test";
import assert from "node:assert/strict";
import { archiveRecordPath, safeArchiveReturn } from "../src/components/Archives/archiveNavigation.js";

test("each archive link identifies the correct module and exact record instead of matching names", () => {
    for (const [module, path] of [["Crop", "/crops"], ["Livestock", "/livestock"], ["Inventory", "/inventory"], ["Report", "/reports"]]) {
        const url = new URL(archiveRecordPath({ module, sourceId: 123, recordName: "Same name" }), "http://farm.local");
        assert.equal(url.pathname, path);
        assert.equal(url.searchParams.get("archive"), "1");
        assert.equal(url.searchParams.get("record"), "123");
        assert.equal(url.searchParams.get("archive_module"), module);
    }
});
test("workforce archive links retain the existing Archives tab", () => {
    const url = new URL(archiveRecordPath({ module: "Employee", sourceId: 7 }), "http://farm.local");
    assert.equal(url.pathname, "/task-management"); assert.equal(url.searchParams.get("tab"), "archives");
});
test("return navigation preserves filters, dates and pagination", () => {
    const returnTo = "/settings?section=archive&archive_search=Field+A&archive_module=Crop&archive_offset=25&archive_from=2026-08-01";
    const url = new URL(archiveRecordPath({ module: "Crop", sourceId: 7 }, returnTo), "http://farm.local");
    assert.equal(url.searchParams.get("return_to"), returnTo);
});
test("archive navigation rejects invalid IDs, unsupported modules and external return targets", () => {
    assert.equal(archiveRecordPath({ module: "Unknown", sourceId: 7 }), null);
    for (const id of [0, -1, "other", 1.5]) assert.equal(archiveRecordPath({ module: "Crop", sourceId: id }), null);
    for (const value of ["https://example.com/settings", "//example.com/settings", "/settings-evil?section=archive"]) {
        assert.equal(safeArchiveReturn(value), "");
        assert.equal(new URL(archiveRecordPath({ module: "Crop", sourceId: 1 }, value), "http://farm.local").searchParams.has("return_to"), false);
    }
});
