"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { farmEventService } from "../../services/farmEventService.js";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";
import { EVENT_KINDS, eventForm, eventLocalTime, eventTouchesDate } from "./eventView.js";
import "./FarmEvents.css";

const Icon = ({ children }) => <span className="material-symbols-outlined" aria-hidden="true">{children}</span>;
function Button({ children, secondary = false, ...props }) {
    return <button type="button" className={`workforce-button ${secondary ? "secondary" : ""}`} {...props}>{children}</button>;
}
function HeldTaskReview({ row, event, employees, run, busy }) {
    const [action, setAction] = useState("Release");
    const [reason, setReason] = useState("");
    const [employee, setEmployee] = useState("");
    const [newDate, setNewDate] = useState("");
    const [start, setStart] = useState("");
    const [end, setEnd] = useState("");
    return <article className="farm-event-record">
        <div className="farm-event-row"><div><strong>{row.name}</strong><p>{row.code} · {row.date} {row.start_time?.slice(0, 5)} · {row.assigned_to}</p></div><span className="farm-event-badge">{row.resolution}</span></div>
        <small>Original schedule: {row.original.date} {row.original.start_time?.slice(0, 5)} · {row.original.status}</small>
        {row.essential_review && <p className="farm-event-warning">Essential or time-sensitive care: review individually. Rescheduling is restricted.</p>}
        {row.review_reason && <p>Last decision: {row.review_reason}</p>}
        {row.can_review && <form className="farm-event-form farm-event-task-form" onSubmit={(e) => {
            e.preventDefault();
            run(() => farmEventService.review(event.id, row.id, { expected_version: row.version, action, reason,
                employee_id: employee ? Number(employee) : null, new_date: newDate || null, start_time: start || null, end_time: end || null }));
        }}>
            <label>Decision<select aria-label="Decision" value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="Release">Release after reopening</option>
                <option value="Reschedule" disabled={row.essential_review || row.time_sensitive}>Reschedule routine work</option>
                <option value="Reassign">Reassign</option><option value="Essential Duty">Authorize essential duty</option><option value="Cancel">Cancel task with reason</option>
            </select></label>
            {["Reassign", "Essential Duty"].includes(action) && <label>Authorized employee<select aria-label="Authorized employee" required value={employee} onChange={(e) => setEmployee(e.target.value)}><option value="">Select employee</option>{employees.map((x) => <option key={x.id} value={x.id}>{x.full_name}</option>)}</select></label>}
            {action === "Reschedule" && <><label>New date<input type="date" required value={newDate} onChange={(e) => setNewDate(e.target.value)} /></label><label>Start<input type="time" required value={start} onChange={(e) => setStart(e.target.value)} /></label><label>End<input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></label></>}
            <label className="full">Decision reason<textarea rows={2} required minLength={3} maxLength={3000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
            <div className="full farm-event-actions"><button className="workforce-button" disabled={busy}>{busy ? "Saving…" : "Save Task Decision"}</button></div>
        </form>}
    </article>;
}

export function FarmEventPanel({ onClose, onChanged, employees = [], events = [], date, timezone = "Asia/Manila", initial = null, initialId = null, canManage = false }) {
    const modal = useRef(null);
    const previousFocus = useRef(null);
    const createKey = useRef(null);
    const [ready, setReady] = useState(false);
    const [event, setEvent] = useState(null);
    const [form, setForm] = useState(() => eventForm(initial || {}, date, timezone));
    const [editing, setEditing] = useState(Boolean(initial));
    const [tab, setTab] = useState("details");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [impact, setImpact] = useState(null);
    const [decisionReason, setDecisionReason] = useState("");
    const [taskPage, setTaskPage] = useState({ items: [], total: 0, offset: 0 });
    const [report, setReport] = useState({ area: "", description: "" });
    const show = async (id) => { const next = await farmEventService.get(id); setEvent(next); setForm(eventForm(next, date, timezone)); setEditing(false); setImpact(null); return next; };
    const run = async (operation, { reload = true } = {}) => {
        if (busy) return;
        setBusy(true); setError("");
        try {
            const result = await operation();
            if (reload && event?.id) {
                await show(event.id);
                if (tab === "tasks") setTaskPage(await farmEventService.tasks(event.id, taskPage.offset));
            }
            onChanged?.();
            return result;
        } catch (err) { setError(err?.message || "Unable to save. Your entries are still here."); }
        finally { setBusy(false); }
    };
    useEffect(() => {
        setReady(true); previousFocus.current = document.activeElement;
        const overflow = document.body.style.overflow; document.body.style.overflow = "hidden";
        return () => { document.body.style.overflow = overflow; previousFocus.current?.focus?.(); };
    }, []);
    useEffect(() => {
        if (!ready) return;
        modal.current?.querySelector("button, input")?.focus();
        const trap = (e) => {
            if (e.key === "Escape") { if (!busy) onClose(); return; }
            if (e.key !== "Tab") return;
            const focusable = [...modal.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')].filter((x) => x.getClientRects().length);
            const first = focusable[0], last = focusable.at(-1);
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
        };
        document.addEventListener("keydown", trap); return () => document.removeEventListener("keydown", trap);
    }, [ready, busy, onClose]);
    useEffect(() => { if (initialId) show(initialId).catch((err) => setError(err.message)); }, [initialId]); // A fresh record is loaded only when opening, never over a form being edited.
    const saveDraft = async (preview = false) => {
        if (event && !event.can_edit) return;
        await run(async () => {
            createKey.current ||= globalThis.crypto?.randomUUID?.() || `farm-event-${Date.now()}-${Math.random()}`;
            const saved = event?.id ? await farmEventService.update(event.id, { ...form, expected_version: event.version })
                : await farmEventService.create({ ...form, request_key: createKey.current });
            const next = await show(saved.id);
            if (preview) setImpact(await farmEventService.preview(next.id));
        }, { reload: false });
    };
    const change = (field, value) => { setForm((old) => ({ ...old, [field]: value })); setImpact(null); };
    const loadTasks = (offset = 0) => run(async () => { setTaskPage(await farmEventService.tasks(event.id, offset)); setTab("tasks"); }, { reload: false });
    const decide = (action) => run(() => farmEventService.decide(event.id, action, { expected_version: event.version, reason: decisionReason, preview_token: impact?.preview_token }));
    if (!ready) return null;
    return createPortal(<div className="farm-events-overlay workforce-layout" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
        <section className="farm-events-modal" role="dialog" aria-modal="true" aria-labelledby="farm-events-title" ref={modal}>
            <header className="farm-events-header"><div><span className="farm-events-eyebrow">STAFF CALENDAR</span><h2 id="farm-events-title">{editing ? (event ? "Edit Farm Declaration" : "Add Farm Event") : event?.title || "Farm Events & No-Work Days"}</h2><p>Times use {timezone}. Emergency suspensions require explicit reopening.</p></div><Button secondary onClick={onClose} disabled={busy} aria-label="Close farm events"><Icon>close</Icon></Button></header>
            <div className="farm-events-body">
                {error && <div className="workforce-error" role="alert">{error}{event && <Button secondary onClick={() => run(() => show(event.id), { reload: false })} disabled={busy}>Load Latest Record</Button>}</div>}
                {!event && !editing && <><div className="farm-event-row"><p>Prepare a draft, review the impact, then request Owner/Admin approval.</p>{canManage && <Button onClick={() => { createKey.current = null; setForm(eventForm({}, date, timezone)); setEditing(true); }}> <Icon>add</Icon>Add Farm Event</Button>}</div>
                    {!events.length && <p className="farm-event-empty">No declarations in the displayed calendar range.</p>}
                    {events.map((x) => <button className="farm-event-list-item" key={x.id} disabled={busy} onClick={() => run(() => show(x.id), { reload: false })}><span><strong>{x.title}</strong><small>{x.kind} · {eventLocalTime(x.starts_at, timezone).replace("T", " ")} → {eventLocalTime(x.ends_at, timezone).replace("T", " ")}</small></span><span className="farm-event-badge">{x.status}</span><Icon>chevron_right</Icon></button>)}</>}
                {event && !editing && <><div className="farm-event-row"><Button secondary disabled={busy} onClick={() => { setEvent(null); setTab("details"); }}> <Icon>arrow_back</Icon>All Events</Button><span className="farm-event-badge">{event.status}</span></div>
                    <nav className="workforce-tabs workforce-primary-tabs farm-event-tabs" aria-label="Farm event sections">
                        <button className={`workforce-tab workforce-primary-tab ${tab === "details" ? "active" : ""}`} onClick={() => setTab("details")}>Details</button>
                        {event.can_manage && <button disabled={busy} className={`workforce-tab workforce-primary-tab ${tab === "tasks" ? "active" : ""}`} onClick={() => loadTasks()}>Affected Work</button>}
                        {event.can_manage && <button className={`workforce-tab workforce-primary-tab ${tab === "history" ? "active" : ""}`} onClick={() => setTab("history")}>History & Acknowledgements</button>}
                    </nav></>}
                {editing ? <form className="farm-event-form" onSubmit={(e) => { e.preventDefault(); saveDraft(true); }}>
                    <label className="full">Title *<input required minLength={3} maxLength={150} value={form.title} onChange={(e) => change("title", e.target.value)} /></label>
                    <label>Event type<select aria-label="Event type" value={form.kind} onChange={(e) => change("kind", e.target.value)}>{EVENT_KINDS.map((x) => <option key={x}>{x}</option>)}</select></label>
                    <label>Affected people / areas<select aria-label="Affected people / areas" value={form.scope_type} onChange={(e) => { change("scope_type", e.target.value); change("scope_values", []); }}><option value="All">Whole farm</option><option value="Employees">Selected employees</option><option value="Areas">Selected areas</option></select></label>
                    {form.scope_type === "Employees" && <fieldset className="full farm-event-employee-options"><legend>Affected employees *</legend>{employees.map((x) => <label key={x.id}><input type="checkbox" checked={form.scope_values.includes(String(x.id))} onChange={(e) => change("scope_values", e.target.checked ? [...form.scope_values, String(x.id)] : form.scope_values.filter((id) => id !== String(x.id)))} />{x.full_name}</label>)}</fieldset>}
                    {form.scope_type === "Areas" && <label className="full">Affected areas *<input required placeholder="Field A, Piglet Pen (separate areas with commas)" value={form.scope_values.join(",")} onChange={(e) => change("scope_values", e.target.value.split(","))} /><small>Use the same area names as employee assignments and task locations.</small></label>}
                    <label>Starts *<input type="datetime-local" required value={form.starts_at} onChange={(e) => change("starts_at", e.target.value)} /></label>
                    <label>{form.kind === "Emergency Suspension" ? "Expected end *" : "Ends *"}<input type="datetime-local" required min={form.starts_at} value={form.ends_at} onChange={(e) => change("ends_at", e.target.value)} /></label>
                    <label className="full">Reason *<textarea required rows={3} minLength={3} maxLength={3000} value={form.reason} onChange={(e) => change("reason", e.target.value)} /></label>
                    <label className="full">Employee instructions<textarea rows={3} maxLength={5000} value={form.instructions} onChange={(e) => change("instructions", e.target.value)} /></label>
                    <label>Source / issuing authority<input maxLength={150} placeholder="e.g. Owner, PAGASA bulletin, LGU advisory" value={form.source_name} onChange={(e) => change("source_name", e.target.value)} /></label>
                    <label>Reference / bulletin<input maxLength={600} value={form.source_reference} onChange={(e) => change("source_reference", e.target.value)} /></label>
                    <p className="full farm-event-warning">Drafts do not affect work. Approval holds unfinished affected tasks and excuses attendance only during the declared hours. Completed and submitted work keeps its history.</p>
                    <div className="full farm-event-actions"><Button secondary disabled={busy} onClick={() => { if (event) { setForm(eventForm(event, date, timezone)); setEditing(false); } else setEditing(false); }}>Cancel</Button><button className="workforce-button secondary" type="button" disabled={busy} onClick={(e) => { if (e.currentTarget.form.reportValidity()) saveDraft(false); }}>Save Draft</button><button className="workforce-button" disabled={busy}>{busy ? "Saving…" : "Save & Preview Impact"}</button></div>
                </form> : event && tab === "details" ? <>
                    <dl className="farm-event-facts"><div><dt>Type</dt><dd>{event.kind}</dd></div><div><dt>Scope</dt><dd>{event.scope_type === "All" ? "Whole farm" : event.scope_type}{event.scope_type === "Areas" ? `: ${event.scope_values.join(", ")}` : ""}</dd></div><div><dt>Starts</dt><dd>{eventLocalTime(event.starts_at, timezone).replace("T", " ")}</dd></div><div><dt>{event.requires_reopening ? "Expected end" : "End"}</dt><dd>{eventLocalTime(event.ended_at || event.ends_at, timezone).replace("T", " ")}</dd></div></dl>
                    <h3>Reason & Instructions</h3><p className="farm-event-preserve">{event.reason}</p><p className="farm-event-preserve">{event.instructions || "No additional instructions recorded."}</p>
                    {event.source_name && <p>Source: {event.source_name} {event.source_reference}</p>}
                    {event.requires_reopening && <p className="farm-event-warning">Work remains suspended until Owner/Admin records reopening, even after the expected end.</p>}
                    {event.end_reason && <p>Ending decision: {event.end_reason}</p>}
                    {event.can_edit && <div className="farm-event-actions"><Button secondary disabled={busy} onClick={() => setEditing(true)}>Edit Draft</Button><Button disabled={busy} onClick={() => run(async () => setImpact(await farmEventService.preview(event.id)), { reload: false })}>Preview Impact</Button></div>}
                    {impact && <section className="farm-event-record" aria-label="Impact preview"><h3>Impact Preview</h3><p>{impact.employee_count} employees · {impact.task_count} tasks to hold · {impact.essential_task_count} essential tasks to review · {impact.protected_task_count} protected completed/submitted records</p>
                        {impact.overlaps.length > 0 && <p className="farm-event-warning">Overlaps: {impact.overlaps.map((x) => x.title).join(", ")}. Each declaration must be reviewed separately.</p>}
                        <p>Affected employees: {impact.employees.map((x) => x.name).join(", ") || "None"}</p>
                        <ul>{impact.tasks.map((x) => <li key={x.id}>{x.date} · {x.name}{x.essential ? " · Essential care" : ""}</li>)}</ul>
                        {impact.task_count > impact.tasks.length && <small>Showing the first {impact.tasks.length} tasks. All affected tasks are held on approval.</small>}
                        {!event.can_approve && <p>Owner/Admin approval is required.</p>}
                    </section>}
                    {event.can_approve && !["Cancelled", "Ended"].includes(event.status) && <section className="farm-event-record"><label className="farm-event-decision-label">Decision reason *<textarea rows={2} minLength={3} maxLength={3000} value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} /></label><div className="farm-event-actions">
                        {event.status === "Draft" && <Button disabled={busy || !impact || decisionReason.trim().length < 3} onClick={() => decide("approve")}>Approve Declaration</Button>}
                        {event.approved_at && <Button disabled={busy || decisionReason.trim().length < 3} onClick={() => decide("end")}>{event.requires_reopening ? "Record Reopening" : "End Declaration"}</Button>}
                        <Button secondary disabled={busy || decisionReason.trim().length < 3} onClick={() => decide("cancel")}>Cancel Declaration</Button>
                    </div></section>}
                    {event.can_acknowledge && <section className="farm-event-record"><h3>Employee Notice</h3><p>Acknowledging this notice records that you have read it. Attendance is recorded separately.</p><Button disabled={busy || event.acknowledged} onClick={() => run(() => farmEventService.acknowledge(event.id, event.notice_version))}>{event.acknowledged ? "Acknowledged" : "I Have Read This Notice"}</Button></section>}
                    {event.can_manage && event.checklist.length > 0 && <section className="farm-event-record"><h3>Farm Protocol Checklist</h3>{["Before", "During", "After"].map((phase) => <fieldset className="farm-event-checklist" key={phase}><legend>{phase}</legend>{event.checklist.filter((x) => x.phase === phase).map((x) => <label key={x.id}><input type="checkbox" disabled={busy} checked={x.completed} onChange={(e) => run(() => farmEventService.checklist(event.id, { expected_version: event.version, item_id: x.id, completed: e.target.checked }))} />{x.text}</label>)}</fieldset>)}</section>}
                    {event.approved_at && <section className="farm-event-record"><h3>Damage / Observation Report</h3><p>Record what you observed. Crop, livestock and inventory quantities require their normal review workflows.</p><form className="farm-event-form" onSubmit={(e) => { e.preventDefault(); run(async () => { await farmEventService.report(event.id, report); setReport({ area: "", description: "" }); }); }}><label className="full">Area *<input required maxLength={150} value={report.area} onChange={(e) => setReport({ ...report, area: e.target.value })} /></label><label className="full">Observation *<textarea required minLength={3} rows={3} maxLength={5000} value={report.description} onChange={(e) => setReport({ ...report, description: e.target.value })} /></label><div className="full farm-event-actions"><button disabled={busy} className="workforce-button">Submit Observation</button></div></form>{event.reports?.map((x) => <p className="farm-event-preserve" key={x.id}><strong>{x.area}</strong> · {x.description}</p>)}</section>}
                </> : event && tab === "tasks" ? <section><p>Review each task. Routine work is released only after reopening. Essential duty requires an authorized employee and a reason.</p>{!taskPage.items.length && <p>No held tasks recorded.</p>}{taskPage.items.map((row) => <HeldTaskReview key={`${row.id}:${row.version}`} row={row} event={event} employees={employees} busy={busy} run={run} />)}<div className="farm-event-row"><span>{taskPage.total} affected task records</span><div className="farm-event-actions"><Button secondary disabled={busy || !taskPage.offset} onClick={() => loadTasks(Math.max(0, taskPage.offset - 25))}>Previous</Button><Button secondary disabled={busy || taskPage.offset + 25 >= taskPage.total} onClick={() => loadTasks(taskPage.offset + 25)}>Next</Button></div></div></section> : event && tab === "history" ? <section><h3>Employee Acknowledgements</h3>{!event.acknowledgements?.length && <p>No acknowledgements yet.</p>}{event.acknowledgements?.map((x, i) => <p key={i}>{x.employee_name} · Notice {x.notice_version} · {eventLocalTime(x.acknowledged_at, timezone).replace("T", " ")}</p>)}<h3>Decision History</h3>{event.audit?.map((x) => <article className="farm-event-record" key={x.id}><strong>{x.action} · {x.actor_name}</strong><p>{x.reason}</p><small>{eventLocalTime(x.created_at, timezone).replace("T", " ")}</small></article>)}</section> : null}
            </div>
        </section>
    </div>, document.body);
}

export function FarmEventNotices({ date, timezone = "Asia/Manila" }) {
    const [events, setEvents] = useState([]);
    const [selected, setSelected] = useState(null);
    const [error, setError] = useState("");
    const load = useCallback(async () => {
        try { const rows = await farmEventService.list(date, date); setEvents(rows || []); setError(""); }
        catch (err) { setError(err?.message || "Farm notices could not be loaded."); }
    }, [date]);
    useEffect(() => { load(); }, [load]);
    useFarmModuleUpdates(["calendar", "my_tasks"], load, { editing: Boolean(selected) });
    return <>{error && <div className="workforce-error" role="alert">{error} <Button secondary onClick={load}>Retry Notices</Button></div>}{events.filter((x) => x.status !== "Cancelled").map((x) => <section className="farm-event-notice" key={x.id}><Icon>{x.kind === "Emergency Suspension" ? "warning" : "event_busy"}</Icon><div><strong>{x.title} · {x.status}</strong><p>{x.instructions || x.reason}</p><small>{x.kind} · {eventLocalTime(x.starts_at, timezone).replace("T", " ")} → {x.requires_reopening ? "until Owner/Admin reopens work" : eventLocalTime(x.ended_at || x.ends_at, timezone).replace("T", " ")}{x.acknowledged ? " · Acknowledged" : ""}</small></div><Button secondary onClick={() => setSelected(x.id)}>Read Notice</Button></section>)}{selected && <FarmEventPanel initialId={selected} events={events} date={date} timezone={timezone} onClose={() => setSelected(null)} onChanged={load} />}</>;
}

export function CalendarEventBands({ events = [], date, timezone, onOpen }) {
    const visible = events.filter((x) => !["Draft", "Cancelled"].includes(x.status) && (!date || eventTouchesDate(x, date, timezone)));
    if (!visible.length) return null;
    return <div className="farm-calendar-events" aria-label="Farm declarations">{visible.map((x) => <button className="farm-calendar-event" key={x.id} type="button" onClick={() => onOpen(x.id)}><Icon>{x.kind === "Emergency Suspension" ? "warning" : "event"}</Icon><span>{x.title} · {x.status}</span></button>)}</div>;
}
