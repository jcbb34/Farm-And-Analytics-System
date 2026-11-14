/** Physical section labels on crop list rows; never infer a location from crop variety. */
export function sectionLabelForCrop(crop) {
    if (!crop || typeof crop !== "object") return null;
    const label = String(crop.sectionName ?? crop.section_name ?? "").trim();
    if (label) return label;
    const sectionId = crop.section_id ?? crop.sectionId;
    const number = Number(sectionId);
    return sectionId != null && sectionId !== "" && Number.isInteger(number) && number > 0
        ? `Section ID ${number}` : null;
}
