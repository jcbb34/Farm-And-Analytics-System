import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { createRequire } from "node:module";
import { evidencePaths } from "../src/components/EvidencePhoto/evidencePaths.js";
import { farmDateKey } from "../src/utils/farmCalendar.js";
import { validateStaffCalendarPayload } from "../src/views/StaffCalendar/staffAttendance.js";

const require = createRequire(import.meta.url);
const parser = require("next/dist/compiled/babel/parser");
const files = { calendar: "src/views/StaffCalendar/StaffCalendar.jsx", image: "src/components/EvidencePhoto/useEvidenceImage.js", component: "src/components/EvidencePhoto/EvidencePhoto.jsx" };
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
        if (node.type === "VariableDeclarator" && node.id?.name === name) found = node.init;
        else if (node.type === "FunctionDeclaration" && node.id?.name === name) found = node;
        else for (const value of Object.values(node)) {
            if (Array.isArray(value)) value.forEach(visit);
            else if (value?.type) visit(value);
        }
    };
    visit(source(file).tree); assert.ok(found, name);
    return found;
}
function evaluate(ctx, file, node) {
    const { text } = source(file);
    return new vm.Script(`(${text.slice(node.start, node.end)})`).runInContext(ctx);
}
function callback(ctx, file, name) {
    const node = find(file, name);
    return evaluate(ctx, file, node.type === "CallExpression" ? node.arguments[0] : node);
}
function effect(ctx, file, name) {
    const fn = find(file, name);
    const node = fn.body.body.find(node => node.type === "ExpressionStatement" && node.expression.callee?.name === "useEffect");
    return evaluate(ctx, file, node.expression.arguments[0])();
}
function returned(ctx, file, name) {
    return evaluate(ctx, file, find(file, name).body.body.find(node => node.type === "ReturnStatement").argument);
}
function state(initial, extra) {
    const ctx = { ...initial, AbortController, ...extra };
    for (const name of Object.keys(initial)) ctx[`set${name[0].toUpperCase()}${name.slice(1)}`] = next => {
        ctx[name] = typeof next === "function" ? next(ctx[name]) : next;
    };
    return vm.createContext(ctx);
}
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const turn = () => new Promise(resolve => setImmediate(resolve));
const payload = id => ({ tasks: [{ id }], attendance: [], leave: [], shifts: [], availability: [] });
const fixed = Date.parse("2026-11-12T03:00:00Z");
class Clock extends Date { constructor(...args) { super(...(args.length ? args : [fixed])); } static now() { return fixed; } }
function calendarContext(service) {
    return state({ data: null, todayData: null, loading: false, refreshing: false, loadedRange: "", updatedAt: null, error: "", todayError: "" }, {
        Date: Clock, range: ["2026-11-01", "2026-11-30"], rangeKey: "november:7", todayKey: "2026-11-12", employeeId: "7", configReady: true, canManage: true,
        requestSequenceRef: { current: 0 }, calendarRequestRef: { current: null }, validateStaffCalendarPayload,
        workforceService: { getCalendar: service },
    });
}
test("staff calendar scopes requests to the selected employee and reuses overlapping refreshes", async () => {
    const gate = deferred(), calls = [];
    const ctx = calendarContext(async (...args) => { calls.push(args); return gate.promise; });
    const load = callback(ctx, files.calendar, "loadCalendar"), one = load(), two = load({ background: true });
    assert.equal(calls.length, 1); assert.equal(calls[0][2], "7"); assert.ok(calls[0][3].signal);
    gate.resolve(payload(7)); await Promise.all([one, two]);
    assert.equal(ctx.data.tasks[0].id, 7); assert.equal(ctx.todayData.employeeId, "7"); assert.equal(ctx.calendarRequestRef.current, null);
});
test("staff calendar cancels an abandoned employee and ignores its late response", async () => {
    const gate = deferred(), calls = [];
    const ctx = calendarContext(async (...args) => { calls.push(args); return args[2] === "7" ? gate.promise : payload(8); });
    const load = callback(ctx, files.calendar, "loadCalendar"), old = load();
    ctx.employeeId = "8"; ctx.rangeKey = "november:8"; await load();
    assert.equal(calls[0][3].signal.aborted, true); gate.resolve(payload(7)); await old;
    assert.equal(ctx.todayData.employeeId, "8"); assert.equal(ctx.data.tasks[0].id, 8); assert.equal(ctx.loading, false);
});
test("an off-month calendar failure does not discard today's successful attendance", async () => {
    const calls = [];
    const ctx = calendarContext(async (...args) => { calls.push(args); if (args[0] === "2026-10-01") throw new Error("month unavailable"); return payload(7); });
    ctx.range = ["2026-10-01", "2026-10-31"]; ctx.rangeKey = "october:7";
    await callback(ctx, files.calendar, "loadCalendar")();
    assert.equal(calls.length, 2); assert.ok(calls.every(row => row[2] === "7"));
    assert.equal(ctx.error, "month unavailable"); assert.equal(ctx.todayError, ""); assert.equal(ctx.todayData.data.tasks.length, 1);
});
function metadataContext() {
    const calls = [];
    const ctx = vm.createContext({ Date: Clock, farmDateKey, actionBusyRef: { current: false }, farmTimezone: "Asia/Manila", todayKey: "2026-11-12",
        configReady: true, configError: "", employeesReady: true, employeesError: "",
        metadataRef: { current: { configAt: fixed, employeesAt: fixed, employeeRevision: 0, loadedEmployeeRevision: 0 } },
        loadConfig: async () => calls.push("config"), loadEmployees: async () => calls.push("employees"), loadCalendar: async () => calls.push("calendar"),
    });
    return { ctx, calls, refresh: callback(ctx, files.calendar, "refreshCalendar") };
}
test("routine calendar refresh does not reload fresh employee and configuration data", async () => {
    const { ctx, calls, refresh } = metadataContext(); await refresh();
    assert.deepEqual(calls, ["calendar"]); calls.length = 0;
    ctx.metadataRef.current.employeeRevision++; await refresh();
    assert.deepEqual(calls.sort(), ["calendar", "employees"]);
});
test("metadata refreshes after five minutes, date rollover or a failed load", async () => {
    const { ctx, calls, refresh } = metadataContext();
    ctx.metadataRef.current.configAt -= 300001; ctx.metadataRef.current.employeesAt -= 300001; await refresh();
    assert.deepEqual(calls.sort(), ["calendar", "config", "employees"]); calls.length = 0;
    ctx.metadataRef.current.configAt = fixed; ctx.metadataRef.current.employeesAt = fixed;
    ctx.todayKey = "2026-11-11"; await refresh(); assert.ok(calls.includes("config")); calls.length = 0;
    ctx.todayKey = "2026-11-12"; ctx.employeesError = "offline"; await refresh(); assert.ok(calls.includes("employees")); calls.length = 0;
    ctx.actionBusyRef.current = true; await refresh(); assert.equal(calls.length, 0);
});
test("evidence paths select thumbnails without accepting external or traversal URLs", () => {
    assert.deepEqual(evidencePaths("/workforce/evidence-assets/abc-123"), { original: "/workforce/evidence-assets/abc-123", thumbnail: "/workforce/evidence-assets/abc-123/thumbnail" });
    assert.equal(evidencePaths("/workforce/evidence-assets/abc-123/thumbnail").original, "/workforce/evidence-assets/abc-123");
    assert.deepEqual(evidencePaths("/workforce/evidence/legacy.png"), { original: "/workforce/evidence/legacy.png", thumbnail: null });
    for (const path of ["https://example.org/photo.jpg", "data:image/png,test", "/workforce/evidence-assets/id?redirect=1", "/workforce/evidence/..", "/workforce/evidence/%2fetc", "/workforce/evidence/%5csecret", "/workforce/evidence/%00.png", "/workforce/evidence/%zz"]) assert.equal(evidencePaths(path), null, path);
});
function imageContext(service, enabled = true) {
    const created = [], revoked = [];
    const ctx = state({ image: { path: "", url: "", error: "", loading: false }, attempt: 0 }, {
        requestRef: { current: null }, evidenceUrl: "/workforce/evidence-assets/abc/thumbnail", enabled,
        workforceService: { downloadEvidencePhoto: service }, URL: { createObjectURL: blob => { created.push(blob); return `blob:${created.length}`; }, revokeObjectURL: url => revoked.push(url) },
    });
    return { ctx, created, revoked };
}
test("disabled evidence requests do not download originals or previews", async () => {
    let calls = 0;
    const { ctx } = imageContext(async () => { calls++; }, false);
    effect(ctx, files.image, "useEvidenceImage"); await turn(); assert.equal(calls, 0);
    ctx.enabled = true; ctx.evidenceUrl = null; effect(ctx, files.image, "useEvidenceImage"); assert.equal(calls, 0);
});
test("evidence download cancellation ignores late blobs and frees successful object URLs", async () => {
    const gate = deferred(), calls = [];
    const { ctx, created, revoked } = imageContext(async (...args) => { calls.push(args); return gate.promise; });
    const cleanup = effect(ctx, files.image, "useEvidenceImage"); cleanup();
    assert.equal(calls[0][1].signal.aborted, true); assert.equal(calls[0][1].cache, "no-store");
    gate.resolve(new Blob(["synthetic"])); await turn(); assert.equal(created.length, 0);
    ctx.workforceService.downloadEvidencePhoto = async () => new Blob(["synthetic"]);
    const close = effect(ctx, files.image, "useEvidenceImage"); await turn();
    ctx.matching = callback(ctx, files.image, "matching"); assert.equal(returned(ctx, files.image, "useEvidenceImage").url, "blob:1");
    close(); assert.deepEqual(revoked, ["blob:1"]);
    ctx.matching = callback(ctx, files.image, "matching"); const reopened = returned(ctx, files.image, "useEvidenceImage");
    assert.equal(reopened.url, ""); assert.equal(reopened.loading, true);
});
test("image failures finish loading and expose a retry", async () => {
    const { ctx } = imageContext(async () => { throw new Error("permission denied"); });
    const cleanup = effect(ctx, files.image, "useEvidenceImage"); await turn();
    ctx.matching = callback(ctx, files.image, "matching"); const result = returned(ctx, files.image, "useEvidenceImage");
    assert.equal(result.error, "permission denied"); assert.equal(result.loading, false); result.retry(); assert.equal(ctx.attempt, 1); cleanup();
});
test("visibility observation postpones preview loading and disconnects on cleanup", () => {
    let notify, observed = 0, disconnected = 0;
    const ctx = state({ visibleIdentity: "old" }, { target: { current: {} }, identity: "new",
        IntersectionObserver: class { constructor(callback, options) { notify = callback; assert.equal(options.rootMargin, "200px"); } observe() { observed++; } disconnect() { disconnected++; } },
    });
    const cleanup = effect(ctx, files.image, "useNearViewport"); assert.equal(observed, 1); assert.equal(ctx.visibleIdentity, "");
    notify([{ isIntersecting: false }]); assert.equal(ctx.visibleIdentity, "");
    notify([{ isIntersecting: true }]); assert.equal(ctx.visibleIdentity, "new"); cleanup();
    ctx.visibleIdentity = "later"; notify([{ isIntersecting: true }]); assert.equal(ctx.visibleIdentity, "later"); assert.ok(disconnected >= 1);
});
test("inline component enables the original request only after opening that evidence", () => {
    function requests(openEvidence, path = "/workforce/evidence-assets/abc") {
        const calls = []; let states = 0;
        const ctx = vm.createContext({ evidenceUrl: path, evidencePaths, useRef: () => ({ current: null }), useNearViewport: () => true,
            useState: () => [states++ === 0 ? openEvidence : "", () => {}], useEvidenceImage: (url, enabled) => { calls.push({ url, enabled }); return {}; },
        });
        const fn = find(files.component, "EvidenceInlinePreview"), end = fn.body.body.find(node => node.type === "ReturnStatement").start;
        const text = source(files.component).text;
        new vm.Script(`(() => {${text.slice(fn.body.start + 1, end)}})()`).runInContext(ctx);
        return calls;
    }
    assert.deepEqual(requests("").map(row => row.enabled), [true, false]);
    assert.deepEqual(requests("/workforce/evidence-assets/abc").map(row => row.enabled), [true, true]);
    assert.equal(requests("", "/workforce/evidence/legacy.png")[0].url, null);
});
