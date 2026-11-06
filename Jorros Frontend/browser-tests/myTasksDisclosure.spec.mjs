import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { serveSessionPolicy } from "./helpers/serveSessionPolicy.mjs";

const today = "2026-11-05";
const user = { id: 41, username: "tasks.disclosure", fullName: "Task Test Employee", role: "Employee", status: "Active", permissions: ["workforce:submit"] };
const photo = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGMUabJhYGBgYmBgYGBgAAAJ2gDWk0BfggAAAABJRU5ErkJggg==", "base64");
const base = { activity_date: today, start_time: "15:00", location: "Piglet pen", priority: "Medium", related_to: "Piglet Batch 1", assigned_employee_id: 20, assigned_to: user.fullName, employee_name: user.fullName, status: "Pending", requires_review: true, requires_evidence: false, resource_required: true, resource_linked: true, planned_inventory_item_name: "Pig Starter Feed", planned_inventory_unit: "kg", planned_unit: "kg", planned_quantity: 12.5, planned_inventory_available_quantity: 812.5, is_archived: false, description: "Afternoon feeding occurrence 2 of 2. Daily schedule: Twice Daily | Morning, Afternoon. Feed type: Pig Starter Feed. Completing this activity records only this feeding occurrence; the next feeding stays pending in Upcoming Tasks.", instructions: "Distribute the planned feed evenly and check that drinking water is available." };
const submission = { id: 70, employee_id: 20, employee_name: user.fullName, review_status: "Submitted", worker_notes: "Previous work notes with additional detail.", actual_quantity: 12.4, actual_unit: "kg", submitted_at: `${today}T08:30:00`, evidence_url: `/workforce/evidence-assets/${"e".repeat(32)}`, attempt_number: 1 };

async function prepare(page, { theme = "light" } = {}) {
    const state = { reads: 0, writes: [], photoReads: 0, tasks: [
        { ...base, id: 1, activity_code: "ACT-DISC-1", name: "Afternoon Feeding - Piglet Batch 1" },
        { ...base, id: 2, name: "Yesterday's feeding", status: "In Progress", activity_date: "2026-11-04" },
        { ...base, id: 3, name: "Returned feeding", status: "Returned", priority: "High", latest_submission: { ...submission, review_status: "Returned", review_feedback: "Correct the quantity and provide a clearer photo." } },
        { ...base, id: 4, name: "Submitted feeding", status: "Submitted for Review", latest_submission: submission },
        { ...base, id: 5, name: "Completed feeding", status: "Completed", activity_date: "2026-11-04", completed_at: `${today}T09:00:00`, can_void: true, latest_submission: { ...submission, review_status: "Approved", review_feedback: "Work approved." } },
        { ...base, id: 6, name: "Apply fertilizer", related_to: "East field", resource_required: false, planned_quantity: 3, activity_date: "2026-11-06" },
        { ...base, id: 7, name: "Feeding without linked stock", resource_linked: false },
        { ...base, id: 8, name: "Held care task", work_suspended: true, suspension_holds: [{ state: "Review Required", title: "Storm operations hold" }] },
        { ...base, id: 9, name: "Cover feeding", needs_reassignment: true, assignment_source: "Leave Coverage", original_employee_name: "Original Employee", coverage_start_date: today, coverage_end_date: "2026-11-06", coverage_reason: "Approved leave" },
        { ...base, id: 10, name: "Feeding with low stock", planned_inventory_available_quantity: 0 },
    ] };
    await page.clock.install({ time: new Date(`${today}T04:00:00Z`) });
    await page.addInitScript(({ profile, theme }) => {
        sessionStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-task-disclosure-token", user: profile, expiresAt: Date.now() + 28800000 }));
        localStorage.setItem("joross-theme", theme);
    }, { profile: user, theme });
    await page.route("**/api/v1/**", async (route) => {
        if (await serveSessionPolicy(route, page)) return;
        const req = route.request(), url = new URL(req.url()), path = url.pathname;
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path.endsWith("/events/stream") || path.includes("/weather")) return route.fulfill({ status: 503, json: {} });
        if (path.endsWith("/my-tasks/page")) {
            state.reads += 1;
            const view = url.searchParams.get("view");
            const items = state.tasks.filter((task) => view === "completed" ? task.status === "Completed" : view === "all" || task.status !== "Completed");
            return route.fulfill({ json: { items, total: items.length, offset: 0, limit: 25 } });
        }
        if (path.endsWith("/my-tasks/summary")) return route.fulfill({ json: { total: 9, today: 7, missed: 1, progress: 1, returned: 1, review: 1, upcoming: 1, held: 1 } });
        if (path.endsWith("/my-schedule")) return route.fulfill({ json: { tasks: [], attendance: [], leave: [], shifts: [], availability: [] } });
        if (/\/workforce\/tasks\/\d+\/(start|submit)$/.test(path)) {
            state.writes.push({ path, body: req.postDataJSON() });
            const id = Number(path.split("/").at(-2));
            const task = state.tasks.find((item) => item.id === id);
            task.status = path.endsWith("/start") ? "In Progress" : "Submitted for Review";
            if (path.endsWith("/submit")) task.latest_submission = { ...submission, ...req.postDataJSON() };
            return route.fulfill({ json: task });
        }
        if (path.startsWith("/api/v1/workforce/evidence-assets/")) {
            state.photoReads += 1;
            expect(req.headers().authorization).toBe("Bearer synthetic-task-disclosure-token");
            return route.fulfill({ body: photo, contentType: "image/png" });
        }
        if (/\/workforce\/tasks\/\d+$/.test(path)) return route.fulfill({ json: state.tasks.find((task) => task.id === Number(path.split("/").at(-1))) });
        return route.fulfill({ json: [] });
    });
    return state;
}
const card = (page, id) => page.locator(`#my-task-${id}`);
const details = (page, id) => card(page, id).locator("details.my-task-details");
const toggle = (page, id) => details(page, id).locator("summary");
async function contrast(foreground, background) {
    return foreground.evaluate((element, bg) => {
        const luminance = (color) => {
            const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map((channel) => {
                const value = channel / 255;
                return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
            });
            return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
        };
        const text = luminance(getComputedStyle(element).color), surface = luminance(bg);
        return (Math.max(text, surface) + .05) / (Math.min(text, surface) + .05);
    }, await background.evaluate((element) => getComputedStyle(element).backgroundColor));
}
async function openTasks(page, url = "/my-tasks") {
    // Move into the page before using its controls, away from the existing
    // hover-expanded navigation rail. Clicks still use normal hit testing.
    await page.mouse.move(1000, 100);
    await page.goto(url);
    await expect(page.getByRole("heading", { name: "Assigned Work", exact: true })).toBeVisible();
    await page.mouse.move(1000, 100);
    if (page.viewportSize().width > 720) await expect(page.locator(".sidebar")).toHaveCSS("width", "80px");
}

