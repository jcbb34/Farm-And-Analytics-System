import { test, expect } from "@playwright/test";

const today = "2026-10-29";
const employee = { id: 1, full_name: "Task Review Employee", employee_code: "VOID-EMP", employment_status: "Active", is_archived: false };

async function setup(page, { status = "Submitted for Review", eligible, sourceType = "crop_watering", staleVoid = false } = {}) {
    const writes = [];
    let task = {
        id: 1, activity_code: "VOID-TASK", name: "Water test crop", category: "Crop Care", related_to: "Test crop", location: "Field A",
        activity_date: today, start_time: "08:00", assigned_employee_id: 1, assigned_to: employee.full_name,
        employee_name: employee.full_name, status, priority: "Medium", is_automatic: true, requires_review: true,
        requires_evidence: false, needs_reassignment: false, source_module: "Crop", source_type: sourceType, source_record_id: 1,
        resource_required: false, resource_linked: false, has_performed_work_record: true, is_archived: false,
        can_void: eligible ?? status === "Completed", latest_submission: { id: 2, activity_id: 1, attempt_number: 1,
            employee_id: 1, employee_name: employee.full_name, submitted_at: "2026-10-29T08:30:00",
            review_status: status === "Completed" ? "Approved" : status === "Returned" ? "Returned" : "Submitted", worker_notes: "Watering completed" },
    };
    const user = { id: 1, username: "void.browser.test", fullName: "Task Reviewer", role: "System Administrator", permissions: ["*"], status: "Active" };
    await page.clock.install({ time: new Date("2026-10-29T04:00:00Z") });
    await page.addInitScript((profile) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "test-task-void-browser-token", user: profile, expiresAt: Date.now() + 86400000 })), user);
    await page.route("**/api/v1/**", async (route) => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path.endsWith("/review") && request.method() === "POST") {
            const payload = request.postDataJSON(); writes.push({ path, payload });
            task = { ...task, status: payload.decision === "Approve" ? "Completed" : "Returned", can_void: payload.decision === "Approve",
                latest_submission: { ...task.latest_submission, review_status: payload.decision === "Approve" ? "Approved" : "Returned", review_feedback: payload.feedback } };
            return route.fulfill({ json: task });
        }
        if (path === "/api/v1/void-authorizations/preview") return route.fulfill({ json: { preview_token: "test-void-preview", label: task.name, impact: "No stock restoration required.", requires_owner_credentials: false } });
        if (path === "/api/v1/void-authorizations" && request.method() === "POST") {
            writes.push({ path, payload: request.postDataJSON() });
            task = { ...task, status: "Voided", can_void: false, latest_submission: { ...task.latest_submission, review_status: "Voided" } };
            if (staleVoid) return route.fulfill({ status: 409, json: { detail: "Only approved, completed work can be voided. Refresh the task list." } });
            return route.fulfill({ json: task });
        }
        if (path.endsWith("/review-report")) return route.fulfill({ json: { task, current_submission: task.latest_submission, previous_submissions: [], evidence: [], resource_usage: { tracked: false, movements: [] } } });
        if (path.endsWith("/tasks/page")) return route.fulfill({ json: { items: [task], total: 1, offset: 0, limit: 25 } });
        if (path.endsWith("/tasks/summary")) return route.fulfill({ json: { total: 1 } });
        if (path.endsWith("/employees")) return route.fulfill({ json: [employee] });
        if (path === "/api/v1/workforce/tasks/1") return route.fulfill({ json: task });
        return route.fulfill({ json: [] });
    });
    await page.goto("/task-management");
    await page.getByLabel("Filter by schedule", { exact: true }).selectOption("All Scheduled");
    await expect(page.getByText("Water test crop", { exact: true })).toBeVisible();
    return writes;
}

async function openReview(page) {
    await page.getByRole("button", { name: /Review Submission/ }).click();
    const dialog = page.getByRole("dialog", { name: "Work Submission Report", exact: true });
    await expect(dialog).toBeVisible();
    return dialog;
}

test("pending review offers Approve and Return with no Void action", async ({ page }) => {
    await setup(page);
    const dialog = await openReview(page);
    await expect(dialog.getByRole("button", { name: /Approve Work/ })).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Return for Correction/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Void/ })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Review Submission/ })).toBeFocused();
});

