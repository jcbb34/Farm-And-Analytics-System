import assert from "node:assert/strict";
import test from "node:test";
import { livestockService } from "../src/services/livestockService.js";
import { invalidateReadCache } from "../src/services/httpClient.js";

const original = Object.fromEntries(["window", "sessionStorage", "localStorage", "fetch"].map((key) => [key, globalThis[key]]));
const plan = { monitoringEnabled: true, monitoringStartDate: "2026-10-29", monitoringEndDate: "2026-11-30", monitoringFrequencyDays: 3, assignedEmployeeId: 7 };
const stored = { id: 42, monitoring_enabled: true, monitoring_start_date: "2026-10-29", monitoring_end_date: "2026-11-30", monitoring_frequency_days: 3, assigned_employee_id: 7 };
const disabled = { ...stored, monitoring_enabled: false };

test.beforeEach(() => {
    invalidateReadCache();
    globalThis.window = { location: { origin: "http://localhost:3000" }, setTimeout, clearTimeout };
    globalThis.sessionStorage = globalThis.localStorage = { getItem: () => null };
});
test.after(() => Object.assign(globalThis, original));

test("enabling monitoring returns the persisted configuration after an uncached read", async () => {
    const requests = [];
    globalThis.fetch = async (url, options) => {
        requests.push({ path: new URL(url).pathname, ...options });
        return Response.json(stored);
    };
    const saved = await livestockService.updateLivestock(42, plan);
    assert.equal(saved.monitoringEnabled, true);
    assert.equal(saved.monitoringFrequencyDays, 3);
    assert.equal(saved.assignedEmployeeId, 7);
    assert.deepEqual(requests.map((request) => request.method), ["PUT", "GET"]);
    assert.equal(requests[1].cache, "no-store");
});

test("HTTP success cannot hide an older backend silently ignoring monitoring fields", async () => {
    globalThis.fetch = async () => Response.json({ id: 42, record_name: "Old response" });
    await assert.rejects(livestockService.updateLivestock(42, plan), { code: "MONITORING_SAVE_NOT_CONFIRMED" });
});

test("a write echo without persisted monitoring is rejected instead of announcing success", async () => {
    globalThis.fetch = async (_url, options) => Response.json(options.method === "PUT" ? stored : disabled);
    await assert.rejects(livestockService.updateLivestock(42, plan), { code: "MONITORING_SAVE_NOT_CONFIRMED" });
});

test("a cached disabled record cannot undo a verified enabled schedule", async () => {
    let row = disabled;
    globalThis.fetch = async (_url, options) => {
        if (options.method === "PUT") row = stored;
        return Response.json(row);
    };
    assert.equal((await livestockService.getLivestockRecord(42)).monitoringEnabled, false);
    assert.equal((await livestockService.updateLivestock(42, plan)).monitoringEnabled, true);
    assert.equal((await livestockService.getLivestockRecord(42)).monitoringEnabled, true);
});

test("disabling recurrence is verified and retained rather than replaced by a checked default", async () => {
    globalThis.fetch = async () => Response.json(disabled);
    assert.equal((await livestockService.updateLivestock(42, { ...plan, monitoringEnabled: false })).monitoringEnabled, false);
});

test("a changed interval or employee must also survive the database read-back", async () => {
    globalThis.fetch = async (_url, options) => Response.json(options.method === "PUT" ? stored : { ...stored, assigned_employee_id: 8 });
    await assert.rejects(livestockService.updateLivestock(42, plan), { code: "MONITORING_SAVE_NOT_CONFIRMED" });
});

test("unrelated livestock updates keep their existing API behavior", async () => {
    const requests = [];
    globalThis.fetch = async (_url, options) => { requests.push(options.method); return Response.json({ id: 42, health_status: "Healthy" }); };
    assert.equal((await livestockService.updateLivestock(42, { healthStatus: "Healthy" })).healthStatus, "Healthy");
    assert.deepEqual(requests, ["PUT"]);
});

test("new livestock monitoring is confirmed before create is reported successful", async () => {
    const requests = [];
    globalThis.fetch = async (_url, options) => { requests.push(options); return Response.json(stored); };
    assert.equal((await livestockService.createLivestock({ ...plan, recordName: "Test group" }, { idempotencyKey: "test-monitoring-create" })).monitoringEnabled, true);
    assert.deepEqual(requests.map((request) => request.method), ["POST", "GET"]);
    assert.equal(requests[0].headers["Idempotency-Key"], "test-monitoring-create");
});
