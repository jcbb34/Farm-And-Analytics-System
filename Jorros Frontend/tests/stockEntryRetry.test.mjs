import assert from "node:assert/strict";
import test from "node:test";
import { productionSalesService } from "../src/services/productionSalesService.js";
import { livestockService } from "../src/services/livestockService.js";
import { resourceUsageService } from "../src/services/resourceUsageService.js";
import { reportService } from "../src/services/reportService.js";
import { clearStableIdempotencyKey, stableIdempotencyKey } from "../src/services/idempotencyKey.js";
import { invalidateReadCache } from "../src/services/httpClient.js";

const original = Object.fromEntries(["window", "sessionStorage", "localStorage", "fetch"].map((key) => [key, globalThis[key]]));
test.beforeEach(() => {
    invalidateReadCache();
    globalThis.window = { location: { origin: "http://farm.local:3000" }, setTimeout, clearTimeout };
    globalThis.sessionStorage = globalThis.localStorage = { getItem: () => null };
});
test.after(() => Object.assign(globalThis, original));

for (const [name, path, call, payload] of [
    ["resource usage", "/resource-usages", (body, options) => resourceUsageService.createUsage(body, options), { module: "Crop", targetId: 1, inventoryItemId: 7, usageType: "Fertilizer", quantity: 2, usageDate: "2026-10-31" }],
    ["production", "/production-sales/production", (body, options) => productionSalesService.createProduction(body, options), { livestock_id: 1, quantity: 5 }],
    ["reproduction", "/production-sales/reproduction", (body, options) => productionSalesService.createReproduction(body, options), { livestock_id: 1, record_type: "Hatch" }],
    ["vaccination", "/livestock/1/vaccination-records", (body, options) => livestockService.addVaccinationRecord(1, body, options), { vaccine: "Synthetic Test Vaccine", dateAdministered: "2026-10-31", inventoryItemId: 7, quantityUsed: 2 }],
]) {
    test(`${name} retry after a failed response sends the same key and body`, async () => {
        const requests = [], ref = { current: null };
        globalThis.fetch = async (url, options) => {
            requests.push({ url, ...options });
            return requests.length === 1
                ? Response.json({ detail: "Temporary test failure" }, { status: 503 })
                : Response.json({ id: 42 });
        };
        const key = stableIdempotencyKey(ref, payload, name);
        await assert.rejects(call(payload, { idempotencyKey: key }), { status: 503 });
        await call(payload, { idempotencyKey: stableIdempotencyKey(ref, payload, name) });
        assert.equal(requests.length, 2);
        assert.equal(new URL(requests[0].url).pathname, `/api/v1${path}`);
        assert.equal(requests[0].method, "POST");
        assert.equal(requests[0].headers["Idempotency-Key"], key);
        assert.equal(requests[1].headers["Idempotency-Key"], key);
        assert.equal(requests[0].body, requests[1].body);
        clearStableIdempotencyKey(ref);
        assert.notEqual(stableIdempotencyKey(ref, payload, name), key, "a separate successful entry gets a new key");
    });
}

test("report counters use the backend summary and pass the selected status filter", async () => {
    let requested;
    globalThis.fetch = async (url) => {
        requested = new URL(url);
        return Response.json({ matching_total: 12, total: 50, approved: 30, for_review: 15, automatic: 20, custom: 30 });
    };
    const summary = await reportService.getReportSummary({ status: "For Review", tab: "Crop Reports" });
    assert.equal(requested.searchParams.get("status"), "For Review");
    assert.equal(requested.searchParams.get("tab"), "Crop Reports");
    assert.deepEqual(summary, { matchingTotal: 12, total: 50, approved: 30, forReview: 15, automatic: 20, custom: 30 });
});
