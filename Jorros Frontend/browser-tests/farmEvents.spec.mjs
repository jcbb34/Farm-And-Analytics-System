import { test, expect } from "@playwright/test";
const today = "2026-11-02";
const admin = { id: 10, username: "event.admin", fullName: "Farm Administrator", role: "System Administrator", permissions: ["*"], status: "Active" };
const employees = [{ id: 1, full_name: "Event Employee", employment_status: "Active", is_archived: false, assigned_area: "Field A", position: "Farm Worker" }];
const eventSeed = { id: 5, title: "Farm weather suspension", kind: "Emergency Suspension", status: "Active", starts_at: `${today}T08:00:00+08:00`, ends_at: `${today}T12:00:00+08:00`, scope_type: "All", scope_values: [], reason: "Official advisory reviewed", instructions: "Follow the approved farm preparation plan.", source_name: "LGU advisory", source_reference: "Bulletin 1", version: 2, notice_version: 1, approved_at: `${today}T08:00:00+08:00`, ended_at: null, requires_reopening: true, can_edit: false, can_manage: true, can_approve: true, checklist: [], reports: [], audit: [], acknowledgements: [], can_acknowledge: false, acknowledged: false };
async function prepare(page, { employee = false, preexisting = false, rejectFirst = false } = {}) {
    const user = employee ? { ...admin, id: 20, role: "Employee", permissions: ["workforce:submit"] } : admin;
    const writes = []; let event = preexisting ? { ...eventSeed, can_manage: !employee, can_approve: !employee, can_acknowledge: employee } : null; let reject = rejectFirst;
    let taskRow = { id: 9, activity_id: 71, name: "Morning Feeding", code: "ACT-71", date: today, start_time: "08:00", status: "Pending", assigned_to: "Event Employee", resolution: "Held", version: 1, essential_review: true, time_sensitive: true, original: { date: today, start_time: "08:00", status: "Pending" }, can_review: true };
    const work = { id: 71, name: "Morning Feeding", activity_code: "ACT-71", activity_date: today, start_time: "08:00", status: "Pending", priority: "Medium", assigned_employee_id: 1, location: "Field A", work_suspended: true, suspension_holds: [{ id: 9, event_id: 5, title: eventSeed.title, state: "Held" }] };
    await page.clock.install({ time: new Date(`${today}T01:00:00Z`) });
    await page.addInitScript((profile) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-event-token", user: profile, expiresAt: Date.now() + 86400000 })), user);
    await page.route("**/api/v1/**", async (route) => {
        const req = route.request(), path = new URL(req.url()).pathname, body = req.method() === "GET" ? null : req.postDataJSON();
        if (req.method() !== "GET") writes.push({ path, body });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path === "/api/v1/roles") return route.fulfill({ json: [{ id: 1, name: user.role, permissions: user.permissions, is_active: true }] });
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path.endsWith("/workforce/employees")) return route.fulfill({ json: employees });
        if (path.endsWith("/workforce/calendar")) return route.fulfill({ json: { tasks: [], leave: [], shifts: [], attendance: [], availability: [], farm_events: event ? [event] : [] } });
        if (path === "/api/v1/farm-events" && req.method() === "POST") {
            if (reject) { reject = false; return route.fulfill({ status: 503, json: { detail: "Temporary save failure" } }); }
            event = { ...eventSeed, ...body, id: 5, status: "Draft", version: 1, approved_at: null, requires_reopening: false, can_edit: true };
            return route.fulfill({ status: 201, json: event });
        }
        if (path === "/api/v1/farm-events") return route.fulfill({ json: event ? [event] : [] });
        if (path.endsWith("/farm-events/5/preview")) return route.fulfill({ json: { preview_token: "preview-123", employee_count: 1, task_count: 1, essential_task_count: 1, protected_task_count: 2, employees, tasks: [{ id: 71, name: "Morning Feeding", date: today, essential: true }], overlaps: [] } });
        if (path.endsWith("/farm-events/5/approve")) { event = { ...event, status: "Active", version: 2, approved_at: `${today}T09:00:00+08:00`, requires_reopening: event.kind === "Emergency Suspension", can_edit: false }; return route.fulfill({ json: event }); }
        if (path.endsWith("/farm-events/5/acknowledge")) { event = { ...event, acknowledged: true }; return route.fulfill({ json: event }); }
        if (path.endsWith("/farm-events/5/tasks/9/review")) { taskRow = { ...taskRow, version: 2, resolution: body.action, review_reason: body.reason }; return route.fulfill({ json: taskRow }); }
        if (path.endsWith("/farm-events/5/tasks")) return route.fulfill({ json: { items: [taskRow], total: 1, offset: 0 } });
        if (path.endsWith("/farm-events/5")) return route.fulfill({ json: event });
        if (path.endsWith("/my-attendance/today")) return route.fulfill({ json: { id: 81, attendance_date: today, status: "Work Suspended", check_in_at: null, check_out_at: null } });
        if (path.endsWith("/my-schedule")) return route.fulfill({ json: { tasks: [work], attendance: [], leave: [], shifts: [], availability: [{ employee_id: 1, work_date: today, status: "Work Suspended", attendance_suspended_now: true, suspension_full_shift: true, is_working_day: false, schedule_status: "Configured" }] } });
        if (path.endsWith("/my-tasks/page")) return route.fulfill({ json: { items: [work], total: 1, offset: 0, limit: 25 } });
        if (path.endsWith("/my-tasks/summary")) return route.fulfill({ json: { total: 1, today: 1, held: 1, missed: 0, for_review: 0 } });
        return route.fulfill({ json: [] });
    });
    return { writes, getEvent: () => event };
}
for (const width of [1440, 390]) test(`draft preview and approval use one consistent panel at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    if (width === 390) await page.addInitScript(() => localStorage.setItem("joross-theme", "dark"));
    const { writes } = await prepare(page);
    await page.goto(`/staff-calendar?view=day&date=${today}`);
    await page.getByRole("button", { name: "Farm Events & No-Work Days", exact: true }).click();
    const dialog = page.getByRole("dialog"); await dialog.getByRole("button", { name: "Add Farm Event", exact: true }).click();
    await dialog.getByLabel("Title *", { exact: true }).fill("Typhoon preparation review");
    await dialog.getByLabel("Event type", { exact: true }).selectOption("Emergency Suspension");
    await dialog.getByLabel("Reason *", { exact: true }).fill("Reviewed local advisory for affected farm work");
    await page.screenshot({ path: `/workspace/scratch/49f4365c18e1/event-panel-${width}.png` });
    await dialog.getByRole("button", { name: "Save & Preview Impact", exact: true }).click();
    await expect(dialog.getByRole("heading", { name: "Impact Preview", exact: true })).toBeVisible();
    expect(writes.map((x) => x.path)).toEqual(["/api/v1/farm-events"]);
    await expect(dialog.getByRole("button", { name: "Approve Declaration", exact: true })).toBeDisabled();
    await dialog.getByLabel("Decision reason *", { exact: true }).fill("Impact reviewed; suspend affected work");
    await dialog.getByRole("button", { name: "Approve Declaration", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Record Reopening", exact: true })).toBeVisible();
    expect(writes.at(-1).body.preview_token).toBe("preview-123");
    expect(writes.at(-1).body.expected_version).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0);
});
test("failed draft save preserves entries and reuses the request key", async ({ page }) => {
    const { writes } = await prepare(page, { rejectFirst: true });
    await page.goto(`/staff-calendar?date=${today}&eventAction=create`);
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Title *", { exact: true }).fill("Planned farm day off");
    await dialog.getByLabel("Reason *", { exact: true }).fill("Owner approved planned closure");
    await dialog.getByRole("button", { name: "Save Draft", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Temporary save failure");
    await expect(dialog.getByLabel("Title *", { exact: true })).toHaveValue("Planned farm day off");
    await dialog.getByRole("button", { name: "Save Draft", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Edit Draft", exact: true })).toBeVisible();
    expect(writes).toHaveLength(2); expect(writes[0].body.request_key).toBe(writes[1].body.request_key);
});
test("essential duty requires an employee and reason in affected work", async ({ page }) => {
    const { writes } = await prepare(page, { preexisting: true });
    await page.goto(`/staff-calendar?date=${today}&eventId=5`);
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Affected Work", exact: true }).click();
    await dialog.getByLabel("Decision", { exact: true }).selectOption("Essential Duty");
    await dialog.getByLabel("Authorized employee", { exact: true }).selectOption("1");
    await dialog.getByLabel("Decision reason", { exact: true }).fill("Authorized essential animal care by assigned trained employee");
    await dialog.getByRole("button", { name: "Save Task Decision", exact: true }).click();
    await expect(dialog).toContainText("Last decision: Authorized essential animal care");
    expect(writes[0].body).toMatchObject({ expected_version: 1, action: "Essential Duty", employee_id: 1 });
});
test("employee acknowledgement is separate from check-in and held task work", async ({ page }) => {
    const { writes } = await prepare(page, { employee: true, preexisting: true });
    await page.goto("/my-tasks?tab=tasks");
    await expect(page.getByRole("region", { name: "Today's Attendance", exact: true }).getByRole("button", { name: "Check In", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Start", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Read Notice", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: "Approve Declaration", exact: true })).toHaveCount(0);
    await dialog.getByRole("button", { name: "I Have Read This Notice", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Acknowledged", exact: true })).toBeDisabled();
    expect(writes.map((x) => x.path)).toEqual(["/api/v1/farm-events/5/acknowledge"]);
});

test("stale weather is labelled unknown and refreshes independently on focus", async ({ page }) => {
    const { writes } = await prepare(page);
    let status = "Stale", weatherFetches = 0;
    await page.route("**/api/v1/weather", async (route) => {
        weatherFetches++;
        return route.fulfill({ json: { location: "Synthetic farm location", latitude: 13.1, longitude: 123.7,
            source: "OpenWeather", fetched_at: `${today}T00:50:00Z`, data_status: status,
            last_fetch_error: status === "Stale" ? "Last fetch failed" : null,
            official_alerts_status: "Not configured", official_alerts: [],
            current: { observed_at: `${today}T00:30:00Z`, temperature_c: 30, feels_like_c: 31, humidity_percent: 80, weather_code: 800, wind_speed_kph: 10, wind_gust_kph: 65, description: "Clear" },
            next_24_hours: { max_temperature_c: 31, max_wind_speed_kph: 20, max_wind_gust_kph: 65, rain_total_mm: 10, max_rain_probability_percent: 30 },
            forecast: [{ forecast_at: `${today}T03:00:00Z`, temperature_c: 30 }],
        } });
    });
    await page.goto("/dashboard");
    const weather = page.getByRole("region", { name: "Weather status and official advisories", exact: true });
    await expect(weather).toContainText("Weather needs verification");
    await expect(weather.getByRole("link", { name: "Review Farm Work", exact: true })).toHaveCount(0);
    await weather.getByRole("button", { name: "Details", exact: true }).click();
    await expect(weather).toContainText("Last fetch failed");
    expect(weatherFetches).toBe(1);
    status = "Fresh";
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(weather).toContainText("Fresh weather");
    await expect(weather).toContainText("Strong wind or gusts");
    await expect(weather.getByRole("link", { name: "Review Farm Work", exact: true })).toHaveAttribute("href", /eventAction=create/);
    expect(weatherFetches).toBe(2);
    expect(writes.filter((x) => x.path.startsWith("/api/v1/farm-events"))).toHaveLength(0); // Forecasts never create or approve declarations.
});

test("shared device shows notices and blocks work on a held task", async ({ page }) => {
    const { writes } = await prepare(page, { employee: true, preexisting: true });
    await page.goto("/my-tasks?shared=1");
    const card = page.locator(".shared-task-card").first();
    await expect(card).toContainText("Held");
    await expect(page.getByRole("button", { name: "Read Notice", exact: true })).toBeVisible();
    await card.locator(".shared-primary-button").click();
    await expect(page.locator(".shared-start-button")).toBeDisabled();
    await expect(page.locator(".shared-submit-button")).toBeDisabled();
    expect(writes).toHaveLength(0);
});

async function prepareDashboardWeather(page, { warnings = [] } = {}) {
    const state = await prepare(page);
    await page.route("**/api/v1/weather", (route) => route.fulfill({ json: {
        location: "Joross Farm Area", latitude: 13.1391, longitude: 123.7438,
        source: "OpenWeather", fetched_at: `${today}T00:55:00Z`, data_status: "Cached",
        official_alerts_status: warnings.length ? "Available" : "Not configured", official_alerts: warnings,
        current: { observed_at: `${today}T00:50:00Z`, temperature_c: 26, feels_like_c: 28, humidity_percent: 92, weather_code: 802, wind_speed_kph: 5, wind_gust_kph: 11, description: "scattered clouds" },
        next_24_hours: { max_temperature_c: 28, max_wind_speed_kph: 8, max_wind_gust_kph: 11, rain_total_mm: 10, max_rain_probability_percent: 45 },
        forecast: [{ forecast_at: `${today}T03:00:00Z`, temperature_c: 26 }],
    } }));
    return state;
}

for (const width of [1440, 390]) test(`quiet weather stays in one compact card with expandable details at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    if (width === 390) await page.addInitScript(() => localStorage.setItem("joross-theme", "dark"));
    const { writes } = await prepareDashboardWeather(page);
    await page.goto("/dashboard");
    const card = page.getByRole("region", { name: "Current farm weather", exact: true });
    const status = card.getByRole("region", { name: "Weather status and official advisories", exact: true });
    await expect(card).toContainText("Scattered Clouds");
    await expect(card).toContainText("92%");
    await expect(card).toContainText("45%");
    await expect(card).toContainText("5 km/h");
    const details = status.getByRole("button", { name: "Details", exact: true });
    await expect(details).toHaveAttribute("aria-expanded", "false");
    await expect(status.getByText("Configured coordinates", { exact: true })).not.toBeVisible();
    await expect(status.getByRole("link", { name: "Review Farm Work", exact: true })).not.toBeVisible();
    expect((await card.boundingBox()).height).toBeLessThan(width === 390 ? 330 : 180);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `/workspace/scratch/49f4365c18e1/weather-layout-${width}.png` });
    await card.screenshot({ path: `/workspace/scratch/49f4365c18e1/weather-layout-card-${width}.png` });
    await details.focus();
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("aria-expanded", "true");
    await expect(status.getByText("Configured coordinates", { exact: true })).toBeVisible();
    await expect(status).toContainText("13.1391, 123.7438");
    await expect(status.getByText("Not configured", { exact: true })).toBeVisible();
    await expect(status.getByRole("link", { name: "Review Farm Work", exact: true })).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("aria-expanded", "false");
    await expect(status.getByText("Configured coordinates", { exact: true })).not.toBeVisible();
    expect(writes.filter((x) => x.path.startsWith("/api/v1/farm-events"))).toHaveLength(0);
});

