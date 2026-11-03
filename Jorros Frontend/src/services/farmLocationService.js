import { httpClient } from './httpClient.js';
import { eventDomain, isEquipmentItem } from './eventPlanning.js';
export const cleanLocationName = (value) => String(value || '').trim().replace(/\s+/g, ' ');
export const locationSearchKey = (value) => cleanLocationName(value).normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
export function uniqueLocationNames(values = []) {
    const names = new Map();
    for (const raw of values) {
        const name = cleanLocationName(raw);
        if (name && !names.has(name.toLocaleLowerCase())) names.set(name.toLocaleLowerCase(), name);
    }
    return [...names.values()].sort((a, b) => a.localeCompare(b));
}
export function canonicalLocationName(value, options = []) {
    const clean = cleanLocationName(value);
    return options.find((name) => name.toLocaleLowerCase() === clean.toLocaleLowerCase()) || clean;
}
const rows = (response) => Array.isArray(response) ? response : Array.isArray(response?.items) ? response.items : Array.isArray(response?.data) ? response.data : Array.isArray(response?.data?.items) ? response.data.items : [];
const activeRows = (response) => rows(response).filter((row) => !(row.is_archived ?? row.isArchived));
async function recordLocations(context, signal, { eventType, sourceModule, sourceRecordId } = {}) {
    const domain = context === 'crops' ? 'Crop' : context === 'inventory' ? 'Inventory' : eventDomain(eventType);
    const effective = domain === 'General' && sourceModule ? sourceModule : domain;
    const selected = (row) => !sourceRecordId || String(row.id) === String(sourceRecordId);
    const request = (path) => httpClient.get(path, { query: { include_archived: false }, cache: 'no-store', signal });
    const sources = [];
    if (['Crop', 'General'].includes(effective)) sources.push(request('/crops').then((data) => activeRows(data).filter(selected).map((row) => row.field)));
    if (['Inventory', 'Equipment', 'General'].includes(effective)) sources.push(request('/inventory').then((data) => activeRows(data).filter(selected).filter((row) => effective !== 'Equipment' || isEquipmentItem(row)).map((row) => row.location)));
    if (['Livestock', 'General'].includes(effective)) {
        sources.push(request('/livestock').then((data) => activeRows(data).filter(selected).map((row) => row.pen_location ?? row.penLocation ?? row.location)));
        if (!sourceRecordId) sources.push(request('/livestock/pens').then((data) => activeRows(data).filter((row) => row.status === 'Active').map((row) => row.name)));
    }
    const results = await Promise.allSettled(sources);
    if (signal?.aborted) throw new DOMException('Location lookup cancelled', 'AbortError');
    const successful = results.filter((result) => result.status === 'fulfilled');
    if (!successful.length && results.length) throw results[0].reason;
    return uniqueLocationNames(successful.flatMap((result) => result.value));
}
export const farmLocationService = Object.freeze({
    async getChoices(context, signal, filters = {}) {
        try {
            const response = await httpClient.get('/farm-locations', {
                query: { context, event_type: filters.eventType, source_module: filters.sourceModule || undefined, source_record_id: filters.sourceRecordId || undefined },
                cache: 'no-store', signal,
            });
            const names = uniqueLocationNames(rows(response));
            // Reuse actual records if an older backend or a stale lookup returns
            // an empty list while the corresponding records are already present.
            const domain = eventDomain(filters.eventType);
            const expectedDomain = domain === 'General' && filters.sourceModule ? filters.sourceModule : domain;
            // Older location APIs returned a mixed list for every event. Only
            // trust an event-specific result when the server identifies its domain.
            const scoped = context !== 'events' || expectedDomain === 'General' || response?.domain === expectedDomain;
            if (names.length && scoped) return names;
        } catch (error) {
            if (signal?.aborted || [401, 403].includes(error?.status)) throw error;
        }
        return recordLocations(context, signal, filters);
    },
});
