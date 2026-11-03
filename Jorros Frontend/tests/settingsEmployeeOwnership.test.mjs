import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relativePath) => fs.readFile(path.join(projectRoot, relativePath), "utf8");

const userManagement = await read("src/components/UserManagement/UserManagement.jsx");
const settings = await read("src/views/Settings/Settings.jsx");
const taskManagement = (await Promise.all([
    "src/views/TaskManagement/TaskManagement.jsx",
    "src/views/TaskManagement/components/EmployeePanels.jsx",
    "src/views/TaskManagement/hooks/useTaskManagementData.js",
].map(read))).join("\n");

test("System Settings manages login accounts without duplicating employee profiles", () => {
    assert.match(settings, /label:\s*"User Management"/);
    assert.match(userManagement, /Create user accounts, assign roles, and control account access\./);

    assert.doesNotMatch(userManagement, /Employee Profiles/);
    assert.doesNotMatch(userManagement, /workforceService/);
    assert.doesNotMatch(userManagement, /getEmployees\(/);
    assert.doesNotMatch(userManagement, /createEmployee\(/);
    assert.doesNotMatch(userManagement, /updateEmployee\(/);
});

test("Task Management remains the employee-profile owner", () => {
    assert.match(taskManagement, /Employee Profiles/);
    assert.match(taskManagement, /Add Employee/);
    assert.match(taskManagement, /getEmployees\(/);
    assert.match(taskManagement, /createEmployee\(/);
    assert.match(taskManagement, /updateEmployee\(/);
});


test("System Settings hides Task Management Employee login accounts from System Users", () => {
    assert.match(userManagement, /function isTaskManagementEmployeeRole\(role\)/);
    assert.match(userManagement, /normalizeRole\(role\) === "employee"/);
    assert.match(userManagement, /const systemUsers =/);
    assert.match(userManagement, /!isTaskManagementEmployeeRole\([\s\S]*?user\.role/);
    assert.match(userManagement, /return systemUsers\.filter/);
    assert.match(userManagement, /total:\s*systemUsers\.length/);
    assert.match(userManagement, /\{systemUsers\.length\}\{" "\}[\s\S]*?total accounts/);
    assert.match(userManagement, /!isTaskManagementEmployeeRole\(roleName\)/);
});