test("official advisories remain visible while technical details are collapsed", async ({ page }) => {
    const warning = { id: "test-advisory", event: "Test farm advisory", source: "Test issuing authority", provider: "OpenWeather", location: "Joross Farm Area", starts_at: `${today}T00:00:00Z`, ends_at: `${today}T03:00:00Z`, description: "Synthetic advisory instructions", reference: "Test bulletin" };
    const { writes } = await prepareDashboardWeather(page, { warnings: [warning, { ...warning, id: "expired-advisory", event: "Expired test advisory", ends_at: "2026-11-01T00:00:00Z" }] });
    await page.goto("/dashboard");
    const status = page.getByRole("region", { name: "Weather status and official advisories", exact: true });
    await expect(status.getByRole("button", { name: "Details", exact: true })).toHaveAttribute("aria-expanded", "false");
    await expect(status.getByText("Test farm advisory", { exact: true })).toBeVisible();
    await expect(status.getByText("Expired test advisory", { exact: true })).toHaveCount(0);
    const review = status.getByRole("link", { name: "Review Farm Work", exact: true });
    await expect(review).toBeVisible();
    const params = new URL(await review.getAttribute("href"), "http://test").searchParams;
    expect(params.get("source")).toBe("Test issuing authority");
    expect(params.get("reference")).toBe("Test bulletin");
    await status.locator(".weather-official-warning summary").click();
    await expect(status.getByText("Synthetic advisory instructions", { exact: true })).toBeVisible();
    expect(writes.filter((x) => x.path.startsWith("/api/v1/farm-events"))).toHaveLength(0);
});
