"use client";

import { useEffect, useRef, useState } from "react";

import { workforceService } from "../../services/workforceService.js";
import { useNotification } from "../../context/NotificationContext.jsx";
import "./EvidencePhoto.css";

const isManagedEvidence = (value) => {
    const text = String(value || "");
    return text.startsWith("/workforce/evidence-assets/") || text.startsWith("/workforce/evidence/");
};

export function EvidenceViewButton({ evidenceUrl, label = "View Image", compact = false, disabled = false }) {
    const notification = useNotification();
    const [previewUrl, setPreviewUrl] = useState("");
    const [loading, setLoading] = useState(false);
    const objectUrlRef = useRef("");
    const closeButtonRef = useRef(null);

    useEffect(() => () => {
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    }, []);

    useEffect(() => {
        if (!previewUrl) return undefined;
        const previousOverflow = document.body.style.overflow;
        const onKeyDown = (event) => {
            if (event.key === "Escape") {
                setPreviewUrl("");
                if (objectUrlRef.current) {
                    URL.revokeObjectURL(objectUrlRef.current);
                    objectUrlRef.current = "";
                }
            }
        };
        document.body.style.overflow = "hidden";
        document.addEventListener("keydown", onKeyDown);
        closeButtonRef.current?.focus();
        return () => {
            document.body.style.overflow = previousOverflow;
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [previewUrl]);

    if (!evidenceUrl) return null;

    const closePreview = () => {
        setPreviewUrl("");
        if (objectUrlRef.current) {
            URL.revokeObjectURL(objectUrlRef.current);
            objectUrlRef.current = "";
        }
    };

    const openPreview = async () => {
        if (disabled || loading) return;
        setLoading(true);
        try {
            if (!isManagedEvidence(evidenceUrl)) {
                throw new Error("External evidence links are disabled for security. Upload the photo to the task instead.");
            }
            const blob = await workforceService.downloadEvidencePhoto(evidenceUrl);
            if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
            objectUrlRef.current = URL.createObjectURL(blob);
            setPreviewUrl(objectUrlRef.current);
        } catch (error) {
            notification.error(error?.message || "Unable to open the evidence photo.", "Evidence");
        } finally {
            setLoading(false);
        }
    };

    return <>
        <button
            type="button"
            className={`evidence-action-button evidence-action-button--view evidence-view-button ${compact ? "compact" : ""}`}
            onClick={openPreview}
            disabled={disabled || loading}
            aria-busy={loading}
        >
            <span className="material-symbols-outlined" aria-hidden="true">visibility</span>
            <span>{loading ? "Opening…" : label}</span>
        </button>
        {previewUrl && <div className="evidence-preview-overlay" onMouseDown={(event)=>{ if (event.target === event.currentTarget) closePreview(); }}>
            <div className="evidence-preview-modal" role="dialog" aria-modal="true" aria-label="Evidence photo preview" onMouseDown={(event)=>event.stopPropagation()}>
                <header>
                    <div>
                        <strong>Evidence Photo</strong>
                        <span>Review the image submitted with this work record.</span>
                    </div>
                    <button ref={closeButtonRef} type="button" className="evidence-preview-close" onClick={closePreview} aria-label="Close image preview">
                        <span className="material-symbols-outlined" aria-hidden="true">close</span>
                    </button>
                </header>
                <div className="evidence-preview-body">
                    <img src={previewUrl} alt="Submitted work evidence" onError={() => notification.error("This evidence could not be displayed as an image.", "Evidence")}/>
                </div>
            </div>
        </div>}
    </>;
}

export function EvidenceInlinePreview({ evidenceUrl, alt = "Submitted work evidence" }) {
    const notification = useNotification();
    const [imageUrl, setImageUrl] = useState("");
    const [previewOpen, setPreviewOpen] = useState(false);
    const [loading, setLoading] = useState(Boolean(evidenceUrl));
    const [failed, setFailed] = useState(false);
    const objectUrlRef = useRef("");
    const closeButtonRef = useRef(null);

    useEffect(() => {
        let cancelled = false;
        const loadImage = async () => {
            if (!evidenceUrl) {
                setLoading(false);
                return;
            }
            setLoading(true);
            setFailed(false);
            try {
                if (!isManagedEvidence(evidenceUrl)) throw new Error("External evidence links are disabled.");
                const blob = await workforceService.downloadEvidencePhoto(evidenceUrl);
                if (cancelled) return;
                if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
                objectUrlRef.current = URL.createObjectURL(blob);
                setImageUrl(objectUrlRef.current);
            } catch (error) {
                if (!cancelled) {
                    setFailed(true);
                    notification.error(error?.message || "Unable to load the evidence photo.", "Evidence");
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        loadImage();
        return () => { cancelled = true; };
    }, [evidenceUrl]);

    useEffect(() => () => {
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    }, []);

    useEffect(() => {
        if (!previewOpen) return undefined;
        const previousOverflow = document.body.style.overflow;
        const onKeyDown = (event) => {
            if (event.key === "Escape") setPreviewOpen(false);
        };
        document.body.style.overflow = "hidden";
        document.addEventListener("keydown", onKeyDown);
        closeButtonRef.current?.focus();
        return () => {
            document.body.style.overflow = previousOverflow;
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [previewOpen]);

    if (!evidenceUrl) return <div className="evidence-inline-empty">No evidence photo submitted.</div>;
    if (loading) return <div className="evidence-inline-loading"><span className="material-symbols-outlined evidence-spin" aria-hidden="true">progress_activity</span>Loading secure evidence…</div>;
    if (failed || !imageUrl) return <div className="evidence-inline-error" role="status">Evidence photo could not be displayed.</div>;

    return <>
        <button type="button" className="evidence-inline-preview" onClick={() => setPreviewOpen(true)} aria-label="Open larger evidence photo preview">
            <img src={imageUrl} alt={alt} onError={() => setFailed(true)} />
            <span className="evidence-inline-zoom"><span className="material-symbols-outlined" aria-hidden="true">zoom_in</span>View larger</span>
        </button>
        {previewOpen && <div className="evidence-preview-overlay" onMouseDown={(event)=>{ if (event.target === event.currentTarget) setPreviewOpen(false); }}>
            <div className="evidence-preview-modal" role="dialog" aria-modal="true" aria-label="Evidence photo preview" onMouseDown={(event)=>event.stopPropagation()}>
                <header>
                    <div><strong>Evidence Photo</strong><span>Secure image attached to this work submission.</span></div>
                    <button ref={closeButtonRef} type="button" className="evidence-preview-close" onClick={() => setPreviewOpen(false)} aria-label="Close image preview">
                        <span className="material-symbols-outlined" aria-hidden="true">close</span>
                    </button>
                </header>
                <div className="evidence-preview-body"><img src={imageUrl} alt={alt} onError={() => setFailed(true)} /></div>
            </div>
        </div>}
    </>;
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

    const clearEvidence = () => {
        if (blocked) return;
        onChange("");
        setUploadedName("");
        setPendingName("");
        setStatus({ type: "idle", message: "Photo removed from this submission." });
        if (inputRef.current) inputRef.current.value = "";
    };

    const triggerFilePicker = () => {
        if (!blocked) inputRef.current?.click();
    };

    const displayedName = pendingName || uploadedName || (managed ? "Attached evidence photo" : "");
    const uploadText = uploading ? "Uploading…" : hasEvidence ? "Replace Photo" : "Upload Photo";
    const uploadIcon = uploading ? "progress_activity" : hasEvidence ? "photo_camera_back" : "add_a_photo";

    return <div className="workforce-field full evidence-photo-field" data-evidence-state={uploading ? "uploading" : hasEvidence ? "uploaded" : status.type}>
        <label>{label}{required ? " *" : ""}</label>

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
                disabled={blocked}
            >
                <span className="material-symbols-outlined" aria-hidden="true">delete</span>
                <span>Remove</span>
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
