import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const accessControlPath = path.join(projectRoot, "src/utils/accessControl.js");
const accessControlSource = await fs.readFile(accessControlPath, "utf8");
const access = await import(
    `data:text/javascript;base64,${Buffer.from(accessControlSource).toString("base64")}`
);

const employee = {
    role: "Employee",
    permissions: ["workforce:submit"],
};
const farmStaff = {
    role: "Farm Staff",
    permissions: ["workforce:submit"],
};
const customTaskRole = {
    role: "Harvest Crew",
    permissions: ["workforce:submit"],
};
const manager = {
    role: "Manager",
    permissions: ["dashboard:view", "workforce:manage", "workforce:review"],
};
const administrator = {
    role: "System Administrator",
    permissions: ["*"],
};

test("employee login without a requested destination goes to My Tasks", () => {
    assert.equal(access.resolvePostAuthDestination(employee), "/my-tasks");
    assert.equal(access.resolvePostAuthDestination(farmStaff), "/my-tasks");
    assert.equal(access.resolvePostAuthDestination(customTaskRole), "/my-tasks");
});

test("employee login ignores an invalid dashboard destination", () => {
    assert.equal(
        access.resolvePostAuthDestination(employee, "/dashboard"),
        "/my-tasks"
    );
    assert.equal(
        access.resolvePostAuthDestination(employee, "/reports"),
        "/my-tasks"
    );
});

test("employee two-factor completion ignores a stored dashboard destination", () => {
    const storedTwoFactorDestination = "/dashboard";
    assert.equal(
        access.resolvePostAuthDestination(employee, storedTwoFactorDestination),
        "/my-tasks"
    );
});

test("authenticated employee opening root uses My Tasks as home", () => {
    assert.equal(access.getHomeRoute(employee), "/my-tasks");
    assert.equal(access.getHomeRoute(customTaskRole), "/my-tasks");
});

test("employee and Farm Staff Access Restricted fallback goes to My Tasks", () => {
    const expected = {
        destination: "/my-tasks",
        label: "Go to My Tasks",
    };
    assert.deepEqual(access.getAccessDeniedFallback(employee), expected);
    assert.deepEqual(access.getAccessDeniedFallback(farmStaff), expected);
});

test("Manager, Owner, Admin, Administrator, System Administrator, and dashboard-authorized roles use Dashboard", () => {
    const dashboardUsers = [
        manager,
        administrator,
        { role: "Owner", permissions: ["*"] },
        { role: "Admin", permissions: ["*"] },
        { role: "Administrator", permissions: ["*"] },
        { role: "Operations Lead", permissions: ["dashboard:view"] },
    ];

    for (const user of dashboardUsers) {
        assert.equal(access.getHomeRoute(user), "/dashboard");
        assert.equal(access.resolvePostAuthDestination(user), "/dashboard");
        assert.deepEqual(access.getAccessDeniedFallback(user), {
            destination: "/dashboard",
            label: "Return to Dashboard",
        });
    }
});

test("employee cannot satisfy dashboard permission", () => {
    assert.equal(access.explicitUserHasPermission(employee, "dashboard:view"), false);
    // Prompt 4 compatibility: a stale dashboard:view on a task-only permission
    // set must not expand an employee session into the management dashboard.
    assert.equal(
        access.explicitUserHasPermission(
            { role: "Employee", permissions: ["workforce:submit", "dashboard:view"] },
            "dashboard:view"
        ),
        false
    );
});

test("task-only redirects stabilize on My Tasks and cannot loop through Dashboard", () => {
    const deniedFallback = access.getAccessDeniedFallback(employee).destination;
    assert.notEqual(deniedFallback, "/dashboard");
    assert.equal(deniedFallback, "/my-tasks");

    let destination = "/dashboard";
    for (let attempt = 0; attempt < 5; attempt += 1) {
        destination = access.resolvePostAuthDestination(employee, destination);
    }
    assert.equal(destination, "/my-tasks");
    assert.equal(access.getAccessDeniedFallback(employee).destination, destination);
});

test("shared role-aware routing helper is used by all redirect entry points", async () => {
    const expectedUsage = new Map([
        ["src/app/page.jsx", "getHomeRoute"],
        ["src/views/Login/Login.jsx", "resolvePostAuthDestination"],
        ["src/views/TwoFactorVerify/TwoFactorVerify.jsx", "resolvePostAuthDestination"],
        ["src/components/Common/AccessDenied.jsx", "getAccessDeniedFallback"],
        ["src/components/Auth/PublicOnlyRoute.jsx", "getHomeRoute"],
    ]);

    for (const [relativePath, helperName] of expectedUsage) {
        const source = await fs.readFile(path.join(projectRoot, relativePath), "utf8");
        assert.match(source, new RegExp(`\\b${helperName}\\b`), `${relativePath} must use ${helperName}`);
    }
});

test("employee sidebar remains task-only plus basic profile without logout", async () => {
    const source = await fs.readFile(
        path.join(projectRoot, "src/components/Sidebar/Sidebar.jsx"),
        "utf8"
    );
    assert.match(source, /name:\s*"My Tasks"/);
    assert.match(source, /name:\s*"My Profile"/);
    assert.doesNotMatch(source, />Logout</);
    assert.doesNotMatch(source, /sidebar-logout/);
    assert.match(source, /permission:\s*"dashboard:view"/);
    assert.match(source, /if \(!hasPermission\(item\.permission\)\) return false/);
});

test("profile menu places logout directly below Dark Mode and preserves guarded sign-out", async () => {
    const header = await fs.readFile(
        path.join(projectRoot, "src/components/AppHeaderActions/AppHeaderActions.jsx"),
        "utf8"
    );
    const themeIndex = header.indexOf('className="app-header-theme-row"');
    const logoutIndex = header.indexOf('className="app-header-profile-action app-header-logout-action"');
    assert.ok(themeIndex >= 0, "Dark Mode row should remain in profile menu");
    assert.ok(logoutIndex > themeIndex, "Log Out should appear after Dark Mode");
    assert.match(header, /<strong>Log Out<\/strong>/);
    assert.match(header, /onClick=\{handleLogout\}/);
    assert.match(header, /confirmDiscard/);
    assert.match(header, /confirmAction\(\{/);
    assert.match(header, /await logout\(\)/);
});
