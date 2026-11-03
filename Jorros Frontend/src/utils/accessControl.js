export const TASK_ONLY_PERMISSION = "workforce:submit";
export const DASHBOARD_PERMISSION = "dashboard:view";
export const TASK_HOME_ROUTE = "/my-tasks";
export const DASHBOARD_HOME_ROUTE = "/dashboard";
export const PROFILE_ROUTE = "/profile";

const TASK_ONLY_ROLE_NAMES = new Set([
    "employee",
    "farm staff",
]);

const DASHBOARD_ROLE_NAMES = new Set([
    "admin",
    "administrator",
    "system administrator",
    "owner",
    "manager",
    "viewer",
]);

const ELEVATED_WORKFORCE_PERMISSIONS = new Set([
    "*",
    "workforce:manage",
    "workforce:review",
    "workforce:attendance",
]);

function normalizedRoleName(role) {
    return String(role || "").trim().toLowerCase();
}

function hasExplicitPermissionList(user = {}) {
    return Array.isArray(user?.permissions);
}

export function permissionsAreTaskOnly(permissionValues = []) {
    const permissions = new Set(Array.isArray(permissionValues) ? permissionValues : []);
    if (!permissions.has(TASK_ONLY_PERMISSION)) return false;
    for (const permission of ELEVATED_WORKFORCE_PERMISSIONS) {
        if (permissions.has(permission)) return false;
    }
    return true;
}

export function isTaskOnlyUser(user = {}) {
    if (hasExplicitPermissionList(user)) {
        return permissionsAreTaskOnly(user.permissions);
    }

    // Mock/legacy fallback only. Real API sessions carry backend permissions.
    return TASK_ONLY_ROLE_NAMES.has(normalizedRoleName(user?.role));
}

export function explicitUserHasPermission(user = {}, permission) {
    if (!permission) return true;
    const permissions = new Set(Array.isArray(user?.permissions) ? user.permissions : []);
    if (permissions.has("*")) return true;
    if (isTaskOnlyUser(user)) return permission === TASK_ONLY_PERMISSION;
    return permissions.has(permission);
}

export function canUseDashboard(user = {}) {
    if (hasExplicitPermissionList(user)) {
        return explicitUserHasPermission(user, DASHBOARD_PERMISSION);
    }

    return DASHBOARD_ROLE_NAMES.has(normalizedRoleName(user?.role));
}

export function canUseTaskWorkflow(user = {}) {
    if (hasExplicitPermissionList(user)) {
        return explicitUserHasPermission(user, TASK_ONLY_PERMISSION);
    }

    return TASK_ONLY_ROLE_NAMES.has(normalizedRoleName(user?.role));
}

/**
 * Return the safe authenticated landing page for the current account.
 * Backend-provided permissions are authoritative. Role names are used only
 * as a mock/legacy fallback when a permission list is unavailable.
 */
export function getHomeRoute(user = {}) {
    if (isTaskOnlyUser(user) || (!canUseDashboard(user) && canUseTaskWorkflow(user))) {
        return TASK_HOME_ROUTE;
    }

    if (canUseDashboard(user)) {
        return DASHBOARD_HOME_ROUTE;
    }

    // Existing non-task accounts are expected to carry dashboard:view. Keep
    // the historical dashboard fallback for an incomplete/legacy session,
    // but AccessDenied will never send task-only accounts back there.
    return DASHBOARD_HOME_ROUTE;
}

export function sanitizeRequestedDestination(value) {
    if (value === null || value === undefined || value === "") {
        return null;
    }

    const destination = String(value).trim();
    if (!destination.startsWith("/") || destination.startsWith("//")) {
        return null;
    }

    if (
        destination === "/" ||
        destination.startsWith("/login") ||
        destination.startsWith("/verify-2fa")
    ) {
        return null;
    }

    return destination;
}

function isTaskWorkflowDestination(destination) {
    return (
        destination === TASK_HOME_ROUTE ||
        destination.startsWith(`${TASK_HOME_ROUTE}?`) ||
        destination.startsWith(`${TASK_HOME_ROUTE}/`) ||
        destination === PROFILE_ROUTE ||
        destination.startsWith(`${PROFILE_ROUTE}?`) ||
        destination.startsWith(`${PROFILE_ROUTE}/`)
    );
}

/**
 * Resolve a post-login/2FA destination without allowing an employee/task-only
 * account to be bounced into a management page from a stale `from` value.
 */
export function resolvePostAuthDestination(user = {}, requested = null) {
    const homeRoute = getHomeRoute(user);
    const destination = sanitizeRequestedDestination(requested);

    if (!destination) {
        return homeRoute;
    }

    if (homeRoute === TASK_HOME_ROUTE) {
        return isTaskWorkflowDestination(destination)
            ? destination
            : TASK_HOME_ROUTE;
    }

    return destination;
}

export function getAccessDeniedFallback(user = {}) {
    const destination = getHomeRoute(user);

    if (destination === TASK_HOME_ROUTE) {
        return {
            destination: TASK_HOME_ROUTE,
            label: "Go to My Tasks",
        };
    }

    return {
        destination: DASHBOARD_HOME_ROUTE,
        label: "Return to Dashboard",
    };
}

// Backward-compatible alias for callers using the earlier redirect code.
// should use resolvePostAuthDestination/getHomeRoute directly.
export function taskOnlyDestination(user = {}, requested = null) {
    return resolvePostAuthDestination(user, requested);
}
