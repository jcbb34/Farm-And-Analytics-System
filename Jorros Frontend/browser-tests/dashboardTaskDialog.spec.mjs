import { serveSessionPolicy } from './helpers/serveSessionPolicy.mjs';
import { test, expect } from '@playwright/test';

// API requests are intercepted; no farm database is used by these checks.
const today = '2026-11-05';
const admin = { id: 1, username: 'dialog.admin', fullName: 'Dialog Test Administrator', role: 'System Administrator', permissions: ['*'], status: 'Active' };
const activities = [
    { id: 11, name: 'Morning Feeding - NP-Native Pig - Batch 04', related_to: 'NP-Native Pig - Batch 04', available_actions: ['resolve_assignment'], workflow_type: 'workforce_task', linked_task_id: 101, needs_reassignment: true },
    { id: 12, name: 'Morning Feeding - LWL-Large White/Landrace - Batch 02', related_to: 'LWL-Large White/Landrace - Batch 02', available_actions: ['open_task', 'assisted_submission'], workflow_type: 'workforce_task', linked_task_id: 102 },
    { id: 13, name: 'Inspect the greenhouse', related_to: 'Greenhouse A', available_actions: ['start_directly'], can_complete_directly: true },
    { id: 14, name: 'Review pending farm work', related_to: 'Test field', available_actions: [] },
    { id: 15, name: 'Check irrigation', related_to: 'Field B', available_actions: ['open_my_tasks'], workflow_type: 'workforce_task', linked_task_id: 105 },
    { id: 16, name: 'Reproduction Follow-up — BG-Boer Goat - Batch 02 with a long monitoring description', related_to: 'Pregnancy Check — BG-Boer Goat - Batch 02', available_actions: ['open_source'], source_path: '/livestock', source_module: 'Livestock', source_record_id: 7 },
].map((item) => ({ ...item, date: today, start_time: '06:00:00', status: 'Pending', priority: 'Medium' }));

async function prepare(page) {
    const mutations = [];
    await page.clock.install({ time: new Date(`${today}T02:00:00Z`) });
    await page.addInitScript((user) => sessionStorage.setItem('joross-auth-session-v1', JSON.stringify({ accessToken: 'synthetic-dialog-token', user, expiresAt: Date.now() + 86400000 })), admin);
    await page.route('**/api/v1/**', async (route) => {
        if (await serveSessionPolicy(route, page)) return;
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (!['GET', 'HEAD'].includes(request.method())) mutations.push({ path, method: request.method() });
        if (path === '/api/v1/auth/me') return route.fulfill({ json: admin });
        if (path.endsWith('/calendar/config')) return route.fulfill({ json: { today, timezone: 'Asia/Manila' } });
        if (path.endsWith('/events/stream') || path.includes('/weather')) return route.fulfill({ status: 503, json: {} });
        if (path === '/api/v1/activities') return route.fulfill({ json: activities });
        if (path === '/api/v1/workforce/tasks/page') return route.fulfill({ json: { items: [], total: 0 } });
        if (path === '/api/v1/workforce/tasks/summary') return route.fulfill({ json: {} });
        if (path === '/api/v1/workforce/tasks/101') return route.fulfill({ json: { id: 101, name: activities[0].name, status: 'Pending', activity_date: today, needs_reassignment: true } });
        return route.fulfill({ json: [] });
    });
    await page.goto('/dashboard');
    return mutations;
}

async function openList(page, kind = 'tasks') {
    const card = page.locator(kind === 'tasks' ? '.upcoming-tasks-card' : '.farm-activity-card');
    const trigger = card.getByRole('button', { name: /View All/ });
    await trigger.click();
    const dialog = page.getByRole('dialog', { name: kind === 'tasks' ? 'Upcoming Tasks' : 'Recent Farm Activity', exact: true });
    await expect(dialog).toBeVisible();
    return { trigger, dialog };
}

async function boundsInside(child, parent) {
    const box = await child.boundingBox();
    const outer = await parent.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(outer.x - 1);
    expect(box.x + box.width).toBeLessThanOrEqual(outer.x + outer.width + 1);
    expect(box.y).toBeGreaterThanOrEqual(outer.y - 1);
    expect(box.y + box.height).toBeLessThanOrEqual(outer.y + outer.height + 1);
    return box;
}

function expectSeparate(a, b) {
    const overlapX = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
    const overlapY = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
    expect(overlapX <= 0 || overlapY <= 0, 'The status badge and action must not overlap').toBe(true);
}

async function expectReadableButton(button) {
    const contrast = await button.evaluate((node) => {
        const style = getComputedStyle(node);
        const luminance = (color) => {
            const channels = color.match(/[\d.]+/g).slice(0, 3).map((value) => {
                const channel = Number(value) / 255;
                return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
            });
            return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
        };
        const text = luminance(style.color), background = luminance(style.backgroundColor);
        return (Math.max(text, background) + 0.05) / (Math.min(text, background) + 0.05);
    });
    expect(contrast).toBeGreaterThanOrEqual(4.5);
}

