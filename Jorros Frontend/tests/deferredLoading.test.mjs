import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import { createRequire } from "node:module";
import { observeWhenVisible } from "../src/utils/observeWhenVisible.js";

function controlledObserver() {
    const state = { callbacks: [], disconnected: 0, observed: [] };
    class Observer {
        constructor(callback, options) { state.callbacks.push(callback); state.options = options; }
        observe(element) { state.observed.push(element); }
        disconnect() { state.disconnected++; }
    }
    return { state, Observer };
}

test("offscreen analytics waits until it is near the viewport and reveals once", () => {
    const { state, Observer } = controlledObserver();
    let reveals = 0;
    const element = {};
    const stop = observeWhenVisible(element, () => reveals++, Observer);
    assert.equal(reveals, 0);
    assert.equal(state.options.rootMargin, "200px 0px");
    assert.deepEqual(state.observed, [element]);
    state.callbacks[0]([{ isIntersecting: false }]);
    assert.equal(reveals, 0);
    state.callbacks[0]([{ isIntersecting: true }]);
    state.callbacks[0]([{ isIntersecting: true }]);
    assert.equal(reveals, 1);
    assert.equal(state.disconnected, 1);
    stop();
});

test("unmounted analytics cannot be revealed by a delayed observer callback", () => {
    const { state, Observer } = controlledObserver();
    let reveals = 0;
    const stop = observeWhenVisible({}, () => reveals++, Observer);
    stop();
    state.callbacks[0]([{ isIntersecting: true }]);
    assert.equal(reveals, 0);
    assert.equal(state.disconnected, 1);
});

test("analytics remains available without IntersectionObserver support", () => {
    let reveals = 0;
    observeWhenVisible({}, () => reveals++, null)();
    assert.equal(reveals, 1);
});

test("analytics remains available if observer construction or observation fails", () => {
    let reveals = 0;
    class BrokenConstructor { constructor() { throw new Error("unsupported"); } }
    class BrokenObserve { observe() { throw new Error("unsupported"); } disconnect() {} }
    observeWhenVisible({}, () => reveals++, BrokenConstructor)();
    observeWhenVisible({}, () => reveals++, BrokenObserve)();
    assert.equal(reveals, 2);
});

test("the notification bell pauses hidden-tab reads and refreshes after visibility returns", async () => {
    // Execute the actual UI callback with a controlled API, not a copy of it.
    const require = createRequire(import.meta.url);
    const parser = require("next/dist/compiled/babel/parser");
    const text = fs.readFileSync(new URL("../src/context/AppHeaderContext.jsx", import.meta.url), "utf8");
    const tree = parser.parse(text, { sourceType: "module", plugins: ["jsx"] });
    let expression;
    function visit(node) {
        if (!node || typeof node !== "object" || expression) return;
        if (node.type === "VariableDeclarator" && node.id?.name === "refreshAlertNotifications") expression = node.init.arguments[0];
        else for (const value of Object.values(node)) {
            if (Array.isArray(value)) value.forEach(visit);
            else if (value?.type) visit(value);
        }
    }
    visit(tree);
    assert.ok(expression);
    let requests = 0, displayed;
    const document = { visibilityState: "hidden" };
    const context = vm.createContext({
        document, console, isPublicAuthRoute: false, isAuthLoading: false, isAuthenticated: true,
        hasPermission: () => true, alertLoadRunningRef: { current: false },
        knownTriggerIdsRef: { current: new Set() }, firstAlertLoadRef: { current: true },
        alertService: { getNotificationPreview: async () => { requests++; return []; } },
        setNotifications: value => { displayed = value; }, readNotificationSettings: () => ({}),
        makeAlertNotificationId: row => row.id,
    });
    const refresh = new vm.Script(`(${text.slice(expression.start, expression.end)})`).runInContext(context);
    await refresh(); await refresh();
    assert.equal(requests, 0);
    assert.equal(context.firstAlertLoadRef.current, true);
    document.visibilityState = "visible";
    await refresh();
    assert.equal(requests, 1);
    assert.equal(displayed.length, 0);
    assert.equal(context.alertLoadRunningRef.current, false);
});
