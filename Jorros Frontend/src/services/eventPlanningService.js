import { httpClient } from './httpClient.js';
const rows = (data) => Array.isArray(data) ? data : data?.items || data?.data || [];
const active = (data) => rows(data).filter((row) => !(row.is_archived ?? row.isArchived));
const normalize = (data) => ({
    crops: active(data.crops || []).map((row) => ({ ...row, name: row.name, field: row.field })),
    livestock: active(data.livestock || []).map((row) => ({ ...row, name: row.name || row.record_name || row.recordName, code: row.code || row.animal_code || row.animalCode, location: row.location || row.pen_location || row.penLocation })),
    inventory: active(data.inventory || []),
});
export async function loadEventResources(signal) {
    let data;
    try {
        data = await httpClient.get('/activities/event-resources', { cache: 'no-store', signal });
        if (Array.isArray(data?.crops) && Array.isArray(data?.livestock) && Array.isArray(data?.inventory)) {
            const normalized = normalize(data);
            if (normalized.inventory.some((row) => row.location === undefined)) {
                try {
                    const items = active(await httpClient.get('/inventory', { query: { include_archived: false }, cache: 'no-store', signal }));
                    normalized.inventory = normalized.inventory.map((row) => ({ ...items.find((item) => item.id === row.id), ...row }));
                } catch (error) { if (signal?.aborted) throw error; }
            }
            return normalized;
        }
    } catch (error) {
        if (signal?.aborted || error?.status === 401) throw error;
    }
    const endpoints = [['crops', '/crops'], ['livestock', '/livestock'], ['inventory', '/inventory']];
    const results = await Promise.allSettled(endpoints.map(async ([key, path]) => [key, active(await httpClient.get(path, { query: { include_archived: false }, cache: 'no-store', signal }))]));
    if (signal?.aborted) throw new DOMException('Record lookup cancelled', 'AbortError');
    if (results.every((result) => result.status === 'rejected')) throw results[0].reason;
    return normalize(Object.fromEntries(results.filter((result) => result.status === 'fulfilled').map((result) => result.value)));
}
