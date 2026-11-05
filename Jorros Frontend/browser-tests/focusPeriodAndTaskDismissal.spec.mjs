import { test, expect } from '@playwright/test';

// All API traffic is isolated. These checks never use the farm database.
const today = '2026-11-05';
const admin = { id: 1, username: 'ui.admin', fullName: 'UI Test Administrator', role: 'System Administrator', permissions: ['*'], status: 'Active' };
const employee = { id: 42, full_name: 'Test Employee', employment_status: 'Active', portal_assignment_ready: true, positions: [] };
const task = { id: 5097, task_code: 'ACT-TEST', name: 'Inspect test fence', category: 'Inspection', related_to: 'Test farm', location: 'Test field', activity_date: today, status: 'Pending', priority: 'Medium', assigned_employee_id: 42, assigned_employee_name: employee.full_name, resource_required: false, requires_evidence: false, requires_review: true };
const activity = { id: 90, name: task.name, date: today, status: 'Pending', related_to: task.related_to, assigned_employee_id: 42, workflow_type: 'workforce_task', linked_task_id: task.id, available_actions: ['open_task', 'assisted_submission'] };

async function prepare(page, { authenticated = true, taskInPage = true, holdDetail = false } = {}) {
    const state = { writes: [], pageRequests: 0, detailRequests: 0 };
    const detailGate = new Promise((resolve) => { state.releaseDetail = resolve; });
    await page.clock.install({ time: new Date(`${today}T02:00:00Z`) });
    if (authenticated) await page.addInitScript((user) => {
        localStorage.setItem('joross-auth-session-v1', JSON.stringify({ accessToken: 'synthetic-ui-token', user, expiresAt: Date.now() + 86400000 }));
    }, admin);
    await page.route('**/api/v1/**', async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname;
        if (!['GET', 'HEAD'].includes(request.method())) state.writes.push({ path, method: request.method() });
        if (path === '/api/v1/auth/me') return route.fulfill({ json: admin });
        if (path.endsWith('/calendar/config')) return route.fulfill({ json: { today, timezone: 'Asia/Manila' } });
        if (path.endsWith('/events/stream') || path.includes('/weather')) return route.fulfill({ status: 503, json: {} });
        if (path === '/api/v1/workforce/tasks/page') {
            state.pageRequests += 1;
            return route.fulfill({ json: { items: taskInPage ? [task] : [], total: taskInPage ? 1 : 0 } });
        }
        if (path === `/api/v1/workforce/tasks/${task.id}`) {
            state.detailRequests += 1;
            if (holdDetail) await detailGate;
            return route.fulfill({ json: task });
        }
        if (path === '/api/v1/workforce/tasks/summary') return route.fulfill({ json: { pending: 1, progress: 0, review: 0, overdue: 0, reassign: 0 } });
        if (path === '/api/v1/workforce/employees') return route.fulfill({ json: url.searchParams.has('archived_only') ? [] : [employee] });
        if (path === '/api/v1/activities') return route.fulfill({ json: [activity] });
        return route.fulfill({ json: [] });
    });
    return state;
}

async function expectInside(child, parent) {
    const box = await child.boundingBox();
    const bounds = await parent.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(bounds.x);
    expect(box.x + box.width).toBeLessThanOrEqual(bounds.x + bounds.width + 1);
}