test("cards start collapsed with the next work action and planned feed still visible", async ({ page }) => {
    const state = await prepare(page); await openTasks(page);
    await expect(card(page, 1)).toBeVisible();
    expect(await page.locator(".my-task-details[open]").count()).toBe(0);
    await expect(card(page, 1).getByRole("heading", { name: "Afternoon Feeding - Piglet Batch 1", exact: true })).toBeVisible();
    await expect(card(page, 1).locator(".task-meta")).toContainText(`${today} 15:00`);
    await expect(card(page, 1).locator(".my-task-resource-summary")).toContainText("Pig Starter Feed · Planned 12.5 kg");
    await expect(card(page, 1).getByRole("button", { name: "Start", exact: true })).toBeVisible();
    await expect(card(page, 1).getByRole("button", { name: "Submit Work", exact: true })).toBeVisible();
    await expect(card(page, 1).getByText(base.description, { exact: true })).toBeHidden();
    await expect(card(page, 1).getByText(base.instructions, { exact: false })).toBeHidden();
    await expect(card(page, 1).getByText("Available stock:", { exact: true })).toBeHidden();
    expect(state.writes).toEqual([]); expect(state.photoReads).toBe(0);
});

test("details toggle independently and remain open after a background refresh", async ({ page }) => {
    const state = await prepare(page); await openTasks(page);
    await toggle(page, 1).click();
    await expect(details(page, 1)).toHaveJSProperty("open", true);
    await expect(card(page, 1).getByText(base.description, { exact: true })).toBeVisible();
    await expect(card(page, 1).getByText("Available stock:", { exact: true })).toBeVisible();
    await expect(details(page, 2)).toHaveJSProperty("open", false);
    const before = state.reads;
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("joross:modules-updated", { detail: { modules: ["my_tasks"] } })));
    await expect.poll(() => state.reads).toBeGreaterThan(before);
    await expect(details(page, 1)).toHaveJSProperty("open", true);
    await toggle(page, 1).click();
    await expect(details(page, 1)).toHaveJSProperty("open", false);
    await expect(card(page, 1).getByRole("button", { name: "Submit Work", exact: true })).toBeVisible();
    expect(state.writes).toEqual([]); expect(state.photoReads).toBe(0);
});

