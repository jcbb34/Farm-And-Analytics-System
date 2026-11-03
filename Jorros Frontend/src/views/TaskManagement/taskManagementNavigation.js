const TAB_ALIASES = Object.freeze({
    tasks: "tasks",
    employees: "employees",
    leave: "leave",
    "leave-requests": "leave",
    templates: "templates",
    "care-protocols": "templates",
    archives: "archives",
});

export function normalizeTaskManagementTab(value) {
    return TAB_ALIASES[String(value || "").toLowerCase()] || "tasks";
}

export function safeInternalReturnPath(value) {
    if (!value) return "";
    let decoded = String(value);
    try { decoded = decodeURIComponent(decoded); } catch {}
    if (!decoded.startsWith("/")) return "";
    if (decoded.startsWith("//") || decoded.includes("://") || decoded.includes("\\")) return "";
    const allowed = (
        decoded === "/staff-calendar"
        || decoded.startsWith("/staff-calendar?")
        || decoded.startsWith("/staff-calendar#")
        || decoded === "/dashboard"
        || decoded.startsWith("/dashboard?")
        || decoded.startsWith("/dashboard#")
        || decoded === "/crops"
        || decoded.startsWith("/crops?")
        || decoded.startsWith("/crops#")
    );
    if (!allowed) return "";
    return decoded;
}

export function parseTaskManagementNavigation(searchParams) {
    const get = (key) => searchParams?.get?.(key) || "";
    const assignmentState = get("assignmentState");
    const source = get("from");
    const action = get("action");
    const parsed = {
        tab: normalizeTaskManagementTab(get("tab")),
        taskId: /^\d+$/.test(get("taskId")) ? get("taskId") : "",
        employeeId: /^\d+$/.test(get("employeeId")) ? get("employeeId") : "",
        date: /^\d{4}-\d{2}-\d{2}$/.test(get("date")) ? get("date") : "",
        leaveRequestId: /^\d+$/.test(get("leaveRequestId")) ? get("leaveRequestId") : "",
        assignmentState: assignmentState === "needs-reassignment" ? "Needs Reassignment" : "All",
        fromStaffCalendar: source === "staff-calendar",
        returnTo: safeInternalReturnPath(get("returnTo")),
    };

    // Keep legacy Staff Calendar parser shape stable while exposing Dashboard-only
    // navigation metadata when those query parameters are actually present.
    if (source === "dashboard") parsed.fromDashboard = true;
    if (source === "crops") parsed.fromCrops = true;
    if (action === "assisted-submission") parsed.action = "assisted-submission";
    if (action === "work-schedule" && parsed.tab === "employees" && parsed.employeeId) {
        parsed.action = "work-schedule";
        parsed.scheduleDate = /^\d{4}-\d{2}-\d{2}$/.test(get("scheduleDate")) ? get("scheduleDate") : "";
    }
    return parsed;
}