for (const theme of ['light', 'dark']) {
    test(`login has one complete field highlight and a usable password toggle (${theme})`, async ({ page }) => {
        await prepare(page, { authenticated: false });
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto('/login');
        await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), theme);
        const username = page.getByLabel('User Account', { exact: true });
        const password = page.getByLabel('Password', { exact: true });
        for (const input of [username, password]) {
            const wrapper = input.locator('..');
            const before = await wrapper.boundingBox();
            await input.focus();
            await expect(input).toHaveCSS('box-shadow', 'none');
            await expect(input).toHaveCSS('outline-style', 'none');
            await expect(wrapper).not.toHaveCSS('box-shadow', 'none');
            expect(await wrapper.boundingBox()).toEqual(before);
            await expectInside(input, wrapper);
        }
        await password.fill('synthetic-password');
        await page.getByRole('button', { name: 'Show password', exact: true }).click();
        await expect(password).toHaveAttribute('type', 'text');
        await expect(password).toHaveValue('synthetic-password');
        await page.getByRole('button', { name: 'Hide password', exact: true }).click();
        await expect(password).toHaveAttribute('type', 'password');
        await expect(username.locator('..')).toHaveCSS('box-shadow', 'none');
    });

    for (const width of [320, 390, 768, 1536]) {
        test(`Dashboard date controls stay aligned and inside the popover (${theme}, ${width}px)`, async ({ page }) => {
            await prepare(page);
            await page.setViewportSize({ width, height: 1000 });
            await page.goto('/dashboard');
            await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), theme);
            const period = page.getByRole('combobox', { name: 'Dashboard date period' });
            const control = page.locator('.dashboard-period-control');
            await period.focus();
            await expect(period).toHaveCSS('box-shadow', 'none');
            await expect(control).not.toHaveCSS('box-shadow', 'none');
            const periodBox = await control.boundingBox();
            const qrBox = await page.getByRole('button', { name: 'Show phone QR code' }).boundingBox();
            expect(periodBox.height).toBe(qrBox.height);
            expect(qrBox.x + qrBox.width).toBeLessThan(periodBox.x);
            await period.selectOption('custom');
            const dialog = page.getByRole('dialog', { name: 'Custom Date Range' });
            await expect(dialog).toBeVisible();
            await expect(dialog.getByLabel('From', { exact: true })).toBeFocused();
            const bounds = await dialog.boundingBox();
            expect(bounds.x).toBeGreaterThanOrEqual(0);
            expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
            for (const field of ['From', 'To']) await expectInside(dialog.getByLabel(field, { exact: true }), dialog);
            const cancel = dialog.getByRole('button', { name: 'Cancel', exact: true });
            const apply = dialog.getByRole('button', { name: 'Apply', exact: true });
            await expectInside(cancel, dialog);
            await expectInside(apply, dialog);
            expect((await cancel.boundingBox()).width).toBeCloseTo((await apply.boundingBox()).width, 0);
            if (process.env.UI_QA_SCREENSHOT_DIR && [390, 1536].includes(width)) {
                await page.screenshot({ path: `${process.env.UI_QA_SCREENSHOT_DIR}/period-${theme}-${width}.png` });
            }
        });
    }
}

