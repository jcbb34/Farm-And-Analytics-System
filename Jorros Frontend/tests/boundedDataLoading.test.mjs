import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { createRequire } from "node:module";
import { calendarRanges } from "../src/components/DashboardCalendar/calendarRanges.js";
import { withDisplayData } from "../browser-tests/helpers/displayApiFixtures.mjs";

const require = createRequire(import.meta.url);
const parser = require("next/dist/compiled/babel/parser");
const sources = new Map();
function expression(relative, name, returned = false) {
    if (!sources.has(relative)) {
        const text = fs.readFileSync(new URL(`../${relative}`, import.meta.url), "utf8");
        sources.set(relative, { text, tree: parser.parse(text, { sourceType: "module" }) });
    }
    const { text, tree } = sources.get(relative);
    let found;
    function visit(node) {
        if (!node || typeof node !== "object" || found) return;
        if (node.type === "VariableDeclarator" && node.id?.name === name) found = node.init;
        else if (node.type === "FunctionDeclaration" && node.id?.name === name) found = node;
        else for (const child of Object.values(node)) {
            if (Array.isArray(child)) child.forEach(visit);
            else if (child?.type) visit(child);
        }
    }
    visit(tree); assert.ok(found, name);
    if (returned) found = found.body.body.find(node => node.type === "ReturnStatement").argument;
    else if (found.type === "CallExpression") found = found.arguments[0];
    return `(${text.slice(found.start, found.end)})`;
}
function state(initial, extra) {
    const ctx = { AbortController, ...initial, ...extra };
    for (const name of Object.keys(initial)) ctx[`set${name[0].toUpperCase()}${name.slice(1)}`] = next => {
        ctx[name] = typeof next === "function" ? next(ctx[name]) : next;
    };
    return vm.createContext(ctx);
}
const run = (ctx, path, name, returned) => new vm.Script(expression(path, name, returned)).runInContext(ctx);
const stock = "src/views/ProductionSales/useSaleStock.js";
const calendar = "src/components/DashboardCalendar/useCalendarData.js";
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const turn = () => new Promise(resolve => setImmediate(resolve));
function stockContext(service) {
    const ctx = state({ page: { key: "", items: [], total: 0 }, loading: false, error: "" }, {
        open: true, kind: "Production", query: { kind: "Production", search: "", limit: 25 }, key: "production",
        sequence: { current: 0 }, controller: { current: null }, busy: { current: false },
        productionSalesService: { getStock: service }, matching: true, pendingSearch: false,
    });
    ctx.load = run(ctx, stock, "load"); ctx.loadMore = run(ctx, stock, "loadMore"); return ctx;
}
test("sale stock cancels an old search and ignores its late response", async () => {
    const old = deferred(); let calls = 0;
    const ctx = stockContext(async options => ++calls === 1 ? old.promise : { items: [{ id: 71, name: options.search }], total: 1 });
    const request = ctx.load(), abandoned = ctx.controller.current;
    ctx.query = { ...ctx.query, search: "older stock" }; ctx.key = "older";
    await ctx.load(); assert.equal(abandoned.signal.aborted, true);
    old.resolve({ items: [{ id: 1 }], total: 4000 }); await request;
    assert.equal(ctx.page.items[0].id, 71); assert.equal(ctx.page.total, 1); assert.equal(ctx.loading, false);
});
test("sale stock does not request data while closed or append overlapping pages", async () => {
    const gate = deferred(), calls = [];
    const ctx = stockContext(async options => { calls.push(options); return gate.promise; });
    ctx.open = false; await ctx.load(); assert.equal(calls.length, 0); ctx.open = true;
    ctx.page = { key: ctx.key, items: [{ id: 1 }], total: 4 };
    const more = run(ctx, stock, "loadMore"); more(); more();
    assert.equal(calls.length, 1); assert.equal(calls[0].offset, 1); assert.equal(calls[0].limit, 25);
    gate.resolve({ items: [{ id: 1 }, { id: 2 }], total: 4 }); await turn();
    assert.equal(ctx.page.items.length, 2); assert.equal(ctx.page.items[1].id, 2);
});
test("an initial stock failure stops loading and retry can recover", async () => {
    let failing = true;
    const ctx = stockContext(async () => { if (failing) throw new Error("stock unavailable"); return { items: [], total: 0 }; });
    await ctx.load(); ctx.matching = false;
    let result = run(ctx, stock, "useSaleStock", true);
    assert.equal(result.loading, false); assert.equal(result.error, "stock unavailable");
    ctx.pendingSearch = true;
    result = run(ctx, stock, "useSaleStock", true);
    assert.equal(result.loading, true); assert.equal(result.error, ""); ctx.pendingSearch = false;
    failing = false; await result.retry(); ctx.matching = true;
    result = run(ctx, stock, "useSaleStock", true);
    assert.equal(result.error, ""); assert.equal(result.total, 0); assert.equal(result.loading, false);
});
test("calendar ranges cover both month grids, leap dates, and week/day navigation", () => {
    const date = new Date(2024, 1, 29);
    const month = calendarRanges(new Date(2024, 1, 1), date);
    assert.deepEqual(month.summary, { date_from: "2024-01-28", date_to: "2024-03-10" });
    assert.deepEqual(month.day, { date_from: "2024-02-29", date_to: "2024-02-29" });
    assert.deepEqual(month.upcoming, { date_from: "2024-03-01", date_to: "2024-03-07" });
    assert.deepEqual(calendarRanges(date, date, "Week", true).summary, { date_from: "2024-02-25", date_to: "2024-03-02" });
    assert.deepEqual(calendarRanges(date, date, "Day", true).summary, month.day);
    assert.deepEqual(calendarRanges(date, date, "Agenda", true).summary, { date_from: "2024-02-01", date_to: "2024-02-29" });
});
function calendarContext(service) {
    const ranges = calendarRanges(new Date(2026, 10, 1), new Date(2026, 10, 11));
    const ctx = state({ data: { key: "", days: [], summary: {}, day: [], dayTotal: 0, upcoming: [], upcomingTotal: 0, agenda: [], agendaTotal: 0 },
        loading: false, error: "", loadingMore: false, moreError: "" }, {
        ranges, key: "november", agendaOpen: false, sequence: { current: 0 }, controller: { current: null }, moreBusy: { current: false },
        activityService: { getCalendarEvents: service, getCalendarSummary: async () => ({ days: [], summary: { total: 900 } }) },
    });
    ctx.refresh = run(ctx, calendar, "refresh"); ctx.more = run(ctx, calendar, "more"); return ctx;
}
test("calendar initial requests use visible ranges and bounded day/upcoming pages", async () => {
    const calls = [];
    const ctx = calendarContext(async options => { calls.push(options); return { items: [{ id: 1 }], total: 70 }; });
    await ctx.refresh();
    assert.equal(calls.length, 2); assert.deepEqual(calls.map(row => row.limit), [25, 5]);
    assert.equal(ctx.data.summary.total, 900); assert.equal(ctx.data.dayTotal, 70); assert.equal(ctx.data.day.length, 1);
    assert.ok(calls.every(row => row.date_from && row.date_to));
    calls.length = 0; ctx.agendaOpen = true; await ctx.refresh();
    assert.equal(calls.length, 3); assert.equal(calls[2].limit, 25);
});
test("calendar page loading deduplicates and ignores a late page after navigation", async () => {
    const gate = deferred(); let calls = 0;
    const ctx = calendarContext(async () => { calls++; return gate.promise; });
    ctx.data = { ...ctx.data, key: ctx.key, day: [{ id: 1 }], dayTotal: 4 };
    const pending = ctx.more("day"); await ctx.more("day"); assert.equal(calls, 1);
    gate.resolve({ items: [{ id: 1 }, { id: 2 }], total: 4 }); await pending;
    assert.equal(ctx.data.day.length, 2);
    const late = deferred(); ctx.activityService.getCalendarEvents = async () => late.promise;
    const abandoned = ctx.more("day"); ctx.sequence.current++; ctx.key = "december";
    late.resolve({ items: [{ id: 3 }], total: 4 }); await abandoned;
    assert.equal(ctx.data.day.length, 2);
});
test("calendar refresh ignores an obsolete failure and does not erase a newer month", async () => {
    const gate = deferred(); let calls = 0;
    const ctx = calendarContext(async () => ++calls <= 2 ? gate.promise : { items: [{ id: 22 }], total: 1 });
    const old = ctx.refresh(), abandoned = ctx.controller.current;
    ctx.key = "december"; await ctx.refresh(); gate.reject(new Error("obsolete")); await old;
    assert.equal(abandoned.signal.aborted, true); assert.equal(ctx.data.key, "december");
    assert.equal(ctx.data.day[0].id, 22); assert.equal(ctx.error, ""); assert.equal(ctx.loading, false);
});
test("calendar changes received in a hidden tab refresh once when it becomes visible", () => {
    const text = fs.readFileSync(new URL(`../${calendar}`, import.meta.url), "utf8");
    const tree = parser.parse(text, { sourceType: "module" });
    const hook = tree.program.body.find(node => node.type === "ExportDefaultDeclaration").declaration;
    const effect = hook.body.body.find(node => node.type === "ExpressionStatement" && node.expression.callee?.name === "useEffect").expression.arguments[0];
    const listeners = new Map(); let calls = 0;
    const ctx = vm.createContext({ refresh: () => { calls++; }, sequence: { current: 0 }, controller: { current: null },
        window: { addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) },
        document: { visibilityState: "visible", addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name) },
    });
    const cleanup = new vm.Script(`(${text.slice(effect.start, effect.end)})`).runInContext(ctx)();
    assert.equal(calls, 1); ctx.document.visibilityState = "hidden";
    listeners.get("joross:activities-updated")(); listeners.get("joross:activities-updated")(); assert.equal(calls, 1);
    ctx.document.visibilityState = "visible"; listeners.get("visibilitychange")(); listeners.get("visibilitychange")();
    assert.equal(calls, 2); cleanup(); assert.equal(listeners.size, 0); assert.equal(ctx.sequence.current, 1);
});
async function fixture(path, rows) {
    let result;
    await withDisplayData(route => route.fulfill({ json: rows }))({
        request: () => ({ url: () => `http://localhost/api/v1${path}` }), fulfill: options => { result = options.json; },
    });
    return result;
}
test("calendar fixtures keep exact counts while limiting preview rows", async () => {
    const rows = Array.from({ length: 70 }, (_, index) => ({ id: index + 1, activity_date: "2026-11-11", status: "Pending" }));
    const summary = await fixture("/activities/calendar/summary?date_from=2026-11-01&date_to=2026-11-30", rows);
    assert.equal(summary.summary.total, 70); assert.equal(summary.days[0].items.length, 4);
    const page = await fixture("/activities/calendar/events?date_from=2026-11-01&date_to=2026-11-30&offset=25&limit=25", rows);
    assert.equal(page.total, 70); assert.equal(page.items.length, 25); assert.equal(page.items[0].id, 26);
});
test("stock fixtures search the whole collection and exclude unsaleable inventory", async () => {
    const rows = Array.from({ length: 70 }, (_, index) => ({ id: index + 1, name: `Feed ${index}`, quantity: 10, is_saleable: true, unit: "kg" }));
    rows[68].is_saleable = false;
    const page = await fixture("/production-sales/stock?kind=Inventory&search=Feed%2069&limit=25", rows);
    assert.equal(page.total, 1); assert.equal(page.items[0].id, 70);
    assert.equal((await fixture("/production-sales/stock?kind=Inventory&search=Feed%2068", rows)).total, 0);
});