test("the disclosure supports Enter, Space and a visible keyboard focus ring", async ({ page }) => {
    await prepare(page); await openTasks(page);
    await toggle(page, 1).focus();
    await expect(toggle(page, 1)).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(details(page, 1)).toHaveJSProperty("open", true);
    await expect(toggle(page, 1)).toHaveCSS("outline-style", "solid");
    await page.keyboard.press("Space");
    await expect(details(page, 1)).toHaveJSProperty("open", false);
    await page.keyboard.press("Tab");
    await expect(card(page, 1).getByRole("button", { name: "Start", exact: true })).toBeFocused();
});

test("overdue, returned corrections, resource problems and holds stay visible without opening details", async ({ page }) => {
    await prepare(page); await openTasks(page);
    await expect(card(page, 2).getByText("Missed / Overdue", { exact: true })).toBeVisible();
    await expect(card(page, 3).getByText("Correct the quantity and provide a clearer photo.", { exact: false })).toBeVisible();
    await expect(card(page, 3).getByRole("button", { name: "Correct & Submit", exact: true })).toBeVisible();
    await expect(card(page, 7).getByText("Inventory resource not linked.", { exact: true })).toBeVisible();
    await expect(card(page, 7).getByRole("button", { name: "Resource Link Needed", exact: true })).toBeDisabled();
    await expect(card(page, 8).getByText(/Held — Awaiting reopening review/)).toBeVisible();
    await expect(card(page, 9).getByText("Availability Warning / Needs Coverage", { exact: true })).toBeVisible();
    await expect(card(page, 9).getByText(/Coverage Task — originally assigned/)).toBeVisible();
    await expect(card(page, 6).getByText("Upcoming Task", { exact: true })).toBeVisible();
    await expect(card(page, 6).getByText("East field", { exact: true })).toBeVisible();
    await expect(card(page, 6).getByRole("button", { name: "Start", exact: true })).toHaveCount(0);
    await expect(card(page, 6).getByRole("button", { name: "Submit Work", exact: true })).toHaveCount(0);
    await expect(card(page, 10).getByRole("note", { name: "Stock check needed", exact: true })).toBeVisible();
    await expect(card(page, 1).getByRole("note", { name: "Stock check needed", exact: true })).toHaveCount(0);
});

test("completed history stays read-only and its report, evidence and notes remain accessible", async ({ page }) => {
    const state = await prepare(page); await openTasks(page, "/my-tasks?view=completed&taskId=5");
    await expect(card(page, 5).getByText("Completed work is read-only.", { exact: true })).toBeVisible();
    await expect(card(page, 5).getByRole("button", { name: "View Report", exact: true })).toBeVisible();
    await expect(card(page, 5).getByRole("button", { name: "Request Void", exact: true })).toBeVisible();
    await expect(card(page, 5).getByRole("button", { name: "Submit Work", exact: true })).toHaveCount(0);
    await expect(card(page, 5).getByText(submission.worker_notes, { exact: false })).toBeHidden();
    await toggle(page, 5).click();
    await expect(card(page, 5).getByText(submission.worker_notes, { exact: false })).toBeVisible();
    await expect(card(page, 5).getByText("Actual quantity:", { exact: true })).toBeVisible();
    await card(page, 5).getByRole("button", { name: "View Image", exact: true }).click();
    const preview = page.getByRole("dialog", { name: "Evidence photo preview", exact: true });
    await expect(preview).toBeVisible();
    await expect.poll(() => preview.getByRole("img").evaluate((image) => image.naturalWidth)).toBe(2);
    expect(state.photoReads).toBe(1);
});

