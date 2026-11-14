'use client';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import useModalScrollLock from '../../hooks/useModalScrollLock.js';
import FarmSectionToggle from '../FarmAreas/FarmSectionToggle.jsx';
import { areGroupsExpanded, setGroupsExpanded, toggleExpandedGroup } from '../FarmAreas/areaDisclosureState.js';
import { cropPlanningService } from '../../services/cropPlanningService.js';
import { emptyLandEditor, usableMeasuredArea, validateLandEditor } from './landSetupEditor.js';
import './CropPlanning.css';

const freshForm = () => ({ ...emptyLandEditor });

function LandAreaDialog({ editor, land, saving, onClose, onSave, onEditParent }) {
    const [form, setForm] = useState(editor.form);
    const [type, setType] = useState(editor.type);
    const [parentId, setParentId] = useState(editor.parentId || '');
    const [error, setError] = useState('');
    const closeRef = useRef(null);
    const dialogRef = useRef(null);
    const closeCallback = useRef(onClose);
    const busyRef = useRef(saving);
    // Prevent the farm page (or Add Crop behind this dialog) from scrolling.
    useModalScrollLock(true);
    closeCallback.current = onClose;
    busyRef.current = saving;
    useEffect(() => {
        const previous = document.activeElement;
        closeRef.current?.focus();
        const handleKey = event => {
            if (event.key === 'Escape') { event.stopPropagation(); if (!busyRef.current) closeCallback.current(); }
            if (event.key === 'Tab' && dialogRef.current) {
                const targets = Array.from(dialogRef.current.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled])'));
                if (!targets.length) return;
                if (event.shiftKey && document.activeElement === targets[0]) { event.preventDefault(); targets.at(-1).focus(); }
                else if (!event.shiftKey && document.activeElement === targets.at(-1)) { event.preventDefault(); targets[0].focus(); }
            }
        };
        document.addEventListener('keydown', handleKey, true);
        return () => { document.removeEventListener('keydown', handleKey, true); previous?.focus?.(); };
    }, []);

    const editing = editor.mode === 'edit';
    const parent = (land?.fields || []).find(field => String(field.id) === String(parentId));
    const parentUsable = usableMeasuredArea(parent);
    const liveUsable = usableMeasuredArea(form);
    const fmtArea = amount => Number(amount || 0).toLocaleString(undefined, { maximumFractionDigits: 4 });
    const canSave = !saving && (type !== 'section' || Boolean(parentId));
    const submit = async event => {
        event.preventDefault();
        event.stopPropagation();
        const nextError = validateLandEditor({ land, type, parentId, editingId: editor.id, form });
        if (nextError) { setError(nextError); return; }
        setError('');
        const result = await onSave({ type, parentId, id: editor.id, form });
        if (result?.error) setError(result.error);
    };
    const patch = (key, value) => { setError(''); setForm(old => ({ ...old, [key]: value })); };
    return createPortal(<div className="crop-land-dialog-backdrop" onMouseDown={e => { if (e.target === e.currentTarget && !saving) onClose(); }}>
        <section className="crop-land-dialog" role="dialog" aria-modal="true" aria-labelledby="crop-land-dialog-title" aria-describedby="crop-land-dialog-summary" ref={dialogRef}>
            <div className="crop-land-dialog-header">
                <div className="crop-land-dialog-heading">
                    <span className="material-symbols-outlined" aria-hidden="true">{editing ? 'edit_square' : 'add_circle'}</span>
                    <div><h3 id="crop-land-dialog-title">{editing ? `Edit ${type}` : 'Create field or section'}</h3>
                        <p id="crop-land-dialog-summary">{editing ? 'Update the existing record without creating a duplicate.' : 'Add a new location to the measured crop land setup.'}</p></div>
                </div>
                <button ref={closeRef} type="button" className="crop-land-dialog-close" aria-label="Close dialog" onClick={onClose} disabled={saving}><span className="material-symbols-outlined" aria-hidden="true">close</span></button>
            </div>
            <form className="crop-land-dialog-form" onSubmit={submit}>
                <div className="crop-land-dialog-content">
                    {error && <p className="crop-land-dialog-error" role="alert"><span className="material-symbols-outlined" aria-hidden="true">error</span>{error}</p>}
                    <div className="crop-land-dialog-grid">
                        <label>Location type
                            <select value={type} disabled={editing || saving} onChange={e => { setType(e.target.value); setParentId(''); setError(''); }}>
                                <option value="field">Field</option><option value="section">Section within a field</option>
                            </select>
                        </label>
                        {type === 'section' && <label>Parent field
                            <select value={parentId} required disabled={editing || saving} onChange={e => { setParentId(e.target.value); setError(''); }}>
                                <option value="">Choose a field</option>{land?.fields.map(field => <option key={field.id} value={field.id}>{field.name}</option>)}
                            </select>
                        </label>}
                        <label className="crop-land-dialog-wide">{type === 'field' ? 'Field name' : 'Section name'}
                            <input required maxLength={100} value={form.name} onChange={e => patch('name', e.target.value)} placeholder={type === 'field' ? 'e.g. Field E — Vegetable Plot' : 'e.g. Section A2'} />
                        </label>
                        <label>Measured area <span className="crop-land-unit">(m²)</span>
                            <input type="number" min="0.0001" step="0.0001" value={form.area_m2} onChange={e => patch('area_m2', e.target.value)} placeholder="Unknown until measured" />
                        </label>
                        <label>Unavailable area <span className="crop-land-unit">(m²)</span>
                            <input type="number" required min="0" step="0.0001" value={form.unavailable_area_m2} onChange={e => patch('unavailable_area_m2', e.target.value)} />
                            <span className="crop-land-field-help">Only space that cannot be planted (e.g., structures, blocked paths). Do not repeat the entire field size.</span>
                        </label>
                        <label className="crop-land-dialog-wide">Unavailable-space description
                            <input value={form.unavailable_reason || ''} maxLength={500} required={Number(form.unavailable_area_m2) > 0}
                                onChange={e => patch('unavailable_reason', e.target.value)} placeholder="Only required when unavailable area is greater than zero" />
                        </label>
                    </div>
                    {liveUsable != null && <div className={`crop-land-usable-preview${liveUsable <= 0 ? ' crop-land-usable-preview-warning' : ''}`} role="status">
                        <span className="material-symbols-outlined" aria-hidden="true">calculate</span>
                        <span>Usable {type === 'field' ? 'field' : 'section'} area: <strong>{fmtArea(form.area_m2)} − {fmtArea(form.unavailable_area_m2)} = {fmtArea(liveUsable)} m²</strong>
                            {liveUsable <= 0 && <span className="crop-land-preview-detail"> All measured space is marked unavailable. If this land can be planted, lower Unavailable area.</span>}
                        </span>
                    </div>}
                    {type === 'section' && (parentUsable != null && parentUsable <= 0 ?
                        <div className="crop-land-parent-warning" role="alert">
                            <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                            <div><strong>{parent.name} has no usable planting space.</strong>
                                <p>{fmtArea(parent.area_m2)} m² measured − {fmtArea(parent.unavailable_area_m2)} m² unavailable = {fmtArea(parentUsable)} m² usable. Correct the parent’s unavailable area if this field is plantable.</p>
                                <button type="button" className="crop-land-edit-parent" onClick={() => onEditParent(parent)} disabled={saving}>Edit parent field</button>
                            </div>
                        </div> :
                        <p className="crop-land-dialog-note"><span className="material-symbols-outlined" aria-hidden="true">info</span>
                            {parentUsable == null ? 'Measure the parent field before entering a measured section size. You may still create an unmeasured section.'
                                : `Parent usable area: ${fmtArea(parentUsable)} m². Other sections and existing plantings must fit within it.`}
                        </p>)}
                </div>
                <div className="crop-land-dialog-footer">
                    <button type="button" className="crop-land-dialog-cancel" disabled={saving} onClick={onClose}>Cancel</button>
                    <button type="submit" className="crop-land-dialog-submit" disabled={!canSave}>
                        <span className="material-symbols-outlined" aria-hidden="true">{editing ? 'save' : 'add'}</span>
                        {saving ? 'Saving…' : editing ? 'Save changes' : `Create ${type}`}
                    </button>
                </div>
            </form>
        </section>
    </div>, document.body);
}

