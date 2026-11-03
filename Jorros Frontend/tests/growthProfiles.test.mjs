import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const modals = readFileSync(new URL('../src/components/LivestockModals/LivestockModals.jsx', import.meta.url), 'utf8');
const service = readFileSync(new URL('../src/services/livestockService.js', import.meta.url), 'utf8');

test('livestock form requests explicit age-estimation provenance instead of inventing a birth date', () => {
  assert.match(modals, /Estimated Biological Age \(days\)/);
  assert.match(modals, /Estimation Date/);
  assert.match(modals, /Confidence/);
  assert.match(modals, /Source \/ Basis/);
  assert.doesNotMatch(modals, /suggestGrowthStatus\s*\(/);
});

test('frontend delegates growth suggestions to backend profile assessment', () => {
  assert.match(service, /\/livestock\/growth-assessment\/preview/);
  assert.match(service, /\/livestock\/\$\{livestockId\}\/growth-assessment/);
  assert.match(modals, /Backend Suggested Stage/);
  assert.match(modals, /suggestionReason/);
  assert.match(modals, /profileStatus === "Draft"/);
});

test('growth history keeps actual and expected values visibly separate', () => {
  assert.match(modals, /Expected vs Actual Growth/);
  assert.match(modals, /Actual Weight/);
  assert.match(modals, /Expected Weight/);
  assert.match(modals, /record\.expectedStage/);
  assert.match(modals, /record\.deviationStatus/);
});

test('manager stage override requires a reason and calls audited backend action', () => {
  assert.match(service, /growth-stage-override/);
  assert.match(modals, /Manager Stage Override/);
  assert.match(modals, /stageOverride\.reason\.trim\(\)/);
  assert.match(modals, /Save Audited Override/);
});

test('acquisition history fields are sent independently from biological age', () => {
  assert.match(service, /acquisition_vaccination_history/);
  assert.match(service, /acquisition_treatment_history/);
  assert.match(service, /estimated_age_as_of_date/);
  assert.match(service, /estimated_age_confidence/);
  assert.match(service, /estimated_age_source/);
});
