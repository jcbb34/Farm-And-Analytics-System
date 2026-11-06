import { test, expect } from '@playwright/test';
const baseTime = Date.parse('2026-11-05T02:00:00Z');
const user = { id: 1, username: 'session.test', fullName: 'Session Test Administrator', role: 'System Administrator', status: 'Active', permissions: ['*'] };
const authKey = 'joross-auth-session-v1';
const clockContexts = new WeakSet();

async function prepare(page, { absoluteSeconds = 28800, persistent = false, blockStorage = false, state } = {}) {
    const server = state || { token: '', version: 0, active: false, requests: [], now: baseTime, absoluteSeconds };
    if (!clockContexts.has(page.context())) {
        await page.clock.install({ time: new Date(server.now) });
        clockContexts.add(page.context());
    }
    if (persistent) await page.addInitScript(({ key, user }) => localStorage.setItem(key, JSON.stringify({ accessToken: 'old-persistent-token', expiresAt: Date.now() + 86400000, user })), { key: authKey, user });
    if (blockStorage) await page.addInitScript((key) => {
        const original = Storage.prototype.setItem;
        Storage.prototype.setItem = function(name, value) { if (name === key) throw new DOMException('Storage blocked', 'SecurityError'); return original.call(this, name, value); };
    }, authKey);
    await page.route('**/api/v1/**', async (route) => {
        const req = route.request(), path = new URL(req.url()).pathname;
        try { server.now = Math.max(server.now, await page.evaluate(() => Date.now())); }
        catch { try { await route.abort('aborted'); } catch {} return; }
        if (path === '/api/v1/auth/login') {
            server.version += 1; server.token = `synthetic-session-${server.version}`; server.active = true;
            server.absolute = server.now + server.absoluteSeconds * 1000;
            server.idle = Math.min(server.now + 900000, server.absolute);
            return route.fulfill({ json: { access_token: server.token, token_type: 'bearer', expires_in: server.absoluteSeconds, user } });
        }
        const authorized = req.headers().authorization === `Bearer ${server.token}` && server.active && server.now < server.idle && server.now < server.absolute;
        const policy = () => ({ session_id: `1:${server.version}`, server_time: server.now / 1000, idle_expires_at: server.idle / 1000, absolute_expires_at: server.absolute / 1000, idle_timeout_seconds: 900, warning_seconds: 60 });
        if (path.startsWith('/api/v1/auth/')) server.requests.push({ path, method: req.method(), authorized });
        if (!authorized && path.startsWith('/api/v1/auth/')) return route.fulfill({ status: 401, json: { detail: 'Your session expired. Please sign in again.' } });
        if (path === '/api/v1/auth/session/activity') {
            if (server.failActivity) return route.fulfill({ status: 503, json: { detail: 'Synthetic connection failure' } });
            server.idle = Math.min(server.now + 900000, server.absolute);
            return route.fulfill({ json: policy() });
        }
        if (path === '/api/v1/auth/session') return route.fulfill({ json: policy() });
        if (path === '/api/v1/auth/logout') { server.active = false; if (server.logoutGate) await server.logoutGate; return route.fulfill({ json: { success: true } }); }
        if (path === '/api/v1/auth/me') return route.fulfill({ json: user });
        if (path.endsWith('/calendar/config')) return route.fulfill({ json: { today: '2026-11-05', timezone: 'Asia/Manila' } });
        if (path.includes('/weather') || path.endsWith('/events/stream')) return route.fulfill({ status: 503, json: {} });
        if (path.endsWith('/page')) return route.fulfill({ json: { items: [], total: 0 } });
        return route.fulfill({ json: [] });
    });
    return server;
}