export default function LandSetup({ initialLand, onSaved, embedded = false, canEdit = true, createRequestId = 0 }) {
    const [land, setLand] = useState(initialLand), [error, setError] = useState(''), [notice, setNotice] = useState('');
    const [saving, setSaving] = useState(false), [editor, setEditor] = useState(null);
    const [expandedFields, setExpandedFields] = useState({});
    const handledCreateRequest = useRef(0);
    useEffect(() => { if (initialLand) setLand(initialLand); else cropPlanningService.land().then(setLand).catch(e => setError(e.message)); }, [initialLand]);
    const startCreate = (type = 'field', parentId = '') => {
        setError(''); setNotice(''); setEditor({ mode: 'create', type, parentId: String(parentId), id: null, form: freshForm() });
    };
    useEffect(() => {
        if (!canEdit || !land || createRequestId <= 0 || handledCreateRequest.current === createRequestId) return;
        handledCreateRequest.current = createRequestId;
        setError(''); setNotice('');
        setEditor({ mode: 'create', type: 'field', parentId: '', id: null, form: freshForm() });
    }, [createRequestId, canEdit, land]);
    const startEdit = (row, type, parentId = '') => {
        setError(''); setNotice(''); setEditor({ mode: 'edit', type, id: row.id, parentId: String(parentId), editVersion: row.edit_version,
            form: { name: row.name, area_m2: row.area_m2 ?? '', unavailable_area_m2: row.unavailable_area_m2 ?? '0', unavailable_reason: row.unavailable_reason || '' } });
    };
    const closeEditor = () => { if (!saving) setEditor(null); };
    const submit = async ({ type, parentId, id, form }) => {
        if (saving) return { error: 'A save is already in progress.' };
        const guard = validateLandEditor({ land, type, parentId, editingId: id, form });
        if (guard) return { error: guard };
        setSaving(true);
        const payload = { name: form.name.trim(), area_m2: form.area_m2 === '' ? null : form.area_m2,
            unavailable_area_m2: form.unavailable_area_m2 || '0', unavailable_reason: form.unavailable_reason.trim() || null,
            ...(id != null ? { expected_version: editor.editVersion } : {}) };
        try {
            const result = type === 'section' ? await cropPlanningService.saveSection(Number(parentId), id, payload)
                : await cropPlanningService.saveField(id, payload);
            setLand(result); onSaved?.(result); setEditor(null); setError('');
            setNotice(`${type === 'field' ? 'Field' : 'Section'} ${id == null ? 'created' : 'updated'} successfully.`);
            return { ok: true };
        } catch (e) {
            return { error: e.message || 'Unable to save this area. Please review its measurements.' };
        } finally { setSaving(false); }
    };
    const fields = land?.fields || [];
    const withSections = fields.filter(field => field.sections?.length > 0);
    const allExpanded = areGroupsExpanded(expandedFields, withSections.map(field => field.id));
    const toggleField = id => setExpandedFields(old => toggleExpandedGroup(old, id));
    const toggleAll = () => setExpandedFields(old => setGroupsExpanded(old, withSections.map(field => field.id), !allExpanded));
    return <div className="crop-land-panel">
        <div className="crop-land-heading"><span className="material-symbols-outlined" aria-hidden="true">landscape</span><h3>Measured Crop Land</h3></div>
        <div className="crop-land-intro-row">
            <p>Farm total: <strong>{land ? Number(land.total_area_m2).toLocaleString() : '…'} m²</strong>. Configure measured crop fields and sections. Edit an existing location rather than creating it again.</p>
            <button className="crop-land-create" type="button" onClick={() => startCreate()} disabled={saving || !land || !canEdit}>
                <span className="material-symbols-outlined" aria-hidden="true">add</span>Create field or section</button>
        </div>
        {embedded && <p className="crop-land-secondary-note"><a href="/farm-plan">Open Farm Land &amp; Facilities</a> to manage all the livestock and building locations.</p>}
        {error && <p role="alert" className="crop-planning-error">{error}</p>}
        {notice && <p role="status" className="crop-land-success">{notice}</p>}
        {withSections.length > 0 && <div className="crop-land-collapse-toolbar">
            <span><span className="material-symbols-outlined" aria-hidden="true">account_tree</span>{fields.length} fields · Open a field to view its sections</span>
            <button type="button" onClick={toggleAll}><span className="material-symbols-outlined" aria-hidden="true">{allExpanded ? 'unfold_less' : 'unfold_more'}</span>{allExpanded ? 'Collapse all' : 'Expand all'}</button>
        </div>}
        <div className="crop-land-table-wrap" role="region" aria-label="Measured fields and sections" tabIndex={0}>
            <table><thead><tr><th>Field / Section</th><th>Measured m²</th><th>Unavailable m²</th><th>Available m²</th><th>Actions</th></tr></thead>
                {fields.map(field => <LandRows key={field.id} field={field} edit={startEdit} create={startCreate} canEdit={canEdit} expanded={Boolean(expandedFields[field.id])} onToggle={() => toggleField(field.id)} />)}</table>
        </div>
        {!land?.fields.length && <p>No fields are configured yet. Select Create field or section to get started.</p>}
        {Boolean(land?.legacy_unmapped_count) && <p>{land.legacy_unmapped_count} legacy planting(s) need review and measured-location mapping. Old area values are not treated as measured allocations.</p>}
        {editor && <LandAreaDialog key={`${editor.mode}-${editor.type}-${editor.id ?? editor.parentId}`} editor={editor} land={land} saving={saving} onClose={closeEditor} onSave={submit} onEditParent={field => startEdit(field, 'field')} />}
    </div>;
}

