import assert from "node:assert/strict";
import test from "node:test";

import { httpClient, invalidateReadCache } from "../src/services/httpClient.js";

const sessionKey = "joross-auth-session-v1";

function memoryStorage() {
    const entries = new Map();
    return {
        getItem: (key) => entries.get(key) ?? null,
        setItem: (key, value) => entries.set(key, String(value)),
        removeItem: (key) => entries.delete(key),
    };
}

function loggedIn(storage, token) {
    storage.setItem(sessionKey, JSON.stringify({ accessToken: token }));
}

const originalGlobals = {
    window: globalThis.window,
    sessionStorage: globalThis.sessionStorage,
    localStorage: globalThis.localStorage,
    fetch: globalThis.fetch,
    CustomEvent: globalThis.CustomEvent,
};

test.beforeEach(() => {
    invalidateReadCache();
    const events = [];
    globalThis.window = {
        location: { origin: "http://localhost:3000" },
        setTimeout,
        clearTimeout,
        dispatchEvent: (event) => events.push(event),
        events,
    };
    globalThis.sessionStorage = memoryStorage();
    globalThis.localStorage = memoryStorage();
    globalThis.CustomEvent = class {
        constructor(type, options) {
            this.type = type;
            this.detail = options.detail;
        }
    };
});

test("simultaneous reads share one fetch and writes invalidate cached results", async () => {
    loggedIn(sessionStorage, "one-token");
    let reads = 0;
    globalThis.fetch = async (_url, options) => {
        if (options.method === "GET") { reads += 1; return Response.json({ reads }); }
        return Response.json({ saved: true });
    };
    const [first, second] = await Promise.all([httpClient.get("/crops"), httpClient.get("/crops")]);
    assert.deepEqual(first, second);
    assert.equal(reads, 1);
    assert.deepEqual(await httpClient.get("/crops"), first);
    assert.equal(reads, 1);
    await httpClient.post("/crops", { name: "New" });
    assert.deepEqual(await httpClient.get("/crops"), { reads: 2 });
});

test("private reads never reuse another user's cache entry", async () => {
    let requests = 0;
    globalThis.fetch = async (_url, options) => {
        requests += 1;
        return Response.json({ owner: options.headers.Authorization });
    };
    loggedIn(sessionStorage, "user-one");
    assert.deepEqual(await httpClient.get("/workforce/my-tasks"), { owner: "Bearer user-one" });
    loggedIn(sessionStorage, "user-two");
    assert.deepEqual(await httpClient.get("/workforce/my-tasks"), { owner: "Bearer user-two" });
    assert.equal(requests, 2);
});

test.after(() => {
    Object.assign(globalThis, originalGlobals);
});

test("an old 401 cannot log out a user who signed in while the request was in flight", async () => {
    loggedIn(sessionStorage, "old-token");
    globalThis.fetch = async (_url, options) => {
        assert.equal(options.headers.Authorization, "Bearer old-token");
        loggedIn(sessionStorage, "new-token");
        return Response.json({ detail: "Unauthorized" }, { status: 401 });
    };

    await assert.rejects(httpClient.get("/alerts"), { status: 401 });
    assert.equal(JSON.parse(sessionStorage.getItem(sessionKey)).accessToken, "new-token");
    assert.equal(window.events.length, 0);
});

test("a 401 still clears the session whose own token failed", async () => {
    loggedIn(sessionStorage, "invalid-token");
    globalThis.fetch = async () => Response.json({ detail: "Unauthorized" }, { status: 401 });

    await assert.rejects(httpClient.get("/alerts"), { status: 401 });
    assert.equal(sessionStorage.getItem(sessionKey), null);
    assert.equal(window.events[0]?.type, "joross:auth-changed");
});

test("persistent credentials are never used when temporary storage is damaged", async () => {
    sessionStorage.setItem(sessionKey, "{invalid-json");
    loggedIn(localStorage, "old-persistent-token");
    globalThis.fetch = async (_url, options) => {
        assert.equal(options.headers.Authorization, undefined);
        return Response.json({ ok: true });
    };
    assert.deepEqual(await httpClient.get("/alerts"), { ok: true });
});
