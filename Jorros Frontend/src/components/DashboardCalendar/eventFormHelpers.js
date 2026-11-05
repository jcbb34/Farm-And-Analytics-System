import { eventDomain } from '../../services/eventPlanning.js';
export { eventSourceModule } from '../../services/eventPlanning.js';
export function activeEventEmployees(rows = []) {
    return (Array.isArray(rows) ? rows : []).filter((row) => !row.is_archived && row.employment_status === "Active")
        .sort((a, b) => String(a.full_name || "").localeCompare(String(b.full_name || "")));
}
export function eventNeedsResource(form) {
    if (!form.assignedEmployeeId || ['Inventory', 'Equipment'].includes(eventDomain(form.type)) || ['Weight Monitoring', 'Crop Growth Monitoring'].includes(form.type)) return false;
    const text = `${form.title || ""} ${form.type || ""}`.toLowerCase();
    return ["feed", "fertiliz", "pesticide", "pest control", "herbicide", "spray", "vaccin", "booster", "medicat", "medicine", "deworm", "vitamin", "supplement", "seed", "planting material", "disinfect", "sanitize"].some((term) => text.includes(term));
}
