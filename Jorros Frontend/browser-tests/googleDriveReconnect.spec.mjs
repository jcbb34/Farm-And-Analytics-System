import { test, expect } from '@playwright/test';

const profile = { id: 77, username: 'drive.admin', fullName: 'Drive Test Administrator', role: 'System Administrator', permissions: ['*'], status: 'Active' };
const googleUrl = 'https://accounts.google.com/o/oauth2/v2/auth?client_id=synthetic-client.apps.googleusercontent.com&state=synthetic-state';

async function prepare(page, { configured = false, status = 'Needs reconnection', authorizationUrl = googleUrl } = {}) {
    const state = { overviewRequests: 0, connectRequests: [], overviewStatus: 200, authorizationUrl };
    state.data = {
        sets: [], jobs: [], drills: [], rollbacks: [], audit: [],
        options: { format: 'zip', destination: 'local', encrypted: true, recovery_key_acknowledged: true, schedule_enabled: false, frequency: 'daily', hour: 2, minute: 0, weekday: 0, month_day: 1, interval_days: 7, timezone: 'Asia/Manila', reminder_enabled: false, reminder_days: 7, retention_enabled: false, retain_count: 10 },
        drive: { configured, status, email: status ? 'owner@example.test' : null, folder_name: status ? 'Farm Backups' : null },
        storage: { free_bytes: 2 ** 34 }, readiness: { available: true },
    };
    await page.addInitScript((user) => localStorage.setItem('joross-auth-session-v1', JSON.stringify({ accessToken: 'synthetic-drive-token', user, expiresAt: Date.now() + 86400000 })), profile);
    // Google navigation is fulfilled locally: these tests never contact Google
    // or request real credentials, and every farm API request is intercepted.
    await page.route('https://accounts.google.com/**', (route) => route.fulfill({ contentType: 'text/html', body: '<title>Synthetic Google sign-in</title><p>Test authorization page</p>' }));
    await page.route('**/api/v1/**', (route) => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path === '/api/v1/auth/me') return route.fulfill({ json: profile });
        if (path.endsWith('/events/stream')) return route.fulfill({ status: 503, json: {} });
        if (path === '/api/v1/backup-recovery/overview') {
            state.overviewRequests += 1;
            return route.fulfill({ status: state.overviewStatus, json: state.overviewStatus === 200 ? state.data : { detail: 'Administrator permission is required.' } });
        }
        if (path === '/api/v1/backup-recovery/drive/connect') {
            state.connectRequests.push({ method: request.method(), authorization: request.headers().authorization });
            return route.fulfill({ json: { authorization_url: state.authorizationUrl } });
        }
        return route.fulfill({ json: [] });
    });
    await page.goto('/settings?section=data');
    await expect(page.getByRole('button', { name: 'Back Up Now', exact: true })).toBeEnabled();
    return state;
}

