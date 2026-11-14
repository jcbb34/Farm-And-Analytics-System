'use client';
import { useEffect, useState } from 'react';
import { cropPlanningService, farmTodayDateKey, validScheduleStartDate } from '../../services/cropPlanningService.js';

export default function CareScheduleFields({ schedule, onChange, employees, defaultEmployee, originalStartDate = '' }) {
    const [slots, setSlots] = useState(null), [error, setError] = useState('');
    const today = farmTodayDateKey();
    const preservedHistoricalStart = Boolean(originalStartDate && originalStartDate < today && schedule.start_date === originalStartDate);
    const employeeId = schedule.employee_id || defaultEmployee;
    useEffect(() => {
        setSlots(null); setError('');
        if (!schedule.enabled || !employeeId || !schedule.start_date || !Number(schedule.duration_minutes)) return;
        let alive = true;
        cropPlanningService.slots({ employee_id: employeeId, work_date: schedule.start_date, duration_minutes: schedule.duration_minutes })
            .then(result => { if (alive) setSlots(result); }).catch(e => { if (alive) setError(e.message); });
        return () => { alive = false; };
    }, [employeeId, schedule.enabled, schedule.start_date, schedule.duration_minutes]);
    const field = (key, value) => onChange({ ...schedule, [key]: value });
    const enable = enabled => {
        if (!enabled) { field('enabled', false); return; }
        const start = validScheduleStartDate(schedule.start_date, originalStartDate, today) && schedule.start_date
            ? schedule.start_date : today;
        onChange({ ...schedule, enabled: true, start_date: start,
            end_date: schedule.end_date && schedule.end_date < start ? null : schedule.end_date });
    };
    const updateStartDate = date => {
        if (!validScheduleStartDate(date, originalStartDate, today)) {
            setError('The start date cannot be in the past. Choose today or a future date.');
            return;
        }
        setError('');
        onChange({ ...schedule, start_date: date,
            end_date: schedule.end_date && date && schedule.end_date < date ? null : schedule.end_date });
    };
    return <div className="crop-care-row">
        <label className="crop-care-heading"><input type="checkbox" checked={schedule.enabled} onChange={event => enable(event.target.checked)} /><span className="material-symbols-outlined" aria-hidden="true">{schedule.activity === 'watering' ? 'water_drop' : 'monitoring'}</span><span>{schedule.activity === 'watering' ? 'Watering' : 'Growth Observation'}</span><span className="crop-care-state">{schedule.enabled ? 'Enabled' : 'Optional'}</span></label>
        {schedule.enabled && <>
            <div className="crop-form-grid">
                <label>Start date<input required type="date" min={preservedHistoricalStart ? originalStartDate : today} value={schedule.start_date || ''} onChange={event => updateStartDate(event.target.value)} />
                    {preservedHistoricalStart && <small>Saved historical start date. Changing it requires today or a future date.</small>}</label>
                <label>Optional end date<input type="date" min={schedule.start_date} value={schedule.end_date || ''} onChange={event => field('end_date', event.target.value || null)} /></label>
                <label>Repeat every (days)<input required type="number" min="1" max="365" value={schedule.frequency_days} onChange={event => field('frequency_days', Number(event.target.value))} disabled={Boolean(schedule.weekdays?.length)} /></label>
                <label>Employee<select required={!defaultEmployee} value={schedule.employee_id || ''} onChange={event => field('employee_id', event.target.value ? Number(event.target.value) : null)}>
                    <option value="">{defaultEmployee ? 'Use planting employee' : 'Choose employee'}</option>{employees.map(employee => <option value={employee.id} key={employee.id}>{employee.full_name}</option>)}
                </select></label>
                <label>Start time<input required type="time" step="1" value={schedule.start_time || ''} onChange={event => field('start_time', event.target.value)} /></label>
                <label>Duration (minutes)<input required type="number" min="1" max="720" value={schedule.duration_minutes || ''} onChange={event => field('duration_minutes', Number(event.target.value))} /></label>
            </div>
            <div className="crop-weekdays"><span className="crop-weekdays-title">Repeat on specific days (optional)</span><div className="crop-weekday-list" role="group" aria-label={`${schedule.activity} selected days`}>{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day, index) => <label className="crop-weekday-option" key={day}>
                <input type="checkbox" checked={schedule.weekdays?.includes(index) || false} onChange={event => field('weekdays', event.target.checked ? [...(schedule.weekdays || []), index] : schedule.weekdays.filter(x => x !== index))} />{day}
            </label>)}</div>
            <small>Select weekdays for a weekly pattern, or leave them unchecked to repeat by the day interval.</small></div>
            {error && <p role="alert" className="crop-planning-error">{error}</p>}
            {slots && <label className="crop-care-slot">Available full-duration slots on the start date<select value="" onChange={event => field('start_time', event.target.value)}>
                <option value="">{slots.slots.length ? 'Choose a slot or enter a time above' : slots.reason}</option>{slots.slots.map(slot => <option key={slot.start_time} value={slot.start_time}>{slot.start_time}–{slot.end_time}</option>)}
            </select></label>}
        </>}
    </div>;
}
