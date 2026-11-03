const cropEvents = new Set(['Planting', 'Fertilization', 'Irrigation', 'Harvesting', 'Pest Control']);
const livestockEvents = new Set(['Livestock Health Check', 'Livestock Feeding', 'Vaccination']);
const equipmentCategories = new Set(['equipment', 'tools', 'machinery', 'machine', 'machines', 'farm equipment', 'farm tools', 'implements']);
export function eventDomain(type) {
    if (cropEvents.has(type)) return 'Crop';
    if (livestockEvents.has(type)) return 'Livestock';
    if (type === 'Inventory Restocking') return 'Inventory';
    if (type === 'Equipment Maintenance') return 'Equipment';
    return 'General';
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
