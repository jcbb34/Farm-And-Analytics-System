import { schedulePayload, normalizeSchedule } from "../components/Monitoring/monitoring.js";
import { httpClient } from "./httpClient.js";

export const CROP_GROWTH_STAGES = Object.freeze([
    "Seeded",
    "Germination",
    "Seedling",
    "Vegetative",
    "Flowering",
    "Fruiting",
    "Maturity",
    "Harvest Ready",
    "Harvesting / Production",
    "Harvested",
]);

export const CROP_STAGE_PROGRESS = Object.freeze({
    Seeded: 0,
    Germination: 15,
    Seedling: 30,
    Vegetative: 50,
    Flowering: 65,
    Fruiting: 80,
    Maturity: 90,
    "Harvest Ready": 100,
    "Harvesting / Production": 100,
    Harvested: 100,
});

export function getCropStageProgress(stage) {
    return CROP_STAGE_PROGRESS[stage] ?? 0;
}

export function calculateAutomaticCropProgress(
    plantingDate,
    estimatedHarvest,
    today = new Date()
) {
    if (!plantingDate || !estimatedHarvest) {
        return 0;
    }

    const planting = new Date(`${plantingDate}T00:00:00`);
    const harvest = new Date(`${estimatedHarvest}T00:00:00`);
    const current = new Date(
        today.getFullYear(),
        today.getMonth(),
        today.getDate()
    );

    if (Number.isNaN(planting.getTime()) || Number.isNaN(harvest.getTime())) {
        return 0;
    }
    if (current <= planting) {
        return 0;
    }
    if (current >= harvest) {
        return 100;
    }

    const totalMs = harvest.getTime() - planting.getTime();
    if (totalMs <= 0) {
        return 100;
    }
    const elapsedMs = current.getTime() - planting.getTime();
    return Math.round(
        Math.max(0, Math.min(100, (elapsedMs / totalMs) * 100)) * 10
    ) / 10;
}

export function getAutomaticGrowthStage(progress) {
    const value = Math.max(0, Math.min(100, Number(progress) || 0));
    if (value >= 100) return "Harvest Ready";
    if (value >= 90) return "Maturity";
    if (value >= 80) return "Fruiting";
    if (value >= 65) return "Flowering";
    if (value >= 50) return "Vegetative";
    if (value >= 30) return "Seedling";
    if (value >= 15) return "Germination";
    return "Seeded";
}

export function getAutomaticCropStatus(progress) {
    const value = Number(progress) || 0;
    if (value <= 0) return "Planted";
    if (value < 90) return "Growing";
    return "Ready for Harvest";
}


export const WATERING_FREQUENCIES = Object.freeze([
    "Daily",
    "Twice Daily",
    "Every 2 Days",
    "3 Times per Week",
    "Weekly",
    "As Needed",
    "Rain-Fed",
    "Automated/Continuous",
]);

export const WATERING_PERIODS = Object.freeze([
    "Morning",
    "Afternoon",
    "Evening",
]);

export const WATERING_WEEKDAYS = Object.freeze([
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]);

export function serializeWateringSchedule({ frequency, days = [], periods = [] } = {}) {
    const cleanFrequency = String(frequency || "").trim();
    if (!cleanFrequency) return "Not specified";
    if (["As Needed", "Rain-Fed", "Automated/Continuous"].includes(cleanFrequency)) {
        return cleanFrequency;
    }

    const parts = [cleanFrequency];
    if (["3 Times per Week", "Weekly"].includes(cleanFrequency)) {
        parts.push(`Days: ${days.join(", ")}`);
    }
    if (periods.length) {
        parts.push(`Periods: ${periods.join(", ")}`);
    }
    return parts.join(" | ");
}

