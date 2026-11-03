import { farmDateKey } from "../../utils/farmCalendar.js";

export function scheduleForm(record = {}, crop = false) {
    return {
        monitoringEnabled: record.monitoringEnabled ?? crop,
        monitoringStartDate: record.monitoringStartDate || "",
        monitoringEndDate: record.monitoringEndDate || "",
        monitoringFrequencyDays: record.monitoringFrequencyDays ?? "",
    };
}

export function schedulePayload(value = {}) {
    return {
        monitoring_enabled: Boolean(value.monitoringEnabled),
        monitoring_start_date: value.monitoringStartDate || null,
        monitoring_end_date: value.monitoringEndDate || null,
        monitoring_frequency_days: value.monitoringFrequencyDays === "" || value.monitoringFrequencyDays == null ? null : Number(value.monitoringFrequencyDays),
    };
}

export function normalizeSchedule(value = {}) {
    return {
        monitoringSummary: value.monitoring_summary ?? value.monitoringSummary ?? null,
        monitoringEnabled: value.monitoring_enabled ?? value.monitoringEnabled ?? false,
        monitoringStartDate: value.monitoring_start_date ?? value.monitoringStartDate ?? "",
        monitoringEndDate: value.monitoring_end_date ?? value.monitoringEndDate ?? "",
        monitoringFrequencyDays: value.monitoring_frequency_days ?? value.monitoringFrequencyDays ?? "",
    };
}

export function assertMonitoringSaved(payload, record = {}) {
    if (!Object.hasOwn(payload, "monitoring_enabled")) return;
    const fields = {
        monitoring_enabled: "monitoringEnabled",
        monitoring_start_date: "monitoringStartDate",
        monitoring_end_date: "monitoringEndDate",
        monitoring_frequency_days: "monitoringFrequencyDays",
        assigned_employee_id: "assignedEmployeeId",
    };
    for (const [field, alias] of Object.entries(fields)) {
        if (!Object.hasOwn(payload, field)) continue;
        const actual = Object.hasOwn(record, field) ? record[field] : record[alias];
        if (actual === payload[field]) continue;
        const error = new Error("Monitoring settings were not confirmed by the backend. Restart the backend with the updated project files, then save again. Your entries are still in this form.");
        error.code = "MONITORING_SAVE_NOT_CONFIRMED";
        throw error;
    }
}

export function initialObservation(context) {
    if (!context) return null;
    const today = farmDateKey();
    return { resource_type: context.resource_type, observation_date: today > context.latest_date ? context.latest_date : today,
        observed_stage: "", current_surviving: "", animals_measured: "", average_weight_kg: "", total_measured_weight_kg: "", min_weight_kg: "", max_weight_kg: "",
        _totalWeightAuto: true };
}

export function observationPayload(value, context) {
    if (!context) return null;
    const animalsMeasured = value?.animals_measured === "" || value?.animals_measured == null ? null : Number(value.animals_measured);
    const avgWeight = value?.average_weight_kg === "" || value?.average_weight_kg == null ? null : Number(value.average_weight_kg);
    const minWeight = value?.min_weight_kg === "" || value?.min_weight_kg == null ? null : Number(value.min_weight_kg);
    const maxWeight = value?.max_weight_kg === "" || value?.max_weight_kg == null ? null : Number(value.max_weight_kg);
    const currentSurviving = value?.current_surviving === "" || value?.current_surviving == null ? null : Number(value.current_surviving);
    // Auto-compute total from animals_measured × average_weight_kg
    const totalMeasuredWeight = (animalsMeasured !== null && avgWeight !== null) ? Number((animalsMeasured * avgWeight).toFixed(3)) : null;
    const result = {
        ...value,
        resource_type: context.resource_type,
        observed_stage: value?.observed_stage || null,
        current_surviving: currentSurviving,
        animals_measured: animalsMeasured,
        average_weight_kg: avgWeight,
        total_measured_weight_kg: totalMeasuredWeight,
        min_weight_kg: minWeight,
        max_weight_kg: maxWeight,
    };
    return result;
}

export function validateObservation(value, context) {
    if (!context) return "";
    if (!value?.observation_date) return "Enter the monitoring observation date.";
    if (context.resource_type === "Crop" && (!value.observed_stage || value.current_surviving === "" || value.current_surviving == null)) return "Enter the observed crop stage and surviving plant count.";
    if (context.resource_type === "Livestock") {
        const animalsMeasured = Number(value.animals_measured);
        const avgWeight = Number(value.average_weight_kg);
        const minWeight = Number(value.min_weight_kg);
        const maxWeight = Number(value.max_weight_kg);
        if (!(animalsMeasured > 0) || !(avgWeight > 0)) return "Enter the number of animals measured and average weight (must be greater than zero).";
        if (animalsMeasured > 1) {
            if (!(minWeight > 0) || !(maxWeight > 0)) return "Record minimum and maximum measured weights (must be greater than zero) when measuring more than one animal.";
            if (minWeight > avgWeight || maxWeight < avgWeight) return "Minimum weight must be ≤ average weight ≤ maximum weight.";
        }
    }
    return "";
}
