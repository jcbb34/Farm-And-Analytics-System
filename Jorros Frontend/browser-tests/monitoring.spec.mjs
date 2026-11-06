import { serveSessionPolicy } from './helpers/serveSessionPolicy.mjs';
import { test, expect } from "@playwright/test";

const today = "2026-10-29";
const employee = { id: 1, employee_code: "MON-EMP", full_name: "Monitoring Employee", employment_status: "Active", is_archived: false, assigned_area: "Field A" };
const crop = {
    id: 1, crop_code: "MON-CROP", name: "Eggplant", variety: "Test variety", field: "Field A", area_hectares: 1,
    planting_date: "2026-10-01", estimated_harvest: "2026-11-26", current_growth: 50, estimated_progress: 50,
    growth_stage: "Flowering", observed_growth_stage: "Flowering", last_observation_date: "2026-10-20",
    quantity_planted: 100, current_surviving: 93, status: "Growing", is_archived: false,
    watering_schedule: "Not specified", assigned_employee_id: 1, monitoring_enabled: true, monitoring_frequency_days: null,
    monitoring_start_date: "2026-10-01", monitoring_end_date: "2026-11-30",
    monitoring_summary: { state: "Scheduled", last_date: "2026-10-20", next_date: today, interval_days: 3 },
    growth_records: [
        { id: 1, update_date: "2026-10-10", growth_percentage: 16.1, growth_stage: "Germination", observed_stage: "Seedling", current_surviving: 96 },
        { id: 2, update_date: "2026-10-20", growth_percentage: 33.9, growth_stage: "Seedling", observed_stage: "Flowering", current_surviving: 93 },
    ], yield_records: [], pest_diseases: [],
};
const animal = {
    id: 1, animal_code: "MON-PIG", record_name: "Monitoring Group", animal_type: "Pig", breed: "Test breed",
    record_type: "Batch", lifecycle_status: "Active", quantity: 10, sex: "Mixed", male_quantity: 5, female_quantity: 5,
    unknown_sex_quantity: 0, date_of_birth: "2026-08-01", date_acquired: "2026-10-01", weight_kg: 20,
    min_weight_kg: 18, max_weight_kg: 22, pen_id: 1, pen_location: "Pen A", health_status: "Healthy", healthy_quantity: 10,
    at_risk_quantity: 0, sick_quantity: 0, under_treatment_quantity: 0, growth_status: "Growing", production_purpose: "Growing",
    vaccination_status: "Not Vaccinated", daily_feed_kg: 0, is_archived: false, assigned_employee_id: 1,
    monitoring_enabled: true, monitoring_start_date: today, monitoring_frequency_days: 5,
    monitoring_summary: { state: "Scheduled", last_date: "2026-10-20", next_date: today, interval_days: 5 },
    growth_records: [
        { id: 1, measurement_date: "2026-10-10", weight_kg: 18, min_weight_kg: 16, max_weight_kg: 20, animals_measured: 4, measurement_basis: "Sample" },
        { id: 2, measurement_date: "2026-10-20", weight_kg: 20, min_weight_kg: 18, max_weight_kg: 22, animals_measured: 4, measurement_basis: "Sample" },
    ], vaccination_records: [], feeding_records: [],
};

function monitoringTask(module, reviewing = false) {
    const context = { resource_type: module, earliest_date: today, latest_date: today, quantity: module === "Crop" ? 100 : 10,
        stage_choices: module === "Crop" ? ["Seeded", "Seedling", "Vegetative", "Flowering", "Fruiting", "Maturity", "Harvest Ready"] : ["Newborn", "Growing", "Mature", "Breeding", "Production"], current_stage: "Growing" };
    const observation = module === "Crop"
        ? { resource_type: module, observation_date: today, observed_stage: "Harvest Ready", current_surviving: 93 }
        : { resource_type: module, observation_date: today, observed_stage: "Mature", animals_measured: 4, average_weight_kg: 30, min_weight_kg: 25, max_weight_kg: 35 };
    return { id: 1, activity_code: "MON-TASK", name: `Monitor ${module}`, category: "Farm Inspection", related_to: "Test resource", location: "Test farm",
        description: "Submit a monitoring observation", activity_date: today, start_time: "08:00:00", assigned_by: "System",
        assigned_to: employee.full_name, employee_name: employee.full_name, assigned_employee_id: 1, status: reviewing ? "Submitted for Review" : "In Progress",
        priority: "Medium", source_module: module, source_type: `${module.toLowerCase()}_growth_check`, source_record_id: 1,
        requires_review: true, requires_evidence: true, resource_required: false, needs_reassignment: false, is_archived: false, is_automatic: true,
        monitoring_context: context, latest_submission: reviewing ? { id: 7, employee_id: 1, employee_name: employee.full_name, attempt_number: 1,
            review_status: "Submitted", monitoring: observation, worker_notes: "Observed during monitoring", submitted_at: "2026-10-29T09:00:00" } : null };
}

