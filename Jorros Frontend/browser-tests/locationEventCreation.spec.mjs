import { test, expect } from "@playwright/test";

const today = "2026-11-02";
const admin = { id: 10, username: "location.admin", fullName: "Farm Administrator", role: "System Administrator", permissions: ["*"], status: "Active" };
const employees = [
    { id: 42, full_name: "Ana Reyes", employment_status: "Active", portal_assignment_ready: true, is_archived: false },
    { id: 43, full_name: "Ben Santos", employment_status: "Active", portal_assignment_ready: false, is_archived: false },
    { id: 44, full_name: "Inactive Worker", employment_status: "Inactive", is_archived: false },
    { id: 45, full_name: "Archived Worker", employment_status: "Active", is_archived: true },
];
const crop = { id: 1, crop_code: "CRP-1", name: "Eggplant", variety: "Test variety", field: "Field A", area_hectares: 1, planting_date: today,
    estimated_harvest: "2027-01-02", quantity_planted: 100, current_surviving: 100, current_growth: 0, status: "Growing", is_archived: false,
    watering_schedule: "Not specified", growth_records: [], yield_records: [], pest_diseases: [] };
const item = { id: 1, item_code: "INV-1", name: "Grower Feed", category: "Livestock Feed", quantity: 20, unit: "kg", cost: 1, price: 2,
    reorder_level: 2, supplier: "Farm supplier", location: "Warehouse A", date_acquired: today, is_archived: false, stock_records: [] };

