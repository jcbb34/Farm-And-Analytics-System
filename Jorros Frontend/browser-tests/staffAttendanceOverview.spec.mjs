import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { serveSessionPolicy } from "./helpers/serveSessionPolicy.mjs";
const TODAY = "2026-11-05";
const staff = Array.from({ length: 8 }, (_, i) => ({ id: i + 1, full_name: `Attendance Worker ${i + 1}`, employee_code: `ATT-${i + 1}`, employment_status: "Active", position: "Farm Worker", is_archived: false }));
const admin = { id: 10, username: "attendance.admin", fullName: "Attendance Administrator", role: "System Administrator", permissions: ["*"], status: "Active" };
async function setup(page, { path = "/staff-calendar", permission = "admin", fail = "", dark = false, saveDelay = 0 } = {}) {
    let today = TODAY, saved = null;
    let releaseSave; const saveGate = new Promise((resolve) => { releaseSave = resolve; });
    const failures = new Set(fail ? [fail] : []), writes = [], requests = [];
    const user = permission === "attendance" ? { ...admin, role: "Attendance Clerk", permissions: ["workforce:attendance"] } : permission === "employee" ? { ...admin, role: "Employee", permissions: ["tasks:own"] } : admin;
    await page.clock.install({ time: new Date("2026-11-05T08:30:00Z") });
    await page.addInitScript(({ user, dark }) => {
        sessionStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-attendance-token", user, expiresAt: Date.now() + 86400000 }));
        localStorage.setItem("joross-theme", dark ? "dark" : "light");
    }, { user, dark });
    const payload = (from, to) => {
        const dates = [];
        for (let d = new Date(`${from}T00:00:00Z`); d <= new Date(`${to}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1)) dates.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`);
        const result = { tasks: [], attendance: [], availability: [], shifts: [], leave: [], farm_events: [] };
        for (const date of dates) {
            const isToday = date === today;
            for (const employee of staff) {
                const id = employee.id;
                const status = isToday ? ({ 1: "Available", 2: "Working Day", 3: "Possible Absence", 4: "Rest Day", 5: "On Leave", 6: "Available", 7: "Unavailable", 8: "Work Suspended" })[id] : date > today ? "Scheduled" : "Working Day";
                const recordStatus = isToday ? ({ 1: "On Time", 6: "Missing Check Out", 7: "Absent" })[id] : date < today && id === 1 ? "Checked Out" : null;
                result.availability.push({ employee_id: id, work_date: date, status, is_working_day: ![4, 5, 8].includes(id), attendance_status: recordStatus || null, start_time: "08:00:00", end_time: id === 6 ? "12:00:00" : "17:00:00", attendance_suspended_now: id === 8 });
                if (recordStatus) result.attendance.push({ id: 100 + id, employee_id: id, attendance_date: date, status: recordStatus, check_in_at: id === 7 ? null : `${date}T08:05:00`, check_out_at: recordStatus === "Checked Out" ? `${date}T17:00:00` : null, notes: "Attendance note for testing", attendance_source: "Employee Self Check In", audit: [{ id: 900 + id, action: "Check In", actor_name: employee.full_name, created_at: `${date}T08:05:00` }] });
                if (isToday && id === 5) result.leave.push({ id: 70, employee_id: 5, start_date: date, end_date: date, status: "Approved", leave_type: "Personal" });
            }
            if (isToday) result.tasks.push({ id: 501, name: "Feeding coverage", activity_date: date, status: "Pending", assigned_employee_id: 7, needs_reassignment: true }, { id: 502, name: "Unassigned watering", activity_date: date, status: "Pending", assigned_employee_id: null, needs_reassignment: true });
        }
        if (saved && from <= saved.attendance_date && to >= saved.attendance_date) {
            result.attendance = result.attendance.filter((r) => r.employee_id !== saved.employee_id || r.attendance_date !== saved.attendance_date).concat(saved);
            result.availability = result.availability.map((r) => r.employee_id === saved.employee_id && r.work_date === saved.attendance_date ? { ...r, status: "Available", attendance_status: saved.status } : r);
        }
        return result;
    };
    await page.route("**/api/v1/**", async (route) => {
        if (await serveSessionPolicy(route, page)) return;
        const request = route.request(), url = new URL(request.url()), pathname = url.pathname;
        if (pathname === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (pathname === "/api/v1/roles") return route.fulfill({ json: [{ id: 1, name: user.role, permissions: user.permissions, is_active: true }] });
        if (pathname.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (pathname === "/api/v1/workforce/calendar/config") return failures.has("config") ? route.fulfill({ status: 503, json: { detail: "Farm date unavailable" } }) : route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (pathname === "/api/v1/workforce/employees") return failures.has("employees") ? route.fulfill({ status: 503, json: { detail: "Employee list unavailable" } }) : route.fulfill({ json: staff });
        if (pathname === "/api/v1/workforce/calendar") {
            const from = url.searchParams.get("date_from"), to = url.searchParams.get("date_to"); requests.push({ from, to });
            if (failures.has("calendar") || (failures.has("today") && from === today && to === today)) return route.fulfill({ status: 503, json: { detail: "Attendance service unavailable" } });
            return route.fulfill({ json: payload(from, to) });
        }
        if (request.method() !== "GET" && pathname.startsWith("/api/v1/workforce/attendance/")) {
            const data = request.postDataJSON(); writes.push({ method: request.method(), path: pathname, data });
            if (saveDelay) await saveGate;
            if (failures.has("save")) return route.fulfill({ status: 422, json: { detail: "Attendance could not be saved. Please retry." } });
            const id = Number(pathname.split("/")[5]); saved = { id: 100 + id, employee_id: id, attendance_date: today, status: "On Time", check_in_at: `${today}T16:30:00`, notes: data.notes, attendance_source: "Manager Assisted" };
            return route.fulfill({ json: saved });
        }
        return route.fulfill({ json: [] });
    });
    await page.goto(path); await page.mouse.move(1100, 10);
    if (permission !== "employee") {
        await expect(page.locator(".staff-attendance-overview")).toBeVisible();
        if (!fail) await expect(page.locator(".staff-attendance-overview")).toHaveAttribute("aria-busy", "false");
    }
    return { failures, writes, requests, releaseSave, setToday: (date) => { today = date; } };
}
const panel = (page) => page.locator(".staff-attendance-overview");
const rows = (page) => page.locator(".staff-day-table tbody tr");
async function openReview(page, employeeName) {
    await page.getByRole("button", { name: `View attendance for ${employeeName}`, exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Read-only attendance details");
    await expect(dialog.getByRole("textbox")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Review / Correct Attendance", exact: true }).click();
    return dialog;
}

test("attendance is the default with accurate scheduled counts and farm-local clock times", async ({ page }) => {
    await setup(page); await expect(panel(page).getByRole("button", { name: /Refresh/i })).toHaveCount(0); await expect(page.getByRole("tab", { name: "Day", exact: true })).toHaveAttribute("aria-selected", "true"); await expect(rows(page)).toHaveCount(8);
    for (const [label, count] of [["Present", 2], ["Not Checked In", 2], ["On Leave", 1], ["Needs Coverage", 2]]) await expect(panel(page).getByRole("button", { name: new RegExp(`^${label}: ${count}\\.`) })).toBeEnabled();
    await expect(rows(page).first()).toContainText("08:05"); await expect(rows(page).nth(3)).toContainText("Not scheduled to check in"); await expect(rows(page).nth(6).locator(".calendar-state-badge")).toHaveText("Absent");
});
test("count filters show today's employees without shrinking the summary and Clear Filters restores the list", async ({ page }) => {
    const { writes } = await setup(page); await panel(page).getByRole("button", { name: /^Not Checked In: 2\./ }).click(); await expect(rows(page)).toHaveCount(2); await expect(page.getByRole("combobox", { name: "Status", exact: true })).toHaveValue("not-checked-in");
    await panel(page).getByRole("button", { name: /^Present: 2\./ }).click(); await expect(rows(page)).toHaveCount(2); await expect(rows(page).nth(1)).toContainText("Missing Check Out"); await page.getByRole("button", { name: "Clear Filters", exact: true }).click(); await expect(rows(page)).toHaveCount(8); expect(writes).toEqual([]);
});
test("today is independent of a historical month, uses bounded requests and has an explicit return button", async ({ page }) => {
    const { requests, writes } = await setup(page, { path: "/staff-calendar?view=month&date=2026-03-04" }); await expect(panel(page)).toContainText("Nov 5, 2026"); await expect(panel(page).getByRole("button", { name: /^Present: 2\./ })).toBeEnabled();
    expect(requests.some((r) => r.from === TODAY && r.to === TODAY)).toBe(true); for (const r of requests) expect((new Date(r.to) - new Date(r.from)) / 86400000).toBeLessThanOrEqual(42);
    await panel(page).getByRole("button", { name: "View Today’s Attendance", exact: true }).click(); await expect(rows(page)).toHaveCount(8); await expect(page.getByLabel("Date", { exact: true })).toHaveValue(TODAY); expect(writes).toEqual([]);
});
test("review details distinguish warnings from confirmed absence and include every unassigned task", async ({ page }) => {
    const { writes } = await setup(page); const review = page.locator(".staff-attendance-review"); await review.locator("summary").click(); await expect(review.locator("li")).toHaveCount(4); await expect(review).toContainText("verify before marking absent"); await expect(review).toContainText("Missing check-out"); await expect(review).toContainText("Unassigned watering");
    await review.getByRole("button", { name: "View attendance", exact: true }).first().click(); await expect(page.getByRole("dialog")).toContainText("Read-only attendance details"); await expect(page.getByRole("dialog").getByRole("textbox")).toHaveCount(0); await page.keyboard.press("Escape"); await expect(page.getByRole("dialog")).toHaveCount(0); expect(writes).toEqual([]);
});
test("employee names open read-only reports with collapsed notes and history", async ({ page }) => {
    const { writes } = await setup(page); await rows(page).first().getByRole("button", { name: staff[0].full_name, exact: true }).click(); const dialog = page.getByRole("dialog"); await expect(dialog).toContainText("08:05"); await expect(dialog.getByText("Attendance note for testing", { exact: true })).not.toBeVisible(); await dialog.getByText("Notes and correction history", { exact: true }).click(); await expect(dialog).toContainText("Attendance note for testing"); await expect(dialog).toContainText("Check In · Attendance Worker 1"); await dialog.getByRole("button", { name: "Close calendar editor", exact: true }).click(); await expect(dialog).toHaveCount(0); expect(writes).toEqual([]);
});
test("day rows have one attendance action and no expandable Details column", async ({ page }) => {
    const { writes } = await setup(page);
    const table = page.locator(".staff-day-table");
    await expect(table.getByRole("columnheader")).toHaveCount(5);
    await expect(table.getByRole("columnheader", { name: "Details", exact: true })).toHaveCount(0);
    await expect(table.locator("details, summary")).toHaveCount(0);
    await expect(table.getByText("View attendance history", { exact: true })).toHaveCount(0);
    await expect(table.getByText("Review Attendance", { exact: true })).toHaveCount(0);
    for (const row of await rows(page).all()) {
        await expect(row.getByRole("cell")).toHaveCount(5);
        await expect(row.getByRole("button", { name: /^View attendance for / })).toHaveCount(1);
    }
    await rows(page).first().getByRole("button", { name: /^View attendance for / }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Read-only attendance details");
    await expect(dialog).toContainText("08:00–17:00");
    await expect(dialog.getByRole("button", { name: "Active tasks: 0", exact: true })).toBeVisible();
    await expect(dialog).toContainText("No coverage issue");
    await expect(dialog.getByRole("textbox")).toHaveCount(0);
    expect(writes).toEqual([]);
});
for (const [employeeId, link, query] of [
    [7, /Needs Coverage.*Feeding coverage/, { tab: "tasks", assignmentState: "needs-reassignment", date: TODAY }],
    [5, /^On Leave$/, { tab: "leave", leaveRequestId: "70" }],
]) test(`attendance dialog preserves ${employeeId === 7 ? "coverage" : "leave"} navigation and return filters`, async ({ page }) => {
    const { writes } = await setup(page, { path: `/staff-calendar?view=day&date=${TODAY}&employeeId=${employeeId}` });
    await rows(page).first().getByRole("button", { name: /^View attendance for / }).click();
    await page.getByRole("dialog").getByRole("button", { name: link }).click();
    await expect(page).toHaveURL(/\/task-management\?/);
    const params = new URL(page.url()).searchParams;
    for (const [key, value] of Object.entries(query)) expect(params.get(key)).toBe(value);
    const returnTo = params.get("returnTo"), restored = new URL(returnTo, "http://127.0.0.1");
    expect(restored.searchParams.get("date")).toBe(TODAY);
    expect(restored.searchParams.get("employeeId")).toBe(String(employeeId));
    await page.goto(returnTo);
    await expect(rows(page)).toHaveCount(1);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(writes).toEqual([]);
});
test("future attendance history is keyboard accessible while corrections stay disabled", async ({ page }) => {
    const { writes } = await setup(page, { path: "/staff-calendar?view=day&date=2026-11-06" });
    const trigger = rows(page).first().getByRole("button", { name: /^View attendance for / });
    await trigger.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog"), summary = dialog.locator("summary");
    await dialog.getByRole("button", { name: "Active tasks: 0", exact: true }).focus();
    await page.keyboard.press("Tab"); await expect(summary).toBeFocused();
    await page.keyboard.press("Enter"); await expect(summary.locator("..")).toHaveAttribute("open", "");
    await page.keyboard.press("Tab"); await expect(dialog.getByRole("button", { name: "Close calendar editor", exact: true })).toBeFocused();
    await page.keyboard.press("Escape"); await page.clock.runFor(20);
    await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
    expect(writes).toEqual([]);
});
for (const failure of ["calendar", "employees", "config"]) test(`${failure} errors show unavailable counts rather than zero and can retry`, async ({ page }) => {
    const { failures } = await setup(page, { fail: failure }); await expect(panel(page)).toContainText("Unable to load attendance"); await expect(panel(page).getByRole("button", { name: "Present: unavailable", exact: true })).toBeDisabled(); await expect(panel(page).locator(".staff-attendance-count strong").first()).toHaveText("—"); failures.clear(); await panel(page).getByRole("button", { name: "Retry attendance", exact: true }).click(); await expect(panel(page).getByRole("button", { name: /^Present: 2\./ })).toBeEnabled(); await expect(rows(page)).toHaveCount(8);
});
test("a today-only failure leaves the historical calendar available", async ({ page }) => {
    const { failures } = await setup(page, { path: "/staff-calendar?view=month&date=2026-03-04", fail: "today" }); await expect(page.locator(".staff-month-cell")).not.toHaveCount(0); await expect(panel(page)).toContainText("Unable to load attendance"); failures.clear(); await panel(page).getByRole("button", { name: "Retry attendance", exact: true }).click(); await expect(panel(page).getByRole("button", { name: /^Present: 2\./ })).toBeEnabled(); await expect(page.getByRole("tab", { name: "Month", exact: true })).toHaveAttribute("aria-selected", "true");
});
test("failed saves preserve input and retry once with the same body and selected employee/date", async ({ page }) => {
    const { failures, writes, releaseSave } = await setup(page, { path: `/staff-calendar?view=day&date=${TODAY}&employeeId=2`, fail: "save", saveDelay: 250 }); const dialog = await openReview(page, staff[1].full_name), notes = dialog.getByRole("textbox", { name: "Notes", exact: true }); await notes.fill("Verified on site; keep this note"); const submit = dialog.getByRole("button", { name: "Assisted Check In", exact: true }); await submit.click(); await expect(submit).toBeDisabled(); await expect(notes).toBeDisabled(); releaseSave(); await expect(dialog.getByRole("alert")).toContainText("Attendance could not be saved"); await expect(notes).toHaveValue("Verified on site; keep this note"); expect(writes).toHaveLength(1); failures.clear(); await submit.click(); await expect(dialog).toHaveCount(0); await expect(page.getByRole("status").filter({ hasText: "Attendance updated." })).toBeVisible(); await expect(page.getByRole("combobox", { name: "Employee", exact: true })).toHaveValue("2"); await expect(page.getByLabel("Date", { exact: true })).toHaveValue(TODAY); expect(writes).toHaveLength(2); expect(writes[1]).toEqual(writes[0]);
});
test("closing and background updates preserve filters, scroll and compact rows", async ({ page }) => {
    await setup(page, { path: `/staff-calendar?view=day&date=${TODAY}&employeeId=1` });
    await openReview(page, staff[0].full_name);
    await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
    await page.clock.runFor(20);
    await expect(page.getByRole("button", { name: `View attendance for ${staff[0].full_name}`, exact: true })).toBeFocused();
    const before = await page.evaluate(() => scrollY);
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("joross:modules-updated", { detail: { modules: ["calendar"] } })));
    await page.clock.runFor(60050);
    await expect(panel(page)).toHaveAttribute("aria-busy", "false");
    await expect(page.getByRole("combobox", { name: "Employee", exact: true })).toHaveValue("1");
    await expect(rows(page)).toHaveCount(1); await expect(rows(page).locator("details")).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(Math.abs(await page.evaluate(() => scrollY) - before)).toBeLessThanOrEqual(2);
});
test("attendance clerks cannot edit schedules and employee accounts cannot open Staff Calendar", async ({ page, browser }) => {
    const clerk = await setup(page, { permission: "attendance" }); await expect(page.getByRole("button", { name: "Day Exception", exact: true })).toHaveCount(0); await expect(page.getByRole("button", { name: /^View attendance for / })).toHaveCount(8); await openReview(page, staff[0].full_name); await expect(page.getByRole("dialog").getByRole("textbox", { name: "Notes", exact: true })).toBeVisible(); expect(clerk.writes).toEqual([]); const context = await browser.newContext(), employeePage = await context.newPage(); const { writes } = await setup(employeePage, { permission: "employee" }); await expect(employeePage.getByRole("heading", { name: "Access Restricted", exact: true })).toBeVisible(); await expect(employeePage.locator(".staff-attendance-overview")).toHaveCount(0); expect(writes).toEqual([]); await context.close();
});
test("keyboard controls work and future days expose schedules without attendance editing", async ({ page }) => {
    const { writes } = await setup(page); await page.getByRole("tab", { name: "Day", exact: true }).focus(); await page.keyboard.press("ArrowLeft"); await expect(page.getByRole("tab", { name: "Week", exact: true })).toBeFocused(); await page.getByRole("tab", { name: "Day", exact: true }).click(); await page.getByLabel("Date", { exact: true }).fill("2026-11-06"); await expect(rows(page)).toHaveCount(8); await expect(rows(page).first().locator(".calendar-state-badge")).toHaveText("Scheduled"); await expect(page.getByRole("button", { name: /^View attendance for / })).toHaveCount(8); await rows(page).first().getByRole("button", { name: /^View attendance for / }).click(); await expect(page.getByRole("dialog").getByRole("button", { name: "Review / Correct Attendance", exact: true })).toBeDisabled(); await expect(page.getByRole("dialog").getByRole("textbox")).toHaveCount(0); await page.keyboard.press("Escape"); await expect(rows(page).first().locator(".staff-clock-times")).not.toContainText("08:05"); await page.getByRole("button", { name: "Today", exact: true }).click(); await expect(page.getByLabel("Date", { exact: true })).toHaveValue(TODAY); expect(writes).toEqual([]);
});
for (const width of [320, 390, 768, 1440]) for (const dark of [false, true]) test(`attendance fits ${width}px in ${dark ? "dark" : "light"} mode with readable text and usable actions`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 }); await setup(page, { dark }); await expect(page.locator("html")).toHaveAttribute("data-theme", dark ? "dark" : "light");
    if (process.env.STAFF_QA_DIR) { mkdirSync(process.env.STAFF_QA_DIR, { recursive: true }); await page.screenshot({ path: `${process.env.STAFF_QA_DIR}/attendance-${width}-${dark ? "dark" : "light"}.png`, fullPage: true }); }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    if (width === 1440) {
        const heights = await page.locator(".staff-attendance-count").evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect().height));
        expect(Math.max(...heights)).toBeLessThanOrEqual(112);
        expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
    }
    for (const selector of [".staff-attendance-overview", ".staff-calendar-toolbar", ".staff-day-table"]) expect(await page.locator(selector).evaluate((el) => el.scrollWidth <= el.clientWidth + 1), selector).toBe(true);
    if (width <= 720) expect(await panel(page).evaluate((el) => el.getBoundingClientRect().left)).toBeGreaterThanOrEqual(await page.locator(".sidebar").evaluate((el) => el.getBoundingClientRect().right));
    for (const selector of [".staff-attendance-count-label", ".staff-attendance-heading h2", ".calendar-employee-link", ".staff-day-time-note", ".calendar-legend"]) {
        const contrast = await page.locator(selector).first().evaluate((el) => {
            const lum = (c) => c.match(/[\d.]+/g).slice(0,3).map(Number).map((v) => { const s=v/255; return s<=.04045?s/12.92:((s+.055)/1.055)**2.4; }).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
            let p=el; while(p && ["rgba(0, 0, 0, 0)", "transparent"].includes(getComputedStyle(p).backgroundColor))p=p.parentElement;
            const a=lum(getComputedStyle(el).color),b=lum(getComputedStyle(p).backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        }); expect(contrast, selector).toBeGreaterThanOrEqual(4.5);
    }
    await panel(page).getByRole("button", { name: /^Not Checked In: 2\./ }).click(); await expect(rows(page)).toHaveCount(2); await rows(page).first().getByRole("button", { name: /^View attendance for / }).click(); await expect(page.getByRole("dialog")).toBeVisible(); expect(await page.getByRole("dialog").evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true); await expect(page.getByRole("dialog").getByRole("button", { name: /^Active tasks:/ })).toBeVisible(); await page.getByRole("dialog").getByRole("button", { name: "Review / Correct Attendance", exact: true }).click(); expect(await page.getByRole("dialog").evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true); await page.getByRole("button", { name: "Close calendar editor", exact: true }).click(); await expect(page.getByRole("dialog")).toHaveCount(0);
});
test("coverage count reveals unassigned work and opens the exact task", async ({ page }) => {
    const { writes } = await setup(page); await panel(page).getByRole("button", { name: /^Needs Coverage: 2\./ }).click(); const review = page.locator(".staff-attendance-review"); await expect(review.locator("li")).toHaveCount(2); await expect(review).toContainText("Unassigned watering"); await review.getByRole("button", { name: "Show all review items", exact: true }).click(); await expect(review.locator("li")).toHaveCount(4); await review.getByRole("button", { name: "Resolve assignment", exact: true }).last().click(); await expect(page).toHaveURL(/taskId=502/); expect(new URL(page.url()).searchParams.get("date")).toBe(TODAY); expect(writes).toEqual([]);
});
test("the server farm date updates without moving a deliberately selected historical date", async ({ page }) => {
    const { setToday } = await setup(page, { path: "/staff-calendar?view=day&date=2026-11-03&employeeId=1" }); setToday("2026-11-06"); await page.clock.runFor(60050); await expect(panel(page)).toContainText("Nov 6, 2026"); await expect(page.getByLabel("Date", { exact: true })).toHaveValue("2026-11-03"); await expect(page.getByRole("combobox", { name: "Employee", exact: true })).toHaveValue("1"); await expect(panel(page).getByRole("button", { name: /^Present: 1\./ })).toBeEnabled();
});
test("phone touch controls filter, open read-only history and close with X", async ({ browser }) => {
    const context=await browser.newContext({ viewport:{width:390,height:844}, hasTouch:true, isMobile:true }); const page=await context.newPage(); const {writes}=await setup(page,{dark:true}); await panel(page).getByRole("button",{name:/^Present: 2\./}).tap(); await expect(rows(page)).toHaveCount(2); await rows(page).first().getByRole("button",{name:staff[0].full_name,exact:true}).tap(); await expect(page.getByRole("dialog")).toContainText("Read-only attendance details"); await page.getByRole("dialog").getByText("Notes and correction history",{exact:true}).tap(); await expect(page.getByRole("dialog")).toContainText("Attendance note for testing"); await page.getByRole("button",{name:"Close calendar editor",exact:true}).tap(); await expect(page.getByRole("dialog")).toHaveCount(0); expect(writes).toEqual([]); await context.close();
});
