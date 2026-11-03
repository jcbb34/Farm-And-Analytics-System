import { httpClient } from "./httpClient.js";


function notifyWorkforceResourceChanged() {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new CustomEvent("joross:farm-data-updated", { detail: { sourceModule: "Workforce" } }));
    window.dispatchEvent(new CustomEvent("joross:activities-updated"));
    window.dispatchEvent(new CustomEvent("joross:alerts-updated"));
}

function query(options = {}) {
    return Object.fromEntries(
        Object.entries(options).filter(([, value]) => value !== "" && value !== null && value !== undefined)
    );
}

export const workforceService = Object.freeze({
    getMyProfile: () => httpClient.get("/workforce/me/profile"),
    getPositions: (includeInactive = false) =>
        httpClient.get("/workforce/positions", { query: { include_inactive: includeInactive } }),
    getEmployees: (includeArchived = false) =>
        httpClient.get("/workforce/employees", { query: { include_archived: includeArchived } }),
    getArchivedEmployees: () =>
        httpClient.get("/workforce/employees", { query: { archived_only: true } }),
    createEmployee: (payload) => httpClient.post("/workforce/employees", payload),
    updateEmployee: (id, payload) => httpClient.put(`/workforce/employees/${id}`, payload),
    setEmployeeStatus: (id, employmentStatus) =>
        httpClient.post(`/workforce/employees/${id}/status`, { employment_status: employmentStatus }),
    archiveEmployee: (id, reason = null) =>
        httpClient.post(`/workforce/employees/${id}/archive`, { reason }),
    restoreEmployee: (id) => httpClient.post(`/workforce/employees/${id}/restore`, {}),
    repairEmployeeAccountLinks: () => httpClient.post("/workforce/employees/account-links/repair", {}),
    getEmployeeWorkAssignments: (id, includeAvailable = false) =>
        httpClient.get(`/workforce/employees/${id}/work-assignments`, {
            query: { include_available: includeAvailable },
        }),
    getEmployeeWorkSchedule: (id, onDate = null) => httpClient.get(`/workforce/employees/${id}/work-schedule`, {
        query: query({ on_date: onDate }), cache: "no-store",
    }),
    updateEmployeeWorkSchedule: async (id, payload) => {
        const response = await httpClient.put(`/workforce/employees/${id}/work-schedule`, payload);
        notifyWorkforceResourceChanged();
        return response;
    },
    getAvailability: (dateFrom, dateTo, employeeId = null) => httpClient.get("/workforce/availability", {
        query: query({ date_from: dateFrom, date_to: dateTo, employee_id: employeeId }),
        cache: "no-store",
    }),

    getTasks: (options = {}) => httpClient.get("/workforce/tasks", { query: query(options), cache: "no-store" }),
    getTasksPage: (options = {}) => httpClient.get("/workforce/tasks/page", { query: query(options), cache: "no-store" }),
    getTaskManagementSummary: () => httpClient.get("/workforce/tasks/summary", { cache: "no-store" }),
    getTaskDetail: (id) => httpClient.get(`/workforce/tasks/${id}`, { cache: "no-store" }),
    getMyTasks: (viewOrIncludeCompleted = "active", { sharedDevice = false, signal = undefined, scope = undefined } = {}) => {
        const taskQuery = typeof viewOrIncludeCompleted === "boolean"
            ? { include_completed: viewOrIncludeCompleted }
            : { view: viewOrIncludeCompleted || "active" };
        if (scope && typeof viewOrIncludeCompleted !== "boolean") taskQuery.scope = scope;
        if (sharedDevice) taskQuery.shared_device = true;
        return httpClient.get("/workforce/my-tasks", { query: taskQuery, cache: "no-store", signal });
    },
    getMyTasksPage: (options = {}, { signal } = {}) =>
        httpClient.get("/workforce/my-tasks/page", { query: query(options), cache: "no-store", signal }),
    getMyTaskSummary: ({ signal = undefined } = {}) =>
        httpClient.get("/workforce/my-tasks/summary", { cache: "no-store", signal }),
    createTask: async (payload) => {
        const response = await httpClient.post("/workforce/tasks", payload);
        notifyWorkforceResourceChanged();
        return response;
    },
    scheduleResourceWork: async (payload) => {
        const response = await httpClient.post("/workforce/tasks/schedule-resource-work", payload);
        notifyWorkforceResourceChanged();
        return response;
    },
    updateAssignment: async (id, payload) => {
        const response = await httpClient.put(`/workforce/tasks/${id}/assignment`, payload);
        notifyWorkforceResourceChanged();
        return response;
    },
    startTask: (id, notes = null) => httpClient.post(`/workforce/tasks/${id}/start`, { notes }),
    uploadEvidencePhoto: (taskId, file) => {
        const formData = new FormData();
        formData.append("file", file);
        return httpClient.upload(`/workforce/tasks/${taskId}/evidence`, formData);
    },
    downloadEvidencePhoto: (evidenceUrl) => httpClient.download(evidenceUrl),
    submitTask: async (id, payload, idempotencyKey = null) => {
        const response = await httpClient.post(`/workforce/tasks/${id}/submit`, payload, {
            headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
        });
        notifyWorkforceResourceChanged();
        return response;
    },
    getTaskReviewReport: async (id) => {
        return httpClient.get(`/workforce/tasks/${id}/review-report`, { cache: "no-store" });
    },
    reviewTask: async (id, decision, feedback = null, options = {}) => {
        const response = await httpClient.post(`/workforce/tasks/${id}/review`, { decision, feedback, ...options });
        notifyWorkforceResourceChanged();
        return response;
    },
    voidTask: async (id, reason) => {
        const response = await httpClient.post(`/workforce/tasks/${id}/void`, { reason });
        notifyWorkforceResourceChanged();
        return response;
    },
    resolveTask: (id) => httpClient.post(`/workforce/tasks/${id}/resolve`, {}),

    getCalendarConfig: () => httpClient.get("/workforce/calendar/config", { cache: "no-store" }),
    getAttendance: (options = {}) => httpClient.get("/workforce/attendance", { query: query(options), cache: "no-store" }),
    saveAttendance: (payload) => httpClient.post("/workforce/attendance", payload),
    getMyAttendanceToday: () => httpClient.get("/workforce/my-attendance/today", { cache: "no-store" }),
    getMyAttendanceHistory: (dateFrom = null, dateTo = null) => httpClient.get("/workforce/my-attendance/history", { query: query({ date_from: dateFrom, date_to: dateTo }), cache: "no-store" }),
    checkIn: (notes = null) => httpClient.post("/workforce/my-attendance/check-in", { notes }),
    checkOut: (notes = null) => httpClient.post("/workforce/my-attendance/check-out", { notes }),
    assistedCheckIn: (employeeId, notes = null) => httpClient.post(`/workforce/attendance/${employeeId}/assisted-check-in`, { notes }),
    assistedCheckOut: (employeeId, notes = null) => httpClient.post(`/workforce/attendance/${employeeId}/assisted-check-out`, { notes }),
    setAttendanceStatus: (employeeId, workDate, status, notes = null) => httpClient.post(`/workforce/attendance/${employeeId}/${workDate}/status`, { status, notes }),
    correctAttendance: (employeeId, workDate, payload) => httpClient.put(`/workforce/attendance/${employeeId}/${workDate}/correction`, payload),
    getAttendanceSettings: () => httpClient.get("/workforce/attendance/settings", { cache: "no-store" }),
    updateAttendanceSettings: (payload) => httpClient.put("/workforce/attendance/settings", payload),
    getLeave: (employeeId = null, status = null) => httpClient.get("/workforce/leave", { query: query({ employee_id: employeeId, status }) }),
    getMyLeave: () => httpClient.get("/workforce/leave/my", { cache: "no-store" }),
    getLeaveReview: (id) => httpClient.get(`/workforce/leave/${id}/review`, { cache: "no-store" }),
    createLeave: (payload) => httpClient.post("/workforce/leave", payload),
    requestMyLeave: (payload) => httpClient.post("/workforce/leave/request", payload),
    decideLeave: (id, decisionOrPayload, notes = null) => {
        const payload = typeof decisionOrPayload === "string"
            ? { decision: decisionOrPayload, notes }
            : decisionOrPayload;
        return httpClient.post(`/workforce/leave/${id}/decision`, payload);
    },
    cancelLeave: (id, reason = null) => httpClient.post(`/workforce/leave/${id}/cancel`, { reason }),
    recalculateLeaveCoverage: () => httpClient.post("/workforce/leave/recalculate-coverage", {}),
    getShifts: (options = {}) => httpClient.get("/workforce/shifts", { query: query(options) }),
    createShift: (payload) => httpClient.post("/workforce/shifts", payload),
    updateShift: (id, payload) => httpClient.put(`/workforce/shifts/${id}`, payload),
    cancelShift: (id) => httpClient.post(`/workforce/shifts/${id}/cancel`, {}),
    getCalendar: (dateFrom, dateTo, employeeId = null) =>
        httpClient.get("/workforce/calendar", {
            query: query({ date_from: dateFrom, date_to: dateTo, employee_id: employeeId }),
            cache: "no-store",
        }),
    getMySchedule: (dateFrom, dateTo) =>
        httpClient.get("/workforce/my-schedule", {
            query: query({ date_from: dateFrom, date_to: dateTo }),
            cache: "no-store",
        }),

    getCareTemplates: (module = null, includeInactive = false, includeAllVersions = false) =>
        httpClient.get("/workforce/care-templates", {
            query: query({ module, include_inactive: includeInactive, include_all_versions: includeAllVersions }),
            cache: "no-store",
        }),
    createCareTemplate: (payload) => httpClient.post("/workforce/care-templates", payload),
    updateCareTemplate: (id, payload) => httpClient.put(`/workforce/care-templates/${id}`, payload),
    publishCareTemplate: (id, payload = {}) => httpClient.post(`/workforce/care-templates/${id}/publish`, payload),
    copyCareTemplate: (id, name = null) => httpClient.post(`/workforce/care-templates/${id}/copy`, { name }),
    deactivateCareTemplate: (id, futureTaskAction) => httpClient.post(`/workforce/care-templates/${id}/deactivate`, null, { query: query({ future_task_action: futureTaskAction }) }),
    importCareProtocols: (protocols) => httpClient.post("/workforce/care-templates/import", { protocols }),
    importCareProtocolsCsv: (formData) => httpClient.upload("/workforce/care-templates/import-csv", formData),
    matchCareProtocols: (module, targetId) => httpClient.get("/workforce/care-templates/match", { query: query({ module, target_id: targetId }), cache: "no-store" }),
    generateCareTasks: (payload) => httpClient.post("/workforce/care-templates/generate", payload),
});
