import assert from 'node:assert/strict';
import test from 'node:test';
import { farmLocationService } from '../src/services/farmLocationService.js';
import { invalidateReadCache } from '../src/services/httpClient.js';
import { eventDomain, eventRecordChoices, eventRecordLocation } from '../src/services/eventPlanning.js';
import { eventNeedsResource } from '../src/components/DashboardCalendar/eventFormHelpers.js';
const original = Object.fromEntries(['window', 'fetch', 'localStorage', 'sessionStorage'].map((key) => [key, globalThis[key]]));
test.beforeEach(() => {
    invalidateReadCache();
    globalThis.window = { location: { origin: 'http://farm.test:3000' }, setTimeout, clearTimeout };
    globalThis.localStorage = { getItem: () => JSON.stringify({ accessToken: 'synthetic-event-location-token' }) };
    globalThis.sessionStorage = { getItem: () => null };
});
test.after(() => Object.assign(globalThis, original));

test('an empty crop location lookup falls back to actual fields without requesting warehouses', async () => {
    const calls = [];
    globalThis.fetch = async (url) => {
        const path = new URL(url).pathname; calls.push(path);
        return Response.json(path.endsWith('/farm-locations') ? { items: [] } : [
            { id: 1, field: ' Field A ', is_archived: false }, { id: 2, field: 'Field B' }, { id: 3, field: 'Old field', is_archived: true },
        ]);
    };
    assert.deepEqual(await farmLocationService.getChoices('crops'), ['Field A', 'Field B']);
    assert.deepEqual(calls, ['/api/v1/farm-locations', '/api/v1/crops']);
});
test('a missing location route uses inventory storage records and never crop fields', async () => {
    const calls = [];
    globalThis.fetch = async (url) => {
        const path = new URL(url).pathname; calls.push(path);
        return path.endsWith('/farm-locations') ? Response.json({ detail: 'Not found' }, { status: 404 }) : Response.json([
            { id: 1, location: 'Warehouse A' }, { id: 2, location: 'Feed Room' }, { id: 3, location: 'Hidden store', is_archived: true },
        ]);
    };
    assert.deepEqual(await farmLocationService.getChoices('inventory'), ['Feed Room', 'Warehouse A']);
    assert.deepEqual(calls, ['/api/v1/farm-locations', '/api/v1/inventory']);
});
test('an older mixed event lookup is ignored for restocking and uses only the selected item warehouse', async () => {
    globalThis.fetch = async (url) => Response.json(new URL(url).pathname.endsWith('/farm-locations')
        ? { items: ['Field A', 'Pen A', 'Wrong warehouse'] }
        : [{ id: 1, name: 'Feed', location: 'Feed Room' }, { id: 2, name: 'Vaccine', location: 'Cold store' }]);
    assert.deepEqual(await farmLocationService.getChoices('events', undefined, { eventType: 'Inventory Restocking', sourceModule: 'Inventory', sourceRecordId: 2 }), ['Cold store']);
});
test('equipment events offer equipment storage rather than fields or consumable supplies', async () => {
    globalThis.fetch = async (url) => Response.json(new URL(url).pathname.endsWith('/farm-locations') ? { items: [] } : [
        { id: 1, name: 'Tractor', category: 'Equipment', location: 'Equipment shed' },
        { id: 2, name: 'Feed', category: 'Livestock Feed', location: 'Feed Room' },
    ]);
    assert.deepEqual(await farmLocationService.getChoices('events', undefined, { eventType: 'Equipment Maintenance', sourceModule: 'Inventory' }), ['Equipment shed']);
});
test('event type defines record choices and prevents stock consumption during restock or maintenance', () => {
    const resources = { crops: [{ id: 1, name: 'Corn', field: 'Field A' }], livestock: [{ id: 2, name: 'Pigs', location: 'Pen A' }], inventory: [
        { id: 3, name: 'Grower Feed', category: 'Livestock Feed', location: 'Feed Room' }, { id: 4, name: 'Feed dispenser', category: 'Equipment', location: 'Equipment shed' },
    ] };
    assert.equal(eventDomain('Fertilization'), 'Crop'); assert.equal(eventDomain('Vaccination'), 'Livestock');
    assert.deepEqual(eventRecordChoices({ type: 'Inventory Restocking' }, resources).map((row) => row.id), [3, 4]);
    assert.deepEqual(eventRecordChoices({ type: 'Equipment Maintenance' }, resources).map((row) => row.id), [4]);
    assert.equal(eventRecordLocation(resources.crops[0], 'Crop'), 'Field A');
    for (const type of ['Inventory Restocking', 'Equipment Maintenance']) assert.equal(eventNeedsResource({ type, title: 'Grower feed', assignedEmployeeId: 1 }), false);
});
