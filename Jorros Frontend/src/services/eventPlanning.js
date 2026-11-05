// Shared creation choices for the calendar and Assign Task. Existing category
// strings remain valid for historical records and custom general assignments.
export const WORK_TYPE_GROUPS = [
    { label: 'Crops', module: 'Crop', types: ['Planting', 'Irrigation', 'Fertilization', 'Pest Control', 'Harvesting', 'Crop Growth Monitoring'] },
    { label: 'Livestock', module: 'Livestock', types: ['Livestock Feeding', 'Weight Monitoring', 'Livestock Health Check', 'Vaccination'] },
    { label: 'Inventory', module: 'Inventory', types: ['Inventory Restocking'] },
    { label: 'General', module: 'General', types: ['Farm Inspection', 'Other'] },
];
export const WORK_TYPES = WORK_TYPE_GROUPS.flatMap((group) => group.types);
export const workTypeLabel = (type) => type === 'Irrigation' ? 'Watering / Irrigation' : type;
const equipmentCategories = new Set(['equipment', 'tools', 'machinery', 'machine', 'machines', 'farm equipment', 'farm tools', 'implements']);
export function eventDomain(type) {
    const group = WORK_TYPE_GROUPS.find((entry) => entry.types.includes(type));
    if (group) return group.module;
    if (type === 'Watering') return 'Crop';
    // Read compatibility for older events; this is not a new-work choice.
    if (type === 'Equipment Maintenance') return 'Equipment';
    return 'General';
}
export function taskCategoryUpdate(form, category) {
    const domain = eventDomain(category);
    const module = ['Crop', 'Livestock', 'Inventory'].includes(domain) ? domain : form.source_module === 'Inventory' ? '' : form.source_module;
    return {
        ...form, category, source_module: module,
        ...(['Weight Monitoring', 'Crop Growth Monitoring'].includes(category) ? { requires_review: true, requires_evidence: true } : {}),
        source_type: module === 'Inventory' ? 'inventory_restock_plan' : module ? 'manual_work' : '',
        source_record_id: module === form.source_module ? form.source_record_id : '',
        related_to: module === form.source_module ? form.related_to : '',
        location: module === form.source_module ? form.location : '',
        planned_inventory_item_id: '', planned_usage_type: '', planned_quantity: '', planned_unit: '', feeding_slot: '',
    };
}
export const isEquipmentItem = (item) => equipmentCategories.has(String(item?.category || '').trim().toLowerCase());
export function eventSourceModule(type) {
    const domain = eventDomain(type);
    return domain === 'Equipment' ? 'Inventory' : domain === 'General' ? 'Crop' : domain;
}
export function eventRecordChoices(form, resources) {
    const domain = eventDomain(form.type);
    if (domain === 'Equipment') return resources.inventory.filter(isEquipmentItem);
    const module = domain === 'General' ? form.sourceModule : domain;
    return module === 'Livestock' ? resources.livestock : module === 'Inventory' ? resources.inventory : resources.crops;
}
export function eventRecordLocation(record, module) {
    return module === 'Crop' ? record?.field || '' : record?.location || record?.pen_location || '';
}