async function signIn(page, navigate = true) {
    if (navigate) await page.goto('/login');
    await page.getByLabel('User Account', { exact: true }).fill('session.test');
    await page.getByLabel('Password', { exact: true }).fill('synthetic-password');
    await page.getByRole('button', { name: /Login$/ }).click();
    await expect(page.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    await expect.poll(() => page.evaluate((key) => JSON.parse(sessionStorage.getItem(key))?.sessionPolicy?.sessionId, authKey)).toMatch(/^1:/);
}
const warning = (page) => page.getByRole('alertdialog', { name: 'Your session will end soon' });
const activityCount = (server) => server.requests.filter((request) => request.path.endsWith('/session/activity')).length;

test('normal login is temporary, refresh preserves it and a fresh browser context requires login', async ({ page, browser }) => {
    const server = await prepare(page); await signIn(page);
    expect(await page.evaluate((key) => localStorage.getItem(key), authKey)).toBeNull();
    const saved = await page.evaluate((key) => JSON.parse(sessionStorage.getItem(key)), authKey);
    const originalLease = server.idle;
    await page.clock.fastForward(120000);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    expect(server.idle).toBe(originalLease);
    const restored = await page.evaluate((key) => JSON.parse(sessionStorage.getItem(key)), authKey);
    expect(Math.abs(restored.sessionPolicy.idleDeadline - saved.sessionPolicy.idleDeadline)).toBeLessThan(1000);
    expect(activityCount(server)).toBe(0);
    const fresh = await browser.newContext({ storageState: await page.context().storageState() });
    try {
        const tab = await fresh.newPage(); await prepare(tab, { state: server }); await tab.goto('/dashboard');
        await expect(tab.getByLabel('User Account', { exact: true })).toBeVisible();
    } finally { await fresh.close(); }
});

test('an old permanent login is removed without displaying the dashboard', async ({ page }) => {
    await prepare(page, { persistent: true }); await page.goto('/dashboard');
    await expect(page.getByLabel('User Account', { exact: true })).toBeVisible();
    expect(await page.evaluate((key) => localStorage.getItem(key), authKey)).toBeNull();
    await expect(page.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toHaveCount(0);
});

for (const theme of ['light', 'dark']) test(`idle warning is usable and fits a phone (${theme})`, async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), theme);
    await page.clock.fastForward(840000);
    const dialog = warning(page); await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Stay signed in', exact: true })).toBeFocused();
    const box = await dialog.boundingBox(); expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(390);
    await page.keyboard.press('Tab'); await expect(dialog.getByRole('button', { name: 'Sign out now' })).toBeFocused();
    await page.keyboard.press('Tab'); await expect(dialog.getByRole('button', { name: 'Stay signed in', exact: true })).toBeFocused();
    expect(activityCount(server)).toBe(0);
    if (process.env.SESSION_QA_DIR) await page.screenshot({ path: `${process.env.SESSION_QA_DIR}/warning-${theme}.png` });
    await dialog.getByRole('button', { name: 'Stay signed in', exact: true }).click();
    await expect(dialog).toHaveCount(0); expect(activityCount(server)).toBe(1);
    await page.clock.fastForward(840000); await expect(dialog).toBeVisible();
});

test('polling and synthetic input cannot keep an idle session alive', async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    await page.evaluate(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true })));
    await page.clock.fastForward(900000);
    await expect(page.getByLabel('User Account', { exact: true })).toBeVisible();
    expect(activityCount(server)).toBe(0);
    expect(await page.evaluate((key) => sessionStorage.getItem(key), authKey)).toBeNull();
    await expect(page.getByRole('heading', { name: 'Unsaved Changes' })).toHaveCount(0);
});

test('real activity renews idle time and reload does not renew it', async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    await page.clock.fastForward(600000);
    await page.getByRole('heading', { name: 'Welcome to Joross Farm!' }).click();
    await expect.poll(() => activityCount(server)).toBe(1);
    const deadline = server.idle;
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    expect(server.idle).toBe(deadline);
    await page.clock.fastForward(840000); await expect(warning(page)).toBeVisible();
    await page.clock.fastForward(60000); await expect(page.getByLabel('User Account', { exact: true })).toBeVisible();
});

