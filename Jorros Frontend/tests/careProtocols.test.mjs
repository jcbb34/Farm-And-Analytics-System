import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DRAFT_APPROVAL, emptyForm } from '../src/views/TaskManagement/careProtocolForm.js';

const manager = readFileSync(new URL('../src/views/TaskManagement/CareProtocolManager.jsx', import.meta.url), 'utf8');
const managerCss = readFileSync(new URL('../src/views/TaskManagement/CareProtocolManager.css', import.meta.url), 'utf8');
const taskManagement = [
  '../src/views/TaskManagement/TaskManagement.jsx',
  '../src/views/TaskManagement/components/TaskManagementTabs.jsx',
].map((file) => readFileSync(new URL(file, import.meta.url), 'utf8')).join('\n');
const service = readFileSync(new URL('../src/services/workforceService.js', import.meta.url), 'utf8');

test('Task Management exposes one admin-only Care Protocols manager', () => {
  assert.match(taskManagement, /canManageCareProtocols\s*=\s*hasPermission\("\*"\)/);
  assert.match(taskManagement, /\{ id: "templates", label: "Care Protocols", icon: "clinical_notes" \}/);
  assert.match(taskManagement, /<CareProtocolManager\s*\/>/);
  assert.doesNotMatch(taskManagement, /Show completed history/);
});

test('protocol editor captures version-safe targeting, source, approval and active-date metadata', () => {
  for (const label of ['Protocol Name', 'Exact Target Species / Crop', 'Production Purpose', 'Growth Stage', 'Effective From', 'Effective To', 'Approval Status', 'Last Reviewed', 'Source Title', 'Source URL', 'Citations']) {
    assert.ok(manager.includes(label), `missing ${label}`);
  }
  assert.equal(DRAFT_APPROVAL, 'Draft - Needs Veterinarian/Agriculturist Approval');
  assert.equal(emptyForm().approval_status, DRAFT_APPROVAL);
  assert.match(manager, /DRAFT_APPROVAL/);
});

test('protocol steps expose timing, recurrence, dose, generic resource and safety fields', () => {
  for (const label of ['Timing Basis', 'Repeat Every (days)', 'Occurrences', 'Planned Dose / Quantity', 'Dose Basis', 'Resource Product', 'Resource Category', 'Withdrawal Interval (days)', 'Pre-harvest Interval (days)', 'Safety Notes', 'Step Citation / Approval Record']) {
    assert.ok(manager.includes(label), `missing ${label}`);
  }
  assert.match(manager, /planting_date/);
  assert.match(manager, /birth_date/);
  assert.match(manager, /age_window/);
  assert.match(manager, /previous_step/);
  assert.doesNotMatch(manager, /inventory_item_id/);
});

test('published protocol workflow provides view, new version, copy, publish and deactivate actions', () => {
  for (const action of ['View', 'New Version', 'Copy', 'Publish', 'Deactivate']) {
    assert.ok(manager.includes(action), `missing action ${action}`);
  }
  assert.match(manager, /protocol\.status === "Draft"/);
  assert.match(manager, /protocol\.status !== "Draft" && protocol\.status !== "Inactive"/);
  assert.match(manager, /Published versions are immutable/);
});

test('protocol detail view exposes step evidence, review, resource, interval and citation information', () => {
  assert.match(manager, /aria-expanded=/);
  assert.match(manager, /protocol details/);
  assert.match(manager, /Evidence:/);
  assert.match(manager, /Review:/);
  assert.match(manager, /Resource:/);
  assert.match(manager, /Intervals:/);
  assert.match(manager, /Citation:/);
});

test('protocol import and matching/versioning services use the existing care-template API family', () => {
  for (const path of ['/workforce/care-templates/import', '/workforce/care-templates/import-csv', '/workforce/care-templates/match', '/workforce/care-templates/generate']) {
    assert.ok(service.includes(path), `missing service path ${path}`);
  }
  assert.match(service, /include_all_versions/);
  assert.match(service, /publishCareTemplate/);
  assert.match(service, /copyCareTemplate/);
});

test('Care Protocols layout remains responsive and uses the shared workforce design system', () => {
  assert.match(managerCss, /grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(managerCss, /@media\s*\(max-width:\s*1100px\)/);
  assert.match(managerCss, /@media\s*\(max-width:\s*640px\)/);
  assert.match(managerCss, /var\(--workforce-green/);
  assert.match(managerCss, /care-protocol-detail-grid/);
});