export function parseWateringSchedule(value) {
    const raw = String(value || "").trim();
    if (!raw || raw === "Not specified") {
        return { frequency: "Daily", days: [], periods: ["Morning"], legacy: "" };
    }

    const parts = raw.split("|").map((part) => part.trim()).filter(Boolean);
    const frequency = parts[0];
    if (WATERING_FREQUENCIES.includes(frequency)) {
        const daysPart = parts.find((part) => part.toLowerCase().startsWith("days:"));
        const periodsPart = parts.find((part) => part.toLowerCase().startsWith("periods:"));
        const days = daysPart
            ? daysPart.split(":", 2)[1].split(",").map((item) => item.trim()).filter((item) => WATERING_WEEKDAYS.includes(item))
            : [];
        const periods = periodsPart
            ? periodsPart.split(":", 2)[1].split(",").map((item) => item.trim()).filter((item) => WATERING_PERIODS.includes(item))
            : [];
        return {
            frequency,
            days,
            periods: periods.length ? periods : (["As Needed", "Rain-Fed", "Automated/Continuous"].includes(frequency) ? [] : ["Morning"]),
            legacy: "",
        };
    }

    const normalized = raw.toLowerCase().replaceAll("-", " ").replace(/\s+/g, " ").trim();
    if (["every morning", "daily morning", "morning daily"].includes(normalized)) {
        return { frequency: "Daily", days: [], periods: ["Morning"], legacy: "" };
    }
    if (normalized.includes("morning") && normalized.includes("afternoon")) {
        return { frequency: "Twice Daily", days: [], periods: ["Morning", "Afternoon"], legacy: "" };
    }
    if (["daily", "every day", "everyday"].includes(normalized)) {
        return { frequency: "Daily", days: [], periods: ["Morning"], legacy: "" };
    }

    return { frequency: "", days: [], periods: [], legacy: raw };
}


function dateOnly(value) {
    if (!value) {
        return "";
    }

    return String(value).slice(0, 10);
}


function normalizePestDisease(
    record = {}
) {
    return {
        id: record.id,

        cropId:
            record.cropId ??
            record.crop_id,

        dateDetected:
            record.dateDetected ??
            record.date_detected ??
            "",

        type:
            record.type ??
            record.pestDiseaseType ??
            record.pest_disease_type ??
            "",

        severity:
            record.severity ??
            "",

        affectedArea:
            record.affectedArea ??
            record.affected_area ??
            "",

        notes:
            record.notes ??
            "",

        status:
            record.status ??
            "Active",

        recordedByUserId:
            record.recordedByUserId ??
            record.recorded_by_user_id ??
            null,

        resolvedAt:
            record.resolvedAt ??
            record.resolved_at ??
            null,

        createdAt:
            record.createdAt ??
            record.created_at ??
            null,
    };
}


function normalizeGrowthRecord(
    record = {}
) {
    const growthStage =
        record.growthStage ??
        record.growth_stage ??
        "Seeded";

    return {
        id: record.id,
        cropId:
            record.cropId ??
            record.crop_id,
        growth:
            Number(
                record.growth ??
                    record.growthPercentage ??
                    record.growth_percentage ??
                    getCropStageProgress(growthStage)
            ),
        observedStage: record.observed_stage ?? record.observedStage ?? null,
        relatedTaskId: record.related_task_id ?? record.relatedTaskId ?? null,
        approvedByUserId: record.approved_by_user_id ?? record.approvedByUserId ?? null,
        growthStage,
        currentSurviving:
            record.currentSurviving ??
            record.current_surviving ??
            null,
        status:
            record.status ??
            "",
        updateDate:
            record.updateDate ??
            record.update_date ??
            "",
        notes:
            record.notes ??
            "",
        recordedByUserId:
            record.recordedByUserId ??
            record.recorded_by_user_id ??
            null,
        createdAt:
            record.createdAt ??
            record.created_at ??
            null,
    };
}


