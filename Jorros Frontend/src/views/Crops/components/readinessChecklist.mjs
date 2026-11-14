// Pure validation shared by the readiness inspection modal and tests.
export function readinessInspectionValidation({ profile, findings, verdict, inspectionDate, plantingDate, today, notes }) {
    if (!profile || !Array.isArray(profile.checks)) return "Inspection reference is still loading.";
    if (!inspectionDate || inspectionDate > today) return "Choose a valid inspection date, not later than today.";
    if (plantingDate && inspectionDate < plantingDate) return "Inspection date cannot precede the saved planting date.";
    if (!['ready', 'not_ready'].includes(verdict)) return "Choose the inspection result.";
    const keys = profile.checks.map(item => item.id);
    if (keys.some(key => typeof findings[key] !== 'boolean')) return "Answer Yes or No for every inspection criterion.";
    if (verdict === 'ready' && keys.some(key => findings[key] !== true)) return "To confirm readiness, every required criterion must be Yes. Otherwise record Not yet ready.";
    if (verdict === 'not_ready' && !String(notes || '').trim()) return "Explain what still needs to improve before harvesting.";
    return "";
}

export function cropInspectionIdentity(crop) {
    const location = [crop?.field, crop?.sectionName || crop?.section_name].filter(Boolean).join(' / ');
    const code = crop?.cropCode || crop?.crop_code || (crop?.id != null ? `Crop #${crop.id}` : '');
    return [crop?.name, crop?.variety].filter(Boolean).join(' — ') + (location ? ` · ${location}` : '') + (code ? ` · ${code}` : '');
}
