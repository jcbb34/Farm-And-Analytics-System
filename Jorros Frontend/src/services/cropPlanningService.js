import { httpClient } from './httpClient.js';

const unwrap = response => response?.data ?? response;
const request = promise => promise.then(unwrap);
export const cropPlanningService = {
    references: () => request(httpClient.get('/crop-planning/references')),
    customReference: name => request(httpClient.get('/crop-planning/custom-reference', { query: { name } })),
    land: () => request(httpClient.get('/crop-planning/land')),
    saveFarm: data => request(httpClient.put('/crop-planning/land', data)),
    saveField: (id, data) => request(id ? httpClient.put(`/crop-planning/fields/${id}`, data) : httpClient.post('/crop-planning/fields', data)),
    saveSection: (fieldId, id, data) => request(id ? httpClient.put(`/crop-planning/sections/${id}`, data) : httpClient.post(`/crop-planning/fields/${fieldId}/sections`, data)),
    preview: data => request(httpClient.post('/crop-planning/schedule-preview', data)),
    slots: query => request(httpClient.get('/crop-planning/available-slots', { query })),
    plantings: section_id => request(httpClient.get('/crop-planning/plantings', { query: { section_id } })),
    plantingMaterials: (crop_reference, variety_reference, planting_date, planned_count) =>
        request(httpClient.get('/crops/planting-material-options', { query: {
            crop_reference, variety_reference, planting_date, planned_count
        } })),
    positions: id => request(httpClient.get(`/crop-planning/plantings/${id}/positions`)),
    recordPosition: (id, data, key) => request(httpClient.post(`/crop-planning/plantings/${id}/positions`, data, { headers: { 'Idempotency-Key': key } })),
    end: (id, data) => request(httpClient.post(`/crop-planning/plantings/${id}/end`, data)),
    adjustProfile: (id, data) => request(httpClient.post(`/crop-planning/profiles/${id}/versions`, data)),
};

// Match the farm clock used by the API, even when the operator's computer timezone differs.
export function farmTodayDateKey(instant = new Date()) {
    const pieces = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(instant);
    const part = type => pieces.find(piece => piece.type === type)?.value;
    return `${part('year')}-${part('month')}-${part('day')}`;
}

// Old recorded start dates can remain unchanged on edit, not be backdated anew.
export function validScheduleStartDate(nextDate, originalDate = '', today = farmTodayDateKey()) {
    return !nextDate || nextDate >= today || (Boolean(originalDate) && nextDate === originalDate);
}

export function parseSnapshot(value) {
    if (!value) return null;
    if (typeof value === 'object') return value;
    try { return JSON.parse(value); } catch { return null; }
}

function fraction(value) {
    const match = String(value ?? '').match(/^(\d+)(?:\.(\d+))?$/);
    if (!match) return null;
    return [BigInt(match[1] + (match[2] || '')), 10n ** BigInt((match[2] || '').length)];
}

export function estimatedCapacity(areaHa, rowSpacing, plantSpacing, layout) {
    if (!['square', 'rectangular'].includes(layout)) return null;
    const area = fraction(areaHa), row = fraction(rowSpacing), plant = fraction(plantSpacing);
    if (!area || !row || !plant || !row[0] || !plant[0]) return null;
    const result = area[0] * 10000n * row[1] * plant[1] / (area[1] * row[0] * plant[0]);
    return result <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(result) : null;
}

export const planningKeys = ['registration_kind', 'crop_reference', 'variety_reference', 'section_id', 'spacing_profile_id',
    'spacing_override', 'planting_inventory_item_id', 'planting_start_time', 'shared_footprint_crop_id', 'shared_footprint_reason', 'duplicate_acknowledged',
    'planting_date_precision', 'initial_status', 'confirm_ready', 'care_schedules', 'schedule_effective_date'];

export function planningPayload(value) {
    return Object.fromEntries(planningKeys.filter(key => value[key] !== undefined).map(key => [key, value[key]]));
}

export function profileChoices(profiles, cropKey, varietyKey) {
    return profiles.filter(profile => profile.crop_key === cropKey && profile.variety_key === varietyKey);
}

// Use only the catalog's verified default for the exact crop+variety. Never infer
// spacing for Unknown/custom varieties or silently borrow another variety's data.
export function recommendedSpacingProfile(profiles, cropKey, varietyKey) {
    if (!cropKey || !varietyKey || cropKey === 'unknown' || varietyKey === 'unknown') return null;
    return profileChoices(profiles || [], cropKey, varietyKey)
        .filter(profile => profile.is_default === true && Number.isFinite(Number(profile.id)))
        .sort((a, b) => Number(b.version || 0) - Number(a.version || 0) || Number(b.id) - Number(a.id))[0] || null;
}

export function changeCrop(form, choice) {
    return { ...form, name: choice.label, crop_reference: choice.value, variety: '', variety_reference: null,
        planting_inventory_item_id: null,
        spacing_profile_id: null, spacing_override: null, shared_footprint_crop_id: null };
}

export function changeField(form, field) {
    return { ...form, field: field.label, field_id: field.value, section_id: null, area: '', shared_footprint_crop_id: null };
}
