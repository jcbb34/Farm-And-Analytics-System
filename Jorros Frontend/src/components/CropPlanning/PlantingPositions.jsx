'use client';
import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext.jsx';
import { confirmAction } from '../../context/NotificationContext.jsx';
import { cropPlanningService } from '../../services/cropPlanningService.js';
import { createIdempotencyKey } from '../../services/idempotencyKey.js';
import './CropPlanning.css';

export default function PlantingPositions({ crop, onChanged }) {
    const { hasPermission } = useAuth();
    const [state, setState] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
    const [form, setForm] = useState({ event_type: 'verified_cleared', event_date: '', quantity: '', notes: '' });
    const [reason, setReason] = useState(''), [cleared, setCleared] = useState(false);
    const attempt = useRef(null);
    useEffect(() => { cropPlanningService.positions(crop.id).then(setState).catch(e => setError(e.message)); }, [crop.id, crop.editVersion]);
    const change = (key, value) => { attempt.current = null; setForm(old => ({ ...old, [key]: value })); };
    const save = async event => {
        event.preventDefault(); setBusy(true); setError('');
        attempt.current ||= createIdempotencyKey('positions');
        try {
            const result = await cropPlanningService.recordPosition(crop.id, { ...form, quantity: Number(form.quantity) }, attempt.current);
            setState(result); attempt.current = null; await onChanged?.();
        } catch (e) { setError(e.message); } finally { setBusy(false); }
    };
    const end = async () => {
        if (!reason.trim()) { setError('Enter the reason and describe what was physically cleared.'); return; }
        if (!await confirmAction({ title: cleared ? 'Confirm Area Cleared' : 'End Planting', message: cleared ? 'Confirm this planting was ended and its physical area cleared?' : 'End this planting while keeping its land occupied until clearing is confirmed?', confirmText: cleared ? 'Confirm clearing' : 'End planting' })) return;
        setBusy(true); setError('');
        try { await cropPlanningService.end(crop.id, { expected_version: crop.editVersion, reason, confirm_area_cleared: cleared }); await onChanged?.(); }
        catch (e) { setError(e.message); } finally { setBusy(false); }
    };
    return <section className="crop-land-panel">
        <h3>Planting Positions & Replacements</h3>
        {error && <p role="alert" className="crop-planning-error">{error}</p>}
        {state && <><div className="crop-position-summary">
            {[['Potential replacement positions', state.potential_replacement_positions], ['Verified cleared positions', state.verified_cleared_positions],
                ['Mortality recorded', state.mortality], ['Plants harvested out', state.harvested_out], ['Removed through clearing', state.removed], ['Blocked positions', state.blocked_positions]].map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}
        </div><p>Count unit: {state.count_unit}. Gaps need checking and clearing; they do not automatically free continuous land. Previous unclassified losses: {state.previous_unclassified_losses ?? 'Unknown'}.</p></>}
        {hasPermission('crops:update') && !crop.area_cleared_at && <form onSubmit={save}>
            <label>Event<select value={form.event_type} onChange={event => change('event_type', event.target.value)}>
                {[['verified_cleared', 'Confirm vacant positions checked and cleared'], ['replacement', 'Record replacement planting'], ['mortality', 'Record mortality'],
                    ['removed', 'Record plants removed by clearing'], ['blocked', 'Block unusable vacant positions'], ['unblocked', 'Restore previously blocked positions']].map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select></label>
            <label>Actual date<input required type="date" value={form.event_date} onChange={event => change('event_date', event.target.value)} /></label>
            <label>Quantity<input required type="number" min="1" step="1" value={form.quantity} onChange={event => change('quantity', event.target.value)} /></label>
            <label>Notes<input required minLength={3} value={form.notes} onChange={event => change('notes', event.target.value)} /></label>
            <button disabled={busy} type="submit">Record event</button>
        </form>}
        {state?.events.length > 0 && <details><summary>Position history</summary><ul>{state.events.map(event => <li key={event.id}>{event.event_date} · {event.event_type.replaceAll('_', ' ')} · {event.quantity} · {event.notes}</li>)}</ul></details>}
        {hasPermission('crops:full-edit') && !crop.area_cleared_at && <details><summary>End Planting / Confirm Area Cleared</summary>
            <p>A final harvest and physical clearing are separate. Shared land remains occupied until every planting sharing it is cleared.</p>
            <label>Reason<input value={reason} onChange={event => setReason(event.target.value)} /></label>
            <label className="crop-planning-check"><input type="checkbox" checked={cleared} onChange={event => setCleared(event.target.checked)} />I physically confirmed this planting's area is cleared.</label>
            <button type="button" disabled={busy} onClick={end}>{cleared ? 'End Planting / Confirm Area Cleared' : 'End Planting'}</button>
        </details>}
        {crop.area_cleared_at && <p>Area clearing confirmed: {String(crop.area_cleared_at).slice(0, 10)}. Start the next season as a new planting record.</p>}
    </section>;
}
