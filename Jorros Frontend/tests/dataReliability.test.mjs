import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { createRequire } from "node:module";
import { cropService } from "../src/services/cropService.js";
import { inventoryService } from "../src/services/inventoryService.js";
import { livestockService } from "../src/services/livestockService.js";
import { recordEditVersion, isRecordEditConflict } from "../src/services/recordEditing.js";
import { renderReportPreviewMessage } from "../src/services/reportService.js";
import { invalidateReadCache } from "../src/services/httpClient.js";
const require = createRequire(import.meta.url), parser = require("next/dist/compiled/babel/parser");
const files = { reports: "src/views/Reports/hooks/useReportsData.js", conflict: "src/hooks/useRecordEditConflict.js", task: "src/views/TaskManagement/TaskManagement.jsx" };
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
        else for (const value of Object.values(node)) { if (Array.isArray(value)) value.forEach(visit); else if (value?.type) visit(value); }
    };
    visit(source(file).tree); assert.ok(found, name); return found;
}
const evaluate = (ctx, file, node) => new vm.Script(`(${source(file).text.slice(node.start, node.end)})`).runInContext(ctx);
function callback(ctx, file, name) { const node = find(file, name); return evaluate(ctx, file, node.type === "CallExpression" ? node.arguments[0] : node); }
function state(initial, extra = {}) {
    const ctx = { ...initial, AbortController, ...extra };
    for (const name of Object.keys(initial)) ctx[`set${name[0].toUpperCase()}${name.slice(1)}`] = value => { ctx[name] = typeof value === "function" ? value(ctx[name]) : value; };
    return vm.createContext(ctx);
}
const gate = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { resolve, promise }; };
function reportContext(service) {
    return state({ reports: [], reportSummary: null, reportsLoading: false, reportsLoadingMore: false, reportsError: "", reportsHasMore: false, summaryLoading: false, summaryError: "" }, {
        queryKey: JSON.stringify({ search: "old" }), reportsPageSize: 25, requestSequence: { current: 0 }, rowsRequest: { current: null },
        summarySequence: { current: 0 }, summaryRequest: { current: null }, loadedQuery: { current: "" },
        summaryState: { current: { key: "", value: null } }, nextOffset: { current: 0 }, loadingMoreRef: { current: false }, reportService: service,
    });
}
test("report rows remain usable when totals fail, and totals can retry independently", async () => {
    let listCalls = 0;
    const ctx = reportContext({ getReports: async () => { listCalls++; return [{ id: 7 }]; }, getReportSummary: async () => { throw new Error("totals offline"); } });
    await Promise.all([callback(ctx, files.reports, "loadReportRows")(), callback(ctx, files.reports, "loadReportSummary")()]);
    assert.equal(ctx.reports[0].id, 7); assert.equal(ctx.reportsError, ""); assert.equal(ctx.summaryError, "totals offline");
    ctx.reportService.getReportSummary = async () => ({ matchingTotal: 1, approved: 1 });
    await callback(ctx, files.reports, "loadReportSummary")();
    assert.equal(listCalls, 1); assert.equal(ctx.reportSummary.approved, 1); assert.equal(ctx.summaryError, "");
});
test("a report refresh failure keeps the same-query rows and permits a retry", async () => {
    const ctx = reportContext({ getReports: async () => { throw new Error("offline"); } });
    ctx.loadedQuery.current = ctx.queryKey; ctx.reports = [{ id: 3 }]; ctx.nextOffset.current = 1;
    const load = callback(ctx, files.reports, "loadReportRows"); await load();
    assert.equal(ctx.reports[0].id, 3); assert.equal(ctx.reportsError, "offline"); assert.equal(ctx.reportsLoading, false);
    ctx.reportService.getReports = async () => [{ id: 9 }]; await load();
    assert.equal(ctx.reports[0].id, 9); assert.equal(ctx.reportsError, "");
});
test("new report searches cancel obsolete rows and ignore late totals", async () => {
    const rows = gate(), totals = gate(), calls = [];
    const ctx = reportContext({ getReports: async (_archive, query) => { calls.push(query); return query.search === "old" ? rows.promise : [{ id: 2 }]; },
        getReportSummary: async query => query.search === "old" ? totals.promise : { matchingTotal: 1, approved: 2 } });
    const load = callback(ctx, files.reports, "loadReportRows"), summary = callback(ctx, files.reports, "loadReportSummary");
    const oldRows = load(), oldTotals = summary(); ctx.queryKey = JSON.stringify({ search: "new" }); await Promise.all([load(), summary()]);
    assert.equal(calls[0].signal.aborted, true);
    rows.resolve([{ id: 1 }]); totals.resolve({ matchingTotal: 100, approved: 99 }); await Promise.all([oldRows, oldTotals]);
    assert.equal(ctx.reports[0].id, 2); assert.equal(ctx.reportSummary.approved, 2); assert.equal(ctx.reportsHasMore, false);
});
test("report paging remains available without totals and stops at the final short page", async () => {
    const calls = [], ctx = reportContext({ getReports: async (_archive, query) => { calls.push(query); return query.offset ? [{ id: 26 }] : Array.from({ length: 25 }, (_, index) => ({ id: index + 1 })); } });
    await callback(ctx, files.reports, "loadReportRows")(); assert.equal(ctx.reportsHasMore, true);
    await callback(ctx, files.reports, "loadMoreReports")();
    assert.equal(calls[1].offset, 25); assert.equal(ctx.reports.length, 26); assert.equal(ctx.reportsHasMore, false);
});
test("changing a report query cancels an in-flight next page", async () => {
    const next = gate(), calls = [], ctx = reportContext({ getReports: async (_archive, query) => { calls.push(query); return query.offset ? next.promise : [{ id: 99 }]; } });
    ctx.reportsHasMore = true; ctx.reports = [{ id: 1 }]; ctx.nextOffset.current = 1;
    const old = callback(ctx, files.reports, "loadMoreReports")(); ctx.queryKey = JSON.stringify({ search: "new" }); await callback(ctx, files.reports, "loadReportRows")();
    next.resolve([{ id: 2 }]); await old; assert.equal(calls[0].signal.aborted, true); assert.equal(ctx.reports.length, 1); assert.equal(ctx.reports[0].id, 99);
});
test("assisted work reports inventory failures before it can submit incomplete work", async () => {
    const messages = [], ctx = vm.createContext({ assistedTask: { resource_required: true }, assistedInventoryChoices: { loading: false, error: "Stock lookup failed" }, assistedSelectedInventoryItem: null,
        notification: { error: message => messages.push(message) } });
    await callback(ctx, files.task, "submitAssistedWork")(); assert.deepEqual(messages, ["Stock lookup failed"]);
    ctx.assistedInventoryChoices = { loading: true, error: "" }; await callback(ctx, files.task, "submitAssistedWork")();
    assert.match(messages[1], /finish loading/);
});
function conflictContext(loader) {
    const replacements = [];
    const ctx = state({ message: "", error: "", reloading: false }, { open: true, id: 7, sequence: { current: 0 }, busy: { current: false },
        loadRecord: loader, replaceForm: latest => replacements.push(latest), isRecordEditConflict, recordEditVersion });
    return { ctx, replacements };
}
test("an edit conflict keeps entries until the user explicitly reloads", async () => {
    const { ctx, replacements } = conflictContext(async () => ({ id: 7, editVersion: 5, name: "Current server value" }));
    assert.equal(callback(ctx, files.conflict, "handleError")({ code: "RECORD_CONFLICT", message: "Changed elsewhere" }), true);
    assert.equal(replacements.length, 0); assert.equal(ctx.message, "Changed elsewhere");
    await callback(ctx, files.conflict, "reload")(); assert.equal(replacements[0].editVersion, 5); assert.equal(ctx.message, "");
});
test("failed conflict reloads preserve entries and can retry without discarding the warning", async () => {
    const { ctx, replacements } = conflictContext(async () => { throw new Error("offline"); }); ctx.message = "Changed elsewhere";
    const reload = callback(ctx, files.conflict, "reload"); await reload(); assert.equal(replacements.length, 0); assert.equal(ctx.message, "Changed elsewhere"); assert.equal(ctx.error, "offline"); assert.equal(ctx.reloading, false);
    ctx.loadRecord = async () => ({ id: 7, editVersion: 8 }); await reload(); assert.equal(replacements.length, 1); assert.equal(ctx.error, "");
});
test("an abandoned record reload cannot replace a newly opened form", async () => {
    const request = gate(), { ctx, replacements } = conflictContext(() => request.promise);
    const pending = callback(ctx, files.conflict, "reload")(); ++ctx.sequence.current; ctx.id = 8;
    request.resolve({ id: 7, editVersion: 5 }); await pending; assert.equal(replacements.length, 0);
});
test("invalid or missing versions cannot be silently replaced with a guessed value", () => {
    for (const value of [undefined, null, 0, -1, 1.5, "bad"]) assert.throws(() => recordEditVersion({ editVersion: value }), { code: "RECORD_VERSION_REQUIRED" });
    assert.equal(recordEditVersion({ editVersion: 4 }), 4); assert.equal(recordEditVersion({ edit_version: 5 }), 5);
});
test("PDF preview messages are rendered as literal text with no HTML insertion", () => {
    function element() { return { style: {}, children: [], append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; }, set innerHTML(_value) { throw new Error("HTML insertion is forbidden"); } }; }
    const document = { body: element(), createElement: element }, message = '<img src=x onerror="attack()"><script>attack()</script>';
    renderReportPreviewMessage({ document }, "Error", message, true);
    assert.equal(document.title, "Error"); assert.equal(document.body.children[0].children[1].textContent, message);
});
const original = Object.fromEntries(["window", "sessionStorage", "localStorage", "fetch"].map(key => [key, globalThis[key]]));
function fakeBrowser() {
    invalidateReadCache(); globalThis.window = { location: { origin: "http://localhost:3000" }, setTimeout, clearTimeout, dispatchEvent: () => {} };
    globalThis.sessionStorage = globalThis.localStorage = { getItem: () => null };
}
test.after(() => Object.assign(globalThis, original));
for (const [name,update,read] of [["Crop", cropService.updateCrop, cropService.getCrop], ["Inventory", inventoryService.updateInventory, inventoryService.getInventoryItem], ["Livestock", livestockService.updateLivestock, livestockService.getLivestockRecord]]) {
    test(`${name} edits send their original version without fetching a replacement token`, async () => {
        fakeBrowser(); const calls = []; globalThis.fetch = async (_url, options) => { calls.push(options); return Response.json({ id: 7, edit_version: 5, name: "Mine", record_name: "Mine" }); };
        await update(7, { editVersion: 4, name: "Mine", recordName: "Mine" });
        assert.equal(calls.length, 1); assert.equal(JSON.parse(calls[0].body).expected_version, 4);
    });
    test(`${name} conflicts remain explicit and latest-record reloads bypass cached reads`, async () => {
        fakeBrowser(); let calls = 0;
        globalThis.fetch = async () => { calls++; return Response.json({ detail: "Changed elsewhere" }, { status: 409, headers: { "X-Record-Conflict": "RECORD_CONFLICT" } }); };
        await assert.rejects(update(7, { editVersion: 4, name: "Mine", recordName: "Mine" }), { code: "RECORD_CONFLICT" }); assert.equal(calls, 1);
        globalThis.fetch = async (_url, options) => { assert.equal(options.cache, "no-store"); return Response.json({ id: 7, edit_version: 8 }); };
        assert.equal((await read(7)).editVersion, 8);
    });
}
