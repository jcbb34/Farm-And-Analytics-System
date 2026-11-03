"use client";

import { FarmEventNotices } from "../FarmEvents/FarmEvents.jsx";
import { MonitoringObservationFields, initialObservation, observationPayload, validateObservation } from "../Monitoring/Monitoring.jsx";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { workforceService } from "../../services/workforceService.js";
import {
    canAttemptSyncDraft,
    createOfflineSubmissionKey,
    isOfflineRetryableError,
    isSyncConflictError,
    listOfflineTaskDrafts,
    purgeExpiredOfflineTaskDrafts,
    queueOfflineTaskDraft,
    removeOfflineTaskDraft,
    shouldAutoSyncDraft,
    updateOfflineTaskDraft,
} from "../../services/offlineTaskQueue.js";
import {
    SHARED_DEVICE_INACTIVITY_MS,
    SHARED_DEVICE_LANGUAGE_KEY,
    SHARED_DEVICE_TRANSLATIONS,
    normalizeSharedLanguage,
    sharedDeviceTasksForToday,
} from "../../views/MyTasks/sharedDeviceMode.js";
import { useNotification } from "../../context/NotificationContext.jsx";
import "./SharedDeviceTasks.css";

const MAX_EVIDENCE_BYTES = 6 * 1024 * 1024;

function formatTaskTime(task) {
    const time = String(task?.start_time || "").slice(0, 5);
    return time || "No set time";
}

function statusLabel(task, todayKey, t) {
    if (task?.work_suspended) return "Held — Owner/Admin review";
    if (task?.status === "Returned") return t.attention;
    if (String(task?.activity_date || "") < String(todayKey || "")) return t.overdue;
    if (task?.status === "In Progress") return t.inProgress;
    return t.dueToday;
}

function rebuildEvidenceFile(draft) {
    if (!draft?.evidenceBlob) return null;
    if (typeof File !== "undefined" && draft.evidenceBlob instanceof File) return draft.evidenceBlob;
    if (typeof File !== "undefined") {
        return new File(
            [draft.evidenceBlob],
            draft.evidenceName || "task-evidence.jpg",
            { type: draft.evidenceType || draft.evidenceBlob.type || "image/jpeg" },
        );
    }
    return draft.evidenceBlob;
}