function normalizeYieldRecord(
    record = {}
) {
    return {
        id: record.id,

        cropId:
            record.cropId ??
            record.crop_id,

        harvestDate:
            record.harvestDate ??
            record.harvest_date ??
            "",

        quantityKg:
            Number(
                record.quantityKg ??
                    record.quantity_kg ??
                    0
            ),

        farmUseQuantityKg: Number(record.farmUseQuantityKg ?? record.farm_use_quantity_kg ?? 0),
        damagedQuantityKg: Number(record.damagedQuantityKg ?? record.damaged_quantity_kg ?? 0),
        reservedQuantityKg: Number(record.reservedQuantityKg ?? record.reserved_quantity_kg ?? 0),

        quality:
            record.quality ??
            "",

        harvestType:
            record.harvestType ??
            record.harvest_type ??
            "",

        yieldPerHectare:
            Number(
                record.yieldPerHectare ??
                    record.yield_per_hectare ??
                    0
            ),

        notes:
            record.notes ??
            "",

        performedByEmployeeId:
            record.performedByEmployeeId ??
            record.performed_by_employee_id ??
            null,
        relatedTaskId:
            record.relatedTaskId ??
            record.related_task_id ??
            null,
        manualReason:
            record.manualReason ??
            record.manual_reason ??
            null,
        evidenceUrl:
            record.evidenceUrl ??
            record.evidence_url ??
            null,

        recordedByUserId:
            record.recordedByUserId ??
            record.recorded_by_user_id ??
            null,

        createdAt:
            record.createdAt ??
            record.created_at ??
            null,
    };
}


