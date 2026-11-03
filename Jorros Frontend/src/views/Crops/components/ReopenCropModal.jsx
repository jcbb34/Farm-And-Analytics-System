"use client";

import { useEffect, useRef, useState } from "react";
import "../../../components/CropModals/CropModals.css";
import "./ReopenCropModal.css";

export default function ReopenCropModal({ crop, onClose, onSave }) {
    const [reason, setReason] = useState("");
    const [newStatus, setNewStatus] = useState("Harvesting");
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");
    const reasonRef = useRef(null);
    const dialogRef = useRef(null);
    const busyRef = useRef(false);
    const closeRef = useRef(onClose);
    closeRef.current = onClose;

    useEffect(() => {
        const previousFocus = document.activeElement;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        reasonRef.current?.focus();

        const handleKeyDown = (event) => {
            if (event.key === "Escape" && !busyRef.current) {
                event.preventDefault();
                closeRef.current();
            }
            if (event.key !== "Tab" || !dialogRef.current) return;
            const controls = Array.from(dialogRef.current.querySelectorAll(
                'button:not([disabled]), input:not([disabled]), textarea:not([disabled])'
            ));
            if (!controls.length) return;
            const first = controls[0];
            const last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            document.body.style.overflow = previousOverflow;
            previousFocus?.focus?.();
        };
    }, []);

    const submit = async (event) => {
        event.preventDefault();
        if (busyRef.current) return;
        const cleaned = reason.trim();
        if (cleaned.length < 3) {
            setError("Enter a reason with at least 3 characters.");
            reasonRef.current?.focus();
            return;
        }
        setError("");
        busyRef.current = true;
        setSubmitting(true);
        try {
            await onSave({ reason: cleaned, newStatus });
        } catch (err) {
            setError(err?.message || "Unable to reopen the crop cycle. Try again.");
        } finally {
            busyRef.current = false;
            setSubmitting(false);
        }
    };

    return (
        <div className="crop-modal-overlay" onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busyRef.current) onClose();
        }}>
            <div className="crop-reopen-modal" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="crop-reopen-title" aria-describedby="crop-reopen-description">
                <header className="crop-modal-header">
                    <div>
                        <h2 id="crop-reopen-title">Reopen Crop Cycle</h2>
                        <p id="crop-reopen-description">{crop.name} · {crop.variety} · {crop.field}</p>
                    </div>
                    <button type="button" onClick={onClose} disabled={submitting} aria-label="Close reopen crop cycle form">
                        <span className="material-symbols-outlined" aria-hidden="true">close</span>
                    </button>
                </header>

                <form onSubmit={submit} className="crop-reopen-form">
                    <div className="crop-reopen-body">
                        <section className="crop-form-section crop-reopen-section">
                            <div className="crop-form-section-title">
                                <span className="material-symbols-outlined" aria-hidden="true">restart_alt</span>
                                <div>
                                    <h3>Cycle Details</h3>
                                    <p>Record why this completed crop needs further harvest work.</p>
                                </div>
                            </div>

                            <div className="crop-reopen-current">
                                <span>Current status: <strong>Fully Harvested</strong></span>
                                <span>Harvest already recorded: <strong>{crop.totalHarvestQuantityKg ?? 0} kg</strong></span>
                            </div>

                            <div className="crop-form-group">
                                <label htmlFor="crop-reopen-reason">Reason for reopening <span aria-hidden="true">*</span></label>
                                <textarea
                                    id="crop-reopen-reason"
                                    ref={reasonRef}
                                    value={reason}
                                    onChange={(event) => { setReason(event.target.value); setError(""); }}
                                    placeholder="For example: More produce remains to be harvested."
                                    minLength={3}
                                    maxLength={500}
                                    rows={3}
                                    required
                                    disabled={submitting}
                                    aria-invalid={Boolean(error)}
                                />
                                <small className="crop-reopen-hint">Your reason will appear in the crop history.</small>
                            </div>

                            <fieldset className="crop-reopen-status">
                                <legend>Reopen as</legend>
                                <div className="crop-reopen-choices">
                                    <label><input type="radio" name="reopenStatus" value="Harvesting" checked={newStatus === "Harvesting"} disabled={submitting} onChange={() => setNewStatus("Harvesting")} /><span><strong>Harvesting</strong><small>Continue recording harvests.</small></span></label>
                                    <label><input type="radio" name="reopenStatus" value="Ready for Harvest" checked={newStatus === "Ready for Harvest"} disabled={submitting} onChange={() => setNewStatus("Ready for Harvest")} /><span><strong>Ready for Harvest</strong><small>Ready for the next harvest.</small></span></label>
                                </div>
                            </fieldset>

                            <p className="crop-reopen-history-note">
                                <span className="material-symbols-outlined" aria-hidden="true">history</span>
                                Existing yields and production remain recorded. Reports for dates before reopening still show the crop as completed.
                            </p>
                        </section>
                    </div>

                    <div className="crop-reopen-footer">
                        {error && <p className="crop-reopen-error" role="alert">{error}</p>}
                        <div className="crop-form-footer">
                            <button type="button" className="crop-modal-cancel" onClick={onClose} disabled={submitting}>Cancel</button>
                            <button type="submit" className="crop-modal-save" disabled={submitting || reason.trim().length < 3}>
                                <span className="material-symbols-outlined" aria-hidden="true">restart_alt</span>
                                {submitting ? "Reopening…" : "Reopen Crop Cycle"}
                            </button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    );
}
