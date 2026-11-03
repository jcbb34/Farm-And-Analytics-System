"use client";

import "./WeeklyScheduleEditor.css";

import { WEEK_DAYS, applyWeeklyScheduleTemplate } from "./weeklySchedule.js";

export { makeWeeklySchedule, normalizeWeeklySchedule, validateWeeklySchedule } from "./weeklySchedule.js";

export default function WeeklyScheduleEditor({ value, onChange, employees = [], employeeId = null, needsSetup = false, minEffectiveDate = "" }) {
    const updateDay = (index, patch) => {
        const next = value.days.map((day, dayIndex) => {
            if (dayIndex !== index) return day;
            const updated = { ...day, ...patch };
            if (updated.state === "Rest Day") {
                return { ...updated, start_time: null, end_time: null, break_start_time: null, break_end_time: null };
            }
            return {
                ...updated,
                start_time: updated.start_time || "08:00",
                end_time: updated.end_time || "17:00",
                break_start_time: updated.break_start_time || "12:00",
                break_end_time: updated.break_end_time || "13:00",
            };
        });
        onChange({ ...value, days: next });
    };

    return (
        <section className="weekly-schedule-editor" aria-label="Weekly Work Schedule">
            {needsSetup && <div className="schedule-needs-setup" role="status"><span className="material-symbols-outlined">warning</span><div><strong>Schedule setup required</strong><span>Legacy availability remains in use until this weekly schedule is saved.</span></div></div>}
            <div className="weekly-schedule-top-grid">
                <label><span>Effective Start <b>*</b></span><input type="date" required min={minEffectiveDate || undefined} value={value.effective_from || ""} onChange={(event) => onChange({ ...value, effective_from: event.target.value })} /></label>
                <label><span>Effective End <small>Optional</small></span><input type="date" min={value.effective_from || undefined} value={value.effective_to || ""} onChange={(event) => onChange({ ...value, effective_to: event.target.value || null })} /></label>
                <label><span>Configured Backup Employee</span><select value={value.backup_employee_id || ""} onChange={(event) => onChange({ ...value, backup_employee_id: event.target.value })}><option value="">No configured backup</option>{employees.filter((employee) => employee.employment_status === "Active" && !employee.is_archived && String(employee.id) !== String(employeeId || "")).map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}</select></label>
            </div>
            <div className="schedule-template-row" aria-label="Quick schedule templates">
                <span>Quick templates</span>
                <button type="button" onClick={() => onChange(applyWeeklyScheduleTemplate(value, "mon-sat"))}>Mon–Sat / Sunday Rest</button>
                <button type="button" onClick={() => onChange(applyWeeklyScheduleTemplate(value, "mon-fri"))}>Mon–Fri / Weekend Rest</button>
                <button type="button" onClick={() => onChange(applyWeeklyScheduleTemplate(value, "custom"))}>Custom Schedule</button>
                <button type="button" onClick={() => onChange(applyWeeklyScheduleTemplate(value, "rotating"))}>Rotating / No Fixed Rest Day</button>
            </div>
            {value.schedule_type === "Rotating / No Fixed Rest Day" && <div className="schedule-rotating-note"><span className="material-symbols-outlined">event_repeat</span>Rotating schedules use dated Working Day / Rest Day exceptions in Staff Calendar. The seven-day baseline remains explicit for availability safety.</div>}
            <div className="weekly-day-grid">
                {value.days.map((day, index) => {
                    const working = day.state === "Working Day";
                    return <article key={day.day_of_week} className={`weekly-day-card ${working ? "working" : "rest"}`}>
                        <div className="weekly-day-heading"><strong>{WEEK_DAYS[day.day_of_week]}</strong><button type="button" aria-pressed={!working} onClick={() => updateDay(index, { state: working ? "Rest Day" : "Working Day" })}><span className="material-symbols-outlined" aria-hidden="true">{working ? "work" : "weekend"}</span>{day.state}</button></div>
                        {working ? <div className="weekly-day-times">
                            <label><span>Start</span><input aria-label={`${WEEK_DAYS[day.day_of_week]} start time`} type="time" value={day.start_time || ""} onChange={(event) => updateDay(index, { start_time: event.target.value })} /></label>
                            <label><span>End</span><input aria-label={`${WEEK_DAYS[day.day_of_week]} end time`} type="time" value={day.end_time || ""} onChange={(event) => updateDay(index, { end_time: event.target.value })} /></label>
                            <label><span>Break start</span><input aria-label={`${WEEK_DAYS[day.day_of_week]} break start`} type="time" value={day.break_start_time || ""} onChange={(event) => updateDay(index, { break_start_time: event.target.value || null })} /></label>
                            <label><span>Break end</span><input aria-label={`${WEEK_DAYS[day.day_of_week]} break end`} type="time" value={day.break_end_time || ""} onChange={(event) => updateDay(index, { break_end_time: event.target.value || null })} /></label>
                        </div> : <p className="weekly-rest-copy">No shift hours. Rest Day is not counted as an absence.</p>}
                    </article>;
                })}
            </div>
        </section>
    );
}