async function setup(page, { module = "Crop", reviewing = false, worker = false, monitoringEnabled, ignoreMonitoring = false, holdLivestockSave = false, unknownBirth = false } = {}) {
    let releaseLivestockSave;
    const livestockGate = holdLivestockSave ? new Promise((resolve) => { releaseLivestockSave = resolve; }) : null;
    let savedAnimal = { ...animal, ...(monitoringEnabled === false ? { monitoring_enabled: false, monitoring_start_date: null, monitoring_end_date: null, monitoring_frequency_days: null } : {}) };
    if (unknownBirth) savedAnimal = { ...savedAnimal, date_of_birth: null, age_is_estimated: true,
        estimated_age_days: 100, estimated_age_as_of_date: today, estimated_age_confidence: "Medium", estimated_age_source: "Supplier estimate" };
    const task = monitoringTask(module, reviewing);
    const writes = [];
    const user = { id: 1, username: "monitoring.test", fullName: employee.full_name, role: worker ? "Employee" : "System Administrator", permissions: worker ? ["workforce:submit"] : ["*"], status: "Active" };
    await page.clock.install({ time: new Date("2026-10-29T04:00:00Z") });
    await page.addInitScript((profile) => sessionStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "monitoring-browser-test-token", user: profile, expiresAt: Date.now() + 86400000 })), user);
    await page.route("**/api/v1/**", async (route) => {
        if (await serveSessionPolicy(route, page)) return;
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path.endsWith("/evidence") && request.method() === "POST") return route.fulfill({ status: 201, json: { evidence_id: "11111111111111111111111111111111", evidence_url: "/api/v1/workforce/evidence/11111111111111111111111111111111", file_name: "inspection.png" } });
        if (["POST", "PUT"].includes(request.method())) {
            writes.push({ path, payload: request.postDataJSON() });
            if (path.endsWith("/submit")) return route.fulfill({ json: { ...task, status: "Submitted for Review" } });
            if (path.endsWith("/review")) return route.fulfill({ json: { ...task, status: "Completed" } });
            if (path === "/api/v1/livestock/1" && request.method() === "PUT") {
                if (livestockGate) await livestockGate;
                const payload = request.postDataJSON();
                const accepted = ignoreMonitoring ? Object.fromEntries(Object.entries(payload).filter(([key]) => !key.startsWith("monitoring_"))) : payload;
                savedAnimal = { ...savedAnimal, ...accepted };
                return route.fulfill({ json: savedAnimal });
            }
            return route.fulfill({ json: path.includes("/crops") ? { ...crop, ...request.postDataJSON() } : { ...animal, ...request.postDataJSON() } });
        }
        if (path === "/api/v1/crops" || path === "/api/v1/crops/details") return route.fulfill({ json: [crop] });
        if (path === "/api/v1/crops/1") return route.fulfill({ json: crop });
        if (path === "/api/v1/livestock") return route.fulfill({ json: [savedAnimal] });
        if (path === "/api/v1/livestock/pens") return route.fulfill({ json: [{ id: 1, name: "Pen A", animal_type: "Pig", purpose: "General", capacity: 100, current_quantity: 10, status: "Active", is_archived: false }] });
        if (path === "/api/v1/livestock/1") return route.fulfill({ json: savedAnimal });
        if (path.endsWith("/growth-assessment")) return route.fulfill({ json: { current_stage: "Growing", suggested_stage: "Mature", profile_status: "No matching profile" } });
        if (path.endsWith("/employees")) return route.fulfill({ json: [employee] });
        if (path.endsWith("/my-schedule")) return route.fulfill({ json: { availability: [], attendance: [], leave: [], shifts: [], tasks: [] } });
        if (path.endsWith("/page")) return route.fulfill({ json: { items: [task], total: 1, offset: 0, limit: 20 } });
        if (path.endsWith("/summary")) return route.fulfill({ json: {} });
        if (path.endsWith("/review-report")) return route.fulfill({ json: { task, current_submission: task.latest_submission, previous_submissions: [], evidence: [], resource_usage: { tracked: false, movements: [] } } });
        if (path === "/api/v1/workforce/tasks/1") return route.fulfill({ json: task });
        return route.fulfill({ json: [] });
    });
    return { task, writes, releaseLivestockSave };
}

