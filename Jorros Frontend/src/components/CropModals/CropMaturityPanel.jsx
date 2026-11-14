"use client";

import { useCallback, useEffect, useState } from "react";
import { cropService } from "../../services/cropService.js";
import "./CropMaturityPanel.css";

const dateKey = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
};
const niceDate = (value) => value ? new Date(`${String(value).slice(0,10)}T12:00:00Z`).toLocaleDateString("en-PH", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "Not estimated";
const readinessName = {
    not_estimated: "Not estimated",
    growing: "Growing",
    approaching_harvest: "Approaching harvest",
    inspection_required: "Inspection required",
    confirmed_ready: "Ready for harvest (confirmed)",
    harvesting: "Harvesting",
    completed: "Cycle completed",
};

export default function CropMaturityPanel({ crop, canRecord = false, canSchedule = false, onUpdated }) {
    const [plan, setPlan] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [eventDate, setEventDate] = useState(dateKey());
    const [eventNotes, setEventNotes] = useState("");
    const [harvestDate, setHarvestDate] = useState("");
    const [overrideReason, setOverrideReason] = useState("");
    const [saving, setSaving] = useState(false);
    const [formError, setFormError] = useState("");
    const [feedback, setFeedback] = useState("");

    const load = useCallback(async () => {
        setLoading(true); setLoadError("");
        try {
            const result = await cropService.getMaturityPlan(crop.id);
            setPlan(result);
            const suggestion = result.next_cycle_earliest || result.earliest_harvest;
            setHarvestDate((current) => current || (suggestion && suggestion >= dateKey() ? suggestion : ""));
        } catch (error) {
            setLoadError(error?.message || "Maturity reference could not be loaded.");
        } finally { setLoading(false); }
    }, [crop.id]);

    useEffect(() => {
        void load();
    }, [load]);

    const recordEvent = async (event) => {
        event.preventDefault();
        if (!plan?.anchor_kind || plan.anchor_kind === "planting" || saving) return;
        if (!eventDate || eventDate > dateKey() || (crop.plantingDate && eventDate < crop.plantingDate)) {
            setFormError("Enter the actual observation date, not a future date or a date before planting.");
            return;
        }
        setSaving(true); setFormError(""); setFeedback("");
        try {
            await cropService.saveMaturityEvent(crop.id, { event_kind: plan.anchor_kind, observed_date: eventDate, notes: eventNotes.trim() || null });
        } catch (error) {
            setFormError(error?.message || "Unable to record the observed growth event.");
            setSaving(false);
            return;
        }
        // The write has committed: a later refresh error must not invite a
        // duplicate observation submission.
        setEventNotes(""); setHarvestDate("");
        setFeedback("Growth observation saved. The maturity estimate can now be refreshed.");
        setSaving(false);
        try { await load(); await onUpdated?.(); }
        catch (error) { console.warn("Growth event saved but page refresh failed:", error); setFeedback("Observation saved. Reopen the crop to refresh the reference window."); }
    };
    const scheduleHarvest = async (event) => {
        event.preventDefault();
        if (!plan || !harvestDate || saving) return;
        if (harvestDate < dateKey()) { setFormError("Choose today or a future date for the harvest task."); return; }
        setSaving(true); setFormError(""); setFeedback("");
        try {
            await cropService.scheduleMaturityHarvest(crop.id, { expected_harvest: harvestDate, reason: overrideReason.trim() || null });
        } catch (error) {
            setFormError(error?.message || "Unable to schedule the harvest date.");
            setSaving(false);
            return;
        }
        setFeedback("Harvest schedule saved. Its task is available in Task Management; readiness still needs inspection.");
        setSaving(false);
        try { await load(); await onUpdated?.(); }
        catch (error) { console.warn("Harvest schedule saved but page refresh failed:", error); setFeedback("Schedule saved. Reopen the crop to refresh the task and date."); }
    };

    const expectedFirst = plan?.next_cycle_earliest || plan?.earliest_harvest;
    const expectedLast = plan?.next_cycle_latest || plan?.latest_harvest;
    const isNext = Boolean(plan?.next_cycle_earliest);
    const dateOutside = Boolean(harvestDate && expectedFirst && expectedLast && (harvestDate < expectedFirst || harvestDate > expectedLast));
    const hasSuggestion = Boolean(expectedFirst && expectedLast);
    const eventLabel = plan?.anchor_kind === "shooting" ? "Banana shooting date" : "Coconut flowering date";
    const availableForChanges = !["Harvested", "Failed"].includes(crop.status);

    return (
        <section className="crop-details-section crop-maturity-panel" aria-label="Variety growth and harvest planning">
            <div className="crop-details-section-heading">
                <div>
                    <h3>Variety Growth &amp; Harvest Plan</h3>
                    <p>Plan with crop-specific maturity references. Only a physical inspection confirms harvest readiness.</p>
                </div>
                <button type="button" className="crop-maturity-refresh" onClick={load} disabled={loading || saving}>Refresh</button>
            </div>
            {loading && !plan && <p role="status">Loading maturity reference…</p>}
            {loadError && <div role="alert" className="crop-maturity-error">{loadError} <button type="button" onClick={load}>Retry</button></div>}
            {plan && <>
                <div className="crop-maturity-stats">
                    <div><small>Current growth phase</small><strong>{plan.growth_phase || "Not estimated"}</strong></div>
                    <div><small>Readiness</small><strong>{readinessName[plan.readiness_state] || "Inspection required"}</strong></div>
                    <div><small>{isNext ? "Next harvest suggestion" : "Estimated maturity window"}</small><strong>{hasSuggestion ? `${niceDate(expectedFirst)} – ${niceDate(expectedLast)}` : "Not estimated"}</strong></div>
                    <div><small>Saved harvest date</small><strong>{plan.recorded_expected_harvest ? niceDate(plan.recorded_expected_harvest) : "Not scheduled"}</strong></div>
                </div>
                <div className="crop-maturity-reference">
                    <strong>{plan.crop} — {plan.variety}</strong>
                    <span>{plan.anchor_kind === "shooting" ? "Estimate starts from shooting, not planting." : plan.anchor_kind === "flowering" ? "Fruit maturity estimate starts from observed flowering." : plan.anchor_kind === "planting" ? "Estimate starts from recorded planting date." : "This variety needs observations and a verified maturity reference."}</span>
                    <span>{plan.min_days != null ? `Reference: ${plan.min_days}–${plan.max_days} days` : "No verified variety-specific maturity period; inspect actual plant condition."}</span>
                    <span className="crop-maturity-source">{plan.source || "Reference not available"} · Profile v{plan.version}</span>
                </div>
                {availableForChanges && plan.anchor_kind && !["planting"].includes(plan.anchor_kind) && canRecord && <form onSubmit={recordEvent} className="crop-maturity-form">
                    <h4>Record actual {plan.anchor_kind}</h4>
                    <div className="crop-maturity-fields">
                        <label>{eventLabel}<input type="date" required value={eventDate} min={crop.plantingDate || undefined} max={dateKey()} onChange={event=>setEventDate(event.target.value)} disabled={saving}/></label>
                        <label>Observation notes (optional)<input type="text" maxLength={1000} value={eventNotes} onChange={event=>setEventNotes(event.target.value)} placeholder="What was observed?" disabled={saving}/></label>
                        <button type="submit" disabled={saving}>{saving ? "Saving…" : "Record observation"}</button>
                    </div>
                </form>}
                {availableForChanges && canSchedule && hasSuggestion && <form onSubmit={scheduleHarvest} className="crop-maturity-form">
                    <h4>{isNext ? "Schedule the next harvest cycle" : "Schedule expected harvest"}</h4>
                    <div className="crop-maturity-fields">
                        <label>Expected harvest date<input type="date" min={dateKey()} required value={harvestDate} onChange={event=>setHarvestDate(event.target.value)} disabled={saving}/></label>
                        <button type="submit" disabled={saving || !harvestDate}>{saving ? "Saving…" : "Save harvest schedule"}</button>
                    </div>
                    {dateOutside && <label className="crop-maturity-override">Reason for scheduling outside the suggested window<input required maxLength={500} value={overrideReason} onChange={event=>setOverrideReason(event.target.value)} placeholder="Explain the farm observation or planning reason" disabled={saving}/></label>}
                    <p className="crop-maturity-hint">Saving creates or updates a future harvest task. Reminders remain separate; the date does not confirm physical readiness.</p>
                </form>}
                {!hasSuggestion && <p className="crop-maturity-hint">A verified event or reference is not available to calculate this crop's harvest window. You can still set an expected harvest date in Edit Crop after assessing the planting.</p>}
                {formError && <p role="alert" className="crop-maturity-error">{formError}</p>}
                {feedback && <p role="status" className="crop-maturity-success">{feedback}</p>}
            </>}
        </section>
    );
}
