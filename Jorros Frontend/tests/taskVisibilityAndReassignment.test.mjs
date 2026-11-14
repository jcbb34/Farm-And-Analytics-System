import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {buildTaskManagementQuery} from '../src/views/TaskManagement/taskManagementQuery.js';

const root=path.resolve(fileURLToPath(new URL('..',import.meta.url)));
const read=(p)=>fs.readFile(path.join(root,p),'utf8');
const [page,panel,modals]=await Promise.all([
 'src/views/TaskManagement/TaskManagement.jsx',
 'src/views/TaskManagement/components/AssignmentsPanel.jsx',
 'src/views/TaskManagement/components/TaskManagementModals.jsx',
].map(read));

test('normal Tasks view does not hide future pending harvest tasks',()=>{
 assert.match(page,/navigation\.date \? "All" : "All Scheduled"/);
 assert.match(page,/setTaskScheduleFilter\("All Scheduled"\)/);
 assert.match(page,/taskScheduleFilter === "All Scheduled"/);
 const all=buildTaskManagementQuery({taskScheduleFilter:'All Scheduled',todayKey:'2026-11-14'});
 assert.deepEqual(all,{});
 const attention=buildTaskManagementQuery({taskScheduleFilter:'Actionable Now',todayKey:'2026-11-14'});
 assert.deepEqual(attention,{actionable_only:true});
});
test('empty tasks can be retried or shown without active filters',()=>{
 assert.match(page,/onRetryLoad=\{load\}/);
 assert.match(page,/onShowAllScheduled=\{clearTaskFilters\}/);
 assert.match(panel,/Could not load tasks/);
 assert.match(panel,/View All Scheduled Tasks/);
 assert.match(panel,/Retry loading tasks/);
 assert.match(panel,/!loading && !error && tasks\.length < taskTotal/);
});
test('reassignment distinguishes employee loading, fetch errors, searches and no alternative',()=>{
 assert.match(page,/employees, employeesLoading, employeesError, loadEmployees/);
 assert.match(page,/Number\(employee\.id\) !== Number\(reassignTask\.assigned_employee_id\)/);
 assert.match(modals,/Loading employees/);
 assert.match(modals,/Employee list could not load/);
 assert.match(modals,/No alternative employee available/);
 assert.match(modals,/Clear search/);
 assert.match(modals,/Retry employees/);
});
