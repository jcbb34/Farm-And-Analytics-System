import { test, expect } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
const data = JSON.parse(readFileSync(new URL("../../Jorros Backend/reference_data/philippine_locations.json", import.meta.url), "utf8"));
const today = "2026-10-31";
const administrator = { id: 1, username: "profile.test", fullName: "Profile Administrator", role: "System Administrator", permissions: ["*"], status: "Active" };
const roles = [{ id: 1, name: "System Administrator", permissions: ["*"], is_active: true }, { id: 2, name: "Farm Staff", permissions: ["workforce:submit"], is_active: true }, { id: 3, name: "Employee", permissions: ["workforce:submit"], is_active: true }];
async function setup(page, { worker = false, failApproval = false, failLocations = false, failBundle = false, holdApproval = false } = {}) {
    const writes = [], employees = [], users = [], approvals = [];
    let bundleUnavailable = failBundle, locationRequests = 0;
    let effects = 0, release;
    const gate = new Promise((resolve) => { release = resolve; });
    const user = worker ? { ...administrator, id: 10, username: "profile.worker", fullName: "Profile Worker", role: "Employee", permissions: ["workforce:submit"] } : administrator;
    let task = { id: 42, activity_code: "PERSON-VOID", name: "Approved test work", category: "Maintenance", activity_date: today, start_time: "08:00", location: "Test Farm", related_to: "Test resource", assigned_employee_id: 10, assigned_to: user.fullName, employee_name: user.fullName,
        status: "Completed", can_void: true, priority: "Medium", requires_review: true, requires_evidence: false, is_archived: false, resource_required: false, source_type: "manual", latest_submission: { id: 77, employee_id: 10, employee_name: user.fullName, review_status: "Approved", actual_quantity: 2, actual_unit: "kg", submitted_at: `${today}T08:00:00`, worker_notes: "Test performed work", attempt_number: 1 } };
    await page.clock.install({ time: new Date(`${today}T04:00:00Z`) });
    await page.addInitScript((profile) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-profile-token", user: profile, expiresAt: Date.now() + 86400000 })), user);
    await page.route("**/reference-data/philippine_locations.2026-Q3.json", (route) => bundleUnavailable
        ? route.fulfill({ status: 503, json: { detail: "Synthetic bundled reference failure" } })
        : route.continue());
    await page.route("**/api/v1/**", async (route) => {
        const request = route.request(), url = new URL(request.url()), path = url.pathname;
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path === "/api/v1/reference/locations") {
            locationRequests += 1;
            if (failLocations) return route.fulfill({ status: 503, json: { detail: "Synthetic reference failure" } });
            const level = url.searchParams.get("level"), parent = url.searchParams.get("parent_code"), field = level === "cities" ? "province_code" : "city_code";
            return route.fulfill({ json: { items: data[level].filter((row) => level === "provinces" || row[field] === parent).map(({ code, name }) => ({ code, name })) } });
        }
        if (path === "/api/v1/void-authorizations/preview") return route.fulfill({ json: { preview_token: "synthetic-one-record-preview", label: task.name, impact: "Restore 2 kg of the test resource.", requires_owner_credentials: worker } });
        if (path === "/api/v1/void-authorizations" && request.method() === "POST") {
            approvals.push(request.postDataJSON());
            if (holdApproval) await gate;
            if (failApproval && approvals.length === 1) return route.fulfill({ status: 403, json: { detail: "Owner/Admin authorization failed." } });
            effects += 1; task = { ...task, status: "Voided", can_void: false, latest_submission: { ...task.latest_submission, review_status: "Voided" } };
            return route.fulfill({ json: { status: "Voided" } });
        }
        if (path === "/api/v1/users" && request.method() === "POST") {
            const payload = request.postDataJSON(); writes.push({ path, payload });
            const row = { id: 77, user_code: "USR-PROFILE", ...payload, role: roles.find((role) => role.name === payload.role_name), status: "Active" }; users.push(row);
            return route.fulfill({ status: 201, json: row });
        }
        if (path === "/api/v1/workforce/employees" && request.method() === "POST") {
            const payload = request.postDataJSON(); writes.push({ path, payload });
            const row = { id: 77, employee_code: "EMP-PROFILE", ...payload, position: "Farm Worker", positions: [{ id: 1, name: "Farm Worker", is_primary: true }], login_user_id: 77, login_username: payload.login_username, is_archived: false }; employees.push(row);
            return route.fulfill({ status: 201, json: row });
        }
        if (path === "/api/v1/users") return route.fulfill({ json: users });
        if (path === "/api/v1/roles") return route.fulfill({ json: roles });
        if (path.endsWith("/positions")) return route.fulfill({ json: [{ id: 1, name: "Farm Worker", category: "Farm Operations", is_active: true }] });
        if (path.endsWith("/employees")) return route.fulfill({ json: employees });
        if (path.endsWith("/page")) return route.fulfill({ json: { items: worker ? [task] : [], total: worker ? 1 : 0, offset: 0, limit: 25 } });
        if (path.endsWith("/summary")) return route.fulfill({ json: {} });
        if (path.endsWith("/my-schedule")) return route.fulfill({ json: { availability: [], attendance: [], leave: [], shifts: [], tasks: [] } });
        return route.fulfill({ json: [] });
    });
    return { writes, approvals, release, effectCount: () => effects, locationRequestCount: () => locationRequests, restoreBundle: () => { bundleUnavailable = false; } };
}
async function names(dialog) {
    await dialog.getByLabel("First name", { exact: false }).fill("Casey Ana");
    await dialog.getByLabel("Middle name", { exact: false }).fill("Reyes");
    await dialog.getByLabel("Surname", { exact: false }).fill("De la Cruz");
    await dialog.getByLabel("Suffix", { exact: false }).selectOption("Jr.");
}
async function customAddress(dialog) {
    await dialog.getByLabel("House/Building Number and Street", { exact: true }).fill("12 Sample Street");
    await dialog.getByRole("combobox", { name: "Province / address area", exact: true }).fill("Custom Province");
    await dialog.getByRole("option", { name: /Use .*Custom Province.* as a custom entry/ }).click();
    await dialog.getByRole("combobox", { name: "City / Municipality", exact: true }).fill("Custom City");
    await dialog.getByRole("combobox", { name: "Barangay", exact: true }).fill("Custom Barangay");
    await dialog.getByLabel("Postal / ZIP Code", { exact: true }).fill("0450");
}
async function employeeForm(page) {
    await page.goto("/task-management?tab=employees");
    await page.getByRole("button", { name: /Add Employee/ }).click();
    return page.getByRole("dialog", { name: "Add Employee", exact: true });
}
async function userForm(page) {
    await page.goto("/settings"); await page.getByRole("button", { name: /User Management/ }).click();
    await page.getByRole("button", { name: /Create User/, exact: false }).click();
    return page.getByRole("dialog", { name: /Create User Account/ });
}
async function workerVoid(page) {
    await page.goto("/my-tasks?view=completed");
    await page.getByRole("button", { name: "Request Void", exact: true }).click();
    return page.getByRole("dialog", { name: "Owner/Admin Void Authorization", exact: true });
}

