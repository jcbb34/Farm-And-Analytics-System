import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { invalidateReadCache } from "../src/services/httpClient.js";

const catalogue = JSON.parse(readFileSync(new URL("../public/reference-data/philippine_locations.2026-Q3.json", import.meta.url), "utf8"));
const original = Object.fromEntries(["window", "fetch", "sessionStorage", "localStorage"].map((key) => [key, globalThis[key]]));
let sequence = 0;
const service = () => import(`../src/services/locationReferenceService.js?test=${sequence++}`);

test.beforeEach(() => {
    invalidateReadCache();
    globalThis.window = { location: { origin: "http://farm.local:3000" }, setTimeout, clearTimeout };
    globalThis.sessionStorage = { getItem: () => JSON.stringify({ accessToken: "synthetic-location-token" }) };
    globalThis.localStorage = { getItem: () => null };
});
test.after(() => Object.assign(globalThis, original));

test("bundled suggestions work without the reference API and contain no personal data requests", async () => {
    const calls = [];
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options });
        if (String(url).includes("/api/")) throw new Error("Reference API unavailable");
        return Response.json(catalogue);
    };
    const { getLocationChoices, LOCATION_CATALOGUE_PATH } = await service();
    const provinces = await getLocationChoices("provinces");
    assert.equal(provinces.length, 84);
    assert.ok(provinces.some((row) => row.name === "Albay"));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, LOCATION_CATALOGUE_PATH);
    assert.equal(calls[0].options.credentials, "omit");
    assert.equal(calls[0].options.headers?.Authorization, undefined);
});

test("the complete bundled hierarchy filters by parent and preserves accented names", async () => {
    globalThis.fetch = async () => Response.json(catalogue);
    const { getLocationChoices } = await service();
    const albay = (await getLocationChoices("provinces")).find((row) => row.name === "Albay");
    const cities = await getLocationChoices("cities", albay.code);
    const legazpi = cities.find((row) => row.name.includes("Legazpi"));
    assert.ok(legazpi);
    assert.ok(!cities.some((row) => row.name === "Peñablanca"));
    assert.ok((await getLocationChoices("barangays", legazpi.code)).some((row) => row.name.includes("Gogon")));
    assert.ok((await getLocationChoices("cities", "0201500000")).some((row) => row.name === "Peñablanca"));
});

test("simultaneous forms share one successful bundled download", async () => {
    let calls = 0;
    globalThis.fetch = async () => { calls += 1; return Response.json(catalogue); };
    const { getLocationChoices } = await service();
    const [first, second] = await Promise.all([getLocationChoices("provinces"), getLocationChoices("provinces")]);
    assert.deepEqual(first, second);
    await getLocationChoices("cities", "0201500000");
    assert.equal(calls, 1);
});

test("a missing public file falls back to the compatible authenticated API", async () => {
    const calls = [];
    globalThis.fetch = async (url, options) => {
        calls.push({ url, options });
        return String(url).startsWith("/reference-data/")
            ? new Response("Missing", { status: 404 })
            : Response.json({ items: [{ code: "0201519000", name: "Peñablanca" }] });
    };
    const { getLocationChoices } = await service();
    assert.deepEqual(await getLocationChoices("cities", "0201500000"), [{ code: "0201519000", name: "Peñablanca" }]);
    const api = calls.find((call) => String(call.url).includes("/api/"));
    assert.equal(new URL(api.url).pathname, "/api/v1/reference/locations");
    assert.equal(new URL(api.url).searchParams.get("parent_code"), "0201500000");
    assert.equal(api.options.headers.Authorization, "Bearer synthetic-location-token");
});

test("a failed download can recover on retry instead of caching the failure", async () => {
    let unavailable = true;
    globalThis.fetch = async (url) => unavailable
        ? Response.json({ detail: "Synthetic reference failure" }, { status: 503 })
        : String(url).startsWith("/reference-data/") ? Response.json(catalogue) : new Response(null, { status: 503 });
    const { getLocationChoices } = await service();
    await assert.rejects(getLocationChoices("provinces"), { status: 503 });
    unavailable = false;
    assert.equal((await getLocationChoices("provinces")).length, 84);
});

test("an HTML page in place of the bundled JSON cannot turn into empty successful suggestions", async () => {
    globalThis.fetch = async (url) => String(url).startsWith("/reference-data/")
        ? new Response("<html>Wrong deployment path</html>", { headers: { "Content-Type": "text/html" } })
        : Response.json({ items: [{ code: "0201500000", name: "Cagayan" }] });
    const { getLocationChoices } = await service();
    assert.deepEqual(await getLocationChoices("provinces"), [{ code: "0201500000", name: "Cagayan" }]);
});
