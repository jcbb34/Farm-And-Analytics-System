'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import useModalScrollLock from '../../hooks/useModalScrollLock.js';
import Link from 'next/link';
import Sidebar from '../../components/Sidebar/Sidebar.jsx';
import AppHeaderActions from '../../components/AppHeaderActions/AppHeaderActions.jsx';
import LandSetup from '../../components/CropPlanning/LandSetup.jsx';
import FarmSectionToggle from '../../components/FarmAreas/FarmSectionToggle.jsx';
import { areGroupsExpanded, setGroupsExpanded, toggleExpandedGroup } from '../../components/FarmAreas/areaDisclosureState.js';
import { useAuth } from '../../context/AuthContext.jsx';
import { farmPlanService } from '../../services/farmPlanService.js';
import { readFarmPlanDraft, collectFarmPlanUpdates, previewFarmPlan } from './farmPlanDraft.js';
import './FarmPlan.css';

const formatArea = value => value == null ? 'Not measured' : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })} m²`;
const areaTypes = {
    field: 'Crop field', section: 'Crop section', facility: 'Facility zone', livestock: 'Livestock enclosure',
    storage: 'Storage building', office: 'Farm office', infrastructure: 'Shared infrastructure',
};
const icons = {
    field: 'agriculture', section: 'grass', facility: 'domain', livestock: 'pets', storage: 'warehouse',
    office: 'business', infrastructure: 'route',
};

function FarmAreaDialog({ zone, draft, busy, onClose, onApply }) {
    const creating = !zone;
    const [form, setForm] = useState(creating ? { code:'', name:'', kind:'storage', proposed_area_m2:'100' } : { ...draft });
    const [error, setError] = useState('');
    const closeRef = useRef(null), dialogRef = useRef(null);
    const closeCallback = useRef(onClose), busyRef = useRef(busy);
    // Lock background page scrolling for both Create and Edit dialogs.
    useModalScrollLock(true);
    closeCallback.current = onClose;
    busyRef.current = busy;
    useEffect(() => {
        const previous = document.activeElement;
        closeRef.current?.focus();
        const onKey = event => {
            if (event.key === 'Escape') { event.stopPropagation(); if (!busyRef.current) closeCallback.current(); }
            if (event.key === 'Tab' && dialogRef.current) {
                const items = [...dialogRef.current.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled])')];
                if (!items.length) return;
                if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1).focus(); }
                if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus(); }
            }
        };
        document.addEventListener('keydown', onKey, true);
        return () => { document.removeEventListener('keydown', onKey, true); previous?.focus?.(); };
    }, []);
    const set = (key, value) => { setError(''); setForm(old => ({ ...old, [key]: value })); };
    const submit = async e => {
        e.preventDefault();
        e.stopPropagation();
        if (!form.name.trim()) return setError('Enter a location name.');
        if (!Number.isFinite(Number(form.proposed_area_m2)) || Number(form.proposed_area_m2) <= 0)
            return setError('Area allocation must be greater than zero.');
        if (!creating && !['field','section'].includes(zone.kind) && form.measured_area_m2 !== ''
            && (!Number.isFinite(Number(form.measured_area_m2)) || Number(form.measured_area_m2) <= 0))
            return setError('Verified measured area must be positive or left blank.');
        const result = await onApply(form);
        if (result?.error) setError(result.error);
    };
    const crop = ['field','section'].includes(zone?.kind);
    return createPortal(<div className="farm-plan-dialog-overlay" onMouseDown={e => { if (e.target === e.currentTarget && !busy) onClose(); }}>
        <section ref={dialogRef} className="farm-plan-dialog" role="dialog" aria-modal="true" aria-labelledby="farm-plan-dialog-title">
            <div className="farm-plan-dialog-head">
                <div className="farm-plan-dialog-head-copy"><span className="material-symbols-outlined" aria-hidden="true">{creating ? 'add_business' : 'edit_square'}</span><div>
                    <h2 id="farm-plan-dialog-title">{creating ? 'Create facility area' : `Edit ${zone.name}`}</h2>
                    <p>{creating ? 'Add a new storage, livestock, office or infrastructure location.' : `Location ${zone.code} · ${areaTypes[zone.kind]}`}</p>
                </div></div>
                <button type="button" className="farm-plan-dialog-close" ref={closeRef} onClick={onClose} disabled={busy} aria-label="Close edit dialog"><span className="material-symbols-outlined">close</span></button>
            </div>
            <form onSubmit={submit}>
                <div className="farm-plan-dialog-body">
                    {error && <div className="farm-plan-dialog-error" role="alert">{error}</div>}
                    <div className="farm-plan-dialog-fields">
                        {creating && <><label>Area code<input required maxLength={10} pattern="[A-Z][A-Z0-9]{1,9}" placeholder="S5" value={form.code} onChange={e => set('code',e.target.value.toUpperCase())}/></label>
                            <label>Facility type<select value={form.kind} onChange={e => set('kind',e.target.value)}><option value="storage">Storage</option><option value="livestock">Livestock area</option><option value="office">Office</option><option value="infrastructure">Infrastructure</option></select></label></>}
                        <label className="farm-plan-dialog-wide">Location name<input required maxLength={100} value={form.name} onChange={e=>set('name',e.target.value)} placeholder="Location name" /></label>
                        <label>Area allocation (m²)<input type="number" required min="0.0001" step="0.0001" value={form.proposed_area_m2} onChange={e=>set('proposed_area_m2',e.target.value)}/></label>
                        {!creating && !crop && <label>Verified measured area (m²)<input type="number" min="0.0001" step="0.0001" placeholder="Not measured" value={form.measured_area_m2} onChange={e=>set('measured_area_m2',e.target.value)}/></label>}
                    </div>
                    {crop && <p className="farm-plan-dialog-hint">Actual crop field and section measurements are maintained in the <strong>Measured Crop Land</strong> tab.</p>}
                    {!creating && <p className="farm-plan-dialog-hint">Apply this edit, then select <strong>Save changes</strong> on the page. Related areas can be adjusted together without exceeding the farm's area limits.</p>}
                    {creating && <p className="farm-plan-dialog-hint">The new facility uses space from the shared infrastructure allocation. Existing areas must be saved before creating a new facility.</p>}
                </div>
                <div className="farm-plan-dialog-footer"><button type="button" className="farm-plan-discard" onClick={onClose} disabled={busy}>Cancel</button>
                    <button type="submit" className="farm-plan-save" disabled={busy}><span className="material-symbols-outlined">{creating ? 'add' : 'check'}</span>{busy ? 'Saving…' : creating ? 'Create facility' : 'Apply edit'}</button></div>
            </form>
        </section>
    </div>, document.body);
}

function ZoneEditor({ zone, draft, isAdministrator, error, onOpenMeasurements, onEdit }) {
    const isCrop = zone.kind === 'field' || zone.kind === 'section';
    const isFacility = zone.kind === 'facility';
    const pending = draft.name.trim() !== zone.name || Number(draft.proposed_area_m2) !== Number(zone.proposed_area_m2)
        || (!isCrop && (draft.measured_area_m2 === '' ? null : Number(draft.measured_area_m2)) !== (zone.measured_area_m2 == null ? null : Number(zone.measured_area_m2)));
    return <article id={`farm-zone-${zone.code}`} className={`farm-plan-zone farm-plan-${zone.kind}${error ? ' has-error' : ''}`}>
        <div className="farm-plan-zone-heading">
            <div className="farm-plan-zone-identity">
                <span className="material-symbols-outlined" aria-hidden="true">{icons[zone.kind] || 'place'}</span>
                <span className="farm-plan-zone-code">{zone.code}</span>
                <div className="farm-plan-zone-label"><strong>{draft.name}</strong><small>{areaTypes[zone.kind] || 'Farm location'}</small></div>
            </div>
            <div className="farm-plan-zone-controls">{pending && <span className="farm-plan-staged">Unsaved</span>}
                {isAdministrator && <button type="button" className="farm-plan-edit-button" onClick={() => onEdit(zone)} aria-label={`Edit ${zone.name}`}><span className="material-symbols-outlined" aria-hidden="true">edit</span>Edit</button>}
            </div>
        </div>
        <div className="farm-plan-zone-summary">
            <div><small>Area allocation</small><strong>{formatArea(draft.proposed_area_m2)}</strong></div>
            <div><small>{isCrop ? 'Actual measured area' : 'Verified measured area'}</small><strong>{formatArea(isCrop ? zone.measured_area_m2 : draft.measured_area_m2 === '' ? null : draft.measured_area_m2)}</strong></div>
        </div>
        {error && <p className="farm-plan-zone-error" role="alert"><span className="material-symbols-outlined" aria-hidden="true">error</span>{error}</p>}
        {(zone.target_description || zone.expected_quantity != null || zone.current_quantity != null) && <div className="farm-plan-zone-foot">
            {zone.target_description && <span>{zone.target_description}</span>}
            {zone.current_quantity != null && <span>Recorded {zone.kind === 'livestock' ? 'animals' : zone.kind === 'storage' ? 'inventory entries' : 'surviving plants'}: <b>{Number(zone.current_quantity).toLocaleString()}</b></span>}
            {zone.expected_quantity != null && <span>Target count: <b>{zone.expected_quantity}</b></span>}
        </div>}
        {isCrop && <div className="farm-plan-hint"><span className="material-symbols-outlined" aria-hidden="true">straighten</span>Measured crop areas are managed separately.
            <button type="button" onClick={onOpenMeasurements}>Open measured setup</button></div>}
        {isFacility && <div className="farm-plan-hint"><span className="material-symbols-outlined" aria-hidden="true">info</span>Do not add the facility's measured area again when measuring its children.</div>}
    </article>;
}

export default function FarmPlan() {
    const { isAdministrator } = useAuth();
    const [plan, setPlan] = useState(null);
    const [draft, setDraft] = useState({});
    const [tab, setTab] = useState('areas');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [editingZone, setEditingZone] = useState(null);
    const [creatingFacility, setCreatingFacility] = useState(false);
    const [createLandRequest, setCreateLandRequest] = useState(0);
    const [expandedGroups, setExpandedGroups] = useState({});

    const load = async () => {
        try {
            const result = await farmPlanService.overview();
            setPlan(result);
            setDraft(readFarmPlanDraft(result.zones));
            setError('');
        } catch (e) { setError(e.message || 'Unable to load farm plan. Verify the backend migration.'); }
    };
    useEffect(() => { load(); }, []);
    const zones = plan?.zones || [];
    const children = code => zones.filter(zone => zone.parent_code === code);
    const roots = zones.filter(zone => !zone.parent_code);
    const activeGroups = roots.filter(zone => (tab === 'areas' && zone.kind === 'field') || (tab === 'facilities' && zone.kind === 'facility'));
    const groupsWithChildren = activeGroups.filter(zone => children(zone.code).length > 0);
    const allGroupsExpanded = areGroupsExpanded(expandedGroups, groupsWithChildren.map(zone => zone.code));
    const toggleGroup = code => setExpandedGroups(old => toggleExpandedGroup(old, code));
    const toggleAllGroups = () => setExpandedGroups(old => setGroupsExpanded(old, groupsWithChildren.map(zone => zone.code), !allGroupsExpanded));
    const pending = useMemo(() => collectFarmPlanUpdates(zones, draft), [plan, draft]);
    const preview = useMemo(() => previewFarmPlan(plan, draft), [plan, draft]);
    const activeError = preview.errors[0]?.message || '';
    const hasPending = pending.length > 0;
    const save = async () => {
        setError(''); setMessage('');
        if (!hasPending) { setMessage('There are no changes to save.'); return; }
        if (preview.errors.length) {
            const invalidCodes = new Set(Object.keys(preview.errorByCode).filter(code => preview.errorByCode[code]));
            setExpandedGroups(old => ({ ...old, ...Object.fromEntries(zones.filter(zone => zone.parent_code && invalidCodes.has(zone.code)).map(zone => [zone.parent_code, true])) }));
            setError(`Review the area values before saving: ${activeError}`);
            return;
        }
        setBusy(true);
        try {
            const result = await farmPlanService.update(pending);
            setPlan(result);
            setDraft(readFarmPlanDraft(result.zones));
            setMessage('Area plan saved. Existing crops, animals, stock and verified field measurements were preserved.');
        } catch (e) {
            const detail = e.message || 'Unable to save the area plan.';
            setError(`${detail}${e.status === 409 ? ' Check the area totals or reload changes from another session.' : ''}`);
        } finally { setBusy(false); }
    };
    const create = async payload => {
        setError(''); setMessage('');
        if (hasPending) return { error:'Save or discard your existing area edits before adding a new facility.' };
        setBusy(true);
        try {
            const result = await farmPlanService.addFacility(payload);
            setPlan(result);
            setDraft(readFarmPlanDraft(result.zones));
            setCreatingFacility(false);
            setMessage('Facility created. Its allocation was transferred from shared infrastructure.');
            return { ok:true };
        } catch (e) { return { error:e.message || 'Unable to create this facility.' }; }
        finally { setBusy(false); }
    };
    const applyModalEdit = (payload) => {
        if (!editingZone) return { error:'Choose an area to edit.' };
        setMessage(''); setError('');
        setDraft(old => ({ ...old, [editingZone.code]: { ...payload, name:payload.name.trim() } }));
        setEditingZone(null);
        return { ok:true };
    };
    const discard = () => { setDraft(readFarmPlanDraft(zones)); setError(''); setMessage('Changes discarded.'); };
    const nextTab = value => { setTab(value); setError(''); };
    const percent = preview.total ? Math.min(100, Math.max(0, (preview.allocated / preview.total) * 100)) : 0;

    return <div className="farm-plan-layout"><Sidebar/><main className="farm-plan-page">
        <header className="farm-plan-header"><div><h1>Farm Land &amp; Facilities</h1><p>Plan crop fields, livestock areas, storage and buildings in one editable farm layout.</p></div><AppHeaderActions/></header>

        {plan && <div className="farm-plan-stats">
            <div><small>Total farm area</small><strong>{formatArea(plan.total_area_m2)}</strong><span>Farm boundary</span></div>
            <div><small>Crop field allocation</small><strong>{formatArea(preview.cropTotal)}</strong><span>Fields A–D</span></div>
            <div><small>Facilities allocation</small><strong>{formatArea(preview.facilityTotal)}</strong><span>Livestock, storage and infrastructure</span></div>
            <div><small>Measured crop fields</small><strong>{formatArea(plan.measured_crop_m2)}</strong><span>Verified separately</span></div>
        </div>}
        {error && <div className="farm-plan-alert" role="alert"><span className="material-symbols-outlined" aria-hidden="true">error_outline</span><span>{error}</span><button type="button" onClick={() => { if (hasPending) { setError('Discard your unsaved changes before reloading the latest plan.'); return; } load(); }}>Reload</button></div>}
        {message && <div className="farm-plan-success" role="status"><span className="material-symbols-outlined" aria-hidden="true">check_circle</span>{message}</div>}
        <nav className="farm-plan-tabs" aria-label="Farm land sections">
            <button aria-current={tab==='areas' ? 'page' : undefined} className={tab==='areas'?'selected':''} type="button" onClick={() => nextTab('areas')}><span className="material-symbols-outlined">grid_view</span>Crop Fields &amp; Sections</button>
            <button aria-current={tab==='facilities' ? 'page' : undefined} className={tab==='facilities'?'selected':''} type="button" onClick={() => nextTab('facilities')}><span className="material-symbols-outlined">warehouse</span>Livestock &amp; Buildings</button>
            <button aria-current={tab==='measurements' ? 'page' : undefined} className={tab==='measurements'?'selected':''} type="button" onClick={() => nextTab('measurements')}><span className="material-symbols-outlined">straighten</span>Measured Crop Land</button>
        </nav>
        {!plan && !error && <div className="farm-plan-card">Loading your farm area plan…</div>}
        {plan && <>
            {tab !== 'measurements' && <>
                <section className="farm-plan-card farm-plan-overview" aria-label="Farm area allocation preview">
                    <div className="farm-plan-card-title"><div><h2>Farm space allocation</h2><p>Area totals update automatically when you edit a location.</p></div><strong className={preview.remaining < 0 ? 'is-over' : ''}>{percent.toFixed(1)}% allocated</strong></div>
                    <div className="farm-plan-bar" role="img" aria-label={`${formatArea(preview.cropTotal)} allocated to crop fields and ${formatArea(preview.facilityTotal)} facilities`}>
                        <div style={{ flex: Math.max(0, preview.cropTotal) }} className="farm-plan-bar-crops"/>
                        <div style={{ flex: Math.max(0, preview.facilityTotal) }} className="farm-plan-bar-facilities"/>
                        {preview.remaining > 0 && <div style={{ flex: preview.remaining }} className="farm-plan-bar-remaining"/>}
                    </div>
                    <div className="farm-plan-bar-key"><span><i className="farm-plan-dot crops"/>Crop fields · {formatArea(preview.cropTotal)}</span><span><i className="farm-plan-dot facilities"/>Facilities · {formatArea(preview.facilityTotal)}</span><span><i className="farm-plan-dot remaining"/>{preview.remaining < 0 ? 'Overallocated' : 'Not yet allocated'} · {formatArea(Math.abs(preview.remaining))}</span></div>
                    {activeError && <div className="farm-plan-budget-error" role="alert"><span className="material-symbols-outlined">warning</span>{activeError}</div>}
                </section>
                {(tab === 'areas' || tab === 'facilities') && <div className="farm-plan-section-toolbar">
                    <p>{tab === 'areas' ? 'Open a crop field to view and edit its sections.' : 'Open the facility zone to view livestock areas and buildings.'}</p>
                    <div className="farm-plan-toolbar-actions">
                        {groupsWithChildren.length > 0 && <button className="farm-plan-collapse-all" type="button" onClick={toggleAllGroups}><span className="material-symbols-outlined" aria-hidden="true">{allGroupsExpanded ? 'unfold_less' : 'unfold_more'}</span>{allGroupsExpanded ? 'Collapse all' : 'Expand all'}</button>}
                        {tab === 'areas' && isAdministrator && <button type="button" className="farm-plan-save" onClick={() => { setCreateLandRequest(old => old + 1); nextTab('measurements'); }}><span className="material-symbols-outlined">add</span>Create field or section</button>}
                    </div>
                </div>}
                {tab === 'areas' && roots.filter(zone => zone.kind === 'field').map(field => {
                    const fieldChildren = children(field.code);
                    const isExpanded = Boolean(expandedGroups[field.code]);
                    const childError = fieldChildren.some(item => Boolean(preview.errorByCode[item.code]));
                    return <section className="farm-plan-card farm-plan-location-card" key={field.code}>
                        <div className="farm-plan-card-title"><div><h2>{draft[field.code]?.name || field.name}</h2><p>{formatArea(draft[field.code]?.proposed_area_m2 || field.proposed_area_m2)} · Crop field</p></div>
                            <div className="farm-plan-group-controls">{childError && !isExpanded && <span className="farm-plan-hidden-warning" role="status">Review sections</span>}<FarmSectionToggle label={draft[field.code]?.name || field.name} count={fieldChildren.length} expanded={isExpanded} onToggle={() => toggleGroup(field.code)} controls={`farm-plan-children-${field.code}`}/></div>
                        </div>
                        <ZoneEditor zone={field} draft={draft[field.code]} onEdit={setEditingZone} isAdministrator={isAdministrator} error={preview.errorByCode[field.code]} onOpenMeasurements={() => nextTab('measurements')}/>
                        <div id={`farm-plan-children-${field.code}`} className="farm-plan-collapsible" hidden={!isExpanded}>
                            <div className="farm-plan-section-label">Sections within Field {field.code}</div>
                            <div className="farm-plan-children">{fieldChildren.map(section => <ZoneEditor key={section.code} zone={section} draft={draft[section.code]} onEdit={setEditingZone} isAdministrator={isAdministrator} error={preview.errorByCode[section.code]} onOpenMeasurements={() => nextTab('measurements')}/>)}</div>
                        </div>
                    </section>;
                })}
                {tab === 'facilities' && roots.filter(zone => zone.kind === 'facility').map(facility => {
                    const facilityChildren = children(facility.code);
                    const isExpanded = Boolean(expandedGroups[facility.code]);
                    const childError = facilityChildren.some(item => Boolean(preview.errorByCode[item.code]));
                    return <section className="farm-plan-card farm-plan-location-card" key={facility.code}>
                        <div className="farm-plan-card-title"><div><h2>{draft[facility.code]?.name || facility.name}</h2><p>Facility sub-areas are included in the parent allocation.</p></div>
                            <div className="farm-plan-group-controls">{childError && !isExpanded && <span className="farm-plan-hidden-warning" role="status">Review areas</span>}<FarmSectionToggle label={draft[facility.code]?.name || facility.name} count={facilityChildren.length} expanded={isExpanded} onToggle={() => toggleGroup(facility.code)} controls={`farm-plan-children-${facility.code}`} noun="area"/></div>
                        </div>
                        <ZoneEditor zone={facility} draft={draft[facility.code]} onEdit={setEditingZone} isAdministrator={isAdministrator} error={preview.errorByCode[facility.code]} onOpenMeasurements={() => nextTab('measurements')}/>
                        <div id={`farm-plan-children-${facility.code}`} className="farm-plan-collapsible" hidden={!isExpanded}>
                            <div className="farm-plan-section-label">Livestock areas, storage buildings and shared infrastructure</div>
                            <div className="farm-plan-children">{facilityChildren.map(zone => <ZoneEditor key={zone.code} zone={zone} draft={draft[zone.code]} onEdit={setEditingZone} isAdministrator={isAdministrator} error={preview.errorByCode[zone.code]} onOpenMeasurements={() => nextTab('measurements')}/>)}</div>
                        </div>
                    </section>;
                })}
                {tab==='facilities' && isAdministrator && <section className="farm-plan-card farm-plan-add-card farm-plan-create-prompt">
                    <div><h2>Need another facility?</h2><p>Additional storage buildings, livestock enclosures or offices can be added when needed.</p></div>
                    <button type="button" className="farm-plan-save" disabled={busy || hasPending} onClick={() => setCreatingFacility(true)}><span className="material-symbols-outlined">add</span>Create facility</button>
                    {hasPending && <p className="farm-plan-hint">Save or discard your pending edits before creating a facility.</p>}
                </section>}
            </>}
            {tab==='measurements' && <section className="farm-plan-card farm-plan-measured-card" id="measured-land"><LandSetup onSaved={() => load()} canEdit={isAdministrator} createRequestId={createLandRequest}/></section>}
            {plan.additional_fields?.length > 0 && <section className="farm-plan-card"><h2>Existing fields outside the standard layout</h2><p>Older fields are preserved in the measured totals.</p><ul>{plan.additional_fields.map(item=><li key={item.id}>{item.name} · {formatArea(item.measured_area_m2)}</li>)}</ul></section>}
            <div className="farm-plan-navigation"><Link href="/crops">Crop Management</Link><Link href="/livestock">Livestock Management</Link><Link href="/inventory">Inventory</Link><Link href="/task-management">Task Management</Link></div>
            {isAdministrator && hasPending && tab !== 'measurements' && <div className="farm-plan-actions" role="region" aria-label="Unsaved farm plan changes">
                <div className="farm-plan-unsaved"><span className="material-symbols-outlined" aria-hidden="true">edit_note</span><div><strong>{pending.length} unsaved change{pending.length===1?'':'s'}</strong><small>{preview.errors.length ? `${preview.errors.length} item${preview.errors.length===1?'':'s'} need attention` : 'Review and save all area changes together'}</small></div></div>
                <div className="farm-plan-action-buttons"><button type="button" className="farm-plan-discard" disabled={busy} onClick={discard}>Discard</button><button type="button" className="farm-plan-save" disabled={busy} onClick={save}><span className="material-symbols-outlined" aria-hidden="true">save</span>{busy ? 'Saving…' : 'Save changes'}</button></div>
            </div>}
        </>}
        {editingZone && <FarmAreaDialog key={editingZone.code} zone={editingZone} draft={draft[editingZone.code]} busy={busy} onClose={() => setEditingZone(null)} onApply={applyModalEdit}/>}
        {creatingFacility && <FarmAreaDialog key="new-facility" busy={busy} onClose={() => setCreatingFacility(false)} onApply={create}/>}
    </main></div>;
}
