import { test, expect } from '@playwright/test';
const profile = { id: 77, username: 'recovery.admin', fullName: 'Recovery Administrator', role: 'System Administrator', permissions: ['*'], status: 'Active' };
const options = { format: 'both', destination: 'local', encrypted: true, recovery_key_acknowledged: true, schedule_enabled: false, frequency: 'daily', hour: 2, minute: 0, weekday: 0, month_day: 1, interval_days: 7, timezone: 'Asia/Manila', reminder_enabled: true, reminder_days: 7, retention_enabled: false, retain_count: 10 };
const backup = { id: 'synthetic-backup', created_at: '2026-11-04T02:00:00Z', actor: 'recovery.admin', status: 'Completed', format: 'both', encrypted: true, file_validated: true, tested_formats: ['zip'], restore_tested_at: '2026-11-04T03:00:00Z', cloud_status: 'Needs attention', artifacts: { zip: { name: 'synthetic-backup.recovery.zip', size: 1024, encrypted: true }, bak: { name: 'synthetic-backup.bak', size: 2048, encrypted: true }, assets: { name: 'synthetic-backup.photos.zip', size: 1024, encrypted: true } } };
const candidate = { id: 'candidate123', format: 'zip', status: 'Validated', file_validated: true, row_count: 42, table_count: 8, photo_count: 2, source_date: backup.created_at };
async function setup(page, { ready = true, activation = false, dark = false } = {}) {
    const errors = [], requests = [];
    const data = { options: structuredClone(options), sets: [structuredClone(backup)], jobs: [], drills: [], rollbacks: [], audit: [], recovery_key_exported: true, storage: { free_bytes: 2 ** 34 }, readiness: { available: ready, activation_enabled: activation }, drive: { status: 'Connected', configured: true, email: 'synthetic@example.test', folder_name: 'Farm Backups' }, last_local: backup.created_at, last_test: backup.restore_tested_at };
    page.on('pageerror', error => errors.push(error.message));
    await page.mouse.move(1000, 650);
    await page.addInitScript(({ profile, dark }) => { localStorage.setItem('joross-auth-session-v1', JSON.stringify({ accessToken: 'synthetic-browser-token', expiresAt: Date.now() + 86400000, user: profile })); localStorage.setItem('joross-theme', dark ? 'dark' : 'light'); }, { profile, dark });
    await page.route('**/api/v1/**', route => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path.endsWith('/events/stream')) return route.fulfill({ status: 503, json: {} });
        if (path === '/api/v1/auth/me') return route.fulfill({ json: profile });
        if (!path.startsWith('/api/v1/backup-recovery')) return route.fulfill({ json: [] });
        const endpoint = path.slice('/api/v1/backup-recovery'.length);
        if (endpoint === '/overview') return route.fulfill({ json: data });
        if (endpoint === '/notices') return route.fulfill({ json: [] });
        const payload = request.headers()['content-type']?.includes('application/json') ? request.postDataJSON() : undefined;
        requests.push({ endpoint, payload, key: request.headers()['idempotency-key'] });
        if (endpoint === '/backups') { const job = { id: 'backup-job', kind: 'backup', status: 'Queued', stage: 'Waiting for worker' }; data.jobs.push(job); return route.fulfill({ status: 202, json: job }); }
        if (endpoint === '/settings') { data.options = payload; return route.fulfill({ json: payload }); }
        if (endpoint === '/readiness') return route.fulfill({ json: { ...data.readiness, estimated_bytes: 10000 } });
        if (endpoint.endsWith('/prepare') || endpoint === '/candidates/import') { data.drills = [structuredClone(candidate)]; return route.fulfill({ json: data.drills[0] }); }
        if (endpoint.endsWith('/test')) { data.drills[0] = { ...data.drills[0], status: 'Ready', restore_tested: true, tested_at: '2026-11-04T03:00:00Z', expires_at: '2099-01-01T00:00:00Z' }; const job = { id: 'test-job', kind: 'test', status: 'Completed', result: { id: candidate.id } }; data.jobs.push(job); return route.fulfill({ status: 202, json: job }); }
        if (endpoint.endsWith('/activate')) { const job = { id: 'activate-job', kind: 'activate', status: 'Queued', stage: 'Preparing safety backup' }; data.jobs.push(job); return route.fulfill({ status: 202, json: job }); }
        if (endpoint === '/recovery-key') return payload.password === 'Synthetic Password' ? route.fulfill({ contentType: 'application/octet-stream', body: 'synthetic-key' }) : route.fulfill({ status: 403, json: { detail: 'Administrator verification failed.' } });
        if (endpoint.includes('/download/')) return route.fulfill({ contentType: 'application/octet-stream', body: 'synthetic-encrypted-file' });
        return route.fulfill({ json: {} });
    });
    await page.goto('/settings?section=data');
    await page.mouse.move(page.viewportSize().width - 10, 60);
    await expect(page.locator('.sidebar')).toHaveCSS('width', '80px');
    await expect(page.getByRole('button', { name: 'Back Up Now', exact: true })).toBeEnabled();
    return { data, requests, errors };
}
async function openRestore(page) {
    const row = page.getByRole('row').filter({ hasText: backup.id.slice(0, 12) });
    await row.getByText('Files & Actions', { exact: true }).click();
    await row.getByRole('button', { name: 'Test / Restore ZIP', exact: true }).click();
    return page.getByRole('dialog', { name: 'Restore Backup', exact: true });
}
test('System Data tabs preserve imports and preferences with keyboard navigation', async ({ page }) => {
    const state = await setup(page), tab = page.getByRole('tab', { name: 'Backup & Recovery', exact: true });
    await expect(tab).toHaveAttribute('aria-selected', 'true'); await tab.focus(); await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: 'Smart Import', exact: true })).toBeFocused();
    await expect(page.getByRole('tabpanel', { name: 'Backup & Recovery', exact: true })).toBeHidden();
    await page.keyboard.press('End'); await expect(page.getByRole('tab', { name: 'Preferences', exact: true })).toHaveAttribute('aria-selected', 'true'); expect(state.errors).toEqual([]);
});
test('Both formats queue one encrypted command and display truthful format-specific statuses', async ({ page }) => {
    const state = await setup(page), row = page.getByRole('row').filter({ hasText: backup.id.slice(0, 12) });
    await expect(row.getByText('Completed', { exact: true })).toBeVisible(); await expect(row.getByText('Needs attention', { exact: true })).toBeVisible();
    await expect(row.getByText('ZIP: Restore tested', { exact: true })).toBeVisible(); await expect(row.getByText('BAK: Not restore tested', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Back Up Now', exact: true }).click(); const dialog = page.getByRole('dialog', { name: 'Create Backup', exact: true }); await dialog.getByRole('button', { name: 'Create Backup', exact: true }).click();
    await expect(dialog).toHaveCount(0); expect(state.requests.filter(value => value.endpoint === '/backups')).toHaveLength(1); expect(state.requests.find(value => value.endpoint === '/backups')).toMatchObject({ payload: { format: 'both', destination: 'local', encrypted: true } }); expect(state.requests.find(value => value.endpoint === '/backups').key).toBeTruthy();
    await expect(page.getByRole('region', { name: 'Backup and recovery progress' }).getByText('Queued', { exact: true })).toBeVisible(); expect(state.errors).toEqual([]);
});
test('ZIP works while native server setup is incomplete', async ({ page }) => {
    await setup(page, { ready: false }); await page.getByRole('button', { name: 'Back Up Now', exact: true }).click(); const dialog = page.getByRole('dialog', { name: 'Create Backup', exact: true });
    await expect(dialog.getByRole('button', { name: 'Create Backup', exact: true })).toBeDisabled(); await dialog.getByRole('combobox', { name: 'Backup format', exact: true }).selectOption('zip'); await expect(dialog.getByRole('button', { name: 'Create Backup', exact: true })).toBeEnabled();
});
test('Schedule drafts survive refresh and save custom timing and retention', async ({ page }) => {
    const state = await setup(page); await page.getByLabel('Enable automatic backups', { exact: true }).check(); await page.getByRole('combobox', { name: 'Frequency', exact: true }).selectOption('monthly'); await page.getByRole('spinbutton', { name: /Day of month/ }).fill('31'); await page.getByLabel('Backup time', { exact: true }).fill('03:45'); await page.getByLabel('Automatically clean up older backup sets', { exact: true }).check();
    await page.getByRole('button', { name: 'Check SQL Server', exact: true }).click(); await expect(page.getByRole('spinbutton', { name: /Day of month/ })).toHaveValue('31'); await page.getByRole('button', { name: 'Save Backup Settings', exact: true }).click();
    await expect.poll(() => state.requests.some(value => value.endpoint === '/settings')).toBe(true); expect(state.requests.find(value => value.endpoint === '/settings').payload).toMatchObject({ frequency: 'monthly', month_day: 31, hour: 3, minute: 45, timezone: 'Asia/Manila', retention_enabled: true });
});
test('Activation requires a completed test and deliberate fresh Admin confirmation', async ({ page }) => {
    const state = await setup(page, { activation: true }), dialog = await openRestore(page); await expect(dialog.getByRole('button', { name: 'Restore and Activate', exact: true })).toHaveCount(0); await dialog.getByRole('button', { name: 'Test Restore', exact: true }).click(); await expect(dialog.getByText('Restore test passed', { exact: true })).toBeVisible(); const activate = dialog.getByRole('button', { name: 'Restore and Activate', exact: true }); await expect(activate).toBeDisabled();
    await dialog.getByLabel('Current password', { exact: true }).fill('Synthetic Password'); await dialog.getByLabel('Type RESTORE to confirm', { exact: true }).fill('RESTORE'); await dialog.getByLabel('I understand this replaces', { exact: false }).check(); await activate.click();
    await expect(dialog.getByText('Activation requested', { exact: true })).toBeVisible(); expect(state.requests.find(value => value.endpoint.endsWith('/activate')).payload).toMatchObject({ password: 'Synthetic Password', confirmation: 'RESTORE' }); await expect(dialog.getByRole('button', { name: 'Close Restore Backup', exact: true })).toBeDisabled(); expect(state.errors).toEqual([]);
});
test('Activation remains gated until host setup is completed', async ({ page }) => {
    const state = await setup(page), dialog = await openRestore(page); await dialog.getByRole('button', { name: 'Test Restore', exact: true }).click(); await expect(dialog.getByText('Activation is disabled', { exact: false })).toBeVisible(); await expect(dialog.getByLabel('Current password', { exact: true })).toHaveCount(0); expect(state.requests.some(value => value.endpoint.endsWith('/activate'))).toBe(false);
});
test('BAK import requires its matching photo package', async ({ page }) => {
    const state = await setup(page); await page.getByRole('button', { name: 'Restore Backup', exact: true }).click(); const dialog = page.getByRole('dialog', { name: 'Restore Backup', exact: true }); await dialog.getByRole('combobox', { name: 'Backup format', exact: true }).selectOption('bak'); await dialog.getByLabel('SQL Server BAK file', { exact: true }).setInputFiles({ name: 'test.bak', mimeType: 'application/octet-stream', buffer: Buffer.from('test') }); await dialog.getByRole('button', { name: 'Validate Backup', exact: true }).click(); expect(state.requests.some(value => value.endpoint === '/candidates/import')).toBe(false);
    await dialog.getByLabel('Matching photos and manifest package', { exact: false }).setInputFiles({ name: 'test.photos.zip', mimeType: 'application/zip', buffer: Buffer.from('test') }); await dialog.getByRole('button', { name: 'Validate Backup', exact: true }).click(); await expect(dialog.getByRole('button', { name: 'Test Restore', exact: true })).toBeVisible();
});
test('Key export rejects wrong credentials, clears secrets and downloads after verification', async ({ page }) => {
    await setup(page); await page.getByRole('button', { name: 'Download Recovery Key', exact: true }).click(); const dialog = page.getByRole('dialog', { name: 'Download Recovery Key', exact: true }); await dialog.getByLabel('Current password', { exact: true }).fill('Wrong'); await dialog.getByRole('button', { name: 'Download Recovery Key', exact: true }).click(); await expect(dialog.getByRole('alert')).toHaveText('Administrator verification failed.'); await expect(dialog.getByLabel('Current password', { exact: true })).toHaveValue(''); await dialog.getByLabel('Current password', { exact: true }).fill('Synthetic Password'); const pending = page.waitForEvent('download'); await dialog.getByRole('button', { name: 'Download Recovery Key', exact: true }).click(); expect((await pending).suggestedFilename()).toBe('Joross_recovery.key'); await expect(dialog).toHaveCount(0);
});
for (const dark of [false, true]) test(`Recovery fits a phone in ${dark ? 'dark' : 'light'} mode with modal focus trapping`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 }); const state = await setup(page, { dark }); await expect(page.locator('html')).toHaveAttribute('data-theme', dark ? 'dark' : 'light'); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.getByRole('button', { name: 'Restore Backup', exact: true }).click(); const dialog = page.getByRole('dialog', { name: 'Restore Backup', exact: true }), bounds = await dialog.boundingBox(); expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(390); expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await dialog.getByRole('button', { name: 'Validate Backup', exact: true }).focus(); await page.keyboard.press('Tab'); await expect(dialog.getByRole('button', { name: 'Close Restore Backup', exact: true })).toBeFocused(); await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); expect(state.errors).toEqual([]);
});