async function prepare(page, { locationFailure = false, emptyLocations = false, employeeFailure = false, rejectFirst = false, holdSave = false, rejectInventoryFirst = false, holdInventorySave = false, failInventoryRefresh = false, holdCropReload = false, rejectCropFirst = false, holdCropSave = false } = {}) {
    const writes = [], savedEvents = [], choices = { crops: ["Field A", "Field B", "Peña field"], inventory: ["Warehouse A", "Feed Room"], events: ["Field A", "Warehouse A", "Pen A"] };
    const inventoryCommands = new Map(), auditWrites = [];
    let inventoryAttempts = 0;
    let cropAttempts = 0;
    let failEmployee = employeeFailure, reject = rejectFirst, release;
    const gate = holdSave || holdInventorySave || holdCropReload || holdCropSave ? new Promise((resolve) => { release = resolve; }) : null;
    await page.clock.install({ time: new Date(`${today}T01:00:00Z`) });
    await page.addInitScript((user) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-location-event-token", user, expiresAt: Date.now() + 86400000 })), admin);
    await page.route("**/api/v1/**", async (route) => {
        const req = route.request(), url = new URL(req.url()), path = url.pathname;
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: admin });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path === "/api/v1/roles") return route.fulfill({ json: [{ id: 1, name: admin.role, permissions: ["*"], is_active: true }] });
        if (path === "/api/v1/activities/evaluate") return route.fulfill({ json: { created: 0, updated: 0, archived: 0 } });
        if (path === "/api/v1/farm-locations") return route.fulfill({ status: locationFailure ? 503 : 200, json: locationFailure ? { detail: "Saved locations unavailable" } : { items: emptyLocations ? [] : choices[url.searchParams.get("context")] || [] } });
        if (path === "/api/v1/workforce/employees") {
            if (failEmployee) { failEmployee = false; return route.fulfill({ status: 503, json: { detail: "Employee list unavailable" } }); }
            return route.fulfill({ json: employees });
        }
        if (path === "/api/v1/activities/event-resources") return route.fulfill({ json: {
            crops: [{ id: 1, name: "Eggplant", field: "Field A" }, { id: 2, name: "Corn", field: "Field B" }], livestock: [{ id: 7, name: "Piglet Batch", code: "PIG-7", location: "Pen A" }],
            inventory: [item, { id: 2, name: "Animal Vaccine", category: "Vaccine", quantity: 10, unit: "doses", location: "Cold store", reorder_level: 2 }, { id: 3, name: "Feed dispenser", category: "Equipment", quantity: 1, unit: "pieces", location: "Equipment shed", reorder_level: 0 }],
        } });
        if (["POST", "PUT"].includes(req.method())) {
            const body = req.postDataJSON();
            if (["/api/v1/activities", "/api/v1/crops", "/api/v1/crops/1", "/api/v1/inventory", "/api/v1/inventory/1"].includes(path)) writes.push({ path, body, key: req.headers()["idempotency-key"] });
            if (path === "/api/v1/activities") {
                if (holdSave) await gate;
                if (reject) { reject = false; return route.fulfill({ status: 503, json: { detail: "Temporary event save failure" } }); }
                const saved = { id: 99, activity_code: "ACT-99", ...body, assigned_by: admin.fullName, is_archived: false };
                savedEvents.push(saved);
                return route.fulfill({ status: 201, json: saved });
            }
            if (path.startsWith("/api/v1/crops")) {
                if (path === "/api/v1/crops" && req.method() === "POST") {
                    cropAttempts += 1;
                    if (holdCropSave) await gate;
                    if (rejectCropFirst && cropAttempts === 1) return route.fulfill({ status: 503, json: { detail: "Synthetic crop response lost after commit" } });
                }
                choices.crops.push(body.field);
                return route.fulfill({ status: req.method() === "POST" ? 201 : 200, json: { ...crop, ...body } });
            }
            if (path === "/api/v1/inventory" && req.method() === "POST") {
                inventoryAttempts += 1;
                const key = req.headers()["idempotency-key"];
                if (!inventoryCommands.has(key)) inventoryCommands.set(key, { ...item, id: 100 + inventoryCommands.size, ...body });
                if (holdInventorySave) await gate;
                if (rejectInventoryFirst && inventoryAttempts === 1) return route.fulfill({ status: 503, json: { detail: "Test inventory response lost after commit. Retry this entry." } });
                choices.inventory.push(body.location);
                return route.fulfill({ status: 201, json: inventoryCommands.get(key) });
            }
            if (path.startsWith("/api/v1/inventory")) return route.fulfill({ json: { ...item, ...body } });
            if (path === "/api/v1/audit-logs") auditWrites.push(body);
        }
        if (path === "/api/v1/crops" || path === "/api/v1/crops/details") {
            if (holdCropReload && cropAttempts > 0) await gate;
            return route.fulfill({ json: [crop, { ...crop, id: 2, crop_code: "CRP-2", name: "Corn", field: "Field B" }] });
        }
        if (path === "/api/v1/crops/1") return route.fulfill({ json: crop });
        if (path === "/api/v1/inventory") return route.fulfill({ status: failInventoryRefresh && inventoryAttempts > 0 ? 503 : 200, json: failInventoryRefresh && inventoryAttempts > 0 ? { detail: "Synthetic refresh failure" } : [item, ...inventoryCommands.values()] });
        if (path === "/api/v1/inventory/1") return route.fulfill({ json: item });
        if (path === "/api/v1/inventory/page") return route.fulfill({ status: failInventoryRefresh && inventoryAttempts > 0 ? 503 : 200, json: failInventoryRefresh && inventoryAttempts > 0 ? { detail: "Synthetic refresh failure" } : { items: [item], total: 1, limit: 25, offset: 0 } });
        if (path === "/api/v1/activities") return route.fulfill({ json: savedEvents });
        if (path.endsWith("/summary")) return route.fulfill({ json: {} });
        if (path.endsWith("/page")) return route.fulfill({ json: { items: [], total: 0 } });
        return route.fulfill({ json: [] });
    });
    return { writes, release, inventoryCommands, auditWrites };
}