async function upload(page, scope) {
    const bytes = await page.evaluate(() => { const canvas = document.createElement("canvas"); canvas.width = canvas.height = 100; canvas.getContext("2d").fillRect(0, 0, 100, 100); return canvas.toDataURL("image/png").split(",")[1]; });
    await scope.getByLabel("Upload evidence photo").setInputFiles({ name: "inspection.png", mimeType: "image/png", buffer: Buffer.from(bytes, "base64") });
    await expect(scope.getByText(/Photo uploaded|uploaded successfully|Ready to submit|inspection.png/i).first()).toBeVisible();
}

test("crop list separates estimates and observations, and history supports date ranges", async ({ page }) => {
    await setup(page);
    await page.goto("/crops");
    await expect(page.getByText("Observed: Flowering", { exact: true })).toBeVisible();
    await expect(page.getByText("50% estimated", { exact: true })).toBeVisible();
    await page.getByTitle("View crop", { exact: true }).click();
    const filter = page.locator(".monitoring-history-filter");
    await expect(filter.getByRole("status")).toHaveText("2 records");
    await filter.getByLabel("History from").fill("2026-10-15");
    await filter.getByLabel("History to").fill("2026-10-20");
    await expect(filter.getByRole("status")).toHaveText("1 record");
    await filter.getByRole("button", { name: "Clear dates" }).click();
    await expect(filter.getByRole("status")).toHaveText("2 records");
    if (process.env.MONITORING_QA_DIR) await page.screenshot({ path: `${process.env.MONITORING_QA_DIR}/crop-history.png` });
});

test("livestock edit has one-time assignment and monitoring schedule controls", async ({ page }) => {
    const { writes } = await setup(page, { module: "Livestock" });
    await page.goto("/livestock");
    await page.getByTitle("Edit livestock", { exact: true }).click();
    const panel = page.locator('[aria-label="Livestock monitoring schedule"]');
    await expect(page.getByLabel("Assigned Employee", { exact: true })).toHaveValue("1");
    await expect(panel.getByLabel("Enable recurring monitoring")).toBeChecked();
    await panel.getByLabel("Repeat every (days)", { exact: false }).fill("4");
    await panel.getByLabel("Monitoring end date", { exact: false }).fill("2026-11-30");
    if (process.env.MONITORING_QA_DIR) await page.screenshot({ path: `${process.env.MONITORING_QA_DIR}/livestock-monitoring-settings.png` });
    await page.getByRole("button", { name: /Save Changes/ }).click();
    await expect.poll(() => writes.filter((item) => item.path === "/api/v1/livestock/1").length).toBe(1);
    const payload = writes.find((item) => item.path === "/api/v1/livestock/1").payload;
    expect(payload.monitoring_frequency_days).toBe(4);
    expect(payload.monitoring_end_date).toBe("2026-11-30");
    expect(payload.assigned_employee_id).toBe(1);
    await expect(page.locator(".add-livestock-modal")).toHaveCount(0);
    expect(writes.filter((entry) => entry.path === "/api/v1/audit-logs")).toHaveLength(0);
});