for (const theme of ['light', 'dark']) {
    for (const width of [320, 390, 768, 1024, 1440]) {
        test(`task dialog has balanced controls and non-overlapping actions (${theme}, ${width}px)`, async ({ page }) => {
            await page.setViewportSize({ width, height: 900 });
            await prepare(page);
            await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), theme);
            const { dialog } = await openList(page);
            const shell = await dialog.boundingBox();
            expect(shell.x).toBeGreaterThanOrEqual(0);
            expect(shell.y).toBeGreaterThanOrEqual(0);
            expect(shell.x + shell.width).toBeLessThanOrEqual(width);
            expect(shell.y + shell.height).toBeLessThanOrEqual(900);
            const title = dialog.getByRole('heading', { name: 'Upcoming Tasks', exact: true });
            expect(await title.evaluate((node) => parseFloat(getComputedStyle(node).fontSize))).toBeLessThanOrEqual(22);
            const search = dialog.getByRole('searchbox', { name: 'Search upcoming tasks' });
            const add = dialog.getByRole('button', { name: /Add Event/ });
            await expect(search).toBeFocused();
            await expectReadableButton(add);
            expect((await search.boundingBox()).height).toBe((await add.boundingBox()).height);
            await boundsInside(search, dialog);
            await boundsInside(add, dialog);
            await expect(dialog.getByRole('button', { name: /Add Activity/ })).toHaveCount(0);
            const rows = dialog.locator('.task-full-item');
            await expect(rows).toHaveCount(6);
            for (const row of await rows.all()) {
                await row.scrollIntoViewIfNeeded();
                expect(await row.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
                const status = await boundsInside(row.locator('.task-status-label'), row);
                for (const action of await row.getByRole('button').all()) {
                    const actionBox = await boundsInside(action, row);
                    expectSeparate(status, actionBox);
                }
            }
            // Headers remain visible while only the task list body scrolls.
            await boundsInside(dialog.getByRole('button', { name: 'Close upcoming tasks' }), dialog);
            await rows.first().scrollIntoViewIfNeeded();
            if (process.env.DIALOG_QA_SCREENSHOT_DIR && [390, 1440].includes(width)) {
                await page.mouse.move(width - 18, 18);
                await page.screenshot({ path: `${process.env.DIALOG_QA_SCREENSHOT_DIR}/tasks-${theme}-${width}.png` });
            }
        });
    }
}

for (const kind of ['tasks', 'activity']) {
    test(`${kind} list supports search, keyboard focus, dismissal and Add Event handoff`, async ({ page }) => {
        const mutations = await prepare(page);
        const originalOverflow = await page.evaluate(() => document.body.style.overflow);
        for (const dismissal of ['Escape', 'close', 'backdrop']) {
            const { trigger, dialog } = await openList(page, kind);
            const search = dialog.getByRole('searchbox');
            await expect(search).toBeFocused();
            expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden');
            await page.keyboard.press('Shift+Tab');
            await expect(dialog.getByRole('button', { name: /^Close / })).toBeFocused();
            await page.keyboard.press('Shift+Tab');
            expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
            await page.keyboard.press('Tab');
            await expect(dialog.getByRole('button', { name: /^Close / })).toBeFocused();
            if (dismissal === 'Escape') await page.keyboard.press('Escape');
            else if (dismissal === 'close') await dialog.getByRole('button', { name: /^Close / }).click();
            else await page.locator('.activity-modal-overlay').click({ position: { x: 3, y: 3 } });
            await expect(dialog).toHaveCount(0);
            await expect(trigger).toBeFocused();
            expect(await page.evaluate(() => document.body.style.overflow)).toBe(originalOverflow);
        }
        const { dialog } = await openList(page, kind);
        const search = dialog.getByRole('searchbox');
        await expectReadableButton(dialog.getByRole('button', { name: /Add Event/ }));
        if (kind === 'tasks') {
            await search.fill('Greenhouse A');
            await expect(dialog.locator('.task-full-item')).toHaveCount(1);
            await expect(dialog.getByText('Inspect the greenhouse', { exact: true })).toBeVisible();
            await search.fill('No matching task');
            await expect(dialog.getByText('No pending tasks found.', { exact: true })).toBeVisible();
        }
        await dialog.getByRole('button', { name: /Add Event/ }).click();
        await expect(dialog).toHaveCount(0);
        const eventForm = page.getByRole('dialog', { name: 'Add Farm Event', exact: true });
        await expect(eventForm).toBeVisible();
        expect(await eventForm.evaluate((node) => node.contains(document.activeElement))).toBe(true);
        expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden');
        await page.keyboard.press('Escape');
        await expect(eventForm).toHaveCount(0);
        expect(await page.evaluate(() => document.body.style.overflow)).toBe(originalOverflow);
        expect(mutations).toEqual([]);
    });
}

test('Resolve Assignment opens the exact task workflow without completing farm work', async ({ page }) => {
    const mutations = await prepare(page);
    const { dialog } = await openList(page);
    await dialog.getByRole('button', { name: `Resolve Assignment for ${activities[0].name}`, exact: true }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe('/task-management');
    const params = new URL(page.url()).searchParams;
    expect(params.get('taskId')).toBe('101');
    expect(params.get('assignmentState')).toBe('needs-reassignment');
    expect(params.get('returnTo')).toBe('/dashboard');
    expect(mutations).toEqual([]);
});
