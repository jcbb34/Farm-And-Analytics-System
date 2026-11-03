const DB_NAME = "joross-shared-device-v1";
const DB_VERSION = 1;
const STORE_NAME = "task-submission-drafts";
const MAX_DRAFT_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function ensureIndexedDb() {
    if (typeof indexedDB === "undefined") {
        throw new Error("Offline task storage is unavailable in this browser.");
    }
}

function openDatabase() {
    ensureIndexedDb();
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = () => {
            const database = request.result;
            if (!database.objectStoreNames.contains(STORE_NAME)) {
                const store = database.createObjectStore(STORE_NAME, { keyPath: "id" });
                store.createIndex("ownerUserId", "ownerUserId", { unique: false });
                store.createIndex("updatedAt", "updatedAt", { unique: false });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error("Unable to open offline task storage."));
    });
}

function randomKey() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

export function offlineDraftId(ownerUserId, taskId) {
    return `${String(ownerUserId)}:${String(taskId)}`;
}

export function createOfflineSubmissionKey(ownerUserId, taskId) {
    return `shared-task:${String(ownerUserId)}:${String(taskId)}:${randomKey()}`.slice(0, 100);
}

export function coalesceQueuedDraft(existingDraft, candidateDraft) {
    if (!existingDraft) return { draft: candidateDraft, duplicate: false };
    if (["pending", "syncing", "conflict"].includes(existingDraft.status)) {
        return { draft: existingDraft, duplicate: true };
    }
    return { draft: candidateDraft, duplicate: false };
}

export function canAttemptSyncDraft(draft, online) {
    return Boolean(online && draft && ["pending", "conflict"].includes(draft.status));
}

export function shouldAutoSyncDraft(draft, online) {
    return Boolean(online && draft?.status === "pending");
}

function transactionPromise(database, mode, callback) {
    return new Promise((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, mode);
        const store = transaction.objectStore(STORE_NAME);
        let result;
        try {
            result = callback(store, transaction);
        } catch (error) {
            reject(error);
            return;
        }
        transaction.oncomplete = () => resolve(result);
        transaction.onerror = () => reject(transaction.error || new Error("Offline task storage failed."));
        transaction.onabort = () => reject(transaction.error || new Error("Offline task storage was cancelled."));
    });
}

function requestPromise(request) {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error("Offline task storage failed."));
    });
}

export async function listOfflineTaskDrafts(ownerUserId) {
    const database = await openDatabase();
    try {
        const transaction = database.transaction(STORE_NAME, "readonly");
        const index = transaction.objectStore(STORE_NAME).index("ownerUserId");
        const rows = await requestPromise(index.getAll(String(ownerUserId)));
        return (rows || []).sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)));
    } finally {
        database.close();
    }
}

export async function queueOfflineTaskDraft({
    ownerUserId,
    taskId,
    payload,
    evidenceFile = null,
    evidenceUrl = null,
    idempotencyKey = null,
}) {
    const database = await openDatabase();
    const id = offlineDraftId(ownerUserId, taskId);
    const now = new Date().toISOString();
    try {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        const existing = await requestPromise(store.get(id));
        const candidate = {
            id,
            ownerUserId: String(ownerUserId),
            taskId: Number(taskId),
            payload: { ...payload },
            evidenceBlob: evidenceFile || null,
            evidenceName: evidenceFile?.name || null,
            evidenceType: evidenceFile?.type || null,
            evidenceUrl: evidenceUrl || null,
            idempotencyKey: idempotencyKey || createOfflineSubmissionKey(ownerUserId, taskId),
            status: "pending",
            attempts: 0,
            errorMessage: null,
            createdAt: now,
            updatedAt: now,
        };
        const resolved = coalesceQueuedDraft(existing, candidate);
        if (!resolved.duplicate) store.put(resolved.draft);
        await new Promise((resolve, reject) => {
            transaction.oncomplete = resolve;
            transaction.onerror = () => reject(transaction.error || new Error("Unable to save offline task draft."));
            transaction.onabort = () => reject(transaction.error || new Error("Unable to save offline task draft."));
        });
        return resolved;
    } finally {
        database.close();
    }
}

export async function updateOfflineTaskDraft(id, changes) {
    const database = await openDatabase();
    try {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        const existing = await requestPromise(store.get(id));
        if (!existing) return null;
        const updated = { ...existing, ...changes, updatedAt: new Date().toISOString() };
        store.put(updated);
        await new Promise((resolve, reject) => {
            transaction.oncomplete = resolve;
            transaction.onerror = () => reject(transaction.error || new Error("Unable to update offline task draft."));
        });
        return updated;
    } finally {
        database.close();
    }
}

export async function removeOfflineTaskDraft(id) {
    const database = await openDatabase();
    try {
        await transactionPromise(database, "readwrite", (store) => store.delete(id));
    } finally {
        database.close();
    }
}

export async function purgeExpiredOfflineTaskDrafts(now = Date.now()) {
    const database = await openDatabase();
    let removed = 0;
    try {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        const store = transaction.objectStore(STORE_NAME);
        const rows = await requestPromise(store.getAll());
        for (const row of rows || []) {
            const updated = new Date(row.updatedAt || row.createdAt || 0).getTime();
            if (!Number.isFinite(updated) || Number(now) - updated > MAX_DRAFT_AGE_MS) {
                store.delete(row.id);
                removed += 1;
            }
        }
        await new Promise((resolve, reject) => {
            transaction.oncomplete = resolve;
            transaction.onerror = () => reject(transaction.error || new Error("Unable to clean offline task drafts."));
        });
        return removed;
    } finally {
        database.close();
    }
}

export function isOfflineRetryableError(error) {
    return error?.code === "NETWORK_ERROR" || error?.code === "REQUEST_ABORTED" || Number(error?.status || 0) === 0;
}

export function isSyncConflictError(error) {
    return [400, 403, 404, 409].includes(Number(error?.status || 0));
}