test("livestock pending metadata save disables form edits and dismissal consistently", async ({ page }) => {
    const state = await setup(page, { module: "Livestock", holdLivestockSave: true });
    await page.goto("/livestock");
    await page.getByTitle("Edit livestock", { exact: true }).click();
    const modal = page.locator(".add-livestock-modal");
    await modal.getByRole("button", { name: /Save Changes/ }).click();
    await expect(modal.getByRole("button", { name: /Saving/ })).toBeDisabled();
    await expect(modal.locator("#livestockRecordName")).toBeDisabled();
    await expect(modal.getByRole("button", { name: "Close livestock form" })).toBeDisabled();
    await expect(modal.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    await modal.locator("form").evaluate((form) => form.requestSubmit());
    expect(state.writes.filter((entry) => entry.path === "/api/v1/livestock/1")).toHaveLength(1);
    state.releaseLivestockSave();
    await expect(modal).toHaveCount(0);
    expect(state.writes.filter((entry) => entry.path === "/api/v1/audit-logs")).toHaveLength(0);
});

test("estimated-age livestock edit preserves the nullable birth date and its provenance", async ({ page }) => {
    const state = await setup(page, { module: "Livestock", unknownBirth: true });
    await page.goto("/livestock");
    await page.getByTitle("Edit livestock", { exact: true }).click();
    const modal = page.locator(".add-livestock-modal");
    await expect(modal.locator("#livestockBirthDate")).toHaveValue("");
    await expect(modal.locator("#livestockEstimatedAgeDays")).toHaveValue("100");
    await modal.locator("#livestockRecordName").fill("Renamed estimated-age batch");
    await modal.getByRole("button", { name: /Save Changes/ }).click();
    await expect(modal).toHaveCount(0);
    const write = state.writes.find((entry) => entry.path === "/api/v1/livestock/1");
    expect(write.payload).toMatchObject({ date_of_birth: null, estimated_age_days: 100,
        estimated_age_as_of_date: today, estimated_age_confidence: "Medium", estimated_age_source: "Supplier estimate" });
    expect(state.writes.filter((entry) => entry.path === "/api/v1/audit-logs")).toHaveLength(0);
});

for (const module of ["Crop", "Livestock"]) {
    test(`employee submits structured ${module} monitoring with evidence`, async ({ page }) => {
        const { writes } = await setup(page, { module, worker: true });
        await page.goto("/my-tasks");
        await page.getByRole("button", { name: "Submit Work", exact: true }).click();
        const form = page.locator(".my-task-submit-modal");
        const panel = page.locator(".monitoring-observation");
        await expect(panel.getByLabel("Observation date", { exact: false })).toHaveValue(today);
        if (module === "Crop") {
            await panel.getByLabel("Observed stage", { exact: false }).selectOption("Flowering");
            await panel.getByLabel("Surviving plants", { exact: false }).fill("93");
        } else {
            await panel.getByLabel("Animals measured", { exact: false }).fill("4");
            await panel.getByLabel("Average weight (kg)", { exact: false }).fill("30");
            await panel.getByLabel("Minimum measured weight (kg)").fill("25");
            await panel.getByLabel("Maximum measured weight (kg)").fill("35");
            await panel.getByLabel("Proposed stage", { exact: false }).selectOption("Mature");
        }
        await upload(page, page.locator(".my-task-submit-overlay"));
        await page.getByRole("button", { name: /Submit for Review/ }).click();
        await expect.poll(() => writes.filter((item) => item.path.endsWith("/submit")).length).toBe(1);
        const payload = writes.find((item) => item.path.endsWith("/submit")).payload;
        expect(payload.monitoring.resource_type).toBe(module);
        expect(payload.monitoring.observation_date).toBe(today);
        expect(payload.evidence_url).toContain("/workforce/evidence/");
        if (module === "Crop") expect(payload.monitoring.current_surviving).toBe(93);
        else expect(payload.monitoring.animals_measured).toBe(4);
    });
}

test("crop review requires explicit early-readiness confirmation", async ({ page }) => {
    const { writes } = await setup(page, { reviewing: true });
    await page.goto("/task-management?tab=tasks");
    await page.getByRole("button", { name: /Review Submission/ }).first().click();
    const dialog = page.locator(".work-review-modal");
    await expect(dialog.getByRole("heading", { name: "Resource Monitoring" })).toBeVisible();
    await dialog.getByRole("button", { name: "Approve Work", exact: true }).click();
    await expect(dialog.getByRole("alert")).toHaveText("Confirm physical harvest readiness before approving.");
    expect(writes.filter((item) => item.path.endsWith("/review"))).toHaveLength(0);
    await dialog.getByLabel("I confirm physical harvest readiness", { exact: false }).check();
    if (process.env.MONITORING_QA_DIR) await page.screenshot({ path: `${process.env.MONITORING_QA_DIR}/crop-monitoring-review.png` });
    await dialog.getByRole("button", { name: "Approve Work", exact: true }).click();
    await expect.poll(() => writes.filter((item) => item.path.endsWith("/review")).length).toBe(1);
    expect(writes.find((item) => item.path.endsWith("/review")).payload.confirm_harvest_ready).toBe(true);
});

test("livestock review retains the recorded stage unless the manager explicitly overrides it", async ({ page }) => {
    const { writes } = await setup(page, { module: "Livestock", reviewing: true });
    await page.goto("/task-management?tab=tasks");
    await page.getByRole("button", { name: /Review Submission/ }).first().click();
    const dialog = page.locator(".work-review-modal");
    const stage = dialog.getByLabel("Confirm livestock stage override", { exact: false });
    await expect(stage).toHaveValue("");
    await stage.selectOption("Mature");
    await dialog.getByRole("button", { name: "Approve Work", exact: true }).click();
    await expect(dialog.getByRole("alert")).toHaveText("Enter reviewer feedback explaining the confirmed stage.");
    await dialog.getByLabel("Feedback to employee").fill("Observed stage confirmed from the monitoring evidence.");
    await dialog.getByRole("button", { name: "Approve Work", exact: true }).click();
    await expect.poll(() => writes.filter((item) => item.path.endsWith("/review")).length).toBe(1);
    expect(writes.find((item) => item.path.endsWith("/review")).payload.confirmed_growth_stage).toBe("Mature");
});

test.describe("mobile monitoring", () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    test("employee monitoring fields remain usable in dark mode", async ({ page }) => {
        await setup(page, { module: "Livestock", worker: true });
        await page.goto("/my-tasks");
        await page.getByRole("button", { name: "Submit Work", exact: true }).tap();
        await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
        const panel = page.locator(".monitoring-observation");
        await expect(panel).toBeVisible();
        const box = await panel.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(391);
        await panel.getByLabel("Animals measured", { exact: false }).fill("4");
        const fieldsFit = await panel.locator("input, select").evaluateAll((fields) => fields.every((field) => { const box = field.getBoundingClientRect(); const parent = field.closest(".monitoring-panel").getBoundingClientRect(); return box.left >= parent.left && box.right <= parent.right; }));
        expect(fieldsFit).toBe(true);
        if (process.env.MONITORING_QA_DIR) await page.screenshot({ path: `${process.env.MONITORING_QA_DIR}/monitoring-mobile-dark.png` });
    });
});


