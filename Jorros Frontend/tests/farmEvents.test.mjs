import test from "node:test";
import assert from "node:assert/strict";
import { eventTouchesDate, eventForm, eventCreatePath, eventLocalTime } from "../src/components/FarmEvents/eventView.js";
import { weatherSignals, weatherFarmTip } from "../src/services/weatherPolicy.js";
import { canWorkTaskForView, isMissedTaskForView } from "../src/views/MyTasks/taskView.js";

test("event windows use farm dates and exclude the midnight ending date", () => {
    const event = { starts_at: "2026-11-01T16:00:00Z", ends_at: "2026-11-02T16:00:00Z" };
    assert.equal(eventLocalTime(event.starts_at), "2026-11-02T00:00");
    assert.equal(eventTouchesDate(event, "2026-11-01"), false);
    assert.equal(eventTouchesDate(event, "2026-11-02"), true);
    assert.equal(eventTouchesDate(event, "2026-11-03"), false);
});
test("emergencies continue beyond expected end until explicitly reopened", () => {
    const event = { starts_at: "2026-11-02T08:00:00+08:00", ends_at: "2026-11-02T12:00:00+08:00", requires_reopening: true };
    assert.equal(eventTouchesDate(event, "2026-11-10"), true);
    assert.equal(eventTouchesDate({ ...event, ended_at: "2026-11-03T15:00:00+08:00" }, "2026-11-04"), false);
});
test("declaration links encode source data and new forms retain farm-local times", () => {
    const path = eventCreatePath({ kind: "Emergency Suspension", source: "LGU & PAGASA", reason: "Rain / flooding?" });
    assert.equal(new URL(path, "http://test").searchParams.get("source"), "LGU & PAGASA");
    const form = eventForm({ starts_at: "2026-11-02T00:00:00Z", scope_values: [1, 2] }, "2026-11-02");
    assert.equal(form.starts_at, "2026-11-02T08:00"); assert.deepEqual(form.scope_values, ["1", "2"]);
});
test("held tasks cannot be worked or labelled missed but keep their original status", () => {
    const task = { status: "Pending", activity_date: "2026-11-01", work_suspended: true };
    assert.equal(canWorkTaskForView(task, "2026-11-02"), false);
    assert.equal(isMissedTaskForView(task, "2026-11-02"), false);
    assert.equal(task.status, "Pending");
    assert.equal(canWorkTaskForView({ ...task, work_suspended: false }, "2026-11-02"), true);
});
const weather = { dataStatus: "Fresh", forecast: [{}], current: { temperatureC: 33, windSpeedKph: 10, windGustKph: 65 }, next24Hours: { rainTotalMm: 60, maxTemperatureC: 33, maxWindSpeedKph: 20 } };
test("farm tips and counts share configured thresholds, disabled alerts and gusts", () => {
    const settings = { temperatureThreshold: 35, rainfallThreshold: 50, windSpeedThreshold: 60 };
    assert.deepEqual(weatherSignals(weather, settings), ["Heavy rainfall", "Strong wind or gusts"]);
    assert.match(weatherFarmTip(weather, settings), /Heavy rainfall; Strong wind or gusts/);
    assert.deepEqual(weatherSignals(weather, { ...settings, heavyRainAlert: false, strongWindAlert: false }), []);
});
test("unavailable, stale and missing forecasts never claim normal conditions", () => {
    assert.deepEqual(weatherSignals({ ...weather, dataStatus: "Stale" }), []);
    assert.match(weatherFarmTip({ ...weather, dataStatus: "Stale" }), /could not be verified/);
    assert.match(weatherFarmTip(null), /could not be verified/);
    assert.match(weatherFarmTip({ dataStatus: "Fresh", current: {}, next24Hours: {} }), /Future conditions are unknown/);
});
