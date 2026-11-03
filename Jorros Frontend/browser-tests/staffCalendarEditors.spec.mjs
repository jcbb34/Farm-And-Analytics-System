import { test, expect } from "@playwright/test";

const today = "2026-11-01";
const employees = Array.from({ length: 4 }, (_, index) => ({
    id: index + 1, full_name: `Calendar Employee ${index + 1}`, employee_code: `CAL-${index + 1}`,
    position: "Farm Worker", employment_status: "Active", is_archived: false, assigned_area: "Test Pen",
}));
const admin = { id: 10, username: "calendar.admin", fullName: "Calendar Administrator", role: "System Administrator", permissions: ["*"], status: "Active" };

async function prepare(page, { viewer = false, attendanceOnly = false, failSave = false, recordedStatus = null, path = `/staff-calendar?view=day&date=${today}` } = {}) {
    const user = viewer ? { ...admin, role: "Viewer", permissions: ["workforce:view"] } : attendanceOnly ? { ...admin, role: "Attendance Clerk", permissions: ["workforce:attendance"] } : admin;
    const writes = [];
    let rejectSave = failSave;
    let shifts = [{ id: 51, employee_id: 1, work_date: today, start_time: null, end_time: null, assigned_area: "Test Pen",
        status: "Scheduled", exception_type: "Rest Day Override", exception_reason: "Previously approved rest day", notes: "Retained schedule notes" }];
    let attendance = recordedStatus ? [{ id: 91, employee_id: 1, attendance_date: today, status: recordedStatus,
        check_in_at: null, check_out_at: null, attendance_source: "Manager Assisted", notes: "Retained attendance notes" }] : [];
    await page.clock.install({ time: new Date(`${today}T00:05:00Z`) });
    await page.addInitScript((profile) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({
        accessToken: "synthetic-calendar-token", user: profile, expiresAt: Date.now() + 86400000,
    })), user);
    await page.route("**/api/v1/**", async (route) => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path === "/api/v1/roles") return route.fulfill({ json: [{ id: 1, name: user.role, permissions: user.permissions, is_active: true }] });
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/workforce/calendar/config") return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path === "/api/v1/workforce/employees") return route.fulfill({ json: employees });
        if (path === "/api/v1/workforce/calendar") return route.fulfill({ json: {
            tasks: [], leave: [], shifts, attendance,
            availability: employees.map((employee) => {
                const shift = shifts.find((row) => row.employee_id === employee.id);
                const record = attendance.find((row) => row.employee_id === employee.id);
                const working = shift?.exception_type === "Working Day Override";
                return { employee_id: employee.id, work_date: today, status: working ? "Working Day" : "Rest Day",
                    is_working_day: working, exception_type: shift?.exception_type || null,
                    attendance_status: working && record?.status !== "Day Off" ? record?.status || null : null,
                    start_time: working ? shift.start_time : null, end_time: working ? shift.end_time : null };
            }),
        } });
        if (path.startsWith("/api/v1/workforce/shifts") && ["POST", "PUT"].includes(request.method())) {
            const payload = request.postDataJSON(); writes.push({ method: request.method(), path, payload });
            if (rejectSave) return route.fulfill({ status: 422, json: { detail: "The schedule could not be saved. Please retry." } });
            const id = request.method() === "PUT" ? Number(path.split("/").at(-1)) : 52;
            shifts = [...shifts.filter((row) => row.employee_id !== payload.employee_id), { id, ...payload }];
            return route.fulfill({ json: shifts.at(-1) });
        }
        if (path.endsWith("/assisted-check-in")) {
            const id = Number(path.split("/").at(-2)), payload = request.postDataJSON();
            writes.push({ method: request.method(), path, payload });
            attendance = [{ id: 91, employee_id: id, attendance_date: today, check_in_at: `${today}T08:05:00`, status: "On Time", attendance_source: "Manager Assisted", notes: payload.notes }];
            return route.fulfill({ json: attendance[0] });
        }
        return route.fulfill({ json: [] });
    });
    await page.goto(path);
    if (viewer) await expect(page.getByRole("heading", { name: "Access Restricted", exact: true })).toBeVisible();
    else {
        await expect(page.locator(".staff-calendar-shell")).toBeVisible();
        await expect(page.locator(".calendar-skeleton")).toHaveCount(0);
    }
    return { writes, allowSave: () => { rejectSave = false; } };
}

