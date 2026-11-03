import { ApiError, httpClient } from "./httpClient.js";
import { promptAction, notifyError } from "../context/NotificationContext.jsx";

export { archiveModules, archiveRecordPath, safeArchiveReturn } from "../components/Archives/archiveNavigation.js";

export function announceArchiveChange(module) {
    window.dispatchEvent(new CustomEvent("joross:modules-updated", { detail: { modules: ["archives", "settings", "tasks", "my_tasks", ({ Crop: "crops", Livestock: "livestock", Inventory: "inventory", Report: "reports", Employee: "employees", Task: "tasks", User: "users", Pen: "livestock" })[module]] } }));
}

async function archiveRequest(request) {
    try { return await request; }
    catch (error) {
        if (error.status === 404 && String(error.message).trim().toLowerCase() === "not found") {
            throw new ApiError("Archive service is unavailable. Apply the complete source update and restart the farm backend server.", { status: 404, code: "ARCHIVE_API_UNAVAILABLE" });
        }
        throw error; // Keep actual missing-record and permission errors intact.
    }
}

export const archiveService = {
    list: (query = {}) => archiveRequest(httpClient.get("/archives", { query, cache: "no-store" })),
    impact: (module, id) => archiveRequest(httpClient.get(`/archives/${module}/${id}/impact`, { cache: "no-store" })),
    async restore(record) { await archiveRequest(httpClient.post(`/archives/${record.module}/${record.sourceId}/restore`, {})); announceArchiveChange(record.module); },
    async remove(record) { await archiveRequest(httpClient.delete(`/archives/${record.module}/${record.sourceId}`)); announceArchiveChange(record.module); },
};

const pendingArchives = new Set();
export async function requestArchive(module, id, label = "this record") {
    const key = `${module}:${id}`;
    if (pendingArchives.has(key)) return null;
    pendingArchives.add(key);
    try {
        const impact = await archiveService.impact(module, id);
        if (impact.already_archived) return { id, archived: true };
        if (module === "Inventory" && Number(impact.quantity) !== 0) throw new Error("Inventory must have zero remaining stock before archiving. Record the authorized usage, transfer or adjustment first.");
        const tasks = impact.pending_tasks || [];
        const reason = await promptAction({ title: `Archive ${module} Record`, label: "Reason for archiving", required: true,
            message: `Archive ${label}?${tasks.length ? ` ${tasks.length} linked task(s): ${tasks.slice(0, 8).map((row) => `${row.code} (${row.status})`).join(", ")}${tasks.length > 8 ? ` and ${tasks.length - 8} more` : ""}. ${impact.policy}` : " Its history will remain available in Archived Records."}`,
            placeholder: "Explain why this record is being archived", confirmText: "Archive Record", cancelText: "Cancel" });
        if (reason === null || reason === undefined) return null;
        if (reason.trim().length > 500) throw new Error("Archive reason must be at most 500 characters.");
        const result = await archiveRequest(httpClient.post(`/archives/${module}/${id}/archive`, { reason: reason.trim() }));
        announceArchiveChange(module);
        return result;
    } catch (error) { notifyError(error?.message || "Unable to archive this record."); return null; }
    finally { pendingArchives.delete(key); }
}