async function openEvent(page) {
    await page.goto("/dashboard");
    await page.getByRole("button", { name: /Add Event$/ }).click();
    const dialog = page.getByRole("dialog", { name: "Add Farm Event", exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Event Title", { exact: false }).fill("Inspect fences");
    await dialog.getByRole("button", { name: "Farm Inspection", exact: true }).click();
    return dialog;
}

for (const card of ["Recent Farm Activity", "Upcoming Tasks"]) {
    test(`${card} View All uses the shared employee and contextual event form`, async ({ page }) => {
        const state = await prepare(page);
        await page.goto("/dashboard");
        await page.locator("article").filter({ has: page.getByRole("heading", { name: card, exact: true }) }).getByRole("button", { name: /^View All/ }).click();
        await page.getByRole("button", { name: /Add Activity$/ }).click();
        const dialog = page.getByRole("dialog", { name: "Add Farm Event", exact: true });
        await expect(dialog).toBeVisible();
        await expect(page.locator(".add-activity-modal, .activity-list-modal, .task-list-modal")).toHaveCount(0);
        await expect(dialog.getByLabel("Event Title", { exact: false })).toBeFocused();
        await dialog.getByLabel("Event Title", { exact: false }).fill("Harvest eggplant");
        await dialog.getByRole("button", { name: "Harvesting", exact: true }).click();
        const employee = dialog.getByLabel("Assigned To", { exact: true });
        await expect(employee).not.toContainText("Field Worker 1");
        await employee.selectOption("42");
        await dialog.getByLabel("Related Record", { exact: false }).selectOption("1");
        await expect(dialog.getByRole("combobox", { name: "Location", exact: true })).toHaveValue("Field A");
        await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
        await expect(dialog).toHaveCount(0);
        const write = state.writes.find((entry) => entry.path === "/api/v1/activities");
        expect(write.key).toBeTruthy();
        expect(write.body).toMatchObject({ assigned_employee_id: 42, source_module: "Crop", source_record_id: 1, location: "Field A", status: "Pending", requires_review: true, requires_evidence: true });
        // Reopening via the other dashboard button starts a fresh form.
        await page.getByRole("button", { name: /Add Event$/ }).click();
        await expect(dialog.getByLabel("Event Title", { exact: false })).toHaveValue("");
        await page.keyboard.press("Escape");
        await expect(dialog).toHaveCount(0);
    });
}

async function fillInventory(page, options = {}) {
    const state = await prepare(page, options);
    await page.goto("/inventory");
    await page.getByRole("button", { name: /Add Inventory$/ }).click();
    const modal = page.locator(".inventory-form-modal");
    await modal.locator("#inventoryItemName").fill("New fertilizer");
    await modal.locator("#inventorySupplier").fill("Farm supplier");
    await modal.getByRole("combobox", { name: "Storage Location", exact: true }).fill("Warehouse B");
    for (const id of ["inventoryQuantity", "inventoryReorderLevel", "inventoryCost", "inventoryPrice"]) await modal.locator(`#${id}`).fill("0");
    await modal.locator("#inventoryQuantity").fill("10");
    return { ...state, modal };
}

async function fillCrop(page, options = {}) {
    const state = await prepare(page, options);
    await page.goto("/crops");
    await page.getByRole("button", { name: /Add Crop$/ }).click();
    const modal = page.locator(".add-crop-modal");
    await modal.getByLabel("Crop Name", { exact: false }).fill("New eggplant");
    await modal.getByLabel("Variety", { exact: false }).fill("New variety");
    await modal.getByRole("combobox", { name: "Field / Location", exact: true }).fill("Field A");
    await modal.getByLabel("Area in Hectares", { exact: false }).fill("0.25");
    await modal.getByLabel("Planting Date", { exact: false }).fill(today);
    await modal.getByLabel("Expected First Harvest", { exact: false }).fill("2027-01-02");
    return { ...state, modal };
}

test("crop save stays guarded while the post-save crop list reload is pending", async ({ page }) => {
    const state = await fillCrop(page, { holdCropReload: true });
    await state.modal.getByRole("button", { name: /Save Crop$/ }).click();
    await expect.poll(() => state.writes.filter((entry) => entry.path === "/api/v1/crops").length).toBe(1);
    await expect(state.modal.getByRole("button", { name: /Saving/ })).toBeDisabled();
    await state.modal.locator("form").evaluate((form) => { form.requestSubmit(); form.requestSubmit(); });
    expect(state.writes.filter((entry) => entry.path === "/api/v1/crops")).toHaveLength(1);
    state.release();
    await expect(state.modal).toHaveCount(0);
});

test("crop pending save disables edits and dismissal", async ({ page }) => {
    const state = await fillCrop(page, { holdCropSave: true });
    await state.modal.getByRole("button", { name: /Save Crop$/ }).click();
    await expect(state.modal.getByRole("button", { name: /Saving/ })).toBeDisabled();
    await expect(state.modal.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    await expect(state.modal.getByRole("button", { name: "Close add crop form" })).toBeDisabled();
    await expect(state.modal.getByLabel("Crop Name", { exact: false })).toBeDisabled();
    await page.locator(".crop-modal-overlay").click({ position: { x: 2, y: 2 } });
    await expect(state.modal).toBeVisible();
    state.release();
    await expect(state.modal).toHaveCount(0);
});

test("crop lost-response retry preserves entries and the creation key", async ({ page }) => {
    const state = await fillCrop(page, { rejectCropFirst: true });
    await state.modal.getByRole("button", { name: /Save Crop$/ }).click();
    await expect(page.getByText("Synthetic crop response lost after commit", { exact: true })).toBeVisible();
    await expect(state.modal.getByLabel("Crop Name", { exact: false })).toHaveValue("New eggplant");
    await state.modal.getByRole("button", { name: /Save Crop$/ }).click();
    await expect(state.modal).toHaveCount(0);
    const requests = state.writes.filter((entry) => entry.path === "/api/v1/crops");
    expect(requests).toHaveLength(2);
    expect(requests[0].key).toBeTruthy();
    expect(requests[0].key).toBe(requests[1].key);
});

test("inventory pending save blocks duplicate submits, edits and dismissal", async ({ page }) => {
    const state = await fillInventory(page, { holdInventorySave: true });
    const modal = state.modal;
    await modal.getByRole("button", { name: /Save Inventory$/ }).click();
    await expect(modal.getByRole("button", { name: /Saving Inventory/ })).toBeDisabled();
    await expect(modal.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    await expect(modal.getByRole("button", { name: "Close inventory form" })).toBeDisabled();
    await expect(modal.locator("#inventoryItemName")).toBeDisabled();
    await modal.locator("form").evaluate((form) => { form.requestSubmit(); form.requestSubmit(); });
    await page.locator(".inventory-modal-overlay").click({ position: { x: 2, y: 2 } });
    await expect(modal).toBeVisible();
    expect(state.writes.filter((entry) => entry.path === "/api/v1/inventory")).toHaveLength(1);
    state.release();
    await expect(modal).toHaveCount(0);
    expect(state.inventoryCommands.size).toBe(1);
    expect(state.auditWrites).toHaveLength(0);
});

test("inventory lost response keeps entered values and retries the same command", async ({ page }) => {
    const state = await fillInventory(page, { rejectInventoryFirst: true });
    const modal = state.modal;
    await modal.getByRole("button", { name: /Save Inventory$/ }).click();
    await expect(page.getByText("Test inventory response lost after commit. Retry this entry.", { exact: true })).toBeVisible();
    await expect(modal.locator("#inventoryItemName")).toHaveValue("New fertilizer");
    await expect(modal.locator("#inventoryQuantity")).toHaveValue("10");
    await modal.getByRole("button", { name: /Save Inventory$/ }).click();
    await expect(modal).toHaveCount(0);
    const writes = state.writes.filter((entry) => entry.path === "/api/v1/inventory");
    expect(writes).toHaveLength(2);
    expect(writes[0].key).toBeTruthy();
    expect(writes[0].key).toBe(writes[1].key);
    expect(state.inventoryCommands.size).toBe(1);
    expect(state.auditWrites).toHaveLength(0);
});

test("inventory save remains successful if the following list refresh fails", async ({ page }) => {
    const state = await fillInventory(page, { failInventoryRefresh: true });
    await state.modal.getByRole("button", { name: /Save Inventory$/ }).click();
    await expect(state.modal).toHaveCount(0);
    await expect(page.getByText("Inventory record added successfully.", { exact: true })).toBeVisible();
    expect(state.writes.filter((entry) => entry.path === "/api/v1/inventory")).toHaveLength(1);
    expect(state.auditWrites).toHaveLength(0);
});

test("inventory metadata edit uses the server audit transaction without duplicate browser audit posts", async ({ page }) => {
    const state = await prepare(page);
    await page.goto("/inventory");
    await page.getByTitle("Edit inventory", { exact: true }).click();
    const modal = page.locator(".inventory-form-modal");
    await expect(modal.locator("#inventoryUnit")).toHaveValue("kg");
    await modal.locator("#inventorySupplier").fill("Updated supplier");
    await modal.getByRole("button", { name: /Save Changes$/ }).click();
    await expect(modal).toHaveCount(0);
    expect(state.writes.filter((entry) => entry.path === "/api/v1/inventory/1")).toHaveLength(1);
    expect(state.auditWrites).toHaveLength(0);
});

test("crop field dropdown searches saved names, accepts custom text and saves it for the next form", async ({ page }) => {
    const { writes } = await prepare(page);
    await page.goto("/crops");
    await page.getByRole("button", { name: /Add Crop$/ }).click();
    const modal = page.locator(".add-crop-modal"), field = modal.getByRole("combobox", { name: "Field / Location", exact: true });
    await field.click();
    await expect(modal.getByRole("option", { name: "Field A", exact: true })).toBeVisible();
    await field.fill("pena");
    await modal.getByRole("option", { name: "Peña field", exact: true }).click();
    await expect(field).toHaveValue("Peña field");
    await field.fill(" New  Hillside "); await field.press("Enter");
    expect(writes).toHaveLength(0);
    await expect(field).toHaveValue("New Hillside");
    await modal.getByLabel("Crop Name", { exact: false }).fill("Test corn");
    await modal.getByLabel("Variety", { exact: false }).fill("Test variety");
    await modal.getByLabel("Area in Hectares", { exact: false }).fill("0.25");
    await modal.getByLabel("Planting Date", { exact: false }).fill(today);
    await modal.getByLabel("Expected First Harvest", { exact: false }).fill("2027-01-02");
    await modal.getByRole("button", { name: /Save Crop$/ }).click();
    await expect(modal).toHaveCount(0);
    expect(writes.at(-1).body.field).toBe("New Hillside");
    await page.getByRole("button", { name: /Add Crop$/ }).click();
    await field.click();
    await expect(modal.getByRole("option", { name: "New Hillside", exact: true })).toBeVisible();
});

test("inventory uses the same searchable location control and custom names still work if suggestions fail", async ({ page }) => {
    const { writes } = await prepare(page, { locationFailure: true });
    await page.goto("/inventory");
    await page.getByRole("button", { name: /Add Inventory$/ }).click();
    const modal = page.locator(".inventory-form-modal");
    const location = modal.getByRole("combobox", { name: "Storage Location", exact: true });
    await location.click();
    await expect(modal.getByRole("option", { name: "Warehouse A", exact: true })).toBeVisible();
    await location.fill("New shed"); await location.press("Enter");
    await modal.locator("#inventoryItemName").fill("Test tools");
    await modal.locator("#inventorySupplier").fill("Farm supplier");
    for (const id of ["inventoryQuantity", "inventoryReorderLevel", "inventoryCost", "inventoryPrice"]) await modal.locator(`#${id}`).fill("1");
    await modal.getByRole("button", { name: /Save Inventory$/ }).click();
    await expect(modal).toHaveCount(0);
    expect(writes.at(-1).body.location).toBe("New shed");
});

test("event choices are real employees and locations; assigned work cannot start as completed", async ({ page }) => {
    const { writes } = await prepare(page);
    const dialog = await openEvent(page);
    const assignee = dialog.getByLabel("Assigned To", { exact: true });
    await expect(assignee.locator("option", { hasText: "Ana Reyes" })).toHaveAttribute("value", "42");
    await expect(assignee.locator("option", { hasText: "Ben Santos" })).toBeDisabled();
    await expect(assignee).not.toContainText("Inactive Worker");
    await expect(assignee).not.toContainText("Field Worker 1");
    await assignee.selectOption("42");
    await expect(dialog.getByLabel("Status", { exact: true })).toBeDisabled();
    await dialog.getByRole("combobox", { name: "Location", exact: true }).click();
    await dialog.getByRole("option", { name: "Pen A", exact: true }).click();
    await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes.at(-1).body).toMatchObject({ assigned_employee_id: 42, assigned_to: "Ana Reyes", status: "Pending", requires_review: true, requires_evidence: true, location: "Pen A" });
    await expect(page.getByText("Inspect fences", { exact: true }).first()).toBeVisible();
});

test("failed event saves retain fields and repeat the same idempotency key", async ({ page }) => {
    const { writes } = await prepare(page, { rejectFirst: true });
    const dialog = await openEvent(page);
    await dialog.getByLabel("Assigned To", { exact: true }).selectOption("42");
    await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(page.getByText("Temporary event save failure", { exact: true })).toBeVisible();
    await expect(dialog.getByLabel("Event Title", { exact: false })).toHaveValue("Inspect fences");
    await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes).toHaveLength(2);
    expect(writes[0].key).toBeTruthy(); expect(writes[0].key).toBe(writes[1].key);
    expect(writes[0].body).toEqual(writes[1].body);
});

test("a pending event save blocks duplicate submits and closing until it completes", async ({ page }) => {
    const { writes, release } = await prepare(page, { holdSave: true });
    const dialog = await openEvent(page);
    await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Saving…", exact: true })).toBeDisabled();
    await page.keyboard.press("Escape");
    await dialog.getByRole("button", { name: "Close event form", exact: true }).click();
    await expect(dialog).toBeVisible();
    expect(writes).toHaveLength(1);
    release(); await expect(dialog).toHaveCount(0);
    expect(writes[0].body).toMatchObject({ assigned_employee_id: null, requires_review: false, location: "Joross Farm" });
});

for (const type of ["Livestock Feeding", "Vaccination"]) test(`${type} event captures valid target, stock and planned quantity`, async ({ page }) => {
    const { writes } = await prepare(page);
    const dialog = await openEvent(page);
    await dialog.getByRole("button", { name: type, exact: true }).click();
    await dialog.getByLabel("Assigned To", { exact: true }).selectOption("42");
    const resources = dialog.getByRole("region", { name: "Linked work resources", exact: true });
    await expect(resources).toBeVisible();
    await dialog.getByLabel("Related Record", { exact: false }).selectOption("7");
    const stock = dialog.getByLabel("Inventory Resource", { exact: false });
    const id = type === "Livestock Feeding" ? "1" : "2";
    await stock.selectOption(id);
    await expect(stock).not.toContainText(type === "Livestock Feeding" ? "Animal Vaccine" : "Grower Feed");
    const quantity = dialog.getByLabel("Planned Quantity", { exact: false });
    await quantity.fill("100"); await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    expect(writes).toHaveLength(0);
    await quantity.fill("2"); await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes[0].body).toMatchObject({ assigned_employee_id: 42, source_module: "Livestock", source_record_id: 7, planned_inventory_item_id: Number(id), planned_quantity: 2, location: "Pen A" });
});

test("employee list failure offers retry and does not show fabricated assignees", async ({ page }) => {
    await prepare(page, { employeeFailure: true });
    const dialog = await openEvent(page);
    await expect(dialog.getByLabel("Assigned To", { exact: true })).toBeDisabled();
    await dialog.getByRole("button", { name: "Retry employees", exact: true }).click();
    await expect(dialog.getByLabel("Assigned To", { exact: true })).toBeEnabled();
    await dialog.getByLabel("Assigned To", { exact: true }).selectOption("42");
});

for (const theme of ["light", "dark"]) test(`saved inventory locations use the shared dropdown in ${theme} mode`, async ({ page }) => {
    await prepare(page);
    await page.addInitScript((value) => localStorage.setItem("joross-theme", value), theme);
    await page.goto("/inventory");
    await page.getByRole("button", { name: /Add Inventory$/ }).click();
    const modal = page.locator(".inventory-form-modal"), location = modal.getByRole("combobox", { name: "Storage Location", exact: true });
    await location.click();
    const list = modal.getByRole("listbox", { name: "Storage Location suggestions", exact: true });
    await expect(list.getByRole("option", { name: "Warehouse A", exact: true })).toBeVisible();
    expect(await list.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe(theme === "dark" ? "rgb(19, 33, 25)" : "rgb(255, 255, 255)");
    await page.screenshot({ path: test.info().outputPath(`inventory-locations-${theme}.png`) });
    await list.getByRole("option", { name: "Feed Room", exact: true }).click();
    await expect(location).toHaveValue("Feed Room");
});

test("invalid event end time is rejected without a save and keeps the form editable", async ({ page }) => {
    const { writes } = await prepare(page);
    const dialog = await openEvent(page);
    await dialog.getByLabel("Start Time", { exact: false }).fill("10:00");
    await dialog.getByLabel("End Time", { exact: true }).fill("09:00");
    await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(page.getByText("The end time must be later than the start time.", { exact: true })).toBeVisible();
    expect(writes).toHaveLength(0);
    await expect(dialog.getByRole("button", { name: "Save Event", exact: true })).toBeEnabled();
});

test("event form fits a narrow screen and keyboard selection does not submit it", async ({ page }) => {
    const { writes } = await prepare(page);
    await page.setViewportSize({ width: 390, height: 844 });
    const dialog = await openEvent(page);
    const location = dialog.getByRole("combobox", { name: "Location", exact: true });
    await location.click();
    const firstLocation = await dialog.getByRole("listbox", { name: "Location suggestions", exact: true }).getByRole("option").first().innerText();
    await location.press("ArrowDown"); await location.press("Enter");
    await expect(location).toHaveValue(firstLocation); expect(writes).toHaveLength(0);
    await expect(dialog.getByLabel("Assigned To", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath("event-mobile.png") });
    await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0);
});


test("existing crop fields remain available when the separate location API and fallback request fail", async ({ page }) => {
    await prepare(page, { locationFailure: true });
    await page.route("**/api/v1/crops?*", (route) => route.fulfill({ status: 503, json: { detail: "Field lookup unavailable" } }));
    await page.goto("/crops");
    await page.getByRole("button", { name: /Add Crop$/ }).click();
    const modal = page.locator(".add-crop-modal");
    await modal.getByRole("combobox", { name: "Field / Location", exact: true }).click();
    await expect(modal.getByRole("option", { name: "Field A", exact: true })).toBeVisible();
    await expect(modal.getByRole("option", { name: "Field B", exact: true })).toBeVisible();
    await expect(modal.getByRole("option", { name: "Warehouse A", exact: true })).toHaveCount(0);
});

test("an empty location response recovers actual crop fields and uses field-specific wording", async ({ page }) => {
    await prepare(page, { emptyLocations: true });
    await page.goto("/crops"); await page.getByRole("button", { name: /Add Crop$/ }).click();
    const modal = page.locator(".add-crop-modal");
    const field = modal.getByRole("combobox", { name: "Field / Location", exact: true });
    await expect(field).toHaveAttribute("placeholder", "Search or choose a crop field");
    await field.click(); await expect(modal.getByRole("option", { name: "Field A", exact: true })).toBeVisible();
});

test("restocking selects the actual item and warehouse and saves an inventory plan without consumption", async ({ page }) => {
    const { writes } = await prepare(page);
    const dialog = await openEvent(page);
    await dialog.getByRole("button", { name: "Inventory Restocking", exact: true }).click();
    const itemSelect = dialog.getByLabel("Inventory Item", { exact: false });
    await itemSelect.selectOption("1");
    const location = dialog.getByRole("combobox", { name: "Location", exact: true });
    await expect(location).toHaveValue("Warehouse A"); await expect(location).toHaveAttribute("readonly", "");
    await itemSelect.selectOption("2"); await expect(location).toHaveValue("Cold store");
    await dialog.getByLabel("Assigned To", { exact: true }).selectOption("42");
    await expect(dialog.getByRole("region", { name: "Linked work resources", exact: true })).toHaveCount(0);
    await expect(dialog).toContainText("does not add or deduct stock");
    if (process.env.CONTEXT_LOCATION_QA_DIR) {
        await location.scrollIntoViewIfNeeded();
        await page.screenshot({ path: `${process.env.CONTEXT_LOCATION_QA_DIR}/restocking-plan.png` });
    }
    await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes[0].body).toMatchObject({ source_module: "Inventory", source_record_id: 2, source_type: "inventory_restock_plan", location: "Cold store", planned_inventory_item_id: null, assigned_employee_id: 42 });
});