test('Reconnect is pressable with missing server settings and opens actionable setup help', async ({ page }) => {
    const state = await prepare(page);
    const reconnect = page.getByRole('button', { name: 'Reconnect Google Drive', exact: true });
    await expect(reconnect).toBeEnabled();
    await reconnect.click();
    const dialog = page.getByRole('dialog', { name: 'Google Drive Server Setup', exact: true });
    await expect(dialog).toBeVisible();
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
    for (const setting of ['BACKUP_GOOGLE_CLIENT_ID', 'BACKUP_GOOGLE_CLIENT_SECRET', 'BACKUP_GOOGLE_REDIRECT_URI']) await expect(dialog.getByText(setting, { exact: true })).toBeVisible();
    await expect(dialog.getByText('Jorros Backend/.env', { exact: true })).toBeVisible();
    await expect(dialog.getByText(/restart the application/)).toBeVisible();
    await expect(dialog.locator('input')).toHaveCount(0);
    await dialog.getByRole('button', { name: 'Check Again and Connect', exact: true }).click();
    await expect(dialog.getByRole('button', { name: 'Check Again and Connect', exact: true })).toBeEnabled();
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
    expect(state.connectRequests).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(reconnect).toBeFocused();
    await page.getByRole('button', { name: 'Back Up Now', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Create Backup', exact: true })).toBeVisible();
});

test('new connection can also show setup help without a saved account', async ({ page }) => {
    const state = await prepare(page, { status: null });
    await page.getByRole('button', { name: 'Connect Google Drive', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Google Drive Server Setup', exact: true })).toBeVisible();
    expect(state.connectRequests).toEqual([]);
});

for (const close of ['header', 'footer', 'backdrop']) {
    test(`setup help closes from ${close} and restores reconnect focus`, async ({ page }) => {
        const state = await prepare(page);
        const reconnect = page.getByRole('button', { name: 'Reconnect Google Drive', exact: true });
        await reconnect.click();
        const dialog = page.getByRole('dialog', { name: 'Google Drive Server Setup', exact: true });
        await expect(dialog).toBeVisible();
        if (close === 'backdrop') await page.locator('.br-overlay').click({ position: { x: 3, y: 3 } });
        else await dialog.getByRole('button', { name: close === 'header' ? 'Close Google Drive Server Setup' : 'Close', exact: true }).click();
        await expect(dialog).toHaveCount(0);
        await expect(reconnect).toBeFocused();
        expect(state.connectRequests).toEqual([]);
    });
}

test('Check Again uses the restarted server settings and continues to Google with administrator authorization', async ({ page }) => {
    const state = await prepare(page);
    await page.getByRole('button', { name: 'Reconnect Google Drive', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Google Drive Server Setup', exact: true });
    await expect(dialog).toBeVisible();
    state.data.drive.configured = true;
    await dialog.getByRole('button', { name: /Check Again and Connect|Continue to Google/ }).click();
    await expect(page).toHaveURL(googleUrl);
    await expect(page).toHaveTitle('Synthetic Google sign-in');
    expect(state.connectRequests).toEqual([{ method: 'POST', authorization: 'Bearer synthetic-drive-token' }]);
});

test('Reconnect refreshes stale configuration instead of relying on the old disabled state', async ({ page }) => {
    const state = await prepare(page);
    state.data.drive.configured = true;
    await page.getByRole('button', { name: 'Reconnect Google Drive', exact: true }).click();
    await expect(page).toHaveURL(googleUrl);
    expect(state.connectRequests).toHaveLength(1);
});

test('an already configured server opens Google directly', async ({ page }) => {
    const state = await prepare(page, { configured: true });
    await page.getByRole('button', { name: 'Reconnect Google Drive', exact: true }).click();
    await expect(page).toHaveURL(googleUrl);
    expect(state.connectRequests).toHaveLength(1);
});

for (const authorizationUrl of [null, 'https://untrusted.example.test/oauth', 'https://accounts.google.com:8443/oauth', 'https://user:password@accounts.google.com/oauth']) {
    test(`invalid authorization address is rejected (${authorizationUrl === null ? 'missing' : new URL(authorizationUrl).origin})`, async ({ page }) => {
        const state = await prepare(page, { configured: true, authorizationUrl });
        await page.getByRole('button', { name: 'Reconnect Google Drive', exact: true }).click();
        await expect(page.locator('.br-root').getByRole('alert')).toContainText(/valid Google sign-in address|Unexpected Google authorization address/);
        expect(new URL(page.url()).pathname).toBe('/settings');
        expect(state.connectRequests).toHaveLength(1);
        await expect(page.getByRole('button', { name: 'Reconnect Google Drive', exact: true })).toBeEnabled();
    });
}

test('a failed administrator configuration check leaves reconnect retryable and sends no OAuth request', async ({ page }) => {
    const state = await prepare(page, { configured: true });
    state.overviewStatus = 403;
    await page.getByRole('button', { name: 'Reconnect Google Drive', exact: true }).click();
    await expect(page.locator('.br-root').getByRole('alert')).toContainText('Administrator permission is required.');
    await expect(page.getByRole('button', { name: 'Reconnect Google Drive', exact: true })).toBeEnabled();
    expect(state.connectRequests).toEqual([]);
});

for (const theme of ['light', 'dark']) {
    test(`setup help fits on a phone (${theme})`, async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        await prepare(page);
        await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), theme);
        await page.getByRole('button', { name: 'Reconnect Google Drive', exact: true }).click();
        const dialog = page.getByRole('dialog', { name: 'Google Drive Server Setup', exact: true });
        await expect(dialog).toBeVisible();
        const box = await dialog.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(390);
        expect(box.height).toBeLessThanOrEqual(844);
        expect(await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
        await dialog.getByRole('button', { name: 'Close', exact: true }).click();
        await expect(dialog).toHaveCount(0);
    });
}
