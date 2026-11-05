import { eventNeedsResource } from '../src/components/DashboardCalendar/eventFormHelpers.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { WORK_TYPES, WORK_TYPE_GROUPS, eventDomain, eventRecordChoices, taskCategoryUpdate, workTypeLabel } from '../src/services/eventPlanning.js';

test('shared creation choices use existing crop, livestock and inventory domains', () => {
    assert.equal(new Set(WORK_TYPES).size, WORK_TYPES.length);
    assert.equal(WORK_TYPES.includes('Equipment Maintenance'), false);
    for (const group of WORK_TYPE_GROUPS) for (const category of group.types) assert.equal(eventDomain(category), group.module);
    assert.equal(eventDomain('Weight Monitoring'), 'Livestock');
    assert.equal(eventDomain('Crop Growth Monitoring'), 'Crop');
    assert.equal(workTypeLabel('Irrigation'), 'Watering / Irrigation');
});

test('changing the work type clears stale consumption and switches record domains', () => {
    const initial = { source_module: 'Crop', source_record_id: '1', planned_inventory_item_id: '7', planned_quantity: '2', planned_unit: 'kg', planned_usage_type: 'Fertilizer', feeding_slot: 'Morning' };
    const weight = taskCategoryUpdate(initial, 'Weight Monitoring');
    assert.equal(weight.source_module, 'Livestock');
    assert.equal(weight.source_record_id, '');
    assert.equal(weight.planned_inventory_item_id, '');
    assert.equal(weight.planned_quantity, '');
    assert.equal(weight.feeding_slot, '');
    assert.equal(taskCategoryUpdate(initial, 'Crop Growth Monitoring').source_record_id, '1');
    const restock = taskCategoryUpdate(initial, 'Inventory Restocking');
    assert.equal(restock.source_module, 'Inventory');
    assert.equal(restock.source_type, 'inventory_restock_plan');
    assert.equal(restock.source_record_id, '');
    assert.equal(taskCategoryUpdate(restock, 'Farm Inspection').source_module, '');
});

test('monitoring uses only records from its own farm module', () => {
    const resources = { crops: [{ id: 1 }], livestock: [{ id: 2 }], inventory: [{ id: 3 }] };
    assert.deepEqual(eventRecordChoices({ type: 'Weight Monitoring' }, resources), resources.livestock);
    assert.deepEqual(eventRecordChoices({ type: 'Crop Growth Monitoring' }, resources), resources.crops);
});


test('monitoring remains an observation when its title mentions feeding or fertilizer', () => {
    assert.equal(eventNeedsResource({ assignedEmployeeId: 42, type: 'Weight Monitoring', title: 'Weigh animals after feeding' }), false);
    assert.equal(eventNeedsResource({ assignedEmployeeId: 42, type: 'Crop Growth Monitoring', title: 'Inspect growth after fertilizer application' }), false);
});