test('session status checks preserve an unsaved farm event without broadcasting profile changes', async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    await page.getByRole('button', { name: /Add Event$/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Add Farm Event', exact: true });
    const title = dialog.getByLabel('Event Title', { exact: false });
    await title.fill('Unsaved crop monitoring event');
    await expect.poll(() => activityCount(server)).toBeGreaterThan(0);
    await page.evaluate(() => {
        window.profileEvents = 0;
        window.addEventListener('joross-profile-updated', () => { window.profileEvents += 1; });
    });
    const statusChecks = () => server.requests.filter((request) => request.path === '/api/v1/auth/session').length;
    const before = statusChecks();
    await page.clock.fastForward(65000);
    await expect.poll(statusChecks).toBeGreaterThan(before);
    await expect(title).toHaveValue('Unsaved crop monitoring event');
    expect(await page.evaluate(() => window.profileEvents)).toBe(0);
});

test('failed renewal does not extend the deadline and expiry still logs out', async ({ page }) => {
    const server = await prepare(page); await signIn(page); server.failActivity = true;
    const deadline = server.idle;
    await page.clock.fastForward(840000); await warning(page).getByRole('button', { name: 'Stay signed in', exact: true }).click();
    await expect(warning(page).getByRole('status')).toContainText('Check your connection');
    expect(server.idle).toBe(deadline);
    await page.clock.fastForward(60000); await expect(page.getByLabel('User Account', { exact: true })).toBeVisible();
});

test('the absolute deadline cannot be extended by keeping the warning open or choosing Keep working', async ({ page }) => {
    await prepare(page, { absoluteSeconds: 300 }); await signIn(page);
    await page.clock.fastForward(240000);
    await expect(warning(page)).toContainText('session time limit');
    await warning(page).getByRole('button', { name: 'Keep working' }).click();
    await expect(warning(page)).toHaveCount(0);
    await page.clock.fastForward(60000); await expect(page.getByLabel('User Account', { exact: true })).toBeVisible();
});

test('signing out also clears another open tab with the same session', async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    const session = await page.evaluate((key) => sessionStorage.getItem(key), authKey);
    const peer = await page.context().newPage(); await prepare(peer, { state: server });
    await peer.addInitScript(({ key, session }) => sessionStorage.setItem(key, session), { key: authKey, session });
    await peer.goto('/dashboard'); await expect(peer.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    await page.clock.fastForward(840000);
    await warning(page).getByRole('button', { name: 'Sign out now' }).click();
    await expect(page.getByLabel('User Account', { exact: true })).toBeVisible();
    await expect(peer.getByLabel('User Account', { exact: true })).toBeVisible();
    expect(await peer.evaluate((key) => sessionStorage.getItem(key), authKey)).toBeNull();
});

test('blocked temporary storage shows a sign-in error and releases the server session', async ({ page }) => {
    const server = await prepare(page, { blockStorage: true });
    await page.goto('/login'); await page.getByLabel('User Account', { exact: true }).fill('session.test');
    await page.getByLabel('Password', { exact: true }).fill('synthetic-password');
    await page.getByRole('button', { name: /Login$/ }).click();
    await expect(page.locator('.login-error-message').getByText('Temporary browser storage is unavailable. Enable it before signing in.', { exact: true })).toBeVisible();
    await expect.poll(() => server.active).toBe(false);
});


test('a new tab joins a live temporary session without permanent credentials', async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    const peer = await page.context().newPage(); await prepare(peer, { state: server });
    await peer.goto('/dashboard');
    await expect(peer.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    expect(server.version).toBe(1);
    expect(await peer.evaluate((key) => localStorage.getItem(key), authKey)).toBeNull();
    expect(await peer.evaluate((key) => JSON.parse(sessionStorage.getItem(key)).accessToken, authKey)).toBe(server.token);
});


test('a delayed old logout response cannot clear a newer sign-in', async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    let release;
    server.logoutGate = new Promise((resolve) => { release = resolve; });
    try {
        await page.clock.fastForward(840000);
        await warning(page).getByRole('button', { name: 'Sign out now' }).click();
        await expect(page.getByLabel('User Account', { exact: true })).toBeVisible();
        await signIn(page, false);
        const token = server.token;
        const response = page.waitForResponse((reply) => new URL(reply.url()).pathname === '/api/v1/auth/logout');
        release();
        await (await response).finished();
        await page.evaluate(() => Promise.resolve());
        await expect.poll(() => page.evaluate((key) => JSON.parse(sessionStorage.getItem(key))?.accessToken, authKey)).toBe(token);
        await page.reload();
        await expect(page.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    } finally { release?.(); }
});

test('activity in one tab keeps another tab in the same session alive', async ({ page }) => {
    const server = await prepare(page); await signIn(page);
    const peer = await page.context().newPage(); await prepare(peer, { state: server });
    await peer.goto('/dashboard');
    await expect(peer.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    const original = await peer.evaluate((key) => JSON.parse(sessionStorage.getItem(key)).sessionPolicy.idleDeadline, authKey);
    await page.clock.fastForward(600000); // The clock is shared by every page in this browser context.
    await page.getByRole('heading', { name: 'Welcome to Joross Farm!' }).click();
    await expect.poll(() => peer.evaluate((key) => JSON.parse(sessionStorage.getItem(key)).sessionPolicy.idleDeadline, authKey)).toBeGreaterThan(original + 500000);
    await page.clock.fastForward(300000);
    await expect(peer.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Welcome to Joross Farm!' })).toBeVisible();
});
