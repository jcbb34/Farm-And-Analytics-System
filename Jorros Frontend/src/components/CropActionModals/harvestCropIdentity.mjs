/** Identify actual planting records in harvest workflows (never infer a section from crop variety). */
export function harvestSectionLabel(crop) {
    const name = String(crop?.sectionName ?? crop?.section_name ?? "").trim();
    if (name) return name;
    const rawId = crop?.sectionId ?? crop?.section_id;
    const id = Number(rawId);
    return rawId != null && rawId !== "" && Number.isInteger(id) && id > 0
        ? `Section ID ${id}` : "No section assigned";
}

export function harvestCropRecordCode(crop) {
    const code = String(crop?.cropCode ?? crop?.crop_code ?? "").trim();
    if (code) return code;
    const id = crop?.id;
    return id != null && String(id).trim() ? `Record #${id}` : "No record code";
}

export function harvestCropOptionLabel(crop) {
    const name = String(crop?.name ?? "Crop").trim() || "Crop";
    const variety = String(crop?.variety ?? "").trim();
    const fullField = String(crop?.field ?? "").trim();
    // Keep native select options concise; the full field is shown in the selection summary.
    const field = fullField.split(/\s+[—–-]\s+/)[0].trim() || "Unassigned field";
    return `${name}${variety ? ` (${variety})` : ""} — ${field} / ${harvestSectionLabel(crop)} — ${harvestCropRecordCode(crop)}`;
}

export function harvestYieldPerHectare(quantityKg, areaHectares) {
    const quantity = Number(quantityKg);
    const area = Number(areaHectares);
    if (quantityKg == null || quantityKg === "" || !Number.isFinite(quantity) || quantity <= 0 ||
        areaHectares == null || areaHectares === "" || !Number.isFinite(area) || area <= 0) return null;
    return quantity / area;
}
