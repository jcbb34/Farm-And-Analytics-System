import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (relativePath) => fs.readFile(path.join(projectRoot, relativePath), "utf8");

const profileSource = await read("src/views/EmployeeProfile/EmployeeProfile.jsx");
const profileCss = await read("src/views/EmployeeProfile/EmployeeProfile.css");
const profileRoute = await read("src/app/(protected)/profile/page.jsx");
const sidebarSource = await read("src/components/Sidebar/Sidebar.jsx");
const headerSource = await read("src/components/AppHeaderActions/AppHeaderActions.jsx");

test("employee profile stays inside the authenticated employee navigation shell", () => {
    assert.match(profileRoute, /permission="workforce:submit"/);
    assert.match(profileSource, /import Sidebar from/);
    assert.match(profileSource, /import AppHeaderActions from/);
    assert.match(profileSource, /className="workforce-layout employee-profile-layout"/);
    assert.match(profileSource, /<Sidebar\s*\/>/);
    assert.match(profileSource, /<AppHeaderActions\s*\/>/);
    assert.match(sidebarSource, /name:\s*"My Profile"[\s\S]*?path:\s*"\/profile"/);
});

test("employee profile uses the normal Joross page header and themed card language", () => {
    assert.match(profileSource, /className="employee-profile-header"/);
    assert.match(profileSource, /Employee Information/);
    assert.match(profileSource, /employee-profile-overview-card/);
    assert.match(profileSource, /employee-profile-detail-grid/);
    assert.match(profileCss, /font-family:\s*"Inter", Arial, sans-serif/);
    assert.match(profileCss, /border-bottom:\s*2px solid var\(--theme-green/);
    assert.match(profileCss, /background:\s*var\(--theme-surface/);
    assert.match(profileCss, /color:\s*var\(--theme-text/);
});

test("employee profile keeps the sidebar on desktop and bottom navigation clearance on mobile", () => {
    assert.match(profileCss, /width:\s*calc\(100% - var\(--sidebar-collapsed-width, 80px\)\)/);
    assert.match(profileCss, /margin-left:\s*var\(--sidebar-collapsed-width, 80px\)/);
    assert.match(profileCss, /@media screen and \(max-width: 720px\)[\s\S]*?\.employee-profile-page[\s\S]*?width:\s*100%[\s\S]*?margin-left:\s*0/);
    assert.match(profileCss, /padding:\s*18px 14px calc\(96px \+ env\(safe-area-inset-bottom, 0px\)\)/);
});

test("task-only profile menu routes safely to My Profile instead of System Settings", () => {
    assert.match(headerSource, /import \{ isTaskOnlyUser \} from "\.\.\/\.\.\/utils\/accessControl\.js"/);
    assert.match(headerSource, /const taskOnlyMode = isTaskOnlyUser\(user\)/);
    assert.match(headerSource, /if \(taskOnlyMode\) \{[\s\S]*?requestNavigation\("\/profile"\)/);
    assert.match(headerSource, /\{!taskOnlyMode && \([\s\S]*?Account Settings/);
    assert.match(headerSource, /taskOnlyMode \? "My Profile" : "Profile Settings"/);
});
