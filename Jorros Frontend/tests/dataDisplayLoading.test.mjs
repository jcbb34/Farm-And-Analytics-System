import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import test from "node:test";
import { createRequire } from "node:module";
import { buildMyTasksPageQuery } from "../src/views/MyTasks/taskPageQuery.js";
import { filterAndSortMyTasks } from "../src/views/MyTasks/taskView.js";
import { addCalendarDays } from "../src/utils/farmCalendar.js";
import { chartRange } from "../src/components/DashboardCharts/chartRange.js";

const require = createRequire(import.meta.url);
const parser = require("next/dist/compiled/babel/parser");
const root = path.resolve(import.meta.dirname, "..");
const sourceCache = new Map();
function expression(relative, name) {
    let source = sourceCache.get(relative);
    if (!source) {
        const text = fs.readFileSync(path.join(root, relative), "utf8");
        source = { text, tree: parser.parse(text, { sourceType: "module", plugins: ["jsx"] }) };
        sourceCache.set(relative, source);
    }
    let found;
    function visit(node) {
        if (!node || typeof node !== "object" || found) return;
        if (node.type === "VariableDeclarator" && node.id?.name === name) found = node.init;
        if (node.type === "FunctionDeclaration" && node.id?.name === name) found = node;
        if (!found) for (const value of Object.values(node)) {
            if (Array.isArray(value)) value.forEach(visit);
            else if (value?.type) visit(value);
        }
    }
    visit(source.tree);
    assert.ok(found, `${relative}: ${name}`);
    if (found.type === "CallExpression" && ["useCallback", "useMemo"].includes(found.callee?.name)) found = found.arguments[0];
    return source.text.slice(found.start, found.end);
}
function state(initial) {
    const context = { AbortController, console, ...initial };
    for (const key of Object.keys(initial)) context[`set${key[0].toUpperCase()}${key.slice(1)}`] = value => {
        context[key] = typeof value === "function" ? value(context[key]) : value;
    };
    return vm.createContext(context);
}
const run = (ctx, file, name) => new vm.Script(`(${expression(file, name)})`).runInContext(ctx);
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const files = { tasks: "src/views/MyTasks/MyTasks.jsx", stock: "src/views/Inventory/hooks/useInventoryPage.js", alerts: "src/views/Alerts/Alerts.jsx", sales: "src/views/ProductionSales/ProductionSales.jsx", crops: "src/views/Crops/hooks/useCropsPage.js", animals: "src/views/Livestock/Livestock.jsx", dashboard: "src/views/Dashboard/Dashboard.jsx" };
const today = "2026-11-11";

function tasksContext(service) {
    return Object.assign(state({ tasks: [], taskTotal: 0, activeTaskSnapshot: [], loading: false, loadingMore: false, error: "" }), {
        buildMyTasksPageQuery, addCalendarDays, taskCacheRef: { current: new Map() }, taskRequestRef: { current: null }, taskRequestSequenceRef: { current: 0 },
        identityKey: "test-user", taskView: "active", debouncedSearch: "alpha", priorityFilter: "all", scheduleFilter: "timeline", selectedTaskDate: null, farmToday: today,
        backendTaskView: "active", backendTaskScope: "timeline", sharedDeviceMode: false, workforceService: { getMyTasksPage: service },
    });
}

test("cached My Tasks search cancels a delayed query and keeps matching assignments", async () => {
    const gate = deferred();
    const alpha = { id: 1, name: "Alpha Feeding", status: "Pending", activity_date: today };
    const ctx = tasksContext(async query => query.search === "beta" ? gate.promise : { items: [alpha], total: 1 });
    const load = run(ctx, files.tasks, "loadTasks");
    await load("active", { scope: "timeline" });
    ctx.debouncedSearch = "beta"; const old = load("active", { scope: "timeline" });
    const abandoned = ctx.taskRequestRef.current;
    ctx.debouncedSearch = "alpha"; await load("active", { scope: "timeline" });
    assert.equal(abandoned.signal.aborted, true);
    assert.equal(ctx.loading, false);
    gate.resolve({ items: [{ ...alpha, id: 2, name: "Beta Watering" }], total: 1 }); await old;
    assert.equal(ctx.tasks[0].name, "Alpha Feeding");
    assert.equal(filterAndSortMyTasks({ tasks: ctx.tasks, taskView: "active", searchTerm: "alpha", priorityFilter: "all", scheduleFilter: "timeline", todayKey: today, upcomingLimitKey: "2026-11-18" }).length, 1);
});

