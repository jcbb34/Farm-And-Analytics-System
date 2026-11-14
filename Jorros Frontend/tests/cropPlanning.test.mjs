import assert from 'node:assert/strict';
import test from 'node:test';
import { changeCrop, changeField, estimatedCapacity, planningPayload, profileChoices, recommendedSpacingProfile, farmTodayDateKey, validScheduleStartDate } from '../src/services/cropPlanningService.js';
import { calculateAutomaticCropProgress, getAutomaticGrowthStage } from '../src/services/cropService.js';

test('capacity uses the exact planting allocation and rejects unsupported geometry', () => {
    assert.equal(estimatedCapacity('0.20', '4', '4', 'square'), 125);
    assert.equal(estimatedCapacity('0.20', '5', '5', 'square'), 80);
    assert.equal(estimatedCapacity('0.000123', '0.91', '0.61', 'rectangular'), 2);
    assert.equal(estimatedCapacity('0.2', '4', '4', 'triangular'), null);
    assert.equal(estimatedCapacity('0.2', '0', '4', 'square'), null);
});

test('changing crop or field clears incompatible dependent choices and preserves independent inputs', () => {
    const form = { name: 'Coconut', crop_reference: 'coconut', variety: 'Tall', variety_reference: 'tall',
        spacing_profile_id: 1, section_id: 5, area: '0.12', quantityPlanted: '125', notes: 'Retain my notes' };
    const crop = changeCrop(form, { value: 'banana', label: 'Banana' });
    assert.equal(crop.variety, ''); assert.equal(crop.spacing_profile_id, null);
    assert.equal(crop.quantityPlanted, '125'); assert.equal(crop.notes, form.notes);
    const field = changeField(form, { value: 2, label: 'Other measured field' });
    assert.equal(field.section_id, null); assert.equal(field.area, '');
    assert.equal(field.variety_reference, 'tall'); assert.equal(field.notes, form.notes);
});

test('unknown and legacy/custom choices do not silently adopt another variety spacing', () => {
    const profiles = [{ crop_key: 'banana', variety_key: 'saba' }, { crop_key: 'banana', variety_key: 'latundan' }];
    assert.equal(profileChoices(profiles, 'banana', 'saba').length, 1);
    assert.deepEqual(profileChoices(profiles, 'banana', 'unknown'), []);
    assert.deepEqual(profileChoices(profiles, 'custom:legacy crop', 'custom:legacy variety'), []);
});

test('verified crop and variety defaults auto-select without borrowing optional or unrelated spacing', () => {
    const rows = [
        { id: 8, crop_key: 'coconut', variety_key: 'tall', version: 1, is_default: true },
        { id: 9, crop_key: 'coconut', variety_key: 'dwarf', version: 1, is_default: true },
        { id: 10, crop_key: 'banana', variety_key: 'saba', version: 1, is_default: true },
        { id: 11, crop_key: 'banana', variety_key: 'saba', version: 1, is_default: false },
        { id: 12, crop_key: 'coconut', variety_key: 'tall', version: 2, is_default: true },
    ];
    assert.equal(recommendedSpacingProfile(rows, 'coconut', 'tall')?.id, 12);
    assert.equal(recommendedSpacingProfile(rows, 'coconut', 'dwarf')?.id, 9);
    assert.equal(recommendedSpacingProfile(rows, 'banana', 'saba')?.id, 10);
    assert.equal(recommendedSpacingProfile(rows, 'banana', 'latundan'), null);
    assert.equal(recommendedSpacingProfile(rows, 'coconut', 'unknown'), null);
    assert.equal(recommendedSpacingProfile(rows, 'custom:crop', 'tall'), null);
    assert.equal(recommendedSpacingProfile([], 'coconut', 'tall'), null);
});

test('unknown dates remain not estimated even when an observed status is ready', () => {
    assert.equal(calculateAutomaticCropProgress(null, null), null);
    assert.equal(getAutomaticGrowthStage(null), 'Not estimated');
    const payload = planningPayload({ registration_kind: 'existing', planting_date_precision: 'unknown',
        initial_status: 'Ready for Harvest', confirm_ready: true, quantityPlanted: '42', care_schedules: [] });
    assert.equal(payload.initial_status, 'Ready for Harvest');
    assert.equal(payload.planting_date_precision, 'unknown');
    assert.equal(payload.quantityPlanted, undefined);
});


test('farm date uses Philippine calendar even across UTC midnight', () => {
    assert.equal(farmTodayDateKey(new Date('2026-11-13T16:01:00.000Z')), '2026-11-14');
    assert.equal(farmTodayDateKey(new Date('2026-11-14T15:59:00.000Z')), '2026-11-14');
    assert.equal(farmTodayDateKey(new Date('2026-11-14T16:00:00.000Z')), '2026-11-15');
});

test('new care schedule dates reject backdating, but unchanged historical dates survive edits', () => {
    const today = '2026-11-14';
    assert.equal(validScheduleStartDate('2026-11-13', '', today), false);
    assert.equal(validScheduleStartDate('2026-11-14', '', today), true);
    assert.equal(validScheduleStartDate('2026-11-20', '', today), true);
    assert.equal(validScheduleStartDate('2026-10-01', '2026-10-01', today), true);
    assert.equal(validScheduleStartDate('2026-10-02', '2026-10-01', today), false);
    assert.equal(validScheduleStartDate('2026-09-30', '2026-10-01', today), false);
});
