import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";


const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const srcRoot = path.join(projectRoot, "src");
const read = (relativePath) => fs.readFileSync(path.join(projectRoot, relativePath), "utf8");

const sourceFiles = [];
const pending = [srcRoot];
while (pending.length) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        const fullPath = path.join(current, entry.name);
        if (entry.isDirectory()) pending.push(fullPath);
        else if (/\.(js|jsx)$/.test(entry.name)) sourceFiles.push(fullPath);
    }
}


test("application source does not call the native window alert API", () => {
    const offenders = sourceFiles
        .filter((filePath) => /\bwindow\.alert\s*\(/.test(fs.readFileSync(filePath, "utf8")))
        .map((filePath) => path.relative(projectRoot, filePath));
    assert.deepEqual(offenders, []);
});


test("protected workforce pages declare permissions explicitly", () => {
    const taskPage = read("src/app/(protected)/task-management/page.jsx");
    const calendarPage = read("src/app/(protected)/staff-calendar/page.jsx");
    const protectedLayout = read("src/app/(protected)/layout.jsx");

    assert.match(taskPage, /permission="workforce:manage"/);
    assert.match(calendarPage, /permission=\{\["workforce:attendance","workforce:manage"\]\}/);
    assert.doesNotMatch(protectedLayout, /FrontendPermissionEnforcer/);
    assert.equal(
        fs.existsSync(path.join(srcRoot, "components/Auth/FrontendPermissionEnforcer.jsx")),
        false,
    );
});


test("stale backup source files are absent", () => {
    const stale = sourceFiles
        .filter((filePath) => /(?:\.BACKUP|\.bak|\.old|[._-]copy)\.(?:js|jsx)$/i.test(filePath))
        .map((filePath) => path.relative(projectRoot, filePath));
    assert.deepEqual(stale, []);
});