test("Start and Submit Work operate while the task details remain collapsed", async ({ page }) => {
    const state = await prepare(page); await openTasks(page);
    await card(page, 1).getByRole("button", { name: "Start", exact: true }).click();
    await expect(card(page, 1).locator(".task-status")).toHaveText("In Progress");
    await expect(details(page, 1)).toHaveJSProperty("open", false);
    await card(page, 1).getByRole("button", { name: "Submit Work", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Submit Work", exact: true });
    await dialog.getByLabel("Actual Quantity Used", { exact: false }).fill("12.4");
    await dialog.getByLabel("Work Notes", { exact: true }).fill("Fed the assigned batch");
    await dialog.getByRole("button", { name: /Submit for Review$/ }).click();
    await expect(dialog).toHaveCount(0);
    await expect(card(page, 1).locator(".task-status")).toHaveText("Awaiting Manager Review");
    expect(state.writes.map((request) => request.path)).toEqual(["/api/v1/workforce/tasks/1/start", "/api/v1/workforce/tasks/1/submit"]);
    expect(state.writes[1].body.actual_quantity).toBe(12.4);
    expect(state.writes[1].body.worker_notes).toBe("Fed the assigned batch");
});

for (const theme of ["light", "dark"]) for (const width of [320, 390, 768, 1440]) {
    test(`collapsed and expanded cards fit ${width}px in ${theme} mode`, async ({ page }) => {
        await prepare(page, { theme }); await page.setViewportSize({ width, height: 1000 });
        await openTasks(page);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        const task = card(page, 1);
        await expect(task).toBeVisible();
        await expect.poll(() => contrast(task.getByRole("heading"), task)).toBeGreaterThanOrEqual(4.5);
        // The open summary can have its own hover surface; move away before
        // checking its normal text contrast against the card underneath.
        await expect.poll(() => contrast(toggle(page, 1), task)).toBeGreaterThanOrEqual(4.5);
        const closedHeight = (await task.boundingBox()).height;
        expect((await toggle(page, 1).boundingBox()).height).toBeGreaterThanOrEqual(44);
        const checkBounds = async () => {
            const bounds = await task.boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1);
            for (const element of [toggle(page, 1), task.getByRole("button", { name: "Submit Work", exact: true })]) {
                const box = await element.boundingBox();
                expect(box.x).toBeGreaterThanOrEqual(bounds.x);
                expect(box.x + box.width).toBeLessThanOrEqual(bounds.x + bounds.width + 1);
            }
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        };
        await checkBounds();
        if (process.env.MY_TASKS_QA_DIR && [390, 1440].includes(width)) {
            mkdirSync(process.env.MY_TASKS_QA_DIR, { recursive: true });
            await task.screenshot({ path: `${process.env.MY_TASKS_QA_DIR}/task-${theme}-${width}-collapsed.png` });
        }
        await toggle(page, 1).click();
        await expect(task.getByText(base.description, { exact: true })).toBeVisible();
        await expect.poll(() => contrast(task.getByText(base.description, { exact: true }), task)).toBeGreaterThanOrEqual(4.5);
        await expect.poll(() => contrast(task.locator(".my-task-resource-summary strong").last(), task.locator(".my-task-resource-summary"))).toBeGreaterThanOrEqual(4.5);
        expect((await task.boundingBox()).height).toBeGreaterThan(closedHeight + 70);
        await checkBounds();
        if (process.env.MY_TASKS_QA_DIR && [390, 1440].includes(width)) await task.screenshot({ path: `${process.env.MY_TASKS_QA_DIR}/task-${theme}-${width}-expanded.png` });
    });
}

test.describe("phone touch controls", () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    for (const theme of ["light", "dark"]) test(`details and Submit Work remain usable by touch in ${theme} mode`, async ({ page }) => {
        await prepare(page, { theme }); await openTasks(page);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await toggle(page, 1).tap();
        await expect(details(page, 1)).toHaveJSProperty("open", true);
        await expect(card(page, 1).getByText(base.description, { exact: true })).toBeVisible();
        await toggle(page, 1).tap();
        await expect(details(page, 1)).toHaveJSProperty("open", false);
        await card(page, 1).getByRole("button", { name: "Submit Work", exact: true }).tap();
        const dialog = page.getByRole("dialog", { name: "Submit Work", exact: true });
        await expect(dialog.getByLabel("Actual Quantity Used", { exact: false })).toHaveValue("12.5");
        await dialog.getByRole("button", { name: /Cancel$/ }).tap();
        await expect(dialog).toHaveCount(0);
    });
});

test("work reports retain the top X and Escape without a duplicate bottom Close Report", async ({ page }) => {
    const state = await prepare(page); await openTasks(page, "/my-tasks?view=completed&taskId=5");
    for (const close of ["x", "escape"]) {
        await card(page, 5).getByRole("button", { name: "View Report", exact: true }).click();
        const report = page.getByRole("dialog", { name: "Work Report", exact: true });
        await expect(report).toBeVisible(); await expect(report.locator("footer")).toHaveCount(0); await expect(report.getByRole("button", { name: "Close Report", exact: true })).toHaveCount(0);
        if (close === "x") await report.getByRole("button", { name: "Close work report", exact: true }).click(); else await page.keyboard.press("Escape");
        await expect(report).toHaveCount(0); await expect(card(page, 5)).toBeVisible();
    }
    expect(state.writes).toEqual([]);
});
