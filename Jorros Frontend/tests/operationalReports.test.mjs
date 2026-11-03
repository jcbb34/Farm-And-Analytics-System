import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');

const form = read('src/views/Reports/components/ReportFormModal.jsx');
const filters = read('src/views/Reports/components/ReportsFilters.jsx');
const service = read('src/services/reportService.js');
const pageState = read('src/views/Reports/hooks/useReportsPageState.js');

test('Reports form exposes all ten Prompt 10.5 factual report types', () => {
  for (const reportType of [
    'Daily Attendance Report',
    'Weekly Attendance Summary',
    'Task Completion and Employee Performance',
    'Task Coverage and Reassignment',
    'Care Protocol Compliance',
    'Crop Yield and Input Usage',
    'Livestock Feeding, Growth, and Health',
    'Inventory Movement and Resource Usage',
    'Production and Sales Summary',
    'Generated Report History and Audit Trail',
  ]) {
    assert.match(form, new RegExp(reportType.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('operational reports expose server-side source filters and omit recommendations', () => {
  for (const name of ['employee_id', 'crop_id', 'field', 'livestock_id', 'pen_id', 'inventory_item_id', 'status', 'source']) {
    assert.match(form, new RegExp(`name=["']${name}["']`));
  }
  assert.match(form, /operationalReportTypes\.has\(form\.reportType\)/);
  assert.match(form, /section\.key !== "recommendations"/);
  assert.match(service, /filters:\s*data\.filters/);
});

test('Reports UI supports Prompt 10.5 lifecycle statuses while preserving legacy workflow', () => {
  for (const status of ['Draft', 'For Review', 'Approved', 'In Progress', 'Needs Review', 'Final', 'Revised', 'Failed']) {
    assert.match(filters, new RegExp(`"${status}"`));
  }
  const dataHook = read('src/views/Reports/hooks/useReportsData.js');
  assert.match(dataHook, /reportService\.getReportSummary/);
  assert.match(dataHook, /setReportSummary\(summary\)/);
  assert.match(pageState, /status:\s*statusFilter === "All" \? undefined : statusFilter/);
});

test('Reports history is paginated instead of loading every saved report into the browser', () => {
  const dataHook = read('src/views/Reports/hooks/useReportsData.js');
  const table = read('src/views/Reports/components/ReportsTable.jsx');
  assert.match(service, /offset:\s*options\.offset/);
  assert.match(service, /limit:\s*options\.limit/);
  assert.match(dataHook, /reportsPageSize\s*=\s*25/);
  assert.match(dataHook, /loadMoreReports/);
  assert.match(table, /Load More Reports/);
});
