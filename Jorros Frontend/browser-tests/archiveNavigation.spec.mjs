import { test, expect } from "@playwright/test";

const admin = { id: 1, username: "archive.admin", fullName: "Archive Administrator", role: "System Administrator", permissions: ["*"], status: "Active" };
const today = "2026-10-31";
const names = { Crop: "Eggplant", Livestock: "Piglet Batch", Inventory: "Stored Feed", Report: "Crop Summary" };
function record(module, id, extra = {}) {
    return { id: `${module.toLowerCase()}-${id}`, sourceId: id, module, code: `${module}-${id}`, recordName: `${names[module]} (${module}-${id})`,
        reason: "Cycle closed after review", archivedDate: "2026-10-30T03:00:00+00:00", archivedBy: "Archive Administrator", canRestore: true, canDelete: true,
        details: { name: names[module], status: module === "Report" ? "Archived" : "Harvested", quantity: module === "Livestock" ? "50" : "0" }, ...extra };
}

const currentRecords = {
    Crop: { id: 1, crop_code: "CURRENT-CROP", name: "Eggplant", crop_type: "Vegetable", variety: "Test variety", field: "Field A", area_hectares: 1,
        planting_date: "2026-10-01", estimated_harvest: "2026-11-26", current_growth: 50, estimated_progress: 50, growth_stage: "Flowering",
        quantity_planted: 100, current_surviving: 93, status: "Growing", is_archived: false, yield_records: [], growth_records: [], pest_diseases: [] },
    Livestock: { id: 1, animal_code: "CURRENT-PIG", record_name: "Piglet Batch", animal_type: "Pig", breed: "Test breed", record_type: "Batch",
        lifecycle_status: "Active", quantity: 10, sex: "Mixed", date_of_birth: "2026-08-01", date_acquired: "2026-10-01", weight_kg: 20,
        min_weight_kg: 18, max_weight_kg: 22, pen_location: "Pen A", health_status: "Healthy", healthy_quantity: 10, growth_status: "Growing",
        is_archived: false, growth_records: [], vaccination_records: [], feeding_records: [] },
    Inventory: { id: 1, item_code: "CURRENT-FEED", name: "Stored Feed", category: "Livestock Feed", quantity: 0, unit: "kg", reorder_level: 0,
        cost: 0, price: 0, supplier: "Test Supplier", location: "Test Store", date_acquired: "2026-10-01", is_archived: false, stock_history: [] },
    Report: { id: 1, report_code: "CURRENT-REPORT", title: "Crop Summary", category: "Crop", report_type: "Crop Summary", start_date: "2026-10-01",
        end_date: "2026-10-30", generated_date: "2026-10-31", prepared_by: "Archive Administrator", status: "Draft", revision_number: 1, is_archived: false },
};

