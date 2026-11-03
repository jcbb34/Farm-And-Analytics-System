import { httpClient } from "./httpClient.js";

const AUDIT_CACHE_KEY = "joross-audit-logs-v2";
const UPDATE_EVENT = "joross:farm-intelligence-updated";

function parseStoredJson(key, fallback) {
    try {
        const value = localStorage.getItem(key);
        return value ? JSON.parse(value) : fallback;
    } catch {
        return fallback;
    }
}

function cacheAuditLogs(value) {
    try {
        localStorage.setItem(AUDIT_CACHE_KEY, JSON.stringify(value));
    } catch {
        // The server remains authoritative even when browser storage is full
        // or unavailable (for example, strict private browsing settings).
    }
    return value;
}

function normalizeServerEvent(record = {}) {
    return {
        id: `server-${record.id}`,
        serverId: record.id,
        timestamp: record.createdAt ?? record.created_at ?? new Date().toISOString(),
        action: record.action || "Updated record",
        title: record.action || "Record updated",
        module: record.module || "System",
        recordName: record.recordName ?? record.record_name ?? "",
        entityId: record.entityId ?? record.entity_id ?? "",
        details: record.details || "",
        icon: record.icon || "history",
        user: record.user ?? record.actorName ?? record.actor_name ?? "Joross Farm User",
    };
}

async function postServerEvent(payload) {
    try {
        const saved = await httpClient.post("/audit-logs", payload);
        window.dispatchEvent(
            new CustomEvent(UPDATE_EVENT, {
                detail: { eventType: payload.event_type, saved },
            })
        );
        return saved;
    } catch (error) {
        // Do not manufacture a local "successful" audit record when the
        // server rejected or could not persist the event.
        console.warn("Audit event could not be saved to the server:", error);
        return null;
    }
}

export async function loadAuditLogsFromServer() {
    const records = await httpClient.get(
        "/audit-logs",
        { query: { event_type: "audit", limit: 500 } }
    );
    const normalized = (records || []).map(normalizeServerEvent);
    cacheAuditLogs(normalized);
    return normalized;
}

export function getAuditLogs() {
    return parseStoredJson(AUDIT_CACHE_KEY, []);
}

export function logAudit({
    action,
    module = "System",
    recordName = "",
    entityId = "",
    details = "",
}) {
    const entry = {
        timestamp: new Date().toISOString(),
        action: action || "Updated record",
        module,
        recordName,
        entityId,
        details,
    };

    void postServerEvent({
        event_type: "audit",
        action: entry.action,
        module: entry.module,
        record_name: entry.recordName || null,
        entity_id: String(entry.entityId || "") || null,
        details: entry.details || null,
        icon: "fact_check",
    });

    return entry;
}

export function addTimelineEntry({
    module,
    recordName,
    entityId = "",
    title,
    details = "",
    icon = "history",
}) {
    const entry = {
        timestamp: new Date().toISOString(),
        module: module || "System",
        recordName: recordName || "Record",
        entityId,
        title: title || "Record updated",
        details,
        icon,
    };

    void postServerEvent({
        event_type: "timeline",
        action: entry.title,
        module: entry.module,
        record_name: entry.recordName || null,
        entity_id: String(entry.entityId || "") || null,
        details: entry.details || null,
        icon: entry.icon || "history",
    });

    return entry;
}

export { UPDATE_EVENT };