function normalizeCrop(
    crop = {}
) {
    const pestRecords =
        crop.pestDiseases ??
        crop.pest_diseases ??
        [];

    const growthRecords =
        crop.growthRecords ??
        crop.growth_records ??
        [];

    const yieldRecords =
        crop.yieldRecords ??
        crop.yield_records ??
        [];

    const normalizedPests =
        pestRecords.map(normalizePestDisease);

    const unresolvedPests = normalizedPests.filter((record) =>
        ["Active", "Under Treatment"].includes(record.status)
    );

    const latestPest =
        unresolvedPests.length > 0
            ? unresolvedPests[unresolvedPests.length - 1]
            : normalizedPests.length > 0
              ? normalizedPests[normalizedPests.length - 1]
              : null;

    const updatedAt =
        crop.updatedAt ??
        crop.updated_at ??
        null;

    const plantingDate =
        crop.plantingDate ??
        crop.planting_date ??
        "";

    const estimatedHarvest =
        crop.estimatedHarvest ??
        crop.estimated_harvest ??
        "";

    const growthStage =
        crop.growthStage ??
        crop.growth_stage ??
        (crop.status === "Harvested"
            ? "Harvested"
            : "Seeded");

    const growth = Number(
        crop.growth ??
            crop.currentGrowth ??
            crop.current_growth ??
            getCropStageProgress(growthStage)
    );

    const quantityPlanted = Number(
        crop.quantityPlanted ??
            crop.quantity_planted ??
            0
    );

    const currentSurviving = Number(
        crop.currentSurviving ??
            crop.current_surviving ??
            quantityPlanted
    );

    const survivalRate =
        quantityPlanted > 0
            ? Math.round(
                  (currentSurviving / quantityPlanted) * 1000
              ) / 10
            : null;

    const status = crop.status ?? "Planted";

    return {
        id: crop.id,
        cropCode:
            crop.cropCode ??
            crop.crop_code ??
            "",
        name: crop.name ?? "",
        variety: crop.variety ?? "",
        field: crop.field ?? "",
        area: Number(
            crop.area ??
                crop.areaHectares ??
                crop.area_hectares ??
                0
        ),
        ...normalizeSchedule({ ...crop, monitoring_enabled: crop.monitoring_enabled ?? crop.monitoringEnabled ?? true }),
        estimatedProgress: crop.estimated_progress ?? crop.estimatedProgress ?? growth,
        survivalCountDate: crop.survival_count_date ?? crop.survivalCountDate ?? null,
        observedGrowthStage: crop.observed_growth_stage ?? crop.observedGrowthStage ?? null,
        lastObservationDate: crop.last_observation_date ?? crop.lastObservationDate ?? null,
        growth,
        growthStage,
        quantityPlanted,
        currentSurviving,
        survivalRate,
        status,
        statusMode: status,
        growthIsAutomatic: true,
        growthIsStageBased: false,
        plantingDate,
        estimatedHarvest,
        fertilizerQuantity: Number(
            crop.fertilizerQuantity ??
                crop.fertilizerQuantityKg ??
                crop.fertilizer_quantity_kg ??
                0
        ),
        fertilizerDate:
            crop.fertilizerDate ??
            crop.fertilizer_date ??
            "",
        pesticideUsed:
            crop.pesticideUsed ??
            crop.pesticide_used ??
            "None",
        wateringSchedule:
            crop.wateringSchedule ??
            crop.watering_schedule ??
            "Not specified",
        notes: crop.notes ?? "",
        assignedEmployeeId: crop.assignedEmployeeId ?? crop.assigned_employee_id ?? null,
        careTemplateId: crop.careTemplateId ?? crop.care_template_id ?? null,
        careProtocolName: crop.careProtocolName ?? crop.care_protocol_name ?? null,
        careProtocolVersion: crop.careProtocolVersion ?? crop.care_protocol_version ?? null,
        careProtocolStatus: crop.careProtocolStatus ?? crop.care_protocol_status ?? null,
        pestDisease: latestPest,
        activePestDisease: unresolvedPests.length > 0
            ? unresolvedPests[unresolvedPests.length - 1]
            : null,
        pestDiseases: normalizedPests,
        growthRecords:
            growthRecords.map(normalizeGrowthRecord),
        yieldRecords:
            yieldRecords.map(normalizeYieldRecord),
        readinessStatus:
            crop.readinessStatus ??
            crop.readiness_status ??
            null,
        confirmedReadyAt:
            crop.confirmedReadyAt ??
            crop.confirmed_ready_at ??
            null,
        confirmedReadyByUserId:
            crop.confirmedReadyByUserId ??
            crop.confirmed_ready_by_user_id ??
            null,
        completedAt:
            crop.completedAt ??
            crop.completed_at ??
            null,
        completedByUserId:
            crop.completedByUserId ??
            crop.completed_by_user_id ??
            null,
        harvestCount: Number(crop.harvestCount ?? crop.harvest_count ?? yieldRecords.length),
        totalHarvestQuantityKg: Number(crop.totalHarvestQuantityKg ?? crop.total_harvest_quantity_kg ?? yieldRecords.reduce((sum, record) => sum + Number(record.quantity_kg ?? record.quantityKg ?? 0), 0)),
        previousPartialHarvestTotalKg: Number(crop.previousPartialHarvestTotalKg ?? crop.previous_partial_harvest_total_kg ?? yieldRecords.filter((record) => String(record.harvest_type ?? record.harvestType ?? "").toLowerCase() === "partial harvest").reduce((sum, record) => sum + Number(record.quantity_kg ?? record.quantityKg ?? 0), 0)),
        firstHarvestDate: crop.firstHarvestDate ?? crop.first_harvest_date ?? null,
        finalHarvestDate: crop.finalHarvestDate ?? crop.final_harvest_date ?? null,
        pendingHarvestTaskId: crop.pendingHarvestTaskId ?? crop.pending_harvest_task_id ?? null,
        pendingHarvestTaskCode: crop.pendingHarvestTaskCode ?? crop.pending_harvest_task_code ?? null,
        pendingHarvestTaskStatus: crop.pendingHarvestTaskStatus ?? crop.pending_harvest_task_status ?? null,
        pendingHarvestType: crop.pendingHarvestType ?? crop.pending_harvest_type ?? null,
        pendingHarvestMessage: crop.pendingHarvestMessage ?? crop.pending_harvest_message ?? null,
        isArchived: Boolean(
            crop.isArchived ??
                crop.is_archived ??
                false
        ),
        archivedAt:
            crop.archivedAt ??
            crop.archived_at ??
            null,
        archivedByUserId:
            crop.archivedByUserId ??
            crop.archived_by_user_id ??
            null,
        createdByUserId:
            crop.createdByUserId ??
            crop.created_by_user_id ??
            null,
        createdAt:
            crop.createdAt ??
            crop.created_at ??
            null,
        updatedAt,
        lastUpdate: dateOnly(updatedAt),
    };
}


