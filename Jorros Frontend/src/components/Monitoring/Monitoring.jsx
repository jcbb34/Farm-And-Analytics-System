"use client";

import { useMemo, useState } from "react";
import { farmDateKey } from "../../utils/farmCalendar.js";
import { initialObservation } from "./monitoring.js";
export { scheduleForm, schedulePayload, normalizeSchedule, initialObservation, observationPayload, validateObservation } from "./monitoring.js";
import "./Monitoring.css";




export function MonitoringScheduleFields({ value, onChange, module = "Crop", earliestDate = "", employees, disabled = false }) {
    const set = (name, next) => onChange({ ...value, [name]: next });
    return <section className="monitoring-panel" aria-label={`${module} monitoring schedule`}>
        <div className="monitoring-heading"><span className="material-symbols-outlined" aria-hidden="true">monitoring</span><div><h3>{module === "Crop" ? "Growth" : "Weight"} Monitoring</h3><p>Recurring tasks go to the assigned employee. Photo evidence and authorized review are required.</p></div></div>
        {employees && <label className="monitoring-field"><span>Responsible employee</span><select value={value.assignedEmployeeId || ""} disabled={disabled} onChange={(event) => set("assignedEmployeeId", event.target.value)}><option value="">Unassigned — manager review required</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>}
        <label className="monitoring-check"><input type="checkbox" checked={Boolean(value.monitoringEnabled)} disabled={disabled} onChange={(event) => onChange({ ...value, monitoringEnabled: event.target.checked, monitoringStartDate: value.monitoringStartDate || (module === "Livestock" && event.target.checked ? farmDateKey() : "") })} /> Enable recurring monitoring</label>
        {value.monitoringEnabled && <div className="monitoring-grid">
            <label className="monitoring-field"><span>First monitoring date {module === "Livestock" ? "*" : "(optional)"}</span><input type="date" min={earliestDate || undefined} required={module === "Livestock"} value={value.monitoringStartDate || ""} disabled={disabled} onChange={(event) => set("monitoringStartDate", event.target.value)} /></label>
            <label className="monitoring-field"><span>Monitoring end date (optional)</span><input type="date" min={value.monitoringStartDate || earliestDate || undefined} value={value.monitoringEndDate || ""} disabled={disabled} onChange={(event) => set("monitoringEndDate", event.target.value)} /></label>
            <label className="monitoring-field"><span>Repeat every (days) {module === "Livestock" ? "*" : "(optional)"}</span><input type="number" min="1" max="365" step="1" required={module === "Livestock"} value={value.monitoringFrequencyDays ?? ""} disabled={disabled} placeholder={module === "Crop" ? "Use crop frequency in Settings" : "Enter your monitoring interval"} onChange={(event) => set("monitoringFrequencyDays", event.target.value)} /></label>
        </div>}
        <p className="monitoring-note">{module === "Crop" ? "Blank dates use the planting/inspection schedule; a blank interval follows Settings." : "Choose the interval from your farm's approved monitoring plan."} Changing the assigned employee updates future pending monitoring; performed work keeps its history.</p>
    </section>;
}




