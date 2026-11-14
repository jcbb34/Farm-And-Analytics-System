"use client";

import { useEffect, useRef, useState } from "react";
import { cropService } from "../../../services/cropService.js";
import { readinessInspectionValidation } from "./readinessChecklist.mjs";
import "./CropReadinessInspectionModal.css";

function localToday() {
    const date = new Date();
    const year = String(date.getFullYear());
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

export default function CropReadinessInspectionModal({ crop, onClose, onSaved }) {
    const [reference, setReference] = useState(null);
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [saveError, setSaveError] = useState("");
    const [saving, setSaving] = useState(false);
    const [inspectionDate, setInspectionDate] = useState(localToday);
    const [findings, setFindings] = useState({});
    const [verdict, setVerdict] = useState("ready");
    const [notes, setNotes] = useState("");
    const closeRef = useRef(null);
    const onCloseRef = useRef(onClose);
    const savingRef = useRef(saving);
    onCloseRef.current = onClose;
    savingRef.current = saving;
    const loadingSequence = useRef(0);

    const load = async () => {
        const sequence = ++loadingSequence.current;
        setLoading(true);
        setLoadError("");
        try {
            const details = await cropService.getReadinessInspections(crop.id);
            if (sequence !== loadingSequence.current) return;
            setReference(details?.profile || null);
            setHistory(Array.isArray(details?.inspections) ? details.inspections : []);
            setFindings({});
        } catch (error) {
            if (sequence === loadingSequence.current) setLoadError(error?.message || "Cannot load the crop inspection profile.");
        } finally {
            if (sequence === loadingSequence.current) setLoading(false);
        }
    };

    useEffect(() => {
        void load();
        const previous = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        closeRef.current?.focus();
        const onKey = (event) => {
            if (event.key === "Escape" && !savingRef.current) onCloseRef.current();
        };
        document.addEventListener("keydown", onKey);
        return () => {
            loadingSequence.current += 1;
            document.removeEventListener("keydown", onKey);
            document.body.style.overflow = previous;
        };
    // This dialog is mounted for one selected crop at a time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [crop.id]);

    const error = reference ? readinessInspectionValidation({
        profile: reference, findings, verdict, inspectionDate,
        plantingDate: crop.plantingDate, today: localToday(), notes,
    }) : "";
    const statusConfirmed = Boolean(crop.confirmedReadyAt || crop.readinessStatus === "Confirmed Ready");

    const submit = async (event) => {
        event.preventDefault();
        if (saving || loading || !reference) return;
        if (statusConfirmed && verdict === "not_ready") {
            setSaveError("This planting was already confirmed ready. Review its recorded inspection before changing the status.");
            return;
        }
        if (error) { setSaveError(error); return; }
        setSaving(true);
        setSaveError("");
        try {
            await cropService.saveReadinessInspection(crop.id, {
                inspection_date: inspectionDate,
                verdict,
                findings,
                notes: notes.trim() || null,
            });
            await onSaved?.(crop, verdict);
        } catch (caught) {
            setSaveError(caught?.message || "Unable to record harvest readiness.");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="crop-readiness-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) onClose(); }}>
            <section className="crop-readiness-modal" role="dialog" aria-modal="true" aria-labelledby="readiness-title" aria-describedby="readiness-summary">
                <header className="crop-readiness-header">
                    <div className="crop-readiness-header-main">
                        <span className="material-symbols-outlined" aria-hidden="true">fact_check</span>
                        <div><h2 id="readiness-title">Harvest Readiness Inspection</h2><p id="readiness-summary">Confirm actual crop condition before setting Ready for Harvest.</p></div>
                    </div>
                    <button ref={closeRef} className="crop-readiness-close" type="button" aria-label="Close inspection" onClick={onClose} disabled={saving}>
                        <span className="material-symbols-outlined" aria-hidden="true">close</span>
                    </button>
                </header>

                <form className="crop-readiness-form" onSubmit={submit}>
                    <div className="crop-readiness-scroll">
                        <section className="crop-readiness-identity">
                            <div><span className="crop-readiness-eyebrow">SELECTED PLANTING</span><strong>{crop.name} — {crop.variety}</strong>
                                <p>{[crop.field, crop.sectionName || crop.section_name].filter(Boolean).join(" / ") || "Location not recorded"}</p></div>
                            <span className="crop-readiness-code">{crop.cropCode || `Crop #${crop.id}`}</span>
                        </section>

                        {statusConfirmed && <div className="crop-readiness-note">This crop is already physically confirmed ready. Past inspections are available below.</div>}
                        {loading && <div className="crop-readiness-note" role="status">Loading inspection criteria…</div>}
                        {loadError && <div className="crop-readiness-error" role="alert">{loadError} <button type="button" onClick={load}>Retry</button></div>}
                        {reference && !loading && <>
                            <div className="crop-readiness-profile">
                                <span className="material-symbols-outlined" aria-hidden="true">menu_book</span>
                                <div><strong>{reference.title}</strong><p>{reference.guidance}</p>
                                    <small>{reference.reference_scope === "variety_recognized" ? "Known variety · observational reference" : "General crop guidance · exact variety not verified"} · Profile v{reference.version}</small>
                                </div>
                            </div>
                            <div className="crop-readiness-fieldrow">
                                <label htmlFor="readiness-date">Inspection date <span aria-hidden="true">*</span></label>
                                <input id="readiness-date" type="date" required max={localToday()} min={crop.plantingDate || undefined} value={inspectionDate} onChange={(event) => setInspectionDate(event.target.value)}/>
                            </div>
                            <fieldset className="crop-readiness-checklist">
                                <legend>Physical inspection checklist</legend>
                                <p>Answer each observation for this planting. Estimated harvest dates alone do not confirm readiness.</p>
                                {reference.checks.map((check, index) => (
                                    <div className="crop-readiness-check" key={check.id}>
                                        <div className="crop-readiness-check-copy"><span>{index+1}</span><div><strong>{check.label}</strong><small>{check.help}</small></div></div>
                                        <div className="crop-readiness-choice" role="group" aria-label={check.label}>
                                            <button type="button" className={findings[check.id] === true ? "selected yes" : ""} aria-pressed={findings[check.id] === true} onClick={() => { setFindings(current => ({ ...current, [check.id]: true })); setSaveError(""); }}>Yes</button>
                                            <button type="button" className={findings[check.id] === false ? "selected no" : ""} aria-pressed={findings[check.id] === false} onClick={() => { setFindings(current => ({ ...current, [check.id]: false })); setSaveError(""); }}>No</button>
                                        </div>
                                    </div>
                                ))}
                            </fieldset>
                            <fieldset className="crop-readiness-verdict"><legend>Inspection result</legend>
                                <label><input type="radio" name="readiness-verdict" value="ready" checked={verdict === "ready"} onChange={() => { setVerdict("ready"); setSaveError(""); }}/> <span><strong>Ready for Harvest</strong><small>All observable criteria have been met.</small></span></label>
                                <label><input type="radio" name="readiness-verdict" value="not_ready" checked={verdict === "not_ready"} onChange={() => { setVerdict("not_ready"); setSaveError(""); }}/> <span><strong>Not yet ready</strong><small>Record an inspection without confirming harvest readiness.</small></span></label>
                            </fieldset>
                            <label className="crop-readiness-notes" htmlFor="readiness-notes"><strong>Inspection notes {verdict === "not_ready" ? "(required)" : "(optional)"}</strong><textarea id="readiness-notes" value={notes} maxLength={1000} onChange={(event) => setNotes(event.target.value)} placeholder="Actual observations, product maturity, delays, or follow-up actions…" rows={3}/></label>
                            <p className="crop-readiness-source">Reference: {reference.source}. This checklist documents human observations; it does not automatically verify agricultural maturity. Saving “Not yet ready” does not cancel an existing harvest task; reschedule that task in Task Management if needed.</p>
                            {history.length > 0 && <section className="crop-readiness-history"><h3>Recent readiness inspections</h3>{history.slice(0,5).map(item => <div key={item.id}><span>{item.date}</span><strong>{item.verdict === "ready" ? "Ready confirmed" : "Not yet ready"}</strong><small>{item.inspected_by ? `Inspected by ${item.inspected_by}. ` : ""}{item.notes || "No additional notes"}</small></div>)}</section>}
                        </>}
                        {saveError && <div className="crop-readiness-error" role="alert">{saveError}</div>}
                    </div>
                    <footer className="crop-readiness-footer">
                        <button type="button" onClick={onClose} disabled={saving}>Cancel</button>
                        <button type="submit" className="primary" disabled={!reference || loading || saving || (statusConfirmed && verdict === "not_ready")}>
                            {saving ? "Saving inspection…" : verdict === "ready" ? "Confirm readiness" : "Save inspection"}
                        </button>
                    </footer>
                </form>
            </section>
        </div>
    );
}