test("an obsolete My Tasks error cannot replace a cached result with an error", async () => {
    const gate = deferred();
    const ctx = tasksContext(async query => query.search === "beta" ? gate.promise : { items: [{ id: 1 }], total: 1 });
    const load = run(ctx, files.tasks, "loadTasks");
    await load("active"); ctx.debouncedSearch = "beta"; const old = load("active");
    ctx.debouncedSearch = "alpha"; await load("active");
    gate.reject(new Error("obsolete failure")); await old;
    assert.equal(ctx.error, ""); assert.equal(ctx.loading, false); assert.equal(ctx.tasks[0].id, 1);
});

test("My Tasks prevents overlapping Load More requests and ignores late pages after filter changes", async () => {
    const gate = deferred(); let requests = 0;
    const ctx = tasksContext(async () => { requests += 1; return gate.promise; });
    ctx.tasks = [{ id: 1 }]; ctx.taskTotal = 3;
    const more = run(ctx, files.tasks, "loadMoreTasks");
    const pending = more(); await more(); assert.equal(requests, 1);
    ctx.taskRequestSequenceRef.current += 1;
    gate.resolve({ items: [{ id: 2 }], total: 3 }); await pending;
    assert.equal(ctx.tasks.length, 1);
});

function stockContext(summary, movements) {
    return Object.assign(state({ inventorySummaryData: null, movementSummary: [], summaryLoading: true, summaryError: "", movementError: "", inventoryError: "" }), {
        summaryRequestRef: { current: 0 }, inventoryService: { getInventorySummary: summary, getMovementSummary: movements }, formatCurrency: value => `PHP ${value}`,
    });
}
test("failed inventory summary shows unavailable totals without failing the stock list", async () => {
    const ctx = stockContext(async () => { throw new Error("totals failed"); }, async () => [{ quantity: 7 }]);
    await run(ctx, files.stock, "loadSummary")();
    const cards = run(ctx, files.stock, "inventorySummary")();
    assert.ok(cards.every(card => card.value === "—")); assert.equal(ctx.inventoryError, "");
    assert.equal(ctx.summaryError, "totals failed"); assert.equal(ctx.movementSummary.length, 1);
});
test("stock-movement failure does not erase successful inventory totals", async () => {
    const ctx = stockContext(async () => ({ total: 120, in_stock: 119, low_stock: 0, out_of_stock: 1, total_value: 5000 }), async () => { throw new Error("movements failed"); });
    await run(ctx, files.stock, "loadSummary")();
    assert.equal(run(ctx, files.stock, "inventorySummary")()[0].value, 120);
    assert.equal(ctx.summaryError, ""); assert.equal(ctx.inventoryError, ""); assert.equal(ctx.movementError, "movements failed");
});
test("an old inventory summary cannot overwrite a newer successful summary", async () => {
    const gate = deferred(); let requests = 0;
    const ctx = stockContext(async () => ++requests === 1 ? gate.promise : { total: 121 }, async () => []);
    const load = run(ctx, files.stock, "loadSummary"), old = load(); await load();
    gate.resolve({ total: 1 }); await old;
    assert.equal(ctx.inventorySummaryData.total, 121);
});
test("Alerts distinguishes a failed summary from a successful zero and supports retry", async () => {
    let fail = true;
    const ctx = Object.assign(state({ summaryData: null, summaryLoading: true, summaryError: "" }), {
        summaryRequestRef: { current: 0 }, alertService: { getAlertSummary: async () => { if (fail) throw new Error("summary failed"); return { active: 0, high_priority: 0, overdue_tasks: 0, history: 0 }; } },
    });
    const load = run(ctx, files.alerts, "loadAlertSummary"); await load();
    assert.ok(run(ctx, files.alerts, "summaryCards")().every(card => card.value === "—"));
    assert.equal(ctx.summaryError, "summary failed"); fail = false; await load();
    assert.ok(run(ctx, files.alerts, "summaryCards")().every(card => card.value === 0));
    assert.equal(ctx.summaryError, "");
});