export function MonitoringObservationFields({ context, value, onChange, disabled = false }) {
    if (!context) return null;
    const data = value || initialObservation(context);
    const crop = context.resource_type === "Crop";
    const field = (name, label, options = {}) => <label className="monitoring-field"><span>{label}</span><input {...options} disabled={disabled} value={data[name] ?? ""} onChange={(event) => onChange({ ...data, [name]: event.target.value })} /></label>;
    return <section className="monitoring-panel monitoring-observation"><div className="monitoring-heading"><span className="material-symbols-outlined" aria-hidden="true">fact_check</span><div><h3>{crop ? "Crop observation" : "Livestock measurement"}</h3><p>Enter what you observed. The linked record changes after approval.</p></div></div><div className="monitoring-grid">
        {field("observation_date", "Observation date *", { type: "date", required: true, min: context.earliest_date, max: context.latest_date })}
        <label className="monitoring-field"><span>{crop ? "Observed stage *" : "Proposed stage (optional)"}</span><select disabled={disabled} required={crop} value={data.observed_stage || ""} onChange={(event) => onChange({ ...data, observed_stage: event.target.value })}><option value="">{crop ? "Select observed stage" : "No stage proposal"}</option>{(context.stage_choices || []).map((stage) => <option key={stage}>{stage}</option>)}</select></label>
        {crop ? field("current_surviving", "Surviving plants *", { type: "number", required: true, min: "0", max: context.quantity, step: "1" }) : <>
            {field("animals_measured", "Animals measured *", { type: "number", required: true, min: "1", max: context.quantity, step: "1" })}
            {field("average_weight_kg", "Average weight (kg) *", { type: "number", required: true, min: "0.001", step: "0.001" })}
            {field("total_measured_weight_kg", "Total measured weight (kg)", { type: "number", min: "0.001", step: "0.001" })}
            {field("min_weight_kg", "Minimum measured weight (kg)", { type: "number", required: Number(data.animals_measured) > 1, min: "0.001", step: "0.001" })}
            {field("max_weight_kg", "Maximum measured weight (kg)", { type: "number", required: Number(data.animals_measured) > 1, min: "0.001", step: "0.001" })}
        </>}
    </div>{!crop && <p className="monitoring-note">Record only the animals actually measured. Total measured weight refers to that sample, not an estimated whole-group total. Stage changes need explicit reviewer confirmation.</p>}</section>;
}

export function ObservationSummary({ observation }) {
    if (!observation) return null;
    return <dl className="monitoring-summary"><div><dt>Observation date</dt><dd>{observation.observation_date}</dd></div><div><dt>Observed / proposed stage</dt><dd>{observation.observed_stage || "No stage proposal"}</dd></div>{observation.resource_type === "Crop" ? <div><dt>Surviving plants</dt><dd>{observation.current_surviving}</dd></div> : <><div><dt>Animals measured</dt><dd>{observation.animals_measured}</dd></div><div><dt>Average weight</dt><dd>{observation.average_weight_kg} kg</dd></div><div><dt>Minimum / maximum</dt><dd>{observation.min_weight_kg ?? "Not supplied"} / {observation.max_weight_kg ?? "Not supplied"} kg</dd></div><div><dt>Total measured weight</dt><dd>{observation.total_measured_weight_kg ?? "Not supplied"} kg</dd></div></>}</dl>;
}

export function useHistoryRange(records, dateField) {
    const [range, setRange] = useState({ from: "", to: "" });
    const filtered = useMemo(() => (records || []).filter((row) => {
        const date = row[dateField] || "";
        return (!range.from || date >= range.from) && (!range.to || date <= range.to);
    }), [records, dateField, range]);
    return { range, setRange, filtered };
}

export function HistoryDateRange({ range, onChange, count }) {
    return <div className="monitoring-history-filter" aria-label="Monitoring history date range"><label className="monitoring-field"><span>History from</span><input type="date" max={range.to || undefined} value={range.from} onChange={(event) => onChange({ ...range, from: event.target.value })} /></label><label className="monitoring-field"><span>History to</span><input type="date" min={range.from || undefined} value={range.to} onChange={(event) => onChange({ ...range, to: event.target.value })} /></label><button type="button" onClick={() => onChange({ from: "", to: "" })}>Clear dates</button><span role="status">{count} record{count === 1 ? "" : "s"}</span></div>;
}

export function MonitoringStatus({ summary }) {
    if (!summary) return null;
    return <div className="monitoring-table-meta"><span className={`monitoring-state ${summary.state === "Overdue" ? "overdue" : ""}`}>{summary.state}</span><small>Last inspection: {summary.last_date || "Not recorded"}</small>{summary.next_date && <small>Next: {summary.next_date}</small>}</div>;
}
