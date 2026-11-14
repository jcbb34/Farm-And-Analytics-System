import { httpClient } from './httpClient.js';
const unwrap = response => response?.data ?? response;
const request = promise => promise.then(unwrap);
export const farmPlanService = {
    overview: () => request(httpClient.get('/farm-plan')),
    update: updates => request(httpClient.put('/farm-plan', { updates })),
    addFacility: data => request(httpClient.post('/farm-plan/facilities', data)),
    archiveFacility: (code, expectedVersion) => request(httpClient.post(`/farm-plan/facilities/${encodeURIComponent(code)}/archive`, undefined, { query: { expected_version: expectedVersion } })),
};

// Recommendations are *locations*, not confirmed plantings or verified spacing.
export const DEFAULT_CROP_SECTIONS = Object.freeze({
    'coconut:tall': 'A1', 'banana:lakatan': 'B1', 'banana:saba': 'B2',
    'cassava:lakan-1': 'C1', 'taro:morondon': 'C2', 'taro:iniito-vg2': 'C3',
    'sweet-potato:nsic-sp20': 'C4', 'sweet-potato:nsic-sp30': 'C5',
    'basil:siam-queen': 'D1', 'basil:genovese': 'D2',
});
export function suggestedCropSection(land, cropKey, varietyKey) {
    const code = DEFAULT_CROP_SECTIONS[`${cropKey}:${varietyKey}`];
    if (!code) return null;
    const target = `Section ${code}`;
    for (const field of (land?.fields || [])) {
        const section = (field.sections || []).find(item => item.plan_code === code || item.name === target || item.name === code);
        if (section) return { fieldId: field.id, sectionId: section.id, code };
    }
    return null;
}
