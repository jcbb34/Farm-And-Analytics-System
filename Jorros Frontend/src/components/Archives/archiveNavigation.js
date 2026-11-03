export const archiveModules = {
    Crop: { path: "/crops", current: "Crop Records", archived: "Archived Crops", icon: "eco" },
    Livestock: { path: "/livestock", current: "Livestock Records", archived: "Archived Livestock", icon: "pets" },
    Inventory: { path: "/inventory", current: "Inventory Records", archived: "Archived Inventory", icon: "inventory_2" },
    Report: { path: "/reports", current: "Generated Reports", archived: "Archived Reports", icon: "description" },
    Employee: { path: "/task-management?tab=archives", icon: "badge" },
    Task: { path: "/task-management?tab=archives", icon: "task_alt" },
    User: { path: "/settings?section=archive", icon: "person" },
    Pen: { path: "/livestock", icon: "fence" },
};

export function archiveRecordPath(record, returnTo = "") {
    const config = archiveModules[record.module];
    if (!config || !Number.isInteger(Number(record.sourceId)) || Number(record.sourceId) < 1) return null;
    const [path, search = ""] = config.path.split("?");
    const query = new URLSearchParams(search);
    query.set("archive", "1"); query.set("archive_module", record.module); query.set("record", String(record.sourceId));
    if (returnTo.startsWith("/settings?") && !returnTo.startsWith("//")) query.set("return_to", returnTo);
    return `${path}?${query}`;
}

export function safeArchiveReturn(value) {
    return value?.startsWith("/settings?") && !value.startsWith("//") ? value : "";
}