test("changing event type clears incompatible records and only offers the relevant location domain", async ({ page }) => {
    await prepare(page);
    const dialog = await openEvent(page);
    await dialog.getByRole("button", { name: "Fertilization", exact: true }).click();
    await dialog.getByLabel("Related Record", { exact: false }).selectOption("1");
    const location = dialog.getByRole("combobox", { name: "Location", exact: true });
    await expect(location).toHaveValue("Field A");
    await dialog.getByRole("button", { name: "Livestock Health Check", exact: true }).click();
    await expect(location).toHaveValue("");
    await expect(dialog.getByLabel("Related Record", { exact: false })).toHaveValue("");
    await location.click();
    await expect(dialog.getByRole("option", { name: "Pen A", exact: true })).toBeVisible();
    await expect(dialog.getByRole("option", { name: "Field A", exact: true })).toHaveCount(0);
    await expect(dialog.getByRole("option", { name: "Warehouse A", exact: true })).toHaveCount(0);
});

test("equipment maintenance offers equipment records and uses the equipment shed", async ({ page }) => {
    const { writes } = await prepare(page);
    const dialog = await openEvent(page);
    await dialog.getByRole("button", { name: "Equipment Maintenance", exact: true }).click();
    const equipment = dialog.getByLabel("Equipment / Tool", { exact: false });
    await expect(equipment).not.toContainText("Grower Feed");
    await equipment.selectOption("3");
    await expect(dialog.getByRole("combobox", { name: "Location", exact: true })).toHaveValue("Equipment shed");
    await dialog.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes[0].body).toMatchObject({ source_module: "Inventory", source_record_id: 3, source_type: "equipment_maintenance_plan", planned_inventory_item_id: null });
});

test("loaded inventory warehouses remain available when both location lookup requests fail", async ({ page }) => {
    await prepare(page, { locationFailure: true });
    await page.route("**/api/v1/inventory/page?*", (route) => route.fulfill({ json: { items: [item], total: 1, offset: 0, limit: 25 } }));
    await page.route("**/api/v1/inventory?*", (route) => route.fulfill({ status: 503, json: { detail: "Storage lookup unavailable" } }));
    await page.goto("/inventory");
    await page.getByRole("button", { name: /Add Inventory$/ }).click();
    const modal = page.locator(".inventory-form-modal");
    const location = modal.getByRole("combobox", { name: "Storage Location", exact: true });
    await expect(location).toHaveAttribute("placeholder", "Search or choose a warehouse or storage area");
    await location.click();
    await expect(modal.getByRole("option", { name: "Warehouse A", exact: true })).toBeVisible();
    await expect(modal.getByRole("option", { name: "Field A", exact: true })).toHaveCount(0);
});