function createCropPayload(
    crop = {}
) {
    return {
        ...schedulePayload({ monitoringEnabled: true, ...crop }),
        name:
            crop.name?.trim() ?? "",

        variety:
            crop.variety?.trim() ?? "",

        field:
            crop.field?.trim() ?? "",

        area_hectares:
            Number(crop.area),

        planting_date:
            crop.plantingDate,

        estimated_harvest:
            crop.estimatedHarvest,

        quantity_planted:
            Number(crop.quantityPlanted ?? 0),

        current_surviving:
            Number(
                crop.currentSurviving ??
                    crop.quantityPlanted ??
                    0
            ),

        watering_schedule:
            crop.wateringSchedule?.trim() ||
            null,

        notes:
            crop.notes?.trim() ||
            null,

        assigned_employee_id: crop.assignedEmployeeId ? Number(crop.assignedEmployeeId) : null,
        care_template_id: crop.careTemplateId ? Number(crop.careTemplateId) : null,
    };
}


function createUpdatePayload(
    crop = {}
) {
    const payload = {};

    if (crop.name !== undefined) {
        payload.name =
            crop.name.trim();
    }

    if (crop.variety !== undefined) {
        payload.variety =
            crop.variety.trim();
    }

    if (crop.field !== undefined) {
        payload.field =
            crop.field.trim();
    }

    if (crop.area !== undefined) {
        payload.area_hectares =
            Number(crop.area);
    }

    if (
        crop.statusMode !== undefined
    ) {
        payload.status =
            crop.statusMode;
    } else if (
        crop.status !== undefined
    ) {
        payload.status =
            crop.status;
    }

    if (
        crop.plantingDate !==
        undefined
    ) {
        payload.planting_date =
            crop.plantingDate;
    }

    if (
        crop.estimatedHarvest !==
        undefined
    ) {
        payload.estimated_harvest =
            crop.estimatedHarvest;
    }

    if (crop.quantityPlanted !== undefined) {
        payload.quantity_planted =
            Number(crop.quantityPlanted);
    }

    if (crop.currentSurviving !== undefined) {
        payload.current_surviving =
            Number(crop.currentSurviving);
    }

    if (
        crop.wateringSchedule !==
        undefined
    ) {
        payload.watering_schedule =
            crop.wateringSchedule?.trim() ||
            null;
    }

    if (crop.notes !== undefined) {
        payload.notes =
            crop.notes?.trim() ||
            null;
    }

    if (crop.assignedEmployeeId !== undefined) {
        payload.assigned_employee_id = crop.assignedEmployeeId
            ? Number(crop.assignedEmployeeId)
            : null;
    }

    if (crop.careTemplateId !== undefined) {
        payload.care_template_id = crop.careTemplateId
            ? Number(crop.careTemplateId)
            : null;
    }

    if (crop.futureCareTaskAction) {
        payload.future_care_task_action = crop.futureCareTaskAction;
    }

    if (["monitoringEnabled", "monitoringStartDate", "monitoringEndDate", "monitoringFrequencyDays"].some((key) => crop[key] !== undefined)) Object.assign(payload, schedulePayload(crop));
    return payload;
}


