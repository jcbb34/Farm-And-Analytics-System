import { test, expect } from '@playwright/test';

const today = '2026-11-04';
const admin = { id: 1, username: 'workflow.admin', fullName: 'Test Administrator', role: 'System Administrator', permissions: ['*'], status: 'Active' };
const employee = { id: 42, full_name: 'Ana Reyes', employment_status: 'Active', portal_assignment_ready: true, is_archived: false, positions: [] };
const crop = { id: 1, crop_code: 'CRP-TEST', name: 'Eggplant', variety: 'Test', field: 'Field A', area_hectares: 1, quantity_planted: 100, current_surviving: 100, current_growth: 50, status: 'Growing', planting_date: today, estimated_harvest: '2027-01-01', is_archived: false, growth_records: [], yield_records: [], pest_diseases: [] };
const item = { id: 7, item_code: 'INV-TEST', name: 'Test Fertilizer', category: 'Fertilizer', quantity: 20, reorder_level: 3, unit: 'kg', location: 'Warehouse A', date_acquired: today, is_archived: false, stock_records: [] };

async function prepare(page, { resourceError = false, retryTask = false, linkedUsage = false } = {}) {
    const writes = [];
    let usageRequests = 0;
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await page.clock.install({ time: new Date(`${today}T02:00:00Z`) });
    await page.addInitScript((user) => localStorage.setItem('joross-auth-session-v1', JSON.stringify({ accessToken: 'synthetic-workflow-token', user, expiresAt: Date.now() + 86400000 })), admin);
    await page.route('**/api/v1/**', async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname;
        if (path === '/api/v1/auth/me') return route.fulfill({ json: admin });
        if (path.endsWith('/calendar/config')) return route.fulfill({ json: { today, timezone: 'Asia/Manila' } });
        if (path.endsWith('/events/stream')) return route.fulfill({ status: 503, json: {} });
        if (path === '/api/v1/workforce/tasks' && request.method() === 'POST') {
            writes.push({ body: request.postDataJSON(), key: request.headers()['idempotency-key'] });
            if (retryTask && writes.length === 1) {
                await gate;
                return route.fulfill({ status: 503, json: { detail: 'Synthetic interrupted task response' } });
            }
            return route.fulfill({ status: 201, json: { id: 99, ...request.postDataJSON() } });
        }
        if (path === '/api/v1/workforce/tasks/page') return route.fulfill({ json: { items: [], total: 0 } });
        if (path === '/api/v1/workforce/tasks/summary') return route.fulfill({ json: { pending: 0, progress: 0, review: 0, overdue: 0, reassign: 0 } });
        if (path === '/api/v1/workforce/employees') return route.fulfill({ json: url.searchParams.has('archived_only') ? [] : [employee] });
        if (path === '/api/v1/workforce/availability') return route.fulfill({ json: [{ employee_id: employee.id, date: today, available: true }] });
        if (path === '/api/v1/workforce/positions') return route.fulfill({ json: [] });
        if (['/api/v1/crops', '/api/v1/crops/details'].includes(path)) return route.fulfill({ json: [crop] });
        if (path === '/api/v1/crops/1') return route.fulfill({ json: crop });
        if (path === '/api/v1/inventory') return route.fulfill({ json: [item] });
        if (path === '/api/v1/resource-usages') {
            usageRequests += 1;
            if (resourceError && usageRequests === 1) return route.fulfill({ status: 403, json: { detail: 'Synthetic resource data unavailable' } });
            return route.fulfill({ json: linkedUsage ? [{ id: 1, activity_id: 99, task_submission_id: 100, module: 'Crop', target_id: 1, inventory_item_id: 7, inventory_item_name: 'Test Fertilizer', inventory_item_code: 'INV-TEST', usage_type: 'Fertilizer', quantity: 5, unit: 'kg', usage_date: today }] : [{ id: 2, module: 'Livestock', usage_type: 'Vitamin / Supplement', quantity: 1500, unit: 'mL', usage_date: today }] });
        }
        if (path === '/api/v1/weather') return route.fulfill({ status: 503, json: { detail: 'Synthetic weather unavailable' } });
        if (path === '/api/v1/farm-locations') return route.fulfill({ json: { items: ['Field A', 'Warehouse A', 'Jorros Farm'] } });
        return route.fulfill({ json: [] });
    });
    return { writes, release };
}

test('Assign Task prevents overlapping saves and retains its command across a retry', async ({ page }) => {
    const state = await prepare(page, { retryTask: true });
    await page.goto('/task-management');
    await page.getByRole('button', { name: /Assign Task$/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Assign Task', exact: true });
    await dialog.locator('#assign-task-name').fill('Inspect fence');
    await dialog.locator('#assign-task-employee').selectOption('42');
    await expect(dialog.getByLabel('Manager review is required for assigned work')).toBeDisabled();
    await expect(dialog.getByText('This creates one dated assignment.', { exact: false })).toBeVisible();
    const form = dialog.locator('form');
    await form.evaluate((node) => { node.requestSubmit(); node.requestSubmit(); });
    await expect.poll(() => state.writes.length).toBe(1);
    await expect(dialog.getByRole('button', { name: /Saving/ })).toBeDisabled();
    state.release();
    await expect(page.getByText('Synthetic interrupted task response', { exact: true })).toBeVisible();
    await expect(dialog.locator('#assign-task-name')).toHaveValue('Inspect fence');
    await dialog.getByRole('button', { name: /Save Assignment/ }).click();
    await expect(dialog).toHaveCount(0);
    expect(state.writes).toHaveLength(2);
    expect(state.writes[0].key).toBeTruthy();
    expect(state.writes[1].key).toBe(state.writes[0].key);
});

test('Dashboard distinguishes resource failure from zero and renders unit totals after retry on mobile', async ({ page }) => {
    await prepare(page, { resourceError: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/dashboard');
    const section = page.getByRole('region', { name: 'Resource Consumption' });
    await expect(section.getByRole('alert')).toContainText('Synthetic resource data unavailable');
    await expect(section.getByText('0 usage records', { exact: true })).toHaveCount(0);
    await section.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(section.getByText('1,500 mL', { exact: true })).toBeVisible();
    await expect(section.getByRole('alert')).toHaveCount(0);
    expect(await section.locator('.dashboard-resource-grid').evaluate((node) => getComputedStyle(node).gridTemplateColumns.split(' ').length)).toBe(1);
    const box = await section.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(391);
    await expect(section.locator('.material-symbols-outlined').first()).toHaveAttribute('aria-hidden', 'true');
    await page.screenshot({ path: test.info().outputPath('resource-mobile.png') });
});

test('task-linked resource usage opens its task and does not offer independent edit or void', async ({ page }) => {
    await prepare(page, { linkedUsage: true });
    await page.goto('/crops');
    await page.getByTitle('View crop', { exact: true }).click();
    const panel = page.locator('.resource-usage-panel');
    await expect(panel.getByRole('link', { name: 'View task record' })).toHaveAttribute('href', '/task-management?taskId=99');
    await expect(panel.getByTitle('Correct usage', { exact: true })).toHaveCount(0);
    await expect(panel.getByTitle('Request authorized void and restore stock')).toHaveCount(0);
});
