import assert from "node:assert/strict";
import test from "node:test";
import { canonicalLocationName, cleanLocationName, locationSearchKey, uniqueLocationNames } from "../src/services/farmLocationService.js";
import { activeEventEmployees, eventNeedsResource, eventSourceModule } from "../src/components/DashboardCalendar/eventFormHelpers.js";

test("location names reuse saved spelling, remove accidental spaces and preserve custom names", () => {
    const options = uniqueLocationNames([" Field A ", "field a", "Warehouse   B", "", null, "Peña field"]);
    assert.equal(options.length, 3);
    assert.equal(canonicalLocationName(" FIELD  A ", options), "Field A");
    assert.equal(cleanLocationName("  New   hillside  "), "New hillside");
    assert.equal(canonicalLocationName("New   hillside", options), "New hillside");
    assert.equal(locationSearchKey("PEÑA"), "pena");
    assert.equal(options.find((name) => locationSearchKey(name).includes("pena")), "Peña field");
});

test("event employee choices use active profiles and retain their real IDs", () => {
    const rows = [{ id: 42, full_name: "Zara Cruz", employment_status: "Active" },
        { id: 9, full_name: "Ana Reyes", employment_status: "Active" },
        { id: 3, full_name: "Archived Worker", employment_status: "Active", is_archived: true },
        { id: 8, full_name: "Inactive Worker", employment_status: "Inactive" }];
    assert.deepEqual(activeEventEmployees(rows).map((row) => row.id), [9, 42]);
    assert.equal(rows[0].id, 42); // Sorting must not mutate another consumer's list.
    assert.deepEqual(activeEventEmployees(null), []);
});

test("only assigned resource work requests inventory links", () => {
    for (const type of ["Livestock Feeding", "Vaccination", "Fertilization", "Pest Control"]) {
        assert.equal(eventNeedsResource({ type, assignedEmployeeId: 42 }), true);
        assert.equal(eventNeedsResource({ type, assignedEmployeeId: "" }), false);
    }
    assert.equal(eventNeedsResource({ title: "Apply medicine", type: "Other", assignedEmployeeId: 42 }), true);
    assert.equal(eventNeedsResource({ title: "Inspect fences", type: "Farm Inspection", assignedEmployeeId: 42 }), false);
    assert.equal(eventSourceModule("Vaccination"), "Livestock");
    assert.equal(eventSourceModule("Fertilization"), "Crop");
});
