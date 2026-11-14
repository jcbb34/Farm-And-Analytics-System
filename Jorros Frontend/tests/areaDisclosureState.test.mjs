import test from 'node:test';
import assert from 'node:assert/strict';
import { toggleExpandedGroup, areGroupsExpanded, setGroupsExpanded } from '../src/components/FarmAreas/areaDisclosureState.js';

test('fields start collapsed and toggling one expands only its sections', () => {
    const original = {};
    const first = toggleExpandedGroup(original, 1);
    assert.equal(original['1'], undefined);
    assert.equal(first['1'], true);
    assert.equal(first['2'], undefined);
    assert.equal(toggleExpandedGroup(first, 1)['1'], false);
});

test('expand all then collapse all preserves unrelated area and tab disclosure state', () => {
    const start = { FAC: true, B: false };
    const expanded = setGroupsExpanded(start, ['A', 'B', 'C'], true);
    assert.equal(areGroupsExpanded(expanded, ['A', 'B', 'C']), true);
    assert.equal(expanded.FAC, true);
    const collapsed = setGroupsExpanded(expanded, ['A', 'B', 'C'], false);
    assert.equal(areGroupsExpanded(collapsed, ['A', 'B', 'C']), false);
    assert.equal(collapsed.FAC, true);
});

test('groups with no child rows cannot report all expanded', () => {
    assert.equal(areGroupsExpanded({}, []), false);
    assert.equal(areGroupsExpanded({}, ['A']), false);
});

test('expanded state uses stable IDs even when field names are edited', () => {
    const selected = setGroupsExpanded({}, ['1', 2, 'FAC'], true);
    assert.equal(selected['1'], true);
    assert.equal(selected['2'], true);
    assert.equal(selected.FAC, true);
    assert.deepEqual(setGroupsExpanded(selected, ['2'], false), { '1': true, '2': false, FAC: true });
});
