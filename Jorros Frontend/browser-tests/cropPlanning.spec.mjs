import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import { serveSessionPolicy } from './helpers/serveSessionPolicy.mjs';
import { withDisplayData } from './helpers/displayApiFixtures.mjs';

const user = { id: 1, username: 'synthetic.crop.admin', fullName: 'Synthetic Crop Admin', role: 'System Administrator', permissions: ['*'], status: 'Active' };
const references = JSON.parse(fs.readFileSync(new URL('../../Jorros Backend/reference_data/crop_spacing_profiles.json', import.meta.url), 'utf8'));
const profiles = references.profiles.map((profile, index) => ({ ...profile, id: index + 1 }));
const land = { total_area_m2: '18000', unavailable_area_m2: '0', edit_version: 1, legacy_unmapped_count: 0, fields: [
    { id: 1, name: 'Synthetic Field A', area_m2: '10000', unavailable_area_m2: '0', edit_version: 1, sections: [
        { id: 11, field_id: 1, name: 'Synthetic A1', area_m2: '2000', unavailable_area_m2: '0', available_area_m2: '800', status: 'Partly Occupied', edit_version: 1 }] },
    { id: 2, name: 'Synthetic Field B', area_m2: '8000', unavailable_area_m2: '0', edit_version: 1, sections: [
        { id: 21, field_id: 2, name: 'Synthetic B1', area_m2: '2000', unavailable_area_m2: '0', available_area_m2: '2000', status: 'Available', edit_version: 1 }] },
] };

async function setup(page) {
    const writes = [], records = [];
    await page.addInitScript(profile => sessionStorage.setItem('joross-auth-session-v1', JSON.stringify({ accessToken: 'synthetic-crop-token', user: profile, expiresAt: Date.now() + 3600000 })), user);
    await page.route('**/api/v1/**', withDisplayData(async route => {
        if (await serveSessionPolicy(route, page)) return;
        const request = route.request(), path = new URL(request.url()).pathname.replace(/^\/api\/v1/, '');
        if (path === '/auth/me') return route.fulfill({ json: user });
        if (path === '/events/stream') return route.fulfill({ status: 503, json: {} });
        if (path === '/crop-planning/references') return route.fulfill({ json: { profiles, sources: references.sources, legacy_choices: [] } });
        if (path === '/crop-planning/land') return route.fulfill({ json: land });
        if (path === '/crop-planning/plantings') return route.fulfill({ json: [] });
        if (path === '/crop-planning/schedule-preview') return route.fulfill({ json: { horizon_days: 28, occurrences: [], conflicts: 0, note: 'Synthetic bounded preview.' } });
        if (path === '/workforce/employees') return route.fulfill({ json: [] });
        if (path === '/crops' && request.method() === 'POST') {
            writes.push({ body: request.postDataJSON(), key: request.headers()['idempotency-key'] });
            if (writes.length === 1) return route.fulfill({ status: 503, json: { detail: 'Synthetic temporary save failure; retry your entries.' } });
            const record = { ...request.postDataJSON(), id: 37, crop_code: 'SYN-37', edit_version: 1, status: 'Growing',
                current_growth: null, estimated_progress: null, growth_stage: 'Not estimated', is_archived: false };
            records.push(record);
            return route.fulfill({ status: 201, json: record });
        }
        if (path === '/crops') return route.fulfill({ json: records });
        if (path.startsWith('/alerts')) return route.fulfill({ json: [] });
        return route.fulfill({ json: [] });
    }));
    await page.goto('/crops');
    await page.getByRole('button', { name: /Add Crop/ }).click();
    return writes;
}

async function choose(page, name, query) {
    const input = page.getByRole('combobox', { name });
    await input.fill(query);
    await input.press('ArrowDown');
    await input.press('Enter');
}

test('dependent keyboard choices, unknown dates, saved areas, capacity and retry preserve actual entries', async ({ page }) => {
    const writes = await setup(page);
    await expect(page.getByRole('combobox', { name: /Variety \/ Type/ })).toBeDisabled();
    await expect(page.getByRole('combobox', { name: /^Section/ })).toBeDisabled();
    await choose(page, /Crop Name/, 'Coconut');
    await choose(page, /Variety \/ Type/, 'Tall');
    await choose(page, /Crop Name/, 'Banana');
    await expect(page.getByRole('combobox', { name: /Variety \/ Type/ })).toHaveValue('');
    await choose(page, /Variety \/ Type/, 'Saba');
    await choose(page, /^Field/, 'Synthetic Field A');
    await choose(page, /^Section/, 'Synthetic A1');
    await expect(page.getByLabel('Available usable area')).toHaveValue('800 m² (0.08 ha)');
    await page.getByLabel('Area for this planting (ha)').fill('0.05');
    await expect(page.getByLabel('Estimated Capacity')).toHaveValue('31 banana mat/clump positions');
    await page.getByLabel('Actual Quantity Planted').fill('26');
    await page.getByLabel('Current Surviving Plants').fill('25');
    await page.getByLabel('Already growing on the farm').check();
    await page.getByLabel('Planting date precision').selectOption('unknown');
    await expect(page.getByLabel('Planting Date', { exact: true })).toBeDisabled();
    await expect(page.getByLabel('Estimated schedule progress')).toHaveValue('Not estimated');
    const form = page.locator('form.add-crop-form');
    await form.locator('button[type=submit]').click();
    await expect.poll(() => writes.length).toBe(1);
    await expect(page.getByLabel('Actual Quantity Planted')).toHaveValue('26');
    await expect(page.getByLabel('Area for this planting (ha)')).toHaveValue('0.05');
    await form.locator('button[type=submit]').click();
    await expect.poll(() => writes.length).toBe(2);
    expect(writes[0].key).toBe(writes[1].key);
    expect(writes[1].body.planting_date).toBeNull();
    expect(writes[1].body.quantity_planted).toBe(26);
    expect(writes[1].body.current_surviving).toBe(25);
    expect(writes[1].body.section_id).toBe(11);
    await expect(form).toHaveCount(0);
});

test('changing field resets section and allocation while preserving notes and counts', async ({ page }) => {
    await setup(page);
    await choose(page, /Crop Name/, 'Banana');
    await choose(page, /Variety \/ Type/, 'Saba');
    await choose(page, /^Field/, 'Synthetic Field A');
    await choose(page, /^Section/, 'Synthetic A1');
    await page.getByLabel('Area for this planting (ha)').fill('0.05');
    await page.getByLabel('Actual Quantity Planted').fill('26');
    await page.getByRole('textbox', { name: 'Notes', exact: true }).fill('Keep these measured notes');
    await choose(page, /^Field/, 'Synthetic Field B');
    await expect(page.getByRole('combobox', { name: /^Section/ })).toHaveValue('');
    await expect(page.getByLabel('Area for this planting (ha)')).toHaveValue('');
    await expect(page.getByLabel('Actual Quantity Planted')).toHaveValue('26');
    await expect(page.getByRole('textbox', { name: 'Notes', exact: true })).toHaveValue('Keep these measured notes');
});
