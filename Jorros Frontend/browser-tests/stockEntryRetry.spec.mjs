import { serveSessionPolicy } from './helpers/serveSessionPolicy.mjs';
import { test, expect } from "@playwright/test";

const today = "2026-10-31";
const user = { id: 1, username: "retry.test", fullName: "Retry Tester", role: "System Administrator", permissions: ["*"], status: "Active" };
const animal = {
    id: 1, animal_code: "RETRY-ANIMAL", record_name: "Test laying flock", animal_type: "Chicken", breed: "Test breed",
    record_type: "Batch", lifecycle_status: "Active", quantity: 10, sex: "Female", female_quantity: 10, male_quantity: 0,
    unknown_sex_quantity: 0, healthy_quantity: 10, at_risk_quantity: 0, sick_quantity: 0, under_treatment_quantity: 0,
    health_status: "Healthy", growth_status: "Production", production_purpose: "Egg Production", is_archived: false,
    date_of_birth: "2026-01-01", date_acquired: "2026-01-02", pen_location: "Test pen", weight_kg: 1,
    vaccination_status: "Not Vaccinated", daily_feed_kg: 0, growth_records: [], vaccination_records: [], feeding_records: [],
};

async function setup(page, { holdFirst = false } = {}) {
    const writes = [], saved = new Map();
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await page.clock.install({ time: new Date(`${today}T04:00:00Z`) });
    await page.addInitScript((profile) => sessionStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-retry-token", user: profile, expiresAt: Date.now() + 86400000 })), user);
    await page.route("**/api/v1/**", async (route) => {
        if (await serveSessionPolicy(route, page)) return;
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (request.method() === "POST" && (path.endsWith("/production") || path.endsWith("/vaccination-records"))) {
            const key = request.headers()["idempotency-key"], payload = request.postDataJSON();
            writes.push({ path, key, payload });
            if (!saved.has(key)) saved.set(key, { id: saved.size + 1, ...payload });
            if (writes.length === 1) {
                if (holdFirst) await gate;
                return route.fulfill({ status: 503, json: { detail: "Test response lost after commit. Retry this entry." } });
            }
            return route.fulfill({ json: saved.get(key) });
        }
        if (path === "/api/v1/livestock") return route.fulfill({ json: [animal] });
        if (path === "/api/v1/livestock/1") return route.fulfill({ json: animal });
        if (path.endsWith("/growth-assessment")) return route.fulfill({ json: { current_stage: "Production", profile_status: "No matching profile" } });
        if (path.endsWith("/inventory")) return route.fulfill({ json: [{ id: 7, item_code: "TEST-VAX", name: "Synthetic Test Vaccine", category: "Vaccine", quantity: 100, unit: "test-units", is_archived: false }] });
        if (path.endsWith("/overview")) return route.fulfill({ json: {} });
        return route.fulfill({ json: [] });
    });
    return { writes, saved, release };
}

async function openProduction(page) {
    await page.goto("/production-sales");
    await page.getByRole("group", { name: "Production source filter" }).getByRole("button", { name: "Livestock", exact: true }).click();
    await page.getByRole("button", { name: "Production", exact: true }).click();
    await page.getByRole("button", { name: /Record Production/ }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("combobox", { name: "Livestock", exact: true }).selectOption("1");
    await dialog.getByLabel("Active Laying Females").fill("10");
    await dialog.getByLabel("Gross Production").fill("5");
    expect(await dialog.locator("form").evaluate((form) => form.checkValidity())).toBe(true);
    return dialog;
}

test("production response failure retains the form and reuses one key on retry", async ({ page }) => {
    const state = await setup(page);
    const dialog = await openProduction(page);
    await dialog.getByRole("button", { name: "Record Production", exact: true }).click();
    await expect(page.getByText("Test response lost after commit. Retry this entry.", { exact: true })).toBeVisible();
    await expect(dialog.getByLabel("Gross Production")).toHaveValue("5");
    await dialog.getByRole("button", { name: "Record Production", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(state.writes).toHaveLength(2);
    expect(state.writes[0].key).toBeTruthy();
    expect(state.writes[0].key).toBe(state.writes[1].key);
    expect(state.saved.size).toBe(1);
});

test("a pending production save disables submission and cancel", async ({ page }) => {
    const state = await setup(page, { holdFirst: true });
    const dialog = await openProduction(page);
    await dialog.getByRole("button", { name: "Record Production", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Saving...", exact: true })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toBeVisible();
    expect(state.writes).toHaveLength(1);
    state.release();
    await expect(dialog.getByRole("button", { name: "Record Production", exact: true })).toBeEnabled();
});

test("vaccination failure keeps entered values and retries without a new stock command", async ({ page }) => {
    const state = await setup(page);
    await page.goto("/livestock");
    await page.getByTitle("View livestock details", { exact: true }).click();
    const dialog = page.locator(".livestock-details-modal");
    await dialog.getByRole("button", { name: /Vaccination/, exact: false }).first().click();
    await dialog.getByRole("button", { name: /Add Vaccination/ }).click();
    await dialog.getByLabel("Vaccine Inventory", { exact: false }).selectOption("7");
    await dialog.getByLabel("Inventory Quantity Used").fill("2");
    await dialog.getByLabel("Date Administered", { exact: false }).fill(today);
    await dialog.getByRole("button", { name: "Save Vaccination", exact: true }).click();
    await expect(page.getByText("Test response lost after commit. Retry this entry.", { exact: true })).toBeVisible();
    await expect(dialog.getByLabel("Inventory Quantity Used")).toHaveValue("2");
    await page.clock.fastForward(1000);
    await dialog.getByRole("button", { name: "Save Vaccination", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Save Vaccination", exact: true })).toHaveCount(0);
    expect(state.writes).toHaveLength(2);
    expect(state.writes[0].key).toBeTruthy();
    expect(state.writes[0].key).toBe(state.writes[1].key);
    expect(state.saved.size).toBe(1);
});
