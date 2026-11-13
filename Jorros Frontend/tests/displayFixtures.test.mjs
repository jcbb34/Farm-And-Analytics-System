import assert from "node:assert/strict";
import test from "node:test";
import { withDisplayData } from "../browser-tests/helpers/displayApiFixtures.mjs";

async function fulfill(path, body, status = 200) {
    let result, requested;
    const route = {
        request: () => ({ url: () => `http://localhost/api/v1${path}`, method: () => "GET" }),
        fulfill: async value => { result = value; },
    };
    await withDisplayData(async proxied => {
        requested = proxied.request().url();
        await proxied.fulfill({ json: body, status });
    })(route);
    return { result, requested };
}

test("display fixtures retain global crop totals while filtering and paging rows", async () => {
    const rows = Array.from({ length: 85 }, (_, id) => ({ id, name: `Crop ${id}`, status: "Growing", field: "Field A" }));
    const { result, requested } = await fulfill("/display/crops?offset=50&limit=50", rows);
    assert.ok(requested.includes("/crops/details?"));
    assert.equal(result.json.items.length, 35);
    assert.equal(result.json.items[0].id, 50);
    assert.equal(result.json.overview.total, 85);
    const match = await fulfill("/display/crops?search=Crop%2084", rows);
    assert.equal(match.result.json.total, 1);
});

test("display fixture adapter never changes a server error to successful empty data", async () => {
    const { result } = await fulfill("/display/crops?limit=50", { detail: "Failed query" }, 503);
    assert.equal(result.status, 503);
    assert.deepEqual(result.json, { detail: "Failed query" });
});

test("display fixture adapter leaves unrelated API responses unchanged", async () => {
    const { result, requested } = await fulfill("/auth/me", { full_name: "Test account" });
    assert.equal(requested, "http://localhost/api/v1/auth/me");
    assert.deepEqual(result.json, { full_name: "Test account" });
});
