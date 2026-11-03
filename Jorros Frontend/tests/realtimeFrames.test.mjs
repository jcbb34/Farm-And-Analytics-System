import assert from "node:assert/strict";
import test from "node:test";
import { parseEventFrames } from "../src/services/eventFrames.js";
import { buildMyTasksPageQuery } from "../src/views/MyTasks/taskPageQuery.js";

test("split event frames and heartbeats retain authorized event IDs", () => {
    const events = [];
    let buffer = "";
    for (const chunk of [": heartbeat\n\nid: 8\nevent: change\ndata: {\"modules\":", "[\"tasks\"]}\n\nid: 9\nevent: change\ndata: {}\n\n"]) {
        buffer = parseEventFrames(buffer + chunk, (event) => events.push(event));
    }
    assert.equal(buffer, "");
    assert.deepEqual(events.map((event) => event.id), ["8", "9"]);
});

test("completed history filters remain server-side and date keys use farm dates", () => {
    const query = buildMyTasksPageQuery({ view: "completed", scope: "all", taskView: "completed",
        search: "  Feed plot  ", priorityFilter: "High", scheduleFilter: "all",
        selectedTaskDate: null, todayKey: "2026-09-30", upcomingLimitKey: "2026-10-07", sharedDevice: false });
    assert.equal(query.search, "Feed plot");
    assert.equal(query.priority, "High");
    assert.equal(query.limit, 25);
    const next = buildMyTasksPageQuery({ ...query, search: "", priorityFilter: "all",
        scheduleFilter: "upcoming", todayKey: "2026-09-30", upcomingLimitKey: "2026-10-07" });
    assert.equal(next.date_from, "2026-10-01");
});
