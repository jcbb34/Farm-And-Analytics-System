'use client';
import { useEffect, useState } from 'react';
import { cropPlanningService } from '../../services/cropPlanningService.js';
import './CropPlanning.css';

const blank = { name: '', area_m2: '', unavailable_area_m2: '0', unavailable_reason: '' };
export default function LandSetup({ initialLand, onSaved, embedded = false }) {
    const [land, setLand] = useState(initialLand), [error, setError] = useState(''), [saving, setSaving] = useState(false);
    const [parent, setParent] = useState(''), [editing, setEditing] = useState(null), [form, setForm] = useState(blank);
    useEffect(() => { if (initialLand) setLand(initialLand); else cropPlanningService.land().then(setLand).catch(e => setError(e.message)); }, [initialLand]);
    const edit = (row, fieldId = '') => { setParent(String(fieldId)); setEditing(row); setForm({ ...blank, ...row, area_m2: row.area_m2 ?? '' }); };
    const submit = async event => {
        event.preventDefault(); setError(''); setSaving(true);
        const payload = { name: form.name.trim(), area_m2: form.area_m2 === '' ? null : form.area_m2,
            unavailable_area_m2: form.unavailable_area_m2 || '0', unavailable_reason: form.unavailable_reason || null,
            expected_version: editing?.edit_version };
        try {
            const result = await (parent ? cropPlanningService.saveSection(Number(parent), editing?.id, payload) : cropPlanningService.saveField(editing?.id, payload));
            setLand(result); onSaved?.(result); setForm(blank); setEditing(null);
        } catch (e) { setError(e.message || 'Unable to save measured area.'); } finally { setSaving(false); }
    };
    const FormTag = embedded ? "div" : "form";
    return <div className="crop-land-panel">
        <div className="crop-land-heading"><span className="material-symbols-outlined" aria-hidden="true">landscape</span><h3>Farm Land Setup</h3></div>
        <p>Farm total: <strong>{land ? Number(land.total_area_m2).toLocaleString() : '…'} m²</strong>. Enter measured areas only. Include livestock facilities, buildings, paths and drainage in unavailable space at the level where they occur, once.</p>
        {error && <p role="alert" className="crop-planning-error">{error}</p>}
        <div className="crop-land-table-wrap" role="region" aria-label="Measured fields and sections" tabIndex={0}>
            <table><thead><tr><th>Field / Section</th><th>Measured m²</th><th>Unavailable m²</th><th>Available m²</th><th>Actions</th></tr></thead>
                <tbody>{land?.fields.map(field => <LandRows key={field.id} field={field} edit={edit} />)}</tbody></table>
        </div>
        {!land?.fields.length && <p>No measured fields or sections are configured. Existing location names remain in historical records.</p>}
        {Boolean(land?.legacy_unmapped_count) && <p>{land.legacy_unmapped_count} legacy planting(s) need review and measured-location mapping. Their old area values have not been treated as surveyed allocations.</p>}
        <h4>{editing ? 'Edit measured area' : 'Add a field or section'}</h4>
        <FormTag className="crop-land-form" onSubmit={embedded ? undefined : submit}>
            <label>Parent<select value={parent} disabled={saving || Boolean(editing)} onChange={event => { setParent(event.target.value); setEditing(null); }}>
                <option value="">Farm — add a field</option>{land?.fields.map(field => <option key={field.id} value={field.id}>{field.name} — add a section</option>)}
            </select></label>
            <label>Name<input required={!embedded} maxLength={100} value={form.name} onChange={event => setForm(old => ({ ...old, name: event.target.value }))} /></label>
            <label>Measured area (m²)<input type="number" min="0.0001" step="0.0001" value={form.area_m2} onChange={event => setForm(old => ({ ...old, area_m2: event.target.value }))} placeholder="Unknown until measured" /></label>
            <label>Unavailable area (m²)<input required={!embedded} type="number" min="0" step="0.0001" value={form.unavailable_area_m2} onChange={event => setForm(old => ({ ...old, unavailable_area_m2: event.target.value }))} /></label>
            <label>Unavailable-space description<input required={!embedded && Number(form.unavailable_area_m2) > 0} value={form.unavailable_reason || ''} onChange={event => setForm(old => ({ ...old, unavailable_reason: event.target.value }))} /></label>
            <button className="crop-planning-action crop-land-save" type={embedded ? "button" : "submit"} onClick={embedded ? submit : undefined} disabled={saving}>{saving ? 'Saving…' : 'Save measured area'}</button>
            {editing && <button className="crop-planning-action" type="button" onClick={() => { setEditing(null); setForm(blank); setParent(''); }}>Cancel edit</button>}
        </FormTag>
    </div>;
}

function LandRows({ field, edit }) {
    return <>
        <tr><td><strong>{field.name}</strong></td><td>{field.area_m2 ?? 'Unconfigured'}</td><td>{field.unavailable_area_m2}</td><td>See sections</td><td><button className="crop-land-edit" type="button" onClick={() => edit(field)}>Edit</button></td></tr>
        {field.sections.map(section => <tr key={section.id}><td>↳ {section.name} · {section.status}</td><td>{section.area_m2 ?? 'Unconfigured'}</td><td>{section.unavailable_area_m2}</td><td>{section.available_area_m2 ?? 'Unconfigured'}</td><td><button className="crop-land-edit" type="button" onClick={() => edit(section, field.id)}>Edit</button></td></tr>)}
    </>;
}
