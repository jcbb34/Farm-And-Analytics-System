import test from 'node:test';
import assert from 'node:assert/strict';
import { harvestCropOptionLabel, harvestCropRecordCode, harvestSectionLabel, harvestYieldPerHectare } from '../src/components/CropActionModals/harvestCropIdentity.mjs';

test('two Coconut Tall crops in separate sections are distinct harvest choices', () => {
  const a1 = { id:1, name:'Coconut', variety:'Tall', field:'Field A — Coconut Plantation', sectionName:'Section A1', cropCode:'CROP-001' };
  const a2 = { ...a1, id:2, sectionName:'Section A2', cropCode:'CROP-002' };
  assert.equal(harvestCropOptionLabel(a1), 'Coconut (Tall) — Field A / Section A1 — CROP-001');
  assert.equal(harvestCropOptionLabel(a2), 'Coconut (Tall) — Field A / Section A2 — CROP-002');
  assert.notEqual(harvestCropOptionLabel(a1), harvestCropOptionLabel(a2));
});

test('section name from backend snake_case is shown', () => {
  assert.equal(harvestSectionLabel({ section_name:'Section B2' }), 'Section B2');
  assert.equal(harvestCropOptionLabel({id:4, name:'Banana', variety:'Saba', field:'Field B — Banana Plantation', section_name:'Section B2'}),
    'Banana (Saba) — Field B / Section B2 — Record #4');
});

test('missing section name shows identifier, never invents physical section', () => {
  assert.equal(harvestSectionLabel({section_id:19}), 'Section ID 19');
  assert.equal(harvestSectionLabel({}), 'No section assigned');
  assert.equal(harvestCropRecordCode({id:5}), 'Record #5');
});

test('valid yield per hectare is calculated only from a valid measured area', () => {
  assert.equal(harvestYieldPerHectare('10','0.5'), 20);
  assert.equal(harvestYieldPerHectare('10', null), null);
  assert.equal(harvestYieldPerHectare('10', 0), null);
  assert.equal(harvestYieldPerHectare('10', ''), null);
  assert.equal(harvestYieldPerHectare('10', 'unknown'), null);
  assert.equal(harvestYieldPerHectare('', 2), null);
  assert.equal(harvestYieldPerHectare('0', 2), null);
});