test("employee creation sends separate names, custom address and linked login", async ({ page }) => {
    const state = await setup(page), dialog = await employeeForm(page);
    await names(dialog); await customAddress(dialog);
    await dialog.getByLabel("Primary Position", { exact: false }).selectOption("1");
    await dialog.getByLabel("Initial Password", { exact: false }).fill("Synthetic-Test-Password");
    await dialog.getByLabel("Confirm Password", { exact: false }).fill("Synthetic-Test-Password");
    await dialog.getByRole("button", { name: "Save Employee", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    const body = state.writes.find((entry) => entry.path.endsWith("/employees")).payload;
    expect(body.full_name).toBe("Casey Ana Reyes De la Cruz Jr.");
    expect(body.personal_details.address.barangay).toBe("Custom Barangay");
    expect(body.personal_details.address.postal_code).toBe("0450");
    expect(body.create_login_account).toBe(true);
});
test("user creation uses the same name and address fields", async ({ page }) => {
    const state = await setup(page), dialog = await userForm(page);
    await names(dialog); await customAddress(dialog);
    await dialog.locator("#userUsername").fill("casey.worker");
    await dialog.locator("#userContactNumber").fill("09123456789");
    await dialog.locator("#userPosition").fill("Farm worker");
    await dialog.locator("#userPassword").fill("Synthetic-Test-Password");
    await dialog.locator("#userConfirmPassword").fill("Synthetic-Test-Password");
    if (process.env.PERSONAL_DETAILS_QA_DIR) {
        mkdirSync(process.env.PERSONAL_DETAILS_QA_DIR, { recursive: true });
        await dialog.getByLabel("First name", { exact: false }).scrollIntoViewIfNeeded();
        await page.screenshot({ path: `${process.env.PERSONAL_DETAILS_QA_DIR}/user-profile-desktop.png` });
    }
    await dialog.getByRole("button", { name: "Create User", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(state.writes[0].payload.personal_details.surname).toBe("De la Cruz");
    expect(state.writes[0].payload.personal_details.address.province_code).toBeNull();
});
test("searchable address choices filter children and reset when a parent changes", async ({ page }) => {
    await setup(page); const dialog = await employeeForm(page);
    const province = dialog.getByRole("combobox", { name: "Province / address area", exact: true });
    await province.fill("Albay"); await dialog.getByRole("option", { name: "Albay", exact: true }).click();
    const city = dialog.getByRole("combobox", { name: "City / Municipality", exact: true });
    await city.fill("Legazpi"); await dialog.getByRole("option", { name: /Legazpi/ }).first().click();
    const barangay = dialog.getByRole("combobox", { name: "Barangay", exact: true });
    await barangay.fill("Gogon"); await dialog.getByRole("option", { name: /Gogon/ }).first().click();
    await province.fill("Custom Province");
    await expect(city).toHaveValue(""); await expect(barangay).toHaveValue("");
});
test("address combobox Enter selects a location without submitting the form", async ({ page }) => {
    const state = await setup(page), dialog = await employeeForm(page);
    await dialog.locator("form").evaluate((form) => { window.addressSubmitAttempts = 0; form.addEventListener("submit", () => { window.addressSubmitAttempts += 1; }); });
    const province = dialog.getByRole("combobox", { name: "Province / address area", exact: true });
    await province.fill("Albay"); await expect(dialog.getByRole("option", { name: "Albay", exact: true })).toBeVisible();
    await province.press("ArrowDown"); await province.press("Enter");
    await expect(dialog.getByText("Selected from address list", { exact: true })).toBeVisible();
    const city = dialog.getByRole("combobox", { name: "City / Municipality", exact: true });
    await city.fill("Custom City"); await city.press("Enter");
    await expect(dialog.getByRole("listbox", { name: "City / Municipality choices", exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => window.addressSubmitAttempts)).toBe(0);
    expect(state.writes).toHaveLength(0);
});
test("custom address entry remains available when the local reference endpoint fails", async ({ page }) => {
    await setup(page, { failLocations: true, failBundle: true }); const dialog = await employeeForm(page);
    await expect(dialog.getByText(/Locations unavailable/)).toBeVisible();
    await customAddress(dialog);
    await expect(dialog.getByRole("combobox", { name: "Barangay", exact: true })).toHaveValue("Custom Barangay");
});
test("the real bundled address list works while the reference API is unavailable", async ({ page }) => {
    const state = await setup(page, { failLocations: true }), dialog = await employeeForm(page);
    await dialog.getByRole("combobox", { name: "Province / address area", exact: true }).fill("Albay");
    await dialog.getByRole("option", { name: "Albay", exact: true }).click();
    await dialog.getByRole("combobox", { name: "City / Municipality", exact: true }).fill("Legazpi");
    await dialog.getByRole("option", { name: /Legazpi/ }).first().click();
    await dialog.getByRole("combobox", { name: "Barangay", exact: true }).fill("Gogon");
    await dialog.getByRole("option", { name: /Gogon/ }).first().click();
    await expect(dialog.getByText(/Locations unavailable/)).toHaveCount(0);
    expect(state.locationRequestCount()).toBe(0);
});
test("a missing bundled file uses the existing reference API", async ({ page }) => {
    const state = await setup(page, { failBundle: true }), dialog = await userForm(page);
    await dialog.getByRole("combobox", { name: "Province / address area", exact: true }).fill("Albay");
    await dialog.getByRole("option", { name: "Albay", exact: true }).click();
    await dialog.getByRole("combobox", { name: "City / Municipality", exact: true }).fill("Legazpi");
    await dialog.getByRole("option", { name: /Legazpi/ }).first().click();
    await expect(dialog.getByText(/Locations unavailable/)).toHaveCount(0);
    expect(state.locationRequestCount()).toBeGreaterThan(0);
});
test("retry recovers the bundled choices and clears the unavailable message", async ({ page }) => {
    const state = await setup(page, { failLocations: true, failBundle: true }), dialog = await employeeForm(page);
    await expect(dialog.getByText(/Locations unavailable/)).toBeVisible();
    state.restoreBundle();
    await dialog.getByRole("button", { name: "Retry list", exact: true }).click();
    await expect(dialog.getByText(/Locations unavailable/)).toHaveCount(0);
    await dialog.getByRole("combobox", { name: "Province / address area", exact: true }).fill("Albay");
    await expect(dialog.getByRole("option", { name: "Albay", exact: true })).toBeVisible();
});
test("employee authorization requires owner credentials, clears failed passwords and preserves the session", async ({ page }) => {
    const state = await setup(page, { worker: true, failApproval: true }), dialog = await workerVoid(page);
    await expect(dialog.getByText("Restore 2 kg of the test resource.", { exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: "Authorize & Void", exact: true }).click(); expect(state.approvals).toHaveLength(0);
    await dialog.getByLabel("Reason for voiding", { exact: false }).fill("Wrong approved work entry");
    await dialog.getByLabel("Owner/Admin username", { exact: false }).fill("test.owner");
    await dialog.getByLabel("Owner/Admin password", { exact: false }).fill("Synthetic-Test-Password");
    await dialog.getByRole("button", { name: "Authorize & Void", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Owner/Admin authorization failed.");
    await expect(dialog.getByLabel("Owner/Admin password", { exact: false })).toHaveValue("");
    await expect(dialog.getByLabel("Reason for voiding", { exact: false })).toHaveValue("Wrong approved work entry");
    await dialog.getByLabel("Owner/Admin password", { exact: false }).fill("Synthetic-Test-Password");
    await dialog.getByRole("button", { name: "Authorize & Void", exact: true }).click();
    await expect(dialog).toHaveCount(0); expect(state.effectCount()).toBe(1);
    const session = await page.evaluate(() => JSON.parse(localStorage.getItem("joross-auth-session-v1")));
    expect(session.accessToken).toBe("synthetic-profile-token"); expect(session.user.permissions).toEqual(["workforce:submit"]);
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("Synthetic-Test-Password");
});
test("pending owner authorization blocks duplicate submission and cancellation", async ({ page }) => {
    const state = await setup(page, { worker: true, holdApproval: true }), dialog = await workerVoid(page);
    await dialog.getByLabel("Reason for voiding", { exact: false }).fill("Wrong approved work entry");
    await dialog.getByLabel("Owner/Admin username", { exact: false }).fill("test.owner");
    await dialog.getByLabel("Owner/Admin password", { exact: false }).fill("Synthetic-Test-Password");
    await dialog.getByRole("button", { name: "Authorize & Void", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Authorizing...", exact: true })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
    await page.keyboard.press("Escape"); await expect(dialog).toBeVisible(); expect(state.approvals).toHaveLength(1);
    state.release(); await expect(dialog).toHaveCount(0);
});
test.describe("mobile forms", () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    test("name and custom-address controls fit the dark-mode employee form", async ({ page }) => {
        await setup(page);
        const dialog = await employeeForm(page);
        await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
        await names(dialog); await customAddress(dialog);
        const background = await dialog.getByLabel("First name", { exact: false }).evaluate((input) => getComputedStyle(input).backgroundColor);
        expect(background.match(/\d+/g).slice(0, 3).every((channel) => Number(channel) < 100)).toBe(true);
        const contactColor = await dialog.locator('label[for="employee-contact"]').evaluate((label) => getComputedStyle(label).color);
        expect(contactColor.match(/\d+/g).slice(0, 3).every((channel) => Number(channel) > 150)).toBe(true);
        for (const field of await dialog.locator(".personal-field input,.personal-field select").all()) {
            await field.scrollIntoViewIfNeeded(); const box = await field.boundingBox();
            expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(390);
        }
        if (process.env.PERSONAL_DETAILS_QA_DIR) {
            mkdirSync(process.env.PERSONAL_DETAILS_QA_DIR, { recursive: true });
            await dialog.getByLabel("First name", { exact: false }).scrollIntoViewIfNeeded();
            await page.screenshot({ path: `${process.env.PERSONAL_DETAILS_QA_DIR}/employee-profile-mobile-dark.png` });
        }
    });
});