function LandRows({ field, edit, create, canEdit, expanded, onToggle }) {
    const sections = field.sections || [];
    const sectionsId = `crop-land-sections-${field.id}`;
    const usable = usableMeasuredArea(field);
    return <>
        <tbody className="crop-land-parent-group">
            <tr className="crop-land-field-row"><td>
                <FarmSectionToggle label={field.name} count={sections.length} expanded={expanded} onToggle={onToggle} controls={sectionsId} variant="table" />
            </td><td>{field.area_m2 ?? 'Unconfigured'}</td><td>{field.unavailable_area_m2}</td><td>
                {usable == null ? 'Unconfigured' : <span className={usable <= 0 ? 'crop-land-no-space' : ''}>
                    {usable.toLocaleString(undefined, { maximumFractionDigits: 4 })} m² usable
                    {usable <= 0 && <small> · All area marked unavailable</small>}
                </span>}
            </td><td className="crop-land-row-actions">
                <button className="crop-land-edit" type="button" disabled={!canEdit} onClick={() => edit(field, 'field')}><span className="material-symbols-outlined" aria-hidden="true">edit</span>Edit</button>
                <button className="crop-land-add-section" type="button" disabled={!canEdit} onClick={() => create('section', field.id)}><span className="material-symbols-outlined" aria-hidden="true">add</span>Section</button>
            </td></tr>
        </tbody>
        <tbody id={sectionsId} className="crop-land-child-group" hidden={!expanded}>
            {sections.map(section => <tr key={section.id} className="crop-land-section-row"><td className="crop-land-section-name"><span className="material-symbols-outlined" aria-hidden="true">subdirectory_arrow_right</span><span>{section.name} <small>· {section.status}</small></span></td>
                <td>{section.area_m2 ?? 'Unconfigured'}</td><td>{section.unavailable_area_m2}</td><td>{section.available_area_m2 ?? 'Unconfigured'}</td>
                <td className="crop-land-row-actions"><button className="crop-land-edit" type="button" disabled={!canEdit} onClick={() => edit(section, 'section', field.id)}><span className="material-symbols-outlined" aria-hidden="true">edit</span>Edit</button></td></tr>)}
        </tbody>
    </>;
}