test("pending work can still be returned with required feedback", async ({ page }) => {
    const writes = await setup(page);
    const dialog = await openReview(page);
    await dialog.getByRole("button", { name: /Return for Correction/ }).click();
    await expect(dialog.getByText("Feedback is required before returning this work for correction.")).toBeVisible();
    await dialog.getByLabel("Feedback to employee").fill("Please correct the reported work");
    await dialog.getByRole("button", { name: /Return for Correction/ }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes.filter((entry) => entry.path.endsWith("/review")).map((entry) => entry.payload.decision)).toEqual(["Return"]);
    await expect(page.getByRole("button", { name: /Void/ })).toHaveCount(0);
});

test("approval exposes Void Work even without inventory, and a reason is mandatory", async ({ page }) => {
    const writes = await setup(page);
    const review = await openReview(page);
    await review.getByRole("button", { name: /Approve Work/ }).click();
    await expect(review).toHaveCount(0);
    await page.getByRole("button", { name: /Void Work/ }).click();
    const confirm = page.getByRole("dialog", { name: "Owner/Admin Void Authorization", exact: true });
    await confirm.getByRole("button", { name: "Void Record", exact: true }).click();
    expect(await confirm.getByLabel("Reason for voiding", { exact: false }).evaluate((field) => field.validity.valueMissing)).toBe(true);
    await expect(confirm).toBeVisible();
    expect(writes.filter((entry) => entry.path.endsWith("/void-authorizations"))).toHaveLength(0);
    await confirm.getByLabel("Reason", { exact: false }).fill("Invalid approved report");
    await confirm.getByRole("button", { name: "Void Record", exact: true }).click();
    await expect(confirm).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Void Work/ })).toHaveCount(0);
    expect(writes.filter((entry) => entry.path.endsWith("/void-authorizations"))).toEqual([{ path: "/api/v1/void-authorizations", payload: { preview_token: "test-void-preview", reason: "Invalid approved report" } }]);
    expect(writes.filter((entry) => entry.path.endsWith("/review")).map((entry) => entry.payload.decision)).toEqual(["Approve"]);
});

for (const sourceType of ["crop_growth_check", "crop_harvest"]) {
    test(`protected approved ${sourceType} does not offer Void Work`, async ({ page }) => {
        await setup(page, { status: "Completed", eligible: false, sourceType });
        await expect(page.getByRole("button", { name: /Void/ })).toHaveCount(0);
        await expect(page.getByRole("button", { name: /Review Submission/ })).toHaveCount(0);
    });
}

test("a completed-looking row without an approved attempt cannot expose Void", async ({ page }) => {
    await setup(page, { status: "Returned", eligible: true });
    await expect(page.getByRole("button", { name: /Void/ })).toHaveCount(0);
});

test("a stale void refreshes the table and cannot announce success", async ({ page }) => {
    const writes = await setup(page, { status: "Completed", staleVoid: true });
    await page.getByRole("button", { name: /Void Work/ }).click();
    const confirm = page.getByRole("dialog", { name: "Owner/Admin Void Authorization", exact: true });
    await confirm.getByLabel("Reason", { exact: false }).fill("Invalid approved report");
    await confirm.getByRole("button", { name: "Void Record", exact: true }).click();
    await expect(page.getByText("Only approved, completed work can be voided. Refresh the task list.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Void Work/ })).toHaveCount(0);
    expect(writes.filter((entry) => entry.path.endsWith("/void-authorizations"))).toHaveLength(1);
    await expect(page.getByText("Approved work voided. Any posted inventory usage was reversed, and the reason was recorded.")).toHaveCount(0);
});

test.describe("mobile pending review", () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    test("two review actions fit the dark-mode modal", async ({ page }) => {
        await setup(page);
        await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
        const dialog = await openReview(page);
        await expect(dialog.getByRole("button", { name: /Void/ })).toHaveCount(0);
        for (const name of [/Approve Work/, /Return for Correction/]) {
            const box = await dialog.getByRole("button", { name }).boundingBox();
            expect(box.x).toBeGreaterThanOrEqual(0);
            expect(box.x + box.width).toBeLessThanOrEqual(390);
        }
    });
});
