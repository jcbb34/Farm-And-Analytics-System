'use client';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext.jsx';
import { cropPlanningService, changeCrop, changeField, estimatedCapacity, parseSnapshot, profileChoices, recommendedSpacingProfile, farmTodayDateKey } from '../../services/cropPlanningService.js';
import { calculateAutomaticCropProgress } from '../../services/cropService.js';
import SearchChoice from './SearchChoice.jsx';
import LandSetup from './LandSetup.jsx';
import { suggestedCropSection } from '../../services/farmPlanService.js';
import CareScheduleFields from './CareScheduleFields.jsx';
import PlantingMaterialFields from './PlantingMaterialFields.jsx';
import './CropPlanning.css';

const unknown = { value: 'unknown', label: 'Unknown / Not recorded' };
const unique = rows => [...new Map(rows.map(row => [row.value, row])).values()];
export function emptyDirectSchedules() {
    return ['watering', 'observation'].map(activity => ({ activity, enabled: false, start_date: '', end_date: null,
        frequency_days: 1, weekdays: [], employee_id: null, start_time: '', duration_minutes: '' }));
}

export default function CropPlanningFields({ form, setForm, crop, employees, preview, setPreview, editing }) {
    const { hasPermission, isAdministrator } = useAuth();
    const [references, setReferences] = useState(null), [land, setLand] = useState(null), [plantings, setPlantings] = useState([]);
    const [error, setError] = useState(''), [setup, setSetup] = useState(false), [loadingPreview, setLoadingPreview] = useState(false);
    const [spacingManuallyChosen, setSpacingManuallyChosen] = useState(false);
    const [locationManuallyChosen, setLocationManuallyChosen] = useState(false);
    useEffect(() => {
        let alive = true;
        Promise.all([cropPlanningService.references(), cropPlanningService.land()]).then(([ref, areas]) => {
            if (alive) { setReferences(ref); setLand(areas); }
        }).catch(e => { if (alive) setError(e.message); });
        return () => { alive = false; };
    }, []);
    useEffect(() => {
        setPlantings([]);
        if (!form.section_id) return;
        let alive = true;
        cropPlanningService.plantings(form.section_id).then(rows => { if (alive) setPlantings(rows); }).catch(e => { if (alive) setError(e.message); });
        return () => { alive = false; };
    }, [form.section_id]);
    const proposedSection = suggestedCropSection(land, form.crop_reference, form.variety_reference);
    useEffect(() => {
        if (editing || locationManuallyChosen || !proposedSection) return;
        setForm(old => {
            if (old.crop_reference !== form.crop_reference || old.variety_reference !== form.variety_reference ||
                Number(old.section_id) === Number(proposedSection.sectionId)) return old;
            const parent = (land?.fields || []).find(x => x.id === proposedSection.fieldId);
            return { ...old, field_id: proposedSection.fieldId, section_id: proposedSection.sectionId,
                field: parent?.name || '', area: '', shared_footprint_crop_id: null };
        });
    }, [editing, locationManuallyChosen, proposedSection?.sectionId, proposedSection?.fieldId, form.crop_reference, form.variety_reference, land, setForm]);
    const patch = change => { setPreview(null); setForm(old => ({ ...old, ...change })); };
    const profiles = references?.profiles || [];
    const crops = unique([...profiles.map(x => ({ value: x.crop_key, label: x.crop_name })),
        ...(references?.legacy_choices || []).map(x => ({ value: x.crop_reference || `custom:${x.name.toLowerCase()}`, label: x.name })),
        ...(form.name ? [{ value: form.crop_reference || `custom:${form.name.toLowerCase()}`, label: form.name }] : []), unknown]);
    const varieties = unique([...profiles.filter(x => x.crop_key === form.crop_reference).map(x => ({ value: x.variety_key, label: x.variety_name })),
        ...(references?.legacy_choices || []).filter(x => x.name === form.name).map(x => ({ value: x.variety_reference || `custom:${x.variety.toLowerCase()}`, label: x.variety })),
        ...(form.variety ? [{ value: form.variety_reference || `custom:${form.variety.toLowerCase()}`, label: form.variety }] : []), unknown]);
    const field = land?.fields.find(x => x.id === Number(form.field_id)) || land?.fields.find(x => x.sections.some(s => s.id === form.section_id));
    const section = field?.sections.find(x => x.id === form.section_id);
    const candidates = profileChoices(profiles, form.crop_reference, form.variety_reference);
    const recommended = recommendedSpacingProfile(profiles, form.crop_reference, form.variety_reference);
    const profile = profiles.find(x => Number(x.id) === Number(form.spacing_profile_id) && form.spacing_profile_id != null);
    // Crop choices may be made before /references finishes loading. Apply the
    // exact variety default once it arrives, never overwrite a manual selection
    // or the original spacing snapshot when editing an existing planting.
    useEffect(() => {
        if (!references || !recommended || spacingManuallyChosen || form.spacing_profile_id != null || form.spacing_override) return;
        if (editing && crop?.crop_reference === form.crop_reference && crop?.variety_reference === form.variety_reference) return;
        setForm(old => old.crop_reference === recommended.crop_key && old.variety_reference === recommended.variety_key
            && old.spacing_profile_id == null && !old.spacing_override
            ? { ...old, spacing_profile_id: recommended.id } : old);
    }, [references, recommended?.id, spacingManuallyChosen, form.crop_reference, form.variety_reference,
        form.spacing_profile_id, form.spacing_override, editing, crop?.crop_reference, crop?.variety_reference, setForm]);
    const recordedSnapshot = crop?.crop_reference === form.crop_reference && crop?.variety_reference === form.variety_reference ? parseSnapshot(crop?.spacing_snapshot_json) : null;
    const spacing = form.spacing_override || profile || recordedSnapshot;
    const estimated = spacing ? estimatedCapacity(form.area, spacing.row_spacing_m, spacing.plant_spacing_m, spacing.layout) : null;
    const existing = form.registration_kind === 'existing';
    const today = farmTodayDateKey();
    const historicalPlantingDate = Boolean(editing && crop?.plantingDate && crop.plantingDate < today && form.plantingDate === crop.plantingDate);
    const progress = calculateAutomaticCropProgress(form.plantingDate, form.estimatedHarvest);
    const duplicates = plantings.filter(x => x.id !== crop?.id && x.crop_reference === form.crop_reference && x.variety_reference === form.variety_reference && x.name === form.name);
    const previewSchedule = async () => {
        setLoadingPreview(true); setError('');
        try { setPreview(await cropPlanningService.preview({ care_schedules: form.care_schedules.filter(x => x.enabled),
            assigned_employee_id: form.assignedEmployeeId ? Number(form.assignedEmployeeId) : null,
            crop_id: crop?.id, effective_date: form.schedule_effective_date || null })); }
        catch (e) { setError(e.message); } finally { setLoadingPreview(false); }
    };
    return <>
        {error && <p role="alert" className="crop-planning-error">{error}</p>}
        <label className="crop-planning-check crop-existing-toggle"><input type="checkbox" checked={existing} onChange={event => patch({ registration_kind: event.target.checked ? 'existing' : 'new',
            ...(event.target.checked && form.plantingDate > today ? { plantingDate: today } : {}),
            ...(!event.target.checked ? { initial_status: 'Growing', confirm_ready: false, planting_date_precision: form.planting_date_precision === 'unknown' ? 'known' : form.planting_date_precision, plantingDate: form.plantingDate < today ? today : form.plantingDate } : {}) })} />Already growing on the farm</label>
        <p className="crop-planning-intro">Register one physical planting at a time. Check existing records to avoid duplicates.</p>
        <section className="crop-form-section">
            <div className="crop-form-section-title"><span className="material-symbols-outlined">eco</span><div><h3>Crop Information</h3><p>Select the crop and its saved location.</p></div></div>
            <div className="crop-form-grid">
                <SearchChoice label="Crop Name" required value={form.crop_reference || (form.name ? `custom:${form.name.toLowerCase()}` : '')} options={crops}
                    allowCustom={hasPermission('crops:full-edit')} onChange={choice => { setSpacingManuallyChosen(false); setLocationManuallyChosen(false); setPreview(null); setForm(old => changeCrop(old, choice)); }} />
                <SearchChoice label="Variety / Type" required disabled={!form.name} value={form.variety_reference || (form.variety ? `custom:${form.variety.toLowerCase()}` : '')} options={varieties}
                    allowCustom={hasPermission('crops:full-edit')} onChange={choice => {
                        setSpacingManuallyChosen(false); setLocationManuallyChosen(false);
                        const selected = recommendedSpacingProfile(profiles, form.crop_reference, choice.value);
                        patch({ variety: choice.label, variety_reference: choice.value, spacing_profile_id: selected?.id ?? null, spacing_override: null, planting_inventory_item_id: null });
                    }} />
                <SearchChoice label="Field" required={form.registration_kind !== 'legacy'} value={field?.id || ''} options={(land?.fields || []).map(x => ({ value: x.id, label: x.name }))}
                    onChange={choice => { setLocationManuallyChosen(true); setPreview(null); setForm(old => changeField(old, choice)); }} />
                <SearchChoice label="Section" required={form.registration_kind !== 'legacy'} disabled={!field} value={form.section_id || ''}
                    options={(field?.sections || []).map(x => ({ value: x.id, label: `${x.name} · ${x.status}` }))} onChange={choice => { setLocationManuallyChosen(true); patch({ section_id: choice.value, area: '', shared_footprint_crop_id: null }); }} />
                {proposedSection && !editing && <p className="crop-planning-note" style={{gridColumn:'1 / -1',margin:0}}>Suggested location: Section {proposedSection.code}. Confirm the section’s measured area before planting.</p>}
                <label className="crop-form-group">Field size<input readOnly value={field?.area_m2 == null ? 'Unconfigured' : `${field.area_m2} m² (${Number(field.area_m2) / 10000} ha)`} /></label>
                <label className="crop-form-group">Section size<input readOnly value={section?.area_m2 == null ? 'Unconfigured' : `${section.area_m2} m² (${Number(section.area_m2) / 10000} ha)`} /></label>
                <label className="crop-form-group">Available usable area<input readOnly value={section?.available_area_m2 == null ? 'Unconfigured' : `${section.available_area_m2} m² (${Number(section.available_area_m2) / 10000} ha)`} /></label>
                <label className="crop-form-group">Area for this planting (ha)<input required type="number" min="0.000001" step="0.000001" value={form.area}
                    max={section?.available_area_m2 == null ? undefined : Number(section.available_area_m2) / 10000 + (crop?.section_id === form.section_id && !crop?.area_cleared_at ? Number(crop.area || 0) : 0)}
                    readOnly={Boolean(form.shared_footprint_crop_id)} onChange={event => patch({ area: event.target.value })} /></label>
            </div>
            {form.registration_kind === 'legacy' && !crop?.section_id && <p className="crop-planning-note">Legacy location: {form.field}. Its historical area has not been assumed to be a measured section. Select a measured location to map it.</p>}
            {(!land?.fields.length || (section && section.area_m2 == null)) && <p className="crop-planning-note">Measured sizes are not configured. {isAdministrator ? 'Configure the field and section measurements before allocating planting space.' : 'Ask an administrator to enter measured field and section areas.'}</p>}
            {isAdministrator && <button className="crop-planning-action" type="button" aria-expanded={setup} onClick={() => setSetup(old => !old)}><span className="material-symbols-outlined" aria-hidden="true">map</span>{setup ? 'Close land setup' : !land?.fields.length ? 'Configure fields and sections' : 'Manage fields and sections'}</button>}
            {setup && isAdministrator && <LandSetup initialLand={land} onSaved={setLand} embedded />}
            {section && plantings.some(x => x.id !== crop?.id && x.footprint_id) && <label className="crop-form-group">Intercropping / shared footprint<select value={form.shared_footprint_crop_id || ''} onChange={event => {
                const parent = plantings.find(x => x.id === Number(event.target.value));
                patch({ shared_footprint_crop_id: parent?.id || null, area: parent ? String(parent.area_hectares) : '' });
            }}><option value="">Separate physical allocation</option>{plantings.filter(x => x.id !== crop?.id && x.footprint_id).map(x => <option value={x.id} key={x.id}>Share {x.code} — {x.name}</option>)}</select></label>}
            {form.shared_footprint_crop_id && <label className="crop-form-group">Shared planting arrangement<input required maxLength={500} value={form.shared_footprint_reason || ''} onChange={event => patch({ shared_footprint_reason: event.target.value })} /></label>}
            {duplicates.length > 0 && <div className="crop-planning-note"><strong>Possible duplicate planting:</strong> {duplicates.map(x => x.code).join(', ')}.
                <label className="crop-planning-check"><input type="checkbox" checked={form.duplicate_acknowledged || false} onChange={event => patch({ duplicate_acknowledged: event.target.checked })} />I checked these records; this is a distinct physical planting.</label></div>}
        </section>
        <section className="crop-form-section">
            <div className="crop-form-section-title"><span className="material-symbols-outlined">calendar_month</span><div><h3>Planting & Growth</h3><p>Keep actual counts separate from estimates.</p></div></div>
            <div className="crop-form-grid">
                <label className="crop-form-group">Spacing profile
                    <select aria-label="Spacing profile" disabled={!references || !form.variety_reference} value={form.spacing_profile_id ?? ''}
                        onChange={event => { setSpacingManuallyChosen(true); patch({ spacing_profile_id: event.target.value ? Number(event.target.value) : null, spacing_override: null }); }}>
                        <option value="" disabled={Boolean(candidates.length && !recordedSnapshot)}>
                            {!references ? 'Loading spacing profiles…' : recordedSnapshot ? 'Keep recorded spacing snapshot'
                                : !form.variety_reference ? 'Choose a crop and variety first'
                                : candidates.length ? 'Select a recommended profile' : 'No verified spacing profile for this variety'}
                        </option>
                        {candidates.map(x => <option value={x.id} key={x.id}>{x.label} · v{x.version}{x.is_default ? ' · recommended' : ' · alternative'}</option>)}
                    </select>
                    {profile && <small>{profile.is_default ? 'Default recommendation' : 'Alternative profile'}: {profile.row_spacing_m} m × {profile.plant_spacing_m} m · {profile.layout} layout for {profile.variety_name}.</small>}
                    {references && !profiles.length && <small role="alert">No saved spacing references were returned. Ask the administrator to verify the crop-planning database migration and seed data.</small>}
                </label>
                <label className="crop-form-group">Estimated Capacity<input readOnly value={estimated == null ? 'Not estimated' : `${estimated.toLocaleString()} ${profile?.count_unit || recordedSnapshot?.count_unit || 'plant'} positions`} /></label>
                <label className="crop-form-group">{existing ? 'Actual Quantity Planted' : 'Planned Planting Positions'}<input required={!existing && form.registration_kind !== 'legacy'} type="number" min="0" step="1" value={form.quantityPlanted} placeholder="Unknown / Not recorded" onChange={event => patch({ quantityPlanted: event.target.value })} /></label>
                <label className="crop-form-group">{existing ? 'Current Surviving Plants' : 'Current Surviving Plants (recorded after planting task approval)'}<input disabled={!existing && !editing} type="number" min="0" step="1" value={form.currentSurviving} placeholder="Unknown / Not recorded" onChange={event => patch({ currentSurviving: event.target.value })} /></label>
                <label className="crop-form-group">Planting date precision<select value={form.planting_date_precision || 'known'} onChange={event => patch({ planting_date_precision: event.target.value, ...(event.target.value === 'unknown' ? { plantingDate: '' } : {}) })}>
                    <option value="known">Known</option><option value="estimated">Explicitly estimated</option>{existing && <option value="unknown">Unknown</option>}
                </select></label>
                <label className="crop-form-group">Planting Date<input type="date" required={!existing || form.planting_date_precision !== 'unknown'} disabled={form.planting_date_precision === 'unknown'} min={!existing ? (historicalPlantingDate ? crop.plantingDate : today) : undefined} max={existing ? today : undefined} value={form.plantingDate} onChange={event => {
                    const selected = event.target.value;
                    if (!existing && selected && selected < today && selected !== crop?.plantingDate) {
                        setError('A new planting cannot be backdated. Choose today or a future planting date.'); return;
                    }
                    setError(''); patch({ plantingDate: selected });
                }} />{!existing && <small>New planting: today or a future date only.</small>}{historicalPlantingDate && <small>The original planting date remains unchanged for this recorded crop.</small>}</label>
                <label className="crop-form-group">{existing ? 'Expected Next Harvest (optional)' : 'Expected First Harvest'}<input type="date" required={!existing} value={form.estimatedHarvest} min={form.plantingDate || undefined} onChange={event => patch({ estimatedHarvest: event.target.value })} /></label>
                <label className="crop-form-group">Estimated schedule progress<input readOnly value={progress == null ? 'Not estimated' : `${progress}%`} /></label>
                {existing && !['Harvested', 'Failed'].includes(crop?.status) && <label className="crop-form-group">Observed current status<select value={form.initial_status || 'Growing'} onChange={event => patch({ initial_status: event.target.value })}>
                    <option>Growing</option><option>Ready for Harvest</option><option value="Harvesting">Harvesting / Partially Harvested</option>
                </select></label>}
                {['Harvested', 'Failed'].includes(crop?.status) && <label className="crop-form-group">Recorded status<input readOnly value={crop.status} /></label>}
            </div>
            {!existing && !editing && <PlantingMaterialFields form={form} setForm={setForm} capacity={estimated} />}
            {!existing && estimated != null && <button className="crop-planning-action" type="button" onClick={() => patch({ quantityPlanted: String(estimated), currentSurviving: existing ? String(estimated) : "" })}><span className="material-symbols-outlined" aria-hidden="true">auto_awesome</span>Use capacity as a suggested count</button>}
            {existing && ['Ready for Harvest', 'Harvesting'].includes(form.initial_status) && <label className="crop-planning-check"><input required type="checkbox" checked={form.confirm_ready || false} onChange={event => patch({ confirm_ready: event.target.checked })} />I physically confirmed this planting is producing or ready for harvest. This creates no historical yield or stock.</label>}
            {spacing && <div className="crop-planning-note"><strong>{spacing.row_spacing_m} m between rows × {spacing.plant_spacing_m} m between plants · {spacing.layout}</strong><p>{profile?.evidence_scope || recordedSnapshot?.evidence_scope}</p><p>{profile?.guidance || recordedSnapshot?.guidance}</p>
                {(profile?.source_url || recordedSnapshot?.source_url) && <a href={profile?.source_url || recordedSnapshot?.source_url} target="_blank" rel="noreferrer">Spacing source</a>}
                {(profile?.additional_source_urls || recordedSnapshot?.additional_source_urls || []).map((url, index) => <span key={url}> · <a href={url} target="_blank" rel="noreferrer">Related reference {index + 1}</a></span>)}
                <p>Capacity uses this planting's allocated usable area. Boundary shape and actual positions still need checking. Vacant positions do not release continuous land.</p></div>}
            {hasPermission('crops:full-edit') && <details className="crop-spacing-details"><summary><span className="material-symbols-outlined" aria-hidden="true">straighten</span>Adjust spacing for the actual arrangement</summary><div className="crop-form-grid">
                {['row_spacing_m', 'plant_spacing_m'].map(key => <label key={key}>{key === 'row_spacing_m' ? 'Row spacing (m)' : 'Plant spacing (m)'}<input type="number" min="0.0001" step="0.0001" value={form.spacing_override?.[key] ?? spacing?.[key] ?? ''} onChange={event => patch({ spacing_override: { ...spacing, ...form.spacing_override, [key]: event.target.value } })} /></label>)}
                <label>Layout<select value={form.spacing_override?.layout || spacing?.layout || 'rectangular'} onChange={event => patch({ spacing_override: { ...spacing, ...form.spacing_override, layout: event.target.value } })}><option value="rectangular">Rectangular</option><option value="square">Square</option></select></label>
                <label>Arrangement evidence<input value={form.spacing_override?.evidence_scope || ''} onChange={event => patch({ spacing_override: { ...spacing, ...form.spacing_override, evidence_scope: event.target.value } })} /></label>
                <label>Source URL<input type="url" value={form.spacing_override?.source_url || spacing?.source_url || ''} onChange={event => patch({ spacing_override: { ...spacing, ...form.spacing_override, source_url: event.target.value } })} /></label>
            </div></details>}
        </section>
        <section className="crop-form-section">
            <div className="crop-form-section-title"><span className="material-symbols-outlined">assignment_ind</span><div><h3>Employee & Care Plan</h3><p>Set actual work times. The shared calendar checks working hours, breaks, leave and competing crop/livestock work.</p></div></div>
            <label className="crop-form-group">Assigned Employee<select value={form.assignedEmployeeId} onChange={event => patch({ assignedEmployeeId: event.target.value })}><option value="">Unassigned</option>{employees.map(x => <option value={x.id} key={x.id}>{x.full_name}</option>)}</select></label>
            {editing && <label className="crop-form-group">Schedule changes effective from<input type="date" value={form.schedule_effective_date || ''} onChange={event => patch({ schedule_effective_date: event.target.value || null })} /></label>}
            {(form.care_schedules || emptyDirectSchedules()).map((schedule, index) => <CareScheduleFields key={schedule.activity} schedule={schedule} employees={employees} defaultEmployee={form.assignedEmployeeId}
                originalStartDate={(parseSnapshot(crop?.care_schedules_json) || []).find(old => old.activity === schedule.activity)?.start_date || ''}
                onChange={value => patch({ care_schedules: form.care_schedules.map((old, i) => i === index ? value : old) })} />)}
            <button className="crop-planning-action" type="button" disabled={loadingPreview} onClick={previewSchedule}><span className="material-symbols-outlined" aria-hidden="true">event_available</span>{loadingPreview ? 'Checking…' : 'Preview upcoming activities'}</button>
            {preview && <div className="crop-planning-note" aria-live="polite"><strong>Upcoming Activities · {preview.horizon_days} day window</strong><p>{preview.note}</p>
                <ul className="crop-upcoming">{preview.occurrences.map((x, i) => <li className={x.conflict ? 'crop-planning-error' : ''} key={i}>{x.date} · {x.start_time.slice(0, 5)}–{x.end_time.slice(0, 5)} · {x.activity}{x.conflict ? ` — ${x.conflict}` : ''}</li>)}</ul>
                {!preview.occurrences.length && <p>No enabled activity occurrences in this scheduling window.</p>}</div>}
            <label className="crop-form-group">Notes<textarea rows={3} value={form.notes} onChange={event => patch({ notes: event.target.value })} /></label>
        </section>
    </>;
}