test('date picker dismissal preserves the applied period and Apply normalizes the selected dates', async ({ page }) => {
    await prepare(page);
    await page.goto('/dashboard');
    const period = page.getByRole('combobox', { name: 'Dashboard date period' });
    const dialog = page.getByRole('dialog', { name: 'Custom Date Range' });
    await period.selectOption('today');
    for (const dismissal of ['Cancel', 'Close date picker', 'Escape', 'outside']) {
        await test.step(`dismiss with ${dismissal}`, async () => {
            await period.selectOption('custom');
            await expect(period).toHaveValue('custom');
            await dialog.getByLabel('From', { exact: true }).fill('2026-11-09');
            if (dismissal === 'Escape') await page.keyboard.press('Escape');
            else if (dismissal === 'outside') await page.getByRole('heading', { name: 'Welcome to Joross Farm!' }).click();
            else await dialog.getByRole('button', { name: dismissal, exact: true }).click();
            await expect(dialog).toHaveCount(0);
            await expect(page.getByRole('heading', { name: 'Unsaved Changes', exact: true })).toHaveCount(0);
            await expect(period).toHaveValue('today');
            expect(await page.evaluate(() => localStorage.getItem('joross-dashboard-period'))).toBe('today');
            if (dismissal !== 'outside') await expect(period).toBeFocused();
        });
    }
    await period.selectOption('custom');
    await dialog.getByLabel('From', { exact: true }).fill('2026-11-09');
    await dialog.getByLabel('To', { exact: true }).fill('2026-11-02');
    await dialog.getByRole('button', { name: 'Apply', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(period).toBeFocused();
    expect(await page.evaluate(() => localStorage.getItem('joross-dashboard-period'))).toBe('2026-11-02 to 2026-11-09');
    const edit = page.getByRole('button', { name: 'Edit custom date range' });
    await edit.click();
    await expect(dialog.getByLabel('From', { exact: true })).toHaveValue('2026-11-02');
    await expect(dialog.getByLabel('To', { exact: true })).toHaveValue('2026-11-09');
    await page.keyboard.press('Escape');
    await expect(edit).toBeFocused();
});

for (const dismissal of ['close', 'Cancel', 'Escape', 'backdrop']) {
    test(`Dashboard Record Work stays dismissed after ${dismissal}, refresh, and reload`, async ({ page }) => {
        const state = await prepare(page);
        await page.goto('/dashboard');
        await page.getByRole('button', { name: `Record Work for ${task.name}`, exact: true }).click();
        const dialog = page.getByRole('dialog', { name: 'Record Work for Employee', exact: true });
        await expect(dialog).toBeVisible();
        if (dismissal === 'Escape') await page.keyboard.press('Escape');
        else if (dismissal === 'backdrop') await page.locator('.workforce-modal-overlay').click({ position: { x: 5, y: 5 } });
        else await dialog.getByRole('button', { name: dismissal === 'close' ? 'Close assisted submission modal' : dismissal, exact: true }).click();
        await expect(dialog).toHaveCount(0);
        await expect.poll(() => new URL(page.url()).searchParams.has('action')).toBe(false);
        expect(new URL(page.url()).searchParams.get('taskId')).toBe(String(task.id));
        expect(new URL(page.url()).searchParams.get('returnTo')).toBe('/dashboard');
        const requestsBefore = state.pageRequests;
        await page.evaluate(() => window.dispatchEvent(new CustomEvent('joross:modules-updated', { detail: { modules: ['tasks'] } })));
        await expect.poll(() => state.pageRequests).toBeGreaterThan(requestsBefore);
        await expect(dialog).toHaveCount(0);
        await page.reload();
        await expect(page.locator(`#task-row-${task.id}`)).toBeVisible();
        await expect(dialog).toHaveCount(0);
        await page.getByRole('button', { name: 'Record Work', exact: true }).click();
        await expect(dialog).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(dialog).toHaveCount(0);
        await page.getByRole('button', { name: /Back to Dashboard/ }).click();
        await page.getByRole('button', { name: `Record Work for ${task.name}`, exact: true }).click();
        await expect(dialog).toBeVisible();
        expect(state.writes).toEqual([]);
    });
}

test('an exact task outside the loaded page opens once after its delayed detail arrives', async ({ page }) => {
    const state = await prepare(page, { taskInPage: false, holdDetail: true });
    const dialog = page.getByRole('dialog', { name: 'Record Work for Employee', exact: true });
    const nextTask = { ...task, id: task.id + 1, name: 'Inspect another test fence' };
    let nextDetailRequests = 0;
    let releaseNextDetail;
    const nextDetailGate = new Promise((resolve) => { releaseNextDetail = resolve; });
    await page.route(`**/api/v1/workforce/tasks/${nextTask.id}`, async (route) => {
        nextDetailRequests += 1;
        await nextDetailGate;
        return route.fulfill({ json: nextTask });
    });
    try {
        await page.goto(`/task-management?tab=tasks&taskId=${task.id}&action=assisted-submission&from=dashboard&returnTo=%2Fdashboard`);
        await expect.poll(() => state.detailRequests).toBeGreaterThan(0);
        await expect(dialog).toHaveCount(0);
        state.releaseDetail();
        await expect(dialog).toBeVisible();
        await dialog.getByRole('button', { name: 'Close assisted submission modal' }).click();
        await expect(dialog).toHaveCount(0);
        await expect.poll(() => new URL(page.url()).searchParams.has('action')).toBe(false);
        // A new link in the mounted page must wait for its own task details,
        // rather than reusing the previously focused task's record.
        await page.evaluate((id) => window.history.pushState(null, '', `/task-management?tab=tasks&taskId=${id}&action=assisted-submission&from=dashboard&returnTo=%2Fdashboard`), nextTask.id);
        await expect.poll(() => nextDetailRequests).toBeGreaterThan(0);
        await expect(dialog).toHaveCount(0);
        releaseNextDetail();
        await expect(dialog).toBeVisible();
        await expect(dialog.getByRole('heading', { name: nextTask.name, exact: true })).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(dialog).toHaveCount(0);
        expect(state.writes).toEqual([]);
    } finally {
        state.releaseDetail();
        releaseNextDetail();
    }
});
