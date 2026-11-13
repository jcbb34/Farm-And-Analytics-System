"use client";

import { useEffect, useRef, useState } from "react";

import { workforceService } from "../../services/workforceService.js";
import { useNotification } from "../../context/NotificationContext.jsx";
import { evidencePaths } from "./evidencePaths.js";
import { useEvidenceImage, useNearViewport } from "./useEvidenceImage.js";
import "./EvidencePhoto.css";

const isManagedEvidence = (value) => {
    const text = String(value || "");
    return text.startsWith("/workforce/evidence-assets/") || text.startsWith("/workforce/evidence/");
};

function EvidenceImageDialog({ image, alt, onClose, validPath = true }) {
    const closeButtonRef = useRef(null);
    const [badImage, setBadImage] = useState("");
    useEffect(() => {
        const previousFocus = document.activeElement;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        closeButtonRef.current?.focus();
        return () => {
            document.body.style.overflow = previousOverflow;
            if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
        };
    }, []);
    const onKeyDown = event => {
        if (event.key === "Escape") { event.stopPropagation(); onClose(); }
        if (event.key === "Tab") {
            event.stopPropagation();
            const buttons = [...event.currentTarget.querySelectorAll('button:not([disabled])')];
            const first = buttons[0], last = buttons[buttons.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
    };
    return <div className="evidence-preview-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
        <div className="evidence-preview-modal" role="dialog" aria-modal="true" aria-label="Evidence photo preview" onKeyDown={onKeyDown} onMouseDown={event => event.stopPropagation()}>
            <header><div><strong>Evidence Photo</strong><span>Secure image attached to this work submission.</span></div>
                <button ref={closeButtonRef} type="button" className="evidence-preview-close" onClick={onClose} aria-label="Close image preview"><span className="material-symbols-outlined" aria-hidden="true">close</span></button>
            </header>
            <div className="evidence-preview-body">
                {!validPath ? <p role="alert">External evidence links are disabled.</p> : image.loading ? <p role="status">Loading full-size evidence…</p>
                    : image.error || (image.url && badImage === image.url) ? <div role="alert"><p>{image.error || "This evidence could not be displayed as an image."}</p><button type="button" className="evidence-action-button evidence-action-button--view" onClick={() => { setBadImage(""); image.retry(); }}>Retry photo</button></div>
                    : image.url ? <img src={image.url} alt={alt} decoding="async" onError={() => setBadImage(image.url)} /> : <p role="status">Loading evidence…</p>}
            </div>
        </div>
    </div>;
}

export function EvidenceViewButton({ evidenceUrl, label = "View Image", compact = false, disabled = false }) {
    const [openEvidence, setOpenEvidence] = useState("");
    const previewOpen = Boolean(evidenceUrl) && openEvidence === evidenceUrl;
    const paths = evidencePaths(evidenceUrl);
    const image = useEvidenceImage(paths?.original, previewOpen);
    const loading = image.loading;
    if (!evidenceUrl) return null;
    return <>
        <button type="button" className={`evidence-action-button evidence-action-button--view evidence-view-button ${compact ? "compact" : ""}`}
            onClick={() => setOpenEvidence(evidenceUrl)} disabled={disabled || loading} aria-busy={loading}>
            <span className="material-symbols-outlined" aria-hidden="true">visibility</span><span>{loading ? "Opening…" : label}</span>
        </button>
        {previewOpen && <EvidenceImageDialog image={image} validPath={Boolean(paths)} alt="Submitted work evidence" onClose={() => setOpenEvidence("")} />}
    </>;
}

export function EvidenceInlinePreview({ evidenceUrl, alt = "Submitted work evidence" }) {
    const target = useRef(null);
    const paths = evidencePaths(evidenceUrl);
    const nearViewport = useNearViewport(target, evidenceUrl);
    const thumbnail = useEvidenceImage(paths?.thumbnail, nearViewport);
    const [openEvidence, setOpenEvidence] = useState("");
    const [brokenThumbnail, setBrokenThumbnail] = useState("");
    const previewOpen = Boolean(evidenceUrl) && openEvidence === evidenceUrl;
    const original = useEvidenceImage(paths?.original, previewOpen);
    const previewFailed = Boolean(thumbnail.error || (thumbnail.url && brokenThumbnail === thumbnail.url));
    return <div ref={target} className="evidence-inline-shell">
        {!evidenceUrl ? <div className="evidence-inline-empty">No evidence photo submitted.</div>
            : !paths ? <div className="evidence-inline-error" role="status">External evidence links are disabled.</div>
                : <button type="button" className="evidence-inline-preview" onClick={() => setOpenEvidence(evidenceUrl)} aria-label="Open larger evidence photo preview">
                    {thumbnail.url && !previewFailed ? <img src={thumbnail.url} alt={alt} decoding="async" onError={() => setBrokenThumbnail(thumbnail.url)} />
                        : <span className="evidence-inline-placeholder">{!nearViewport ? "Evidence photo" : thumbnail.loading ? "Loading secure preview…" : previewFailed ? "Preview unavailable. Open the full photo." : "Open evidence photo"}</span>}
                    <span className="evidence-inline-zoom"><span className="material-symbols-outlined" aria-hidden="true">zoom_in</span>View larger</span>
                </button>}
        {previewOpen && <EvidenceImageDialog image={original} validPath={Boolean(paths)} alt={alt} onClose={() => setOpenEvidence("")} />}
    </div>;
}

export default function EvidencePhotoField({
    taskId,
    value,
    onChange,
    required = false,
    disabled = false,
    label = "Evidence",
    helpText = "Upload a photo directly to this task.",
}) {
    const notification = useNotification();
    const [uploading, setUploading] = useState(false);
    const [uploadedName, setUploadedName] = useState("");
    const [pendingName, setPendingName] = useState("");
    const [status, setStatus] = useState({ type: "idle", message: "" });
    const inputRef = useRef(null);
    const managed = isManagedEvidence(value);
    const hasEvidence = Boolean(value);
    const blocked = disabled || uploading;

    const uploadPhoto = async (event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file) return;

        setPendingName(file.name || "Selected photo");
        setStatus({ type: "uploading", message: `Uploading ${file.name || "photo"}…` });

        if (!String(file.type || "").startsWith("image/")) {
            const message = "Select a JPG, PNG, or WEBP photo file.";
            setPendingName("");
            setStatus({ type: "error", message });
            notification.error(message, "Evidence");
            return;
        }

        setUploading(true);
        try {
            if (!taskId) throw new Error("A task must be selected before evidence can be uploaded.");
            const result = await workforceService.uploadEvidencePhoto(taskId, file);
            const fileName = result?.file_name || file.name || "Uploaded evidence photo";
            onChange(result?.evidence_url || "");
            setUploadedName(fileName);
            setStatus({ type: "success", message: `${fileName} is ready to submit.` });
            notification.success(hasEvidence ? "Evidence photo replaced." : "Evidence photo uploaded.", "Evidence");
        } catch (error) {
            const message = error?.message || "Unable to upload the evidence photo.";
            setStatus({ type: "error", message });
            notification.error(message, "Evidence");
        } finally {
            setPendingName("");
            setUploading(false);
        }
    };

    const [deleting, setDeleting] = useState(false);

    const clearEvidence = async () => {
        if (blocked || deleting) return;
        setDeleting(true);
        try {
            // If evidence is managed (server-side), also delete from backend storage
            if (managed && value) {
                await workforceService.deleteEvidencePhoto(value);
            }
        } catch (error) {
            notification.error("Failed to delete evidence from server: " + (error?.message || "Unknown error"), "Evidence");
        } finally {
            // Always clear local form state regardless of backend result
            onChange("");
            setUploadedName("");
            setPendingName("");
            setStatus({ type: "idle", message: "Photo removed from this submission." });
            if (inputRef.current) inputRef.current.value = "";
            setDeleting(false);
        }
    };

    const triggerFilePicker = () => {
        if (!blocked) inputRef.current?.click();
    };

    const displayedName = pendingName || uploadedName || (managed ? "Attached evidence photo" : "");
    const uploadText = uploading ? "Uploading…" : hasEvidence ? "Replace Photo" : "Upload Photo";
    const uploadIcon = uploading ? "progress_activity" : hasEvidence ? "photo_camera_back" : "add_a_photo";

    return <div className="workforce-field full evidence-photo-field" data-evidence-state={uploading ? "uploading" : hasEvidence ? "uploaded" : status.type}>
        <div className="evidence-header-row">
            <label>{label}{required ? " *" : ""}</label>
            {hasEvidence && <span className="evidence-count-badge">1 active attachment</span>}
        </div>

        <div className="evidence-photo-actions" role="group" aria-label={`${label} actions`}>
            <button
                type="button"
                className="evidence-action-button evidence-action-button--upload evidence-upload-button"
                onClick={triggerFilePicker}
                disabled={blocked}
                aria-busy={uploading}
            >
                <span className={`material-symbols-outlined ${uploading ? "evidence-spin" : ""}`} aria-hidden="true">{uploadIcon}</span>
                <span>{uploadText}</span>
            </button>
            <input
                ref={inputRef}
                className="evidence-file-input"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                disabled={blocked}
                onChange={uploadPhoto}
                aria-label={hasEvidence ? "Replace evidence photo" : "Upload evidence photo"}
            />

            {hasEvidence && <EvidenceViewButton evidenceUrl={value} disabled={blocked}/>}
            {hasEvidence && <button
                type="button"
                className="evidence-action-button evidence-action-button--remove evidence-remove-button"
                onClick={clearEvidence}
                disabled={blocked || deleting}
            >
                <span className="material-symbols-outlined" aria-hidden="true">{deleting ? "progress_activity" : "delete"}</span>
                <span>{deleting ? "Removing…" : "Remove Attachment"}</span>
            </button>}
        </div>

        {(managed || pendingName) && (
            <div className="evidence-uploaded-file">
                <span className="material-symbols-outlined" aria-hidden="true">image</span>
                <div className="evidence-uploaded-file-copy">
                    <strong className="evidence-file-name" title={displayedName} aria-label={`Selected evidence file: ${displayedName}`}>{displayedName}</strong>
                    <span>{uploading ? "Validating and securing the image…" : "Bound to this task and attached when you submit the work."}</span>
                </div>
            </div>
        )}

        {status.message && <div
            className={`evidence-inline-status evidence-inline-status--${status.type}`}
            role={status.type === "error" ? "alert" : "status"}
            aria-live="polite"
        >
            <span className="material-symbols-outlined" aria-hidden="true">
                {status.type === "error" ? "error" : status.type === "success" ? "check_circle" : status.type === "uploading" ? "progress_activity" : "info"}
            </span>
            <span>{status.message}</span>
        </div>}

        <small className="workforce-field-help">{helpText} JPG, PNG, or WEBP only. The server validates and safely re-encodes the image.</small>
    </div>;
}
