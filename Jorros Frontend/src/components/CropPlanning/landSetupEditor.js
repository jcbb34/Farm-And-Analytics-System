/** Client-side checks mirror the crop land API's name/measurement rules. */
export const emptyLandEditor = { name: '', area_m2: '', unavailable_area_m2: '0', unavailable_reason: '' };

/** Measured size minus excluded physical space (distinct from crop allocations). */
export function usableMeasuredArea(row) {
    if (row?.area_m2 == null || row.area_m2 === '') return null;
    const measured = Number(row.area_m2);
    const unavailable = Number(row.unavailable_area_m2 || 0);
    if (!Number.isFinite(measured) || !Number.isFinite(unavailable)) return null;
    return measured - unavailable;
}

export function existingLandName(land, { type, parentId, editingId, name }) {
    const normalized = String(name || '').trim().toLocaleLowerCase();
    if (!normalized) return null;
    const rows = type === 'field'
        ? (land?.fields || [])
        : (land?.fields || []).find(field => String(field.id) === String(parentId))?.sections || [];
    return rows.find(row => String(row.id) !== String(editingId ?? '') && row.name.trim().toLocaleLowerCase() === normalized) || null;
}

export function validateLandEditor({ land, type, parentId, editingId, form }) {
    if (!form.name?.trim()) return 'Enter a field or section name.';
    if (form.name.trim().length > 100) return 'The name must be 100 characters or fewer.';
    if (type === 'section' && !parentId) return 'Choose the parent field for this section.';
    if (existingLandName(land, { type, parentId, editingId, name: form.name })) {
        return `A ${type} named "${form.name.trim()}" already exists${type === 'section' ? ' in this field' : ''}. Select Edit on the existing record instead.`;
    }
    const area = form.area_m2 === '' ? null : Number(form.area_m2);
    const unavailable = Number(form.unavailable_area_m2);
    if (area !== null && (!Number.isFinite(area) || area <= 0)) return 'Measured area must be greater than zero, or left blank if not yet measured.';
    if (!Number.isFinite(unavailable) || unavailable < 0) return 'Unavailable area must be zero or greater.';
    if (area === null && unavailable > 0) return 'Enter a measured area before marking any space unavailable.';
    if (area !== null && unavailable > area) return 'Unavailable space cannot exceed the measured area.';
    if (unavailable > 0 && !form.unavailable_reason?.trim()) return 'Describe why the space is unavailable.';
    if (type === 'section' && area !== null) {
        const field = (land?.fields || []).find(row => String(row.id) === String(parentId));
        if (field && field.area_m2 == null) return `Measure "${field.name}" first, before measuring its sections.`;
        if (field?.area_m2 != null) {
            const otherSections = (field.sections || []).filter(row => String(row.id) !== String(editingId ?? ''));
            const used = otherSections.reduce((sum, row) => sum + Number(row.area_m2 || 0), 0);
            const capacity = usableMeasuredArea(field);
            if (capacity <= 0 && area > 0) {
                return `"${field.name}" has ${Number(field.area_m2).toLocaleString()} m² measured but ${Number(field.unavailable_area_m2 || 0).toLocaleString()} m² marked unavailable, leaving 0 m² usable. Edit the parent field and correct its unavailable area before saving this section.`;
            }
            if (used + area > capacity + 0.000001) {
                return `Sections would exceed "${field.name}" by ${(used + area - capacity).toLocaleString(undefined, { maximumFractionDigits: 4 })} m². Edit the parent or another section first.`;
            }
        }
    }
    return '';
}
