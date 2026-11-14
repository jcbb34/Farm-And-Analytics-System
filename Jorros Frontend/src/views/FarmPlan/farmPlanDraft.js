/** Pure preview and validation: proposed areas are never physical measurements. */
const asNumber = value => value === '' || value == null ? null : Number(value);
const positive = value => Number.isFinite(value) && value > 0;

export function readFarmPlanDraft(zones = []) {
    return Object.fromEntries(zones.map(zone => [zone.code, {
        name: zone.name,
        proposed_area_m2: String(zone.proposed_area_m2),
        measured_area_m2: zone.measured_area_m2 == null ? '' : String(zone.measured_area_m2),
    }]));
}

export function collectFarmPlanUpdates(zones = [], draft = {}) {
    return zones.flatMap(zone => {
        const entry = draft[zone.code];
        if (!entry) return [];
        const name = (entry.name || '').trim();
        const proposed = asNumber(entry.proposed_area_m2);
        const measured = entry.measured_area_m2 === '' ? null : asNumber(entry.measured_area_m2);
        const originalMeasured = zone.measured_area_m2 == null ? null : Number(zone.measured_area_m2);
        const proposedChanged = proposed !== Number(zone.proposed_area_m2);
        const nameChanged = name !== zone.name;
        const measuredChanged = !['field', 'section'].includes(zone.kind) && measured !== originalMeasured;
        if (!proposedChanged && !nameChanged && !measuredChanged) return [];
        const update = { code: zone.code, name, proposed_area_m2: entry.proposed_area_m2,
            expected_version: zone.edit_version };
        if (zone.linked_edit_version != null) update.expected_linked_version = zone.linked_edit_version;
        // Omit this for unchanged verification and for crops: it is not a planning value.
        if (measuredChanged) update.measured_area_m2 = entry.measured_area_m2 === '' ? null : entry.measured_area_m2;
        return [update];
    });
}

export function previewFarmPlan(plan, draft) {
    const zones = plan?.zones || [];
    const area = code => asNumber(draft?.[code]?.proposed_area_m2);
    const verified = zone => ['field', 'section'].includes(zone.kind)
        ? asNumber(zone.measured_area_m2) : asNumber(draft?.[zone.code]?.measured_area_m2);
    const errors = [];
    const errorByCode = {};
    const addError = (code, message) => {
        errors.push({ code, message });
        if (code && !errorByCode[code]) errorByCode[code] = message;
    };
    for (const zone of zones) {
        const entry = draft?.[zone.code];
        if (!entry) continue;
        if (!(entry.name || '').trim()) addError(zone.code, `${zone.code}: enter a location name.`);
        if (entry.name?.trim().length > 100) addError(zone.code, `${zone.code}: name cannot exceed 100 characters.`);
        if (!positive(area(zone.code))) addError(zone.code, `${zone.code}: area allocation must be greater than 0 m².`);
        if (!['field', 'section'].includes(zone.kind) && entry.measured_area_m2 !== '' && !positive(verified(zone))) {
            addError(zone.code, `${zone.code}: a verified measurement must be greater than 0 m², or left blank if not measured.`);
        }
        const match = zones.find(other => other.code !== zone.code && other.parent_code === zone.parent_code
            && other.kind === zone.kind && (draft?.[other.code]?.name || other.name).trim().toLowerCase() === entry.name?.trim().toLowerCase());
        if (match) addError(zone.code, `${zone.code} and ${match.code}: locations of the same type cannot have the same name.`);
    }
    const cropTotal = zones.filter(zone => !zone.parent_code && zone.kind === 'field')
        .reduce((sum, zone) => sum + (area(zone.code) || 0), 0);
    const facilityTotal = zones.filter(zone => !zone.parent_code && zone.kind === 'facility')
        .reduce((sum, zone) => sum + (area(zone.code) || 0), 0);
    const total = asNumber(plan?.total_area_m2) || 0;
    if (cropTotal + facilityTotal > total + 0.00001) {
        addError(null, `Area allocation exceeds the ${total.toLocaleString()} m² farm by ${(cropTotal + facilityTotal - total).toLocaleString(undefined, { maximumFractionDigits: 2 })} m². Reduce another field or facility in the same batch before saving.`);
    }
    for (const parent of zones) {
        const children = zones.filter(zone => zone.parent_code === parent.code);
        if (!children.length) continue;
        const childTotal = children.reduce((sum, child) => sum + (area(child.code) || 0), 0);
        if (positive(area(parent.code)) && childTotal > area(parent.code) + 0.00001) {
            addError(parent.code, `${parent.code}: subdivisions total ${childTotal.toLocaleString()} m², exceeding the parent allocation of ${area(parent.code).toLocaleString()} m². Adjust the parent or its sections together.`);
        }
        const verifiedParent = verified(parent);
        const childrenVerified = children.reduce((sum, child) => sum + (verified(child) || 0), 0);
        if (verifiedParent != null && childrenVerified > verifiedParent + 0.00001) {
            addError(parent.code, `${parent.code}: verified child areas total ${childrenVerified.toLocaleString()} m², exceeding the verified parent of ${verifiedParent.toLocaleString()} m².`);
        }
    }
    const measuredCrop = asNumber(plan?.measured_crop_m2) || 0;
    const facility = zones.find(zone => zone.code === 'FAC' && zone.kind === 'facility');
    const facilityVerified = facility ? verified(facility) : null;
    const childFacilityVerified = zones.filter(zone => zone.parent_code === 'FAC')
        .reduce((sum, zone) => sum + (verified(zone) || 0), 0);
    const verifiedFacilityTotal = facilityVerified == null ? childFacilityVerified : facilityVerified;
    if (verifiedFacilityTotal + measuredCrop > total + 0.00001) {
        addError('FAC', `Verified facilities (${verifiedFacilityTotal.toLocaleString()} m²) plus measured crop fields (${measuredCrop.toLocaleString()} m²) exceed the farm's ${total.toLocaleString()} m². Check physical measurements.`);
    }
    return { cropTotal, facilityTotal, total, allocated: cropTotal + facilityTotal,
        remaining: total - cropTotal - facilityTotal, errors, errorByCode };
}

export function canArchiveFarmZone(zone) {
    if (!zone || zone.kind === 'field' || zone.kind === 'section' || zone.kind === 'facility'
        || zone.code === 'R1') return { allowed: false, reason: 'This is a permanent farm planning area.' };
    if (zone.measured_area_m2 != null) return { allowed: false, reason: 'Remove the verified measurement only if it was entered incorrectly, then save before archiving.' };
    if (Number(zone.current_quantity || 0) > 0) return { allowed: false, reason: 'Move all related livestock or inventory records before archiving.' };
    return { allowed: true, reason: '' };
}
