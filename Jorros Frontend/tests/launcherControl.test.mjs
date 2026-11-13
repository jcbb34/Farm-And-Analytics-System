import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { EventEmitter } from "node:events";
import vm from "node:vm";

const code = readFileSync(new URL("../scripts/serve-farm.cjs", import.meta.url), "utf8");

function runner({ controlled = true, ready = true } = {}) {
    const process = new EventEmitter();
    process.env = controlled ? { JOROSS_LAUNCHER_CONTROL: "1" } : {};
    process.stdin = new EventEmitter();
    process.stdin.setEncoding = () => {};
    let stops = 0;
    let received;
    const timers = [];
    const nextCleanup = (value) => { stops++; received = value; };
    if (ready) process.on("SIGTERM", nextCleanup);
    vm.runInNewContext(code, {
        process,
        require: (name) => assert.equal(name, "next/dist/bin/next"),
        setTimeout: (fn) => { timers.push(fn); return timers.length; },
        clearTimeout: () => {},
    });
    return { process, timers, nextCleanup, get stops() { return stops; },
        get received() { return received; } };
}

test("a split stop command reaches Next cleanup exactly once", () => {
    const state = runner();
    state.process.stdin.emit("data", "st");
    assert.equal(state.stops, 0);
    state.process.stdin.emit("data", "op\r\nstop\n");
    state.process.stdin.emit("end");
    assert.equal(state.stops, 1);
    assert.equal(state.received, "SIGTERM");
});

test("launcher pipe closure stops the frontend", () => {
    const state = runner();
    state.process.stdin.emit("end");
    assert.equal(state.stops, 1);
});

test("an early stop waits for Next's cleanup handler", () => {
    const state = runner({ ready: false });
    state.process.stdin.emit("data", "stop\n");
    assert.equal(state.stops, 0);
    assert.equal(state.timers.length, 1);
    state.process.on("SIGTERM", state.nextCleanup);
    state.timers.shift()();
    assert.equal(state.stops, 1);
});

test("Windows break uses the same one-time graceful cleanup", () => {
    const state = runner();
    state.process.emit("SIGBREAK");
    state.process.emit("SIGBREAK");
    assert.equal(state.stops, 1);
});

test("uncontrolled runs do not treat ordinary stdin as management commands", () => {
    const state = runner({ controlled: false });
    state.process.stdin.emit("data", "stop\n");
    state.process.stdin.emit("end");
    assert.equal(state.stops, 0);
});

test("unrecognized commands do not stop the frontend", () => {
    const state = runner();
    state.process.stdin.emit("data", "drain\nhello\n");
    assert.equal(state.stops, 0);
});
