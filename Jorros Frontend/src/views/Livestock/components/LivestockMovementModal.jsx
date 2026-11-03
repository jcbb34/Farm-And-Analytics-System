"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { farmDateKey } from "../../../utils/farmCalendar.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { livestockService } from "../../../services/livestockService.js";
import useModalScrollLock from "../../../hooks/useModalScrollLock.js";
import "./LivestockMovementModal.css";

function todayValue() {
    return farmDateKey();
}

function n(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function defaultSplit(animal) {
    const quantity = 1;
    let male = 0;
    let female = 0;
    let unknown = 0;
    if (n(animal?.maleQuantity) > 0) male = 1;
    else if (n(animal?.femaleQuantity) > 0) female = 1;
    else unknown = 1;

    let healthy = 0;
    let atRisk = 0;
    let sick = 0;
    let treatment = 0;
    if (n(animal?.sickQuantity) > 0) sick = 1;
    else if (n(animal?.underTreatmentQuantity) > 0) treatment = 1;
    else if (n(animal?.atRiskQuantity) > 0) atRisk = 1;
    else healthy = 1;

    return {
        quantity: String(quantity),
        maleQuantity: String(male),
        femaleQuantity: String(female),
        unknownSexQuantity: String(unknown),
        healthyQuantity: String(healthy),
        atRiskQuantity: String(atRisk),
        sickQuantity: String(sick),
        underTreatmentQuantity: String(treatment),
    };
}

export default function LivestockMovementModal({ animal, onClose, onTransfer, onSplit }) {
    const [mode, setMode] = useState("transfer");
    const [pens, setPens] = useState([]);
    const [pensLoading, setPensLoading] = useState(true);
    const [pensError, setPensError] = useState("");
    const [penRetryCount, setPenRetryCount] = useState(0);
    const [busy, setBusy] = useState(false);
    const modalRef = useRef(null);
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;
    const [form, setForm] = useState(() => ({
        penId: "",
        recordName: "",
        eventDate: todayValue(),
        reason: "",
        ...defaultSplit(animal),
    }));

    useModalScrollLock(Boolean(animal));

    useEffect(() => {
        if (!animal) return undefined;

        let active = true;
        setPensLoading(true);
        setPensError("");
        livestockService.getPens()
            .then((rows) => {
                if (active) setPens(rows);
            })
            .catch((error) => {
                if (active) {
                    setPens([]);
                    setPensError(error?.message || "Unable to load pens.");
                }
            })
            .finally(() => {
                if (active) setPensLoading(false);
            });
        return () => { active = false; };
    }, [animal?.id, penRetryCount]);

    useEffect(() => {
        if (!animal) return undefined;

        const previousFocus = document.activeElement;
        modalRef.current?.focus({ preventScroll: true });
        const handleKeyDown = (event) => {
            if (event.key === "Escape") onCloseRef.current();
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
                previousFocus.focus({ preventScroll: true });
            }
        };
    }, [animal?.id]);

    const selectedPen = useMemo(
        () => pens.find((pen) => String(pen.id) === String(form.penId)),
        [pens, form.penId]
    );

    const destinationPens = useMemo(
        () =>
            pens.filter((pen) => {
                if (pen.status !== "Active") return false;
                if (mode === "transfer" && String(pen.id) === String(animal?.penId)) return false;
                const allowedSpecies = String(pen.animalType || "").trim().toLowerCase();
                return (
                    !allowedSpecies ||
                    ["all", "all livestock", "any"].includes(allowedSpecies) ||
                    allowedSpecies === String(animal?.type || "").trim().toLowerCase()
                );
            }),
        [pens, mode, animal?.penId, animal?.type]
    );

    if (!animal) return null;

    const updateField = (event) => {
        const { name, value } = event.target;
        setForm((current) => ({ ...current, [name]: value }));
    };

    const submit = async (event) => {
        event.preventDefault();
        setBusy(true);
        try {
            if (mode === "transfer") {
                if (!selectedPen) {
                    notify("Choose a destination pen.");
                    return;
                }
                await onTransfer({
                    penId: selectedPen.id,
                    penLocation: selectedPen.name,
                    eventDate: form.eventDate,
                    reason: form.reason,
                });
                return;
            }

            const quantity = n(form.quantity);
            const male = n(form.maleQuantity);
            const female = n(form.femaleQuantity);
            const unknown = n(form.unknownSexQuantity);
            const healthy = n(form.healthyQuantity);
            const atRisk = n(form.atRiskQuantity);
            const sick = n(form.sickQuantity);
            const treatment = n(form.underTreatmentQuantity);

            if (!Number.isInteger(quantity) || quantity < 1 || quantity >= animal.quantity) {
                notify(`Split quantity must be between 1 and ${animal.quantity - 1}.`);
                return;
            }
            if (male + female + unknown !== quantity) {
                notify("Split Male + Female + Unknown quantities must equal the split quantity.");
                return;
            }
            if (healthy + atRisk + sick + treatment !== quantity) {
                notify("Split health quantities must equal the split quantity.");
                return;
            }
            const checks = [
                [male, animal.maleQuantity, "male"],
                [female, animal.femaleQuantity, "female"],
                [unknown, animal.unknownSexQuantity, "unknown-sex"],
                [healthy, animal.healthyQuantity, "healthy"],
                [atRisk, animal.atRiskQuantity, "at-risk"],
                [sick, animal.sickQuantity, "sick"],
                [treatment, animal.underTreatmentQuantity, "under-treatment"],
            ];
            const invalid = checks.find(([requested, available]) => requested > n(available));
            if (invalid) {
                notify(`The source batch does not have enough ${invalid[2]} animals for this split.`);
                return;
            }

            await onSplit({
                quantity,
                recordName: form.recordName,
                penId: selectedPen?.id || null,
                penLocation: selectedPen?.name || "",
                eventDate: form.eventDate,
                reason: form.reason,
                maleQuantity: male,
                femaleQuantity: female,
                unknownSexQuantity: unknown,
                healthyQuantity: healthy,
                atRiskQuantity: atRisk,
                sickQuantity: sick,
                underTreatmentQuantity: treatment,
            });
        } finally {
            setBusy(false);
        }
    };

    const sickMove = mode === "split" && (n(form.sickQuantity) + n(form.underTreatmentQuantity) > 0);

    return createPortal(
        <div className="livestock-movement-overlay" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
            <section ref={modalRef} className="livestock-movement-modal" role="dialog" aria-modal="true" aria-labelledby="livestock-movement-title" tabIndex={-1}>
                <header className="livestock-movement-header">
                    <div>
                        <h2 id="livestock-movement-title">Manage Livestock Movement</h2>
                        <p>{animal.animalId} · {animal.recordName} · {animal.quantity} head</p>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close">
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </header>

                <form onSubmit={submit} className="livestock-movement-body">
                    <div className="livestock-movement-mode-row">
                        <button type="button" className={mode === "transfer" ? "active" : ""} onClick={() => setMode("transfer")}>Transfer Pen</button>
                        {animal.quantity > 1 && (
                            <button type="button" className={mode === "split" ? "active" : ""} onClick={() => setMode("split")}>Split / Move Animals</button>
                        )}
                    </div>

                    {mode === "transfer" ? (
                        <div className="livestock-movement-note">
                            Moves the whole batch to another pen. Total livestock population does not change.
                        </div>
                    ) : (
                        <>
                            <div className="livestock-movement-note">
                                Use this when part of a batch moves to another pen, including sick animals moving to isolation. The new batch keeps the same breed.
                            </div>
                            <div className="livestock-movement-grid">
                                <label>
                                    Animals to move
                                    <input name="quantity" type="number" min="1" max={Math.max(animal.quantity - 1, 1)} value={form.quantity} onChange={updateField} required />
                                </label>
                                <label>
                                    New Batch Name
                                    <input name="recordName" value={form.recordName} onChange={updateField} placeholder={`${animal.recordName} Split`} />
                                </label>
                            </div>

                            <div className="livestock-movement-breakdown">
                                <h3>Sex Breakdown</h3>
                                <div className="livestock-movement-grid three">
                                    <label>Male <small>Available: {animal.maleQuantity}</small><input name="maleQuantity" type="number" min="0" value={form.maleQuantity} onChange={updateField} /></label>
                                    <label>Female <small>Available: {animal.femaleQuantity}</small><input name="femaleQuantity" type="number" min="0" value={form.femaleQuantity} onChange={updateField} /></label>
                                    <label>Unknown <small>Available: {animal.unknownSexQuantity}</small><input name="unknownSexQuantity" type="number" min="0" value={form.unknownSexQuantity} onChange={updateField} /></label>
                                </div>
                            </div>

                            <div className="livestock-movement-breakdown">
                                <h3>Health Breakdown</h3>
                                <div className="livestock-movement-grid health-four">
                                    <label>Healthy <small>Available: {animal.healthyQuantity}</small><input name="healthyQuantity" type="number" min="0" value={form.healthyQuantity} onChange={updateField} /></label>
                                    <label>At Risk <small>Available: {animal.atRiskQuantity}</small><input name="atRiskQuantity" type="number" min="0" value={form.atRiskQuantity} onChange={updateField} /></label>
                                    <label>Sick <small>Available: {animal.sickQuantity}</small><input name="sickQuantity" type="number" min="0" value={form.sickQuantity} onChange={updateField} /></label>
                                    <label>Under Treatment <small>Available: {animal.underTreatmentQuantity}</small><input name="underTreatmentQuantity" type="number" min="0" value={form.underTreatmentQuantity} onChange={updateField} /></label>
                                </div>
                            </div>
                        </>
                    )}

                    <div className="livestock-movement-grid">
                        <label>
                            {mode === "transfer" ? "Destination Pen" : "Destination Pen (optional)"}
                            <select name="penId" value={form.penId} onChange={updateField} required={mode === "transfer"} disabled={pensLoading || Boolean(pensError)}>
                                <option value="">{pensLoading ? "Loading pens..." : mode === "transfer" ? "Select a pen" : `Keep in ${animal.penLocation}`}</option>
                                {destinationPens.map((pen) => (
                                    <option key={pen.id} value={pen.id}>{pen.name} — {pen.purpose} — {pen.capacity ? `${pen.currentOccupancy}/${pen.capacity}` : `${pen.currentOccupancy} occupied`}</option>
                                ))}
                            </select>
                            {pensError && <small role="alert" className="livestock-movement-warning">{pensError} <button type="button" onClick={() => setPenRetryCount((count) => count + 1)}>Retry</button></small>}
                            {sickMove && (
                                <small className="livestock-movement-warning">Isolation / Sick or Recovery pen is recommended for separated sick animals.</small>
                            )}
                        </label>
                        <label>
                            Date
                            <input name="eventDate" type="date" value={form.eventDate} onChange={updateField} required />
                        </label>
                    </div>

                    <label className="livestock-movement-reason">
                        Reason / Notes
                        <textarea name="reason" value={form.reason} onChange={updateField} rows="3" placeholder="Example: 2 sick birds moved to Isolation Pen 1" />
                    </label>

                    <footer className="livestock-movement-footer">
                        <button type="button" className="secondary" onClick={onClose}>Cancel</button>
                        <button type="submit" className="primary" disabled={busy || (mode === "transfer" && (pensLoading || Boolean(pensError)))}>{busy ? "Saving..." : mode === "transfer" ? "Transfer Batch" : "Split Batch"}</button>
                    </footer>
                </form>
            </section>
        </div>,
        document.body
    );
}
