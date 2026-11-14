import test from 'node:test';
import assert from 'node:assert/strict';
import { readFarmPlanDraft, collectFarmPlanUpdates, previewFarmPlan, canArchiveFarmZone } from '../src/views/FarmPlan/farmPlanDraft.js';
const zones = [
    { code:'A',parent_code:null,kind:'field',name:'Coconut',proposed_area_m2:9500,measured_area_m2:null,edit_version:2 },
    { code:'A1',parent_code:'A',kind:'section',name:'Section A1',proposed_area_m2:9500,measured_area_m2:null,edit_version:2 },
    { code:'FAC',parent_code:null,kind:'facility',name:'Facilities',proposed_area_m2:8500,measured_area_m2:null,edit_version:2 },
    { code:'L1',parent_code:'FAC',kind:'livestock',name:'Pigs',proposed_area_m2:900,measured_area_m2:null,edit_version:2,current_quantity:0 },
    { code:'R1',parent_code:'FAC',kind:'infrastructure',name:'Roads',proposed_area_m2:7600,measured_area_m2:null,edit_version:2 },
];
const plan = { zones, total_area_m2:18000, measured_crop_m2:0 };
test('initial farm plan has no changes and is valid', () => {
    const draft = readFarmPlanDraft(zones);
    assert.deepEqual(collectFarmPlanUpdates(zones, draft), []);
    const check = previewFarmPlan(plan, draft);
    assert.equal(check.remaining, 0);
    assert.deepEqual(check.errors, []);
});
test('editing a proposal does not convert it into a surveyed measurement', () => {
    const draft = readFarmPlanDraft(zones);
    draft.A.proposed_area_m2 = '9200';
    draft.A1.proposed_area_m2 = '9200';
    draft.FAC.proposed_area_m2 = '8800';
    draft.R1.proposed_area_m2 = '7900';
    const updates = collectFarmPlanUpdates(zones, draft);
    assert.equal(updates.length, 4);
    assert.ok(updates.every(u => !Object.hasOwn(u, 'measured_area_m2')));
    assert.deepEqual(previewFarmPlan(plan, draft).errors, []);
});
test('shows overallocated farm and section parent errors before save', () => {
    const draft = readFarmPlanDraft(zones);
    draft.A.proposed_area_m2 = '9900';
    draft.A1.proposed_area_m2 = '10100';
    const check = previewFarmPlan(plan, draft);
    assert.ok(check.errors.some(e => e.message.includes('exceeds the 18,000 m² farm')));
    assert.ok(check.errorByCode.A.includes('subdivisions'));
});
test('validation catches verified area exceeding physical parent', () => {
    const draft = readFarmPlanDraft(zones);
    draft.FAC.measured_area_m2 = '600';
    draft.L1.measured_area_m2 = '900';
    const check = previewFarmPlan(plan, draft);
    assert.ok(check.errorByCode.FAC.includes('verified'));
});
test('invalid non-positive verified area is identified', () => {
    const draft = readFarmPlanDraft(zones);
    draft.L1.measured_area_m2 = '0';
    assert.ok(previewFarmPlan(plan, draft).errorByCode.L1.includes('greater than 0'));
});
test('editing a verified facility changes only that measurement', () => {
    const draft = readFarmPlanDraft(zones);
    draft.L1.measured_area_m2 = '900';
    const updates = collectFarmPlanUpdates(zones, draft);
    assert.equal(updates.length, 1);
    assert.equal(updates[0].measured_area_m2, '900');
});
test('measured or occupied facilities are not offered archive action', () => {
    assert.equal(canArchiveFarmZone({ code:'L1',kind:'livestock',measured_area_m2:900 }).allowed, false);
    assert.equal(canArchiveFarmZone({ code:'L1',kind:'livestock',measured_area_m2:null,current_quantity:20 }).allowed, false);
    assert.equal(canArchiveFarmZone({ code:'L1',kind:'livestock',measured_area_m2:null,current_quantity:0 }).allowed, true);
    assert.equal(canArchiveFarmZone({ code:'R1',kind:'infrastructure',measured_area_m2:null }).allowed, false);
});
