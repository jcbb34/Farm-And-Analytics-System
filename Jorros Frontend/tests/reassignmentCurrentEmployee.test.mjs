import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const modal = await fs.readFile(path.join(root, 'src/views/TaskManagement/components/TaskManagementModals.jsx'), 'utf8');
const page = await fs.readFile(path.join(root, 'src/views/TaskManagement/TaskManagement.jsx'), 'utf8');
const css = await fs.readFile(path.join(root, 'src/views/TaskManagement/TaskManagement.css'), 'utf8');

test('currently assigned employee remains visible as read-only context', () => {
  assert.match(modal, /currentlyAssignedEmployee = reassignTask\?\.assigned_employee_id/);
  assert.match(modal, /Current employee/);
  assert.match(modal, /Currently assigned to this task/);
  assert.match(css, /\.reassign-current-assignee\s*\{/);
});
test('single active employee already assigned is not presented as a missing record', () => {
  assert.match(modal, /onlyCurrentEmployeeIsActive/);
  assert.match(modal, /Your only active employee is already assigned/);
  assert.match(modal, /Nothing needs to be changed unless you want a different employee/);
  assert.match(page, /Number\(employee\.id\) !== Number\(reassignTask\.assigned_employee_id\)/);
});
test('employees lacking portal access explain why they cannot be selected', () => {
  assert.match(modal, /Cannot assign: \$\{candidate\.employee\.account_issue/);
  assert.match(modal, /disabled=\{!candidate\.employee\.portal_assignment_ready\}/);
  assert.match(modal, /Retry employees/);
});
