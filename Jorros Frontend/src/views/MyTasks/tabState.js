export const DEFAULT_MY_TASKS_TAB = "tasks";
export const MY_TASKS_TAB_IDS = Object.freeze(["tasks", "schedule", "leave"]);

export function normalizeMyTasksTab(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return MY_TASKS_TAB_IDS.includes(normalized) ? normalized : DEFAULT_MY_TASKS_TAB;
}

export function tabFromSearch(search = "") {
    const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
    return normalizeMyTasksTab(params.get("tab"));
}

export function searchWithMyTasksTab(search = "", tab = DEFAULT_MY_TASKS_TAB) {
    const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
    params.set("tab", normalizeMyTasksTab(tab));
    return `?${params.toString()}`;
}