async function setup(page, { viewer = false, legacyEggplant = false, populated = false } = {}) {
    const reads = [], writes = [];
    let rows = [...Array.from({ length: 30 }, (_, index) => record("Crop", index + 1)), record("Livestock", 31), record("Inventory", 32), record("Report", 33)];
    if (legacyEggplant) rows = [record("Crop", 27, { code: "CRP-1027", recordName: "Eggplant (CRP-1027)", archivedDate: null, archivedBy: "Not recorded", reason: "Not recorded" })];
    const user = viewer ? { ...admin, permissions: ["crops:view"], role: "Viewer" } : admin;
    await page.clock.install({ time: new Date(`${today}T04:00:00Z`) });
    await page.addInitScript((profile) => localStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-archive-token", user: profile, expiresAt: Date.now() + 86400000 })), user);
    await page.route("**/api/v1/**", async (route) => {
        const request = route.request(), url = new URL(request.url()), path = url.pathname;
        if (request.method() === "GET") reads.push({ path, query: url.searchParams.toString() });
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path === "/api/v1/roles") return route.fulfill({ json: [{ id: 1, name: "System Administrator", permissions: ["*"], is_active: true }] });
        if (path === "/api/v1/archives") {
            const module = url.searchParams.get("module"), focus = Number(url.searchParams.get("focus_id")), needle = (url.searchParams.get("search") || "").toLowerCase();
            const counts = Object.fromEntries(["Crop", "Livestock", "Inventory", "Report"].map((name) => [name, rows.filter((row) => row.module === name).length]));
            if (url.searchParams.get("counts_only") === "true") return route.fulfill({ json: { items: [], total: module ? counts[module] : rows.length, offset: 0, limit: 50, counts } });
            let matching = rows.filter((row) => !module || row.module === module);
            if (focus) {
                matching = matching.filter((row) => row.sourceId === focus);
                if (!matching.length) return route.fulfill({ status: 409, json: { detail: "This record has already been restored. It is no longer in the archive." } });
            } else if (needle) matching = matching.filter((row) => `${row.recordName} ${row.module} ${row.reason}`.toLowerCase().includes(needle));
            matching.sort((left, right) => right.sourceId - left.sourceId);
            if (!focus && (url.searchParams.get("date_from") || url.searchParams.get("date_to"))) matching = matching.filter((row) => row.archivedDate && (!url.searchParams.get("date_from") || row.archivedDate.slice(0,10) >= url.searchParams.get("date_from")) && (!url.searchParams.get("date_to") || row.archivedDate.slice(0,10) <= url.searchParams.get("date_to")));
            const requestedOffset = Number(url.searchParams.get("offset") || 0), limit = Number(url.searchParams.get("limit") || 25);
            const offset = requestedOffset < matching.length ? requestedOffset : Math.max(0, Math.ceil(matching.length / limit) - 1) * limit;
            return route.fulfill({ json: { items: matching.slice(offset, offset + limit).map((row) => ({ ...row, canRestore: !viewer, canDelete: !viewer })), total: matching.length, offset, limit, counts } });
        }
        if (path.startsWith("/api/v1/archives/") && request.method() === "POST") {
            writes.push({ path, body: request.postDataJSON() });
            const [, module, id, action] = path.match(/\/archives\/(\w+)\/(\d+)\/(\w+)/) || [];
            if (action === "restore") rows = rows.filter((row) => !(row.module === module && row.sourceId === Number(id)));
            return route.fulfill({ json: { id: Number(id), archived: action === "archive" } });
        }
        if (path.endsWith("/calendar/config")) return route.fulfill({ json: { today, timezone: "Asia/Manila" } });
        if (path.endsWith("/calendar")) return route.fulfill({ json: { employees: [], availability: [], attendance: [], leave: [], shifts: [], tasks: [], dates: [] } });
        if (path.endsWith("/positions")) return route.fulfill({ json: [{ id: 1, name: "Farm Worker", is_active: true, category: "Farm Operations" }] });
        if (populated) {
            if (path === "/api/v1/crops/details") return route.fulfill({ json: [currentRecords.Crop] });
            if (path === "/api/v1/livestock") return route.fulfill({ json: [currentRecords.Livestock] });
            if (path === "/api/v1/inventory/page") return route.fulfill({ json: { items: [currentRecords.Inventory], total: 1, offset: 0, limit: 50 } });
            if (path === "/api/v1/reports") return route.fulfill({ json: [currentRecords.Report] });
            if (path === "/api/v1/reports/summary") return route.fulfill({ json: { matching_total: 1 } });
        }
        if (path.endsWith("/page")) return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 25 } });
        if (path.endsWith("/summary")) return route.fulfill({ json: {} });
        if (path.endsWith("/my-schedule")) return route.fulfill({ json: { availability: [], attendance: [], leave: [], shifts: [], tasks: [] } });
        return route.fulfill({ json: [] });
    });
    return { reads, writes, count: (path) => reads.filter((row) => row.path === path).length };
}

