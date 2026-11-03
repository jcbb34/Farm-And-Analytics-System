import { createCrudService } from "../createCrudService.js";
import { httpClient } from "../httpClient.js";

export const cropsApi = createCrudService("/crops");
export const livestockApi = createCrudService("/livestock");
export const inventoryApi = createCrudService("/inventory");
export const alertsApi = createCrudService("/alerts");
export const reportsApi = createCrudService("/reports");
export const usersApi = createCrudService("/users");
export const tasksApi = createCrudService("/tasks");
export const notificationsApi = createCrudService("/notifications");

export const dashboardApi = Object.freeze({
    getSummary: (options = {}) =>
        httpClient.get("/dashboard/summary", options),

    getAnalytics: (query, options = {}) =>
        httpClient.get("/dashboard/analytics", {
            ...options,
            query,
        }),
});

export const settingsApi = Object.freeze({
    getProfile: (options = {}) =>
        httpClient.get("/settings/profile", options),

    updateProfile: (payload, options = {}) =>
        httpClient.put(
            "/settings/profile",
            payload,
            options
        ),

    getSystemSettings: (options = {}) =>
        httpClient.get("/settings/system", options),

    updateSystemSettings: (payload, options = {}) =>
        httpClient.put(
            "/settings/system",
            payload,
            options
        ),
});


export const farmIntelligenceApi = Object.freeze({
    getCropRecommendations: (query, options = {}) =>
        httpClient.get("/intelligence/crop-recommendations", {
            ...options,
            query,
        }),

    getProductionTargets: (query, options = {}) =>
        httpClient.get("/production-targets", {
            ...options,
            query,
        }),

    createProductionTarget: (payload, options = {}) =>
        httpClient.post(
            "/production-targets",
            payload,
            options
        ),

    getAuditLogs: (query, options = {}) =>
        httpClient.get("/audit-logs", {
            ...options,
            query,
        }),

    getRecordHistory: (query, options = {}) =>
        httpClient.get("/record-history", {
            ...options,
            query,
        }),

    createTask: (payload, options = {}) =>
        httpClient.post("/tasks", payload, options),

    uploadAttachmentMetadata: (payload, options = {}) =>
        httpClient.post(
            "/attachments",
            payload,
            options
        ),

    getBackupSchedule: (options = {}) =>
        httpClient.get("/backups/schedule", options),

    updateBackupSchedule: (payload, options = {}) =>
        httpClient.put(
            "/backups/schedule",
            payload,
            options
        ),

    createBackup: (options = {}) =>
        httpClient.post(
            "/backups",
            {},
            options
        ),

    previewImport: (payload, options = {}) =>
        httpClient.post(
            "/imports/preview",
            payload,
            options
        ),

    commitImport: (payload, options = {}) =>
        httpClient.post(
            "/imports/commit",
            payload,
            options
        ),
});
