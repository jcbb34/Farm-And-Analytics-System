import { test, expect } from "@playwright/test";

const today = "2026-11-01";
const user = { id: 41, username: "working.day.test", fullName: "Test Employee", role: "Employee", permissions: ["workforce:submit"], status: "Active" };

test("My Tasks refreshes both today's attendance and My Schedule after a working override", async ({ page }) => {
    let working = false;
    const writes = [];
    const attendance = { id: 91, employee_id: 1, attendance_date: today, status: "Day Off", check_in_at: null, check_out_at: null };
    await page.clock.install({ time: new Date(`${today}T00:05:00Z`) });
    await page.addInitScript((profile) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({
        accessToken: "working-day-test-token", user: profile, expiresAt: Date.now() + 86400000,
    })), user);
    await page.route("**/api/v1/**", async (route) => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (request.method() !== "GET") writes.push(path);
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path.endsWith("/my-attendance/today")) return route.fulfill({ json: attendance });
        if (path.endsWith("/my-schedule")) return route.fulfill({ json: {
            tasks: [], leave: [], shifts: [], attendance: [attendance], availability: [{
                employee_id: 1, work_date: today, status: working ? "Working Day" : "Rest Day",
                reason: working ? "Required for work today" : "Scheduled weekly rest day", schedule_status: "Configured",
                is_working_day: working, exception_type: working ? "Working Day Override" : null,
                attendance_status: null, start_time: working ? "08:00:00" : null, end_time: working ? "17:00:00" : null,
            }],
        } });
        if (path.endsWith("/my-tasks/page")) return route.fulfill({ json: { items: [], total: 0 } });
        return route.fulfill({ json: [] });
    });
    await page.goto("/my-tasks?tab=schedule");
    const bar = page.getByRole("region", { name: "Today's Attendance", exact: true });
    const day = page.locator(".my-schedule-day.today");
    await expect(bar).toContainText("Rest Day");
    await expect(day.locator(".my-schedule-state")).toContainText("Rest Day");
    await expect(bar.getByRole("button", { name: "Check In", exact: true })).toHaveCount(0);
    working = true;
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("joross:modules-updated", { detail: { modules: ["calendar", "my_tasks"] } })));
    await page.clock.runFor(500);
    await expect(day.locator(".my-schedule-state")).toContainText("Working Day");
    await expect(day).toContainText("08:00–17:00");
    await expect(day).toContainText("Attendance: Not Checked In");
    await expect(bar).toContainText("Not Checked In");
    await expect(bar).not.toContainText("Rest Day");
    await expect(bar.getByRole("button", { name: "Check In", exact: true })).toBeEnabled();
    await page.reload();
    await expect(bar).not.toContainText("Rest Day");
    await expect(day).toContainText("Attendance: Not Checked In");
    expect(writes).toHaveLength(0);
});
