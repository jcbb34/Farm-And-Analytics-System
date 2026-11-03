"use client";

import { useCallback, useEffect, useState } from "react";

import WeeklyScheduleEditor, {
    normalizeWeeklySchedule,
    validateWeeklySchedule,
} from "../../components/WeeklyScheduleEditor/WeeklyScheduleEditor.jsx";
import { useNotification } from "../../context/NotificationContext.jsx";
import { workforceService } from "../../services/workforceService.js";
import { today } from "./taskManagementUtils.js";
import "./EmployeeWorkScheduleModal.css";

export default function EmployeeWorkScheduleModal({ employee, employees, effectiveDate, onClose, onSaved }) {
    const notification = useNotification();
    const [schedule, setSchedule] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [saving, setSaving] = useState(false);

    const loadSchedule = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const start = effectiveDate && effectiveDate > today() ? effectiveDate : today();
            const current = await workforceService.getEmployeeWorkSchedule(employee.id, start);
            const normalized = normalizeWeeklySchedule(current, start);
            setSchedule({
                ...normalized,
                effective_from: start,
                effective_to: normalized.effective_to && normalized.effective_to >= start
                    ? normalized.effective_to : null,
            });
        } catch (err) {
            setError(err?.message || "Unable to load this employee's work schedule.");
        } finally {
            setLoading(false);
        }
    }, [employee.id, effectiveDate]);

    useEffect(() => { void loadSchedule(); }, [loadSchedule]);

    useEffect(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const onKeyDown = (event) => {
            if (event.key === "Escape" && !saving) onClose();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("keydown", onKeyDown);
        };
    }, [onClose, saving]);

    const save = async (event) => {
        event.preventDefault();
        if (saving || !schedule) return;
        const validationError = validateWeeklySchedule(schedule);
        if (validationError || schedule.effective_from < today()) {
            notification.error(validationError || "Choose today or a future effective date so past schedules remain unchanged.", "Work Schedule");
            return;
        }
        setSaving(true);
        try {
            await workforceService.updateEmployeeWorkSchedule(employee.id, {
                ...schedule,
                backup_employee_id: schedule.backup_employee_id ? Number(schedule.backup_employee_id) : null,
                effective_to: schedule.effective_to || null,
            });
            notification.success(`${employee.full_name}'s work schedule was saved.`, "Work Schedule");
            onClose();
            void onSaved?.();
        } catch (err) {
            notification.error(err?.message || "Unable to save the work schedule.", "Work Schedule");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="workforce-modal-overlay" onMouseDown={(event) => {
            if (event.target === event.currentTarget && !saving) onClose();
        }}>
            <div className="workforce-task-modal workforce-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="workforce-schedule-title" onMouseDown={(event) => event.stopPropagation()}>
                <header className="workforce-modal-header">
                    <div>
                        <h2 id="workforce-schedule-title">Work Schedule</h2>
                        <p>{employee.full_name} · Set the weekly shift from the effective date. Earlier schedules and attendance remain recorded.</p>
                    </div>
                    <button type="button" className="workforce-modal-close" onClick={onClose} disabled={saving} aria-label="Close work schedule"><span className="material-symbols-outlined">close</span></button>
                </header>
                {loading ? <div className="workforce-schedule-state" role="status">Loading work schedule…</div> : error ? (
                    <div className="workforce-schedule-state" role="alert"><p>{error}</p><button type="button" className="workforce-button secondary" onClick={loadSchedule}>Retry</button></div>
                ) : (
                    <form className="workforce-schedule-form" onSubmit={save}>
                        <div className="workforce-schedule-body">
                            <WeeklyScheduleEditor
                                value={schedule}
                                onChange={setSchedule}
                                employees={employees}
                                employeeId={employee.id}
                                needsSetup={employee.schedule_status === "Needs Setup"}
                                minEffectiveDate={today()}
                            />
                        </div>
                        <footer className="workforce-modal-footer workforce-schedule-footer">
                            <button type="button" className="workforce-modal-cancel" onClick={onClose} disabled={saving}>Cancel</button>
                            <button type="submit" className="workforce-modal-save" disabled={saving}>{saving ? "Saving…" : "Save Work Schedule"}</button>
                        </footer>
                    </form>
                )}
            </div>
        </div>
    );
}