export const cropService =
    Object.freeze({

        async getCrops(
            includeArchived = false,
            includeDetails = false
        ) {
            const response =
                await httpClient.get(
                    includeDetails
                        ? "/crops/details"
                        : "/crops",
                    {
                        query: {
                            include_archived:
                                includeArchived,
                        },
                    }
                );

            const crops =
                Array.isArray(response)
                    ? response
                    : response?.data ??
                      [];

            return crops.map(
                normalizeCrop
            );
        },


        async getCrop(cropId) {
            const response =
                await httpClient.get(
                    `/crops/${cropId}`
                );

            return normalizeCrop(
                response?.data ??
                response
            );
        },


        async createCrop(crop, { idempotencyKey } = {}) {
            const response =
                await httpClient.post(
                    "/crops",
                    createCropPayload(
                        crop
                    ),
                    {
                        headers: idempotencyKey
                            ? { "Idempotency-Key": idempotencyKey }
                            : {},
                    }
                );

            return normalizeCrop(
                response?.data ??
                response
            );
        },


        async updateCrop(
            cropId,
            crop
        ) {
            const response =
                await httpClient.put(
                    `/crops/${cropId}`,
                    createUpdatePayload(
                        crop
                    )
                );

            return normalizeCrop(
                response?.data ??
                response
            );
        },


        async archiveCrop(
            cropId
        ) {
            const response =
                await httpClient.post(
                    `/crops/${cropId}/archive`,
                    {}
                );

            return normalizeCrop(
                response?.data ??
                response
            );
        },


        async restoreCrop(
            cropId
        ) {
            const response =
                await httpClient.post(
                    `/crops/${cropId}/restore`,
                    {}
                );

            return normalizeCrop(
                response?.data ??
                response
            );
        },


        async deleteCropPermanently(cropId) {
            await httpClient.delete(
                `/crops/${cropId}/permanent`
            );

            return true;
        },


        async addGrowthRecord(
            cropId,
            data
        ) {
            const response =
                await httpClient.post(
                    `/crops/${cropId}/growth-records`,
                    {
                        current_surviving:
                            data.currentSurviving === null ||
                            data.currentSurviving === undefined ||
                            data.currentSurviving === ""
                                ? null
                                : Number(data.currentSurviving),
                        observed_stage: data.observedStage || null,
                        update_date:
                            data.updateDate,
                        notes:
                            data.notes?.trim() ||
                            null,
                        performed_by_employee_id: data.performedByEmployeeId ? Number(data.performedByEmployeeId) : null,
                        manual_reason: data.manualReason?.trim() || null,
                        evidence_url: data.evidenceUrl?.trim() || null,
                        final_harvest_confirmed: Boolean(data.finalHarvestConfirmed),
                    },
                    {
                        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
                    }
                );

            return normalizeGrowthRecord(
                response?.data ??
                response
            );
        },


        async addYieldRecord(
            cropId,
            data,
            { idempotencyKey } = {}
        ) {
            const response =
                await httpClient.post(
                    `/crops/${cropId}/yield-records`,
                    {
                        harvest_date:
                            data.harvestDate,

                        quantity_kg:
                            Number(
                                data.quantityKg
                            ),

                        farm_use_quantity_kg: Number(data.farmUseQuantityKg || 0),
                        damaged_quantity_kg: Number(data.damagedQuantityKg || 0),
                        reserved_quantity_kg: Number(data.reservedQuantityKg || 0),

                        quality:
                            data.quality ||
                            null,

                        harvest_type:
                            data.harvestType ||
                            null,

                        notes:
                            data.notes?.trim() ||
                            null,

                        performed_by_employee_id:
                            data.performedByEmployeeId
                                ? Number(data.performedByEmployeeId)
                                : null,

                        manual_reason:
                            data.manualReason?.trim() ||
                            null,

                        evidence_url:
                            data.evidenceUrl?.trim() ||
                            null,

                        final_harvest_confirmed:
                            Boolean(data.finalHarvestConfirmed),
                    },
                    {
                        headers: idempotencyKey
                            ? { "Idempotency-Key": idempotencyKey }
                            : {},
                    }
                );

            return normalizeYieldRecord(
                response?.data ??
                response
            );
        },


        async confirmReady(cropId, notes = null) {
            const response = await httpClient.post(`/crops/${cropId}/confirm-ready`, { notes: notes?.trim() || null });
            return normalizeCrop(response?.data ?? response);
        },

        async reopenCrop(cropId, reason, newStatus = "Harvesting") {
            const response = await httpClient.post(`/crops/${cropId}/reopen`, { reason: reason?.trim(), new_status: newStatus });
            return normalizeCrop(response?.data ?? response);
        },

        async addPestDisease(
            cropId,
            data
        ) {
            const response =
                await httpClient.post(
                    `/crops/${cropId}/pest-diseases`,
                    {
                        date_detected:
                            data.dateDetected,

                        pest_disease_type:
                            data.type?.trim(),

                        severity:
                            data.severity ||
                            null,

                        affected_area:
                            data.affectedArea
                                ?.trim() ||
                            null,

                        notes:
                            data.notes?.trim() ||
                            null,
                    }
                );

            return normalizePestDisease(
                response?.data ??
                response
            );
        },

        async updatePestDisease(cropId, pestId, data) {
            const response = await httpClient.put(
                `/crops/${cropId}/pest-diseases/${pestId}`,
                {
                    severity: data.severity || null,
                    affected_area: data.affectedArea?.trim() || null,
                    notes: data.notes?.trim() || null,
                    status: data.status || null,
                }
            );
            return normalizePestDisease(response?.data ?? response);
        },
    });
