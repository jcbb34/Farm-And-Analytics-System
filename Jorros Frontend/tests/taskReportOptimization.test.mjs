import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url), parser = require("next/dist/compiled/babel/parser");
const files = {
    task: "src/views/TaskManagement/hooks/useTaskManagementData.js", choice: "src/hooks/useResourceChoices.js",
    pdf: "src/views/Reports/hooks/useReportPdfJobs.js", service: "src/services/reportService.js",
};
const sources = new Map();
function source(file) {
    if (!sources.has(file)) {
        const text = fs.readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
        sources.set(file, { text, tree: parser.parse(text, { sourceType: "module", plugins: ["jsx"] }) });
    }
    return sources.get(file);
}
function find(file, name) {
    let found;
    const visit = node => {
        if (!node || typeof node !== "object" || found) return;
        if ((node.type === "VariableDeclarator" || node.type === "FunctionDeclaration") && node.id?.name === name)
            found = node.type === "VariableDeclarator" ? node.init : node;
        else for (const value of Object.values(node)) {
            if (Array.isArray(value)) value.forEach(visit); else if (value?.type) visit(value);
        }
    };
    visit(source(file).tree); assert.ok(found, name); return found;
}
const evaluate = (ctx, file, node) => new vm.Script(`(${source(file).text.slice(node.start, node.end)})`).runInContext(ctx);
function callback(ctx, file, name) { const node = find(file, name); return evaluate(ctx, file, node.type === "CallExpression" ? node.arguments[0] : node); }
function returned(ctx, file, name) { return evaluate(ctx, file, find(file, name).body.body.find(node => node.type === "ReturnStatement").argument); }
function effects(file, name) { return find(file, name).body.body.filter(node => node.type === "ExpressionStatement" && node.expression.callee?.name === "useEffect").map(node => node.expression.arguments[0]); }
function state(initial, extra = {}) {
    const ctx = { ...initial, AbortController, ...extra };
    for (const name of Object.keys(initial)) ctx[`set${name[0].toUpperCase()}${name.slice(1)}`] = value => { ctx[name] = typeof value === "function" ? value(ctx[name]) : value; };
    return vm.createContext(ctx);
}
const gate = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { resolve, promise }; };
function taskContext(service = {}) {
    return state({ tasks: [], taskTotal: 0, loading: false, error: "", taskSummary: null, summaryLoading: false, summaryError: "", employees: [], employeesLoading: false, employeesError: "" }, {
        currentQuery: () => ({ search: "old" }), loadRequestIdRef: { current: 0 }, taskRequest: { current: null },
        moreInFlightRef: { current: false }, summarySequence: { current: 0 }, employeeSequence: { current: 0 }, workforceService: service,
    });
}
test("task results survive independent summary and employee failures", async () => {
    const calls = [], ctx = taskContext({ getTasksPage: async () => { calls.push("tasks"); return { items: [{ id: 7 }], total: 200 }; },
        getTaskManagementSummary: async () => { throw new Error("summary unavailable"); }, getEmployees: async () => { throw new Error("employees unavailable"); } });
    await Promise.all(["load", "loadSummary", "loadEmployees"].map(name => callback(ctx, files.task, name)()));
    assert.deepEqual(calls, ["tasks"]); assert.equal(ctx.tasks[0].id, 7); assert.equal(ctx.taskTotal, 200); assert.equal(ctx.error, "");
    assert.equal(ctx.summaryError, "summary unavailable"); assert.equal(ctx.employeesError, "employees unavailable");
});
test("a new task search aborts and ignores an older response", async () => {
    const old = gate(), calls = [];
    const ctx = taskContext({ getTasksPage: async (query, options) => { calls.push(options); return query.search === "old" ? old.promise : { items: [{ id: 9 }], total: 1 }; } });
    const load = callback(ctx, files.task, "load"), first = load(); ctx.currentQuery = () => ({ search: "new" }); await load();
    assert.equal(calls[0].signal.aborted, true); old.resolve({ items: [{ id: 1 }], total: 100 }); await first;
    assert.equal(ctx.tasks[0].id, 9); assert.equal(ctx.taskTotal, 1); assert.equal(ctx.loading, false);
});
test("failed task requests retain rows and a successful empty retry keeps zero total", async () => {
    const ctx = taskContext({ getTasksPage: async () => { throw new Error("offline"); } });
    ctx.tasks = [{ id: 3 }]; ctx.taskTotal = 100;
    const load = callback(ctx, files.task, "load"); await load(); assert.equal(ctx.tasks[0].id, 3); assert.equal(ctx.error, "offline");
    ctx.workforceService.getTasksPage = async () => ({ items: [], total: 0 }); await load();
    assert.equal(ctx.tasks.length, 0); assert.equal(ctx.taskTotal, 0); assert.equal(ctx.error, "");
});
test("task pagination cannot append after a newer first page", async () => {
    const old = gate(), calls = [];
    const ctx = taskContext({ getTasksPage: async (query, options) => { calls.push(options); return query.offset ? old.promise : { items: [{ id: 99 }], total: 1 }; } });
    ctx.tasks = [{ id: 1 }]; ctx.taskTotal = 30;
    const more = callback(ctx, files.task, "loadMore")(); await callback(ctx, files.task, "load")();
    assert.equal(calls[0].signal.aborted, true); old.resolve({ items: [{ id: 2 }], total: 30 }); await more;
    assert.equal(ctx.tasks.length, 1); assert.equal(ctx.tasks[0].id, 99);
});
test("work filters retain existing priority for feeding, fertilizer and monitoring", () => {
    const kind = callback(vm.createContext({}), files.choice, "resourceChoiceWorkKind");
    assert.equal(kind("Crop", "fertilizer and pest control"), "fertilizer");
    assert.equal(kind("Livestock", "feeding and vitamins"), "feed");
    assert.equal(kind("Livestock", "booster vaccination"), "vaccine");
    assert.equal(kind("Crop", "growth monitoring"), "all");
});
function choiceContext(service) {
    return state({ page: { key: "", items: [], selected: null, total: 0 }, loading: false, error: "" }, {
        enabled: true, pending: false, query: { domain: "Crop", search: "", limit: 25 }, key: "crop", search: "",
        sequence: { current: 0 }, controller: { current: null }, busy: { current: false }, httpClient: { get: service }, setSearch: () => {},
    });
}
test("creation choices use bounded pages and do not fetch when closed", async () => {
    const calls = [], ctx = choiceContext(async (...args) => { calls.push(args); return { items: [{ id: 1 }], total: 81, selected: null }; });
    const load = callback(ctx, files.choice, "load"); ctx.load = load; ctx.enabled = false; await load(); assert.equal(calls.length, 0);
    ctx.enabled = true; await load(); assert.equal(calls[0][1].query.limit, 25); assert.equal(calls[0][1].cache, "no-store"); assert.ok(calls[0][1].signal);
    assert.equal(ctx.page.total, 81);
});
test("a pinned choice stays selectable without changing the matching count or page offset", async () => {
    const calls = [], ctx = choiceContext(async (...args) => { calls.push(args); return calls.length === 1
        ? { items: [{ id: 1 }, { id: 2 }], selected: { id: 90 }, total: 3 }
        : { items: [{ id: 2 }, { id: 3 }], selected: { id: 90 }, total: 3 }; });
    ctx.load = callback(ctx, files.choice, "load"); await ctx.load(); ctx.matching = true; ctx.items = [{ id: 90 }, ...ctx.page.items];
    let result = returned(ctx, files.choice, "useResourceChoices");
    assert.equal(result.items[0].id, 90); assert.equal(result.pageCount, 2); assert.equal(result.total, 3);
    result.loadMore(); await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls[1][1].query.offset, 2); assert.equal(ctx.page.items.length, 3);
});
test("late choice responses cannot overwrite a new domain and failures can retry", async () => {
    const old = gate(), calls = [], ctx = choiceContext(async (...args) => { calls.push(args); return args[1].query.domain === "Crop" ? old.promise : { items: [{ id: 10 }], total: 1 }; });
    const load = callback(ctx, files.choice, "load"), first = load(); ctx.query = { domain: "Livestock", limit: 25 }; ctx.key = "livestock"; await load();
    assert.equal(calls[0][1].signal.aborted, true); old.resolve({ items: [{ id: 1 }], total: 81 }); await first; assert.equal(ctx.page.items[0].id, 10);
    ctx.httpClient.get = async () => { throw new Error("offline"); }; await load(); assert.equal(ctx.error, "offline"); assert.equal(ctx.loading, false);
    ctx.httpClient.get = async () => ({ items: [], total: 0 }); await load(); assert.equal(ctx.error, ""); assert.equal(ctx.page.total, 0);
});
function pdfContext(service) {
    return state({ data: { key: "", rows: [] }, error: "" }, { key: "1", sequence: { current: 0 }, requestRef: { current: null }, reportService: { getPdfJobs: service } });
}
test("PDF status reads coalesce and a forced refresh supersedes an older page", async () => {
    const first = gate(), calls = [], ctx = pdfContext(async (...args) => { calls.push(args); return calls.length === 1 ? first.promise : [{ report_id: 2, status: "Ready" }]; });
    const refresh = callback(ctx, files.pdf, "refreshPdfJobs"), pending = refresh();
    assert.equal(refresh(), pending); assert.equal(calls.length, 1); ctx.key = "2"; await refresh({ force: true });
    assert.equal(calls[0][1].aborted, true); first.resolve([{ report_id: 1, status: "Queued" }]); await pending;
    assert.equal(ctx.data.key, "2"); assert.equal(ctx.data.rows[0].status, "Ready");
});
test("PDF polling pauses while hidden and stops on ready or an error", () => {
    let tick, cleared = 0, calls = 0;
    const ctx = vm.createContext({ pending: true, pdfJobsError: "", document: { hidden: false }, refreshPdfJobs: () => { calls++; },
        window: { setInterval: (fn, ms) => { tick = fn; assert.equal(ms, 2000); return 7; }, clearInterval: value => { assert.equal(value, 7); cleared++; } } });
    const effect = effects(files.pdf, "useReportPdfJobs")[1], cleanup = evaluate(ctx, files.pdf, effect)();
    tick(); ctx.document.hidden = true; tick(); assert.equal(calls, 1); cleanup(); assert.equal(cleared, 1);
    ctx.pending = false; assert.equal(evaluate(ctx, files.pdf, effect)(), undefined);
    ctx.pending = true; ctx.pdfJobsError = "offline"; assert.equal(evaluate(ctx, files.pdf, effect)(), undefined);
});
test("a pending JSON download never becomes a fake PDF file", async () => {
    const ctx = vm.createContext({ httpClient: { download: async () => new Blob([JSON.stringify({ report_id: 1, status: "Queued" })], { type: "application/json" }) }, Error, JSON });
    const download = callback(ctx, files.service, "getAuthenticatedBlob");
    await assert.rejects(download("/reports/1/pdf", "application/pdf"), error => error.pdfJob.status === "Queued");
    ctx.httpClient.download = async () => new Blob(["%PDF"], { type: "application/pdf" });
    assert.equal((await download("/reports/1/pdf", "application/pdf")).type, "application/pdf");
});
