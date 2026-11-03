"use client";

import { ObservationSummary } from "../../components/Monitoring/Monitoring.jsx";

import { useEffect, useRef, useState } from "react";

import { EvidenceInlinePreview } from "../../components/EvidencePhoto/EvidencePhoto.jsx";
import "./WorkSubmissionReviewModal.css";

const formatDate = (value) => {
    if (!value) return "—";
    const parsed = new Date(`${value}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString();
};

const formatDateTime = (value) => {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
};

const formatQuantity = (value, unit) => {
    if (value == null) return "—";
    const number = Number(value);
    const rendered = Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(value);
    return `${rendered}${unit ? ` ${unit}` : ""}`;
};

const InfoItem = ({ label, children, full = false }) => (
    <div className={`review-report-item${full ? " full" : ""}`}>
        <span>{label}</span>
        <strong>{children ?? "—"}</strong>
    </div>
);

export default function WorkSubmissionReviewModal({
    open,
    report,
    loading = false,
    loadError = "",
    actionError = "",
    processingAction = "",
    onClose,
    onRetry,
    onApprove,
    onReturn,
}) {
    const [confirmedStage, setConfirmedStage] = useState("");
    const [confirmedReady, setConfirmedReady] = useState(false);
    const [feedback, setFeedback] = useState("");
    const [feedbackError, setFeedbackError] = useState("");
    const [harvestType, setHarvestType] = useState("Partial Harvest");
    const [finalHarvestConfirmed, setFinalHarvestConfirmed] = useState(false);
    const [harvestError, setHarvestError] = useState("");
    const modalRef = useRef(null);
    const closeRef = useRef(null);
    const previousFocusRef = useRef(null);

    const busy = Boolean(processingAction);
    const task = report?.task;
    const submission = report?.current_submission;
    const resource = report?.resource_usage;
    const canReview = task?.status === "Submitted for Review" && submission?.review_status === "Submitted";
    const isCropHarvest = task?.source_module === "Crop" && task?.source_type === "crop_harvest";
    const closedCropPartialHarvest = isCropHarvest && report?.crop_status === "Harvested" && harvestType !== "Final Harvest";
    const approvalBlocker = isCropHarvest && (report?.harvest_approval_blocker || (
        closedCropPartialHarvest
            ? "This crop is already Fully Harvested. Select Final Harvest to confirm its missing final yield, or correct the crop record in Crops before approving a Partial Harvest."
            : ""
    ));

    useEffect(() => {
        if (!open) return;
        setConfirmedStage(submission?.monitoring?.resource_type === "Crop" ? submission.monitoring.observed_stage || "" : "");
        setConfirmedReady(false);
        setFeedback("");
        setFeedbackError("");
        setHarvestType(submission?.harvest_type_intent || "Partial Harvest");
        setFinalHarvestConfirmed(false);
        setHarvestError("");
    }, [open, task?.id, submission?.id, submission?.harvest_type_intent]);

    useEffect(() => {
        if (!open) return undefined;
        previousFocusRef.current = document.activeElement;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";

        const focusableSelector = [
            "button:not([disabled])",
            "textarea:not([disabled])",
            "input:not([disabled])",
            "select:not([disabled])",
            "a[href]",
            "[tabindex]:not([tabindex='-1'])",
        ].join(",");

        const handleKeyDown = (event) => {
            const activeDialog = modalRef.current;
            if (!activeDialog) return;
            if (event.key === "Escape") {
                event.preventDefault();
                if (busy) return;
                onClose?.();
                return;
            }
            if (event.key !== "Tab") return;
            const focusable = [...activeDialog.querySelectorAll(focusableSelector)].filter((element) => !element.hasAttribute("disabled"));
            if (!focusable.length) {
                event.preventDefault();
                return;
            }
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };

        document.addEventListener("keydown", handleKeyDown);
        window.setTimeout(() => closeRef.current?.focus(), 0);
        return () => {
            document.body.style.overflow = previousOverflow;
            document.removeEventListener("keydown", handleKeyDown);
            previousFocusRef.current?.focus?.();
        };
    }, [open, busy, onClose]);


    if (!open) return null;

    const closeFromBackdrop = (event) => {
        if (event.target === event.currentTarget && !busy) onClose?.();
    };

    const submitReturn = async () => {
        if (!canReview) return;
        const trimmed = feedback.trim();
        if (!trimmed) {
            setFeedbackError("Feedback is required before returning this work for correction.");
            return;
        }
        setFeedbackError("");
        await onReturn?.(trimmed);
    };

    const previousSubmissions = report?.previous_submissions || [];
    const sourceLabel = task?.is_automatic ? "Automatic task" : "Manually assigned task";
    const difference = resource?.quantity_difference;
    const differenceLabel = difference == null
        ? "—"
        : `${difference > 0 ? "+" : ""}${Number(difference).toLocaleString(undefined, { maximumFractionDigits: 3 })}${resource?.actual_unit || resource?.planned_unit ? ` ${resource?.actual_unit || resource?.planned_unit}` : ""}`;

    return (
        <div className="workforce-modal-overlay work-review-overlay" onMouseDown={closeFromBackdrop}>
            <div
                ref={modalRef}
                className="work-review-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="work-submission-report-title"
                aria-describedby="work-submission-report-description"
                onMouseDown={(event) => event.stopPropagation()}
            >
                <header className="work-review-header">
                    <div>
                        <span className="work-review-eyebrow">Task Management</span>
                        <h2 id="work-submission-report-title">Work Submission Report</h2>
                        <p id="work-submission-report-description">Review the employee's complete submitted work before making a decision.</p>
                    </div>
                    <button ref={closeRef} type="button" className="workforce-modal-close" onClick={onClose} disabled={busy} aria-label="Close work submission report">
                        <span className="material-symbols-outlined" aria-hidden="true">close</span>
                    </button>
                </header>

                <div className="work-review-body">
                    {loadError && (
                        <div className="work-review-alert error" role="alert">
                            <span className="material-symbols-outlined" aria-hidden="true">sync_problem</span>
                            <div><strong>Unable to open the current review</strong><span>{loadError}</span></div>
                            {onRetry && <button type="button" className="workforce-button secondary" onClick={onRetry} disabled={loading || busy}>Reload</button>}
                        </div>
                    )}
                    {loading && <div className="work-review-loading" role="status"><span className="material-symbols-outlined review-spin" aria-hidden="true">progress_activity</span>Loading the latest submission…</div>}

                    {!loading && report && (
                        <>
                            <section className="work-review-section">
                                <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">assignment</span><div><h3>Task Information</h3><p>Assignment and schedule details for the work being reviewed.</p></div></div>
                                <div className="work-review-grid">
                                    <InfoItem label="Task name">{task.name}</InfoItem>
                                    <InfoItem label="Activity code">{task.activity_code}</InfoItem>
                                    <InfoItem label="Task category">{task.category}</InfoItem>
                                    <InfoItem label="Related crop / livestock">{task.related_to}</InfoItem>
                                    <InfoItem label="Assigned employee">{task.employee_name || task.assigned_to || "Unassigned"}</InfoItem>
                                    {task.assignment_source === "Leave Coverage" && (
                                        <>
                                            <InfoItem label="Originally assigned to">{task.original_employee_name || `Employee #${task.original_employee_id || "—"}`}</InfoItem>
                                            <InfoItem label="Temporarily assigned to">{task.covering_employee_name || task.employee_name || "Needs Reassignment"}</InfoItem>
                                            <InfoItem label="Related approved leave">{task.coverage_start_date && task.coverage_end_date ? `${formatDate(task.coverage_start_date)} to ${formatDate(task.coverage_end_date)}` : `Leave #${task.related_leave_id || "—"}`}</InfoItem>
                                            <InfoItem label="Coverage reason" full>{task.coverage_reason || "Temporary assignment during approved leave."}</InfoItem>
                                        </>
                                    )}
                                    <InfoItem label="Location / field / pen">{task.location}</InfoItem>
                                    <InfoItem label="Scheduled date and time">{`${formatDate(task.activity_date)} · ${task.start_time || "—"}${task.end_time ? `–${task.end_time}` : ""}`}</InfoItem>
                                    <InfoItem label="Priority">{task.priority}</InfoItem>
                                    <InfoItem label="Assignment type">{sourceLabel}</InfoItem>
                                    <InfoItem label="Instructions" full>{task.instructions || task.description || "No additional task instructions."}</InfoItem>
                                </div>
                            </section>

                            {submission?.monitoring && <section className="work-review-section">
                                <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">monitoring</span><div><h3>Resource Monitoring</h3><p>Approval saves this dated observation to the linked record. Earlier observations remain in history.</p></div></div>
                                <ObservationSummary observation={submission.monitoring} />
                                <div className="monitoring-panel"><label className="monitoring-field"><span>{submission.monitoring.resource_type === "Crop" ? "Confirm observed crop stage" : "Confirm livestock stage override (optional)"}</span><select value={confirmedStage} disabled={busy} onChange={(event) => { setConfirmedStage(event.target.value); setConfirmedReady(false); }}>
                                    {submission.monitoring.resource_type === "Livestock" && <option value="">Keep current recorded stage</option>}
                                    {(task.monitoring_context?.stage_choices || [submission.monitoring.observed_stage]).filter(Boolean).map((stage) => <option key={stage}>{stage}</option>)}
                                </select></label>
                                {submission.monitoring.resource_type === "Livestock" && <p className="monitoring-note">A stage override requires management permission and a reviewer reason. Weight approval alone does not change the recorded stage.</p>}
                                {submission.monitoring.resource_type === "Crop" && confirmedStage === "Harvest Ready" && <label className="monitoring-check"><input type="checkbox" checked={confirmedReady} disabled={busy} onChange={(event) => setConfirmedReady(event.target.checked)} /> I confirm physical harvest readiness from the inspection and evidence.</label>}
                                </div>
                            </section>}

                            <section className="work-review-section current-submission-section">
                                <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">fact_check</span><div><h3>Employee Work Submission</h3><p>Current pending attempt requiring a manager decision.</p></div></div>
                                <div className="current-submission-badge">Current pending attempt</div>
                                <div className="work-review-grid">
                                    <InfoItem label="Actually performed by">{submission.employee_name || `Employee #${submission.employee_id}`}</InfoItem>
                                    <InfoItem label="Recorded by">{submission.recorded_by_name || submission.employee_name || "Employee self-submission"}</InfoItem>
                                    <InfoItem label="Attempt number">{`Attempt ${submission.attempt_number}`}</InfoItem>
                                    <InfoItem label="Submitted">{formatDateTime(submission.submitted_at)}</InfoItem>
                                    <InfoItem label="Review status">{submission.review_status}</InfoItem>
                                    <InfoItem label="Reported problem">{submission.problem_report || "None reported"}</InfoItem>
                                    <InfoItem label="Employee work notes" full>{submission.worker_notes || "No employee notes submitted."}</InfoItem>
                                </div>
                            </section>

                            <section className="work-review-section">
                                <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">inventory_2</span><div><h3>Resource and Inventory Usage</h3><p>Inventory is posted only when work is approved; pending submissions do not deduct stock.</p></div></div>
                                {!resource?.tracked ? (
                                    <div className="work-review-empty-inline">No tracked inventory resource required</div>
                                ) : (
                                    <>
                                        <div className="work-review-grid">
                                            <InfoItem label="Inventory item">{resource.inventory_item_name ? `${resource.inventory_item_name}${resource.inventory_item_code ? ` (${resource.inventory_item_code})` : ""}` : "Tracked resource"}</InfoItem>
                                            <InfoItem label="Inventory category">{resource.inventory_category || "—"}</InfoItem>
                                            <InfoItem label="Planned quantity">{formatQuantity(resource.planned_quantity, resource.planned_unit)}</InfoItem>
                                            <InfoItem label="Actual quantity">{formatQuantity(resource.actual_quantity, resource.actual_unit)}</InfoItem>
                                            <InfoItem label="Actual vs planned">{differenceLabel}</InfoItem>
                                            <InfoItem label="Inventory deduction status">{resource.deduction_status}</InfoItem>
                                            <InfoItem label="Resource usage ID">{resource.resource_usage_id ? `#${resource.resource_usage_id}` : "—"}</InfoItem>
                                            <InfoItem label="Movement reference">{resource.movement_reference || "—"}</InfoItem>
                                        </div>
                                        <div className="work-review-posted-note"><span className="material-symbols-outlined" aria-hidden="true">check_circle</span><span>{resource.resource_usage_id ? "This record already has an inventory posting. Its movements are listed below." : "Inventory remains reserved until approval. Approving the work deducts the actual quantity; returning it releases the reservation."}</span></div>
                                        {resource.movements?.length > 0 && <div className="review-movement-list" aria-label="Inventory movement history">
                                            {resource.movements.map((movement) => <div className="review-movement-row" key={movement.id}>
                                                <strong>{movement.movement_type}</strong>
                                                <span>{formatQuantity(movement.quantity, resource.actual_unit || resource.planned_unit)}</span>
                                                <span>{movement.reference || `Movement #${movement.id}`}</span>
                                                <small>{formatDateTime(movement.created_at)}</small>
                                            </div>)}
                                        </div>}
                                    </>
                                )}
                            </section>

                            <section className="work-review-section">
                                <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">photo_camera</span><div><h3>Evidence</h3><p>Secure evidence attached to the current work submission.</p></div></div>
                                {submission.evidence_url ? (
                                    <EvidenceInlinePreview evidenceUrl={submission.evidence_url} alt={`Evidence for ${task.name}`} />
                                ) : (
                                    <div className="work-review-empty-inline">{task.requires_evidence ? "No evidence photo was submitted." : "No evidence was required or submitted."}</div>
                                )}
                            </section>

                            <section className="work-review-section">
                                <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">history</span><div><h3>Previous Review History</h3><p>Earlier attempts are retained separately from the current pending submission.</p></div></div>
                                {previousSubmissions.length ? (
                                    <div className="review-history-list">
                                        {previousSubmissions.map((item) => (
                                            <article className="review-history-card" key={item.id}>
                                                <div className="review-history-top"><strong>{`Attempt ${item.attempt_number}`}</strong><span className={`review-result ${String(item.review_status || "").toLowerCase()}`}>{item.review_status}</span></div>
                                                <div className="review-history-grid">
                                                    <span><small>Submitted</small>{formatDateTime(item.submitted_at)}</span>
                                                    <span><small>Reviewer</small>{item.reviewed_by_name || "—"}</span>
                                                    <span><small>Review date</small>{formatDateTime(item.reviewed_at)}</span>
                                                    <span><small>Feedback / reason</small>{item.review_feedback || "No feedback recorded."}</span>
                                                </div>
                                            </article>
                                        ))}
                                    </div>
                                ) : <div className="work-review-empty-inline">No previous submission attempts.</div>}
                            </section>

                            {isCropHarvest && (
                                <section className="work-review-section crop-harvest-review-section">
                                    <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">agriculture</span><div><h3>Harvest Lifecycle Decision</h3><p>The employee reports only this occurrence's actual yield. The manager must decide whether the crop remains active or this is the final harvest.</p></div></div>
                                    <div className="work-review-grid">
                                        <InfoItem label="Employee reported yield">{formatQuantity(submission?.actual_quantity, submission?.actual_unit || "kg")}</InfoItem>
                                        <InfoItem label="Employee reported harvest type">{submission?.harvest_type_intent || "Not selected (legacy submission)"}</InfoItem>
                                        <InfoItem label="Harvest task date">{formatDate(task?.activity_date)}</InfoItem>
                                    </div>
                                    {report?.crop_status === "Harvested" && !report?.harvest_approval_blocker && (
                                        <div className="work-review-harvest-warning" role="note">
                                            <span className="material-symbols-outlined" aria-hidden="true">info</span>
                                            <span>Crops already shows Fully Harvested, but no conflicting final yield is recorded. Confirming this task as Final Harvest will record its reported yield once.</span>
                                        </div>
                                    )}
                                    <label className="review-feedback-field" htmlFor="review-harvest-type">
                                        <span>Harvest type *</span>
                                        <select id="review-harvest-type" value={harvestType} onChange={(event) => { setHarvestType(event.target.value); setFinalHarvestConfirmed(false); setHarvestError(""); }} disabled={busy}>
                                            <option value="Partial Harvest">Partial Harvest</option>
                                            <option value="Final Harvest">Final/Fully Harvested</option>
                                        </select>
                                    </label>
                                    {submission?.harvest_type_intent && harvestType !== submission.harvest_type_intent && (
                                        <div className="review-inline-validation" role="note">You are changing the employee-reported harvest type from {submission.harvest_type_intent} to {harvestType}. Add reviewer feedback explaining the change before approval.</div>
                                    )}
                                    {harvestType === "Final Harvest" && (
                                        <div className="work-review-harvest-warning">
                                            <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                                            <label><input type="checkbox" checked={finalHarvestConfirmed} onChange={(event) => { setFinalHarvestConfirmed(event.target.checked); setHarvestError(""); }} disabled={busy} /> Final Harvest will close this crop cycle and stop future care tasks. I confirm this is the final harvest.</label>
                                        </div>
                                    )}
                                </section>
                            )}

                            <section className="work-review-section reviewer-feedback-section">
                                <div className="work-review-section-title"><span className="material-symbols-outlined" aria-hidden="true">rate_review</span><div><h3>Reviewer Feedback</h3><p>Optional for approval. Required when returning work for correction.</p></div></div>
                                <label className="review-feedback-field" htmlFor="review-feedback">
                                    <span>Feedback to employee</span>
                                    <textarea id="review-feedback" rows="4" value={feedback} onChange={(event) => { setFeedback(event.target.value); if (event.target.value.trim()) setFeedbackError(""); }} disabled={busy} placeholder="Add review notes or explain what needs correction…" />
                                </label>
                                {feedbackError && <div className="review-inline-validation" role="alert">{feedbackError}</div>}
                            </section>
                        </>
                    )}
                </div>

                {(actionError || harvestError || approvalBlocker) && (
                    <div className="work-review-footer-error" role="alert">
                        <span className="material-symbols-outlined" aria-hidden="true">error</span>
                        <span>{actionError || harvestError || approvalBlocker}</span>
                    </div>
                )}
                <footer className="work-review-footer">
                    <div className="work-review-footer-main">
                        <button type="button" className="work-review-return" onClick={submitReturn} disabled={busy || loading || !canReview}>
                            <span className="material-symbols-outlined" aria-hidden="true">assignment_return</span>{processingAction === "Return" ? "Returning…" : "Return for Correction"}
                        </button>
                        <button type="button" className="work-review-approve" onClick={() => {
                            if (!canReview) return;
                            if (isCropHarvest && submission?.harvest_type_intent && harvestType !== submission.harvest_type_intent && !feedback.trim()) {
                                setHarvestError(`Add reviewer feedback explaining why ${submission.harvest_type_intent} is being changed to ${harvestType}.`);
                                return;
                            }
                            if (isCropHarvest && harvestType === "Final Harvest" && !finalHarvestConfirmed) {
                                setHarvestError("Confirm the Final Harvest consequence before approval.");
                                return;
                            }
                            if (submission?.monitoring) {
                                if (submission.monitoring.resource_type === "Crop" && confirmedStage === "Harvest Ready" && !confirmedReady) { setFeedbackError("Confirm physical harvest readiness before approving."); return; }
                                if (confirmedStage && (submission.monitoring.resource_type === "Livestock" || confirmedStage !== submission.monitoring.observed_stage) && !feedback.trim()) { setFeedbackError("Enter reviewer feedback explaining the confirmed stage."); return; }
                            }
                            onApprove?.(feedback.trim() || null, submission?.monitoring
                                ? { confirmed_growth_stage: confirmedStage || null, confirm_harvest_ready: confirmedReady }
                                : isCropHarvest ? { harvest_type: harvestType, final_harvest_confirmed: finalHarvestConfirmed } : {});
                        }} disabled={busy || loading || !canReview || Boolean(approvalBlocker)}>
                            <span className={`material-symbols-outlined${processingAction === "Approve" ? " review-spin" : ""}`} aria-hidden="true">{processingAction === "Approve" ? "progress_activity" : "check_circle"}</span>{processingAction === "Approve" ? "Approving…" : "Approve Work"}
                        </button>
                    </div>
                </footer>
            </div>

        </div>
    );
}