test("crop monitoring edits preserve the Settings fallback and save a deliberate override", async ({ page }) => {
    const { writes } = await setup(page);
    await page.goto("/crops");
    await page.getByTitle("Edit crop information", { exact: true }).click();
    const panel = page.locator('[aria-label="Crop monitoring schedule"]');
    await expect(panel.getByLabel("Repeat every (days)", { exact: false })).toHaveValue("");
    await panel.getByLabel("Repeat every (days)", { exact: false }).fill("4");
    await page.getByRole("button", { name: /Save Changes/ }).click();
    await expect.poll(() => writes.filter((item) => item.path === "/api/v1/crops/1").length).toBe(1);
    expect(writes.find((item) => item.path === "/api/v1/crops/1").payload.monitoring_frequency_days).toBe(4);
});

test("livestock history shows all records and filters an inclusive date range", async ({ page }) => {
    await setup(page, { module: "Livestock" });
    await page.goto("/livestock");
    await page.getByTitle("View livestock details", { exact: true }).click();
    await page.getByRole("button", { name: /Growth History/ }).click();
    const filter = page.locator(".monitoring-history-filter");
    await expect(filter.getByRole("status")).toHaveText("2 records");
    await filter.getByLabel("History from").fill("2026-10-20");
    await filter.getByLabel("History to").fill("2026-10-20");
    await expect(filter.getByRole("status")).toHaveText("1 record");
    await filter.getByRole("button", { name: "Clear dates" }).click();
    await expect(filter.getByRole("status")).toHaveText("2 records");
});



