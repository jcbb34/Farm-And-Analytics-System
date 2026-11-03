import test from "node:test";
import assert from "node:assert/strict";
import { composeFullName, emptyPersonalDetails, personalDetailsPayload, validatePersonalDetails } from "../src/components/PersonalDetails/personalDetails.js";
import { userService } from "../src/services/userService.js";
import { voidAuthorizationService } from "../src/services/voidAuthorizationService.js";
import { invalidateReadCache } from "../src/services/httpClient.js";

const original = Object.fromEntries(["window", "fetch", "sessionStorage", "localStorage"].map((key) => [key, globalThis[key]]));
test.beforeEach(() => {
    invalidateReadCache();
    globalThis.window = { location: { origin: "http://farm.local:3000" }, setTimeout, clearTimeout };
    globalThis.localStorage = globalThis.sessionStorage = { getItem: () => null, setItem: () => { throw new Error("Credentials must not be persisted"); } };
});
test.after(() => Object.assign(globalThis, original));
const details = { first_name: "María Ana", middle_name: "Reyes", surname: "De la Cruz", suffix: "Jr.", address: { province: "Custom Province", city: "Custom City", barangay: "Custom Barangay", postal_code: "0450" } };

test("compound names and optional fields form one display name without guessing legacy names", () => {
    assert.equal(composeFullName(details), "María Ana Reyes De la Cruz Jr.");
    assert.equal(composeFullName(null, "Maria del Carmen de la Cruz"), "Maria del Carmen de la Cruz");
    assert.equal(validatePersonalDetails(details, true), "");
    assert.match(validatePersonalDetails(emptyPersonalDetails(), true), /first name and surname/);
    assert.equal(validatePersonalDetails(null, false), "");
    assert.match(validatePersonalDetails({ ...details, address: { ...details.address, postal_code: "450" } }), /four-digit/);
});
test("custom address codes stay absent and leading zero ZIP codes survive", () => {
    const result = personalDetailsPayload({ ...details, middle_name: "   ", suffix: "", address: { ...details.address, barangay_code: null } });
    assert.equal(result.middle_name, null);
    assert.equal(result.suffix, null);
    assert.equal(result.address.barangay_code, null);
    assert.equal(result.address.postal_code, "0450");
});
test("user creation sends structured details and normalizes the saved response", async () => {
    let request;
    globalThis.fetch = async (url, options) => { request = { url, options }; return Response.json({ id: 77, full_name: composeFullName(details), personal_details: details }); };
    const result = await userService.createUser({ fullName: composeFullName(details), personalDetails: details, username: "sample.user", role: "Employee", password: "Synthetic-Test-Password" });
    assert.deepEqual(JSON.parse(request.options.body).personal_details, personalDetailsPayload(details));
    assert.deepEqual(result.personalDetails, details);
});
test("void authorization sends one scoped request without replacing the employee session", async () => {
    const calls = [];
    globalThis.fetch = async (url, options) => { calls.push({ url, options }); return Response.json(url.includes("/preview") ? { preview_token: "synthetic-scoped-preview", requires_owner_credentials: true } : { status: "Voided" }); };
    const preview = await voidAuthorizationService.preview("task", 42);
    const data = { preview_token: preview.preview_token, reason: "Wrong entry", owner_username: "test.owner", owner_password: "Synthetic-Test-Password" };
    await voidAuthorizationService.authorize(data);
    assert.equal(new URL(calls[0].url).searchParams.get("record_id"), "42");
    assert.equal(new URL(calls[1].url).pathname, "/api/v1/void-authorizations");
    assert.deepEqual(JSON.parse(calls[1].options.body), data);
    assert.equal(calls.length, 2);
});
