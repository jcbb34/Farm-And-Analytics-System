import assert from 'node:assert/strict';
import test from 'node:test';
import { suggestedCropSection, DEFAULT_CROP_SECTIONS } from '../src/services/farmPlanService.js';
const land = { fields: [
    { id: 3, name: 'Field A — Coconut Plantation', sections: [{ id: 7, name: 'Section A1' }] },
    { id: 4, name: 'Field B — Banana Plantation', sections: [{ id: 8, name: 'Section B1' }, { id: 9, name: 'Section B2' }] },
    { id: 5, name: 'Field C — Root Crops', sections: [
        { id: 10, name: 'Section C1' }, { id: 11, name: 'Section C2' },
        { id: 12, name: 'Section C3' }, { id: 13, name: 'Section C4' }, { id: 14, name: 'Section C5' }] },
    { id: 6, name: 'Field D — Herb Plantation', sections: [{ id: 15, name: 'Section D1' }, { id: 16, name: 'Section D2' }] },
] };
test('all ten crop varieties suggest the matching draft field and section', () => {
    for (const [key, code] of Object.entries(DEFAULT_CROP_SECTIONS)) {
        const [crop, variety] = key.split(':');
        const result = suggestedCropSection(land, crop, variety);
        assert.equal(result?.code, code, key);
        assert.ok(result.fieldId > 0 && result.sectionId > 0, key);
    }
});
test('unknown, custom and unregistered crop varieties are not mapped silently', () => {
    assert.equal(suggestedCropSection(land, 'banana', 'latundan'), null);
    assert.equal(suggestedCropSection(land, 'banana', 'unknown'), null);
    assert.equal(suggestedCropSection(land, 'custom:anything', 'lakatan'), null);
    assert.equal(suggestedCropSection(null, 'coconut', 'tall'), null);
});
