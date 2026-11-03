import { httpClient } from "./httpClient.js";

async function change(path, payload, method = "post") {
    const result = await httpClient[method](`/farm-events${path}`, payload);
    if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("joross:farm-data-updated", { detail: { sourceModule: "Workforce" } }));
        window.dispatchEvent(new CustomEvent("joross:activities-updated"));
    }
    return result;
}
export const farmEventService = Object.freeze({
    list: async (dateFrom, dateTo) => { const rows = await httpClient.get("/farm-events", { query: { date_from: dateFrom, date_to: dateTo }, cache: "no-store" }); return Array.isArray(rows) ? rows : []; },
    get: (id) => httpClient.get(`/farm-events/${id}`, { cache: "no-store" }),
    create: (payload) => change("", payload),
    update: (id, payload) => change(`/${id}`, payload, "put"),
    preview: (id) => httpClient.get(`/farm-events/${id}/preview`, { cache: "no-store" }),
    decide: (id, action, payload) => change(`/${id}/${action}`, payload),
    checklist: (id, payload) => change(`/${id}/checklist`, payload),
    acknowledge: (id, noticeVersion) => change(`/${id}/acknowledge`, { notice_version: noticeVersion }),
    report: (id, payload) => change(`/${id}/reports`, payload),
    tasks: (id, offset = 0) => httpClient.get(`/farm-events/${id}/tasks`, { query: { offset, limit: 25 }, cache: "no-store" }),
    review: (id, holdId, payload) => change(`/${id}/tasks/${holdId}/review`, payload),
});
