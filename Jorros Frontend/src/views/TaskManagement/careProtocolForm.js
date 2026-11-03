export const DRAFT_APPROVAL = "Draft - Needs Veterinarian/Agriculturist Approval";

export const emptyStep = () => ({
    sequence_number: 1,
    title: "",
    category: "inspection",
    timing_anchor: "base_date",
    offset_days: 0,
    age_start_days: "",
    age_end_days: "",
    previous_step_sequence: "",
    recurrence_interval_days: "",
    recurrence_occurrences: 1,
    instructions: "",
    priority: "Medium",
    requires_review: true,
    requires_evidence: false,
    planned_quantity: "",
    planned_unit: "",
    dose_basis: "",
    resource_product_name: "",
    resource_category: "",
    safety_notes: "",
    withdrawal_interval_days: "",
    preharvest_interval_days: "",
    source_citation: "",
});

export const emptyForm = () => ({
    id: null,
    name: "",
    module: "Livestock",
    target_type: "",
    target_breed: "",
    target_variety: "",
    production_purpose: "",
    growth_stage: "",
    description: "",
    effective_from: "",
    effective_to: "",
    approval_status: DRAFT_APPROVAL,
    source_title: "",
    source_url: "",
    citations_text: "",
    last_reviewed_date: "",
    steps: [],
});

const asText = (value) => value == null ? "" : String(value);
const trimmed = (value) => asText(value).trim();
const nullableNumber = (value) => trimmed(value) === "" ? null : Number(value);

const normalizeStep = (step, index) => ({
    sequence_number: index + 1,
    title: trimmed(step.title),
    category: trimmed(step.category),
    timing_anchor: step.timing_anchor || "base_date",
    offset_days: Number(step.offset_days || 0),
    age_start_days: nullableNumber(step.age_start_days),
    age_end_days: nullableNumber(step.age_end_days),
    previous_step_sequence: nullableNumber(step.previous_step_sequence),
    recurrence_interval_days: nullableNumber(step.recurrence_interval_days),
    recurrence_occurrences: Number(step.recurrence_occurrences || 1),
    instructions: trimmed(step.instructions) || null,
    priority: step.priority || "Medium",
    requires_review: Boolean(step.requires_review),
    requires_evidence: Boolean(step.requires_evidence),
    planned_quantity: nullableNumber(step.planned_quantity),
    planned_unit: trimmed(step.planned_unit) || null,
    dose_basis: trimmed(step.dose_basis) || null,
    resource_product_name: trimmed(step.resource_product_name) || null,
    resource_category: trimmed(step.resource_category) || null,
    safety_notes: trimmed(step.safety_notes) || null,
    withdrawal_interval_days: nullableNumber(step.withdrawal_interval_days),
    preharvest_interval_days: nullableNumber(step.preharvest_interval_days),
    source_citation: trimmed(step.source_citation) || null,
});

export const protocolPayload = (form) => ({
    name: trimmed(form.name),
    module: form.module,
    target_type: trimmed(form.target_type) || null,
    target_breed: trimmed(form.target_breed) || null,
    target_variety: trimmed(form.target_variety) || null,
    production_purpose: trimmed(form.production_purpose) || null,
    growth_stage: trimmed(form.growth_stage) || null,
    description: trimmed(form.description) || null,
    effective_from: form.effective_from || null,
    effective_to: form.effective_to || null,
    approval_status: form.approval_status,
    source_title: trimmed(form.source_title) || null,
    source_url: trimmed(form.source_url) || null,
    citations: asText(form.citations_text).split("\n").map(trimmed).filter(Boolean),
    last_reviewed_date: form.last_reviewed_date || null,
    steps: (form.steps || []).map(normalizeStep),
});

const stepTextFields = [
    "title", "category", "instructions", "priority", "planned_unit", "dose_basis",
    "resource_product_name", "resource_category", "safety_notes", "source_citation",
];
const stepOptionalNumbers = [
    "age_start_days", "age_end_days", "previous_step_sequence", "recurrence_interval_days",
    "planned_quantity", "withdrawal_interval_days", "preharvest_interval_days",
];

export const fromProtocol = (protocol) => ({
    id: protocol.id,
    name: asText(protocol.name),
    module: protocol.module || "Livestock",
    target_type: asText(protocol.target_type),
    target_breed: asText(protocol.target_breed),
    target_variety: asText(protocol.target_variety),
    production_purpose: asText(protocol.production_purpose),
    growth_stage: asText(protocol.growth_stage),
    description: asText(protocol.description),
    effective_from: protocol.effective_from || "",
    effective_to: protocol.effective_to || "",
    approval_status: protocol.approval_status || DRAFT_APPROVAL,
    source_title: asText(protocol.source_title),
    source_url: asText(protocol.source_url),
    citations_text: (protocol.citations || []).join("\n"),
    last_reviewed_date: protocol.last_reviewed_date || "",
    steps: (protocol.steps || []).map((step) => {
        const input = { ...emptyStep(), ...step };
        for (const field of stepTextFields) input[field] = asText(input[field]);
        for (const field of stepOptionalNumbers) input[field] = input[field] ?? "";
        input.timing_anchor ||= "base_date";
        input.priority ||= "Medium";
        return input;
    }),
});
