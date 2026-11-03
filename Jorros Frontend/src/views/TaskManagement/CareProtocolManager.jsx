"use client";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { workforceService } from "../../services/workforceService.js";
import { promptAction, useNotification } from "../../context/NotificationContext.jsx";
import useModalScrollLock from "../../hooks/useModalScrollLock.js";
import { DRAFT_APPROVAL, emptyForm, emptyStep, fromProtocol, protocolPayload } from "./careProtocolForm.js";
import "./CareProtocolManager.css";

export default function CareProtocolManager() {
    const notification = useNotification();
    const [protocols, setProtocols] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState(emptyForm);
    const [step, setStep] = useState(emptyStep);
    const [filter, setFilter] = useState("All");
    const [expandedProtocolId, setExpandedProtocolId] = useState(null);
    const [editorOpen, setEditorOpen] = useState(false);
    const editorRef = useRef(null);
    const savingRef = useRef(false);
    savingRef.current = saving;

    useModalScrollLock(editorOpen);

    const closeEditor = useCallback(() => {
        if (savingRef.current) return;
        setEditorOpen(false);
        setForm(emptyForm());
        setStep(emptyStep());
    }, []);

    useEffect(() => {
        if (!editorOpen) return undefined;

        const previousFocus = document.activeElement;
        editorRef.current?.focus({ preventScroll: true });
        const handleKeyDown = (event) => {
            if (event.key === "Escape" && !savingRef.current) {
                event.preventDefault();
                closeEditor();
            }
            if (event.key !== "Tab" || !editorRef.current) return;
            const focusable = Array.from(editorRef.current.querySelectorAll(
                'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
            )).filter((element) => element.getClientRects().length > 0);
            if (!focusable.length) {
                event.preventDefault();
                editorRef.current.focus({ preventScroll: true });
                return;
            }
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && (document.activeElement === first || !editorRef.current.contains(document.activeElement))) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && (document.activeElement === last || !editorRef.current.contains(document.activeElement))) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", handleKeyDown, true);
        return () => {
            document.removeEventListener("keydown", handleKeyDown, true);
            if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
                previousFocus.focus({ preventScroll: true });
            }
        };
    }, [editorOpen, closeEditor]);

    const openNewProtocol = () => {
        setForm(emptyForm());
        setStep(emptyStep());
        setEditorOpen(true);
    };

    const editProtocol = (protocol) => {
        setForm(fromProtocol(protocol));
        setStep(emptyStep());
        setEditorOpen(true);
    };

    const load = async () => {
        setLoading(true);
        try {
            setProtocols(await workforceService.getCareTemplates(null, true, true) || []);
        } catch (error) {
            notification.error(error?.message || "Unable to load care protocols.", "Care Protocols");
        } finally {
            setLoading(false);
        }
    };

    useFarmModuleUpdates(["care_templates"], load, { editing: editorOpen });
    useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const visible = useMemo(() => protocols.filter((protocol) => filter === "All" || protocol.status === filter), [protocols, filter]);

    const addStep = () => {
        if (!step.title.trim()) {
            notification.error("Enter a step name first.", "Care Protocol");
            return;
        }
        if ((step.resource_product_name.trim() || step.resource_category.trim()) && (!step.planned_quantity || Number(step.planned_quantity) <= 0)) {
            notification.error("Resource-linked steps require a planned quantity.", "Care Protocol");
            return;
        }
        if (Number(step.recurrence_occurrences || 1) > 1 && !step.recurrence_interval_days) {
            notification.error("Recurring steps require an interval in days.", "Care Protocol");
            return;
        }
        setForm((current) => ({ ...current, steps: [...current.steps, { ...step, sequence_number: current.steps.length + 1 }] }));
        setStep(emptyStep());
    };

    const save = async (event) => {
        event.preventDefault();
        if (savingRef.current) return;
        if (!form.name.trim() || !form.target_type.trim()) {
            notification.error("Enter the protocol name and exact crop or animal target.", "Care Protocol");
            return;
        }
        if (!form.steps.length) {
            notification.error("Add at least one protocol step.", "Care Protocol");
            return;
        }
        if (form.steps.some((item) => !String(item.title ?? "").trim() || !String(item.category ?? "").trim())) {
            notification.error("Each protocol step needs a name and category.", "Care Protocol");
            return;
        }
        savingRef.current = true;
        setSaving(true);
        try {
            const payload = protocolPayload(form);
            const saved = form.id
                ? await workforceService.updateCareTemplate(form.id, payload)
                : await workforceService.createCareTemplate(payload);
            notification.success(form.id ? `Draft version ${saved.version} updated.` : "Draft care protocol created.", "Care Protocol");
            setForm(emptyForm());
            setStep(emptyStep());
            setEditorOpen(false);
            await load();
        } catch (error) {
            notification.error(error?.message || "Unable to save care protocol.", "Care Protocol");
        } finally {
            savingRef.current = false;
            setSaving(false);
        }
    };

    const createNewVersion = async (protocol) => {
        try {
            const draft = await workforceService.updateCareTemplate(protocol.id, {});
            editProtocol(draft);
            notification.success(`Draft v${draft.version} created from v${protocol.version}.`, "New Protocol Version");
            await load();
        } catch (error) {
            notification.error(error?.message || "Unable to create a new version.", "Care Protocol");
        }
    };

    const copyProtocol = async (protocol) => {
        try {
            const copy = await workforceService.copyCareTemplate(protocol.id, `${protocol.name} Copy`);
            editProtocol(copy);
            notification.success("Protocol copied as a new Draft family.", "Care Protocol");
            await load();
        } catch (error) {
            notification.error(error?.message || "Unable to copy protocol.", "Care Protocol");
        }
    };

    const publish = async (protocol) => {
        const missing = [
            protocol.approval_status !== "Approved" ? "expert approval" : null,
            !protocol.source_title ? "source title" : null,
            !protocol.source_url ? "source URL" : null,
            !protocol.last_reviewed_date ? "last reviewed date" : null,
            !protocol.steps?.length ? "a protocol step" : null,
        ].filter(Boolean);
        if (missing.length) {
            notification.error(`Complete ${missing.join(", ")} and save the draft before publishing.`, "Care Protocol");
            editProtocol(protocol);
            return;
        }
        try {
            await workforceService.publishCareTemplate(protocol.id, { future_task_action: "keep", apply_to_assigned_targets: false });
            notification.success(`Version ${protocol.version} published. Existing assigned records remain pinned until explicitly updated.`, "Care Protocol");
            await load();
        } catch (error) {
            notification.error(error?.message || "Unable to publish protocol.", "Publish Blocked");
        }
    };

    const deactivate = async (protocol) => {
        const action = await promptAction({
            title: "Deactivate Protocol",
            message: "Choose what should happen to future Pending tasks.",
            label: "Type KEEP or RESOLVE",
            initialValue: "KEEP",
            confirmText: "Continue",
            required: true,
        });
        if (!action) return;
        const normalized = action.trim().toLowerCase();
        if (!["keep", "resolve"].includes(normalized)) {
            notification.error("Enter KEEP or RESOLVE.", "Care Protocol");
            return;
        }
        try {
            await workforceService.deactivateCareTemplate(protocol.id, normalized);
            notification.success("Protocol version deactivated using the selected future-task action.", "Care Protocol");
            await load();
        } catch (error) {
            notification.error(error?.message || "Unable to deactivate protocol.", "Care Protocol");
        }
    };

    const importFile = async (event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file) return;
        try {
            if (file.name.toLowerCase().endsWith(".csv")) {
                const data = new FormData(); data.append("file", file);
                await workforceService.importCareProtocolsCsv(data);
            } else {
                const parsed = JSON.parse(await file.text());
                await workforceService.importCareProtocols(parsed.protocols || parsed);
            }
            notification.success("Protocol file imported as Draft version(s).", "Care Protocol Import");
            await load();
        } catch (error) {
            notification.error(error?.message || "Unable to import protocol file.", "Import Error");
        }
    };

    return (
        <section className="workforce-card care-protocol-manager">
            <div className="care-protocol-heading">
                <div>
                    <h2>Care Protocols</h2>
                    <p className="workforce-card-subtitle">Versioned Crop and Livestock care schedules. Published versions are immutable; edits create a new Draft version.</p>
                </div>
                <div className="care-protocol-heading-actions">
                    <label className="workforce-button secondary care-protocol-import">
                        <span className="material-symbols-outlined" aria-hidden="true">upload_file</span>
                        Import JSON / CSV
                        <input type="file" accept=".json,.csv,application/json,text/csv" onChange={importFile} />
                    </label>
                    <button type="button" className="workforce-button care-protocol-add-button" onClick={openNewProtocol}>
                        <span className="material-symbols-outlined" aria-hidden="true">add</span>
                        Add Protocol
                    </button>
                </div>
            </div>

            {editorOpen && createPortal(
                <div className="care-protocol-modal-overlay workforce-layout" onMouseDown={(event) => event.target === event.currentTarget && closeEditor()}>
                    <section ref={editorRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="care-protocol-modal-title" className="care-protocol-modal">
                        <header className="care-protocol-modal-header">
                            <div>
                                <h2 id="care-protocol-modal-title">{form.id ? `Edit Draft Protocol v${protocols.find((p) => p.id === form.id)?.version || ""}` : "Add Care Protocol"}</h2>
                                <p>Set the target, source, and steps. Save as a draft before publication.</p>
                            </div>
                            <button type="button" className="care-protocol-modal-close" onClick={closeEditor} disabled={saving} aria-label="Close protocol editor">
                                <span className="material-symbols-outlined" aria-hidden="true">close</span>
                            </button>
                        </header>
            <form className="care-protocol-editor" onSubmit={save}>
                <div className="care-protocol-modal-body">
                <div className="care-protocol-editor-title"><h3>Protocol Details</h3></div>
                <div className="workforce-modal-form-grid care-protocol-grid">
                    <div className="workforce-field"><label>Protocol Name</label><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
                    <div className="workforce-field"><label>Module</label><select value={form.module} disabled={Boolean(form.id)} onChange={(e) => setForm({ ...form, module: e.target.value })}><option>Livestock</option><option>Crop</option></select></div>
                    <div className="workforce-field"><label>Exact Target Species / Crop</label><input required placeholder="Pig, Chicken, Tomato, Corn…" value={form.target_type} onChange={(e) => setForm({ ...form, target_type: e.target.value })} /></div>
                    {form.module === "Livestock" ? <div className="workforce-field"><label>Breed <span className="field-optional">optional</span></label><input value={form.target_breed} onChange={(e) => setForm({ ...form, target_breed: e.target.value })} /></div> : <div className="workforce-field"><label>Variety <span className="field-optional">optional</span></label><input value={form.target_variety} onChange={(e) => setForm({ ...form, target_variety: e.target.value })} /></div>}
                    <div className="workforce-field"><label>Production Purpose <span className="field-optional">optional</span></label><input value={form.production_purpose} onChange={(e) => setForm({ ...form, production_purpose: e.target.value })} /></div>
                    <div className="workforce-field"><label>Growth Stage <span className="field-optional">optional</span></label><input value={form.growth_stage} onChange={(e) => setForm({ ...form, growth_stage: e.target.value })} /></div>
                    <div className="workforce-field"><label>Effective From</label><input type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} /></div>
                    <div className="workforce-field"><label>Effective To</label><input type="date" value={form.effective_to} onChange={(e) => setForm({ ...form, effective_to: e.target.value })} /></div>
                    <div className="workforce-field"><label>Approval Status</label><select value={form.approval_status} onChange={(e) => setForm({ ...form, approval_status: e.target.value })}><option>{DRAFT_APPROVAL}</option><option>Approved</option><option>Rejected</option></select></div>
                    <div className="workforce-field"><label>Last Reviewed</label><input type="date" value={form.last_reviewed_date} onChange={(e) => setForm({ ...form, last_reviewed_date: e.target.value })} /></div>
                    <div className="workforce-field full"><label>Description</label><textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
                    <div className="workforce-field"><label>Source Title</label><input value={form.source_title} onChange={(e) => setForm({ ...form, source_title: e.target.value })} /></div>
                    <div className="workforce-field"><label>Source URL</label><input type="url" value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} /></div>
                    <div className="workforce-field full"><label>Citations <span className="field-optional">one per line</span></label><textarea value={form.citations_text} onChange={(e) => setForm({ ...form, citations_text: e.target.value })} /></div>
                </div>
                {form.approval_status === "Approved" && <p className="care-protocol-approval-note">Record approval only after expert review. Add the source title, source URL, and last reviewed date. Save this draft, then use Publish.</p>}

                <div className="care-protocol-step-builder">
                    <h3>Add Protocol Step</h3>
                    <p className="care-protocol-ownership-note">When the same crop or livestock record already schedules this action on the same date, My Tasks shows the built-in task once. Other protocol steps still create work.</p>
                    <div className="workforce-modal-form-grid care-protocol-grid">
                        <div className="workforce-field"><label>Step Name</label><input value={step.title} onChange={(e) => setStep({ ...step, title: e.target.value })} /></div>
                        <div className="workforce-field"><label>Category</label><select value={step.category} onChange={(e) => setStep({ ...step, category: e.target.value })}>{["feeding","fertilizer","pesticide","vaccine","vitamin","inspection","weighing","general care"].map((v) => <option key={v}>{v}</option>)}</select></div>
                        <div className="workforce-field"><label>Timing Basis</label><select value={step.timing_anchor} onChange={(e) => setStep({ ...step, timing_anchor: e.target.value })}>{["base_date","planting_date","birth_date","acquisition_date","age_window","stage","previous_step"].map((v) => <option key={v} value={v}>{v.replaceAll("_", " ")}</option>)}</select></div>
                        <div className="workforce-field"><label>Offset Days</label><input type="number" min="0" value={step.offset_days} onChange={(e) => setStep({ ...step, offset_days: e.target.value })} /></div>
                        {step.timing_anchor === "age_window" && <><div className="workforce-field"><label>Age Start (days)</label><input type="number" min="0" value={step.age_start_days} onChange={(e) => setStep({ ...step, age_start_days: e.target.value })} /></div><div className="workforce-field"><label>Age End (days)</label><input type="number" min="0" value={step.age_end_days} onChange={(e) => setStep({ ...step, age_end_days: e.target.value })} /></div></>}
                        {step.timing_anchor === "previous_step" && <div className="workforce-field"><label>Previous Step #</label><input type="number" min="1" value={step.previous_step_sequence} onChange={(e) => setStep({ ...step, previous_step_sequence: e.target.value })} /></div>}
                        <div className="workforce-field"><label>Repeat Every (days)</label><input type="number" min="1" placeholder="One-time if blank" value={step.recurrence_interval_days} onChange={(e) => setStep({ ...step, recurrence_interval_days: e.target.value })} /></div>
                        <div className="workforce-field"><label>Occurrences</label><input type="number" min="1" max="366" value={step.recurrence_occurrences} onChange={(e) => setStep({ ...step, recurrence_occurrences: e.target.value })} /></div>
                        <div className="workforce-field"><label>Planned Dose / Quantity</label><input type="number" min="0" step="0.001" value={step.planned_quantity} onChange={(e) => setStep({ ...step, planned_quantity: e.target.value })} /></div>
                        <div className="workforce-field"><label>Unit</label><input placeholder="kg, L, mL, pcs" value={step.planned_unit} onChange={(e) => setStep({ ...step, planned_unit: e.target.value })} /></div>
                        <div className="workforce-field"><label>Dose Basis</label><select value={step.dose_basis} onChange={(e) => setStep({ ...step, dose_basis: e.target.value })}><option value="">Not applicable</option>{["per_head","per_kg_body_weight","per_batch","per_plant","per_hectare"].map((v) => <option key={v} value={v}>{v.replaceAll("_", " ")}</option>)}</select></div>
                        <div className="workforce-field"><label>Resource Product <span className="field-optional">generic</span></label><input placeholder="Product name, not lot/batch" value={step.resource_product_name} onChange={(e) => setStep({ ...step, resource_product_name: e.target.value })} /></div>
                        <div className="workforce-field"><label>Resource Category</label><input placeholder="Feed, Fertilizer, Vaccine…" value={step.resource_category} onChange={(e) => setStep({ ...step, resource_category: e.target.value })} /></div>
                        <div className="workforce-field"><label>Withdrawal Interval (days)</label><input type="number" min="0" value={step.withdrawal_interval_days} onChange={(e) => setStep({ ...step, withdrawal_interval_days: e.target.value })} /></div>
                        <div className="workforce-field"><label>Pre-harvest Interval (days)</label><input type="number" min="0" value={step.preharvest_interval_days} onChange={(e) => setStep({ ...step, preharvest_interval_days: e.target.value })} /></div>
                        <div className="workforce-field full"><label>Instructions</label><textarea value={step.instructions} onChange={(e) => setStep({ ...step, instructions: e.target.value })} /></div>
                        <div className="workforce-field full"><label>Safety Notes</label><textarea value={step.safety_notes} onChange={(e) => setStep({ ...step, safety_notes: e.target.value })} /></div>
                        <div className="workforce-field full"><label>Step Citation / Approval Record</label><textarea value={step.source_citation} onChange={(e) => setStep({ ...step, source_citation: e.target.value })} /></div>
                        <label className="care-protocol-check"><input type="checkbox" checked={step.requires_review} onChange={(e) => setStep({ ...step, requires_review: e.target.checked })} /> Manager review required</label>
                        <label className="care-protocol-check"><input type="checkbox" checked={step.requires_evidence} onChange={(e) => setStep({ ...step, requires_evidence: e.target.checked })} /> Photo evidence required</label>
                    </div>
                    <button type="button" className="workforce-button secondary" onClick={addStep}>Add Step</button>
                </div>

                {form.steps.length > 0 && <div className="care-protocol-steps-list">{form.steps.map((item, index) => <div className="care-protocol-step-row" key={`${item.title}-${index}`}><div><strong>{index + 1}. {item.title}</strong><span>{item.category} · {item.timing_anchor.replaceAll("_", " ")} +{item.offset_days || 0} day(s){Number(item.recurrence_occurrences || 1) > 1 ? ` · every ${item.recurrence_interval_days} day(s) × ${item.recurrence_occurrences}` : ""}</span></div><button type="button" className="workforce-button danger small" onClick={() => setForm((current) => ({ ...current, steps: current.steps.filter((_, idx) => idx !== index) }))}>Remove</button></div>)}</div>}

                </div>
                <footer className="care-protocol-editor-actions">
                    <button type="button" className="workforce-button secondary" onClick={closeEditor} disabled={saving}>Cancel</button>
                    <button type="submit" className="workforce-button" disabled={saving}>{saving ? "Saving…" : form.id ? "Save Draft" : "Create Draft"}</button>
                </footer>
            </form>
                    </section>
                </div>,
                document.body
            )}

            <div className="care-protocol-library-heading"><div><h3>Protocol Library</h3><p>Draft presets require licensed-expert approval before publication.</p></div><select aria-label="Filter protocols by status" value={filter} onChange={(e) => setFilter(e.target.value)}><option>All</option><option>Draft</option><option>Published</option><option>Superseded</option><option>Inactive</option></select></div>
            {loading ? <div className="workforce-empty-state">Loading care protocols…</div> : visible.length === 0 ? <div className="workforce-empty-state">No protocols match this filter.</div> : <div className="care-protocol-library">{visible.map((protocol) => <article className="care-protocol-card" key={protocol.id}>
                <div className="care-protocol-card-top"><div><span className={`care-protocol-status ${protocol.status.toLowerCase()}`}>{protocol.status}</span><h3>{protocol.name}</h3><p>{protocol.protocol_family_code} · v{protocol.version} · {protocol.module} · {protocol.target_type || "All targets"}</p></div><span className="care-protocol-approval">{protocol.approval_status}</span></div>
                <p>{protocol.description || "No description."}</p>
                <div className="care-protocol-meta"><span>Steps: {protocol.steps?.length || 0}</span><span>Effective: {protocol.effective_from || "Open"} – {protocol.effective_to || "Open"}</span><span>Reviewed: {protocol.last_reviewed_date || "Not yet"}</span></div>
                {protocol.source_url && <a className="care-protocol-source" href={protocol.source_url} target="_blank" rel="noreferrer">{protocol.source_title || "Authoritative source"}</a>}
                <div className="care-protocol-card-actions">
                    <button
                        type="button"
                        className="workforce-button secondary"
                        aria-expanded={expandedProtocolId === protocol.id}
                        onClick={() => setExpandedProtocolId((current) => current === protocol.id ? null : protocol.id)}
                    >
                        <span className="material-symbols-outlined" aria-hidden="true">visibility</span>
                        {expandedProtocolId === protocol.id ? "Hide Details" : "View"}
                    </button>
                    {protocol.status === "Draft" && <><button type="button" className="workforce-button secondary" onClick={() => editProtocol(protocol)}>Edit Draft</button><button type="button" className="workforce-button" onClick={() => publish(protocol)}>Publish</button></>}
                    {protocol.status !== "Draft" && protocol.status !== "Inactive" && <button type="button" className="workforce-button secondary" onClick={() => createNewVersion(protocol)}>New Version</button>}
                    <button type="button" className="workforce-button secondary" onClick={() => copyProtocol(protocol)}>Copy</button>
                    {protocol.status !== "Inactive" && <button type="button" className="workforce-button danger small" onClick={() => deactivate(protocol)}>Deactivate</button>}
                </div>
                {expandedProtocolId === protocol.id && <div className="care-protocol-details" aria-label={`${protocol.name} protocol details`}>
                    <div className="care-protocol-detail-grid">
                        <span><strong>Target:</strong> {protocol.target_type || "All"}</span>
                        <span><strong>Breed:</strong> {protocol.target_breed || "Any"}</span>
                        <span><strong>Variety:</strong> {protocol.target_variety || "Any"}</span>
                        <span><strong>Purpose:</strong> {protocol.production_purpose || "Any"}</span>
                        <span><strong>Growth stage:</strong> {protocol.growth_stage || "Any"}</span>
                        <span><strong>Source:</strong> {protocol.source_title || "Not supplied"}</span>
                    </div>
                    <div className="care-protocol-detail-steps">
                        {(protocol.steps || []).map((protocolStep) => <div className="care-protocol-detail-step" key={protocolStep.id || protocolStep.sequence_number}>
                            <strong>{protocolStep.sequence_number}. {protocolStep.title}</strong>
                            <span>{protocolStep.category} · {(protocolStep.timing_anchor || "base_date").replaceAll("_", " ")} +{protocolStep.offset_days || 0} day(s)</span>
                            {Number(protocolStep.recurrence_occurrences || 1) > 1 && <span>Recurring every {protocolStep.recurrence_interval_days} day(s) × {protocolStep.recurrence_occurrences}</span>}
                            {(protocolStep.planned_quantity != null || protocolStep.planned_unit) && <span>Planned: {protocolStep.planned_quantity ?? "—"} {protocolStep.planned_unit || ""}{protocolStep.dose_basis ? ` · ${protocolStep.dose_basis.replaceAll("_", " ")}` : ""}</span>}
                            {(protocolStep.resource_product_name || protocolStep.resource_category) && <span>Resource: {protocolStep.resource_product_name || "Any product"}{protocolStep.resource_category ? ` · ${protocolStep.resource_category}` : ""}</span>}
                            <span>Evidence: {protocolStep.requires_evidence ? "Required" : "Not required"} · Review: {protocolStep.requires_review ? "Required" : "Protocol optional (employee-work rules may still require review)"}</span>
                            {protocolStep.instructions && <p>{protocolStep.instructions}</p>}
                            {protocolStep.safety_notes && <p><strong>Safety:</strong> {protocolStep.safety_notes}</p>}
                            {(protocolStep.withdrawal_interval_days != null || protocolStep.preharvest_interval_days != null) && <p><strong>Intervals:</strong> {protocolStep.withdrawal_interval_days != null ? `Withdrawal ${protocolStep.withdrawal_interval_days} day(s)` : ""}{protocolStep.withdrawal_interval_days != null && protocolStep.preharvest_interval_days != null ? " · " : ""}{protocolStep.preharvest_interval_days != null ? `Pre-harvest ${protocolStep.preharvest_interval_days} day(s)` : ""}</p>}
                            {protocolStep.source_citation && <p><strong>Citation:</strong> {protocolStep.source_citation}</p>}
                        </div>)}
                    </div>
                </div>}
            </article>)}</div>}
        </section>
    );
}
