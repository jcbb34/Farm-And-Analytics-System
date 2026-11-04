import assert from "node:assert/strict";
import test from "node:test";
import { authService } from "../src/services/authService.js";
import { userService } from "../src/services/userService.js";
import { invalidateReadCache } from "../src/services/httpClient.js";

const original = Object.fromEntries(["window", "fetch", "sessionStorage", "localStorage"].map((key) => [key, globalThis[key]]));
const details = { first_name: "Casey Ana", middle_name: "Reyes", surname: "De la Cruz", suffix: "Jr.", address: { street: "12 Sample Street", subdivision: "Sample Village", province: "Custom Province", city: "Custom City", barangay: "Custom Barangay", postal_code: "0450" } };
const record = { id: 77, user_code: "USR-TEST", full_name: "Casey Ana Reyes De la Cruz Jr.", username: "casey.admin", email: "casey@example.com", contact_number: "09123456789", position: "Farm Administrator", role: { name: "System Administrator" }, status: "Active", permissions: ["*"], personal_details: details, two_factor_enabled: true };

test.beforeEach(() => {
    invalidateReadCache();
    globalThis.window = { location: { origin: "http://farm.local:3000" }, setTimeout, clearTimeout };
    globalThis.localStorage = globalThis.sessionStorage = { getItem: () => null };
});
test.after(() => Object.assign(globalThis, original));

test("Account and User Management return the same complete saved profile", async () => {
    globalThis.fetch = async (url) => Response.json(new URL(url).pathname.endsWith("/users") ? [record] : record);
    const account = await authService.getCurrentUser();
    const [managed] = await userService.getUsers();
    assert.deepEqual(account, managed);
    assert.deepEqual(account.personalDetails, details);
    assert.equal(account.personalDetails.address.postal_code, "0450");
    assert.equal(account.twoFactorEnabled, true);
});

test("sign-in preserves the same structured details as User Management", async () => {
    globalThis.fetch = async () => Response.json({ access_token: "synthetic-test-token", expires_in: 3600, user: record });
    const result = await authService.login({ username: record.username, password: "Synthetic-Test-Password" });
    assert.deepEqual(result.user.personalDetails, details);
    assert.equal(result.user.fullName, record.full_name);
});

test("legacy names remain intact and cleared optional details do not reappear", async () => {
    globalThis.fetch = async () => Response.json({ ...record, personal_details: null, full_name: "Maria del Carmen de la Cruz", email: null, contact_number: null, position: null });
    const account = await authService.getCurrentUser();
    assert.equal(account.fullName, "Maria del Carmen de la Cruz");
    assert.equal(account.personalDetails, null);
    assert.equal(account.email, "");
    assert.equal(account.contactNumber, "");
    assert.equal(account.position, "");
});
