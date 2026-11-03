import { test, expect } from "@playwright/test";

test.use({ timezoneId: "America/Los_Angeles" });

const user = {
    id: 41, userCode: "LEAVE-TEST", username: "leave.test", fullName: "Leave Test Employee",
    role: "Employee", permissions: ["workforce:submit"], status: "Active",
};

async function prepare(page, initialToday = "2026-10-29") {
    let today = initialToday;
    const submitted = [];
    // The computer/browser clock is behind the farm's date. The API date wins.
    await page.clock.install({ time: new Date("2026-10-28T15:30:00Z") });
    await page.addInitScript((profile) => {
        localStorage.setItem("joross-auth-session-v1", JSON.stringify({
            accessToken: "leave-browser-test-token", user: profile, expiresAt: Date.now() + 86400000,
        }));
    }, user);
    await page.route("**/api/v1/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path === "/api/v1/workforce/calendar/config") return route.fulfill({ json: { timezone: "Asia/Manila", today } });
        if (path === "/api/v1/workforce/leave/request") {
            submitted.push(route.request().postDataJSON());
            return route.fulfill({ status: 201, json: { id: 1, ...submitted.at(-1), status: "Pending" } });
        }
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path.endsWith("/my-schedule")) return route.fulfill({ json: { tasks: [], attendance: [], leave: [], shifts: [], availability: [] } });
        if (path.endsWith("/my-tasks/page")) return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } });
        return route.fulfill({ json: [] });
    });
    await page.goto("/my-tasks?tab=leave");
    const form = page.locator("form.my-leave-request");
    await expect(form).toBeVisible();
    await expect(form.getByLabel("Start date")).toHaveAttribute("min", "2026-10-30");
    return { form, submitted, setToday: (value) => { today = value; } };
}

test("both leave dates default to farm tomorrow and native date controls reject today and the past", async ({ page }) => {
    const { form, submitted } = await prepare(page);
    const start = form.getByLabel("Start date");
    const end = form.getByLabel("End date");
    await expect(start).toHaveValue("2026-10-30");
    await expect(end).toHaveValue("2026-10-30");
    await expect(start).toHaveAttribute("required", "");
    await expect(end).toHaveAttribute("required", "");
    for (const date of ["2026-10-28", "2026-10-29"]) {
        await start.fill(date);
        expect(await start.evaluate((input) => input.validity.rangeUnderflow)).toBe(true);
        await form.getByRole("button", { name: "Submit Leave Request" }).click();
        expect(submitted).toHaveLength(0);
    }
    await start.fill("2026-10-30");
    await end.fill("2026-10-29");
    expect(await end.evaluate((input) => input.validity.rangeUnderflow)).toBe(true);
    await form.getByRole("button", { name: "Submit Leave Request" }).click();
    expect(submitted).toHaveLength(0);
});

test("Other requires a real reason and submits trimmed text", async ({ page }) => {
    const { form, submitted } = await prepare(page);
    await form.getByLabel("Leave type").selectOption("Other");
    const reason = form.getByLabel("Reason", { exact: false });
    await expect(reason).toHaveAttribute("required", "");
    await expect(form.getByText("(required)", { exact: true })).toBeVisible();
    await form.getByRole("button", { name: "Submit Leave Request" }).click();
    expect(submitted).toHaveLength(0);
    await reason.fill("   ");
    await form.getByRole("button", { name: "Submit Leave Request" }).click();
    await expect(page.getByText("Please enter a reason when the leave type is Other.", { exact: true })).toBeVisible();
    expect(submitted).toHaveLength(0);
    await reason.fill("  Personal appointment  ");
    await form.getByRole("button", { name: "Submit Leave Request" }).click();
    await expect.poll(() => submitted.length).toBe(1);
    expect(submitted[0]).toEqual({ leave_type: "Other", start_date: "2026-10-30", end_date: "2026-10-30", reason: "Personal appointment" });
});

test("other leave types keep reason optional and end date cannot precede start", async ({ page }) => {
    const { form, submitted } = await prepare(page);
    const type = form.getByLabel("Leave type");
    const reason = form.getByLabel("Reason", { exact: false });
    await type.selectOption("Other");
    for (const value of ["Sick Leave", "Vacation Leave", "Emergency Leave", "Day Off"]) {
        await type.selectOption(value);
        await expect(reason).not.toHaveAttribute("required");
        await expect(form.getByText("(optional)", { exact: true })).toBeVisible();
    }
    await form.getByLabel("Start date").fill("2026-11-02");
    await expect(form.getByLabel("End date")).toHaveValue("2026-11-02");
    await form.getByLabel("End date").fill("2026-11-01");
    await form.getByRole("button", { name: "Submit Leave Request" }).click();
    expect(submitted).toHaveLength(0);
    await form.getByLabel("End date").fill("2026-11-02");
    await form.getByRole("button", { name: "Submit Leave Request" }).click();
    await expect.poll(() => submitted.length).toBe(1);
    expect(submitted[0].reason).toBeNull();
});

test("farm-day refresh advances expired defaults and preserves a still-future selected range", async ({ page }) => {
    const { form, setToday } = await prepare(page);
    setToday("2026-10-30");
    await page.clock.fastForward(60001);
    await expect(form.getByLabel("Start date")).toHaveAttribute("min", "2026-10-31");
    await expect(form.getByLabel("Start date")).toHaveValue("2026-10-31");
    await expect(form.getByLabel("End date")).toHaveValue("2026-10-31");
    await form.getByLabel("Start date").fill("2026-11-05");
    await form.getByLabel("End date").fill("2026-11-07");
    setToday("2026-10-31");
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(form.getByLabel("Start date")).toHaveAttribute("min", "2026-11-01");
    await expect(form.getByLabel("Start date")).toHaveValue("2026-11-05");
    await expect(form.getByLabel("End date")).toHaveValue("2026-11-07");
});

test("server validation is readable and keeps the employee's entered reason", async ({ page }) => {
    const { form } = await prepare(page);
    await page.route("**/api/v1/workforce/leave/request", (route) => route.fulfill({
        status: 422,
        json: { detail: [{ loc: ["body"], msg: "Value error, Leave start and end dates must be after today in the farm timezone.", type: "value_error" }] },
    }));
    await form.getByLabel("Reason", { exact: false }).fill("Personal appointment");
    await form.getByRole("button", { name: "Submit Leave Request" }).click();
    await expect(page.getByText("Value error, Leave start and end dates must be after today in the farm timezone.", { exact: true })).toBeVisible();
    await expect(form.getByLabel("Reason", { exact: false })).toHaveValue("Personal appointment");
});