// Compare rendered sizing to the existing reference, rather than copying CSS values.
async function navigationSizes(nav) {
    return nav.evaluate((element) => {
        const properties = ["minHeight", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "gap", "borderRadius"];
        const read = (node, keys) => {
            const style = getComputedStyle(node);
            return Object.fromEntries(keys.map((key) => [key, style[key]]));
        };
        const buttons = [...element.querySelectorAll("button")];
        const button = buttons[0];
        return {
            // Action groups can wrap below the tabs; the tab controls retain the My Tasks scale.
            bar: read(element.closest(".records-toolbar") || element, properties),
            buttons: buttons.map((node) => ({ ...read(node, [...properties, "fontFamily", "fontSize", "fontWeight", "lineHeight"]), height: node.getBoundingClientRect().height })),
            icon: read(button.querySelector(".material-symbols-outlined"), ["fontSize", "lineHeight"]),
        };
    });
}

for (const [label, width, dark] of [["desktop", 1440, false], ["tablet", 768, false], ["mobile dark mode", 390, true]]) {
    test(`new module tabs match My Tasks sizing on ${label}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        await setup(page);
        if (dark) await page.addInitScript(() => localStorage.setItem("joross-theme", "dark"));
        await page.goto("/my-tasks");
        const reference = page.getByRole("navigation", { name: "My Tasks sections" });
        await expect(reference).toBeVisible();
        if (dark) await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
        await page.evaluate(() => document.fonts.ready);
        const expected = await navigationSizes(reference);
        for (const path of ["/crops", "/livestock", "/inventory", "/reports"]) {
            await page.goto(path);
            const nav = page.locator(".archive-tabs");
            await expect(nav).toBeVisible();
            await page.evaluate(() => document.fonts.ready);
            const actual = await navigationSizes(nav);
            expect(actual.bar, `${path}: tab bar`).toEqual(expected.bar);
            expect(actual.icon, `${path}: icon`).toEqual(expected.icon);
            expect(actual.buttons[0], `${path}: current tab`).toEqual(expected.buttons[0]);
            expect(actual.buttons[1], `${path}: archive tab`).toEqual(expected.buttons[1]);
            const toolbar = page.locator(({ "/crops": ".crop-toolbar", "/livestock": ".livestock-toolbar", "/inventory": ".inventory-page-toolbar", "/reports": ".reports-page-management-card" })[path]);
            const toolbarBox = await toolbar.boundingBox(), navBox = await nav.boundingBox();
            expect(navBox.y, `${path}: navigation follows the filters`).toBeGreaterThanOrEqual(toolbarBox.y + toolbarBox.height);
            await nav.getByRole("button").nth(1).click();
            const archivedNav = page.locator(".archive-tabs");
            await expect(archivedNav.getByRole("button").nth(1)).toHaveAttribute("aria-pressed", "true");
            const archiveSizes = await navigationSizes(archivedNav);
            expect(archiveSizes.bar, `${path}: archive tab bar`).toEqual(expected.bar);
            expect(archiveSizes.buttons[0], `${path}: inactive current tab`).toEqual(expected.buttons[0]);
            expect(archiveSizes.buttons[1], `${path}: active archive tab`).toEqual(expected.buttons[1]);
            const filtersBox = await page.locator(".archive-filters").boundingBox(), archivedNavBox = await archivedNav.boundingBox();
            expect(archivedNavBox.y, `${path}: archive navigation follows archive filters`).toBeGreaterThanOrEqual(filtersBox.y + filtersBox.height);
            if (width < 720) expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
        }
    });
}

async function recordLayout(page) {
    return page.locator(".records-workspace").evaluate((workspace) => {
        const read = (selector, properties) => {
            const node = workspace.querySelector(selector);
            if (!node) return null;
            const style = getComputedStyle(node);
            return Object.fromEntries(properties.map((property) => [property, style[property]]));
        };
        const frame = ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "borderTopWidth", "borderRadius", "backgroundColor", "boxShadow"];
        return {
            filter: read(".records-filter-panel", [...frame, "marginTop", "marginBottom"]),
            search: read(".records-search input", ["height", "borderRadius", "fontSize", "paddingLeft", "color", "backgroundColor"]),
            date: read(".records-date-filter", ["minHeight", "borderRadius", "paddingLeft", "backgroundColor"]),
            toolbar: read(".records-toolbar", frame),
            caption: read(".records-caption", ["marginTop", "fontSize", "fontWeight", "lineHeight", "color"]),
            table: read(".records-table-surface", frame),
            heading: read("thead th", ["height", "paddingLeft", "paddingRight", "fontSize", "fontWeight", "backgroundColor", "color"]),
            cell: read("tbody td", ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "fontSize", "lineHeight", "color"]),
            action: read(".records-row-actions > button", ["height", "minHeight", "borderRadius", "fontSize"]),
        };
    });
}

for (const [module, path, searchLabel, searchTerm, actions] of [
    ["Crop", "/crops", "Search crops", "Eggplant", ["Add Yield Record", "Add Crop"]],
    ["Livestock", "/livestock", "Search livestock", "Piglet", ["Manage Pens", "Add Livestock"]],
    ["Inventory", "/inventory", "Search inventory", "Stored Feed", ["Add Inventory"]],
    ["Report", "/reports", "Search reports", "Crop Summary", ["Automatic Reports", "Generate Custom Report"]],
]) {
    for (const [size, width, dark] of [["desktop", 1440, false], ["mobile dark mode", 390, true]]) {
        test(`${module} current and archived records share their layout on ${size}`, async ({ page }) => {
            await page.setViewportSize({ width, height: 1000 });
            await setup(page, { populated: true });
            if (dark) await page.addInitScript(() => localStorage.setItem("joross-theme", "dark"));
            await page.goto(path);
            await expect(page.locator(".records-table-scroll")).toHaveAttribute("aria-busy", "false");
            await expect(page.locator(".records-row-actions").first()).toBeVisible();
            await page.evaluate(() => document.fonts.ready);
            const before = await recordLayout(page);
            const clippedHeaders = await page.locator(".records-table-surface th").evaluateAll((headers) => headers.filter((header) => header.getBoundingClientRect().width > 0 && header.scrollWidth > header.clientWidth).map((header) => header.textContent.trim()));
            expect(clippedHeaders, "Current record headers remain readable").toEqual([]);
            const tabs = page.locator(".archive-tabs");
            for (const name of actions) {
                const button = page.locator(".records-toolbar-actions").getByRole("button", { name: new RegExp(`${name}$`) });
                await expect(button).toBeVisible();
                const actionBox = await button.boundingBox(), tabBox = await tabs.getByRole("button").first().boundingBox();
                expect(actionBox.height, `${name} matches the tabs`).toBeCloseTo(tabBox.height, 0);
            }
            await page.getByRole("searchbox", { name: searchLabel, exact: true }).fill(searchTerm);
            await tabs.getByRole("button").nth(1).click();
            await expect(page.locator(".archive-records .records-table-scroll")).toHaveAttribute("aria-busy", "false");
            await expect(page.locator(".archive-actions").first()).toBeVisible();
            const after = await recordLayout(page);
            const clippedArchiveHeaders = await page.locator(".records-table-surface th").evaluateAll((headers) => headers.filter((header) => header.getBoundingClientRect().width > 0 && header.scrollWidth > header.clientWidth).map((header) => header.textContent.trim()));
            expect(clippedArchiveHeaders, "Archive headers remain readable").toEqual([]);
            // The livestock current list has no date filter; its archive still has a date range.
            expect({ ...after, date: before.date ? after.date : null }).toEqual(before);
            const rowActions = page.locator(".archive-actions").first();
            const colors = await rowActions.locator("button").evaluateAll((buttons) => buttons.map((button) => getComputedStyle(button).color));
            expect(colors[0], "View Details and Restore retain the same neutral action style").toBe(colors[1]);
            expect(colors[2], "Delete alone uses the destructive action color").not.toBe(colors[0]);
            if (width < 720) {
                for (const input of await page.locator(".records-date-filter input").all()) {
                    expect((await input.boundingBox()).width, "The complete date control remains usable on a phone").toBeGreaterThan(170);
                }
            }
            const panels = page.locator(".records-filter-panel, .records-toolbar, .records-table-surface");
            const boxes = await panels.evaluateAll((nodes) => nodes.map((node) => { const box = node.getBoundingClientRect(); return { x: box.x, width: box.width }; }));
            for (const box of boxes) {
                expect(box.x).toBeCloseTo(boxes[0].x, 0);
                expect(box.width).toBeCloseTo(boxes[0].width, 0);
            }
            await expect(page.locator(".archive-records-has-navigation")).toHaveCSS("padding", "0px");
            await expect(page.locator(".archive-records-has-navigation")).toHaveCSS("border-top-width", "0px");
            await expect(page.locator(".archive-records-has-navigation")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
            await expect(page.locator(".records-toolbar-actions")).toHaveCount(0);
            await page.locator(".archive-actions").first().getByRole("button", { name: "View Details", exact: true }).click();
            await expect(page.getByRole("dialog")).toContainText("Read only");
            await page.keyboard.press("Escape");
            await page.locator(".archive-tabs").getByRole("button").first().click();
            await expect(page.getByRole("searchbox", { name: searchLabel, exact: true })).toHaveValue(searchTerm);
            if (width < 720) expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
        });
    }
}

test("opening archive tabs clears stale archive filters and reveals an existing legacy Eggplant", async ({ page }) => {
    await setup(page, { legacyEggplant: true });
    await page.goto("/crops?archive_search=Maize&archive_from=2099-01-01&archive_offset=25");
    await page.getByRole("button", { name: /^Archived Crops/ }).click();
    await expect(page.getByRole("button", { name: "Eggplant (CRP-1027)", exact: true })).toBeVisible();
    await expect(page.locator(".archive-search input")).toHaveValue("");
    await expect(page.getByLabel("Archived from", { exact: true })).toHaveValue("");
    await expect(page.getByText(/Showing 1–1 of 1 matching records/)).toBeVisible();
});

test("a corrected archive page keeps the legacy Eggplant row and displays the server page number", async ({ page }) => {
    await setup(page, { legacyEggplant: true });
    await page.goto("/crops?archive=1&archive_offset=25");
    await expect(page.getByRole("button", { name: "Eggplant (CRP-1027)", exact: true })).toBeVisible();
    await expect(page.getByText(/Showing 1–1 of 1 matching records/)).toBeVisible();
    await expect(page.locator(".archive-footer").getByRole("button", { name: "Previous", exact: true })).toBeDisabled();
});

for (const [path, label] of [["/crops", "Archived Crops"], ["/livestock", "Archived Livestock"], ["/inventory", "Archived Inventory"], ["/reports", "Archived Reports"]]) {
    test(`${path} identifies a missing archive API and recovers after the backend is updated`, async ({ page }) => {
        await setup(page);
        let unavailable = true;
        await page.route("**/api/v1/archives**", (route) => unavailable ? route.fulfill({ status: 404, json: { detail: "Not Found" } }) : route.fallback());
        await page.goto(path);
        await expect(page.locator(".archive-error")).toContainText("Archive service is unavailable");
        await page.getByRole("button", { name: new RegExp(`^${label}`) }).click();
        const section = page.locator(".archive-records");
        await expect(section.locator(".archive-error")).toContainText("restart the farm backend");
        await expect(section.locator(".archive-footer")).toContainText("could not be loaded");
        await expect(section.locator(".records-caption")).toContainText("could not be loaded");
        await expect(section.locator(".records-caption")).not.toContainText("0 archived records found");
        await expect(section).not.toContainText("No archived records match");
        await expect(section.locator(".archive-footer")).not.toContainText("0 archived records");
        unavailable = false;
        await section.locator(".archive-error").getByRole("button", { name: "Retry", exact: true }).click();
        await expect(section.locator(".archive-error")).toHaveCount(0);
        await expect(section.getByRole("button", { name: "View Details", exact: true }).first()).toBeVisible();
    });
}

for (const [module, path, label] of [["Crop", "/crops", "Archived Crops"], ["Livestock", "/livestock", "Archived Livestock"], ["Inventory", "/inventory", "Archived Inventory"], ["Report", "/reports", "Archived Reports"]]) {
    test(`${module} has a matching archive tab and read-only details`, async ({ page }) => {
        await setup(page); await page.goto(path);
        const tab = page.getByRole("button", { name: new RegExp(`^${label}`) });
        await tab.click(); await expect(tab).toHaveAttribute("aria-pressed", "true");
        const section = page.locator(".archive-records");
        await expect(section.getByRole("button", { name: "View Details", exact: true }).first()).toBeVisible();
        await section.getByRole("button", { name: "View Details", exact: true }).first().click();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toContainText("Read only"); await expect(dialog.locator("input,textarea,select")).toHaveCount(0);
        await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0);
        await expect(page.getByRole("button", { name: /^Add (Crop|Livestock|Inventory)$/ })).toHaveCount(0);
    });
}

test("central archives jump to the exact row, highlight briefly and return with filters and pagination", async ({ page }) => {
    await setup(page);
    await page.goto("/settings?section=archive&archive_module=Crop&archive_search=Crop&archive_offset=25&archive_from=2026-08-01");
    const row = page.locator("#archive-record-Crop-1"); await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Go to Record", exact: true }).click();
    await expect(page).toHaveURL(/\/crops\?.*archive=1/);
    await expect(page.getByRole("button", { name: /^Archived Crops/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#archive-record-Crop-1")).toHaveClass(/archive-highlight/);
    await page.clock.runFor(3100);
    await expect(page.locator("#archive-record-Crop-1")).not.toHaveClass(/archive-highlight/);
    await page.getByRole("button", { name: "Back to Archived Records", exact: true }).click();
    await expect(page).toHaveURL(/\/settings\?/);
    await expect(page.locator(".archive-search input")).toHaveValue("Crop");
    await expect(page.getByText(/Showing 26–30 of 30 matching records/)).toBeVisible();
});

test("restoring an archive updates its list and count once", async ({ page }) => {
    const state = await setup(page); await page.goto("/inventory?archive=1");
    await page.locator(".archive-records").getByRole("button", { name: "Restore", exact: true }).click();
    await page.getByRole("alertdialog", { name: "Restore Archived Record" }).getByRole("button", { name: "Restore", exact: true }).click();
    await expect(page.getByText("No archived records match these filters.")).toBeVisible();
    expect(state.writes.filter((call) => call.path.endsWith("/restore"))).toHaveLength(1);
    await expect(page.getByRole("button", { name: /^Archived Inventory/ })).toContainText("0");
});

test("stale archive links explain restoration and recover to the current list", async ({ page }) => {
    await setup(page); await page.goto("/crops?archive=1&archive_module=Crop&record=99999");
    await expect(page.locator(".archive-error[role=alert]")).toContainText("already been restored");
    await page.getByRole("button", { name: "Show current archive list", exact: true }).click();
    await expect(page.locator(".archive-error[role=alert]")).toHaveCount(0);
    await expect(page.getByText(/of 30 matching records/)).toBeVisible();
});

test("a viewer can inspect permitted archives without restore or delete controls", async ({ page }) => {
    await setup(page, { viewer: true }); await page.goto("/crops?archive=1");
    await expect(page.locator(".archive-records").getByRole("button", { name: "View Details", exact: true }).first()).toBeVisible();
    await expect(page.locator(".archive-records").getByRole("button", { name: /^(Restore|Delete)$/ })).toHaveCount(0);
});

for (const [path, endpoint] of [["/task-management", "/api/v1/workforce/tasks/page"], ["/staff-calendar", "/api/v1/workforce/calendar"], ["/my-tasks", "/api/v1/workforce/my-tasks/page"]]) {
    test(`${path} removes routine Refresh and updates when returning to the page`, async ({ page }) => {
        const state = await setup(page); await page.goto(path);
        await expect.poll(() => state.count(endpoint)).toBeGreaterThan(0);
        await expect(page.getByRole("button", { name: /Refresh/i })).toHaveCount(0);
        const before = state.count(endpoint);
        await page.evaluate(() => window.dispatchEvent(new Event("focus")));
        await expect.poll(() => state.count(endpoint)).toBeGreaterThan(before);
    });
}

test("tab title and favicon use Joross Farm branding", async ({ page }) => {
    await setup(page); await page.goto("/crops"); await expect(page).toHaveTitle("Joross Farm");
    const href = await page.locator('link[rel="icon"]').getAttribute("href"); expect(href).toContain("favicon-farm.png");
    const icon = await page.request.get(href); expect(icon.ok()).toBe(true); expect(icon.headers()["content-type"]).toContain("image/png");
});

test("live updates wait for an unfinished employee form and refresh after it closes", async ({ page }) => {
    const state = await setup(page); await page.goto("/task-management?tab=employees");
    await page.getByRole("button", { name: /Add Employee/ }).click();
    const dialog = page.getByRole("dialog", { name: "Add Employee", exact: true });
    await dialog.getByLabel("First name", { exact: false }).fill("Unfinished profile");
    const before = state.count("/api/v1/workforce/tasks/page");
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("joross:modules-updated", { detail: { modules: ["employees", "tasks"] } })));
    await page.clock.runFor(500);
    expect(state.count("/api/v1/workforce/tasks/page")).toBe(before);
    await expect(dialog.getByLabel("First name", { exact: false })).toHaveValue("Unfinished profile");
    await dialog.getByRole("button", { name: "Close add employee modal", exact: true }).click();
    await page.getByRole("button", { name: "Leave Without Saving", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect.poll(() => state.count("/api/v1/workforce/tasks/page")).toBeGreaterThan(before);
});

test("My Tasks schedule and leave update automatically and preserve the leave form", async ({ page }) => {
    const state = await setup(page); await page.goto("/my-tasks");
    await page.getByRole("button", { name: "My Schedule", exact: true }).click();
    await expect(page.getByRole("button", { name: /Refresh/i })).toHaveCount(0);
    await expect.poll(() => state.count("/api/v1/workforce/my-schedule")).toBeGreaterThan(0);
    await page.getByRole("button", { name: "Leave Requests", exact: true }).click();
    await page.getByPlaceholder("Reason for leave").fill("Keep this unfinished reason");
    const before = state.count("/api/v1/workforce/leave/my");
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("joross:modules-updated", { detail: { modules: ["calendar", "my_tasks"] } })));
    await expect.poll(() => state.count("/api/v1/workforce/leave/my")).toBeGreaterThan(before);
    await expect(page.getByPlaceholder("Reason for leave")).toHaveValue("Keep this unfinished reason");
    await expect(page.getByRole("button", { name: /Refresh/i })).toHaveCount(0);
});

test.describe("mobile archive views", () => {
    test.use({ viewport: { width: 390, height: 844 } });
    test("dark-mode archive filters and actions fit the page", async ({ page }) => {
        await setup(page); await page.goto("/livestock?archive=1");
        await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
        await expect(page.locator(".archive-records").getByRole("button", { name: "View Details", exact: true })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    });
});
