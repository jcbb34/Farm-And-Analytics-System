import { withDisplayData } from "./helpers/displayApiFixtures.mjs";
import { test, expect } from "@playwright/test";
import { serveSessionPolicy } from "./helpers/serveSessionPolicy.mjs";

const today = "2026-11-06";
const user = { id: 10, username: "focus.admin", fullName: "Focus Test Admin", role: "System Administrator", permissions: ["*"], status: "Active" };
const employees = [
    { id: 1, full_name: "Current Worker", employee_code: "FOCUS-01", assigned_area: "Field A" },
    { id: 2, full_name: "Harvest Worker Two", employee_code: "FOCUS-02", assigned_area: "Field A" },
    { id: 3, full_name: "Harvest Worker Three", employee_code: "FOCUS-03", assigned_area: "Field B" },
].map((employee) => ({ ...employee, employment_status: "Active", is_archived: false, portal_assignment_ready: true, account_status: "Account Linked", positions: [{ id: 20, name: "Harvest Worker", category: "Crop", is_primary: true }] }));

async function setup(page, { dark = false } = {}) {
    const writes = [], errors = [];
    let task = { id: 701, activity_code: "FOCUS-TASK", name: "Harvest test crop", category: "Crop Care", related_to: "Test crop", location: "Field A", activity_date: today, start_time: "08:00", status: "Pending", priority: "Medium", assigned_employee_id: 1, employee_name: employees[0].full_name, requires_review: true, resource_required: false, is_archived: false };
    page.on("pageerror", (error) => errors.push(error.message));
    await page.clock.install({ time: new Date(`${today}T01:00:00Z`) });
    await page.addInitScript(({ user, dark }) => {
        sessionStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-focus-token", user, expiresAt: Date.now() + 86400000 }));
        localStorage.setItem("joross-theme", dark ? "dark" : "light");
    }, { user, dark });
    await page.route("**/api/v1/**", withDisplayData(async (route) => {
        if (await serveSessionPolicy(route, page)) return;
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path === "/api/v1/roles") return route.fulfill({ json: [{ id: 1, name: user.role, permissions: user.permissions, is_active: true }] });
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path === "/api/v1/workforce/employees") return route.fulfill({ json: employees });
        if (path === "/api/v1/workforce/tasks/page") return route.fulfill({ json: { items: [task], total: 1, offset: 0, limit: 25 } });
        if (path === "/api/v1/workforce/tasks/summary") return route.fulfill({ json: { pending: 1, progress: 0, review: 0, overdue: 0, reassign: 0 } });
        if (path === "/api/v1/workforce/availability") return route.fulfill({ json: [{ available: true, work_date: today, employee_id: 2 }] });
        if (path === "/api/v1/workforce/tasks/701/assignment" && request.method() === "PUT") {
            const payload = request.postDataJSON(); writes.push({ path, method: request.method(), payload });
            task = { ...task, assigned_employee_id: payload.employee_id, employee_name: employees.find((employee) => employee.id === payload.employee_id).full_name };
            return route.fulfill({ json: task });
        }
        return route.fulfill({ json: [] });
    }));
    await page.goto(`/task-management?date=${today}`);
    await page.getByRole("button", { name: /Reassign/, exact: false }).click();
    const dialog = page.getByRole("dialog", { name: "Reassign Task", exact: true });
    const search = dialog.getByRole("searchbox");
    await expect(search).toBeFocused();
    return { dialog, search, wrapper: search.locator(".."), writes, errors };
}

async function expectSingleFocus(search, wrapper) {
    await expect(search).toHaveCSS("outline-style", "none");
    await expect(search).toHaveCSS("box-shadow", "none");
    await expect(wrapper).not.toHaveCSS("box-shadow", "none");
    expect(await wrapper.evaluate((element) => element.matches(":focus-within"))).toBe(true);
    const input = await search.boundingBox(), control = await wrapper.boundingBox();
    expect(input.x).toBeGreaterThan(control.x);
    expect(input.x + input.width).toBeLessThanOrEqual(control.x + control.width);
    expect(input.y).toBeGreaterThan(control.y);
    expect(input.y + input.height).toBeLessThanOrEqual(control.y + control.height);
}

for (const width of [390, 1440]) for (const dark of [false, true]) {
    test(`reassignment search has one complete focus highlight at ${width}px in ${dark ? "dark" : "light"} mode`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        const { dialog, search, wrapper, writes, errors } = await setup(page, { dark });
        await expect(page.locator("html")).toHaveAttribute("data-theme", dark ? "dark" : "light");
        await expectSingleFocus(search, wrapper);
        const before = await wrapper.boundingBox();
        await search.fill("FOCUS-02");
        await expect(dialog.locator(".reassign-candidate")).toHaveCount(1);
        await expect(dialog.locator(".reassign-candidate")).toContainText(employees[1].full_name);
        await expectSingleFocus(search, wrapper);
        expect(await wrapper.boundingBox()).toEqual(before);
        await search.press("Tab");
        const candidate = dialog.locator(".reassign-candidate");
        await expect(candidate).toBeFocused();
        await expect(candidate).not.toHaveCSS("box-shadow", "none");
        await expect(wrapper).toHaveCSS("box-shadow", "none");
        await page.keyboard.press("Shift+Tab");
        await expect(search).toBeFocused();
        await expectSingleFocus(search, wrapper);
        await search.fill("no-such-employee");
        await expect(dialog.getByText("No available employee found", { exact: true })).toBeVisible();
        await search.clear(); await expect(dialog.locator(".reassign-candidate")).toHaveCount(2);
        await expectSingleFocus(search, wrapper);
        await search.fill("FOCUS-02");
        await search.press("Tab"); await page.keyboard.press("Enter");
        await dialog.getByRole("button", { name: /Reassign Task$/ }).click();
        await expect(dialog).toHaveCount(0);
        expect(writes).toEqual([{ path: "/api/v1/workforce/tasks/701/assignment", method: "PUT", payload: { employee_id: 2, allow_unavailable_override: false, reason: "Manual reassignment by authorized manager." } }]);
        expect(errors).toEqual([]);
    });
}

test("the reassignment search keeps a visible outer focus outline in high contrast mode", async ({ page }) => {
    await page.emulateMedia({ forcedColors: "active" });
    const { dialog, search, wrapper, writes, errors } = await setup(page);
    await expect(search).toHaveCSS("box-shadow", "none");
    await expect(search).toHaveCSS("outline-style", "none");
    await expect(wrapper).toHaveCSS("outline-style", "solid");
    await expect(wrapper).toHaveCSS("outline-width", "2px");
    await search.fill("FOCUS-02");
    await expect(dialog.locator(".reassign-candidate")).toHaveCount(1);
    await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0);
    expect(writes).toEqual([]); expect(errors).toEqual([]);
});
