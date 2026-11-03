"use client";

import { useEffect, useState } from "react";

import {
    notifyError,
    notifySuccess,
    notifyWarning,
    confirmAction,
} from "../../../context/NotificationContext.jsx";

import {
    UPDATE_EVENT,
    addTimelineEntry,
    deleteAttachment,
    getAttachments,
    getTimelineEntries,
    loadTimelineEntriesFromServer,
    logAudit,
    saveAttachment,
} from "../../../services/farmIntelligenceService.js";

// Format timeline dates for display
function formatDateTime(value) {
    if (!value) {
        return "--";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return date.toLocaleString("en-PH", {
        dateStyle: "medium",
        timeStyle: "short",
    });
}

function getTodayKey() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

// Record history and attachments
function RecordsPanel({ canEdit }) {
    const [timeline, setTimeline] =
        useState(getTimelineEntries);
    const [attachments, setAttachments] =
        useState(getAttachments);

    const [historyForm, setHistoryForm] =
        useState({
            module: "Crop",
            recordName: "",
            title: "",
            details: "",
            date: getTodayKey(),
        });

    const [attachmentForm, setAttachmentForm] =
        useState({
            module: "Crop",
            recordName: "",
            entityId: "",
            caption: "",
        });

    const [selectedFile, setSelectedFile] =
        useState(null);

    const refresh = () => {
        setTimeline(
            getTimelineEntries()
        );
        setAttachments(
            getAttachments()
        );
    };

    useEffect(() => {
        let cancelled = false;

        loadTimelineEntriesFromServer()
            .then((entries) => {
                if (!cancelled) {
                    setTimeline(entries);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setTimeline(getTimelineEntries());
                }
            });

        const handleRefresh = () => {
            loadTimelineEntriesFromServer()
                .then((entries) => {
                    if (!cancelled) {
                        setTimeline(entries);
                    }
                })
                .catch(() => {
                    if (!cancelled) {
                        setTimeline(getTimelineEntries());
                    }
                });
        };

        window.addEventListener(UPDATE_EVENT, handleRefresh);

        return () => {
            cancelled = true;
            window.removeEventListener(UPDATE_EVENT, handleRefresh);
        };
    }, []);

    const handleHistoryChange = (event) => {
        const { name, value } =
            event.target;

        setHistoryForm((current) => ({
            ...current,
            [name]: value,
        }));
    };

    const handleAttachmentChange = (
        event
    ) => {
        const { name, value } =
            event.target;

        setAttachmentForm((current) => ({
            ...current,
            [name]: value,
        }));
    };

    const addManualHistory = (event) => {
        event.preventDefault();

        if (!canEdit) {
            return;
        }

        if (
            !historyForm.recordName.trim() ||
            !historyForm.title.trim()
        ) {
            notifyWarning(
                "Record name and history title are required."
            );
            return;
        }

        addTimelineEntry({
            module: historyForm.module,
            recordName:
                historyForm.recordName.trim(),
            title: historyForm.title.trim(),
            details:
                historyForm.details.trim(),
            timestamp: new Date(
                `${historyForm.date}T12:00:00`
            ).toISOString(),
            icon:
                historyForm.module === "Crop"
                    ? "grass"
                    : historyForm.module ===
                        "Livestock"
                      ? "pets"
                      : "history",
        });

        logAudit({
            action: "Added record history entry",
            module: historyForm.module,
            recordName:
                historyForm.recordName.trim(),
            details:
                historyForm.title.trim(),
        });

        setHistoryForm((current) => ({
            ...current,
            recordName: "",
            title: "",
            details: "",
        }));

        refresh();

        notifySuccess(
            "Record history entry added."
        );
    };

    const saveFile = async (event) => {
        event.preventDefault();

        if (!canEdit) {
            return;
        }

        if (
            !selectedFile ||
            !attachmentForm.recordName.trim()
        ) {
            notifyWarning(
                "Choose a file and enter the related record name."
            );
            return;
        }

        if (
            selectedFile.size >
            1.5 * 1024 * 1024
        ) {
            notifyWarning(
                "For the frontend demo, attachments must be 1.5 MB or smaller. The backend version can use normal file storage."
            );
            return;
        }

        const reader = new FileReader();

        reader.onload = () => {
            saveAttachment({
                module: attachmentForm.module,
                recordName:
                    attachmentForm.recordName.trim(),
                entityId:
                    attachmentForm.entityId.trim(),
                caption:
                    attachmentForm.caption.trim(),
                fileName: selectedFile.name,
                mimeType: selectedFile.type,
                size: selectedFile.size,
                dataUrl: reader.result,
            });

            setAttachmentForm((current) => ({
                ...current,
                recordName: "",
                entityId: "",
                caption: "",
            }));

            setSelectedFile(null);
            refresh();

            notifySuccess(
                "Photo or attachment added to the record."
            );
        };

        reader.onerror = () => {
            notifyError(
                "The selected file could not be read."
            );
        };

        reader.readAsDataURL(
            selectedFile
        );
    };

    const removeAttachment = async (
        attachment
    ) => {
        if (!canEdit) {
            return;
        }

        const confirmed =
            await confirmAction({
                title: "Remove Attachment",
                message:
                    `Remove ${attachment.fileName}?`,
                type: "warning",
                confirmText: "Remove",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        deleteAttachment(
            attachment.id
        );

        refresh();
    };

    return (
        <div className="fi-stack">
            <div className="fi-two-column">
                <section className="fi-card">
                    <div className="fi-section-heading">
                        <div>
                            <h3>
                                Add Record History
                            </h3>
                            <p>
                                Create a timeline of important crop,
                                livestock, inventory, and farm events.
                            </p>
                        </div>
                    </div>

                    <form
                        className="fi-form-grid single"
                        onSubmit={addManualHistory}
                    >
                        <label>
                            <span>Module</span>
                            <select
                                name="module"
                                value={historyForm.module}
                                onChange={handleHistoryChange}
                                disabled={!canEdit}
                            >
                                <option>Crop</option>
                                <option>Livestock</option>
                                <option>Inventory</option>
                                <option>Report</option>
                                <option>System</option>
                            </select>
                        </label>

                        <label>
                            <span>Record Name *</span>
                            <input
                                name="recordName"
                                value={
                                    historyForm.recordName
                                }
                                onChange={
                                    handleHistoryChange
                                }
                                disabled={!canEdit}
                            />
                        </label>

                        <label>
                            <span>History Title *</span>
                            <input
                                name="title"
                                value={historyForm.title}
                                onChange={
                                    handleHistoryChange
                                }
                                placeholder="Example: Fertilizer applied"
                                disabled={!canEdit}
                            />
                        </label>

                        <label>
                            <span>Date</span>
                            <input
                                type="date"
                                name="date"
                                value={historyForm.date}
                                onChange={
                                    handleHistoryChange
                                }
                                disabled={!canEdit}
                            />
                        </label>

                        <label className="full">
                            <span>Details</span>
                            <textarea
                                rows="4"
                                name="details"
                                value={
                                    historyForm.details
                                }
                                onChange={
                                    handleHistoryChange
                                }
                                disabled={!canEdit}
                            />
                        </label>

                        {canEdit && (
                            <div className="fi-form-actions">
                                <button
                                    type="submit"
                                    className="fi-primary-button"
                                >
                                    <span className="material-symbols-outlined">
                                        history
                                    </span>
                                    Add History
                                </button>
                            </div>
                        )}
                    </form>
                </section>

                <section className="fi-card">
                    <div className="fi-section-heading">
                        <div>
                            <h3>
                                Photo / Attachment Record
                            </h3>
                            <p>
                                Attach crop condition, pest, vaccination,
                                delivery, or other record evidence.
                            </p>
                        </div>
                    </div>

                    <form
                        className="fi-form-grid single"
                        onSubmit={saveFile}
                    >
                        <label>
                            <span>Module</span>
                            <select
                                name="module"
                                value={attachmentForm.module}
                                onChange={
                                    handleAttachmentChange
                                }
                                disabled={!canEdit}
                            >
                                <option>Crop</option>
                                <option>Livestock</option>
                                <option>Inventory</option>
                                <option>Report</option>
                            </select>
                        </label>

                        <label>
                            <span>Record Name *</span>
                            <input
                                name="recordName"
                                value={
                                    attachmentForm.recordName
                                }
                                onChange={
                                    handleAttachmentChange
                                }
                                disabled={!canEdit}
                            />
                        </label>

                        <label>
                            <span>Record ID</span>
                            <input
                                name="entityId"
                                value={
                                    attachmentForm.entityId
                                }
                                onChange={
                                    handleAttachmentChange
                                }
                                placeholder="Optional"
                                disabled={!canEdit}
                            />
                        </label>

                        <label>
                            <span>Caption</span>
                            <input
                                name="caption"
                                value={
                                    attachmentForm.caption
                                }
                                onChange={
                                    handleAttachmentChange
                                }
                                disabled={!canEdit}
                            />
                        </label>

                        <label className="full">
                            <span>File</span>
                            <input
                                type="file"
                                accept="image/*,.pdf"
                                onChange={(event) =>
                                    setSelectedFile(
                                        event.target
                                            .files?.[0] ||
                                            null
                                    )
                                }
                                disabled={!canEdit}
                            />
                        </label>

                        {canEdit && (
                            <div className="fi-form-actions">
                                <button
                                    type="submit"
                                    className="fi-primary-button"
                                >
                                    <span className="material-symbols-outlined">
                                        attach_file
                                    </span>
                                    Add Attachment
                                </button>
                            </div>
                        )}
                    </form>
                </section>
            </div>

            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>
                            Record Timeline
                        </h3>
                        <p>
                            Chronological history from farm records and
                            manual timeline entries.
                        </p>
                    </div>

                    <span className="fi-count-chip">
                        {timeline.length} entries
                    </span>
                </div>

                <div className="fi-timeline">
                    {timeline.map((item) => (
                        <article
                            key={item.id}
                            className="fi-timeline-item"
                        >
                            <span className="fi-timeline-icon">
                                <span className="material-symbols-outlined">
                                    {item.icon ||
                                        "history"}
                                </span>
                            </span>

                            <div>
                                <div className="fi-timeline-title">
                                    <strong>
                                        {item.title}
                                    </strong>
                                    <span>
                                        {formatDateTime(
                                            item.timestamp
                                        )}
                                    </span>
                                </div>

                                <p>
                                    <b>
                                        {item.module}
                                    </b>
                                    {" • "}
                                    {item.recordName}
                                </p>

                                {item.details && (
                                    <p>
                                        {item.details}
                                    </p>
                                )}

                                <small>
                                    By {item.user}
                                </small>
                            </div>
                        </article>
                    ))}
                </div>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>
                            Saved Attachments
                        </h3>
                        <p>
                            Frontend demo stores small files in browser
                            storage. The backend should store files outside
                            the SQL database and save only file metadata.
                        </p>
                    </div>

                    <span className="fi-count-chip">
                        {attachments.length} files
                    </span>
                </div>

                <div className="fi-attachment-grid">
                    {attachments.length === 0 ? (
                        <div className="fi-empty">
                            No attachments yet.
                        </div>
                    ) : (
                        attachments.map(
                            (attachment) => (
                                <article
                                    key={
                                        attachment.id
                                    }
                                    className="fi-attachment-card"
                                >
                                    {attachment.mimeType?.startsWith(
                                        "image/"
                                    ) ? (
                                        <img
                                            src={
                                                attachment.dataUrl
                                            }
                                            alt={
                                                attachment.caption ||
                                                attachment.fileName
                                            }
                                        />
                                    ) : (
                                        <div className="fi-file-preview">
                                            <span className="material-symbols-outlined">
                                                picture_as_pdf
                                            </span>
                                        </div>
                                    )}

                                    <div>
                                        <strong>
                                            {
                                                attachment.recordName
                                            }
                                        </strong>
                                        <p>
                                            {attachment.caption ||
                                                attachment.fileName}
                                        </p>
                                        <small>
                                            {
                                                attachment.module
                                            }
                                            {" • "}
                                            {formatDateTime(
                                                attachment.createdAt
                                            )}
                                        </small>
                                    </div>

                                    {canEdit && (
                                        <button
                                            type="button"
                                            className="fi-icon-button danger"
                                            onClick={() =>
                                                removeAttachment(
                                                    attachment
                                                )
                                            }
                                        >
                                            <span className="material-symbols-outlined">
                                                delete
                                            </span>
                                        </button>
                                    )}
                                </article>
                            )
                        )
                    )}
                </div>
            </section>
        </div>
    );
}

export default RecordsPanel;
