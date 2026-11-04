import assert from 'node:assert/strict';
import test from 'node:test';
import { buildResourceCards, formatUsageTotal, resourcePeriodRange } from '../src/views/Dashboard/resourceOverview.js';

test('consumption totals format numbers while preserving separate units', () => {
    const rows = [
        { usageType: 'Fertilizer', quantity: 1500.25, unit: 'kg' },
        { usageType: 'Fertilizer', quantity: 2.5, unit: 'kg' },
        { usageType: 'Fertilizer', quantity: 5, unit: 'bags' },
    ];
    assert.equal(formatUsageTotal(rows, ['Fertilizer']), '1,502.75 kg / 5 bags');
});
test('animal health includes the current Vitamin / Supplement usage type', () => {
    const cards = buildResourceCards([{ usageType: 'Vitamin / Supplement', quantity: 1500, unit: 'mL' }], null);
    assert.equal(cards.find((row) => row.id === 'health').value, '1,500 mL');
    assert.equal(cards.find((row) => row.id === 'stock-watch').value, 'Unavailable');
});
test('voided usage is not counted and zero remains explicit', () => {
    assert.equal(formatUsageTotal([{ usageType: 'Feed', quantity: 10, unit: 'kg', isVoided: true }], ['Feed']), '0');
});
test('invalid numeric data and missing units fail instead of looking like zero usage', () => {
    for (const row of [{ quantity: NaN, unit: 'kg' }, { quantity: -2, unit: 'kg' }, { quantity: 2, unit: '' }]) {
        assert.throws(() => formatUsageTotal([{ usageType: 'Feed', ...row }], ['Feed']), /could not be read/);
    }
});
test('custom dashboard range is preserved for the resource API', () => {
    const range = resourcePeriodRange('2026-11-02 to 2026-11-04');
    assert.equal(range.startDate, '2026-11-02');
    assert.equal(range.endDate, '2026-11-04');
});
test('resource cards respect module permissions rather than claiming inaccessible modules have zero usage', () => {
    const cards = buildResourceCards([], null, { crop: true, livestock: false, inventory: false });
    assert.deepEqual(cards.map((row) => row.id), ['fertilizer', 'pesticide']);
});


test('small recorded usage retains the inventory ledger precision instead of becoming zero', () => {
    assert.equal(formatUsageTotal([{ usageType: 'Medicine', quantity: 0.001, unit: 'L' }], ['Medicine']), '0.001 L');
});