function salesContext(service) {
    const ctx = Object.assign(state({ reproduction: [], production: [], processing: [], sales: [], hasMore: {}, tabLoading: false, loadingMore: false, listError: "" }), {
        listRequestRef: { current: 0 }, moreRequestRef: { current: false }, PAGE_SIZE: 50, scope: "crops", debouncedSearch: "older crop", search: "older crop", activeTab: "sales",
        productionSalesService: { getSales: service, getProduction: service, getProcessing: service, getReproduction: service },
    });
    ctx.listOptions = run(ctx, files.sales, "listOptions"); ctx.fetchTab = run(ctx, files.sales, "fetchTab"); ctx.setTabRows = run(ctx, files.sales, "setTabRows");
    return ctx;
}
test("Production & Sales sends the scope and full search before its first page and Load More", async () => {
    const calls = [];
    const ctx = salesContext(async options => { calls.push(options); return Array.from({ length: 50 }, (_, id) => ({ id: id + options.offset })); });
    await run(ctx, files.sales, "loadTab")("sales"); await run(ctx, files.sales, "loadMore")();
    assert.equal(calls.length, 2);
    assert.deepEqual(calls.map(row => row.offset), [0, 50]);
    assert.ok(calls.every(row => row.source_type === "Crop" && row.search === "older crop" && row.include_voided === false));
    assert.equal(ctx.sales.length, 100);
});
test("changing a sales scope ignores late records from the old scope", async () => {
    const gate = deferred();
    const ctx = salesContext(async options => options.source_type === "Crop" ? gate.promise : [{ id: 2, source_type: "Livestock" }]);
    const load = run(ctx, files.sales, "loadTab"); const old = load("sales");
    ctx.scope = "livestock"; await load("sales"); gate.resolve([{ id: 1, source_type: "Crop" }]); await old;
    assert.equal(ctx.sales[0].source_type, "Livestock"); assert.equal(ctx.tabLoading, false);
});
test("Load More cannot append a page after a newer sales search completes", async () => {
    const gate = deferred();
    const ctx = salesContext(async options => options.offset ? gate.promise : [{ id: 9 }]);
    ctx.sales = [{ id: 1 }]; ctx.hasMore = { sales: true };
    const old = run(ctx, files.sales, "loadMore")();
    ctx.debouncedSearch = "new"; ctx.search = "new"; await run(ctx, files.sales, "loadTab")("sales");
    gate.resolve([{ id: 2 }]); await old;
    assert.equal(ctx.sales.length, 1); assert.equal(ctx.sales[0].id, 9);
});
test("Crops uses independent whole-farm totals instead of the 50 loaded rows", async () => {
    const ctx = Object.assign(state({ crops: [], cropTotal: 0, overview: null, cropsLoading: false, cropsError: "", overviewLoading: true, overviewError: "", loadingMore: false }), {
        requestRef: { current: 0 }, moreRef: { current: false }, overviewSequence: { current: 0 }, query: {},
        cropService: {
            getCropPage: async options => { assert.equal(options.include_overview, false); return { items: Array.from({ length: 50 }, (_, id) => ({ id })), total: 500, overview: null }; },
            getSummary: async () => ({ total: 700, active: 500, harvested: 200, alerts: 12 }),
        },
    });
    await Promise.all([run(ctx, files.crops, "loadCrops")(), run(ctx, files.crops, "loadCropSummary")()]);
    const cards = run(ctx, files.crops, "cropSummary")();
    assert.equal(ctx.crops.length, 50); assert.equal(ctx.cropTotal, 500); assert.equal(cards[0].value, 700); assert.equal(cards[1].value, 500);
});
test("Livestock list refresh leaves the open detailed animal and history untouched", async () => {
    const ctx = Object.assign(state({ livestock: [], livestockTotal: 0, livestockOverview: null, livestockLoading: false, livestockError: "", loadingMore: false,
        selectedAnimal: { id: 1, growthRecords: [{ id: 90 }], vaccinationRecords: [{ id: 91 }] } }), {
        listRequestRef: { current: 0 }, moreRequestRef: { current: false }, listQuery: {}, decorateLivestockRecord: row => row,
        livestockService: { getLivestockPage: async () => ({ items: [{ id: 1, growthRecords: [] }], total: 100, overview: { total: 1000, healthy: 900, risk: 100, vaccination_due: 30, births: 20 } }) },
    });
    await run(ctx, files.animals, "loadLivestock")();
    assert.equal(ctx.selectedAnimal.growthRecords.length, 1); assert.equal(ctx.selectedAnimal.vaccinationRecords.length, 1);
    assert.equal(run(ctx, files.animals, "statistics")()[0].value, 1000);
});
test("legacy livestock events defer refresh until the open dialog closes", async () => {
    const listeners = new Map(), timers = new Map(), effects = []; let dialogOpen = true, observer, refreshed = 0, id = 0;
    const ctx = vm.createContext({
        useRef: initial => ({ current: initial }), useEffect: effect => { effects.push(effect()); },
        notifyInfo() {}, setTimeout: callback => { timers.set(++id, callback); return id; }, clearTimeout: key => timers.delete(key),
        document: { visibilityState: "visible", body: {}, querySelector: () => dialogOpen ? {} : null, addEventListener() {}, removeEventListener() {} },
        window: { addEventListener: (name, listener) => listeners.set(name, listener), removeEventListener: name => listeners.delete(name) },
        MutationObserver: class { constructor(callback) { observer = callback; } observe() {} disconnect() {} },
    });
    run(ctx, "src/hooks/useFarmModuleUpdates.js", "useFarmModuleUpdates")(["livestock"], async () => { refreshed += 1; });
    listeners.get("joross:livestock-updated")({ type: "joross:livestock-updated" });
    assert.equal(refreshed, 0); assert.equal(timers.size, 0);
    dialogOpen = false; observer();
    for (const callback of timers.values()) await callback();
    assert.equal(refreshed, 1);
    for (const cleanup of effects) cleanup?.();
});
test("Dashboard failed crop and task totals stay unavailable while other modules remain valid", async () => {
    const ctx = Object.assign(state({ loading: false, loadError: "", crops: [], livestock: [], inventory: [], cropOverview: null,
        livestockOverview: null, inventoryOverview: null, alertCount: null, sourceErrors: {}, inventoryError: "", activitiesLoading: false, activitiesError: "", taskCount: null }), {
        range: { startDate: today, endDate: today }, coreRequestRef: { current: 0 }, tasksRequestRef: { current: 0 }, farmDateKey: () => today,
        cropService: { getOverview: async () => { throw new Error("crop failed"); } },
        livestockService: { getOverview: async () => ({ total: 400, chart_records: [] }) },
        inventoryService: { getInventorySummary: async () => ({ preview_items: [] }) },
        alertService: { getAlertSummary: async () => ({ active: 7 }) },
        activityService: { getSummary: async () => { throw new Error("tasks failed"); } },
    });
    await run(ctx, files.dashboard, "loadCoreDashboardData")(); await run(ctx, files.dashboard, "loadDashboardActivities")();
    const cards = run(ctx, files.dashboard, "summaryCards")();
    assert.equal(cards[0].value, "—"); assert.equal(cards[1].value, "400"); assert.equal(cards[2].value, "7"); assert.equal(cards[4].value, "—");
    assert.equal(ctx.activitiesError, "tasks failed");
});

test("chart filters request exact ranges including month/year boundaries and custom dates", () => {
    const now = new Date(2026, 0, 2, 12);
    assert.deepEqual(chartRange("Last Month", now), { startDate: "2025-12-01", endDate: "2025-12-31" });
    assert.deepEqual(chartRange("Last 7 Days", now), { startDate: "2025-12-27", endDate: "2026-01-02" });
    assert.deepEqual(chartRange("2026-09-03 to 2026-11-27", now), { startDate: "2026-09-03", endDate: "2026-11-27" });
});
