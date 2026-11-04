import { test, expect } from "@playwright/test";

const today = "2026-10-31";
const user = { id: 1, username: "recovery.test", fullName: "Recovery Tester", role: "System Administrator", permissions: ["*"], status: "Active" };
const crop = {
    id: 1, crop_code: "RECOVERY-CROP", name: "Eggplant", variety: "Test variety", field: "Field A", area_hectares: 1,
    planting_date: "2026-10-01", estimated_harvest: "2026-11-26", current_growth: 50, estimated_progress: 50,
    growth_stage: "Flowering", quantity_planted: 100, current_surviving: 100, status: "Growing", is_archived: false,
    watering_schedule: "Not specified", growth_records: [], yield_records: [], pest_diseases: [],
};

async function setup(page, { holdFirst = false } = {}) {
    const writes = [], saved = new Map(), downloads = [];
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await page.clock.install({ time: new Date(`${today}T04:00:00Z`) });
    await page.addInitScript((profile) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-recovery-token", user: profile, expiresAt: Date.now() + 86400000 })), user);
    await page.route("**/api/v1/**", async (route) => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path === "/api/v1/resource-usages" && request.method() === "POST") {
            const key = request.headers()["idempotency-key"], payload = request.postDataJSON();
            writes.push({ key, payload });
            if (!saved.has(key)) saved.set(key, { id: saved.size + 1, ...payload, unit: "kg", inventory_item_name: "Synthetic Fertilizer" });
            if (writes.length === 1) {
                if (holdFirst) await gate;
                return route.fulfill({ status: 503, json: { detail: "Test response lost after commit. Retry this usage." } });
            }
            return route.fulfill({ status: 201, json: saved.get(key) });
        }
        if (path === "/api/v1/resource-usages") return route.fulfill({ json: [...saved.values()] });
        if (path === "/api/v1/inventory") return route.fulfill({ json: [{ id: 7, item_code: "TEST-FERT", name: "Synthetic Fertilizer", category: "Fertilizer", quantity: 100 - saved.size * 2, unit: "kg", is_archived: false }] });
        if (["/api/v1/crops", "/api/v1/crops/details"].includes(path)) return route.fulfill({ json: [crop] });
        if (path === "/api/v1/crops/1") return route.fulfill({ json: crop });
        if (path === "/api/v1/backup-recovery/overview") return route.fulfill({ json: {
            options: { format: "zip", destination: "local", encrypted: false, hour: 2, minute: 0, frequency: "daily", timezone: "Asia/Manila", reminder_days: 7, retain_count: 10 },
            sets: [
                { id: "BKP-RECOVERY", created_at: `${today}T08:00:00Z`, status: "Completed", format: "zip", legacy: true, protected: true, file_validated: true, artifacts: { zip: { name: "BKP-RECOVERY.recovery.zip", size: 234, encrypted: false } } },
                { id: "BKP-LEGACY", created_at: `${today}T07:00:00Z`, status: "Completed", format: "json", legacy: true, protected: true, file_validated: false, artifacts: { json: { name: "BKP-LEGACY.json", size: 120, encrypted: false } } },
            ], jobs: [], drills: [], rollbacks: [], audit: [], drive: {}, readiness: {}, storage: {},
        } });
        if (path === "/api/v1/backup-recovery/notices") return route.fulfill({ json: [] });
        if (path === "/api/v1/backup-recovery/backups/BKP-RECOVERY/download/zip" || path === "/api/v1/backup-recovery/backups/BKP-LEGACY/download/json") { downloads.push(path); return route.fulfill({ contentType: "application/octet-stream", body: Buffer.from([80, 75, 3, 4, 0, 255]) }); }

        if (path === "/api/v1/backups") return route.fulfill({ json: [
            { id: 1, backup_code: "BKP-RECOVERY", filename: "BKP-RECOVERY.json", status: "Completed", recovery_available: true, recovery_file_size_bytes: 234, file_size_bytes: 123, created_at: `${today}T08:00:00` },
            { id: 2, backup_code: "BKP-LEGACY", filename: "BKP-LEGACY.json", status: "Completed", file_size_bytes: 120, created_at: `${today}T07:00:00` },
        ] });
        if (path === "/api/v1/backups/1/recovery-package") {
            downloads.push(path);
            return route.fulfill({ contentType: "application/zip", body: Buffer.from([80, 75, 3, 4, 0, 255]) });
        }
        if (path === "/api/v1/backups/2/content") {
            downloads.push(path);
            return route.fulfill({ json: { format_version: "1.0", tables: {} } });
        }
        return route.fulfill({ json: [] });
    });
    return { writes, saved, release, downloads };
}

async function openUsage(page) {
    await page.goto("/crops");
    await page.getByTitle("View crop", { exact: true }).click();
    const panel = page.locator(".resource-usage-panel");
    await panel.getByRole("button", { name: "Record Usage", exact: false }).click();
    await panel.getByLabel("Inventory Item", { exact: true }).selectOption("7");
    await panel.getByLabel("Quantity Used", { exact: true }).fill("2");
    return panel;
}

test("manual usage keeps failed entries and reuses one stock command", async ({ page }) => {
    const state = await setup(page), panel = await openUsage(page);
    await panel.getByRole("button", { name: "Save Usage", exact: false }).click();
    await expect(page.getByText("Test response lost after commit. Retry this usage.", { exact: true })).toBeVisible();
    await expect(panel.getByLabel("Quantity Used", { exact: true })).toHaveValue("2");
    await page.clock.fastForward(1000);
    await panel.getByRole("button", { name: "Save Usage", exact: false }).click();
    await expect(panel.getByLabel("Quantity Used", { exact: true })).toHaveCount(0);
    expect(state.writes).toHaveLength(2);
    expect(state.writes[0].key).toBeTruthy();
    expect(state.writes[0].key).toBe(state.writes[1].key);
    expect(state.saved.size).toBe(1);
});

test("manual usage prevents another submission while saving", async ({ page }) => {
    const state = await setup(page, { holdFirst: true }), panel = await openUsage(page);
    await panel.getByRole("button", { name: "Save Usage", exact: false }).click();
    await expect(panel.getByRole("button", { name: "Saving...", exact: false })).toBeDisabled();
    await expect(panel.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    expect(state.writes).toHaveLength(1);
    state.release();
    await expect(panel.getByRole("button", { name: "Save Usage", exact: false })).toBeEnabled();
});

for (const [code, filename, path, action] of [
    ["BKP-RECOVERY", "BKP-RECOVERY.recovery.zip", "/api/v1/backup-recovery/backups/BKP-RECOVERY/download/zip", "Download ZIP"],
    ["BKP-LEGACY", "BKP-LEGACY.json", "/api/v1/backup-recovery/backups/BKP-LEGACY/download/json", "Download Legacy JSON"],
]) {
    test(`System Data downloads ${code} in its supported format`, async ({ page }) => {
        const state = await setup(page);
        await page.goto("/settings?section=data");
        const row = page.getByRole("row").filter({ hasText: code });
        await row.getByText("Files & Actions", { exact: true }).click();
        const pending = page.waitForEvent("download");
        await row.getByRole("button", { name: action, exact: true }).click();
        const downloaded = await pending;
        expect(downloaded.suggestedFilename()).toBe(filename);
        expect(await downloaded.failure()).toBeNull();
        expect(state.downloads).toEqual([path]);
    });
}