test("enabled livestock recurrence survives saving, reopening, and a full page reload", async ({ page }) => {
    await setup(page, { module: "Livestock", monitoringEnabled: false });
    await page.goto("/livestock");
    await page.getByTitle("Edit livestock", { exact: true }).click();
    let panel = page.locator('[aria-label="Livestock monitoring schedule"]');
    await expect(panel.getByLabel("Enable recurring monitoring")).not.toBeChecked();
    await panel.getByLabel("Enable recurring monitoring").check();
    await panel.getByLabel("Repeat every (days)", { exact: false }).fill("3");
    await panel.getByLabel("Monitoring end date", { exact: false }).fill("2026-11-30");
    await page.getByRole("button", { name: /Save Changes/ }).click();
    await expect(page.getByRole("heading", { name: "Edit Livestock", exact: true })).toHaveCount(0);
    await page.getByTitle("Edit livestock", { exact: true }).click();
    await expect(panel.getByLabel("Enable recurring monitoring")).toBeChecked();
    await expect(panel.getByLabel("First monitoring date", { exact: false })).toHaveValue(today);
    await expect(panel.getByLabel("Repeat every (days)", { exact: false })).toHaveValue("3");
    await page.reload();
    await page.getByTitle("Edit livestock", { exact: true }).click();
    panel = page.locator('[aria-label="Livestock monitoring schedule"]');
    await expect(panel.getByLabel("Enable recurring monitoring")).toBeChecked();
    await expect(panel.getByLabel("Monitoring end date", { exact: false })).toHaveValue("2026-11-30");
    await expect(panel.getByLabel("Repeat every (days)", { exact: false })).toHaveValue("3");
});

test("an API that ignores monitoring cannot show saved success or discard the checked form", async ({ page }) => {
    await setup(page, { module: "Livestock", monitoringEnabled: false, ignoreMonitoring: true });
    await page.goto("/livestock");
    await page.getByTitle("Edit livestock", { exact: true }).click();
    const panel = page.locator('[aria-label="Livestock monitoring schedule"]');
    await panel.getByLabel("Enable recurring monitoring").check();
    await panel.getByLabel("Repeat every (days)", { exact: false }).fill("3");
    await page.getByRole("button", { name: /Save Changes/ }).click();
    await expect(page.getByText(/Monitoring settings were not confirmed by the backend/)).toBeVisible();
    await expect(panel.getByLabel("Enable recurring monitoring")).toBeChecked();
    await expect(panel.getByLabel("Repeat every (days)", { exact: false })).toHaveValue("3");
    await expect(page.getByText("Livestock record updated successfully.", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Save Changes/ })).toBeEnabled();
});


test("monitoring save waits for verification and blocks duplicate clicks", async ({ page }) => {
    const { writes } = await setup(page, { module: "Livestock" });
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    await page.route("**/api/v1/livestock/1", async (route) => {
        if (route.request().method() === "PUT") await pending;
        await route.fallback();
    });
    await page.goto("/livestock");
    await page.getByTitle("Edit livestock", { exact: true }).click();
    const panel = page.locator('[aria-label="Livestock monitoring schedule"]');
    await panel.getByLabel("Repeat every (days)", { exact: false }).fill("4");
    await page.getByRole("button", { name: /Save Changes/ }).evaluate((button) => { button.click(); button.click(); });
    await expect(page.getByRole("button", { name: /Saving/ })).toBeDisabled();
    await expect(panel.getByLabel("Enable recurring monitoring")).toBeDisabled();
    release();
    await expect(page.getByRole("heading", { name: "Edit Livestock", exact: true })).toHaveCount(0);
    expect(writes.filter((write) => write.path === "/api/v1/livestock/1")).toHaveLength(1);
});