export default function SharedDeviceTasks({
    tasks,
    loading,
    error,
    todayKey,
    user,
    onRefresh,
    onTaskUpdated,
    onExit,
    onLock,
}) {
    const notification = useNotification();
    const [language, setLanguage] = useState(() => {
        if (typeof window === "undefined") return "en";
        return normalizeSharedLanguage(localStorage.getItem(SHARED_DEVICE_LANGUAGE_KEY));
    });
    const [online, setOnline] = useState(() => typeof navigator === "undefined" ? true : navigator.onLine);
    const [selectedTaskId, setSelectedTaskId] = useState(null);
    const [form, setForm] = useState({ actual_quantity: "", actual_unit: "", worker_notes: "", problem_report: "" });
    const [evidenceFile, setEvidenceFile] = useState(null);
    const [startingId, setStartingId] = useState(null);
    const [submitting, setSubmitting] = useState(false);
    const [queueRows, setQueueRows] = useState([]);
    const [successState, setSuccessState] = useState(null);
    const [listening, setListening] = useState(false);
    const [locking, setLocking] = useState(false);
    const submissionKeyRef = useRef("");
    const syncingRef = useRef(new Set());
    const inactivityTimerRef = useRef(null);

    const t = SHARED_DEVICE_TRANSLATIONS[language];
    const ownerUserId = user?.id == null ? "" : String(user.id);
    const visibleTasks = useMemo(() => sharedDeviceTasksForToday(tasks, todayKey), [tasks, todayKey]);
    const selectedTask = useMemo(
        () => visibleTasks.find((task) => Number(task.id) === Number(selectedTaskId)) || null,
        [visibleTasks, selectedTaskId],
    );
    const queueByTask = useMemo(() => new Map(queueRows.map((row) => [Number(row.taskId), row])), [queueRows]);

    const refreshQueue = useCallback(async () => {
        if (!ownerUserId) return [];
        try {
            const rows = await listOfflineTaskDrafts(ownerUserId);
            setQueueRows(rows);
            return rows;
        } catch {
            setQueueRows([]);
            return [];
        }
    }, [ownerUserId]);

    useEffect(() => {
        if (!ownerUserId) return;
        purgeExpiredOfflineTaskDrafts().catch(() => {}).finally(() => refreshQueue());
    }, [ownerUserId, refreshQueue]);

    useEffect(() => {
        const updateStatus = () => setOnline(navigator.onLine);
        window.addEventListener("online", updateStatus);
        window.addEventListener("offline", updateStatus);
        return () => {
            window.removeEventListener("online", updateStatus);
            window.removeEventListener("offline", updateStatus);
        };
    }, []);

    useEffect(() => {
        const resetInactivity = () => {
            if (inactivityTimerRef.current) window.clearTimeout(inactivityTimerRef.current);
            inactivityTimerRef.current = window.setTimeout(async () => {
                setLocking(true);
                try {
                    await onLock?.("inactivity");
                } finally {
                    setLocking(false);
                }
            }, SHARED_DEVICE_INACTIVITY_MS);
        };
        const events = ["pointerdown", "keydown", "touchstart"];
        events.forEach((name) => window.addEventListener(name, resetInactivity, { passive: true }));
        resetInactivity();
        return () => {
            if (inactivityTimerRef.current) window.clearTimeout(inactivityTimerRef.current);
            events.forEach((name) => window.removeEventListener(name, resetInactivity));
        };
    }, [onLock]);

    useEffect(() => () => {
        if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
    }, []);

    const changeLanguage = (nextLanguage) => {
        const normalized = normalizeSharedLanguage(nextLanguage);
        setLanguage(normalized);
        localStorage.setItem(SHARED_DEVICE_LANGUAGE_KEY, normalized);
    };

    const openTask = (task) => {
        setSuccessState(null);
        setSelectedTaskId(task.id);
        setEvidenceFile(null);
        const previous = task.latest_submission || null;
        setForm({
            monitoring: previous?.monitoring || initialObservation(task.monitoring_context),
            actual_quantity: previous?.actual_quantity != null
                ? String(previous.actual_quantity)
                : task.resource_required && task.planned_quantity != null
                    ? String(task.planned_quantity)
                    : "",
            actual_unit: previous?.actual_unit
                || (task.resource_required ? (task.planned_inventory_unit || task.planned_unit || "") : (task.planned_unit || "")),
            worker_notes: previous?.worker_notes || "",
            problem_report: previous?.problem_report || "",
        });
        submissionKeyRef.current = createOfflineSubmissionKey(ownerUserId, task.id);
        window.scrollTo({ top: 0, behavior: "smooth" });
    };

    const closeTask = () => {
        setSelectedTaskId(null);
        setEvidenceFile(null);
        submissionKeyRef.current = "";
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        setListening(false);
    };

    const startTask = async (task) => {
        if (task?.work_suspended) { notification.warning("This work is held for Owner/Admin review.", t.modeTitle); return; }
        if (String(task?.activity_date || "") > String(todayKey || "")) {
            notification.warning(t.upcomingLocked, t.modeTitle);
            return;
        }
        if (!online) {
            notification.warning(t.startOnline, t.offline);
            return;
        }
        if (startingId) return;
        setStartingId(task.id);
        try {
            const updated = await workforceService.startTask(task.id);
            onTaskUpdated?.(updated);
            await onRefresh?.();
            notification.success("Task started.", t.modeTitle);
        } catch (startError) {
            notification.error(startError?.message || "Unable to start task.", t.modeTitle);
        } finally {
            setStartingId(null);
        }
    };

    const speakInstructions = () => {
        if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") return;
        if (listening) {
            window.speechSynthesis.cancel();
            setListening(false);
            return;
        }
        const text = selectedTask?.instructions || selectedTask?.description || selectedTask?.name || "";
        if (!text) return;
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = language === "fil" ? "fil-PH" : "en-PH";
        utterance.rate = 0.92;
        utterance.onend = () => setListening(false);
        utterance.onerror = () => setListening(false);
        setListening(true);
        window.speechSynthesis.speak(utterance);
    };

    const handleEvidenceFile = (event) => {
        const file = event.target.files?.[0] || null;
        event.target.value = "";
        if (!file) return;
        if (!String(file.type || "").startsWith("image/")) {
            notification.error("Select a JPG, PNG, or WEBP photo.", t.evidencePhoto);
            return;
        }
        if (file.size > MAX_EVIDENCE_BYTES) {
            notification.error("Evidence photo must be 6 MB or smaller.", t.evidencePhoto);
            return;
        }
        setEvidenceFile(file);
    };

    const submitSharedWork = async (event) => {
        event.preventDefault();
        const task = selectedTask;
        if (!task || submitting) return;
        if (task.work_suspended) { notification.warning("This work is held for Owner/Admin review.", t.modeTitle); return; }
        if (String(task?.activity_date || "") > String(todayKey || "")) {
            notification.warning(t.upcomingLocked, t.modeTitle);
            return;
        }
        if (task.status !== "In Progress") {
            notification.warning(t.startFirst, t.modeTitle);
            return;
        }
        if (task.resource_required && !task.resource_linked) {
            notification.error(t.resourceNeeded, t.modeTitle);
            return;
        }
        if (task.resource_required && (!(Number(form.actual_quantity) > 0) || !form.actual_unit)) {
            notification.error(t.quantityHelp, t.actualQuantity);
            return;
        }
        if (task.requires_evidence && !evidenceFile) {
            notification.error(t.photoRequired, t.evidencePhoto);
            return;
        }

        const monitoringError = validateObservation(form.monitoring, task.monitoring_context);
        if (monitoringError) { notification.error(monitoringError, t.modeTitle); return; }
        const payload = {
            monitoring: observationPayload(form.monitoring, task.monitoring_context),
            actual_quantity: form.actual_quantity === "" ? null : Number(form.actual_quantity),
            actual_unit: form.actual_unit || null,
            evidence_url: null,
            worker_notes: String(form.worker_notes || "").trim() || null,
            problem_report: String(form.problem_report || "").trim() || null,
        };
        const key = submissionKeyRef.current || createOfflineSubmissionKey(ownerUserId, task.id);
        submissionKeyRef.current = key;

        setSubmitting(true);
        try {
            const queued = await queueOfflineTaskDraft({
                ownerUserId,
                taskId: task.id,
                payload,
                evidenceFile,
                idempotencyKey: key,
            });
            await refreshQueue();

            if (!online) {
                setSuccessState({ type: "queued", title: t.queuedTitle, message: t.queuedMessage });
                closeTask();
                return;
            }

            const synced = await syncOneDraft(queued.draft);
            if (synced) {
                setSuccessState({ type: "success", title: t.successTitle, message: t.successMessage });
                closeTask();
                notification.success(t.successMessage, t.successTitle);
                return;
            }

            const currentQueue = await listOfflineTaskDrafts(ownerUserId).catch(() => []);
            const currentDraft = currentQueue.find((row) => row.id === queued.draft.id);
            if (currentDraft?.status === "conflict") {
                notification.error(currentDraft.errorMessage || "This saved submission conflicts with the current task state.", t.conflict);
            } else {
                setSuccessState({ type: "queued", title: t.queuedTitle, message: t.queuedMessage });
            }
            closeTask();
        } catch (submitError) {
            notification.error(submitError?.message || "Unable to save this task submission.", t.modeTitle);
        } finally {
            setSubmitting(false);
        }
    };

    const syncOneDraft = useCallback(async (draft) => {
        if (!ownerUserId || !canAttemptSyncDraft(draft, navigator.onLine) || syncingRef.current.has(draft.id)) return false;
        syncingRef.current.add(draft.id);
        try {
            let working = await updateOfflineTaskDraft(draft.id, {
                status: "syncing",
                attempts: Number(draft.attempts || 0) + 1,
                errorMessage: null,
            }) || draft;
            let evidenceUrl = working.evidenceUrl || working.payload?.evidence_url || null;
            if (!evidenceUrl && working.evidenceBlob) {
                const file = rebuildEvidenceFile(working);
                const uploaded = await workforceService.uploadEvidencePhoto(working.taskId, file);
                evidenceUrl = uploaded?.evidence_url || null;
                working = await updateOfflineTaskDraft(working.id, {
                    evidenceUrl,
                    evidenceBlob: null,
                    evidenceName: null,
                    evidenceType: null,
                    payload: { ...working.payload, evidence_url: evidenceUrl },
                }) || working;
            }
            const finalPayload = { ...working.payload, evidence_url: evidenceUrl || working.payload?.evidence_url || null };
            const updated = await workforceService.submitTask(working.taskId, finalPayload, working.idempotencyKey);
            await removeOfflineTaskDraft(working.id);
            onTaskUpdated?.(updated);
            return true;
        } catch (syncError) {
            const status = isOfflineRetryableError(syncError) ? "pending" : "conflict";
            await updateOfflineTaskDraft(draft.id, {
                status: isSyncConflictError(syncError) ? "conflict" : status,
                errorMessage: syncError?.message || "Unable to synchronize this submission.",
            }).catch(() => {});
            return false;
        } finally {
            syncingRef.current.delete(draft.id);
            await refreshQueue();
        }
    }, [onTaskUpdated, ownerUserId, refreshQueue]);

    const syncPendingDrafts = useCallback(async () => {
        if (!navigator.onLine || !ownerUserId) return;
        const rows = await listOfflineTaskDrafts(ownerUserId).catch(() => []);
        let changed = false;
        for (const draft of rows) {
            if (!shouldAutoSyncDraft(draft, true)) continue;
            changed = (await syncOneDraft(draft)) || changed;
        }
        if (changed) await onRefresh?.();
    }, [onRefresh, ownerUserId, syncOneDraft]);

    useEffect(() => {
        if (!online) return;
        syncPendingDrafts().catch(() => {});
    }, [online, syncPendingDrafts]);

    const discardDraft = async (draft) => {
        await removeOfflineTaskDraft(draft.id);
        await refreshQueue();
    };

    const speechSupported = typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";

    if (locking) {
        return <main className="shared-device-lock-screen" role="status" aria-live="assertive" aria-busy="true">
            <span className="material-symbols-outlined" aria-hidden="true">lock</span>
            <strong>{t.locking}</strong>
        </main>;
    }

    return <main className="shared-device-page" aria-label="Shared Device employee task mode">
        <header className="shared-device-header">
            <div className="shared-device-brand">
                <img src="/images/Jorros Logo 2.png" alt="JoRoss Farm" />
                <div>
                    <span className="shared-device-eyebrow">{t.modeTitle}</span>
                    <h1>{t.todayTasks}</h1>
                    <p>{t.shortHelp}</p>
                </div>
            </div>
            <div className="shared-device-header-actions">
                <span className={`shared-connectivity ${online ? "online" : "offline"}`} role="status" aria-live="polite">
                    <span className="material-symbols-outlined" aria-hidden="true">{online ? "wifi" : "wifi_off"}</span>
                    {online ? t.online : t.offline}
                </span>
                <div className="shared-language" role="group" aria-label="Language / Wika">
                    <button type="button" className={language === "en" ? "active" : ""} onClick={() => changeLanguage("en")}>{t.english}</button>
                    <button type="button" className={language === "fil" ? "active" : ""} onClick={() => changeLanguage("fil")}>{t.filipino}</button>
                </div>
                <button type="button" className="shared-header-button" onClick={onExit}>
                    <span className="material-symbols-outlined" aria-hidden="true">desktop_windows</span>{t.exitMode}
                </button>
                <button type="button" className="shared-header-button danger" disabled={locking} onClick={async () => { setLocking(true); try { await onLock?.("manual"); } finally { setLocking(false); } }}>
                    <span className="material-symbols-outlined" aria-hidden="true">lock</span>{t.lockDevice}
                </button>
            </div>
        </header>

        <section className="shared-device-status-row" aria-label="Employee and synchronization status">
            <div className="shared-current-user"><span className="material-symbols-outlined" aria-hidden="true">badge</span><span>{user?.fullName || user?.username || "Employee"}</span></div>
            {queueRows.length > 0 && <div className="shared-pending-summary" role="status">
                <span className="material-symbols-outlined" aria-hidden="true">sync_problem</span>
                <strong>{queueRows.length}</strong> {queueRows.length === 1 ? t.pendingCount : t.pendingCountPlural}
            </div>}
            
        </section>

        {!online && <div className="shared-offline-notice" role="status">
            <span className="material-symbols-outlined" aria-hidden="true">cloud_off</span>
            <span>{t.offlineHelp}</span>
        </div>}
        <FarmEventNotices date={todayKey} />
        {error && <div className="shared-error" role="alert">{error}</div>}
        {successState && !selectedTask && <div className={`shared-success ${successState.type}`} role="status" aria-live="polite">
            <span className="material-symbols-outlined" aria-hidden="true">{successState.type === "queued" ? "schedule_send" : "check_circle"}</span>
            <div><strong>{successState.title}</strong><span>{successState.message}</span></div>
        </div>}

        {!selectedTask ? <section className="shared-task-list" aria-label={t.todayTasks}>
            {loading ? <div className="shared-empty">{t.loading}</div> : visibleTasks.length === 0 ? <div className="shared-empty"><span className="material-symbols-outlined" aria-hidden="true">task_alt</span><strong>{t.noTasks}</strong></div> : visibleTasks.map((task) => {
                const draft = queueByTask.get(Number(task.id));
                const overdue = !task.work_suspended && String(task.activity_date || "") < String(todayKey || "");
                return <article className={`shared-task-card ${draft ? "has-draft" : ""}`} key={task.id}>
                    <div className="shared-task-card-main">
                        <div className="shared-task-card-title"><span className="material-symbols-outlined" aria-hidden="true">assignment</span><h2>{task.name}</h2></div>
                        <div className="shared-task-meta">
                            <span><span className="material-symbols-outlined" aria-hidden="true">schedule</span>{formatTaskTime(task)}</span>
                            <span><span className="material-symbols-outlined" aria-hidden="true">location_on</span>{task.location || "Farm"}</span>
                            <span className={overdue || task.status === "Returned" ? "attention" : ""}><span className="material-symbols-outlined" aria-hidden="true">{overdue ? "warning" : "today"}</span>{statusLabel(task, todayKey, t)}</span>
                        </div>
                        {task.work_suspended && <div className="shared-resource-warning">Held: {task.suspension_holds?.map((x) => x.title).join("; ")}. Owner/Admin must review or authorize essential duty.</div>}
                        {task.assignment_source === "Leave Coverage" && <div className="shared-coverage-note"><span className="material-symbols-outlined" aria-hidden="true">swap_horiz</span>{t.coverageTask}</div>}
                        {task.resource_required && !task.resource_linked && <div className="shared-resource-warning">{t.resourceNeeded}</div>}
                    </div>
                    <div className="shared-task-card-actions">
                        {draft ? <>
                            <span className={`shared-sync-badge ${draft.status}`}><span className="material-symbols-outlined" aria-hidden="true">{draft.status === "conflict" ? "error" : "sync"}</span>{draft.status === "conflict" ? t.conflict : draft.status === "syncing" ? t.syncing : t.pendingSync}</span>
                            {draft.errorMessage && <small role="alert">{draft.errorMessage}</small>}
                            <button type="button" className="shared-primary-button" onClick={() => syncOneDraft(draft)} disabled={!online || draft.status === "syncing"}><span className="material-symbols-outlined" aria-hidden="true">sync</span>{t.retrySync}</button>
                            <button type="button" className="shared-secondary-button" onClick={() => discardDraft(draft)} disabled={draft.status === "syncing"}><span className="material-symbols-outlined" aria-hidden="true">delete</span>{t.discardDraft}</button>
                        </> : <button type="button" className="shared-primary-button" onClick={() => openTask(task)}><span className="material-symbols-outlined" aria-hidden="true">open_in_new</span>{t.openTask}</button>}
                    </div>
                </article>;
            })}
        </section> : <section className="shared-task-detail" aria-label={`Task: ${selectedTask.name}`}>
            <button type="button" className="shared-back-button" onClick={closeTask}><span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>{t.back}</button>
            <article className="shared-detail-card">
                <div className="shared-detail-heading">
                    <div><span className="shared-detail-status">{statusLabel(selectedTask, todayKey, t)}</span><h2>{selectedTask.name}</h2><p>{formatTaskTime(selectedTask)} · {selectedTask.location || "Farm"} · {selectedTask.priority || "Normal"}</p></div>
                    {selectedTask.status !== "In Progress" && <button type="button" className="shared-start-button" disabled={selectedTask.work_suspended || !online || startingId === selectedTask.id} onClick={() => startTask(selectedTask)}><span className="material-symbols-outlined" aria-hidden="true">play_arrow</span>{startingId === selectedTask.id ? t.starting : t.start}</button>}
                </div>

                <section className="shared-instructions">
                    <div className="shared-section-title"><span className="material-symbols-outlined" aria-hidden="true">menu_book</span><h3>{t.instructions}</h3></div>
                    <p>{selectedTask.instructions || selectedTask.description || "Follow the farm manager's task instructions for this assignment."}</p>
                    {selectedTask.latest_submission?.review_status === "Returned" && selectedTask.latest_submission?.review_feedback && <div className="shared-correction-feedback" role="note">
                        <span className="material-symbols-outlined" aria-hidden="true">assignment_return</span>
                        <div><strong>{t.correctionNeeded}</strong><span>{t.managerFeedback}: {selectedTask.latest_submission.review_feedback}</span></div>
                    </div>}
                    <button type="button" className="shared-listen-button" onClick={speakInstructions} disabled={!speechSupported}><span className="material-symbols-outlined" aria-hidden="true">volume_up</span>{!speechSupported ? t.listenUnavailable : listening ? t.stopListening : t.listen}</button>
                </section>

                <form className="shared-submit-form" onSubmit={submitSharedWork}>
                    <MonitoringObservationFields context={selectedTask.monitoring_context} value={form.monitoring} onChange={(monitoring) => setForm({ ...form, monitoring })} disabled={submitting} />
                    <div className="shared-field-grid">
                        <label className="shared-field"><span>{t.actualQuantity}{selectedTask.resource_required ? " *" : ""}</span><input type="number" min="0" step="0.001" required={selectedTask.resource_required} inputMode="decimal" value={form.actual_quantity} onChange={(event) => setForm((current) => ({ ...current, actual_quantity: event.target.value }))} /><small>{t.quantityHelp}</small></label>
                        {form.actual_unit && <label className="shared-field"><span>{t.unit}</span><input value={form.actual_unit} readOnly /></label>}
                        <label className="shared-field full"><span>{t.evidencePhoto}{selectedTask.requires_evidence ? " *" : ""}</span><span className="shared-photo-picker"><span className="material-symbols-outlined" aria-hidden="true">photo_camera</span><strong>{evidenceFile ? t.replacePhoto : t.takePhoto}</strong><input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={handleEvidenceFile} /></span>{evidenceFile && <small className="shared-selected-file"><span className="material-symbols-outlined" aria-hidden="true">image</span>{t.selectedPhoto}: {evidenceFile.name}</small>}</label>
                        <label className="shared-field full"><span>{t.notes} <small>{t.optional}</small></span><textarea rows="3" value={form.worker_notes} onChange={(event) => setForm((current) => ({ ...current, worker_notes: event.target.value }))} /></label>
                        <label className="shared-field full"><span>{t.problem} <small>{t.optional}</small></span><textarea rows="3" value={form.problem_report} onChange={(event) => setForm((current) => ({ ...current, problem_report: event.target.value }))} /></label>
                    </div>
                    {selectedTask.resource_required && !selectedTask.resource_linked && <div className="shared-resource-warning">{t.resourceNeeded}</div>}
                    <button type="submit" className="shared-submit-button" disabled={selectedTask.work_suspended || submitting || selectedTask.status !== "In Progress" || (selectedTask.resource_required && !selectedTask.resource_linked)}><span className="material-symbols-outlined" aria-hidden="true">send</span>{submitting ? t.submitting : t.submit}</button>
                </form>
            </article>
        </section>}
    </main>;
}