for (const recordedStatus of ["Day Off", "Not Checked In"]) {
    test(`a working override survives reload with an older ${recordedStatus} attendance row`, async ({ page }) => {
        const { writes } = await prepare(page, { recordedStatus });
        const row = page.locator(".staff-day-table tbody tr").first();
        await expect(row.locator(".calendar-state-badge")).toHaveText("Rest Day");
        await row.getByRole("button", { name: "Day Exception", exact: true }).click();
        let dialog = page.getByRole("dialog");
        await dialog.getByRole("combobox", { name: "Schedule exception", exact: true }).selectOption("Working Day Override");
        await dialog.getByRole("textbox", { name: "Start", exact: true }).fill("08:00");
        await dialog.getByRole("textbox", { name: "End", exact: true }).fill("17:00");
        await dialog.getByRole("button", { name: "Update Shift", exact: true }).click();
        await expect(dialog).toHaveCount(0);
        await expect(row.locator(".calendar-state-badge")).toHaveText("Working Day");
        await expect(row).toContainText("08:00–17:00");
        await page.reload();
        await expect(row.locator(".calendar-state-badge")).toHaveText("Working Day");
        await row.getByRole("button", { name: /^Review attendance for / }).click();
        dialog = page.getByRole("dialog");
        await expect(dialog.locator(".attendance-detail-grid > div").filter({ hasText: "Current Attendance" })).toContainText("Not Checked In");
        await expect(dialog.getByRole("button", { name: "Assisted Check In", exact: true })).toBeEnabled();
        await expect(dialog.getByRole("textbox", { name: "Notes", exact: true })).toHaveValue("Retained attendance notes");
        await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
        await page.getByRole("tab", { name: "Month", exact: true }).click();
        const todayCell = page.locator(".staff-month-cell.today");
        await expect(todayCell.locator(".calendar-summary-chip.scheduled")).toHaveText("1 Scheduled");
        await expect(todayCell.locator(".calendar-summary-chip.rest")).toHaveText("3 Rest Day");
        expect(writes).toHaveLength(1); // A schedule change never creates a check-in.
    });
}

