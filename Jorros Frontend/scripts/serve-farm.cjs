"use strict";

// Run the installed Next CLI directly. npm.cmd adds a Windows batch process
// which prompts "Terminate batch job?" and receives Ctrl+C out of order.
// The launcher owns stdin and uses it to request Next's normal cleanup.
let stopRequested = false;
let stopTimer;

function requestStop() {
    if (stopRequested) return;
    stopRequested = true;
    const stopWhenReady = () => {
        if (process.listenerCount("SIGTERM")) {
            process.emit("SIGTERM", "SIGTERM");
        } else {
            // Next may still be loading its CLI/config when Ctrl+C is pressed.
            // Wait briefly for its own cleanup handler instead of abandoning a
            // startup that might later open the port.
            stopTimer = setTimeout(stopWhenReady, 25);
        }
    };
    stopWhenReady();
}

process.on("SIGBREAK", requestStop);
if (process.env.JOROSS_LAUNCHER_CONTROL === "1") {
    process.stdin.setEncoding("utf8");
    let pending = "";
    process.stdin.on("data", (chunk) => {
        pending += chunk;
        let end;
        while ((end = pending.indexOf("\n")) !== -1) {
            const command = pending.slice(0, end).trim();
            pending = pending.slice(end + 1);
            if (command === "stop") requestStop();
        }
    });
    process.stdin.on("end", requestStop);
}
process.on("exit", () => clearTimeout(stopTimer));

require("next/dist/bin/next");