for (const [name, width, dark] of [["desktop", 1440, false], ["phone dark mode", 390, true]]) {
    test(`Day Exception opens the selected form immediately on ${name}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        if (dark) await page.addInitScript(() => localStorage.setItem("joross-theme", "dark"));
        const { writes } = await prepare(page);
        const trigger = page.locator(".staff-day-table").getByRole("button", { name: "Day Exception", exact: true }).first();
        await trigger.click();
        const dialog = page.getByRole("dialog");
        await expect(dialog.getByRole("heading", { name: "Edit Shift / Schedule Exception", exact: true })).toBeInViewport();
        await expect(dialog).toContainText("Sunday, November 1, 2026");
        await expect(dialog).toContainText(employees[0].full_name);
        await expect(dialog.getByRole("heading", { name: "Staffing Summary", exact: true })).toHaveCount(0);
        await expect(dialog.getByRole("heading", { name: "Employee List", exact: true })).toHaveCount(0);
        const exception = dialog.getByRole("combobox", { name: "Schedule exception", exact: true });
        await expect(exception).toHaveValue("Rest Day Override");
        await expect(exception).toBeFocused();
        await page.clock.runFor(20);
        await expect(exception).toBeFocused();
        await expect(dialog.getByRole("textbox", { name: "Start", exact: true })).toBeDisabled();
        await expect(dialog.getByRole("textbox", { name: "Exception reason", exact: true })).toHaveValue("Previously approved rest day");
        await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
        await expect(dialog).toHaveCount(0);
        await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(4);
        await page.clock.runFor(20);
        await expect(trigger).toBeFocused();
        expect(writes).toEqual([]);

        await trigger.click();
        await expect(page.getByRole("dialog").getByRole("combobox", { name: "Schedule exception", exact: true })).toBeFocused();
        await page.keyboard.press("Shift+Tab");
        await expect(page.getByRole("button", { name: "Close calendar editor", exact: true })).toBeFocused();
        await page.keyboard.press("Shift+Tab");
        await expect(page.getByRole("button", { name: "Update Shift", exact: true })).toBeFocused();
        await page.keyboard.press("Tab");
        await expect(page.getByRole("button", { name: "Close calendar editor", exact: true })).toBeFocused();
        expect(await page.getByRole("dialog").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
        if (width < 720) expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    });
}

test("saving an exception preserves its employee/date and opens assisted attendance directly", async ({ page }) => {
    const { writes } = await prepare(page);
    await page.locator(".staff-day-table").getByRole("button", { name: "Day Exception", exact: true }).first().click();
    let dialog = page.getByRole("dialog");
    await dialog.getByRole("combobox", { name: "Schedule exception", exact: true }).selectOption("Working Day Override");
    await dialog.getByRole("textbox", { name: "Start", exact: true }).fill("08:00");
    await dialog.getByRole("textbox", { name: "End", exact: true }).fill("17:00");
    await dialog.getByRole("textbox", { name: "Exception reason", exact: true }).fill("Needed for farm coverage");
    await dialog.getByRole("button", { name: "Update Shift", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(4);
    expect(writes[0]).toEqual({ method: "PUT", path: "/api/v1/workforce/shifts/51", payload: {
        employee_id: 1, work_date: today, start_time: "08:00", end_time: "17:00", assigned_area: "Test Pen", status: "Scheduled",
        notes: "Retained schedule notes", exception_type: "Working Day Override", exception_reason: "Needed for farm coverage",
    } });
    const review = page.locator(".staff-day-table").getByRole("button", { name: `Review attendance for ${employees[0].full_name}`, exact: true });
    await expect(page.locator(".staff-day-table tbody tr").first().locator(".calendar-state-badge")).toHaveText("Working Day");
    await review.click();
    await expect(dialog.getByRole("heading", { name: "Review Attendance", exact: true })).toBeInViewport();
    await expect(dialog.getByRole("textbox", { name: "Notes", exact: true })).toBeFocused();
    await expect(dialog.getByRole("heading", { name: "Employee List", exact: true })).toHaveCount(0);
    await dialog.getByRole("textbox", { name: "Notes", exact: true }).fill("Manager verified the employee on site");
    await dialog.getByRole("button", { name: "Assisted Check In", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(4);
    expect(writes[1]).toEqual({ method: "POST", path: "/api/v1/workforce/attendance/1/assisted-check-in", payload: { notes: "Manager verified the employee on site" } });
});

test("a failed new exception stays editable and retries without losing the selected employee", async ({ page }) => {
    const { writes, allowSave } = await prepare(page, { failSave: true });
    await page.locator(".staff-day-table").getByRole("button", { name: "Day Exception", exact: true }).nth(1).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(employees[1].full_name);
    await expect(dialog.getByRole("heading", { name: "Add Shift / Schedule Exception", exact: true })).toBeInViewport();
    await dialog.getByRole("combobox", { name: "Schedule exception", exact: true }).selectOption("Working Day Override");
    await dialog.getByRole("textbox", { name: "Start", exact: true }).fill("08:00");
    await dialog.getByRole("textbox", { name: "End", exact: true }).fill("17:00");
    await dialog.getByRole("textbox", { name: "Notes", exact: true }).fill("Keep this entered note");
    await expect(dialog.getByRole("textbox", { name: "Notes", exact: true })).toBeFocused();
    await dialog.getByRole("button", { name: "Add Shift", exact: true }).click();
    await expect(page.getByText("The schedule could not be saved. Please retry.", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("textbox", { name: "Notes", exact: true })).toHaveValue("Keep this entered note");
    await expect(dialog.getByRole("textbox", { name: "Start", exact: true })).toHaveValue("08:00");
    await expect(dialog.getByRole("combobox", { name: "Schedule exception", exact: true })).toHaveValue("Working Day Override");
    allowSave();
    await dialog.getByRole("button", { name: "Add Shift", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(4);
    expect(writes).toHaveLength(2);
    expect(writes[1]).toEqual(writes[0]);
    expect(writes[0].payload.employee_id).toBe(2);
});

test("an account without attendance or workforce management access cannot reach the editors", async ({ page }) => {
    const { writes } = await prepare(page, { viewer: true });
    await expect(page.getByRole("button", { name: "Day Exception", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Review attendance for / })).toHaveCount(0);
    expect(writes).toEqual([]);
});

for (const [name, width, dark] of [["desktop", 1440, false], ["phone dark mode", 390, true]]) {
    test(`calendar navigation and date selection use Day view without a popup on ${name}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        if (dark) await page.addInitScript(() => localStorage.setItem("joross-theme", "dark"));
        await prepare(page, { path: `/staff-calendar?view=month&date=${today}` });
        for (const view of ["Day", "Week", "Month", "Day"]) {
            await page.getByRole("tab", { name: view, exact: true }).click();
            await expect(page.getByRole("tab", { name: view, exact: true })).toHaveAttribute("aria-selected", "true");
            await expect(page.getByRole("dialog")).toHaveCount(0);
            await page.getByRole("button", { name: "Today", exact: true }).click();
            await expect(page.getByRole("dialog")).toHaveCount(0);
        }
        await page.getByRole("button", { name: /Previous$/ }).click();
        await expect(page).toHaveURL(/date=2026-10-31/);
        await expect(page.getByRole("dialog")).toHaveCount(0);
        await page.getByRole("button", { name: /^Next/ }).click();
        await expect(page).toHaveURL(/date=2026-11-01/);
        await expect(page.getByRole("dialog")).toHaveCount(0);
        await page.getByRole("button", { name: "Today", exact: true }).click();
        await page.getByRole("combobox", { name: "Employee", exact: true }).selectOption("2");
        await page.getByRole("tab", { name: "Month", exact: true }).click();
        await expect(page.locator(".calendar-skeleton")).toHaveCount(0);
        await page.getByRole("button", { name: "Open day view for November 1, 2026", exact: true }).click();
        await expect(page.getByRole("tab", { name: "Day", exact: true })).toHaveAttribute("aria-selected", "true");
        await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(1);
        await expect(page.locator(".staff-day-table")).toContainText(employees[1].full_name);
        await expect(page.getByRole("combobox", { name: "Employee", exact: true })).toHaveValue("2");
        await expect(page.getByRole("dialog")).toHaveCount(0);
        await page.getByRole("tab", { name: "Week", exact: true }).click();
        await expect(page.locator(".calendar-skeleton")).toHaveCount(0);
        await page.getByRole("button", { name: "Open day view for November 1, 2026", exact: true }).click();
        await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(1);
        await expect(page.getByRole("dialog")).toHaveCount(0);
        await expect(page.getByRole("heading", { name: "Staffing Summary", exact: true })).toHaveCount(0);
        await expect(page.getByRole("button", { name: "View Staffing Details", exact: true })).toHaveCount(0);
    });

    test(`Review Attendance is explicit and Notes matches the other textarea on ${name}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        if (dark) await page.addInitScript(() => localStorage.setItem("joross-theme", "dark"));
        const { writes } = await prepare(page);
        const table = page.locator(".staff-day-table");
        await expect(table.getByRole("button", { name: /^Review attendance for / })).toHaveCount(4);
        await expect(table.getByRole("button", { name: "Day Exception", exact: true })).toHaveCount(4);
        await expect(table.locator("button.calendar-state-badge")).toHaveCount(0);
        await table.getByRole("button", { name: `Review attendance for ${employees[0].full_name}`, exact: true }).click();
        let dialog = page.getByRole("dialog");
        await expect(dialog.getByRole("heading", { name: "Review Attendance", exact: true })).toBeInViewport();
        const notes = dialog.getByRole("textbox", { name: "Notes", exact: true });
        const reason = dialog.getByRole("textbox", { name: "Correction Reason *", exact: true });
        await expect(notes).toBeFocused();
        if (dark) await expect(dialog.locator(".attendance-detail-grid > div").first()).not.toHaveCSS("background-color", "rgb(255, 255, 255)");
        const readStyle = (node) => {
            const style = getComputedStyle(node);
            return Object.fromEntries(["minHeight", "paddingTop", "paddingLeft", "borderRadius", "borderTopWidth", "backgroundColor", "color", "fontSize", "fontFamily"].map((key) => [key, style[key]]));
        };
        expect(await notes.evaluate(readStyle)).toEqual(await reason.evaluate(readStyle));
        const notesBox = await notes.boundingBox(), reasonBox = await reason.boundingBox();
        expect(notesBox.width).toBeCloseTo(reasonBox.width, 0);
        const noteLabel = await notes.evaluate((node) => { const label = node.closest("label").querySelector("span").getBoundingClientRect(); return { bottom: label.bottom, left: label.left }; });
        expect(notesBox.y).toBeGreaterThanOrEqual(noteLabel.bottom);
        expect(notesBox.x).toBeCloseTo(noteLabel.left, 0);
        await expect(dialog.getByText(/Working Day Override required/)).toBeVisible();
        await expect(dialog.getByRole("button", { name: "Assisted Check In", exact: true })).toBeDisabled();
        await expect(dialog.getByRole("button", { name: "Mark Absent", exact: true })).toBeDisabled();
        await dialog.getByRole("button", { name: "Create Working Day Override", exact: true }).click();
        dialog = page.getByRole("dialog");
        await expect(dialog.getByRole("combobox", { name: "Schedule exception", exact: true })).toHaveValue("Working Day Override");
        await expect(dialog.getByRole("combobox", { name: "Schedule exception", exact: true })).toBeFocused();
        await expect(dialog).toContainText(employees[0].full_name);
        await expect(dialog.getByRole("textbox", { name: "Start", exact: true })).toBeEnabled();
        await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
        await expect(page.getByRole("dialog")).toHaveCount(0);
        expect(writes).toEqual([]);
        if (width < 720) expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    });
}

test("old selectedDate links open the right Day view and task return links keep the filters", async ({ page }) => {
    await prepare(page, { path: `/staff-calendar?view=week&date=2026-10-28&selectedDate=${today}&employeeId=2&availability=all` });
    await expect(page.getByRole("tab", { name: "Day", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(1);
    await expect(page.locator(".staff-day-table")).toContainText(employees[1].full_name);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get("date")).toBe(today);
    expect(new URL(page.url()).searchParams.has("selectedDate")).toBe(false);
    await page.locator(".staff-day-table").getByRole("button", { name: "0", exact: true }).click();
    await expect(page).toHaveURL(/\/task-management\?/);
    const returnTo = new URL(page.url()).searchParams.get("returnTo");
    const restored = new URL(returnTo, "http://127.0.0.1");
    expect(restored.pathname).toBe("/staff-calendar");
    expect(restored.searchParams.get("view")).toBe("day");
    expect(restored.searchParams.get("date")).toBe(today);
    expect(restored.searchParams.get("employeeId")).toBe("2");
    expect(restored.searchParams.has("selectedDate")).toBe(false);
    await page.goto(returnTo);
    await expect(page.locator(".staff-day-table tbody tr")).toHaveCount(1);
    await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("attendance-only permission exposes review but no schedule-override action", async ({ page }) => {
    await prepare(page, { attendanceOnly: true });
    await expect(page.locator(".staff-day-table").getByRole("button", { name: /^Review attendance for / })).toHaveCount(4);
    await expect(page.getByRole("button", { name: "Day Exception", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: `Review attendance for ${employees[0].full_name}`, exact: true }).click();
    await expect(page.getByRole("dialog").getByText(/Working Day Override required/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Create Working Day Override", exact: true })).toHaveCount(0);
});

test("a future day remains a normal calendar view with attendance review disabled", async ({ page }) => {
    const { writes } = await prepare(page, { path: "/staff-calendar?view=day&date=2026-11-02" });
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const reviews = page.locator(".staff-day-table").getByRole("button", { name: /^Review attendance for / });
    await expect(reviews).toHaveCount(4);
    for (const button of await reviews.all()) await expect(button).toBeDisabled();
    await page.getByRole("button", { name: "Day Exception", exact: true }).nth(1).click();
    await expect(page.getByRole("dialog")).toContainText("Monday, November 2, 2026");
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(writes).toEqual([]);
});
